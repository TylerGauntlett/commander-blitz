"""An extra turn, and skipping one.

"Take an extra turn after this one" (Time Warp); "Gift an extra turn ... they take
an extra turn after this one" (Perch Protection); "If an opponent would begin an
extra turn, that player skips that turn instead" (Trouble in Pairs).

Rule 500.7: an extra turn is added *directly after* the specified turn; several
are added one at a time, in APNAP order when several players get them; and the
most recently created is taken first. Before this the engine had no notion of a
turn that was not the next seat's -- `turn._begin_next_turn` advanced
`active_idx` by one live seat and that was the whole of the turn order. Four
things would each be wrong in a way a one-turn test does not see:

- **The turn order must not move.** Perch Protection's caster hands an opponent
  a turn. In a pod the next *ordinary* turn is still the seat after the caster's,
  not the seat after whoever just took the extra one -- which is why
  `GameState.turn_order_idx` exists at all. A version that simply set
  `active_idx` to the recipient would silently skip everyone between them.
- **Most recent first.** A stack, not a queue: a turn created during an extra
  turn comes straight after it, ahead of the ones already waiting.
- **The gift reaches the promised seat, and only when promised.** The
  `"gift_recipient"` spec resolves to nobody on the unpromised line, so the op
  schedules nothing -- the same mechanism that makes Parting Gust's Fish
  conditional. Written as `"opponent"` it would be a free turn for the whole
  table on every cast.
- **A skip is a replacement on the turn beginning** (614.1b, 614.10), not a
  filter on scheduling. Trouble in Pairs asked when the turn would begin catches
  a turn scheduled before it arrived, lets through one scheduled while it was
  out if it has gone by then, removes one queued turn per "would begin", and
  never touches an ordinary turn -- the printed line is inert against the normal
  order, and a skip that reached it would be a far stronger card.

The witnesses are `t_time_warp`, `t_gift_turn` (Perch Protection's reward alone),
`t_turns_for_all` and `t_turn_skipper` (Trouble in Pairs' first line alone), in
`tests/data/extra_turn.cards.json`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

TIME_WARP = "t_time_warp"  # {U} sorcery: take an extra turn
GIFT_TURN = "t_gift_turn"  # {W} instant: gift an extra turn; draw a card
TURNS_FOR_ALL = "t_turns_for_all"  # {U} sorcery: each player takes an extra turn
SKIPPER = "t_turn_skipper"  # opponents skip extra turns


def position(
    builder, *, players: int = 2, hand: list[str] | None = None, board: list[str] | None = None
):
    """Player 0 in their first main phase with ``hand``, every seat holding a stop.

    Every player has a Lightning Bolt and a Mountain. Never cast -- the passive
    answer is always Pass -- but it keeps a priority window open in every step,
    so the game surfaces a decision each turn instead of auto-passing the whole
    table inside one `apply`, and `turns` can stop where it is told to.
    """
    b = (
        builder(players=players)
        .hand(0, [*(hand or []), "lightning_bolt"])
        .battlefield(0, ["island", "plains", "mountain", *(board or [])])
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b = b.hand(pid, ["lightning_bolt"]).battlefield(pid, ["mountain"])
    return b.build()


def turns(game, count: int) -> list[tuple[int, bool]]:
    """The next ``count`` turns to begin, as ``(player, extra)``.

    Read off `TURN_BEGAN` rather than sampled from `active_player`, because the
    claim is about the *sequence*: a player taking two turns in a row is only
    visible as two events.
    """
    start = len(game.state.events)

    def begun(g):
        return [e for e in g.state.events[start:] if e.type == EventType.TURN_BEGAN]

    pass_until(game, lambda g: len(begun(g)) >= count, limit=3000)
    return [(e.player, bool(e.data.get("extra"))) for e in begun(game)[:count]]


def skipped(game) -> list[int]:
    return [e.player for e in game.state.events if e.type == EventType.TURN_SKIPPED]


def cast(game, card_id: str, **match) -> None:
    """Cast ``card_id`` from player 0's hand and pass until it has resolved."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and all(getattr(a, k) == v for k, v in match.items())
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)


def oid_of(game, def_id: str) -> int:
    return next(oid for oid, obj in game.state.objects.items() if obj.def_id == def_id)


class TestTheTurnComesDirectlyAfterThisOne:
    def test_time_warp_gives_its_caster_the_next_turn(self, builder):
        game = position(builder, hand=[TIME_WARP])
        cast(game, TIME_WARP)
        assert turns(game, 3) == [(0, True), (1, False), (0, False)]

    def test_without_one_the_table_goes_round(self, builder):
        """The control."""
        game = position(builder)
        assert turns(game, 2) == [(1, False), (0, False)]

    def test_an_extra_turn_is_a_turn_but_not_a_round(self, builder):
        """500.7: a turn in every respect -- it counts, it untaps -- but the
        table has not gone round, so the log's round number stays put."""
        game = position(builder, hand=[TIME_WARP])
        turn, rnd = game.state.turn, game.state.round
        cast(game, TIME_WARP)
        turns(game, 1)
        assert game.state.turn == turn + 1
        assert game.state.round == rnd
        assert game.state.extra_turn

    def test_only_an_extra_turn_says_so(self, builder):
        """`extra` is absent on an ordinary turn, so recorded logs do not change."""
        game = position(builder, hand=[TIME_WARP])
        cast(game, TIME_WARP)
        turns(game, 2)
        began = [e for e in game.state.events if e.type == EventType.TURN_BEGAN]
        assert began[-2].data.get("extra") is True
        assert "extra" not in began[-1].data
        assert not game.state.extra_turn

    def test_the_previous_turns_player_is_remembered(self, builder):
        """Day and night ask about the previous turn's active player (726.2),
        which after an extra turn is not the seat to the right."""
        game = position(builder, hand=[TIME_WARP])
        cast(game, TIME_WARP)
        turns(game, 1)
        assert game.state.active_player == 0
        assert game.state.previous_active == 0, "the seat to the right would say 1"


class TestTheGift:
    def test_the_promised_opponent_takes_the_turn(self, builder):
        """And the order resumes after the *caster*, so they take two in a row."""
        game = position(builder, hand=[GIFT_TURN])
        cast(game, GIFT_TURN, gift_to=1)
        assert turns(game, 3) == [(1, True), (1, False), (0, False)]

    def test_no_promise_no_turn(self, builder):
        """`gift_recipient` resolves to nobody, so nothing is scheduled."""
        game = position(builder, hand=[GIFT_TURN])
        cast(game, GIFT_TURN, gift_to=None)
        assert game.state.extra_turns == []
        assert turns(game, 2) == [(1, False), (0, False)]

    def test_at_a_pod_the_order_resumes_after_the_caster(self, builder):
        """Gifted to the seat across the table, the seat between is not skipped."""
        game = position(builder, players=3, hand=[GIFT_TURN])
        cast(game, GIFT_TURN, gift_to=2)
        assert turns(game, 4) == [(2, True), (1, False), (2, False), (0, False)]


class TestMostRecentFirst:
    def test_two_waiting_are_taken_newest_first(self, builder):
        game = position(builder, players=3)
        game.state.extra_turns.extend([1, 2])
        assert turns(game, 5) == [(2, True), (1, True), (1, False), (2, False), (0, False)]

    def test_a_turn_created_during_an_extra_turn_comes_straight_after_it(self, builder):
        """Created later, so it goes ahead of the one already waiting."""
        game = position(builder, players=3)
        game.state.extra_turns.extend([2, 1])
        pass_until(game, lambda g: g.state.extra_turn and g.state.active_player == 1, limit=3000)
        game.state.extra_turns.append(0)
        assert turns(game, 4) == [(0, True), (2, True), (1, False), (2, False)]

    def test_each_player_is_added_in_apnap_order(self, builder):
        """One at a time in APNAP order, newest first: the table in reverse."""
        game = position(builder, players=3, hand=[TURNS_FOR_ALL])
        cast(game, TURNS_FOR_ALL)
        assert game.state.extra_turns == [0, 1, 2]
        assert turns(game, 4) == [(2, True), (1, True), (0, True), (1, False)]

    def test_a_player_who_has_left_takes_no_turn(self, builder):
        game = position(builder, players=3)
        game.state.extra_turns.append(1)
        game.state.players[1].life = 0
        assert turns(game, 2) == [(2, False), (0, False)]
        assert game.state.extra_turns == []


class TestSkippingAnExtraTurn:
    def test_an_opponent_skips_theirs(self, builder):
        game = position(builder, board=[SKIPPER])
        game.state.extra_turns.append(1)
        turn = game.state.turn
        assert turns(game, 2) == [(1, False), (0, False)]
        assert skipped(game) == [1]
        assert game.state.turn == turn + 2, "a skipped turn takes no turn number"

    def test_the_controller_does_not(self, builder):
        """`affects_player: "opponent"`."""
        game = position(builder, board=[SKIPPER], hand=[TIME_WARP])
        cast(game, TIME_WARP)
        assert turns(game, 2) == [(0, True), (1, False)]
        assert skipped(game) == []

    def test_ordinary_turns_are_untouched(self, builder):
        """The printed line is inert against the normal turn order."""
        game = position(builder, board=[SKIPPER])
        assert turns(game, 3) == [(1, False), (0, False), (1, False)]
        assert skipped(game) == []

    def test_two_queued_turns_are_skipped_one_at_a_time(self, builder):
        game = position(builder, board=[SKIPPER])
        game.state.extra_turns.extend([1, 1])
        assert turns(game, 1) == [(1, False)]
        assert skipped(game) == [1, 1]

    def test_it_catches_a_turn_scheduled_before_it_arrived(self, builder):
        """Asked when the turn would begin, not when it was created."""
        game = position(builder, hand=[SKIPPER])
        game.state.extra_turns.append(1)
        move_object(game.state, oid_of(game, SKIPPER), Zone.BATTLEFIELD)
        assert turns(game, 1) == [(1, False)]
        assert skipped(game) == [1]

    def test_gone_before_the_turn_begins_it_skips_nothing(self, builder):
        game = position(builder, board=[SKIPPER])
        game.state.extra_turns.append(1)
        move_object(game.state, oid_of(game, SKIPPER), Zone.GRAVEYARD)
        assert turns(game, 2) == [(1, True), (1, False)]
        assert skipped(game) == []


class TestTheLoaderGuardsIt:
    def sorcery(self, effect: dict, **extra) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
            **extra,
        }

    def test_controller_is_refused(self):
        """Parting Gust aims its reward with `controller`; copied here it would
        be ignored and hand the promised turn to the caster."""
        with pytest.raises(DslError, match="player"):
            compile_card(
                CardModel.model_validate(
                    self.sorcery(
                        {"op": "extra_turn", "controller": "gift_recipient"},
                        gift="an extra turn",
                    )
                )
            )

    def test_a_bad_player_spec_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(self.sorcery({"op": "extra_turn", "player": "nobody"}))
            )

    def test_the_skip_needs_to_say_whose(self):
        card = {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{W}",
            "types": ["Enchantment"],
            "abilities": [{"kind": "static", "effect": "skip_extra_turn"}],
        }
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    def test_the_plain_forms_compile(self, registry):
        assert registry.get(GIFT_TURN).spell_effects[0] == {
            "op": "extra_turn",
            "player": "gift_recipient",
        }
        static = registry.get(SKIPPER).abilities[0].static
        assert static["effect"] == "skip_extra_turn"
        assert static["affects_player"] == "opponent"
