"""Snort — "each opponent **who discarded their hand this way**".

    Each player may discard their hand and draw five cards. Then Snort deals 5
    damage to each opponent who discarded their hand this way.

Nothing recorded which players accepted an optional action. `set_flag` and
`set_turn_flag` are object-scoped -- `op_set_flag` writes `obj.flags` on a
battlefield permanent and `has_flag` is always asked of `ctx.source_oid` -- so
neither can say anything about a *player*. `for_each_player` does bind
`each_player`, but the binding is overwritten each iteration and restored when
the loop ends, so nothing survives to be read afterwards.

So `may` grew an `as`, and it is the only recorder whose binding is a **set of
seats**. The `{"binding": …}` player spec reads it back.

**It records the acceptance, not what the effects moved**, and on this card that
is the whole difference. Deriving the set from the cards discarded looks
equivalent and is wrong for the player a wheel is aimed at: somebody with an
empty hand who takes the free draw-five *has* discarded their hand -- of nothing
-- and is still burned. `t_snort_by_cards` is that near-miss, and it spares them.

`except` is the other half. "Each **opponent** who did this" is an inclusive set
narrowed by a seat, and `not` could not say it: `not` is the complement over the
whole table, while the recorded set contains you whenever you took the same
option.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind

SNORT = "t_snort"
BY_CARDS = "t_snort_by_cards"


def board(builder, card_id: str, *, opponent_hand: int):
    return (
        builder(players=2)
        .hand(0, [card_id, "forest"])
        .hand(1, ["forest"] * opponent_hand)
        .battlefield(0, ["mountain"] * 4)
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )


def resolve(game, card_id: str, *, accept: bool = True):
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    for _ in range(60):
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        if decision.kind is DecisionKind.PRIORITY and not state.stack:
            break
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if accept else ActionKind.NO
            game.apply(next(a for a in actions if a.kind is want))
            continue
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        game.apply(choices[0] if choices else actions[0])
    return game


def life(game):
    return game.state.players[0].life, game.state.players[1].life


class TestTheAcceptanceIsRecorded:
    def test_an_opponent_who_accepts_is_burned(self, builder):
        game = resolve(board(builder, SNORT, opponent_hand=3), SNORT)
        assert life(game) == (40, 35)

    def test_nobody_is_burned_when_nobody_accepts(self, builder):
        game = resolve(board(builder, SNORT, opponent_hand=3), SNORT, accept=False)
        assert life(game) == (40, 40)


class TestTheEmptyHandedPlayerIsStillBurned:
    """The case the obvious implementation gets backwards.

    A wheel is aimed at the player who has run out of cards. They discard a hand
    of nothing, draw five, and are still an opponent who discarded their hand
    this way.
    """

    def test_accepting_with_no_cards_still_costs_five(self, builder):
        game = resolve(board(builder, SNORT, opponent_hand=0), SNORT)
        assert life(game) == (40, 35)

    def test_the_cards_based_near_miss_spares_them(self, builder):
        """Same card, set derived from the cards discarded instead."""
        game = resolve(board(builder, BY_CARDS, opponent_hand=0), BY_CARDS)
        assert life(game) == (40, 40)

    def test_the_near_miss_is_wrong_in_both_directions(self, builder):
        """It under-burns an empty hand and over-burns a full one.

        Looping the damage over the *cards* discarded fires once per card, so a
        three-card hand takes 5 five times over instead of once. A set of seats
        is not a bag of cards, and no amount of care with `owner_of` makes one
        into the other.
        """
        real = life(resolve(board(builder, SNORT, opponent_hand=3), SNORT))
        near = life(resolve(board(builder, BY_CARDS, opponent_hand=3), BY_CARDS))
        assert real == (40, 35)
        assert near[1] < real[1], "the near miss burns once per card, not once"


class TestExceptNarrowsTheSet:
    def test_the_caster_is_not_burned(self, builder):
        """"each **opponent**" -- you accepted too, and you take nothing."""
        game = resolve(board(builder, SNORT, opponent_hand=3), SNORT)
        assert game.state.players[0].life == 40


class TestTheLoaderKeepsItHonest:
    def test_except_needs_something_to_narrow(self):
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_except",
                "name": "Test Bad Except",
                "oracle_text": "Deal 1 damage.",
                "mana_cost": "{R}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "damage",
                        "amount": {"const": 1},
                        "player": {"except": "you"},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="narrows another spec"):
            compile_card(card, source="test")
