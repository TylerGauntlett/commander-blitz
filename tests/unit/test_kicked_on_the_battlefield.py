"""``{"kicked": true}`` read by a permanent's own enters trigger.

    Slinn Voda, the Rising Deep — "Kicker {1}{U}. When Slinn Voda enters, **if
    it was kicked**, return all creatures to their owners' hands except for
    Merfolk, Krakens, Leviathans, Octopuses, and Serpents."

The kicker cost and the `kicked` condition both already existed, and the card
still could not be written — because the flag lived only on the `StackItem`.
`stack._resolve_spell` passed `kicked=item.kicked` into the resolution context,
and by the time an *enters* trigger resolves the StackItem is gone and the
context is a trigger's own, with `kicked` False.

That is the worst shape a bug can have here. The card loads clean — the loader's
half-a-kicker guard is satisfied, because something *does* read `kicked` — and
then the kicked clause is silently unreachable. You pay {1}{U} extra and nothing
happens.

`cast_x` already had exactly this contract and solved it the same way: it is
written onto the object at resolution and survives onto the battlefield, so
"enters with X counters" can read it. `cast_kicked` is its sibling.

So the property under test is the *lifetime*, not the condition: the flag must
be readable after the object has stopped being a spell, and must be false again
when the same card is cast without the kicker.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind
from tests.conftest import only_oid

KICKED_LABEL = "(kicked)"


def board(builder, lands: int = 8):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * lands)
        .battlefield(1, ["grizzly_bears"])
        .hand(0, ["t_kicker_creature"])
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_it(game, *, kicked: bool):
    """Take the kicked or unkicked variant of the only castable spell."""
    options = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "t_kicker_creature"
    ]
    assert options, "the creature is not castable at all"
    wanted = [a for a in options if a.kicked is kicked]
    assert wanted, f"no {'kicked' if kicked else 'unkicked'} variant offered"
    game.apply(wanted[0])


def settle(game) -> None:
    for _ in range(60):
        if game.pending() is not None:
            choose = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind in (ActionKind.YES, ActionKind.CHOOSE)
                ),
                None,
            )
            if choose is None:
                return
            game.apply(choose)
            continue
        if not game.state.stack:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if action is None:
            return
        game.apply(action)


class TestTheFlagSurvivesResolution:
    def test_kicked_reaches_the_enters_trigger(self, builder):
        """The whole bug. Before this the trigger fired and its `if` was False."""
        game = board(builder)
        cast_it(game, kicked=True)
        settle(game)
        oid = only_oid(game, "t_kicker_creature")
        assert game.state.objects[oid].cast_kicked is True
        assert game.state.players[0].life == 45, (
            "the kicked clause did not run; `kicked` was unreadable on the permanent"
        )

    def test_unkicked_leaves_it_false(self, builder):
        """The pair. Without it, a flag that is always True passes the test above."""
        game = board(builder)
        cast_it(game, kicked=False)
        settle(game)
        oid = only_oid(game, "t_kicker_creature")
        assert game.state.objects[oid].cast_kicked is False
        assert game.state.players[0].life == 40, "the kicked clause ran unkicked"


class TestBothVariantsAreOffered:
    def test_legality_lists_the_cheap_line_and_the_kicked_one(self, builder):
        game = board(builder)
        options = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "t_kicker_creature"
        ]
        assert {a.kicked for a in options} == {False, True}
        assert options[0].kicked is False, "the cheap line should come first"

    def test_without_the_mana_only_the_cheap_line_is_offered(self, builder):
        game = board(builder, lands=4)
        options = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "t_kicker_creature"
        ]
        assert {a.kicked for a in options} == {False}
