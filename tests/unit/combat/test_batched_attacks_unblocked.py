"""Coveted Jewel -- "Whenever **one or more** creatures an opponent controls
attack you and aren't blocked, that player draws three cards and gains control
of this artifact. Untap it."

Rule 603.2c: an ability that triggers on "one or more" of something triggers
once for an event that does several of them at once, and 509.1h makes every
attacker blocked or unblocked at one instant, when the block declaration
closes. `ATTACKED_UNBLOCKED` fires once per creature, because that is what
flanking and frenzy need, so without a batch the printed ability queues once
per unblocked attacker: two creatures through would draw six cards and run the
control change twice. `combat.finish_blockers` now writes one ``batch`` on every
event of the declaration, and `attacks_unblocked` is in
`triggers.BATCHED_EVENTS`, so `batched: true` queues the ability once.

`creatures_attack_player` is the near miss and is batched already, per
defending player, but it fires as attackers are declared -- before anybody has
blocked -- so it cannot ask "aren't blocked".

"Attack **you**" is the `attacking_player: "you"` trigger filter (506.2: a
creature sent at your planeswalker is not attacking you), asked of each
attacker *before* the batch is spent, so a walker-bound creature cannot use up
the one firing. "That player" is `{"binding": "event_player"}`, the attacking
creature's controller.

`t_greedy_jewel` is the counterfactual, the same trigger without `batched`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import tap_permanent
from tests.conftest import _default_answer, oids_of, only_oid, settle

JEWEL = "t_coveted_jewel"
GREEDY = "t_greedy_jewel"
BEAR = "t_bear"
WALL = "t_wall"
WALKER = "t_walker"

#: Where a bear is sent: at a seat's face, or at that seat's planeswalker.
FACE = "face"
PW = "walker"


def position(builder, *, bears: int, p1=(), p2=(), players: int = 2):
    """Player 0 attacks with ``bears`` bears; player 1 (and 2) defend.

    Player 0 holds an instant and a land so priority genuinely stops after the
    block triggers, instead of auto-passing into the next turn's untap step --
    which would untap the Jewel and make "Untap it." look done.
    """
    b = builder(players=players)
    b.hand(0, ["t_bolt"])
    b.battlefield(0, ["mountain"] + [BEAR] * bears)
    if p1:
        b.battlefield(1, list(p1))
    if p2:
        b.battlefield(2, list(p2))
    for pid in range(players):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def combat(game, plan: list[tuple[int, str]], blocks: dict[int, int] | None = None):
    """Send player 0's bears per ``plan`` (``(seat, FACE | PW)`` each), then
    have the defenders block per ``blocks`` (blocker oid -> plan index).

    Returns ``(bears in plan order, player 0's hand size before blocks)``.
    """
    blocks = blocks or {}
    for _ in range(80):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    # Tapped once the untap step is behind us, so "Untap it." has something to do.
    for name in (JEWEL, GREEDY):
        for pid in range(len(game.state.players)):
            for oid in oids_of(game, name, pid):
                tap_permanent(game.state, oid)
    bears = list(oids_of(game, BEAR, 0))
    sent = []
    for seat, at in plan:
        oid = bears.pop(0)
        want = ("player", seat) if at == FACE else ("object", only_oid(game, WALKER, seat))
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any((t.kind, t.id) == want for t in a.targets)
            )
        )
        sent.append(oid)
    finish(game)
    hand = len(game.state.players[0].hand)
    for _ in range(80):
        if game.state.combat is None or game.state.combat.blockers_declared:
            break
        decision = game.pending()
        if decision.kind is DecisionKind.DECLARE_BLOCKERS:
            for blocker, index in blocks.items():
                if game.state.objects[blocker].controller != decision.player:
                    continue
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.ADD_BLOCKER
                        and a.source == blocker
                        and any(t.id == sent[index] for t in a.targets)
                    )
                )
            finish(game)
            continue
        game.apply(_default_answer(game, decision))
    settle(game)
    assert game.state.turn == 1, "still the turn the attack happened in"
    return sent, hand


def finish(game) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )


def drawn(game, hand_before: int) -> int:
    return len(game.state.players[0].hand) - hand_before


class TestOneOrMoreThroughIsOneTrigger:
    def test_two_unblocked_draw_three_once_and_take_the_jewel(self, builder):
        game = position(builder, bears=2, p1=(JEWEL,))
        jewel = only_oid(game, JEWEL, 1)
        _, hand = combat(game, [(1, FACE), (1, FACE)])

        assert drawn(game, hand) == 3
        assert game.state.objects[jewel].controller == 0
        assert not game.state.objects[jewel].tapped

    def test_without_batched_the_same_swing_draws_six(self, builder):
        game = position(builder, bears=2, p1=(GREEDY,))
        _, hand = combat(game, [(1, FACE), (1, FACE)])

        assert drawn(game, hand) == 6

    def test_one_blocked_and_one_through_still_fires(self, builder):
        game = position(builder, bears=2, p1=(JEWEL, WALL))
        jewel = only_oid(game, JEWEL, 1)
        wall = only_oid(game, WALL, 1)
        _, hand = combat(game, [(1, FACE), (1, FACE)], blocks={wall: 0})

        assert drawn(game, hand) == 3
        assert game.state.objects[jewel].controller == 0

    def test_each_jewel_hears_the_batch(self, builder):
        """Keyed by permanent too, so the first Jewel does not spend it."""
        game = position(builder, bears=1, p1=(JEWEL, JEWEL))
        _, hand = combat(game, [(1, FACE)])

        assert drawn(game, hand) == 6
        assert len(oids_of(game, JEWEL, 0)) == 2


class TestNothingThroughIsNothing:
    def test_every_attacker_blocked(self, builder):
        game = position(builder, bears=1, p1=(JEWEL, WALL))
        jewel = only_oid(game, JEWEL, 1)
        wall = only_oid(game, WALL, 1)
        _, hand = combat(game, [(1, FACE)], blocks={wall: 0})

        assert drawn(game, hand) == 0
        assert game.state.objects[jewel].controller == 1
        assert game.state.objects[jewel].tapped


class TestAttackYouIsYouOnly:
    def test_unblocked_at_your_planeswalker_is_not_attacking_you(self, builder):
        """506.2. And asked before the batch is spent: the walker-bound bear,
        first in the declaration, must not use up the one firing."""
        game = position(builder, bears=1, p1=(JEWEL, WALKER))
        jewel = only_oid(game, JEWEL, 1)
        _, hand = combat(game, [(1, PW)])

        assert drawn(game, hand) == 0
        assert game.state.objects[jewel].controller == 1

    def test_walker_and_face_together_fire_once(self, builder):
        game = position(builder, bears=2, p1=(JEWEL, WALKER))
        jewel = only_oid(game, JEWEL, 1)
        _, hand = combat(game, [(1, PW), (1, FACE)])

        assert drawn(game, hand) == 3
        assert game.state.objects[jewel].controller == 0

    def test_at_a_pod_an_attack_on_someone_else_is_not_you(self, builder):
        game = position(builder, bears=2, p1=(JEWEL,), players=3)
        jewel = only_oid(game, JEWEL, 1)
        _, hand = combat(game, [(2, FACE), (2, FACE)])

        assert drawn(game, hand) == 0
        assert game.state.objects[jewel].controller == 1


def _model(event: str) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x_batched",
            "name": "X",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": event, "controller": "opponent", "batched": True},
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_batched_attacks_unblocked_loads(self):
        compile_card(_model("attacks_unblocked"))

    def test_batched_becomes_blocked_is_still_refused(self):
        """Its events carry the batch too, but nothing has asked for "one or
        more creatures become blocked", so the flag stays refused there."""
        with pytest.raises(DslError, match="batched"):
            compile_card(_model("becomes_blocked"))
