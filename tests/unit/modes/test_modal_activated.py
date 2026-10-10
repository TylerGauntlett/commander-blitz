"""Phoenix Down — a modal **activated** ability whose bullets own their targets.

    {1}{W}, {T}, Exile this artifact: Choose one —
    • Return target creature card with mana value 4 or less from your graveyard
      to the battlefield tapped.
    • Exile target Skeleton, Spirit, or Zombie.

`mode` on a target spec already existed and `loader._check_mode_targets`
explicitly refused it here, with a good reason: 601.2b chooses the mode and
601.2c declares that mode's targets straight after, and an activated ability had
no moment that owned both questions. `legality` enumerated one activation per
legal target tuple, so the targets were fixed before `Game._activate` asked
which bullet — the reverse of the printed order.

Putting both bullets' targets on the ability unconditionally is not the same
card, which is why this is engine work: it would demand a legal creature card in
the graveyard **and** a legal Skeleton/Spirit/Zombie before the ability could be
activated at all, so an empty graveyard would switch off the removal bullet too.

So `_ability_aims` offers one activation **per mode**, each carrying only the
targets that mode owns, and the bullet rides on the action the way `kicked`
rides on a cast. A bullet with no legal target is simply not offered, which is
601.2b's other half — a mode that cannot be chosen is not among the choices —
and `Game._activate` reads the mode off the action instead of asking a question
the player has already answered.

The fixture puts the two bullets' targets in **different zones** so the board
can make one legal and the other not, which is the whole experiment.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Zone

CARD = "t_modal_down"
BEAR = "t_bear"


def board(builder, *, graveyard: bool, opponent: bool):
    b = (
        builder(players=2)
        .battlefield(0, [CARD])
        .battlefield(0, ["plains"] * 2)
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
    )
    if graveyard:
        b = b.graveyard(0, [BEAR])
    if opponent:
        b = b.battlefield(1, [BEAR])
    game = b.build()
    state = game.state
    oid = next(
        o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == CARD
    )
    return game, oid


def offered(game, oid: int):
    return sorted(
        a.ability_modes
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    )


class TestEachBulletIsOfferedOnItsOwnTerms:
    def test_both_when_both_are_legal(self, builder):
        game, oid = board(builder, graveyard=True, opponent=True)
        assert offered(game, oid) == [(0,), (1,)]

    def test_only_the_reanimation_with_an_empty_board(self, builder):
        game, oid = board(builder, graveyard=True, opponent=False)
        assert offered(game, oid) == [(0,)]

    def test_only_the_removal_with_an_empty_graveyard(self, builder):
        """The case that makes the flat reading wrong.

        With both bullets' targets on the ability unconditionally, an empty
        graveyard would take the removal bullet away too.
        """
        game, oid = board(builder, graveyard=False, opponent=True)
        assert offered(game, oid) == [(1,)]

    def test_neither_when_nothing_can_be_aimed_at(self, builder):
        game, oid = board(builder, graveyard=False, opponent=False)
        assert offered(game, oid) == []


class TestTheChosenBulletIsWhatHappens:
    def activate(self, game, oid: int, mode: int):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and a.ability_modes == (mode,)
        )
        game.apply(action)
        state = game.state
        for _ in range(20):
            if not state.stack:
                break
            actions = game.legal_actions()
            if not actions:
                break
            game.apply(actions[0])
        return game

    def test_the_first_bullet_returns_the_card(self, builder):
        game, oid = board(builder, graveyard=True, opponent=True)
        buried = game.state.players[0].graveyard[0]
        self.activate(game, oid, 0)
        assert game.state.objects[buried].zone is Zone.HAND

    def test_the_second_bullet_exiles_the_creature(self, builder):
        game, oid = board(builder, graveyard=True, opponent=True)
        theirs = next(o.oid for o in game.state.battlefield_objects(1))
        self.activate(game, oid, 1)
        assert game.state.objects[theirs].zone is Zone.EXILE

    def test_the_first_bullet_leaves_their_creature_alone(self, builder):
        """The bullets are exclusive -- taking one does not run the other."""
        game, oid = board(builder, graveyard=True, opponent=True)
        theirs = next(o.oid for o in game.state.battlefield_objects(1))
        self.activate(game, oid, 0)
        assert game.state.objects[theirs].zone is Zone.BATTLEFIELD

    def test_the_second_bullet_leaves_the_graveyard_alone(self, builder):
        game, oid = board(builder, graveyard=True, opponent=True)
        buried = game.state.players[0].graveyard[0]
        self.activate(game, oid, 1)
        assert game.state.objects[buried].zone is Zone.GRAVEYARD


class TestTheModeIsNotAskedTwice:
    def test_activating_asks_no_mode_question(self, builder):
        """It was answered when the action was chosen.

        Asking again would put a question the player has already answered, and
        an answer that disagreed with the targets already declared would be
        unresolvable.
        """
        from commanderblitz.engine.enums import DecisionKind

        game, oid = board(builder, graveyard=True, opponent=True)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and a.ability_modes == (1,)
        )
        game.apply(action)
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.CHOOSE_MODE
