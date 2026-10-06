"""``unplayable_reason`` -- the UI's "why can't I play this?" diagnostic.

The function restates gates that :mod:`automtg.engine.legality` already owns, so
the tests that matter most are the agreement ones: a reason must appear exactly
when no action names the card, and never when one does.  If a future change to
the generators drifts from the diagnostic, ``test_agrees_with_the_action_list``
is what fails.

Every position here is built with ``advance=False`` and then handed priority
explicitly.  Letting the engine advance would auto-pass a seat whose only legal
action is Pass -- which is precisely the seat these tests are about.
"""

from __future__ import annotations

from automtg.engine.actions import PendingDecision
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.legality import UNPLAYABLE_REASONS, legal_actions, unplayable_reason


def priority_to(game, pid: int = 0):
    """Freeze the game with ``pid`` holding priority, whatever it can do."""
    game.state.pending_decision = PendingDecision(kind=DecisionKind.PRIORITY, player=pid)
    return game


def reason_for(game, card_id: str, pid: int = 0) -> str | None:
    """The reason recorded against the first copy of ``card_id`` in hand."""
    for oid in game.state.players[pid].hand:
        if game.state.objects[oid].def_id == card_id:
            return unplayable_reason(game.state, pid, oid)
    raise AssertionError(f"{card_id} is not in player {pid}'s hand")


class TestAgreement:
    def test_agrees_with_the_action_list(self, builder):
        """No reason iff an action names the card. The whole contract, in one."""
        game = priority_to(
            builder()
            .hand(0, ["forest", "island", "llanowar_elves", "t_counterspell"])
            .battlefield(0, ["forest"])
            .build(advance=False)
        )
        named = {
            action.source
            for action in legal_actions(game.state)
            if action.kind in (ActionKind.PLAY_LAND, ActionKind.CAST)
        }
        for oid in game.state.players[0].hand:
            reason = unplayable_reason(game.state, 0, oid)
            assert (reason is None) == (oid in named), (
                f"{game.state.objects[oid].def_id}: reason={reason!r} but "
                f"{'an action names it' if oid in named else 'no action names it'}"
            )

    def test_agrees_when_nothing_at_all_is_playable(self, builder):
        game = priority_to(
            builder().hand(0, ["llanowar_elves", "t_counterspell"]).build(advance=False)
        )
        assert [a.kind for a in legal_actions(game.state)] == [ActionKind.PASS]
        for oid in game.state.players[0].hand:
            assert unplayable_reason(game.state, 0, oid) is not None

    def test_every_reason_is_a_known_one(self, builder):
        game = priority_to(
            builder().hand(0, ["forest", "t_counterspell"]).build(advance=False)
        )
        for oid in game.state.players[0].hand:
            reason = unplayable_reason(game.state, 0, oid)
            assert reason is None or reason in UNPLAYABLE_REASONS


class TestReasons:
    def test_a_land_with_a_drop_left_is_playable(self, builder):
        game = priority_to(builder().hand(0, ["forest"]).build(advance=False))
        assert reason_for(game, "forest") is None

    def test_land_drop_already_spent(self, builder):
        game = priority_to(
            builder().hand(0, ["forest"]).lands_played(0, 1).build(advance=False)
        )
        assert reason_for(game, "forest") == "land_drop"

    def test_a_sorcery_speed_card_outside_a_main_phase(self, builder):
        game = priority_to(
            builder()
            .hand(0, ["llanowar_elves"])
            .battlefield(0, ["forest"])
            .step(Step.UPKEEP)
            .build(advance=False)
        )
        assert reason_for(game, "llanowar_elves") == "timing"

    def test_a_land_outside_a_main_phase(self, builder):
        game = priority_to(
            builder().hand(0, ["forest"]).step(Step.UPKEEP).build(advance=False)
        )
        assert reason_for(game, "forest") == "timing"

    def test_not_enough_mana(self, builder):
        """No lands at all, so a one-drop is unaffordable rather than mistimed."""
        game = priority_to(builder().hand(0, ["llanowar_elves"]).build(advance=False))
        assert reason_for(game, "llanowar_elves") == "mana"

    def test_affordable_once_the_mana_is_there(self, builder):
        game = priority_to(
            builder()
            .hand(0, ["llanowar_elves"])
            .battlefield(0, ["forest"])
            .build(advance=False)
        )
        assert reason_for(game, "llanowar_elves") is None

    def test_a_tapped_source_does_not_count(self, builder):
        game = priority_to(
            builder()
            .hand(0, ["llanowar_elves"])
            .battlefield(0, ["forest"], tapped=True)
            .build(advance=False)
        )
        assert reason_for(game, "llanowar_elves") == "mana"

    def test_no_legal_target(self, builder):
        """Counterspell is affordable and instant-speed, but the stack is empty."""
        game = priority_to(
            builder()
            .hand(0, ["t_counterspell"])
            .battlefield(0, ["island", "island"])
            .build(advance=False)
        )
        assert reason_for(game, "t_counterspell") == "targets"

    def test_it_is_not_your_priority(self, builder):
        game = priority_to(
            builder().hand(1, ["forest"]).active(0).build(advance=False), pid=0
        )
        # Seat 0 holds priority, so seat 1 is shut out for a reason that has
        # nothing to do with the card it is holding.
        assert reason_for(game, "forest", pid=1) == "priority"


class TestOrdering:
    def test_timing_is_named_before_mana(self, builder):
        """A player who is broke *and* out of phase hears the phase problem.

        Timing is the gate that explains why the whole hand is dim on someone
        else's turn; naming a mana shortfall there would be noise.
        """
        game = priority_to(
            builder()
            .hand(0, ["llanowar_elves"])
            .step(Step.UPKEEP)
            .build(advance=False)
        )
        assert reason_for(game, "llanowar_elves") == "timing"

    def test_mana_is_named_before_targets(self, builder):
        game = priority_to(builder().hand(0, ["t_counterspell"]).build(advance=False))
        assert reason_for(game, "t_counterspell") == "mana"


class TestSerialized:
    def test_hand_reasons_reaches_the_player_view(self, builder):
        from automtg.engine.serialize import player_view

        game = priority_to(
            builder().hand(0, ["forest", "llanowar_elves"]).build(advance=False)
        )
        view = player_view(game.state, 0)
        reasons = view["players"][0]["hand_reasons"]
        # The forest is playable, so it is absent; the elves are not.
        assert len(reasons) == 1
        assert next(iter(reasons.values())) == "mana"

    def test_opponents_get_no_reasons(self, builder):
        from automtg.engine.serialize import player_view

        game = priority_to(
            builder().hand(0, ["forest"]).hand(1, ["forest"]).build(advance=False)
        )
        view = player_view(game.state, 0)
        assert view["players"][1]["hand_reasons"] is None
        assert view["players"][1]["hand"] is None
