"""Hold the client's selection audit to the engine it describes.

`frontend/src/components/game/decisionAudit.ts` is a table of every question
the engine can ask -- each `DecisionKind`, and each `purpose` tag the engine
stamps on a decision's context -- against the surface that answers it today
and the press ceiling it is held to. A table like that is only worth reading
while it is complete, and the failure is silent in the direction that matters:
a purpose added to a new op with no row leaves the audit quietly claiming the
question does not exist, which is exactly the reading that lets a new surface
drift away from the rule.

So the rows are checked in both directions, the way `test_keyword_census.py`
checks the keyword census:

- every value of `DecisionKind` has a row, and every kind the engine actually
  constructs a `PendingDecision` of has a row that names a surface;
- every purpose literal the engine passes to an asking helper -- by keyword,
  by position, as a parameter default, or inside a `context` dict -- has a row,
  and every purpose a row names is one of those, so the audit cannot describe
  a question the engine no longer asks.

The purposes are found by walking the engine's AST rather than by grepping,
because most call sites pass the tag positionally (`choose_objects(ctx, spec,
"Sacrifice", "sacrifice")`) and a regex that missed them would be the silent
failure again. A tag passed through a variable is not found; that is the one
shape this cannot see, and no site in the engine uses it today.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from commanderblitz.engine.enums import DecisionKind

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "src" / "commanderblitz" / "engine"
AUDIT = ROOT / "frontend" / "src" / "components" / "game" / "decisionAudit.ts"

#: The first two fields of a row, which the module promises to keep on one
#: line: `kind: "choose_objects", purpose: "sacrifice",` or `purpose: null,`.
ROW = re.compile(r'kind:\s*"([a-z_]+)",\s*purpose:\s*(null|"([a-z_]+)")')
#: The `today` list of the row that follows a `kind:` line, up to its `]`.
TODAY = re.compile(r"today:\s*\[([^\]]*)\]")


def _purpose_param(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, str | None] | None:
    """Where ``purpose`` sits in a signature: its positional index (or -1 for
    keyword-only) and its string default, if any."""
    params = node.args.posonlyargs + node.args.args
    names = [p.arg for p in params]
    if "purpose" in names:
        index = names.index("purpose")
        first_default = len(params) - len(node.args.defaults)
        default = None
        if index >= first_default:
            value = node.args.defaults[index - first_default]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                default = value.value
        return index, default
    kw_names = [p.arg for p in node.args.kwonlyargs]
    if "purpose" in kw_names:
        value = node.args.kw_defaults[kw_names.index("purpose")]
        default = value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None
        return -1, default
    return None


def _trees() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in sorted(ENGINE.rglob("*.py"))]


def engine_purposes() -> dict[str, set[str]]:
    """Every purpose literal the engine stamps, with the sites that stamp it."""
    trees = _trees()
    askers: dict[str, int] = {}
    found: dict[str, set[str]] = {}
    for path, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where = _purpose_param(node)
                if where is None:
                    continue
                index, default = where
                askers[node.name] = index
                if default is not None:
                    found.setdefault(default, set()).add(f"{path.name}:{node.lineno} default of {node.name}")
    # Mana payment takes a `purpose` too (`costs.SpendPurpose`), and it is a
    # different word for a different thing. Those take no string literal, so
    # they never contribute a tag; they are in `askers` harmlessly.
    for path, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name in askers:
                    for keyword in node.keywords:
                        value = keyword.value
                        if keyword.arg == "purpose" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                            found.setdefault(value.value, set()).add(f"{path.name}:{node.lineno} {name}(purpose=)")
                    index = askers[name]
                    if 0 <= index < len(node.args):
                        arg = node.args[index]
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            found.setdefault(arg.value, set()).add(f"{path.name}:{node.lineno} {name}(#{index})")
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "purpose"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.setdefault(value.value, set()).add(f"{path.name}:{node.lineno} context dict")
    return found


def raised_kinds() -> set[str]:
    """Every `DecisionKind` the engine constructs a `PendingDecision` of."""
    out: set[str] = set()
    for _, tree in _trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "PendingDecision"):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if keyword.arg == "kind" and isinstance(value, ast.Attribute):
                    out.add(DecisionKind[value.attr].value)
    return out


def audit_rows() -> list[tuple[str, str | None, list[str]]]:
    """`(kind, purpose, today)` per row, in file order."""
    text = AUDIT.read_text(encoding="utf-8")
    rows = []
    for match in ROW.finditer(text):
        today_match = TODAY.search(text, match.end())
        assert today_match is not None, f"no `today` after {match.group(0)}"
        today = re.findall(r'"([a-z]+)"', today_match.group(1))
        rows.append((match.group(1), match.group(3), today))
    return rows


@pytest.fixture(scope="module")
def rows() -> list[tuple[str, str | None, list[str]]]:
    found = audit_rows()
    assert len(found) > len(DecisionKind), "the row parser matched almost nothing; its shape has moved"
    return found


@pytest.fixture(scope="module")
def purposes() -> dict[str, set[str]]:
    found = engine_purposes()
    assert {"sacrifice", "target", "mulligan_bottom"} <= set(found), "the AST walk found too little"
    return found


def test_every_kind_has_a_row(rows):
    kinds = {kind for kind, _, _ in rows}
    missing = {kind.value for kind in DecisionKind} - kinds
    assert not missing, f"DecisionKind values with no audit row: {sorted(missing)}"


def test_every_row_names_a_real_kind(rows):
    known = {kind.value for kind in DecisionKind}
    unknown = sorted({kind for kind, _, _ in rows} - known)
    assert not unknown, f"audit rows for kinds the engine does not have: {unknown}"


def test_every_raised_kind_has_a_surface(rows):
    """A kind the engine constructs is answered somewhere; one it only declares
    may honestly say it is answered nowhere."""
    raised = raised_kinds()
    assert raised, "no PendingDecision construction found; the walk is broken"
    silent = sorted({kind for kind, _, today in rows if kind in raised and not today})
    assert not silent, f"kinds the engine raises whose every row names no surface: {silent}"
    # The honest case is held too, so a row cannot claim a surface for a
    # question nobody asks.
    declared_only = {kind.value for kind in DecisionKind} - raised
    claimed = sorted({kind for kind, _, today in rows if kind in declared_only and today})
    assert not claimed, f"kinds nothing raises whose row claims a surface: {claimed}"


def test_every_engine_purpose_has_a_row(rows, purposes):
    tagged = {purpose for _, purpose, _ in rows if purpose is not None}
    missing = {purpose: sorted(sites) for purpose, sites in purposes.items() if purpose not in tagged}
    assert not missing, f"purposes the engine stamps with no audit row: {missing}"


def test_every_row_purpose_is_stamped_by_the_engine(rows, purposes):
    tagged = {purpose for _, purpose, _ in rows if purpose is not None}
    stale = sorted(tagged - set(purposes))
    assert not stale, f"audit rows for purposes the engine no longer stamps: {stale}"


def test_rows_are_unique(rows):
    keys = [(kind, purpose) for kind, purpose, _ in rows]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicates, f"the same question has two rows: {duplicates}"
