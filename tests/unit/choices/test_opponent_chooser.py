"""Rejoin the Fight — "each **opponent** chooses a creature card in your graveyard".

    Mill three cards. Then starting with the next opponent in turn order, each
    opponent chooses a creature card in your graveyard that hasn't been chosen.
    Return each card chosen this way to the battlefield under your control.

The gap record named three things. Two of them had been built by the time this
card came back round, which is the whole reason it is one small change:

- **cumulative exclusion** -- "a creature card that **hasn't been chosen**".
  `choose_permanents`'s binding accumulates, so `exclude_binding` on the same
  name grows with every pick instead of only remembering the last one.
- **the deferred batch** -- "Return **each** card chosen this way". The choices
  happen inside the loop and the single `return_from_graveyard` happens after
  it, so the creatures arrive together rather than one per iteration.

What was genuinely missing is **who is asked**. `chooser` was validated to
exactly `controller`, `owner` or `none`, and for a pool of
`{"zone": "graveyard", "controller": "you"}` both names resolve to the spell's
controller -- so the caster picked the cards their opponents are supposed to,
which is the entire card. It now accepts an ordinary player spec, resolved
through `select_players`, so `{"binding": "each_player"}` inside a
`for_each_player` loop asks the seat the loop is on.

A spec naming nobody chooses nothing rather than quietly falling back to the
controller, which is the same safe direction the rest of the selector language
takes.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, DecisionKind

REJOIN = "t_rejoin"


def board(builder, *, players: int = 3, buried=("t_bear", "t_dork", "acidic_slime")):
    return (
        builder(players=players)
        .hand(0, [REJOIN, "forest"])
        .battlefield(0, ["plains"] * 4)
        .graveyard(0, list(buried))
        .library(0, ["forest"] * 10)
        .build()
    )


def resolve(game):
    """Cast it, answering every choice with the first option, and note who was asked."""
    state = game.state
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
    game.apply(action)
    asked: list[int] = []
    for _ in range(30):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            asked.append(decision.player)
            choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
            game.apply(choices[0] if choices else actions[0])
            continue
        if decision.kind is DecisionKind.PRIORITY and not state.stack:
            break
        game.apply(actions[0])
    return asked


def creatures(game, pid: int = 0):
    state = game.state
    return sorted(
        state.card_of(o).id
        for o in state.battlefield_objects(pid)
        if state.card_of(o).is_creature
    )


class TestWhoIsAsked:
    """The claim the change exists for."""

    def test_every_opponent_chooses(self, builder):
        game = board(builder)
        assert resolve(game) == [1, 2]

    def test_the_caster_is_not_asked(self, builder):
        """Both old chooser names resolved here, which is the bug."""
        game = board(builder)
        assert 0 not in resolve(game)


class TestTheChoicesAccumulate:
    def test_they_pick_different_cards(self, builder):
        """"…that **hasn't been chosen**" -- the exclusion grows per pick."""
        game = board(builder)
        resolve(game)
        assert creatures(game) == ["t_bear", "t_dork"]

    def test_the_unchosen_card_stays_buried(self, builder):
        game = board(builder)
        resolve(game)
        state = game.state
        left = sorted(state.card_of(state.objects[o]).id for o in state.players[0].graveyard)
        assert "acidic_slime" in left

    def test_one_opponent_returns_one_card(self, builder):
        """Two seats, one choice: the loop and the batch both scale down."""
        game = board(builder, players=2)
        assert resolve(game) == [1]
        assert len(creatures(game)) == 1


class TestTheLoaderValidatesIt:
    def test_a_player_spec_is_accepted(self):
        from commanderblitz.engine.effects.selectors import validate_selector

        validate_selector({"zone": "graveyard", "chooser": "opponent"}, "test")
        validate_selector(
            {"zone": "graveyard", "chooser": {"binding": "each_player"}}, "test"
        )

    def test_a_typo_is_still_refused(self):
        """The whole reason the three names were a closed set."""
        from commanderblitz.engine.effects.selectors import validate_selector
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="unknown chooser"):
            validate_selector({"zone": "graveyard", "chooser": "each_oponent"}, "test")
