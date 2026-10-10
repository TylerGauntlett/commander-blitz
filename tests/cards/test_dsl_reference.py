"""Hold `docs/card-dsl-reference.md` and its generator to the engine.

`docs/card-dsl.md` used to open with "139 of them" and a hand-kept op table, and
the number was wrong within a release: `/extend-dsl` registers an op in `OPS`
and nowhere else. `scripts/gen_dsl_reference.py` reads every family's *names*
off the engine and keeps only the *descriptions* by hand, so the one way the
reference can lie is a description missing or orphaned -- and that is what is
checked here, in both directions, for every family:

- every name the engine has is described, so shipping an op without a line in
  the script fails here rather than leaving the reference quietly short;
- every description names something the engine still has, so the reference
  cannot claim vocabulary the engine lost.

Then the committed file must equal what the script generates now, and every
link it emits must land on a real heading in `docs/card-dsl.md` or
`docs/card-dsl-cookbook.md`. The heading lookup reads the live docs, so moving a
section between those two files is caught as a stale reference -- one
`--write` away from green -- rather than as a dead link.

Same pattern as `test_keyword_census.py`: the document is held to the engine,
never the engine to the document.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_dsl_reference.py"
REFERENCE = ROOT / "docs" / "card-dsl-reference.md"

#: A rendered link cell: `[label](file#slug)`.
LINK = re.compile(r"\[[^\]]*\]\(([^)#]*)#([^)]+)\)")

#: The headings another document links to by slug; renaming one is a
#: cross-document break, which is why they are pinned here and not only in the
#: script.
REQUIRED_SECTIONS = (
    "Effect ops",
    "Selectors",
    "Player specs",
    "Values",
    "Conditions",
    "Trigger events",
    "Trigger filters",
    "Static effects",
    "Player-wide statics",
    "Grantable statics",
    "Cost reduction",
    "Ability costs",
    "Card-level costs",
    "Keywords",
    "Card types and supertypes",
    "Durations",
    "Decision kinds",
)


@pytest.fixture(scope="module")
def gen():
    """The generator module, imported from `scripts/` by path."""
    spec = importlib.util.spec_from_file_location("gen_dsl_reference", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gen_dsl_reference", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated(gen) -> tuple[str, list[str], list[str]]:
    return gen.generate()


class TestEveryFamilyMatchesTheEngine:
    """The curated maps and the engine's registries agree, both ways."""

    def test_no_family_has_an_undescribed_or_orphaned_name(self, gen):
        problems = [p for fam in gen.families() for p in gen.coverage_problems(fam)]
        assert not problems, "\n".join(problems)

    def test_every_family_is_non_empty(self, gen):
        # A registry that imported as empty would make every map "complete".
        empty = [fam.title for fam in gen.families() if not fam.names]
        assert not empty, f"{empty} enumerated nothing -- import broken?"

    def test_the_required_sections_are_emitted_under_their_exact_titles(self, gen):
        titles = [fam.title for fam in gen.families()]
        assert list(titles[: len(REQUIRED_SECTIONS)]) == list(REQUIRED_SECTIONS), (
            "another document links to these headings by slug; keep them first and verbatim"
        )


class TestTheCommittedFileIsCurrent:
    """What is on disk is what the script would write now."""

    def test_reference_equals_generated_text(self, generated):
        text, errors, warnings = generated
        assert not errors, "\n".join(errors)
        assert not warnings, "\n".join(warnings)
        assert REFERENCE.exists(), f"{REFERENCE.name} is missing; run the script with --write"
        assert REFERENCE.read_text(encoding="utf-8") == text, (
            f"{REFERENCE.name} is stale; run `python scripts/gen_dsl_reference.py --write`"
        )

    def test_reference_uses_lf_line_endings(self):
        assert b"\r" not in REFERENCE.read_bytes(), f"{REFERENCE.name} has CRLF line endings"


class TestEveryLinkResolves:
    """A link in the reference lands on a heading that exists right now."""

    def test_every_source_doc_link_resolves(self, gen):
        docs = ROOT / "docs"
        text = REFERENCE.read_text(encoding="utf-8")
        own = gen.headings_in(REFERENCE)
        dead: list[str] = []
        for file, slug in LINK.findall(text):
            if file == "":
                if slug not in own:
                    dead.append(f"#{slug}")
                continue
            if file not in gen.SOURCE_DOCS:
                continue  # keywords.md and friends are somebody else's contract
            path = docs / file
            if not path.exists() or slug not in gen.headings_in(path):
                dead.append(f"{file}#{slug}")
        assert not dead, f"links to headings that do not exist: {sorted(set(dead))}"

    def test_slug_rule_matches_github(self, gen):
        # The anchors card-dsl.md already uses for its own cross-references.
        assert gen.slugify("Can't attack or block **alone**") == "cant-attack-or-block-alone"
        assert (
            gen.slugify("Gift — a promise made to one opponent, for nothing")
            == "gift--a-promise-made-to-one-opponent-for-nothing"
        )
        assert gen.slugify('"If it was cast" — 603.6e') == "if-it-was-cast--6036e"
        assert gen.slugify("`exert` — the keyword as a cost") == "exert--the-keyword-as-a-cost"
