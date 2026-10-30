"""Mayhem: a graveyard price offered only to the card you discarded this turn.

702.187a: "Mayhem [cost]" means "You may cast this card from your graveyard
for [cost] if you discarded it this turn. Timing rules still apply." The Doom
Prevails witnesses are Abomination, World Ravager, Chameleon, Master of
Disguise and The Squadron Sinister: permanents that resolve onto the
battlefield, cast from the graveyard for less than they print.

The graveyard-cost slot flashback, escape and jump-start share already had the
price and the widening. What it lacked was a condition, and the near miss is
`graveyard_cost` plus `graveyard_cast: "graveyard"`. That loads clean and makes
the card castable from the graveyard every turn, however it got there, which is
a much stronger card. The `cast_from_graveyard` static has a condition slot but
casts at the printed price, a weaker card.

The condition is about one *object*: 400.7 makes the card that left the
graveyard and came back a new object, nobody discarded it this turn, so the
record is dropped at the next zone change and with the turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.templates import _translate_line
from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import discard_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, pass_until, settle

BRUTE = "t_mayhem_brute"  # {4}{R} 4/4 creature; mayhem {1}{R}
BOLT = "t_mayhem_bolt"  # {2}{R} instant, 2 damage to a player; mayhem {R}
DISCARD = "t_discard_one"  # {0} sorcery: discard a card


def oid_of(game, card_id: str) -> int:
    (oid,) = [oid for oid, o in game.state.objects.items() if o.def_id == card_id]
    return oid


def graveyard_casts(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        and game.state.objects[a.source].zone is Zone.GRAVEYARD
    ]


def position(builder, card_id: str, *, lands: int = 2, step: Step | None = None):
    """``card_id`` and a discard spell in hand, mountains to pay with."""
    b = (
        builder(players=2)
        .hand(0, [DISCARD, card_id])
        .battlefield(0, ["mountain"] * lands)
        .active(0)
    )
    if step is not None:
        b = b.step(step)
    return b.build()


def discard_by_spell(game) -> None:
    """Cast the discard spell; the mayhem card is the only card left to discard."""
    game.apply(action_for_card(game, ActionKind.CAST, DISCARD))
    settle(game)


class TestTheDiscardOpensTheLine:
    def test_a_discarded_creature_is_cast_from_the_graveyard_for_its_mayhem_price(
        self, builder
    ):
        game = position(builder, BRUTE)
        discard_by_spell(game)
        brute = oid_of(game, BRUTE)
        assert game.state.objects[brute].zone is Zone.GRAVEYARD
        (cast,) = graveyard_casts(game, BRUTE)
        assert "mayhem" in cast.label
        game.apply(cast)
        settle(game)
        assert game.state.objects[brute].zone is Zone.BATTLEFIELD, (
            "a permanent cast with mayhem goes where it normally would"
        )

    def test_the_price_is_the_mayhem_cost_not_the_printed_one(self, builder):
        """Two mountains pay {1}{R}; the printed {4}{R} would need five."""
        game = position(builder, BRUTE, lands=1)
        discard_by_spell(game)
        assert graveyard_casts(game, BRUTE) == [], "one land cannot pay {1}{R}"

    def test_an_instant_goes_back_to_the_graveyard_not_to_exile(self, builder):
        game = position(builder, BOLT)
        discard_by_spell(game)
        before = sum(p.life for p in game.state.players)
        game.apply(graveyard_casts(game, BOLT)[0])
        settle(game)
        assert sum(p.life for p in game.state.players) == before - 2
        assert game.state.objects[oid_of(game, BOLT)].zone is Zone.GRAVEYARD

    def test_the_card_that_resolved_back_is_a_new_object(self, builder):
        """400.7: nobody discarded the card the spell became, so a second
        mayhem cast is not offered even with mana left."""
        game = position(builder, BOLT, lands=3)
        discard_by_spell(game)
        game.apply(graveyard_casts(game, BOLT)[0])
        settle(game)
        assert graveyard_casts(game, BOLT) == []


class TestOnlyADiscardThisTurn:
    def test_a_card_that_reached_the_graveyard_another_way_is_not_offered(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, [BRUTE])
            .battlefield(0, ["mountain"] * 5)
            .active(0)
            .build()
        )
        assert graveyard_casts(game, BRUTE) == []

    def test_a_zone_change_after_the_discard_ends_it(self, builder):
        game = position(builder, BRUTE)
        discard_by_spell(game)
        brute = oid_of(game, BRUTE)
        move_object(game.state, brute, Zone.EXILE)
        move_object(game.state, brute, Zone.GRAVEYARD)
        assert graveyard_casts(game, BRUTE) == []

    def test_the_record_ends_with_the_turn(self, builder):
        """Discarded on its owner's turn, the instant cannot be cast on the
        next turn, with an untapped mountain and instant timing."""
        game = position(builder, BOLT)
        discard_by_spell(game)
        assert graveyard_casts(game, BOLT), "castable on the turn it was discarded"
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn != turn and g.state.priority_idx is not None
            and g.state.players[g.state.priority_idx].pid == 0,
        )
        assert game.state.turn != turn
        assert graveyard_casts(game, BOLT) == []

    def test_the_discard_is_recorded_for_the_player_who_discarded(self, builder):
        game = (
            builder(players=2)
            .hand(1, [BOLT])
            .battlefield(0, ["mountain"])
            .active(0)
            .build()
        )
        bolt = oid_of(game, BOLT)
        discard_cards(game.state, 1, [bolt])
        assert game.state.turn_ledger.discarded == {bolt: 1}
        assert graveyard_casts(game, BOLT) == [], "it is not player 0's card to cast"

    def test_a_discard_replaced_out_of_the_graveyard_records_nothing(self, builder):
        """Rest in Peace exiles the discarded card, so nothing is left to cast."""
        game = (
            builder(players=2)
            .hand(0, [BOLT])
            .battlefield(0, ["mountain", "rest_in_peace"])
            .active(0)
            .build()
        )
        bolt = oid_of(game, BOLT)
        discard_cards(game.state, 0, [bolt])
        assert game.state.objects[bolt].zone is Zone.EXILE
        assert game.state.turn_ledger.discarded == {}


class TestTimingRulesStillApply:
    def test_a_creature_discarded_outside_a_main_phase_waits_for_sorcery_timing(
        self, builder
    ):
        game = (
            builder(players=2)
            .hand(0, [BRUTE, BOLT])
            .battlefield(0, ["mountain"] * 3)
            .active(0)
            .step(Step.BEGIN_COMBAT)
            .build()
        )
        discard_cards(game.state, 0, [oid_of(game, BRUTE), oid_of(game, BOLT)])
        assert graveyard_casts(game, BRUTE) == []
        assert graveyard_casts(game, BOLT), "the instant keeps instant timing"


class TestTheLoader:
    def base(self, **extra) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Mayhem {1}{R}",
            "mana_cost": "{4}{R}",
            "types": ["Creature"],
            "power": 4,
            "toughness": 4,
            **extra,
        }

    def compile(self, **extra):
        return compile_card(CardModel.model_validate(self.base(**extra)))

    def test_it_compiles_onto_the_graveyard_cost_slot(self):
        card = self.compile(mayhem="{1}{R}")
        assert card.mayhem
        assert card.flashback is not None and card.flashback.mana.text == "{1}{R}"
        assert not card.graveyard_cast_exiles

    @pytest.mark.parametrize(
        "extra",
        [
            {"graveyard_cost": {"mana": "{1}{R}"}},
            {"flashback": {"mana": "{1}{R}"}},
        ],
    )
    def test_a_second_graveyard_price_is_refused(self, extra):
        with pytest.raises(DslError, match="'mayhem' or a graveyard cost"):
            self.compile(mayhem="{1}{R}", **extra)

    def test_a_destination_beside_it_is_refused(self):
        with pytest.raises(DslError, match="already says where the card goes"):
            self.compile(mayhem="{1}{R}", graveyard_cast="exile")

    def test_retrace_beside_it_is_refused(self):
        with pytest.raises(DslError, match="retrace"):
            self.compile(mayhem="{1}{R}", retrace=True)

    def test_it_needs_mana(self):
        with pytest.raises(DslError):
            self.compile(mayhem="")


class TestThePrintedLine:
    REMINDER = (
        "Mayhem {4}{R} (You may cast this card from your graveyard for {4}{R} "
        "if you discarded it this turn. Timing rules still apply.)"
    )

    def test_the_template_reads_it_as_the_card_level_price(self):
        produced = _translate_line(self.REMINDER, is_spell=False)
        assert produced is not None
        kind, payload, _translation, name = produced
        assert (kind, payload, name) == ("card", {"mayhem": "{4}{R}"}, "mayhem")

    @pytest.mark.parametrize("line", ["Mayhem", "Mayhem {4}{R}, then draw a card."])
    def test_a_line_that_says_more_or_less_is_not_claimed(self, line):
        produced = _translate_line(line, is_spell=False)
        assert produced is None or produced[3] != "mayhem"

    def test_the_residual_gate_claims_only_the_declared_price(self, registry):
        """Warp's strictness: `{1}{R}` cannot claim a printed `{2}{R}`."""
        card = registry.get(BRUTE)
        assert _covered(card, "Mayhem {1}{R} (You may cast this card…)")
        assert not _covered(card, "Mayhem {2}{R} (You may cast this card…)")
