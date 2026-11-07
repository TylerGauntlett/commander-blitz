"""The first spell each turn **that mana from a Treasure was spent to cast**.

    Rain of Riches -- "The first spell you cast each turn that mana from a
    Treasure was spent to cast has cascade."

An ordinal over a run of casts counted by *payment*, not by face. Rule 603.2
triggers the ability as the spell becomes cast (601.2i), and the question it
asks is about every spell the caster has cast this turn -- including those cast
before Rain of Riches was on the battlefield, Rain of Riches itself among them.
Those spells have left the stack, and the Treasures that paid for them have left
the game, so the only place the answer survives is the turn ledger:
`TurnLedger.spells_cast_mana` keeps each cast's `mana_spent_traits` index for
index with `spells_cast_ids`, and `triggers._spell_ordinal` matches a
selector-valued `paid_by` against it.

The near miss the gap record names is `max_per_turn: 1`, and it is wrong in the
card's ordinary line of play: cast Rain of Riches with Treasure mana, crack one
of the two Treasures it makes, and the next spell would cascade -- but it is the
turn's *second* Treasure-paid spell, and the printed card gives it nothing. A
plain `paid_by` filter without `nth` is wider still: every Treasure-paid spell
would cascade.

"Has cascade" is written the way every printed cascade is in this engine -- a
`spell_cast` trigger running the `cascade` op -- with the ceiling taken from the
triggering spell (`mana_value_of {binding: subject}`) rather than from the
enchantment, since it is the spell that has cascade (702.85a).

Witness: `t_treasure_cascade`, Rain of Riches' two lines verbatim.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, oids_of, only_oid, pass_until, settle

RAIN = "t_treasure_cascade"
TREASURE = "treasure_token"
BEAR = "t_bear"  # {1}{G}, mana value 2
INSTANT = "t_plain_instant"  # {W}, mana value 1


def position(builder, *, hand, rain_in_play=True, treasures=2, library=None):
    """``game`` with seat 0 active in its main phase, Treasures and lands untapped.

    Lands for everything in ``hand`` off lands alone, so a test chooses which
    casts Treasure mana pays for by cracking one first. The placed Treasures are
    flagged as tokens, as `test_treasure_mana_spent.py` explains: a sacrificed
    token leaves `state.objects`, which is the case the ledger snapshot is for.
    A spare instant stays in hand, never cast, so seat 0 still has a decision
    after the last cast and the engine's auto-pass does not roll the turn over.
    """
    permanents = ([RAIN] if rain_in_play else []) + [TREASURE] * treasures
    permanents += ["forest"] * 6 + ["island"] * 2 + ["mountain"] * 3 + ["plains"] * 3
    game = (
        builder(players=2)
        .battlefield(0, permanents)
        .hand(0, [*hand, INSTANT])
        .library(0, list(library or ["forest"] * 20))
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    for obj in game.state.objects.values():
        if obj.def_id == TREASURE:
            obj.is_token = True
    return game


def crack_a_treasure(game) -> None:
    """Sacrifice one Treasure for mana by hand; the solver never offers one."""
    treasure = oids_of(game, TREASURE, 0)[0]
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == treasure and a.mana_option is not None
        )
    )


def cast(game, card_id: str, *, with_treasure: bool = False) -> None:
    if with_treasure:
        crack_a_treasure(game)
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)


def cascades(game) -> list:
    """The cascades Rain of Riches' ability performed, oldest first."""
    rain = only_oid(game, RAIN, 0)
    return [e for e in game.state.events if e.type == "cascade" and e.source == rain]


class TestTheFirstTreasurePaidSpellHasCascade:
    def test_a_treasure_paid_spell_cascades(self, builder):
        game = position(builder, hand=[BEAR])
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 1

    def test_a_spell_paid_off_lands_does_not(self, builder):
        game = position(builder, hand=[BEAR])
        cast(game, BEAR)
        assert cascades(game) == []

    def test_earlier_land_paid_spells_do_not_use_up_the_first(self, builder):
        """The flat ordinal says 3; the printed run says first."""
        game = position(builder, hand=[INSTANT, BEAR, BEAR])
        cast(game, INSTANT)
        cast(game, BEAR)
        cast(game, BEAR, with_treasure=True)
        assert game.state.turn_ledger.spells_cast[0] == 3
        assert len(cascades(game)) == 1

    def test_the_ceiling_is_the_triggering_spells_mana_value(self, builder):
        """A Bear (2) cascades past another Bear (not less than 2) to the
        instant (1): two cards exiled, read off the spell, not the enchantment
        (whose mana value is 5 and would have stopped at the first Bear)."""
        game = position(builder, hand=[BEAR], library=[BEAR, INSTANT] + ["forest"] * 18)
        cast(game, BEAR, with_treasure=True)
        [cascade] = cascades(game)
        assert cascade.data["exiled"] == 2


class TestTheSecondTreasurePaidSpellDoesNot:
    def test_the_second_is_silent(self, builder):
        game = position(builder, hand=[BEAR, BEAR])
        cast(game, BEAR, with_treasure=True)
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 1

    def test_a_land_paid_spell_between_them_changes_nothing(self, builder):
        game = position(builder, hand=[BEAR, INSTANT, BEAR])
        cast(game, BEAR, with_treasure=True)
        cast(game, INSTANT)
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 1


class TestSpellsCastBeforeItArrivedStillCount:
    """The ordinal is the turn's, not the permanent's -- the `max_per_turn` miss."""

    def test_an_earlier_treasure_paid_spell_was_the_first(self, builder):
        game = position(builder, hand=[BEAR, RAIN, BEAR], rain_in_play=False)
        cast(game, BEAR, with_treasure=True)
        cast(game, RAIN)
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 0

    def test_rain_of_riches_cast_with_treasure_mana_is_the_first(self, builder):
        """The gap record's case: Rain of Riches paid for with a Treasure, then
        one of the two Treasures it makes cracked for the next spell."""
        game = position(builder, hand=[RAIN, BEAR], rain_in_play=False, treasures=1)
        cast(game, RAIN, with_treasure=True)
        assert len(oids_of(game, TREASURE, 0)) == 2, "its enters trigger made two"
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 0

    def test_land_paid_spells_before_it_leave_the_first_open(self, builder):
        game = position(builder, hand=[INSTANT, RAIN, BEAR], rain_in_play=False, treasures=0)
        cast(game, INSTANT)
        cast(game, RAIN)
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 1


class TestItResetsEachTurn:
    def test_the_next_turn_has_a_first_of_its_own(self, builder):
        game = position(builder, hand=[BEAR, BEAR])
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 1
        pass_until(
            game,
            lambda g: g.state.turn > 2
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert game.state.turn_ledger.spells_cast_mana.get(0, []) == []
        cast(game, BEAR, with_treasure=True)
        assert len(cascades(game)) == 2


class TestTheLedgerKeepsThePayment:
    def test_index_for_index_with_the_ids(self, builder):
        game = position(builder, hand=[INSTANT, BEAR])
        cast(game, INSTANT)
        cast(game, BEAR, with_treasure=True)
        ledger = game.state.turn_ledger
        assert ledger.spells_cast_ids[0] == [INSTANT, BEAR]
        land_paid, treasure_paid = ledger.spells_cast_mana[0]
        assert not any("Treasure" in o.subtypes for o in land_paid)
        assert any("Treasure" in o.subtypes for o in treasure_paid)


def watcher(paid_by) -> dict:
    """The card as raw JSON, for the load-time guard."""
    text = "The first spell you cast each turn that mana from a Treasure was spent to cast has cascade."
    return {
        "id": "t_treasure_ordinal_probe",
        "name": "Test Treasure Ordinal Probe",
        "oracle_text": text,
        "mana_cost": "{U}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": {
                    "event": "spell_cast",
                    "controller": "you",
                    "filter": {"paid_by": paid_by},
                    "nth": 1,
                },
                "effects": [{"op": "cascade"}],
            }
        ],
    }


class TestTheLoaderGuards:
    @pytest.mark.parametrize(
        "paid_by", [{"subtypes": ["Treasure"]}, {"subtypes": ["Treasure"], "controller": "you"}]
    )
    def test_a_selector_paid_by_loads_beside_nth(self, paid_by):
        compile_card(CardModel.model_validate(watcher(paid_by)))

    def test_the_oid_form_is_refused_beside_nth(self):
        """"Mana from this" names one object the ledger does not follow."""
        with pytest.raises(DslError, match="'paid_by' must be a selector"):
            compile_card(CardModel.model_validate(watcher("self")))
