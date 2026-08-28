"""Discard, when the count is the player's and the cards are read back.

Three shipped cards needed this and none could be written without it:

- **Joshua, Phoenix's Dominant** — "Discard up to two cards, then draw that many
  cards."
- **Celes, Rune Knight** — "You may discard any number of cards, then draw that
  many cards plus one."
- **Mog, Moogle Warrior** — "…each player may discard a card. … If a **creature
  card** was discarded this way…"

`op_discard` read only `amount`, evaluated it to an integer, and called
`ask_objects(..., take, take, ...)` with the same number as both floor and
ceiling. So the count was always exact — "up to two" could not be satisfied with
one, and "any number" could not be satisfied with none — and the op wrote no
binding, so nothing downstream could name what had left.

Two additions, one op: `up_to` turns `amount` into a ceiling with a floor of
zero, and `as` records what actually went, the way `exile`, `sacrifice` and
`reveal` already do.

Every near-miss for the read-back is wrong in a way nobody would catch on the
board, which is why this is engine work rather than a clever card:
`cards_to_graveyard_this_turn` is one turn-wide integer over every graveyard at
the table, counting deaths and mills and earlier discards; counting your own
graveyard counts what was already sitting in it — two creature cards in the
authoring sandbox alone, so Mog's creature branch would fire unconditionally.

`t_exact_pitch` is the counterfactual: the same `as`, no `up_to`, so the floor
stays where it was.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind

UP_TO = "t_pitch_and_draw"
ANY_NUMBER = "t_pitch_plus_one"
EXACT = "t_exact_pitch"


def board(builder, card_id: str, *, hand: int = 3):
    return (
        builder(players=2)
        .hand(0, [card_id, *["forest"] * hand])
        .battlefield(0, ["island"] * 4)
        .library(0, ["mountain"] * 20)
        .build()
    )


def cast(game, card_id: str):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    return game


def answer_discard(game, *, take: int):
    """Pick ``take`` cards at the discard prompt, then finish."""
    for _ in range(50):
        decision = game.pending()
        if decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS:
            return game
        actions = game.legal_actions()
        if take > 0:
            choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
            if choose is not None:
                take -= 1
                game.apply(choose)
                continue
        done = next(
            (a for a in actions if a.kind is ActionKind.FINISH_DECLARATION), None
        )
        if done is None:
            return game
        game.apply(done)
        return game
    return game


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


class TestTheFloorDrops:
    """"Up to two" has to be satisfiable with none."""

    def test_declining_entirely_is_offered(self, builder):
        game = cast(board(builder, UP_TO), UP_TO)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        ), "'discard up to two' must let the player discard none"

    def test_an_exact_discard_does_not_offer_it(self, builder):
        """The counterfactual, and the reason `up_to` is opt-in.

        A cost or effect that says "discard two cards" must not become a
        suggestion; without this half the change would quietly weaken every
        discard in the pool.
        """
        game = cast(board(builder, EXACT), EXACT)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert not any(
            a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
        )


class TestTheBindingIsRead:
    """"…then draw that many cards" -- the count comes back out."""

    def test_discarding_two_draws_two(self, builder):
        game = board(builder, UP_TO)
        before = hand_size(game)
        cast(game, UP_TO)
        answer_discard(game, take=2)
        # -1 the spell, -2 discarded, +2 drawn
        assert hand_size(game) == before - 3 + 2

    def test_discarding_none_draws_none(self, builder):
        """The whole point of the binding: it is a count, not a constant."""
        game = board(builder, UP_TO)
        before = hand_size(game)
        cast(game, UP_TO)
        answer_discard(game, take=0)
        assert hand_size(game) == before - 1

    def test_the_two_cases_differ_where_they_can(self, builder):
        """Measured on the library and graveyard, not the hand.

        "Discard N, then draw N" leaves the hand size *invariant* -- both paths
        above end on three cards -- so a test comparing hands would compare two
        numbers that are equal for a correct card and equal for a broken one.
        The cards themselves moved, though, and that is visible: two left for
        the graveyard and two came off the library, or neither did.
        """
        a = board(builder, UP_TO)
        cast(a, UP_TO)
        answer_discard(a, take=2)

        b = board(builder, UP_TO)
        cast(b, UP_TO)
        answer_discard(b, take=0)

        assert len(a.state.players[0].library) == len(b.state.players[0].library) - 2
        assert len(a.state.players[0].graveyard) == len(b.state.players[0].graveyard) + 2


class TestArithmeticOnTheBinding:
    """Celes: "draw that many cards **plus one**"."""

    def test_discarding_one_draws_two(self, builder):
        game = board(builder, ANY_NUMBER)
        before = hand_size(game)
        cast(game, ANY_NUMBER)
        answer_discard(game, take=1)
        # -1 the spell, -1 discarded, +2 drawn
        assert hand_size(game) == before - 2 + 2

    def test_discarding_none_still_draws_one(self, builder):
        game = board(builder, ANY_NUMBER)
        before = hand_size(game)
        cast(game, ANY_NUMBER)
        answer_discard(game, take=0)
        assert hand_size(game) == before - 1 + 1


class TestTheLoaderKeepsItHonest:
    def test_an_as_on_discard_is_now_allowed(self, registry):
        assert registry.get(EXACT) is not None

    def test_random_and_up_to_together_are_refused(self):
        """Nobody is choosing, so there is no floor to relax."""
        import pytest

        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        card = CardModel.model_validate(
            {
                "id": "t_bad_random_up_to",
                "name": "Test Bad Random Up To",
                "oracle_text": "Discard up to two cards at random.",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "discard",
                        "player": "you",
                        "amount": {"const": 2},
                        "random": True,
                        "up_to": True,
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="random"):
            compile_card(card, source="test")
