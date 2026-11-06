""""Exile <this card> with three time counters on it." -- `suspends_itself`

    Rousing Refrain, Suspended Sentence -- "... **Exile Suspended Sentence with
    three time counters on it.** Suspend 3--{1}{B}"

608.2n puts a resolved instant or sorcery into its owner's graveyard; this
card's own last instruction puts it in exile instead, with N time counters on
it, and because it has suspend those counters tick down at its owner's upkeep
and it is cast for free when the last one comes off (702.62). Cast that way, it
resolves and exiles itself again: the card recurs for the whole game.

**The near misses.** `exiles_itself` exiles with no counters and no suspended
mark, so the card never comes back. A `suspend` op in the card's own effects
runs while the spell is already off the stack, and `_place_after_resolution`
then moves it on to the graveyard regardless, wiping the mark. Hence a rider on
the resolution slot, read in `stack._place_after_resolution`.

**Only on resolution.** A spell whose every target is gone does not resolve
(608.2b) and goes to the graveyard, with none of its instructions carried out.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.suspend import TIME_COUNTER
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, pass_until

SPELL = "t_suspends_itself"  # sorcery: gain 2 life; exile it with two time counters
KILL = "t_suspends_itself_kill"  # instant: destroy target creature; the same rider
BEAR = "grizzly_bears"


def board(builder, card_id: str = SPELL):
    """Seat 0 holds two copies and the mana for them; seat 1 has a Bear to target.

    The second copy is what keeps seat 0 at priority with the first on the
    stack: with nothing left to do, the engine would auto-pass straight through
    the resolution and on into the next turn.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + ["swamp"] * 4)
        .battlefield(1, [BEAR])
        .hand(0, [card_id, card_id])
        .library(0, ["plains"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )
    return game, game.state.players[0].hand[0]


def cast(game, oid: int) -> None:
    """Cast that copy, at the Bear if it takes a target."""
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid))


def resolve(game) -> None:
    """Pass until the stack is empty and the table is back at priority."""
    for _ in range(200):
        decision = game.pending()
        if not game.state.stack and decision.kind is DecisionKind.PRIORITY:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def past_the_next_upkeep_of(game, pid: int) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == pid
        and g.state.step > Step.UPKEEP,
    )


class TestAsItResolves:
    def test_it_is_exiled_with_its_time_counters_and_suspended(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.EXILE
        assert oid in game.state.players[0].exile
        assert oid not in game.state.players[0].graveyard
        assert obj.counter(TIME_COUNTER) == 2
        assert obj.suspended_by == 0

    def test_its_effects_still_happened(self, builder):
        game, oid = board(builder)
        life = game.state.players[0].life
        cast(game, oid)
        resolve(game)
        assert game.state.players[0].life == life + 2


class TestItComesBack:
    def test_the_countdown_casts_it_again_and_it_suspends_itself_again(self, builder):
        """The recurrence: two of my upkeeps, a free cast, and back into exile."""
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        life = game.state.players[0].life

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 1
        assert game.state.players[0].life == life, "not cast yet"

        past_the_next_upkeep_of(game, 0)
        pass_until(game, lambda g: g.state.players[0].life == life + 2)
        resolve(game)
        obj = game.state.objects[oid]
        assert game.state.players[0].life == life + 2, "cast free and resolved"
        assert obj.zone is Zone.EXILE
        assert obj.counter(TIME_COUNTER) == 2
        assert obj.suspended_by == 0

    def test_the_opponents_upkeep_does_not_tick_it(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        past_the_next_upkeep_of(game, 1)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 2


class TestOnlyOnResolution:
    def test_a_spell_whose_target_is_gone_goes_to_the_graveyard(self, builder):
        """608.2b: it does not resolve, so its last instruction never happens."""
        game, oid = board(builder, KILL)
        bear = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)
        cast(game, oid)
        assert game.state.stack, "on the stack, targeting the Bear"
        move_object(game.state, bear, Zone.GRAVEYARD, cause="test")
        resolve(game)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.GRAVEYARD
        assert obj.counter(TIME_COUNTER) == 0
        assert obj.suspended_by is None

    def test_with_its_target_it_destroys_and_suspends(self, builder):
        game, oid = board(builder, KILL)
        bear = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[oid].zone is Zone.EXILE
        assert game.state.objects[oid].suspended_by == 0


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_suspends_itself",
                "name": "Bad Suspends Itself",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "colors": ["W"],
                "color_identity": ["W"],
                "types": ["Sorcery"],
                "spell_effects": [{"op": "gain_life", "amount": {"const": 1}}],
                **extra,
            }
        )

    def test_it_loads(self):
        assert compile_card(self._card(suspends_itself=3)).suspends_itself == 3

    def test_absent_is_none(self):
        assert compile_card(self._card()).suspends_itself is None

    def test_no_counters_is_refused(self):
        with pytest.raises(Exception, match="suspends_itself"):
            compile_card(self._card(suspends_itself=0))

    def test_a_permanent_carrying_it_is_refused(self):
        with pytest.raises(Exception, match="suspends_itself"):
            compile_card(
                self._card(
                    types=["Creature"], power=1, toughness=1, spell_effects=[],
                    suspends_itself=2,
                )
            )

    @pytest.mark.parametrize(
        "other", [{"exiles_itself": True}, {"rebound": True}, {"tucks_itself": "bottom"}]
    )
    def test_another_destination_beside_it_is_refused(self, other):
        with pytest.raises(Exception, match="suspends_itself"):
            compile_card(self._card(suspends_itself=2, **other))
