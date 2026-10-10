"""A cap on a player's draws: "Each opponent can't draw more than one card each turn."

Narset, Parter of Veils is the witness; Spirit of the Labyrinth prints the same
sentence for every player. One static, `draw_limit`, with the cap in `amount`.

The rules argument, and what goes wrong without each half:

- **A "can't", not a replacement (101.2).** A draw past the cap does not happen.
  It is not replaced by nothing -- which is why it is asked in
  `replacements._draw_one` *before* dredge, the empty-library win and the
  doublers: an event that cannot happen cannot be replaced either. A dredger
  whose second draw is refused is not offered dredge; a Laboratory Maniac with
  an empty library does not win on a draw that could not occur; and a draw
  doubled by Thought Reflection yields the one card the cap still allows.
- **Each turn, not since the static arrived.** The count is the turn's
  `cards_drawn_this_turn` ledger, so a card drawn before Narset entered still
  uses up the opponent's one (the printed ruling). A version that counted from
  its own arrival would let the opponent draw again.
- **Nothing is attempted.** A refused draw from an empty library is not the
  104.3c attempt, so it sets no "will lose" flag.
- **The turn-based draw is a draw like any other.** An opponent who drew in
  their upkeep skips the card of their draw step.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import draw_cap
from commanderblitz.engine.replacements import draw as draw_with_replacements
from commanderblitz.engine.turn import _draw_step
from commanderblitz.engine.zones import move_object

NARSET = "t_narset_limit"  # Each opponent can't draw more than one card each turn.
LABYRINTH = "t_labyrinth_limit"  # Each player can't draw more than one card each turn.
DOUBLER = "t_draw_doubler"  # If you would draw a card, draw two cards instead.
DREDGER = "t_dredger"  # dredge 3
MANIAC = "t_lab_maniac"  # If you would draw from an empty library, you win instead.


def position(
    builder,
    mine: tuple[str, ...] = (),
    theirs: tuple[str, ...] = (),
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    active: int = 0,
    library: int = 20,
    their_graveyard: tuple[str, ...] = (),
):
    """Player 0 holds ``mine``, player 1 ``theirs``; nobody has drawn this turn."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .graveyard(1, list(their_graveyard))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * library)
        .step(step)
        .turn(3)
        .build(advance=False)
    )
    game.state.active_idx = active
    game.state.cards_drawn_this_turn.clear()
    return game


def drive(gen) -> tuple[int, list]:
    """Run a draw generator, declining every question; return (result, questions)."""
    asked = []
    send = None
    while True:
        try:
            asked.append(gen.send(send))
        except StopIteration as stop:
            return stop.value, asked
        send = []


def draws(game, pid: int, count: int = 1) -> int:
    before = len(game.state.players[pid].hand)
    drive(draw_with_replacements(game.state, pid, count))
    return len(game.state.players[pid].hand) - before


class TestTheCap:
    def test_the_first_draw_happens(self, builder):
        game = position(builder, (NARSET,))
        assert draws(game, 1) == 1

    def test_the_second_does_not(self, builder):
        game = position(builder, (NARSET,))
        draws(game, 1)
        assert draws(game, 1) == 0
        assert len(game.state.players[1].library) == 19

    def test_draw_three_is_one(self, builder):
        game = position(builder, (NARSET,))
        assert draws(game, 1, 3) == 1

    def test_its_controller_draws_freely(self, builder):
        """"Each **opponent**" -- Narset's controller is not capped."""
        game = position(builder, (NARSET,))
        assert draw_cap(game.state, 0) is None
        assert draws(game, 0, 3) == 3

    def test_each_player_names_the_controller_too(self, builder):
        game = position(builder, (LABYRINTH,))
        assert draws(game, 0, 3) == 1
        assert draws(game, 1, 3) == 1

    def test_no_cap_without_the_static(self, builder):
        game = position(builder)
        assert draw_cap(game.state, 1) is None
        assert draws(game, 1, 3) == 3


class TestEachTurn:
    def test_a_card_drawn_before_narset_arrived_counts(self, builder):
        game = position(builder, (NARSET,))
        narset = next(o for o in game.state.battlefield if game.state.objects[o].def_id == NARSET)
        move_object(game.state, narset, Zone.HAND, to_player=0)
        assert draws(game, 1) == 1
        # Narset arrives after the opponent's first draw of the turn.
        move_object(game.state, narset, Zone.BATTLEFIELD, to_player=0)
        assert draws(game, 1) == 0

    def test_a_new_turn_allows_one_more(self, builder):
        game = position(builder, (NARSET,))
        draws(game, 1)
        game.state.cards_drawn_this_turn.clear()  # what the turn start does
        assert draws(game, 1) == 1

    def test_an_upkeep_draw_uses_up_the_draw_step(self, builder):
        game = position(builder, (NARSET,), step=Step.UPKEEP, active=1)
        draws(game, 1)
        game.state.step = Step.DRAW
        before = len(game.state.players[1].hand)
        drive(_draw_step(game.state))
        assert len(game.state.players[1].hand) == before

    def test_the_draw_step_card_is_the_one(self, builder):
        game = position(builder, (NARSET,), step=Step.UPKEEP, active=1)
        game.state.step = Step.DRAW
        drive(_draw_step(game.state))
        assert draws(game, 1) == 0
        assert len(game.state.players[1].hand) == 1


class TestNothingReplacesARefusedDraw:
    def test_a_doubled_draw_yields_the_one_card(self, builder):
        game = position(builder, (NARSET,), (DOUBLER,))
        assert draws(game, 1) == 1

    def test_dredge_is_not_offered_past_the_cap(self, builder):
        game = position(builder, (NARSET,), their_graveyard=(DREDGER,))
        draws(game, 1)
        _, asked = drive(draw_with_replacements(game.state, 1, 1))
        assert asked == []
        assert game.state.players[1].graveyard, "the dredger stays put"

    def test_dredge_is_still_offered_under_the_cap(self, builder):
        """The pair: the first draw of the turn is a draw, and replaceable."""
        game = position(builder, (NARSET,), their_graveyard=(DREDGER,))
        _, asked = drive(draw_with_replacements(game.state, 1, 1))
        assert asked

    def test_an_empty_library_does_not_win_past_the_cap(self, builder):
        game = position(builder, (NARSET,), (MANIAC,), library=0)
        game.state.cards_drawn_this_turn[1] = 1
        drive(draw_with_replacements(game.state, 1, 1))
        assert not game.over

    def test_a_refused_draw_is_not_an_attempt(self, builder):
        """104.3c is an attempt to draw; a draw that cannot happen is not one."""
        game = position(builder, (NARSET,), library=0)
        game.state.cards_drawn_this_turn[1] = 1
        drive(draw_with_replacements(game.state, 1, 1))
        assert not game.state.players[1].attempted_draw_from_empty


class TestItFollowsItsSource:
    def test_it_lifts_when_narset_leaves(self, builder):
        game = position(builder, (NARSET,))
        draws(game, 1)
        narset = next(o for o in game.state.battlefield if game.state.objects[o].def_id == NARSET)
        move_object(game.state, narset, Zone.GRAVEYARD)
        assert draws(game, 1) == 1


class TestTheLoaderRefusesWhatIsNotACard:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_affects_player_is_required(self):
        card = _card()
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    def test_the_amount_is_required(self):
        """Absent, the cap reads 0 -- "can't draw cards", a harsher lock."""
        card = _card()
        card["abilities"][0].pop("amount")
        with pytest.raises(DslError, match="draw_limit needs an 'amount'"):
            compile_card(CardModel.model_validate(card))

    def test_a_permanent_filter_is_refused(self):
        card = _card()
        card["abilities"][0]["affects"] = {"types": ["Creature"]}
        with pytest.raises(DslError, match="draw_limit takes"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    return {
        "id": "t_bad_narset",
        "name": "Test Bad Narset",
        "oracle_text": "Each opponent can't draw more than one card each turn.",
        "mana_cost": "{1}{U}{U}",
        "types": ["Enchantment"],
        "colors": ["U"],
        "color_identity": ["U"],
        "abilities": [
            {
                "kind": "static",
                "text": "Each opponent can't draw more than one card each turn.",
                "effect": "draw_limit",
                "affects_player": "opponent",
                "amount": {"const": 1},
            }
        ],
    }
