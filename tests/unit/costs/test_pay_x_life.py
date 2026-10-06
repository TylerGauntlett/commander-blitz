"""Toxic Deluge — "As an additional cost to cast this spell, pay X life."

Rule 601.2b: the caster announces the value of X as the spell is cast. The
engine could already do that for a `{X}` in a **mana** cost, and nowhere else:
`_ask_x` returns 0 immediately unless `cost.mana.x_count` is nonzero, and Toxic
Deluge's mana cost is `{2}{B}`. So `{"x": true}` evaluated to 0 and the sweep
resolved as -0/-0 — a card that loads, casts, resolves and does nothing, which
is the exact failure the authoring pipeline exists to prevent.

Every existing shape was wrong in a way that survives a casual reading:

- `pay_life` is a literal, or a value expression the *board* decides (War
  Room's count of commander colours). This number is the player's.
- `x_value` **defines** X rather than asking for it, and the loader refuses it
  outside an activated ability with a literal `{X}` in its own mana.
- `additional_repeatable` with `pay_life: 1` produces the same set of outcomes
  and is still a different card: it caps at `legality.MAX_ADDITIONAL_TIMES`
  (six, where Toxic Deluge is often cast for more), it turns one payment of X
  life into X payments of one — visible to anything watching life payments —
  and it describes an optional cost paid a number of times rather than one
  mandatory announced number.

So `pay_life_x` is a flag on the cost, asked with the general `ask_x` helper at
the same moment the mana X would be, and the answer is carried onto the stack
item as the spell's `x`. 118.4 sets the ceiling: a player may pay life down to
exactly 0, so the whole life total is on offer.

`t_fixed_deluge` is the counterfactual — a fixed 3 life for a fixed -3/-3 — the
best the DSL could say before, and a card you cannot aim.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind

DELUGE = "t_toxic_deluge"
FIXED = "t_fixed_deluge"
BEAR = "t_bear"


def board(builder, card_id: str, *, life: int = 40):
    return (
        builder(players=2)
        .hand(0, [card_id, "forest"])
        .battlefield(0, ["swamp"] * 4)
        .battlefield(0, [BEAR])
        .battlefield(1, [BEAR])
        .life(0, life)
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_for(game, card_id: str, x: int | None):
    """Cast the card, answering the X prompt with ``x`` if one appears."""
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(20):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        if decision.kind is DecisionKind.CHOOSE_X:
            assert x is not None, "this card should not have asked for an X"
            game.apply(next(a for a in actions if getattr(a, "choice", None) == x))
            continue
        if decision.kind is DecisionKind.PRIORITY and not state.stack:
            break
        game.apply(actions[0])
    return game


def bear_toughnesses(game):
    state = game.state
    return [
        chars(state, o.oid).toughness
        for pid in (0, 1)
        for o in state.battlefield_objects(pid)
        if state.card_of(o).id == BEAR
    ]


class TestTheCasterAnnouncesIt:
    def test_the_spell_asks_for_an_x(self, builder):
        game = board(builder, DELUGE)
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and state.objects[a.source].def_id == DELUGE
        )
        game.apply(action)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_X

    def test_a_fixed_cost_does_not(self, builder):
        """The counterfactual: nothing to announce, so nothing is asked."""
        game = cast_for(board(builder, FIXED), FIXED, None)
        assert game.state.players[0].life == 37


class TestTheLifeIsActuallyPaid:
    def test_x_of_two_costs_two_life(self, builder):
        game = cast_for(board(builder, DELUGE), DELUGE, 2)
        assert game.state.players[0].life == 38

    def test_x_of_zero_costs_nothing(self, builder):
        game = cast_for(board(builder, DELUGE), DELUGE, 0)
        assert game.state.players[0].life == 40


class TestTheEffectIsSizedByIt:
    """The half that silently read 0 before, and the reason this is engine work."""

    def test_x_of_two_wipes_the_two_two_creatures(self, builder):
        game = cast_for(board(builder, DELUGE), DELUGE, 2)
        assert bear_toughnesses(game) == [], "-2/-2 kills a 2/2 on both sides"

    def test_x_of_zero_kills_nothing(self, builder):
        game = cast_for(board(builder, DELUGE), DELUGE, 0)
        assert bear_toughnesses(game) == [2, 2]

    def test_x_of_one_only_shrinks_them(self, builder):
        """The boundary: -1/-1 is not lethal to a 2/2."""
        game = cast_for(board(builder, DELUGE), DELUGE, 1)
        assert bear_toughnesses(game) == [1, 1]
        assert game.state.players[0].life == 39


class TestTheCeiling:
    def test_you_may_pay_down_to_exactly_zero(self, builder):
        """118.4. Losing is a state-based action afterwards, not an illegal cost."""
        game = board(builder, DELUGE, life=3)
        state = game.state
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and state.objects[a.source].def_id == DELUGE
        )
        game.apply(action)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_X
        assert max(o.value for o in decision.options) == 3


class TestTheLoaderKeepsItHonest:
    def test_an_announced_x_and_a_fixed_amount_are_refused(self):
        """Two numbers for one payment; one of them would never be charged."""
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_x_life",
                "name": "Test Bad X Life",
                "oracle_text": "Draw a card.",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "additional_cost": {"pay_life_x": True, "pay_life": 3},
                "spell_effects": [{"op": "draw", "player": "you"}],
            }
        )
        with pytest.raises(DslError, match="pay_life_x"):
            compile_card(card, source="test")
