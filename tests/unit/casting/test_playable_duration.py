"""An impulse permission whose clock outlives the turn it was granted in.

Two cards, two clocks, and the same missing idea:

- "Exile the top card of your library. You may play it **until your next end
  step**." (Haste Magic.)
- "Exile the top two cards of your library. **Until the end of your next turn**,
  you may play those cards." (Light Up the Stage.)

The engine had one duration -- `playable_turn`, compared against `state.turn` in
seven places -- and it is the impulse-draw "this turn". For either card that is a
**strictly worse** card than printed, which is the unusual direction and the
reason this is not a rounding error worth accepting. Haste Magic is an instant:
cast on an opponent's turn, the printed card lets you play the exiled card right
through your following turn, and `playable_this_turn` revokes it at the turn
boundary. Nothing on the board shows a permission expiring early, so the loss is
silent. `TestTheThisTurnPermissionIsShorter` keeps that card alive and measures
the difference.

Neither clock is arithmetic on a future turn number. Both are keyed to the
**player** and ended when their step arrives -- the choice detain, goad and
"until your next turn" all made, for the reason `_untap_step` gives: eliminating
a player moves everybody else's next turn, and extra turns move it again.

The two differ in one word, and it is the word "next". "Your next end step",
asked on your own turn, is *this* turn's -- so the permission is no longer than
the this-turn one. "Your next turn" is never the turn you are standing in, so
Light Up the Stage cast on your own turn lives through the whole of the
following one. `TestGrantedOnYourOwnTurn` is that pair.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

THIS_TURN = "t_impulse"  # playable_this_turn -- the duration the engine had
END_STEP = "t_haste_magic"  # playable: "your_next_end_step"
NEXT_TURN = "t_light_up"  # playable: "end_of_your_next_turn"


def position(builder, spell: str, *, seat: int = 0):
    """``seat`` casts ``spell``; the exiled card is always a Mountain.

    A land is the exiled card on purpose: "you may **play** it" covers a land
    drop, and a land needs no mana, so the permission is the only thing that can
    make the action legal or not.
    """
    hands = {0: ["t_plain_instant"], 1: ["t_plain_instant"]}
    hands[seat] = [spell]
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, ["mountain"] * 4)
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, hands[0])
        .hand(1, hands[1])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def hand_turn_to(game, seat: int, spell: str) -> None:
    """Pass until ``seat`` is active and seat 0 may cast ``spell`` in response.

    Two things the obvious version gets wrong, both silently.

    `game._advance()` first: a game built with `advance=False` has no pending
    decision, and `pass_until` returns the moment it finds none -- so without
    it this does nothing at all, the spell is cast on seat 0's own turn, and
    every "granted on an opponent's turn" claim below tests the other case.

    And the condition is the **action**, not the step. Reaching seat 1's
    precombat main is not enough: seat 0 has to hold priority there to cast an
    instant, and stopping at the step leaves the turn with the wrong player.
    """
    game._advance()
    pass_until(
        game,
        lambda g: g.state.active_player == seat
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == spell
            for a in g.legal_actions()
        ),
    )


def cast_it(game, spell: str) -> int:
    """Cast ``spell``, let it resolve, and return the oid it exiled."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == spell
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    exiled = [o for o in game.state.objects.values() if o.zone is Zone.EXILE]
    assert len(exiled) == 1, f"expected one exiled card, got {len(exiled)}"
    return exiled[0].oid


def playable(game, oid: int) -> bool:
    """Is the exiled card offered to its grantee right now?"""
    return any(a.source == oid for a in game.legal_actions())


def to_step(game, step: Step, seat: int, *, after_turn: int | None = None) -> None:
    pass_until(
        game,
        lambda g: g.state.step is step
        and g.state.active_player == seat
        and (after_turn is None or g.state.turn > after_turn),
    )


class TestTheGrantIsLiveImmediately:
    @pytest.mark.parametrize("spell", [THIS_TURN, END_STEP, NEXT_TURN])
    def test_every_duration_starts_on(self, builder, spell):
        """The control for all three: without it nothing below means anything."""
        game = position(builder, spell)
        oid = cast_it(game, spell)

        assert playable(game, oid)


class TestGrantedOnAnOpponentsTurn:
    """The case the this-turn permission gets wrong, and the reason for all this.

    Seat 1 is active; seat 0 casts the instant. The permission must survive into
    seat 0's own turn, which is where a card exiled on somebody else's turn is
    actually playable -- a land drop needs a main phase you own.
    """

    def position_on_their_turn(self, builder, spell: str):
        game = position(builder, spell)
        hand_turn_to(game, 1, spell)
        assert game.state.active_player == 1, "the premise of every test in this class"
        return game

    def test_the_end_step_clock_survives_to_your_turn(self, builder):
        game = self.position_on_their_turn(builder, END_STEP)
        oid = cast_it(game, END_STEP)
        turn = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=turn)

        assert playable(game, oid), "'until your next end step' reaches your next turn"

    def test_the_next_turn_clock_does_too(self, builder):
        game = self.position_on_their_turn(builder, NEXT_TURN)
        oid = cast_it(game, NEXT_TURN)
        turn = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=turn)

        assert playable(game, oid)


class TestTheThisTurnPermissionIsShorter:
    """Kept as a live card: this is the strictly worse card the durations avoid."""

    def test_it_is_gone_by_your_next_turn(self, builder):
        game = position(builder, THIS_TURN)
        hand_turn_to(game, 1, THIS_TURN)
        oid = cast_it(game, THIS_TURN)
        turn = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=turn)

        assert not playable(game, oid), "revoked at the turn boundary, silently"


class TestTheEndStepClockEnds:
    def test_it_is_gone_after_your_end_step(self, builder):
        """"until your next **end step**" -- and then no longer."""
        game = position(builder, END_STEP)
        oid = cast_it(game, END_STEP)
        turn = game.state.turn
        to_step(game, Step.END_STEP, 0)
        pass_until(game, lambda g: g.state.turn > turn)

        assert not playable(game, oid)

    def test_an_opponents_end_step_does_not_end_it(self, builder):
        """It is keyed to the grantee. Seat 1's end step is not seat 0's.

        The hook is applied directly rather than navigated to. Passing priority
        to a particular seat's end step and stopping there is unreliable -- the
        window seat 0 gets to cast on seat 1's turn may *be* that end step, in
        which case the hook has already run and the test would pass without
        having asked anything. Calling it is the claim: same state, seat 1
        active, and a permission belonging to seat 0 left alone.
        """
        from automtg.engine import turn as turn_module

        game = position(builder, END_STEP)
        hand_turn_to(game, 1, END_STEP)
        oid = cast_it(game, END_STEP)
        assert game.state.active_player == 1

        turn_module._expire_permissions(game.state, "your_next_end_step")

        assert game.state.objects[oid].playable_by == 0, "seat 1's end step is not yours"


class TestGrantedOnYourOwnTurn:
    """The one word the two clocks differ by, measured.

    Cast in your own precombat main, "your next end step" is *this* turn's, so
    the permission is no longer than the this-turn one. "Your next turn" is
    never the turn you are standing in, so it lives through the whole of the
    following one.
    """

    def played_next_turn(self, builder, spell: str) -> bool:
        game = position(builder, spell)
        oid = cast_it(game, spell)
        turn = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=turn)
        return playable(game, oid)

    def test_the_end_step_clock_does_not_reach_your_next_turn(self, builder):
        assert not self.played_next_turn(builder, END_STEP)

    def test_the_next_turn_clock_does(self, builder):
        assert self.played_next_turn(builder, NEXT_TURN)


class TestTheNextTurnClockEnds:
    def test_it_is_gone_the_turn_after_that(self, builder):
        game = position(builder, NEXT_TURN)
        oid = cast_it(game, NEXT_TURN)
        turn = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=turn)
        second = game.state.turn
        to_step(game, Step.PRECOMBAT_MAIN, 0, after_turn=second)

        assert not playable(game, oid)


class TestTheLoaderRefusesTheAmbiguousSpellings:
    def spell(self, effect):
        return {
            "id": "t_probe_playable",
            "name": "Probe Playable",
            "mana_cost": "{R}",
            "types": ["Instant"],
            "spell_effects": [effect],
        }

    def exile(self, **extra):
        return {
            "op": "look_at_top",
            "player": "you",
            "amount": {"const": 1},
            "objects": {"count": 1},
            "destination": "exile",
            **extra,
        }

    def test_both_spellings_at_once(self):
        """One key, two names -- a precedence rule nobody can read off the card."""
        with pytest.raises(DslError, match="two spellings of one key"):
            compile_card(
                CardModel.model_validate(
                    self.spell(self.exile(playable="this_turn", playable_this_turn=True))
                )
            )

    def test_an_unknown_duration(self):
        """A typo would grant no permission at all -- a card that says it does."""
        with pytest.raises(DslError, match="unknown 'playable' duration"):
            compile_card(
                CardModel.model_validate(self.spell(self.exile(playable="until_i_say_so")))
            )

    def test_playable_on_an_op_that_grants_nothing(self):
        with pytest.raises(DslError, match="grants no 'you may play it' permission"):
            compile_card(
                CardModel.model_validate(
                    self.spell({"op": "draw", "player": "you", "amount": {"const": 1},
                                "playable": "this_turn"})
                )
            )


class TestTheOldSpellingIsUnchanged:
    def test_playable_this_turn_still_means_this_turn(self, registry):
        card = registry.get(THIS_TURN)
        assert card.spell_effects[0]["playable_this_turn"] is True
        assert "playable" not in card.spell_effects[0]
