"""The permanents destroyed this way: `destroy`'s ``as`` binding.

    "Destroy all creatures. You gain 1 life for each creature **destroyed this
    way**."                                                          -- Avenge

The second sentence counts what the first one *did*, not what it was pointed
at. 701.8a: to destroy a permanent is to move it to its owner's graveyard, and
four things stop that move without the permanent being destroyed at all --
indestructible (702.12b), a regeneration shield (701.15a), a shield counter
(122.1c) and totem armor (702.88a). A creature saved by any of them was not
destroyed this way, so it is worth no life.

The near miss is counting the board before the wrath: a `snapshot`, or a
`count` of creatures written ahead of the `destroy`. It agrees with the printed
card exactly until somebody controls an indestructible creature or holds up a
regeneration shield, and then it gains a life for every survivor -- looking
implemented the whole time. `zones.destroy` has always answered "did it die";
`op_destroy` threw the answer away. ``as`` keeps the oids it was True for, as a
list read back with ``{"count": {"binding": …}}``, accumulating across a loop
the way `exile`'s record does.

Avenge is the witness. It waits on a second capability (its cost reduction) and
is not shipped yet; `t_dtw_avenge` in `tests/data/destroyed_this_way.cards.json`
is its second sentence.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects import RECORDING_OPS, execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Keyword, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import SHIELD
from commanderblitz.engine.primitives import add_counters, attach, create_token
from tests.conftest import action_for_card, oids_of, only_oid, settle

BEAR = "t_bear"  # 2/2, nothing else
TROLL = "t_regenerator"  # {G}: regenerate
AURA = "t_totem_armor"
AVENGE = "t_dtw_avenge"
SOLDIER = "human_soldier_1_1_w"

WRATH = {
    "op": "destroy",
    "objects": {"zone": "battlefield", "types": ["Creature"], "count": "all"},
    "as": "destroyed",
}
LIFE = {"op": "gain_life", "player": "you", "amount": {"count": {"binding": "destroyed"}}}


def board(builder, mine=(), theirs=()):
    """Player 0's ``mine`` facing player 1's ``theirs``, both at 40 life.

    Returns ``(game, oids)`` -- every creature's oid, player 0's first.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .life(0, 40)
        .life(1, 40)
        .build(advance=False)
    )
    oids = [o.oid for pid in (0, 1) for o in game.state.battlefield_objects(pid)]
    return game, oids


def run(game, effects) -> EffectContext:
    """Resolve a decision-free effect list for player 0 and hand back its context."""
    ctx = EffectContext(state=game.state, controller=0)
    for _ in execute(ctx, effects):  # pragma: no cover - nothing here asks
        raise AssertionError("a wrath asks no questions")
    return ctx


def shield(game, oid: int) -> None:
    """One regeneration shield on ``oid``, put there by its own ability."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    effects = [{"op": "regenerate", "objects": {"zone": "battlefield", "self_only": True}}]
    for _ in execute(ctx, effects):  # pragma: no cover - nothing here asks
        raise AssertionError("a shield asks no questions")


class TestEveryDestroyedCreatureCounts:
    def test_three_creatures_three_life(self, builder):
        game, oids = board(builder, [BEAR, BEAR], [BEAR])
        ctx = run(game, [WRATH, LIFE])

        assert sorted(ctx.bindings["destroyed"]) == sorted(oids)
        assert game.state.players[0].life == 43

    def test_an_empty_board_gains_nothing(self, builder):
        game, _ = board(builder)
        ctx = run(game, [WRATH, LIFE])

        assert ctx.bindings["destroyed"] == []
        assert game.state.players[0].life == 40

    def test_a_token_is_counted(self, builder):
        """A destroyed token goes to the graveyard before it ceases to exist
        (111.7), so it was destroyed, and the count is read in the same
        resolution -- before the state-based action takes it away."""
        game, _ = board(builder, [BEAR])
        token = create_token(game.state, SOLDIER, 1)[0]
        ctx = run(game, [WRATH, LIFE])

        assert token in ctx.bindings["destroyed"]
        assert game.state.players[0].life == 42

    def test_a_death_sent_to_exile_was_still_a_destruction(self, builder):
        """A replacement on *where* it goes does not undo *that* it was
        destroyed -- the creature left the battlefield to the wrath."""
        game, oids = board(builder, [BEAR, BEAR])
        game.state.objects[oids[0]].dies_to = "exile"
        run(game, [WRATH, LIFE])

        assert game.state.objects[oids[0]].zone is Zone.EXILE
        assert game.state.players[0].life == 42


class TestASurvivorIsNotCounted:
    """The four things that stop a destruction. Each is the near miss's error."""

    def test_indestructible(self, builder):
        game, oids = board(builder, [BEAR], [BEAR])
        game.state.objects[oids[1]].granted_keywords.add(Keyword.INDESTRUCTIBLE.value)
        game.state.bump_chars()
        ctx = run(game, [WRATH, LIFE])

        assert ctx.bindings["destroyed"] == [oids[0]]
        assert game.state.objects[oids[1]].zone is Zone.BATTLEFIELD
        assert game.state.players[0].life == 41

    def test_a_regeneration_shield(self, builder):
        game, _ = board(builder, [BEAR], [TROLL])
        troll = only_oid(game, TROLL)
        shield(game, troll)
        ctx = run(game, [WRATH, LIFE])

        assert troll not in ctx.bindings["destroyed"]
        assert game.state.objects[troll].zone is Zone.BATTLEFIELD
        assert game.state.players[0].life == 41

    def test_no_regeneration_puts_the_troll_back_in(self, builder):
        """The boundary of the one above: a Wrath of God's troll *was* destroyed."""
        game, _ = board(builder, [BEAR], [TROLL])
        troll = only_oid(game, TROLL)
        shield(game, troll)
        ctx = run(game, [{**WRATH, "no_regeneration": True}, LIFE])

        assert troll in ctx.bindings["destroyed"]
        assert game.state.players[0].life == 42

    def test_a_shield_counter(self, builder):
        game, oids = board(builder, [BEAR, BEAR])
        add_counters(game.state, oids[0], SHIELD, 1)
        ctx = run(game, [WRATH, LIFE])

        assert ctx.bindings["destroyed"] == [oids[1]]
        assert game.state.players[0].life == 41

    def test_totem_armor(self, builder):
        """The Aura is destroyed instead, and it is not a creature -- nor was it
        destroyed by *this* op's choice, so it is not in the record at all."""
        game, _ = board(builder, [BEAR, AURA])
        bear = only_oid(game, BEAR)
        aura = only_oid(game, AURA)
        attach(game.state, aura, bear)
        ctx = run(game, [WRATH, LIFE])

        assert ctx.bindings["destroyed"] == []
        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == 40


class TestTheRecord:
    def test_it_accumulates_under_one_name(self, builder):
        """Two destructions in one resolution, one count -- `exile`'s semantics."""
        game, oids = board(builder, [BEAR], [BEAR])
        mine = {**WRATH, "objects": {**WRATH["objects"], "controller": "you"}}
        theirs = {**WRATH, "objects": {**WRATH["objects"], "controller": "opponent"}}
        ctx = run(game, [mine, theirs, LIFE])

        assert ctx.bindings["destroyed"] == oids
        assert game.state.players[0].life == 42

    def test_without_as_nothing_is_bound(self, builder):
        game, _ = board(builder, [BEAR])
        plain = {k: v for k, v in WRATH.items() if k != "as"}
        ctx = run(game, [plain])

        assert "destroyed" not in ctx.bindings


class TestTheCard:
    def test_cast_and_resolved(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", BEAR, TROLL])
            .battlefield(1, [BEAR, BEAR])
            .hand(0, [AVENGE])
            .life(0, 40)
            .build()
        )
        shield(game, only_oid(game, TROLL))
        game.apply(action_for_card(game, ActionKind.CAST, AVENGE))
        settle(game)

        assert oids_of(game, BEAR) == []
        assert only_oid(game, TROLL) is not None
        assert game.state.players[0].life == 43


class TestTheLoader:
    def test_destroy_is_a_recording_op(self):
        assert "destroy" in RECORDING_OPS

    def test_as_on_destroy_loads(self):
        _validate_effect(WRATH, "test", {})

    def test_a_non_string_as_is_refused(self):
        with pytest.raises(DslError, match="'as' must be a non-empty binding name"):
            _validate_effect({**WRATH, "as": 3}, "test", {})
