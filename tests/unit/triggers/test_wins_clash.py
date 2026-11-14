""""Whenever you win a clash" and "clash with defending player" -- rule 701.23.

Marvo, Deep Operative is the witness: "Whenever Marvo attacks, clash with
defending player." / "Whenever you win a clash, draw a card. Then you may cast
a spell from your hand with mana value 8 or less without paying its mana cost."

Both clashing players clash (701.23a) and either may win (701.23b), so the win
belongs to whoever revealed the bigger card, not to whoever's card made the
clash. `clash_won` is the near miss and is narrower: it is the instigator's
result, read only by the ability that clashed, so hanging Marvo's draw on an
`if` would pay for Marvo's own clashes and miss every clash won off any other
card. So `op_clash` fires one `CLASHED` per clashing player carrying that
player's own ``won``, and `wins_clash` hears the won ones.

The claims this file pins:

- **One event per clasher**, the instigator first, each with its own result.
- **A win, and only a win.** A loss pays nothing, a tie pays nobody, and an
  event that forgot to say ``won`` pays nothing either.
- **The winner is the actor.** An opponent who wins my clash has won a clash.
- **Any source.** A spell's clash counts as much as an attack trigger's.
- **"Clash with defending player"** names its opponent and asks nobody; a pool
  with no living opponent in it is no clash.
- **The loader** accepts a clash whose win only a `wins_clash` on the same card
  reads, and still refuses a clash nothing reads at all.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.triggers import fire
from tests.conftest import attack_with, find_action, only_oid, pass_until

WATCHER = "t_clash_watcher"   # Whenever you win a clash, you gain 1 life.
RAIDER = "t_clash_raider"     # Attacks: clash with defending player. Win: draw.
FOREST = "forest"             # mana value 0
BEAR = "t_bear"               # mana value 2
GIANT = "t_big"               # mana value 6


def position(builder, mine, theirs, *, watchers=((0, WATCHER),), players=2, third=()):
    b = builder(players=players).library(0, list(mine)).library(1, list(theirs))
    if players > 2:
        b = b.library(2, list(third))
    for pid, card in watchers:
        b = b.battlefield(pid, [card])
    return b.build(advance=False)


def clash(game, controller=0, *, spec=None, bindings=None, source=None):
    """Drive one clash for ``controller``, keeping both cards on top."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    if bindings:
        ctx.bindings.update(bindings)
    gen = OPS["clash"](ctx, spec or {"op": "clash"})
    asked, send = [], None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx, asked
        asked.append(decision.kind)
        send = [decision.options[0].player] if decision.kind is DecisionKind.CHOOSE_PLAYER else [0]


def clashed(game) -> list[tuple[int, int, bool]]:
    return [
        (e.player, e.data["opponent"], e.data["won"])
        for e in game.state.events
        if e.type == EventType.CLASHED
    ]


def queued(game, pid=None) -> int:
    """How many watcher triggers are waiting, optionally only ``pid``'s."""
    return sum(
        1
        for t in game.state.pending_triggers
        if game.state.objects[t.source_oid].def_id == WATCHER
        and (pid is None or t.controller == pid)
    )


class TestOneEventPerClasher:
    def test_each_clasher_hears_their_own_result(self, builder):
        game = position(builder, [GIANT], [BEAR])
        clash(game)
        assert clashed(game) == [(0, 1, True), (1, 0, False)], "the instigator first"

    def test_a_tie_is_two_lost_clashes(self, builder):
        game = position(builder, [BEAR], [BEAR])
        clash(game)
        assert clashed(game) == [(0, 1, False), (1, 0, False)]


class TestAWinAndOnlyAWin:
    def test_winning_triggers(self, builder):
        game = position(builder, [GIANT], [BEAR])
        clash(game)
        assert queued(game) == 1

    def test_losing_does_not(self, builder):
        game = position(builder, [BEAR], [GIANT])
        clash(game)
        assert queued(game) == 0

    def test_a_tie_pays_nobody(self, builder):
        game = position(builder, [BEAR], [BEAR], watchers=((0, WATCHER), (1, WATCHER)))
        clash(game)
        assert queued(game) == 0

    def test_an_event_that_does_not_say_won_does_not(self, builder):
        """Wider is the dangerous direction: a silent outcome is no win."""
        game = position(builder, [BEAR], [BEAR])
        fire(game.state, EventType.CLASHED, player=0, opponent=1)
        assert queued(game) == 0


class TestTheWinnerIsTheActor:
    def test_an_opponent_who_wins_my_clash_has_won_a_clash(self, builder):
        game = position(builder, [FOREST], [GIANT], watchers=((0, WATCHER), (1, WATCHER)))
        clash(game, controller=0)
        assert queued(game, pid=1) == 1, "their watcher: they won"
        assert queued(game, pid=0) == 0, "mine: I lost"

    def test_my_watcher_ignores_their_win(self, builder):
        game = position(builder, [FOREST], [GIANT])
        clash(game, controller=1)
        assert queued(game) == 0


class TestAnySource:
    def test_a_clash_off_a_spell_on_the_stack_counts(self, builder):
        game = position(builder, [GIANT], [BEAR])
        clash(game, source=None)
        assert queued(game) == 1


class TestClashWithDefendingPlayer:
    DEFENDER = {"op": "clash", "opponent": {"binding": "defender"}}

    def test_a_named_opponent_is_not_asked_for(self, builder):
        game = position(builder, [BEAR], [FOREST], players=3, third=[GIANT])
        ctx, asked = clash(game, spec=self.DEFENDER, bindings={"defender": 2})
        assert DecisionKind.CHOOSE_PLAYER not in asked
        assert ctx.bindings["clash_won"] == 0, "compared against seat 2's Giant"
        assert [opp for pid, opp, _ in clashed(game) if pid == 0] == [2]

    def test_an_opponent_not_in_the_pool_is_no_clash(self, builder):
        """The pool is narrowed to opponents: "you" names nobody to clash with."""
        game = position(builder, [GIANT], [BEAR])
        ctx, asked = clash(game, spec={"op": "clash", "opponent": "you"})
        assert asked == []
        assert ctx.bindings["clash_won"] == 0
        assert clashed(game) == []

    def test_the_attack_trigger_clashes_with_the_seat_attacked(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [RAIDER])
            .library(0, [BEAR, FOREST, FOREST])
            .library(1, [FOREST, FOREST])
            .library(2, [GIANT, FOREST])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.DECLARE_ATTACKERS,
        )
        attack_with(game, only_oid(game, RAIDER, 0), defender=2)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        hand = len(game.state.players[0].hand)
        pass_until(
            game, lambda g: bool(clashed(g)) and not g.state.stack and not g.state.pending_triggers
        )
        assert [opp for pid, opp, _ in clashed(game) if pid == 0] == [2], "never seat 1"
        assert len(game.state.players[0].hand) == hand, "lost to the Giant, so no draw"


def card(*abilities) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_clash_probe",
            "name": "Clash Probe",
            "oracle_text": "x",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": list(abilities),
        }
    )


ATTACK_CLASH = {
    "kind": "triggered",
    "text": "x",
    "trigger": {"event": "attacks"},
    "effects": [{"op": "clash", "opponent": {"binding": "defender"}}],
}
WINS = {
    "kind": "triggered",
    "text": "x",
    "trigger": {"event": "wins_clash", "controller": "you"},
    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
}


class TestTheLoader:
    def test_a_clash_heard_by_a_wins_clash_on_the_same_card_loads(self):
        compile_card(card(ATTACK_CLASH, WINS))

    def test_a_clash_nothing_hears_is_still_refused(self):
        with pytest.raises(DslError, match="wins_clash"):
            compile_card(card(ATTACK_CLASH))

    def test_a_wins_clash_alone_loads(self):
        """The watcher need not clash: it hears every clash at the table."""
        compile_card(card(WINS))

    def test_a_misspelled_opponent_is_refused(self):
        bad = dict(ATTACK_CLASH, effects=[{"op": "clash", "opponent": "each_oponent"}])
        with pytest.raises(DslError):
            compile_card(card(bad, WINS))
