"""Copying an **ability** on the stack — a different object from a spell.

    Peter Parker's Camera — "{2}, {T}, Remove a film counter from this artifact:
    Copy target activated or triggered ability you control. You may choose new
    targets for the copy."

Two things were missing, and neither was a near miss.

### An ability could not be targeted at all

`TargetModel.kind` was a closed Literal, and both stack-facing branches of
`enumerate_target_tuples` filtered on `item.is_spell` — which is exactly
`kind == "spell"`. So an ability on the stack was *unreachable* as a target
rather than awkward to name. 113.7a is why: an ability on the stack is its own
kind of object, with no card behind it, only a source, an index and its bindings.

`_spell_matches` is deliberately **not** reused by the new matcher.
`TestTheMatcherIsNarrow` is that claim: every clause that function reads is a
characteristic of a printed face, and asking it about an ability would silently
answer about the *source permanent* — so "target activated ability" would become
"target ability of a creature" the moment anyone wrote a `types` clause. That is
the same silently-inert selector `_spell_matches`'s own docstring says it exists
to prevent.

### `copy_spell` would have loaded and done nothing

`_spell_named_by` returns `None` for an ability on purpose, and
`put_copy_on_stack` builds `kind="spell"` around a `new_object` card token with
an `oid` — which an ability StackItem has not got. A Camera written with
`copy_spell` compiles, passes its gates and quietly copies nothing, which is why
the gap record refused it.

So `copy_ability` is `dataclasses.replace` with a fresh sid: 706.10's copiable
values are every field of the original, **including the bindings the trigger
captured** and the `x` that was announced. `TestTheCopyKeepsWhatMatters` pins
those, because a copy that lost its bindings would be a copied "whenever a land
enters" ability that no longer knows which land.

### What is deliberately *not* built

"Target **triggered** ability" alone — Strionic Resonator — is not expressible.
`StackItem.kind` is `"ability"` for both activated and triggered ones and nothing
on the item records which, so there is no honest way to filter. Guessing from
`bindings` would be wrong: an activated ability's cost writes bindings too, via
`costs.bind_paid_object`. The Camera and Lithoform Engine both say "activated or
triggered" and so need no distinction; a card that needs it needs a field first,
and is a gap record until it has one.

Witness: Peter Parker's Camera
(`peter_parker_s_camera` in `data/cards/auto/`).
"""

from __future__ import annotations

from dataclasses import replace

from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.stack import push_activated_ability
from commanderblitz.engine.structs import TargetRef
from tests.conftest import only_oid

CAMERA = "t_camera"
GAINER = "t_gainer"  # {T}: you gain 2 life -- no target
PINGER = "t_camera_pinger"  # {T}: target player loses 1 life
PLAINS = "plains"


def board(builder, mine=(CAMERA, GAINER)):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4 + list(mine))
        .battlefield(1, [PLAINS])
        .hand(0, [PLAINS])
        .build(advance=False)
    )


def builder_with_opponent_gainer(game):
    """Put a Gainer onto the opponent's battlefield in an existing game.

    Built by hand rather than through the builder because the position under test
    needs the Camera on one side and the ability's source on the other, which the
    fixture's single `battlefield(0, ...)` call cannot express.
    """
    from commanderblitz.engine.enums import Zone
    from commanderblitz.engine.state import new_object

    obj = new_object(game.state, GAINER, owner=1, zone=Zone.BATTLEFIELD)
    obj.controller = 1
    game.state.battlefield.append(obj.oid)
    game.state.bump_chars()
    return game


def ctx(game, targets=None, controller: int = 0, source=None) -> EffectContext:
    return EffectContext(
        state=game.state,
        controller=controller,
        source_oid=source,
        targets=dict(targets or {}),
    )


def run(ctx_, spec):
    gen = OPS["copy_ability"](ctx_, spec)
    sent = None
    while True:
        try:
            gen.send(sent)
        except StopIteration:
            return
        sent = [0]


class TestAnAbilityCanBeTargeted:
    def test_the_camera_sees_an_ability_on_the_stack(self, builder):
        from commanderblitz.engine.targeting import candidates

        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        camera = game.state.registry.get(CAMERA)
        spec = camera.abilities[0].targets[0]

        refs = candidates(game.state, 0, spec, only_oid(game, CAMERA, 0))
        assert [r.id for r in refs] == [item.sid]

    def test_a_spell_is_not_offered(self, builder):
        """The complement of the `spell` kind, not a widening of it: this branch
        takes only non-spell stack items."""
        from commanderblitz.engine.targeting import candidates

        game = board(builder)
        push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        camera = game.state.registry.get(CAMERA)
        spec = camera.abilities[0].targets[0]
        before = len(candidates(game.state, 0, spec, only_oid(game, CAMERA, 0)))

        # A spell on the stack must not enlarge the pool.
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.stack import push_spell
        from commanderblitz.engine.state import new_object

        obj = new_object(game.state, PLAINS, owner=0, zone=Zone.HAND)
        game.state.players[0].hand.append(obj.oid)
        push_spell(game.state, obj.oid, 0)

        assert len(candidates(game.state, 0, spec, only_oid(game, CAMERA, 0))) == before

    def test_an_opponents_ability_is_not_offered(self, builder):
        """"…you control" -- the one selector clause this kind honours."""
        from commanderblitz.engine.targeting import candidates

        game = board(builder, mine=(CAMERA,))
        # The Gainer on the opponent's side, so its activation is theirs.
        theirs = only_oid(
            builder_with_opponent_gainer(game), GAINER, 1
        )
        item = push_activated_ability(game.state, theirs, 0, 1)
        spec = game.state.registry.get(CAMERA).abilities[0].targets[0]

        refs = candidates(game.state, 0, spec, only_oid(game, CAMERA, 0))
        assert item.sid not in [r.id for r in refs]


class TestTheCopyKeepsWhatMatters:
    def test_a_copy_is_put_on_the_stack(self, builder):
        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        before = len(game.state.stack)

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})

        assert len(game.state.stack) == before + 1

    def test_the_copy_is_on_top(self, builder):
        """706.10 -- so it resolves first, which is the whole reason the card is
        worth playing."""
        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})

        assert game.state.stack[-1].sid != item.sid
        assert game.state.stack[-1].source_oid == item.source_oid

    def test_the_copy_has_a_fresh_sid(self, builder):
        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})
        copy = game.state.stack[-1]

        assert copy.sid != item.sid, "a shared sid would make them one object"

    def test_it_keeps_the_bindings_the_trigger_captured(self, builder):
        """706.10's copiable values. A copy that lost these would be a copied
        "whenever a land enters" ability that no longer knows which land."""
        game = board(builder)
        item = push_activated_ability(
            game.state, only_oid(game, GAINER, 0), 0, 0, bindings={"subject": [99]}
        )

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})

        assert game.state.stack[-1].bindings == {"subject": [99]}

    def test_it_keeps_the_announced_x(self, builder):
        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0, x=3)

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})

        assert game.state.stack[-1].x == 3


class TestItFizzlesRatherThanCrashes:
    def test_an_ability_that_already_resolved_is_skipped(self, builder):
        """608.2b, and the printed behaviour: a Camera activation whose target
        resolved first does nothing."""
        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        game.state.stack.remove(item)
        before = len(game.state.stack)

        run(ctx(game, {"t1": [TargetRef.stack(item.sid)]}), {"target": "t1"})

        assert len(game.state.stack) == before

    def test_a_spell_ref_is_skipped(self, builder):
        """Defensive: the op copies abilities, and a spell handed to it is not
        one. `copy_spell` is the op for that and they are not interchangeable."""
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.stack import push_spell
        from commanderblitz.engine.state import new_object

        game = board(builder)
        obj = new_object(game.state, PLAINS, owner=0, zone=Zone.HAND)
        game.state.players[0].hand.append(obj.oid)
        spell = push_spell(game.state, obj.oid, 0)
        before = len(game.state.stack)

        run(ctx(game, {"t1": [TargetRef.stack(spell.sid)]}), {"target": "t1"})

        assert len(game.state.stack) == before


class TestTheMatcherIsNarrow:
    """`_spell_matches` is not reused, and this is why.

    An ability has no printed face, so a `types` clause asked of it would answer
    about the source permanent -- turning "target activated ability" into "target
    ability of a creature" without anything saying so. The loader is the guard;
    here we pin that the matcher itself honours only `controller`.
    """

    def test_controller_you_is_honoured(self, builder):
        from commanderblitz.engine.targeting import _ability_matches

        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        spec = game.state.registry.get(CAMERA).abilities[0].targets[0]

        assert _ability_matches(ctx(game), item, spec) is True
        assert _ability_matches(ctx(game, controller=1), item, spec) is False

    def test_an_unrelated_clause_is_ignored_rather_than_misread(self, builder):
        """If somebody does get a `types` clause past the loader, it must not be
        answered off the source permanent -- it is simply not consulted."""
        from commanderblitz.engine.targeting import _ability_matches

        game = board(builder)
        item = push_activated_ability(game.state, only_oid(game, GAINER, 0), 0, 0)
        spec = game.state.registry.get(CAMERA).abilities[0].targets[0]
        widened = replace(spec, selector={"controller": "you", "types": ["Creature"]})

        # The Gainer is an Artifact, not a Creature. A `_spell_matches`-style read
        # would reject it; this matcher ignores the clause entirely.
        assert _ability_matches(ctx(game), item, widened) is True
