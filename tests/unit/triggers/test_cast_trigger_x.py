"""A cast trigger reads the X the spell was cast with.

Rule 601.2b fixes X as the spell is announced, and a trigger on the cast
(603.2, "When you cast this spell, ...") goes on the stack above the spell and
resolves while the spell is still waiting there. Hydroid Krasis gains half X
life and draws half X cards then, rounded down; Nev, the Practical Dean puts X
+1/+1 counters on itself where X is the *cast spell's* X, not its own.

`event_bindings` binds `x` from the trigger source's `cast_x`, which
`stack.resolve` writes only as the spell resolves -- so without the cast event
carrying the X, the Krasis's trigger read 0 and gained and drew nothing, and a
watcher read its own X instead of the spell's. `Game._cast` (and every other
cast path) puts `x=item.x` on `SPELL_CAST`, and `x` is an `EVENT_BINDING_KEYS`
entry, so the event's X overrides the source's. A spell cast without paying its
mana cost has X = 0 (107.3b), and its cast event says so.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, only_oid, plus_one_counters, settle

KRASIS = "t_cast_x_krasis"
WATCHER = "t_cast_x_watcher"
BURN = "t_x_burn"
COUNTER = "t_counterspell"


def position(builder, hand, battlefield=(), lands=8):
    """Player 0 with ``lands`` Forests, Islands and Mountains; player 1 holds a
    Counterspell over two Islands, so the stack stops for a response."""
    pool = ["forest", "island", "mountain"] * lands
    return (
        builder(players=2)
        .battlefield(0, pool[:lands] + list(battlefield))
        .battlefield(1, ["island"] * 2)
        .hand(0, list(hand))
        .hand(1, [COUNTER])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )


def _priority(game, pid: int) -> None:
    """Answer everything passively until ``pid`` holds priority."""
    for _ in range(80):
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.PRIORITY and decision.player == pid:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"player {pid} never got priority")


def cast_with_x(game, card_id: str, x: int) -> None:
    """Player 0 casts ``card_id`` announcing X = ``x``, stopping with it on the stack."""
    _priority(game, 0)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(80):
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.CHOOSE_X:
            ordinal = [o.value for o in decision.options].index(x)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == ordinal
                )
            )
            continue
        if decision.kind is DecisionKind.PRIORITY:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("nobody got priority after the cast")


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def hand_size(game) -> int:
    return len(game.state.players[0].hand)


class TestTheCastTriggerReadsTheAnnouncedX:
    def test_x_five_gains_two_and_draws_two(self, builder):
        """Half of 5 is 2 each time, rounded down."""
        game = position(builder, [KRASIS])
        before_life, before_hand = life(game), hand_size(game)
        cast_with_x(game, KRASIS, 5)
        settle(game)
        assert life(game) == before_life + 2
        # The Krasis left the hand; two cards came in.
        assert hand_size(game) == before_hand - 1 + 2

    def test_the_trigger_resolves_while_the_spell_is_still_on_the_stack(self, builder):
        """The X is read before `stack.resolve` writes `cast_x` -- the case that read 0."""
        game = position(builder, [KRASIS])
        before = life(game)
        cast_with_x(game, KRASIS, 4)
        spell, trigger = game.state.stack
        assert spell.is_spell and not trigger.is_spell
        assert life(game) == before
        for _ in range(20):
            if len(game.state.stack) == 1:
                break
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            _priority(game, 1)
        assert len(game.state.stack) == 1 and game.state.stack[0].is_spell
        assert life(game) == before + 2

    def test_the_permanent_still_enters_with_x_counters(self, builder):
        game = position(builder, [KRASIS])
        cast_with_x(game, KRASIS, 3)
        settle(game)
        assert plus_one_counters(game, only_oid(game, KRASIS)) == 3


class TestTheBoundary:
    def test_x_one_rounds_down_to_nothing(self, builder):
        game = position(builder, [KRASIS])
        before_life, before_hand = life(game), hand_size(game)
        cast_with_x(game, KRASIS, 1)
        settle(game)
        assert life(game) == before_life
        assert hand_size(game) == before_hand - 1

    def test_x_zero_gains_and_draws_nothing(self, builder):
        game = position(builder, [KRASIS])
        before = life(game)
        cast_with_x(game, KRASIS, 0)
        settle(game)
        assert life(game) == before


class TestAWatcherReadsTheCastSpellsX:
    def test_the_spells_x_not_the_watchers_own(self, builder):
        """The watcher was cast for X = 0 here; the burn spell's X = 3 is the one read."""
        game = position(builder, [BURN], battlefield=[WATCHER])
        before = life(game)
        cast_with_x(game, BURN, 3)
        settle(game)
        assert life(game) == before + 3
        assert life(game, 1) == 40 - 3

    def test_a_spell_without_x_reads_zero(self, builder):
        """The watcher's own `cast_x` does not leak through when the spell has none."""
        game = position(builder, [BURN], battlefield=[WATCHER])
        watcher = only_oid(game, WATCHER)
        game.state.objects[watcher].cast_x = 7
        before = life(game)
        cast_with_x(game, BURN, 0)
        settle(game)
        assert life(game) == before
