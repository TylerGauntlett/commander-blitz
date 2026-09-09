"""A planeswalker's printed starting loyalty, carried from Scryfall to the card.

Rule 306.5b: a planeswalker's loyalty **is** counters, and the loader compiles
the printed number into a `self_enters_with_counters` replacement exactly as it
compiles a Saga's lore counter. So a planeswalker written without one does not
arrive smaller -- it arrives at zero and 704.5i removes it from the battlefield
before anybody gets priority. There is no weaker version of the card to fall back
on; loyalty is the one printed characteristic a planeswalker cannot exist without.

The catalog stored it nowhere. Scryfall keeps loyalty in its own field rather
than in `power` or `toughness`, and the index read neither, so **all 327
planeswalkers in the catalog reported no loyalty at all** and every one of them
was unauthorable for that reason alone -- not because the DSL could not say the
card, which it has been able to say since planeswalkers landed, but because
nothing in the repository knew the number. The Theorist, Jace Beleren is the
witness: a worker wrote out three loyalty abilities correctly and then had to
stop, because the starting value existed in no file it could read.

`loyalty` and `back_loyalty` are appended to `COLUMNS` and listed in
`LATE_COLUMNS`, which is the established shape for a column added after the first
build: an index written before them still opens, with `NULL` selected for
whichever are absent, so a fresh clone boots on whatever it was handed.
"""

from __future__ import annotations

import sqlite3

import pytest

from automtg.cards.images import COLUMNS, LATE_COLUMNS, load_index
from automtg.cards.proxy import build_proxy, facts_from_index

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def index():
    return load_index()


class TestTheColumnExists:
    def test_loyalty_is_in_the_schema(self):
        assert "loyalty" in COLUMNS
        assert "back_loyalty" in COLUMNS

    def test_it_is_a_late_column(self):
        """An index built before this must still open.

        `CardIndex` selects `NULL` for absent columns rather than failing, and
        that is the whole reason `LATE_COLUMNS` exists -- omitting the new pair
        would make every checkout with an older `cards.sqlite` fail to boot the
        server, for a field only the authoring pipeline reads.
        """
        assert {"loyalty", "back_loyalty"} <= LATE_COLUMNS

    def test_the_committed_index_actually_has_it(self, index):
        assert index.late_columns_present


class TestWhatTheCatalogNowKnows:
    def test_a_planeswalker_carries_its_printed_loyalty(self, index):
        entry = index.lookup("The Theorist, Jace Beleren")
        assert entry is not None
        assert entry.loyalty == "3"

    def test_a_nonplaneswalker_carries_none(self, index):
        """Read off the same column, so a bug that filled it for everything
        would be visible here rather than as a Lightning Bolt with loyalty."""
        assert index.lookup("Lightning Bolt").loyalty in (None, "")

    def test_almost_every_planeswalker_has_one_now(self):
        """The claim, measured. Before this the answer was zero of 327.

        Not `== all`: the rows without one are joined `//` printings and back
        faces, whose loyalty lives on the face rather than the record. A floor
        rather than an exact number so a catalog refresh that adds planeswalkers
        does not fail this, while dropping the column wholesale still does.
        """
        con = sqlite3.connect("data/catalog/cards.sqlite")
        try:
            total = con.execute(
                "SELECT COUNT(*) FROM cards WHERE type_line LIKE '%Planeswalker%'"
            ).fetchone()[0]
            with_loyalty = con.execute(
                "SELECT COUNT(*) FROM cards WHERE type_line LIKE '%Planeswalker%'"
                " AND loyalty IS NOT NULL AND loyalty != ''"
            ).fetchone()[0]
        finally:
            con.close()
        assert total > 300
        assert with_loyalty > total * 0.9


class TestTheProxyCarriesItThrough:
    """The number reaches the card; the abilities deliberately do not.

    Those are different halves of the printed card -- loyalty is a
    characteristic and the `+1:` lines are rules text -- and the proxy tier has
    always translated the first and never the second. Carrying loyalty does not
    make the proxy able to write a planeswalker; it makes a *worker* able to,
    which is the whole point, since the packet's `starting_point` is built from
    exactly this model.
    """

    def test_the_generated_card_has_the_printed_number(self, index):
        result = build_proxy(facts_from_index(index.lookup("The Theorist, Jace Beleren")))
        assert result.model is not None
        assert result.model.loyalty == 3

    def test_it_still_says_the_abilities_are_not_generated(self, index):
        result = build_proxy(facts_from_index(index.lookup("The Theorist, Jace Beleren")))
        assert any("loyalty abilities are not generated" in n for n in result.notes)

    def test_a_printed_x_is_none_and_says_so(self, index):
        """Nissa, Steward of Elements is the only one, and 0 is the one wrong
        answer available: a planeswalker entering with no loyalty is removed by
        704.5i immediately, so it would be a card that visibly never exists
        rather than one that is merely approximate."""
        result = build_proxy(facts_from_index(index.lookup("Nissa, Steward of Elements")))
        assert result.model.loyalty is None
        assert any("chosen as the spell is cast" in n for n in result.notes)

    def test_the_two_causes_of_a_missing_loyalty_are_told_apart(self, index):
        """A printed `X` and a catalog that is simply short want different work,
        so they are different notes -- one is a card to model, the other a
        column to fill."""
        nissa = build_proxy(facts_from_index(index.lookup("Nissa, Steward of Elements")))
        assert not any("no printed loyalty in the catalog" in n for n in nissa.notes)

    def test_a_creature_gets_no_loyalty(self, index):
        """`_loyalty` returns early on card type, so a creature whose catalog row
        somehow carried the field would still come out clean."""
        result = build_proxy(facts_from_index(index.lookup("Grizzly Bears")))
        assert result.model is not None
        assert result.model.loyalty is None
