"""The Eagles Are Coming! — a target list whose *size* depends on a cost, and a
delayed trigger that counts what came back.

    "Kicker {2}{W}{W}. Choose target creature you own. **If this spell was
    kicked, instead choose any number of target creatures you own.** Return each
    chosen creature to your hand. At the beginning of the next upkeep, create a
    4/4 white Bird Soldier creature token with flying **for each creature
    returned to your hand this way**."

Kicker itself was never the gap: `kicker` is a card-level cost and
`{"kicked": true}` is a live `if` condition. Two other things were.

### The target count, and the rules order the engine had half right

`targeting.resolve_count`'s docstring says a spell's own targets are fixed
"before it has been paid for", and concludes there is nothing to read. Payment
*is* later — 601.2h — but **kicker is announced at 601.2b, one step before
targets are declared at 601.2c**. The choice is already made when the targets are
chosen, which is exactly why this card can be printed.

What was actually missing was plumbing: `_cast_variant` receives one tuple set,
built from the printed counts, and is called for the unkicked and kicked lines
alike. So the kicked line now gets its own enumeration from `_kicked_targets`.

It is a **second count** rather than a value expression because the two sizes are
not two numbers — unkicked is exactly one and kicked is `"any"`, which no
arithmetic yields. `TestTheKickedLineTargetsAnyNumber` measures both lines on one
board, which is the only way to show the switch rather than assert it.

### The binding, which is what makes the delayed half sayable at all

A `{"target": …}` inside a `delay` is refused by name: `_run_delayed` rebuilds its
context with `targets={}`, so the reference would resolve to nothing. `op_delay`
*does* copy `ctx.bindings` forward, so an `as` binding survives where a target
cannot — and that refusal's own docstring names `as` as the intended idiom.
`return_to_hand` simply never had one, though `op_exile` and `op_sacrifice` both
do.

Witness: The Eagles Are Coming!
(`the_eagles_are_coming` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.actions import TargetRef
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import oids_of

EAGLES = "t_eagles"
BEAR = "t_bear"
PLAINS = "plains"


def position(builder, creatures=3, lands=8):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands + [BEAR] * creatures)
        .battlefield(1, [PLAINS])
        .hand(0, [EAGLES])
        .hand(1, [PLAINS])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_lines(game, kicked: bool):
    game._advance()
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == EAGLES
        and a.kicked is kicked
    ]


def target_counts(lines) -> set[int]:
    """How many permanents each offered line targets."""
    return {len([t for t in a.targets if t.kind == "object"]) for a in lines}


class TestTheKickedLineTargetsAnyNumber:
    def test_the_unkicked_line_takes_exactly_one(self, builder):
        game = position(builder)
        counts = target_counts(cast_lines(game, kicked=False))
        assert counts == {1}, counts

    def test_the_kicked_line_takes_any_number(self, builder):
        """Three creatures on the board, so the kicked line should offer sizes
        above one -- which is the whole switch."""
        game = position(builder)
        counts = target_counts(cast_lines(game, kicked=True))
        assert max(counts) > 1, counts

    def test_both_lines_are_offered_at_once(self, builder):
        """601.2b is a choice, so the printed cheap line survives beside it."""
        game = position(builder)
        assert cast_lines(game, kicked=False)
        assert cast_lines(game, kicked=True)

    def test_an_ordinary_card_is_unaffected(self, builder):
        """`_kicked_targets` returns None when nothing carries the key, so every
        other kicker card reuses the shared enumeration exactly as before."""
        from automtg.engine.targeting import kicked_targets

        game = position(builder)
        card = game.state.registry.get(EAGLES)
        assert kicked_targets(card.targets) is not None
        assert kicked_targets(game.state.registry.get(BEAR).targets) is None


class TestTheReturnBinding:
    def test_it_records_what_was_returned(self, builder):
        game = position(builder)
        bears = oids_of(game, BEAR, 0)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=None,
            targets={"t1": [TargetRef.obj(o) for o in bears]},
        )
        list(OPS["return_to_hand"](ctx, {"objects": {"target": "t1"}, "as": "returned"}))

        assert ctx.bindings["returned"] == list(bears)
        assert all(game.state.objects[o].zone is Zone.HAND for o in bears)

    def test_without_the_key_nothing_is_recorded(self, builder):
        game = position(builder)
        bears = oids_of(game, BEAR, 0)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=None,
            targets={"t1": [TargetRef.obj(o) for o in bears]},
        )
        list(OPS["return_to_hand"](ctx, {"objects": {"target": "t1"}}))

        assert "returned" not in ctx.bindings

    def test_it_extends_rather_than_replaces(self, builder):
        """A `for_each_player` loop around the op has to accumulate, which is why
        `op_exile` extends its binding too."""
        game = position(builder)
        bears = oids_of(game, BEAR, 0)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=None,
            targets={
                "a": [TargetRef.obj(bears[0])],
                "b": [TargetRef.obj(bears[1])],
            },
        )
        list(OPS["return_to_hand"](ctx, {"objects": {"target": "a"}, "as": "back"}))
        list(OPS["return_to_hand"](ctx, {"objects": {"target": "b"}, "as": "back"}))

        assert ctx.bindings["back"] == [bears[0], bears[1]]

    def test_the_binding_is_written_before_the_moves(self, builder):
        """`op_exile`'s reason: the binding must record what this op returned,
        not whatever happens to be in a hand once it is done. Measured by
        putting a card in hand first and checking it is not counted."""
        game = position(builder)
        bears = oids_of(game, BEAR, 0)
        before = len(game.state.players[0].hand)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=None,
            targets={"t1": [TargetRef.obj(bears[0])]},
        )
        list(OPS["return_to_hand"](ctx, {"objects": {"target": "t1"}, "as": "returned"}))

        assert ctx.bindings["returned"] == [bears[0]]
        assert len(game.state.players[0].hand) == before + 1


class TestTheLoaderRefusals:
    def _card(self, **extra) -> CardModel:
        payload = {
            "id": "t_eagles_probe",
            "name": "Eagles Probe",
            "mana_cost": "{W}",
            "oracle_text": "Kicker {2}{W}{W}\nChoose target creature you own.",
            "types": ["Instant"],
            "kicker": "{2}{W}{W}",
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "count": 1,
                    "count_if_kicked": "any",
                    "selector": {"zone": "battlefield", "owner": "you", "types": ["Creature"]},
                }
            ],
            "spell_effects": [{"op": "return_to_hand", "objects": {"target": "t1"}}],
        }
        payload.update(extra)
        return CardModel.model_validate(payload)

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_no_kicker_is_refused(self):
        """A choice that can never be made. The clause would read as unkicked for
        ever and the card would silently be its small half."""
        with pytest.raises(DslError, match="no 'kicker'"):
            compile_card(self._card(kicker=None))


class TestTheResolutionAgreesWithTheDeclaration:
    """The half the first build missed, and the reason it is its own class.

    `kicked_targets` was substituted in `casting` only. `stack._resolve_spell`
    rebuilds the specs and hands them to `filter_legal`, which splits the stored
    refs into per-spec buckets by reading `TargetSpec.variable_size` -- false for
    the printed `count: 1`. So a kicked Eagles *stored* two refs and then
    *bucketed* one: the prompt looked right, two creatures were chosen, and one
    came back. The card silently shipped as its small half.

    Nothing in the classes above catches it. `TestTheKickedLineTargetsAnyNumber`
    measures legality, and `TestTheReturnBinding` builds its own EffectContext --
    neither goes anywhere near `filter_legal`. Bestow's own note in
    `_resolve_spell` makes the general point: declaration and resolution have to
    agree about what the specs are.
    """

    def test_filter_legal_buckets_every_kicked_ref(self, builder):
        from automtg.engine.targeting import filter_legal, kicked_targets

        game = position(builder)
        bears = oids_of(game, BEAR, 0)[:2]
        refs = tuple(TargetRef.obj(o) for o in bears)
        card = game.state.registry.get(EAGLES)

        kicked = kicked_targets(card.targets)
        assert kicked is not None
        buckets, _ = filter_legal(game.state, 0, kicked, refs, None)
        assert len(buckets["t1"]) == 2, buckets

    def test_the_printed_specs_bucket_only_one(self, builder):
        """The contrast that shows why the substitution has to happen at
        resolution too: unsubstituted, the second ref is orphaned."""
        from automtg.engine.targeting import filter_legal

        game = position(builder)
        bears = oids_of(game, BEAR, 0)[:2]
        refs = tuple(TargetRef.obj(o) for o in bears)
        card = game.state.registry.get(EAGLES)

        buckets, _ = filter_legal(game.state, 0, card.targets, refs, None)
        assert len(buckets["t1"]) == 1, buckets

    def test_a_kicked_cast_returns_every_chosen_creature(self, builder):
        """End to end, which is the claim that actually matters: cast it kicked
        with two creatures out and both come back."""
        from tests.conftest import _default_answer

        game = position(builder, creatures=2, lands=12)
        line = max(cast_lines(game, kicked=True), key=lambda a: len(a.targets))
        assert len([t for t in line.targets if t.kind == "object"]) == 2
        game.apply(line)
        for _ in range(60):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind.name == "PRIORITY" and not game.state.stack:
                break
            game.apply(_default_answer(game, decision))

        assert oids_of(game, BEAR, 0) == [], "both creatures left the battlefield"
        returned = [
            o for o in game.state.players[0].hand
            if game.state.objects[o].def_id == BEAR
        ]
        assert len(returned) == 2, "both are in hand"
