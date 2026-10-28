"""Unspent mana that becomes colorless instead of being lost.

    "If you would lose unspent mana, that mana becomes colorless instead."
                                    -- Kruphix, God of Horizons; Horizon Stone;
                                       Omnath, Locus of the Void

500.4 and 106.4 empty every mana pool as each step and phase ends. This line is
a replacement on that emptying (614.1a): nothing is lost, and every mana that
would have been is still in the pool as {C}. Without `mana_becomes_colorless`
the nearest spelling is `mana_retention` with all six symbols, which keeps the
mana *in its colours* -- red mana that still pays {R}{R} on the next turn, the
strictly better card. Omnath, Locus of the Void is the witness: its landfall
{C}{C} and the green it floats both grow it, and turn by turn the green goes
colourless.

**A pip moves whole.** The converted mana is the same `Pip` in the {C} slot, so a
"spend this mana only to cast creature spells" or a Cavern rider it carried
still applies -- exactly what `mana_retention` does to the pip it keeps.

**The two compose.** A symbol `mana_retention` keeps is never lost, so it is
never converted; a Tanuki pip kept until end of turn keeps its colour until
then.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaPool, compile_restriction
from commanderblitz.engine.player_statics import colorless_instead_players
from commanderblitz.engine.turn import advance
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of

STONE = "t_colorless_stone"  # "If you would lose unspent mana, ...colorless instead."
TYRANT = "t_retain_red"  # "You don't lose unspent red mana..."
RR_SORCERY = "t_retain_rr"  # {R}{R}
GENERIC_SORCERY = "t_colorless_two"  # {2}

R = SYMBOL_INDEX["R"]
G = SYMBOL_INDEX["G"]
C = SYMBOL_INDEX["C"]


def position(builder, mine=(), theirs=(), *, hand=()):
    """Player 0 in their precombat main phase; no lands anywhere."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def float_mana(game, pid: int, **amounts: int) -> None:
    for symbol, count in amounts.items():
        game.state.players[pid].mana_pool.add(symbol, count)


def pool(game, pid: int = 0) -> list[int]:
    return list(game.state.players[pid].mana_pool.amounts)


def pass_until(game, done, limit: int = 400) -> None:
    """Pass priority, as whoever holds it, until ``done(game)``."""
    for _ in range(limit):
        if done(game):
            return
        action = next(
            a
            for a in game.legal_actions()
            if a.kind in (ActionKind.PASS, ActionKind.FINISH_DECLARATION)
        )
        game.apply(action)
    raise AssertionError("the game never reached the wanted point")


def casts_of(game, def_id: str) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    ]


class TestThePool:
    """`ManaPool.clear` with ``colorless_instead`` in isolation."""

    def test_every_lost_mana_becomes_colorless(self):
        p = ManaPool()
        p.add("R", 2)
        p.add("G", 1)
        p.add("C", 1)
        assert p.clear(5, colorless_instead=True) == 0
        assert p.amounts[R] == 0 and p.amounts[G] == 0
        assert p.amounts[C] == 4
        assert [len(pips) for pips in p.tags] == list(p.amounts)

    def test_at_the_end_of_the_turn_too(self):
        p = ManaPool()
        p.add("U", 3)
        assert p.clear(None, colorless_instead=True) == 0
        assert p.amounts[C] == 3

    def test_a_retained_symbol_keeps_its_colour(self):
        p = ManaPool()
        p.add("R", 2)
        p.add("G", 1)
        assert p.clear(5, frozenset({"R"}), colorless_instead=True) == 0
        assert p.amounts[R] == 2 and p.amounts[G] == 0 and p.amounts[C] == 1

    def test_a_tanuki_pip_keeps_its_colour_until_end_of_turn(self):
        p = ManaPool()
        p.add("G", 1, persists_through_turn=5)
        assert p.clear(5, colorless_instead=True) == 0
        assert p.amounts[G] == 1 and p.amounts[C] == 0
        assert p.clear(None, colorless_instead=True) == 0
        assert p.amounts[G] == 0 and p.amounts[C] == 1

    def test_a_restriction_rides_the_converted_pip(self):
        """The pip moves whole, as a retained one is kept whole."""
        only_creatures = compile_restriction(["creature"], "t")
        p = ManaPool()
        p.add("G", 1, source=7, restriction=only_creatures)
        p.clear(5, colorless_instead=True)
        (pip,) = p.tags[C]
        assert pip.restriction is only_creatures and pip.source == 7
        assert p.spendable(None)[C] == 0  # still withheld from "no purpose"

    def test_without_the_flag_nothing_changes(self):
        p = ManaPool()
        p.add("R", 2)
        assert p.clear(5) == 2
        assert p.amounts[C] == 0


class TestHorizonStone:
    def test_coloured_mana_is_colorless_after_a_step_boundary(self, builder):
        game = position(builder, [STONE])
        float_mana(game, 0, R=2, G=1)
        advance(game.state)
        assert pool(game)[R] == 0 and pool(game)[G] == 0
        assert pool(game)[C] == 3

    def test_nothing_is_reported_lost(self, builder):
        game = position(builder, [STONE])
        float_mana(game, 0, R=2)
        before = len(game.state.events)
        advance(game.state)
        assert not [
            e
            for e in game.state.events[before:]
            if e.type == "mana_emptied" and e.player == 0
        ]

    def test_it_crosses_turns_and_pays_generic_but_not_red(self, builder):
        game = position(builder, [STONE], hand=[RR_SORCERY, GENERIC_SORCERY])
        float_mana(game, 0, R=2)
        pass_until(
            game,
            lambda g: g.state.turn == 3 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert pool(game)[C] == 2
        assert not casts_of(game, RR_SORCERY)
        game.apply(casts_of(game, GENERIC_SORCERY)[0])
        assert pool(game)[C] == 0

    def test_it_is_only_its_controllers_mana(self, builder):
        game = position(builder, [STONE])
        float_mana(game, 1, R=2)
        advance(game.state)
        assert pool(game, 1) == [0] * len(pool(game, 1))

    def test_the_first_boundary_after_it_leaves_empties_the_pool(self, builder):
        game = position(builder, [STONE])
        float_mana(game, 0, R=2)
        advance(game.state)
        move_object(game.state, oids_of(game, STONE, 0)[0], Zone.GRAVEYARD)
        assert pool(game)[C] == 2
        advance(game.state)
        assert pool(game)[C] == 0

    def test_beside_leyline_tyrant_red_stays_red(self, builder):
        game = position(builder, [STONE, TYRANT])
        float_mana(game, 0, R=2, G=1)
        advance(game.state)
        assert pool(game)[R] == 2 and pool(game)[G] == 0 and pool(game)[C] == 1

    def test_the_reader(self, builder):
        game = position(builder, [STONE])
        assert colorless_instead_players(game.state) == frozenset({0})
        assert colorless_instead_players(position(builder).state) == frozenset()


class TestTheLoader:
    def _card(self, **static):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": (
                    "If you would lose unspent mana, that mana becomes colorless instead."
                ),
                "mana_cost": "{5}",
                "types": ["Artifact"],
                "abilities": [
                    {"kind": "static", "effect": "mana_becomes_colorless", **static}
                ],
            }
        )

    def test_a_well_formed_static_loads(self):
        card = compile_card(self._card(affects_player="you"))
        assert card.abilities[0].static["effect"] == "mana_becomes_colorless"

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(self._card())

    def test_a_colour_list_is_refused(self):
        with pytest.raises(DslError, match="mana_retention"):
            compile_card(self._card(affects_player="you", colors=["G"]))

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(
                self._card(affects_player="you", affects={"types": ["Creature"]})
            )
