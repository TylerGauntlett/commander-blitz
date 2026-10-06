""""Cloak the top card of your library." (701.61a)

    Unexplained Absence.

    "To cloak a card, put it onto the battlefield face down as a 2/2 creature
    with ward {2}. Turn it face up any time for its mana cost if it's a creature
    card."

Read against what the engine already had, that is **manifest plus ward {2}** and
nothing else. Manifest ships: the same 2/2 shell, and the same "turn it face up
for its printed mana cost if it's a creature card" — which is 701.34c, the rule
cloak restates verbatim. So `cloak` is a flag on `manifest`, not an op of its
own, and everything below the ward is inherited rather than rewritten.

**The ward is the whole of the difference, and it cannot come from the card.**
Rule 707.2 says a face-down permanent has no abilities, and the card underneath
a cloaked permanent is usually not even a creature. The cloak *rule* grants the
ward, so the engine carries it: `CLOAK_WARD` sits in `carddef` beside
`BESTOW_TARGET`, which is a rules-supplied target for the same reason.

Written as a plain manifest — the obvious shortcut, and one that loads, plays and
looks right — Unexplained Absence's cloaked permanents are free to remove, which
is most of what the keyword is worth.

Two places had to learn about it, and missing either is silent:

- `triggers._candidate_abilities` skips a face-down permanent's abilities
  wholesale. The ward is supplied in the same breath as that skip.
- `stack.ability_of` resolves an ability *by index* off the source's card. Index
  0 on a cloaked permanent would run whatever the hidden card prints first — a
  different ability on a different object, and nothing would say so.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import only_oid, pass_until

CLOAKER = "t_cloaker"  # "Cloak the top card of your library."
BEAR = "t_bear"
BOLT = "t_bolt"  # a targeted removal spell for the opponent to try


def board(builder, top: str = BEAR):
    return (
        builder(players=2)
        # Both colours: {1}{U} to cast the cloaker, {1}{G} to turn the
        # Bear underneath face up.
        .battlefield(0, ["island"] * 3 + ["forest"] * 3)
        .battlefield(1, ["mountain"] * 5)
        .hand(0, [CLOAKER])
        .hand(1, [BOLT])
        .library(0, [top] + ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_the_cloaker(game) -> int:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == CLOAKER
        )
    )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return next(
        o.oid
        for o in game.state.battlefield_objects(0)
        if o.face_down
    )


class TestTheShell:
    def test_it_arrives_face_down(self, builder):
        game = board(builder)
        shell = cast_the_cloaker(game)
        assert game.state.objects[shell].face_down
        assert game.state.objects[shell].cloaked

    def test_it_is_a_two_two_creature(self, builder):
        """707.2, inherited from manifest whole."""
        game = board(builder)
        shell = cast_the_cloaker(game)
        c = chars(game.state, shell)
        assert (c.power, c.toughness) == (2, 2)
        assert c.types == frozenset({"Creature"})

    def test_it_left_the_library(self, builder):
        """A token cannot stand in: the real card has to leave the library and
        stay underneath, so it can be turned face up later."""
        game = board(builder)
        before = len(game.state.players[0].library)
        shell = cast_the_cloaker(game)
        assert len(game.state.players[0].library) == before - 1
        assert game.state.objects[shell].def_id == BEAR


class TestTheWard:
    def targeted(self, game, shell: int) -> None:
        """The opponent points their removal at the shell."""
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST
                and g.state.objects[a.source].def_id == BOLT
                and any(ref.id == shell for ref in a.targets)
                for a in g.legal_actions()
            ),
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == BOLT
                and any(ref.id == shell for ref in a.targets)
            )
        )

    def test_targeting_it_asks_the_opponent_to_pay(self, builder):
        game = board(builder)
        shell = cast_the_cloaker(game)
        self.targeted(game, shell)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY
        )

        decision = game.pending()
        assert decision.kind is DecisionKind.MAY
        assert decision.player == 1, "the ward taxes the caster, not its controller"

    def test_a_plain_manifest_would_not(self, builder):
        """The witness that the flag is doing something. Same board, same spell,
        `cloaked` cleared by hand."""
        game = board(builder)
        shell = cast_the_cloaker(game)
        game.state.objects[shell].cloaked = False
        self.targeted(game, shell)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        assert game.state.objects[shell].zone is not Zone.BATTLEFIELD


class TestTurningItUp:
    def test_a_creature_card_may_be_turned_up_for_its_cost(self, builder):
        """701.61a's second sentence, which is 701.34c and already shipped."""
        game = board(builder)
        shell = cast_the_cloaker(game)
        assert any(
            a.kind is ActionKind.ACTIVATE and a.source == shell
            for a in game.legal_actions()
        )

    def test_a_land_card_may_not(self, builder):
        """"…if it's a creature card." A cloaked land is a 2/2 for ever."""
        game = board(builder, top="island")
        shell = cast_the_cloaker(game)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == shell
        ]

    def test_the_ward_goes_with_the_shell(self, builder):
        game = board(builder)
        shell = cast_the_cloaker(game)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == shell
            )
        )
        pass_until(game, lambda g: not g.state.objects[shell].face_down)

        assert not game.state.objects[shell].cloaked
        assert chars(game.state, shell).power == 2  # the Bear's own printed 2/2
        assert only_oid(game, BEAR, 0) == shell
