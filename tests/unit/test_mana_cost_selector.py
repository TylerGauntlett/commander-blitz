"""``mana_cost`` — "an artifact card **with mana cost {0} or {1}**" (Urza's Saga).

**The rules argument.** A mana cost is the mana symbols printed in the card's
upper right corner (202.1). A card with no symbols there — every artifact land,
Lotus Bloom, Mox Tantalite — has *no* mana cost (202.1b), which is not the same
thing as a mana cost of {0}, even though both have mana value 0 (202.3a). And an
{X} scores 0 for mana value off the stack (202.3b) while being a different
symbol from {0}.

**Why `mana_value` could not stand in.** The nearest spelling —
``mana_value <= 1`` plus ``not_colors`` over all five colours plus
``x_in_mana_cost: false`` — still fetches Seat of the Synod and Darksteel
Citadel, which the printed Urza's Saga cannot, and would fetch a colourless
``{C}`` artifact too. The catalog holds 23 artifacts with no mana cost, most of
them lands played in exactly the decks that play the Saga.

So the key compares **printed symbols**: `{1}` is one generic symbol and only
that, `{C}` is not `{1}`, `{W/P}` and `{2/W}` are not `{1}` or `{2}`, and a card
with no cost never matches anything. The spelling of each wanted cost is
normalised through the cost parser, so `" {1} "` and `"{1}"` agree.

Read in four places, because it is a legal key in all of them and an unread
key loads clean and silently matches everything: effect selectors
(`selectors.matches`), trigger filters (`triggers.matches_card_filter`), static
and spell filters (`characteristics._matches_printed`) and cost-reduction
counts (`cost_reduction._reduction_matches`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.loader.vocabulary import SPELL_FILTER_KEYS, STATIC_FILTER_KEYS
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import _matches_printed
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import SELECTOR_KEYS, matches, validate_selector
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from automtg.engine.mana import ManaCost, printed_cost_is
from automtg.engine.triggers import matches_card_filter
from tests.conftest import action_for_card, only_oid, pass_until

ONE = "t_mc_one"  # {1}, Sol Ring's cost
ZERO = "t_mc_zero"  # {0}, Ornithopter's cost
LAND = "t_mc_land"  # artifact land, no mana cost
X = "t_mc_x"  # {X}
TWO = "t_mc_two"  # {2}
COLORLESS = "t_mc_colorless"  # {C}
PHYREXIAN = "t_mc_phyrexian"  # {W/P}
TWOBRID = "t_mc_twobrid"  # {2/W}
TUTOR = "t_mc_search"  # sorcery: search for an artifact with mana cost {0} or {1}

URZA = ["{0}", "{1}"]
EVERY_SHAPE = [ONE, ZERO, LAND, X, TWO, COLORLESS, PHYREXIAN, TWOBRID]


def board(builder):
    return builder(players=2).battlefield(0, EVERY_SHAPE).build(advance=False)


def selects(game, card_id: str, selector: dict) -> bool:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    return matches(ctx, only_oid(game, card_id), selector)


class TestThePrintedCostIsTheQuestion:
    @pytest.mark.parametrize("card_id", [ONE, ZERO])
    def test_zero_and_one_match(self, builder, card_id):
        game = board(builder)
        assert selects(game, card_id, {"mana_cost": URZA})

    def test_no_mana_cost_is_not_mana_cost_zero(self, builder, registry):
        """202.1b. Mana value 0, and still not a match — the whole reason the
        key exists, since `mana_value <= 1` takes it."""
        game = board(builder)
        assert registry.get(LAND).mana_value == 0
        assert not selects(game, LAND, {"mana_cost": URZA})
        assert selects(game, LAND, {"mana_value": {"op": "<=", "value": 1}}), (
            "the near miss really does take it"
        )

    def test_x_is_not_zero(self, builder):
        """202.3b scores {X} as 0; the symbol is still {X}."""
        game = board(builder)
        assert not selects(game, X, {"mana_cost": URZA})

    def test_two_is_not_one(self, builder):
        game = board(builder)
        assert not selects(game, TWO, {"mana_cost": URZA})

    @pytest.mark.parametrize("card_id", [COLORLESS, PHYREXIAN, TWOBRID])
    def test_a_pip_that_pays_like_generic_is_not_generic(self, builder, card_id):
        """{C}, {W/P} and {2/W} are each some number of mana; none of them is
        the printed symbol {1} or {2}."""
        game = board(builder)
        assert not selects(game, card_id, {"mana_cost": ["{1}", "{2}"]})

    def test_a_pip_matches_itself(self, builder):
        game = board(builder)
        assert selects(game, PHYREXIAN, {"mana_cost": ["{W/P}"]})
        assert selects(game, COLORLESS, {"mana_cost": ["{C}"]})
        assert selects(game, X, {"mana_cost": ["{X}"]})

    def test_the_wanted_spelling_is_normalised(self):
        cost = ManaCost.parse("{1}")
        assert printed_cost_is(cost, [" {1} "])
        assert printed_cost_is(ManaCost.parse("{2}{W/P}"), ["{w/p}{2}"])

    def test_it_composes_with_the_other_keys(self, builder):
        game = board(builder)
        assert not selects(game, ONE, {"types": ["Creature"], "mana_cost": URZA})


class TestUrzasSagaChapterThree:
    def test_the_search_finds_only_the_printed_costs(self, builder):
        """End to end through `search_library`: the land, the {X} and the {2}
        stay in the library, and the {1} is put onto the battlefield."""
        game = (
            builder(players=2)
            .hand(0, [TUTOR])
            .battlefield(0, ["island"] * 2)
            .library(0, [LAND, X, TWO, ONE])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, TUTOR))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        offered = [game.state.objects[option.value].def_id for option in decision.options]
        assert offered == [ONE]
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        pass_until(game, lambda g: not g.state.stack)

        placed = {o.def_id for o in game.state.battlefield_objects(0)}
        library = {game.state.objects[oid].def_id for oid in game.state.players[0].library}
        assert ONE in placed
        assert {LAND, X, TWO} <= library


class TestTheOtherReaders:
    def test_a_trigger_filter_reads_it(self, builder):
        game = board(builder)
        source = game.state.objects[only_oid(game, TWO)]
        filt = {"mana_cost": URZA}
        assert matches_card_filter(game.state, only_oid(game, ONE), filt, source)
        assert not matches_card_filter(game.state, only_oid(game, LAND), filt, source)

    def test_a_static_filter_reads_it(self, registry):
        assert _matches_printed(registry.get(ZERO), {"mana_cost": URZA})
        assert not _matches_printed(registry.get(LAND), {"mana_cost": URZA})

    def test_it_is_vocabulary_everywhere_it_is_read(self):
        assert "mana_cost" in SELECTOR_KEYS
        assert "mana_cost" in STATIC_FILTER_KEYS
        assert "mana_cost" in SPELL_FILTER_KEYS


class TestTheLoaderRefusals:
    def test_a_list_loads(self):
        validate_selector({"mana_cost": URZA}, "probe")

    def test_a_bare_string_is_refused(self):
        """Iterated, "{1}" is three characters and matches nothing."""
        with pytest.raises(DslError, match="non-empty list"):
            validate_selector({"mana_cost": "{1}"}, "probe")

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            validate_selector({"mana_cost": []}, "probe")

    def test_no_cost_is_not_a_cost_to_ask_for(self):
        """A card with no mana cost never matches, so "" would match nothing."""
        with pytest.raises(DslError, match="never matches"):
            validate_selector({"mana_cost": [""]}, "probe")

    def test_an_unparsable_cost_is_refused(self):
        with pytest.raises(DslError):
            validate_selector({"mana_cost": ["{1"]}, "probe")

    def test_a_static_filter_is_checked_too(self):
        card = {
            "id": "probe",
            "name": "Probe",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "Artifacts with mana cost {1} get +1/+1.",
                    "effect": "buff",
                    "affects": {"types": ["Artifact"], "mana_cost": "{1}"},
                    "power": 1,
                    "toughness": 1,
                }
            ],
        }
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(CardModel.model_validate(card))


def test_the_catalog_witnesses_exist(registry):
    """The shapes above are the real ones: Sol Ring is {1}, Ornithopter {0}."""
    assert str(registry.get("sol_ring").mana_cost) == "{1}"
    assert registry.get("ornithopter").mana_cost.text == "{0}"
