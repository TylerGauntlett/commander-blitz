""""Return target **spell or nonland permanent** an opponent controls to its
owner's hand."

Sink into Stupor. One instance of the word "target" whose legal choices live in
two zones at once, which no `TargetModel.kind` could say: `"spell"` walks the
stack, `"permanent"` and `"any"` walk the battlefield, and none of them pools the
two.

**One spec, not two.** Two specs -- one of each kind -- is a card that targets
*twice*: it would need a legal choice of each to be castable at all, and 608.2b
would fizzle it if either became illegal. The printed card is castable with only
a permanent on the board and only a spell on the stack alike, which is what
`TestEitherHalfAlone` asserts.

`still_legal` needed no change whatever, and that is the design working rather
than a lucky escape: it already re-checks a stored ref by `ref.kind` rather than
by the spec's, so a ref this branch offers is one it will accept. The same is
true of the selector -- `not_types` and `controller` are applied to both halves,
because the printed clause ("nonland", "an opponent controls") is meant to narrow
both.

What did need saying is where the chosen thing goes. `return_spell_to_hand` read
only `ctx.target_sids`, so a union target that landed on a permanent returned
nothing and left it on the battlefield with the card looking like it worked --
which is the exact silent failure that op's own docstring was written about, one
kind further along.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

SINK = "t_sink"
BEAR = "t_bear"  # a nonland permanent for seat 1
BAIT = "t_plain_instant"  # {W} instant for seat 1 to cast


def position(builder, *, their_board=(), their_hand=()):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4)
        .battlefield(1, [*their_board, "plains", "plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [SINK])
        .hand(1, list(their_hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def sink_targets(game):
    """Every target Sink into Stupor is currently offered."""
    return [
        a.targets[0]
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == SINK
        and a.targets
    ]


def settle(game):
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestEitherHalfAlone:
    def test_a_permanent_with_nothing_on_the_stack(self, builder):
        game = position(builder, their_board=[BEAR])
        game._advance()

        refs = sink_targets(game)
        assert refs, "castable at a permanent alone"
        assert all(r.kind == "object" for r in refs)

    def test_a_spell_with_no_permanent(self, builder):
        """Seat 1 casts the bait; seat 0 answers it on the stack."""
        game = position(builder, their_hand=[BAIT])
        game._advance()
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == BAIT
                for a in g.legal_actions()
            ),
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BAIT
            )
        )
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == SINK
                for a in g.legal_actions()
            ),
        )

        refs = sink_targets(game)
        assert refs, "castable at a spell alone"
        assert all(r.kind == "stack" for r in refs)


class TestBothAtOnce:
    def test_the_pool_is_the_two_halves_together(self, builder):
        """One spec, one pool -- and the caster picks which half."""
        game = position(builder, their_board=[BEAR], their_hand=[BAIT])
        game._advance()
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == BAIT
                for a in g.legal_actions()
            ),
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BAIT
            )
        )
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == SINK
                for a in g.legal_actions()
            ),
        )

        kinds = {r.kind for r in sink_targets(game)}
        assert kinds == {"object", "stack"}


class TestTheSelectorNarrowsBothHalves:
    def test_your_own_permanent_is_not_offered(self, builder):
        """"an **opponent** controls" -- and seat 0's own board is seat 0's."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, "island", "island", "island", "island"])
            .battlefield(1, ["plains"])
            .library(0, ["forest"] * 20)
            .hand(0, [SINK])
            .hand(1, [BAIT])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()

        mine = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        assert mine, "the premise: seat 0 has one"
        assert not [r for r in sink_targets(game) if r.id in mine]

    def test_a_land_is_not_offered(self, builder):
        """"**nonland** permanent" -- their Plains are on the battlefield."""
        game = position(builder, their_board=[BEAR])
        game._advance()

        lands = [o.oid for o in game.state.battlefield_objects(1) if o.def_id == "plains"]
        assert lands, "the premise"
        assert not [r for r in sink_targets(game) if r.id in lands]


class TestItActuallyBouncesEitherOne:
    def test_a_permanent_goes_to_its_owners_hand(self, builder):
        """The half `return_spell_to_hand` could not reach.

        Reading only `ctx.target_sids` returns nothing here and leaves the
        permanent on the battlefield with the card looking like it worked.
        """
        game = position(builder, their_board=[BEAR])
        game._advance()
        bear = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SINK
            and a.targets
            and a.targets[0].id == bear
        )
        game.apply(action)
        settle(game)

        assert game.state.objects[bear].zone is Zone.HAND
        assert bear in game.state.players[1].hand, "its **owner's** hand"

    def test_a_spell_goes_to_its_owners_hand(self, builder):
        game = position(builder, their_hand=[BAIT])
        game._advance()
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == BAIT
                for a in g.legal_actions()
            ),
        )
        bait = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BAIT
        )
        bait_oid = bait.source
        game.apply(bait)
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == SINK
                for a in g.legal_actions()
            ),
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SINK
            )
        )
        settle(game)

        assert bait_oid in game.state.players[1].hand
