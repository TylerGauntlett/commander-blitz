"""Epic — a restriction that outlives every object it could sit on.

    "Epic (For the rest of the game, you can't cast spells. At the beginning of
    each of your upkeeps, copy this spell except for its epic ability.)"

Two halves, and both are about *where the state lives*. The epic card is in a
graveyard a moment after it resolves, so neither half can be written on it:

- **The restriction is on the player**, one-way and for the rest of the game,
  which is `has_city_s_blessing`'s shape. It is enforced in `_cast_actions`
  rather than as a cost or a condition, because it is not about any one card —
  and lands are unaffected, which is why it sits there and not in
  `legal_actions`.
- **The copy is a rule, not an ability**, for suspend's ticking reason: the card
  has no abilities where it is, and "at the beginning of each of your upkeeps"
  belongs to the game the way the untap step does.

"Except for its epic ability" is one condition, and the test below is the only
thing that would ever have found it: a copy of a spell is a **token** and it
resolves through the same function the original did, so without `not
obj.is_token` each upkeep's copy re-points `epic_source` at itself — and the
copy is removed by a state-based action a moment later, which silently ends the
copying after exactly one turn. The board shows a card that worked once.

The copy is built through the same `put_copy_on_stack` that `copy_spell` uses,
so the two cannot drift on the things that are easy to get wrong: a copy is a
token object, and it announces its targets so ward and heroic see it.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from tests.conftest import _default_answer, action_for_card, pass_until

PLAINS = "plains"
EPIC = "t_epic"       # {1}{W} sorcery, gain 2 life, epic
BEAR = "t_bear"


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 5)
        .hand(0, [EPIC, BEAR])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def cast_the_epic(game):
    pass_until(
        game,
        lambda g: any(
            a.kind is ActionKind.CAST
            and g.state.objects[a.source].def_id == EPIC
            for a in g.legal_actions()
        ),
    )
    game.apply(action_for_card(game, ActionKind.CAST, EPIC))
    pass_until(game, lambda g: not g.state.stack)


def to_turn(game, turn: int):
    for _ in range(900):
        if game.state.turn >= turn and game.state.step is Step.PRECOMBAT_MAIN:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))


class TestTheRestriction:
    def test_it_resolves_normally_the_first_time(self, builder):
        game = position(builder)
        life = game.state.players[0].life
        cast_the_epic(game)
        assert game.state.players[0].life == life + 2

    def test_no_spell_can_be_cast_afterwards(self, builder):
        game = position(builder)
        cast_the_epic(game)
        to_turn(game, 3)

        assert not [a for a in game.legal_actions() if a.kind is ActionKind.CAST]

    def test_lands_are_unaffected(self, builder):
        """"casting no **spells**" -- playing a land is not casting."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 5)
            .hand(0, [EPIC, PLAINS])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        cast_the_epic(game)
        to_turn(game, 3)

        assert [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]

    def test_the_opponent_may_still_cast(self, builder):
        """It is a fact about one *player*, not a rule change for the table."""
        game = position(builder)
        cast_the_epic(game)

        assert game.state.players[0].epic_source is not None
        assert game.state.players[1].epic_source is None


class TestTheCopies:
    def test_each_of_your_upkeeps_copies_it(self, builder):
        game = position(builder)
        cast_the_epic(game)
        life = game.state.players[0].life

        to_turn(game, 3)

        assert game.state.players[0].life == life + 2, "one copy, one upkeep"

    def test_it_keeps_copying(self, builder):
        game = position(builder)
        cast_the_epic(game)
        life = game.state.players[0].life

        to_turn(game, 7)

        assert game.state.players[0].life == life + 6, "turns 3, 5 and 7"

    def test_the_copy_does_not_re_arm_the_restriction(self, builder):
        """The one condition, and the only thing that would have found it."""
        game = position(builder)
        cast_the_epic(game)
        first = game.state.players[0].epic_source
        to_turn(game, 5)

        assert game.state.players[0].epic_source == first

    def test_the_copies_are_tokens(self, builder):
        """A copy is not a card, so nothing accumulates in the graveyard."""
        game = position(builder)
        cast_the_epic(game)
        to_turn(game, 5)

        graveyard = [game.state.objects[o] for o in game.state.players[0].graveyard]
        assert [o.def_id for o in graveyard].count(EPIC) == 1, "the card, and no copies"
