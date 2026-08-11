"""Hold `docs/keywords.md` to the engine it claims to describe.

The census in that file exists so the twenty-third keyword is a lookup rather
than an argument -- it routes every Magic keyword to one of the engine's
mechanisms and marks it shipped, free, routed, blocked or refused. A census is
only worth reading if its shipped column is true, and a hand-written table of
~180 rows goes stale the first time `/extend-dsl` ships anything.

The failure is silent in the direction that matters. A keyword added to
`Keyword` and never written down leaves the census quietly claiming the engine
cannot do something it now can, which is exactly the reading that sends somebody
to build it twice. Nothing about either file would look wrong.

So the shipped rows are checked, in both directions:

- every value in `Keyword` appears exactly once as a shipped row, so shipping
  without documenting fails here rather than in six months' confusion;
- every engine name a shipped row claims resolves against a real registry, so
  the census cannot claim capability the engine does not have.

The other four statuses are deliberately *not* checked. They are editorial
judgements made by reading the DSL, and the honest way to settle one is to point
`/author-cards` at a card and see whether it produces a card or a gap record --
a test that could confirm them would have to be the authoring pipeline itself.
What is checked is that they are drawn from the closed vocabulary, because a
census that drifts into freehand statuses has stopped being a census.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from automtg.cards.loader import STATIC_EFFECTS
from automtg.cards.schema import CardModel
from automtg.engine.effects import known_ops
from automtg.engine.enums import Keyword

CENSUS = Path(__file__).resolve().parents[2] / "docs" / "keywords.md"

#: The closed status vocabulary the document defines for itself.
STATUSES = frozenset({"shipped", "free", "routed", "blocked", "refused"})

#: A census row: `| Keyword | Status | Mechanism | Engine name |`.
ROW = re.compile(r"^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|\s*$")

#: The page's four census tables, by heading.  The routing-rule table is also
#: four columns wide, so the parser tracks headings rather than guessing from
#: the shape of a row -- guessing is what let the routing table in.
CENSUS_SECTIONS = frozenset(
    {
        "## Evergreen keywords",
        "## Keyword actions",
        "## Expansion keywords",
        "## Ability words",
    }
)


def _cell(text: str) -> str:
    """One table cell, stripped of markdown decoration."""
    return text.strip().strip("*").replace("`", "").replace("†", "").strip()


def _rows() -> list[tuple[str, str, str]]:
    """Every census row as `(keyword, status, engine_name)`.

    Header and separator rows are dropped; everything else inside a census
    section is returned *including* rows with an unrecognised status, so the
    closed-vocabulary check has something to fail on.
    """
    out: list[tuple[str, str, str]] = []
    inside = False
    for line in CENSUS.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() in CENSUS_SECTIONS
            continue
        if not inside or not (m := ROW.match(line)):
            continue
        keyword, status, _mechanism, engine = (_cell(g) for g in m.groups())
        if keyword == "Keyword" or set(status) <= set("-: "):
            continue
        out.append((keyword, status, engine))
    return out


@pytest.fixture(scope="module")
def rows() -> list[tuple[str, str, str]]:
    found = _rows()
    # A parser that silently matched nothing would make every assertion below
    # vacuously true, which is the one way this file could fail to do its job.
    assert len(found) > 100, f"parsed only {len(found)} census rows -- parser broken?"
    return found


@pytest.fixture(scope="module")
def shipped(rows) -> list[tuple[str, str]]:
    found = [(kw, engine) for kw, status, engine in rows if status == "shipped"]
    assert found, "no shipped rows parsed -- the census tables moved or renamed"
    return found


class TestEveryShippedKeywordIsDocumented:
    """`Keyword` is the authority; the census must cover all of it."""

    def test_every_keyword_appears_as_a_shipped_row(self, shipped):
        named = [engine for _, engine in shipped]
        missing = {k.value for k in Keyword} - set(named)
        assert not missing, (
            f"{sorted(missing)} are in `Keyword` but not marked shipped in "
            f"{CENSUS.name}. Shipping a keyword includes censusing it."
        )

    def test_no_keyword_is_documented_twice(self, shipped):
        named = [engine for _, engine in shipped if engine in {k.value for k in Keyword}]
        duplicated = {n for n in named if named.count(n) > 1}
        assert not duplicated, f"{sorted(duplicated)} appear on more than one row"


class TestEveryClaimResolves:
    """A shipped row may only name something that exists."""

    def test_engine_names_are_real(self, shipped):
        known = (
            {k.value for k in Keyword}
            | set(STATIC_EFFECTS)
            | set(CardModel.model_fields)
            | set(known_ops())
        )
        bogus = {engine for _, engine in shipped if engine != "—" and engine not in known}
        assert not bogus, (
            f"{sorted(bogus)} are named by shipped rows but are not a Keyword, a "
            f"static effect, a CardModel field or a registered op. Use — where the "
            f"mechanism has no single identifier."
        )


class TestTheStatusVocabularyIsClosed:
    """Drift into freehand statuses is how a census stops meaning anything."""

    def test_no_row_escaped_the_vocabulary(self, rows):
        rogue = [(kw, status) for kw, status, _ in rows if status not in STATUSES]
        assert not rogue, (
            f"census rows with an unrecognised status: {rogue}. "
            f"Statuses must be one of {sorted(STATUSES)}."
        )
