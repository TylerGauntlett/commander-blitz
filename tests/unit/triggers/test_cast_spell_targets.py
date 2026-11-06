"""What a cast spell targets, asked by a trigger about the cast -- two questions
with two different clocks.

**"Whenever you cast a spell with one or more targets, draw that many cards"**
(Voracious Bibliophile). Both halves are about the cast: "with one or more
targets" qualifies the event, so it is asked as the trigger is collected and
never again (603.4 re-checks only an intervening "if"), and "that many" is the
number the spell was cast with. `Game._cast` puts it on `SPELL_CAST` as
`spell_target_count`, every target of every kind, once per target instance
(115.3) -- the `spell_targets` binding is the near miss and carries only
object targets, so a spell aimed at a player read as targetless. Because it is
a snapshot, the spell countered in response still draws its count.

**"…copy that spell if it targets a permanent or player … If you don't copy a
spell this way, draw a card"** (Shiko and Narset, Unified). This "if" sits in
the effect, so it is asked as the ability resolves, of the spell as it is then.
`targets_of_spell` reads the trigger's `sid` live off the stack: a spell
countered in response targets nothing, is not copied, and the draw is the
branch taken. Answered from the cast-time snapshot instead, it would take the
copy branch, copy nothing, and draw nothing -- the printed card always does
one or the other.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pt, settle

BIBLIOPHILE = "t_bibliophile"
SHIKO = "t_shiko"
PUMP = "t_pump_bear"  # target Bear
PLAYER_SPELL = "t_pump_player"  # target player
UNTARGETED = "t_untargeted_gain"
TWIN = "t_twin_gain"  # target player, target player
COUNTER = "t_counterspell"

BEAR = "t_bear"
ISLAND = "island"


def position(builder, watcher: str, hand: list[str]):
    """The watcher and a Bear out for player 0; a Counterspell held by player 1."""
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 6 + [watcher, BEAR])
        .battlefield(1, [ISLAND] * 2)
        .hand(0, list(hand))
        .hand(1, [COUNTER])
        .library(0, ["plains"] * 10)
        .library(1, ["plains"] * 10)
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


def cast(game, card_id: str, targets=None) -> None:
    """Player 0 casts ``card_id`` (at ``targets`` when given), stopping on the stack."""
    _priority(game, 0)
    action = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == card_id
            and (targets is None or tuple(a.targets) == tuple(targets))
        ),
        None,
    )
    assert action is not None, f"no cast of {card_id} at {targets}"
    game.apply(action)
    for _ in range(80):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.PRIORITY:
            return
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("nobody got priority after the cast")


def counter_in_response(game) -> None:
    """Player 0 passes; player 1 counters player 0's spell over the trigger."""
    spell = next(item for item in game.state.stack if item.is_spell)
    if game.pending().player == 0:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    _priority(game, 1)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and TargetRef.stack(spell.sid) in tuple(a.targets)
        )
    )


def library(game) -> int:
    return len(game.state.players[0].library)


def life(game) -> int:
    return game.state.players[0].life


class TestBibliophileCountsEveryTarget:
    def test_a_permanent_target_is_one(self, builder):
        game = position(builder, BIBLIOPHILE, [PUMP])
        cast(game, PUMP)
        settle(game)
        assert library(game) == 9

    def test_a_player_target_is_one(self, builder):
        """The case `spell_targets` cannot see: it holds object targets only."""
        game = position(builder, BIBLIOPHILE, [PLAYER_SPELL])
        cast(game, PLAYER_SPELL, (TargetRef.player(1),))
        settle(game)
        assert library(game) == 9

    def test_two_players_are_two_targets(self, builder):
        game = position(builder, BIBLIOPHILE, [TWIN])
        cast(game, TWIN, (TargetRef.player(0), TargetRef.player(1)))
        settle(game)
        assert library(game) == 8


class TestBibliophileDoesNotTriggerOnATargetlessSpell:
    def test_nothing_goes_on_the_stack(self, builder):
        game = position(builder, BIBLIOPHILE, [UNTARGETED])
        cast(game, UNTARGETED)
        assert [item.is_spell for item in game.state.stack] == [True], (
            "no trigger: 'with one or more targets' is part of the event"
        )
        settle(game)
        assert library(game) == 10


class TestBibliophileCountIsTheCasts:
    def test_a_spell_countered_in_response_still_draws_its_count(self, builder):
        """The count is a snapshot of the cast, not a read of the stack."""
        game = position(builder, BIBLIOPHILE, [TWIN])
        before = life(game)
        cast(game, TWIN, (TargetRef.player(0), TargetRef.player(1)))
        counter_in_response(game)
        settle(game)
        assert life(game) == before, "the spell was countered"
        assert library(game) == 8


class TestShikoCopiesWhatTargetsAPermanentOrPlayer:
    def test_the_first_spell_does_nothing(self, builder):
        game = position(builder, SHIKO, [PUMP])
        bear = only_oid(game, BEAR, 0)
        cast(game, PUMP)
        settle(game)
        assert pt(game, bear) == (3, 3)
        assert library(game) == 10

    def test_a_second_spell_at_a_permanent_is_copied(self, builder):
        game = position(builder, SHIKO, [UNTARGETED, PUMP])
        bear = only_oid(game, BEAR, 0)
        cast(game, UNTARGETED)
        settle(game)
        cast(game, PUMP)
        settle(game)
        assert pt(game, bear) == (4, 4), "the spell and its copy"
        assert library(game) == 10, "copied, so no card"

    def test_a_second_spell_at_a_player_is_copied(self, builder):
        game = position(builder, SHIKO, [UNTARGETED, PLAYER_SPELL])
        cast(game, UNTARGETED)
        settle(game)
        before = life(game)
        cast(game, PLAYER_SPELL, (TargetRef.player(0),))
        settle(game)
        assert life(game) == before + 2, "the spell and its copy"
        assert library(game) == 10

    def test_a_second_targetless_spell_draws_instead(self, builder):
        game = position(builder, SHIKO, [UNTARGETED, UNTARGETED])
        cast(game, UNTARGETED)
        settle(game)
        before = life(game)
        cast(game, UNTARGETED)
        settle(game)
        assert life(game) == before + 1, "not copied"
        assert library(game) == 9


class TestShikoAsksOnResolution:
    def test_a_spell_countered_in_response_is_not_copied_so_it_draws(self, builder):
        """Read live: the snapshot would take the copy branch and do nothing."""
        game = position(builder, SHIKO, [UNTARGETED, PLAYER_SPELL])
        cast(game, UNTARGETED)
        settle(game)
        before = life(game)
        cast(game, PLAYER_SPELL, (TargetRef.player(0),))
        counter_in_response(game)
        settle(game)
        assert life(game) == before
        assert library(game) == 9


class TestTargetsOfSpellReadsTheStackNow:
    """The value directly, with the triggering spell held on the stack."""

    def _ctx(self, game):
        spell = next(item for item in game.state.stack if item.is_spell)
        return EffectContext(state=game.state, controller=0, bindings={"sid": spell.sid})

    def test_it_counts_by_kind(self, builder):
        game = position(builder, BIBLIOPHILE, [PUMP])
        cast(game, PUMP)
        ctx = self._ctx(game)
        assert evaluate_value(ctx, {"targets_of_spell": ["permanent"]}) == 1
        assert evaluate_value(ctx, {"targets_of_spell": ["player"]}) == 0
        assert evaluate_value(ctx, {"targets_of_spell": ["permanent", "player"]}) == 1

    def test_a_permanent_that_left_is_not_a_permanent_it_targets(self, builder):
        game = position(builder, BIBLIOPHILE, [PUMP])
        bear = only_oid(game, BEAR, 0)
        cast(game, PUMP)
        ctx = self._ctx(game)
        move_object(game.state, bear, Zone.HAND)
        assert evaluate_value(ctx, {"targets_of_spell": ["permanent"]}) == 0

    def test_a_trigger_with_no_spell_reads_zero(self, builder):
        game = position(builder, BIBLIOPHILE, [])
        ctx = EffectContext(state=game.state, controller=0, bindings={})
        assert evaluate_value(ctx, {"targets_of_spell": ["player"]}) == 0


class TestTheLoaderRefusesWhatItCannotRead:
    @pytest.mark.parametrize(
        "kinds", [[], ["spell"], "player", ["permanent", "card"], None]
    )
    def test_bad_kinds(self, kinds):
        with pytest.raises(DslError, match="targets_of_spell"):
            validate_value({"targets_of_spell": kinds}, "here")

    def test_good_kinds(self):
        validate_value({"targets_of_spell": ["player", "permanent"]}, "here")
