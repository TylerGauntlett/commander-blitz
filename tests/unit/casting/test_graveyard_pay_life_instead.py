"""`pay_life_instead` on a `cast_from_graveyard` static -- a graveyard permission priced in life.

    Eye of Duskmantle -- "You may play lands and cast spells from among cards
    in your graveyard you've surveilled this turn. If you cast a spell this
    way, you pay life equal to its mana value rather than paying its mana
    cost."

Bolas's Citadel's price on Edgar's permission, and both halves were already
there: the `pay_life_instead` word the Citadel's `cast_from_library_top` reads,
and the life lines Nashi's `playable_pay_life_instead` offers
(`casting._pay_life_lines`). What the composition has to get right:

- **An alternative cost (118.9), and the permission's only one.** "This way" is
  the only way the permission reaches, so no printed-price line is offered under
  it. X is 0 (107.3b); additional costs are still owed (118.9d); life is paid
  only while the player has that much (119.4).
- **Unmetered.** Eye prints no "once each turn". The surveil clause is the
  bound: each cast takes a surveilled card out of the graveyard, and whatever
  comes back is a new object nobody surveilled (400.7). Without
  `surveilled_this_turn` the loader still refuses an uncapped permission.
- **The spell goes where it normally would.** A spell cast under a graveyard
  permission is exiled only when the permission is flashback
  (`grants_flashback`, Lier and Urabrask's grant, which the stack item now
  carries as `exiles_instead`); Eye's instants and sorceries go back to the
  graveyard.
- **The line names the permission billed.** Beside an Edgar-shaped permission
  at the printed price, the life line spends Eye and the printed line spends the
  other, so one never uses up the other's turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import hand_ids, settle

EYE = "t_surveil_eye"
SCAVENGER = "t_surveil_scavenger"  # once a turn, at the printed price
STUDY = "t_study"  # {3}{U} sorcery, draw two: mana value 4
DRAW_X = "t_cane_draw_x"  # {X}{U}: draw X cards, mana value 1
DELUGE = "t_fixed_deluge"  # {2}{B}, as an additional cost pay 3 life
RITE = "t_expend_kicked"  # {1}, kicker {3}: gain 1 life, 1 more if kicked


def position(builder, library, *, mine=(EYE,), islands=0, life=40):
    """Player 0 in their main phase with ``library`` on top, holding priority."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands + list(mine))
        .hand(0, ["plains"])
        .library(0, list(library) + ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .life(0, life)
        .build()
    )


def surveil(game, amount: int) -> list[int]:
    """Player 0 surveils ``amount`` and bins every card."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    gen = OPS["surveil"](ctx, {"op": "surveil", "amount": {"const": amount}})
    binned = list(game.state.players[0].library[:amount])
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return binned
        send = list(range(decision.max_count))


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def life(game) -> int:
    return game.state.players[0].life


def untapped_islands(game) -> int:
    state = game.state
    return sum(
        not state.objects[oid].tapped
        for oid in state.battlefield
        if state.objects[oid].def_id == "island"
    )


class TestPaysLifeRatherThanMana:
    def test_a_four_drop_costs_four_life(self, builder):
        game = position(builder, [STUDY])
        (oid,) = surveil(game, 1)
        (line,) = casts(game, oid)
        assert line.granted_cost == (("pay_life", 4),)
        before = len(hand_ids(game))
        game.apply(line)
        assert life(game) == 36
        settle(game)
        assert len(hand_ids(game)) == before + 2, "the spell resolved"

    def test_mana_on_hand_buys_nothing_else(self, builder):
        """No printed-price line beside the life one, and the Islands stay up."""
        game = position(builder, [STUDY], islands=4)
        (oid,) = surveil(game, 1)
        lines = casts(game, oid)
        assert lines and all(a.granted_cost == (("pay_life", 4),) for a in lines)
        game.apply(lines[0])
        assert untapped_islands(game) == 4

    def test_a_milled_card_is_not_offered(self, builder):
        game = position(builder, [STUDY])
        oid = game.state.players[0].library[0]
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="mill")
        assert casts(game, oid) == []

    def test_without_the_permanent_nothing_is(self, builder):
        game = position(builder, [STUDY], mine=())
        (oid,) = surveil(game, 1)
        assert casts(game, oid) == []


class TestTheAlternativeCostsRules:
    def test_x_is_zero(self, builder):
        """107.3b: {X}{U} costs 1 life and draws nothing."""
        game = position(builder, [DRAW_X])
        (oid,) = surveil(game, 1)
        (line,) = casts(game, oid)
        assert line.granted_cost == (("pay_life", 1),)
        before = len(hand_ids(game))
        game.apply(line)
        settle(game)
        assert life(game) == 39
        assert len(hand_ids(game)) == before

    def test_an_additional_cost_is_still_owed(self, builder):
        """118.9d: three life for the mana value and three more on top."""
        game = position(builder, [DELUGE])
        (oid,) = surveil(game, 1)
        game.apply(casts(game, oid)[0])
        settle(game)
        assert life(game) == 34

    def test_a_kicker_is_still_paid_in_mana(self, builder):
        game = position(builder, [RITE], islands=3)
        (oid,) = surveil(game, 1)
        lines = casts(game, oid)
        assert {a.kicked for a in lines} == {False, True}
        game.apply(next(a for a in lines if a.kicked))
        assert untapped_islands(game) == 0
        settle(game)
        assert life(game) == 41, "40, less 1, plus 2 kicked"


class TestPayingLife:
    def test_exactly_enough_life_pays_down_to_zero(self, builder):
        game = position(builder, [STUDY], life=4)
        (oid,) = surveil(game, 1)
        assert casts(game, oid)

    def test_less_life_casts_nothing(self, builder):
        game = position(builder, [STUDY], life=3, islands=4)
        (oid,) = surveil(game, 1)
        assert casts(game, oid) == [], "and the mana is no help"


class TestUnmetered:
    def test_every_surveilled_spell_may_be_cast(self, builder):
        """No "once each turn": the surveil clause is the whole bound."""
        game = position(builder, [STUDY, DRAW_X])
        first, second = surveil(game, 2)
        game.apply(casts(game, first)[0])
        settle(game)
        assert casts(game, second), "the first cast spent nothing"

    def test_the_spell_goes_back_to_the_graveyard(self, builder):
        """Not flashback: the sorcery is not exiled, and is not surveilled now."""
        game = position(builder, [STUDY])
        (oid,) = surveil(game, 1)
        game.apply(casts(game, oid)[0])
        settle(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert casts(game, oid) == [], "a new object (400.7), surveilled by nobody"


class TestBesideAPrintedPricePermission:
    def test_both_prices_are_offered(self, builder):
        game = position(builder, [STUDY], mine=(EYE, SCAVENGER), islands=4)
        (oid,) = surveil(game, 1)
        prices = {a.granted_cost for a in casts(game, oid)}
        assert (("pay_life", 4),) in prices
        assert () in prices, "the printed line, under the other permission"

    def test_the_life_line_does_not_spend_the_other(self, builder):
        game = position(builder, [STUDY, STUDY], mine=(EYE, SCAVENGER), islands=4)
        first, second = surveil(game, 2)
        game.apply(next(a for a in casts(game, first) if a.granted_cost))
        settle(game)
        assert any(not a.granted_cost for a in casts(game, second)), (
            "the once-a-turn printed line is still unspent"
        )

    def test_the_printed_line_spends_the_other(self, builder):
        game = position(builder, [STUDY, STUDY], mine=(EYE, SCAVENGER), islands=8)
        first, second = surveil(game, 2)
        game.apply(next(a for a in casts(game, first) if not a.granted_cost))
        settle(game)
        lines = casts(game, second)
        assert lines and all(a.granted_cost == (("pay_life", 4),) for a in lines)


class TestLands:
    def test_a_surveilled_land_is_a_land_drop_for_nothing(self, builder):
        game = position(builder, ["forest"])
        (oid,) = surveil(game, 1)
        drop = next(
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.source == oid
        )
        game.apply(drop)
        assert oid in game.state.battlefield
        assert life(game) == 40


def _static(**overrides) -> CardModel:
    static = {
        "kind": "static",
        "text": "You may cast spells from among cards in your graveyard you've surveilled this turn.",
        "effect": "cast_from_graveyard",
        "affects_player": "you",
        "affects_spells": {"not_types": ["Land"]},
        "surveilled_this_turn": True,
        "pay_life_instead": True,
    }
    for key, value in overrides.items():
        if value is None:
            static.pop(key, None)
        else:
            static[key] = value
    return CardModel.model_validate(
        {
            "id": "t_probe_eye",
            "name": "Probe Eye",
            "oracle_text": static["text"],
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": [static],
        }
    )


class TestTheLoader:
    def test_the_witness_shape_loads_unmetered(self):
        static = compile_card(_static(), source="test").abilities[0].static
        assert static["pay_life_instead"] is True
        assert static["max_per_turn"] is None

    def test_without_the_surveil_clause_it_needs_a_rate_limit(self):
        with pytest.raises(DslError, match="max_per_turn"):
            compile_card(_static(surveilled_this_turn=None), source="test")

    def test_beside_flashback_is_a_second_price(self):
        with pytest.raises(DslError, match="pay_life_instead"):
            compile_card(_static(grants_flashback=True), source="test")

    def test_on_a_static_that_does_not_read_it(self):
        with pytest.raises(DslError, match="pay_life_instead"):
            compile_card(
                _static(
                    effect="play_lands_from_graveyard",
                    affects_spells=None,
                ),
                source="test",
            )
