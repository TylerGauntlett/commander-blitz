"""A player who does not lose some of their mana as steps and phases end.

    "You don't lose unspent red mana as steps and phases end."
                                                    -- Leyline Tyrant
    "Players don't lose unspent mana as steps and phases end."
                                                    -- Upwelling

500.4 empties every mana pool as each step and phase ends, and names its own
exception: an effect may say some mana is not lost. Without the `mana_retention`
static there was no spelling of it -- `add_mana`'s `persists_until_end_of_turn`
is a rider on *one ability's* mana and runs out at end of turn, so it can neither
keep red mana a Mountain made nor carry it into the next turn, which is the
whole of Leyline Tyrant (the mana it is holding is what its death trigger pays).

**About the player, not the pip.** Tanuki Transplanter's sentence is about
"this mana" and rides on the pip (`test_mana_doesnt_empty.py`); Leyline Tyrant's
is about every red mana the player has, from whatever source, and is read off
the battlefield at each boundary by `player_statics.retained_mana_by_player`.
So it lasts exactly as long as the permanent does: the first boundary after it
leaves empties the pool.

**The end of the turn is just another boundary.** A turn ends when its cleanup
step ends (500.4 again), so the kept mana survives into the next turn and the
turn after -- across the opponent's turn too, which is when an instant-speed
player wants it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaPool
from commanderblitz.engine.player_statics import retained_mana_symbols
from commanderblitz.engine.serialize import full_view
from commanderblitz.engine.turn import advance
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of

TYRANT = "t_retain_red"  # "You don't lose unspent red mana..."
UPWELLING = "t_retain_all"  # "Players don't lose unspent mana..."
RR_SORCERY = "t_retain_rr"  # {R}{R}: Add {G}.

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
    """Pass priority, as whoever holds it, until ``done(game)``, declaring no
    attackers and no blockers on the way.

    Through `Game.apply` and `legal_actions` rather than `turn.advance`, so the
    priority loop, the auto-pass and the payment planner all see a pool that
    did not empty -- the claim is that nothing between them assumes it does.
    """
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


class TestThePool:
    """`ManaPool.clear` in isolation."""

    def test_a_kept_symbol_survives_the_end_of_the_turn(self):
        p = ManaPool()
        p.add("R", 2)
        assert p.clear(None, frozenset({"R"})) == 0
        assert p.amounts[R] == 2

    def test_other_symbols_in_the_same_pool_do_not(self):
        p = ManaPool()
        p.add("R", 2)
        p.add("G", 3)
        assert p.clear(5, frozenset({"R"})) == 3
        assert p.amounts[R] == 2
        assert p.amounts[G] == 0

    def test_a_tanuki_pip_still_keeps_until_end_of_turn_beside_it(self):
        """The two exceptions compose: the pip's own rider is still asked."""
        p = ManaPool()
        p.add("R", 1)
        p.add("G", 1, persists_through_turn=5)
        p.add("G", 1)
        assert p.clear(5, frozenset({"R"})) == 1
        assert p.amounts[R] == 1 and p.amounts[G] == 1
        assert [len(pips) for pips in p.tags] == list(p.amounts)

    def test_lose_all_unspent_mana_still_takes_everything(self):
        """Mana Short and a player leaving: the plain clear is untouched."""
        p = ManaPool()
        p.add("R", 2)
        assert p.clear() == 2


class TestLeylineTyrant:
    def test_red_mana_survives_a_step_boundary(self, builder):
        game = position(builder, [TYRANT])
        float_mana(game, 0, R=2, G=1)
        advance(game.state)
        assert pool(game)[R] == 2
        assert pool(game)[G] == 0

    def test_and_crosses_into_the_next_turns(self, builder):
        """Through the opponent's whole turn and into this player's next one,
        driven by passing priority -- the mana is still there and still pays."""
        game = position(builder, [TYRANT], hand=[RR_SORCERY])
        float_mana(game, 0, R=2)
        pass_until(game, lambda g: g.state.turn == 2)
        assert pool(game)[R] == 2
        pass_until(
            game,
            lambda g: g.state.turn == 3 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert pool(game)[R] == 2
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == RR_SORCERY
        )
        game.apply(cast)
        assert pool(game)[R] == 0

    def test_the_view_shows_the_kept_mana(self, builder):
        game = position(builder, [TYRANT])
        float_mana(game, 0, R=2)
        pass_until(game, lambda g: g.state.turn == 2)
        assert full_view(game.state)["players"][0]["mana_pool"]["R"] == 2

    def test_it_is_only_its_controllers_mana(self, builder):
        game = position(builder, [TYRANT])
        float_mana(game, 1, R=2)
        advance(game.state)
        assert pool(game, 1)[R] == 0

    def test_the_first_boundary_after_it_leaves_empties_the_pool(self, builder):
        game = position(builder, [TYRANT])
        float_mana(game, 0, R=2)
        advance(game.state)
        move_object(game.state, oids_of(game, TYRANT, 0)[0], Zone.GRAVEYARD)
        assert pool(game)[R] == 2  # leaving does not take the mana itself
        advance(game.state)
        assert pool(game)[R] == 0

    def test_the_emptying_event_counts_only_what_was_lost(self, builder):
        game = position(builder, [TYRANT])
        float_mana(game, 0, R=2, G=1)
        before = len(game.state.events)
        advance(game.state)
        lost = [
            e.data["amount"]
            for e in game.state.events[before:]
            if e.type == "mana_emptied" and e.player == 0
        ]
        assert lost == [1]


class TestUpwelling:
    def test_every_player_keeps_every_type(self, builder):
        game = position(builder, [UPWELLING])
        float_mana(game, 0, G=1, C=2)
        float_mana(game, 1, R=1)
        pass_until(game, lambda g: g.state.turn == 2)
        assert pool(game, 0)[G] == 1 and pool(game, 0)[C] == 2
        assert pool(game, 1)[R] == 1

    def test_the_reader_unions_two_sources(self, builder):
        game = position(builder, [TYRANT], [UPWELLING])
        assert retained_mana_symbols(game.state, 0) == frozenset("WUBRGC")
        assert retained_mana_symbols(game.state, 1) == frozenset("WUBRGC")


class TestTheLoader:
    def _card(self, **static):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You don't lose unspent red mana as steps and phases end.",
                "mana_cost": "{R}",
                "types": ["Enchantment"],
                "abilities": [{"kind": "static", "effect": "mana_retention", **static}],
            }
        )

    def test_a_well_formed_static_loads_with_its_colors(self):
        card = compile_card(self._card(affects_player="you", colors=["R"]))
        assert card.abilities[0].static["colors"] == ["R"]

    def test_colors_are_required(self):
        with pytest.raises(DslError, match="needs 'colors'"):
            compile_card(self._card(affects_player="you"))

    def test_an_empty_list_keeps_nothing_and_is_refused(self):
        with pytest.raises(DslError, match="needs 'colors'"):
            compile_card(self._card(affects_player="you", colors=[]))

    def test_an_unknown_symbol_is_refused(self):
        with pytest.raises(DslError, match="unknown mana symbol"):
            compile_card(self._card(affects_player="you", colors=["X"]))

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(self._card(colors=["R"]))

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(
                self._card(
                    affects_player="you", colors=["R"], affects={"types": ["Creature"]}
                )
            )
