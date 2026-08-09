"""Every card in the catalog, put through the generator for real.

`test_proxy.py` checks the branches with inputs chosen to exercise them. This
file checks the claim in the roadmap -- *all* card support -- against the actual
32,827 rows, because the shapes that break a parser are the ones nobody would
think to invent: a creature with `*` power, a name that is entirely punctuation,
a land that produces mana it does not tap for, an Un-set card with half mana.

The failure this is really guarding is not "one card generates badly". It is
that ``compile_card`` raises ``DslError``, which propagates out through
``CardRegistry.from_paths`` -- so a *single* bad card in an imported deck would
stop the whole registry loading at boot and take every other deck with it.

Skipped when the catalog has not been built, like the rest of the art tests: a
fresh clone must be able to run the suite.
"""

from __future__ import annotations

import collections

import pytest

from automtg.cards.images import catalog_path, load_index
from automtg.cards.loader import compile_card
from automtg.cards.proxy import build_proxy, facts_from_index

pytestmark = pytest.mark.skipif(
    not catalog_path().exists(),
    reason="no card catalog; run scripts/build_card_index.py",
)

#: Every 40th row -- ~820 cards, a couple of seconds.  The whole catalog is a
#: minute, which is too slow for a suite people run constantly; the stride is
#: deterministic so a failure is reproducible.
STRIDE = 40

#: Floor, not a target.  Measured at ~4.4% over the full catalog: most real cards
#: say something, and only vanillas, lands and simple rocks come through whole.
#: This exists to catch keyword lifting or mana-ability generation silently
#: breaking, which would drive it to zero without any test failing.
MIN_FULL_RATE = 0.02


@pytest.fixture(scope="module")
def sample():
    index = load_index()
    assert index is not None
    if not index.late_columns_present:
        pytest.skip("catalog predates the proxy columns; run scripts/build_card_index.py")
    return [e for i, e in enumerate(index.iter_all()) if i % STRIDE == 0]


@pytest.fixture(scope="module")
def generated(sample):
    out = []
    for entry in sample:
        result = build_proxy(facts_from_index(entry))
        compiled = None
        error = None
        if result.model is not None:
            try:
                compiled = compile_card(result.model)
            # Deliberately broad: the assertion is that *nothing* escapes here,
            # so narrowing it would let the next surprise through.
            except Exception as exc:
                error = f"{entry.name}: {type(exc).__name__}: {exc}"
        out.append((entry, result, compiled, error))
    return out


class TestNothingInTheCatalogBreaksTheRegistry:
    def test_every_generated_card_compiles(self, generated):
        failures = [error for *_, error in generated if error]
        assert failures == [], "\n".join(failures[:20])

    def test_the_only_refusals_are_things_that_cannot_be_in_a_deck(self, generated):
        for entry, result, *_ in generated:
            if result.model is None:
                assert entry.is_token or entry.layout != "normal" or "no card type" in result.error, (
                    f"{entry.name} ({entry.layout}) was refused: {result.error}"
                )

    def test_most_of_the_catalog_generates_at_all(self, generated):
        made = sum(1 for _, r, *_ in generated if r.model is not None)
        assert made / len(generated) > 0.95


class TestTheGeneratedCardsAreUsable:
    def test_ids_are_unique_and_fit_the_art_path_guard(self, generated):
        import re

        from automtg.server.art import CARD_ID

        seen = collections.Counter(r.card_id for _, r, c, _ in generated if c)
        assert [cid for cid, n in seen.items() if n > 1] == []
        bad = [cid for cid in seen if not re.match(CARD_ID, cid)]
        assert bad == [], f"ids the art route would reject: {bad[:10]}"

    def test_colour_identity_never_widens_past_the_printed_one(self, generated):
        """The check that keeps imported decks legal.

        `validate_deck` rejects any card whose identity is not a subset of the
        commander's. A generated card whose identity was *derived* would pick up
        every colour its mana ability can make, and a five-colour Command Tower
        is illegal in every deck in the game.
        """
        for entry, _, card, _ in generated:
            if card is None:
                continue
            assert card.color_identity == frozenset(entry.color_identity), entry.name

    def test_a_land_that_taps_for_mana_gets_a_mana_ability(self, generated):
        """The single most deck-breaking thing this generator could get wrong.

        A 37-land mana base that produces nothing is a deck that cannot cast its
        own commander, and nothing about the board would say why.
        """
        missed = [
            entry.name
            for entry, _, card, _ in generated
            if card
            and "Land" in card.types
            and entry.produced_list()
            and "{T}: Add" in entry.oracle_text
            and not any(a.is_mana_ability for a in card.abilities)
        ]
        assert missed == [], f"lands that lost their mana: {missed[:10]}"

    def test_a_creature_always_has_integer_stats(self, generated):
        # `*` and "1+*" are common and `compile_card` demands ints.
        for _, _, card, _ in generated:
            if card and "Creature" in card.types:
                assert isinstance(card.power, int)
                assert isinstance(card.toughness, int)


class TestCoverageIsReportedHonestly:
    def test_a_meaningful_share_still_comes_through_whole(self, generated):
        made = [r for _, r, c, _ in generated if c]
        full = sum(1 for r in made if r.coverage == "full")
        assert full / len(made) > MIN_FULL_RATE, (
            f"only {full}/{len(made)} cards generated cleanly -- keyword lifting "
            "or mana-ability generation has probably regressed"
        )

    def test_full_coverage_always_means_no_notes(self, generated):
        # The two must not drift: the UI shows the count from `coverage` and the
        # explanation from `notes`, and "fully supported, here is what we
        # changed" is the one combination that reads as a bug.
        for _, result, card, _ in generated:
            if card and result.coverage == "full":
                assert result.notes == (), f"{result.card_id}: {result.notes}"

    def test_every_partial_card_says_why(self, generated):
        for _, result, card, _ in generated:
            if card and result.coverage == "partial":
                assert result.notes, f"{result.card_id} is partial but explains nothing"
