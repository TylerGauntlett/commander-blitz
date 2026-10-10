"""Replacing a draw: "If you would draw a card, draw two cards instead."

Bard, King of Dale is the witness -- "If you would draw a card **except the first
one you draw in each of your draw steps**, draw two cards instead." -- with
Thought Reflection as the plain form and Alhammarret's Archive printing Bard's
exemption word for word. One static, `replace_draw`, with `draw_multiplier` and
`except_first_in_draw_step`.

The rules argument, and what goes wrong without each half:

- **614.1a: a replacement, not a trigger.** "Whenever you draw a card, draw a
  card" is the approximation: it puts the extra card in hand *after* the first,
  fires on its own draw and never ends, and lets the table respond between the
  two. This one is applied in `replacements.draw`, before any card moves.
- **121.2: each card is its own draw.** "Draw two" under a doubler is four
  draws, and a doubler asked once for the batch would make the exemption wrong
  for the second card of a draw step -- the first is exempt, the second is not.
- **614.5: once per event.** The two draws a doubler produces are not doubled by
  that doubler again (or the recursion never ends), but a *second* doubler is a
  different replacement and applies to each of them: two compound to four.
- **"Each of your draw steps", not "each turn".** The exemption is keyed on the
  cards drawn during *this* draw step -- `state.cards_drawn_this_draw_step`, not
  `cards_drawn_this_turn`. On a turn where something drew during upkeep the
  per-turn tally is already 1 when the draw step begins, and a version reading
  it would double the turn-based draw on exactly those turns.
- **616.1 against dredge.** The affected player orders the replacements. Dredge
  is offered first at every level, so dredging the original draw replaces it
  outright (no doubling), and declining lets the doubler make two draws that are
  each offered dredge again.
- **121.3/104.3c: an empty library.** A doubled draw from a library of one draws
  one card and is still an attempt to draw from an empty library.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player_statics import draw_replacements
from commanderblitz.engine.primitives import draw_cards
from commanderblitz.engine.replacements import draw as draw_with_replacements
from commanderblitz.engine.turn import _draw_step
from tests.conftest import pass_until

PLAIN = "t_draw_doubler"   # Thought Reflection
BARD = "t_bard_doubler"    # Bard, King of Dale / Alhammarret's Archive
TROLL = "t_dredger"        # dredge 3


def position(
    builder,
    mine: tuple[str, ...] = (),
    theirs: tuple[str, ...] = (),
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    active: int = 0,
    library: int = 20,
    graveyard: tuple[str, ...] = (),
):
    """Two players with ``library`` Islands each; doublers on either side.

    Frozen (`advance=False`) so the step and the active player are exactly what
    the test says -- the exemption reads nothing else.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .graveyard(0, list(graveyard))
        .library(0, ["island"] * library)
        .library(1, ["island"] * library)
        .step(step)
        .turn(3)
        .build(advance=False)
    )
    game.state.active_idx = active
    return game


def drive(gen, answers: list[list[int]] | None = None):
    """Run a draw generator, answering its questions in order (then declining)."""
    pending = list(answers or [])
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration as stop:
            return stop.value
        send = pending.pop(0) if pending else []


def draws(game, pid: int, count: int = 1, answers: list[list[int]] | None = None) -> int:
    """Have ``pid`` draw ``count`` through the replacements; return cards drawn."""
    before = len(game.state.players[pid].hand)
    drive(draw_with_replacements(game.state, pid, count), answers)
    return len(game.state.players[pid].hand) - before


def run_draw_step(game) -> int:
    """Run the active player's draw step as the turn walk does; return cards drawn."""
    game.state.step = Step.DRAW
    pid = game.state.active_player
    before = len(game.state.players[pid].hand)
    drive(_draw_step(game.state))
    return len(game.state.players[pid].hand) - before


class TestThePlainDoubler:
    """Thought Reflection: every draw, whenever."""

    def test_no_doubler_draws_one(self, builder):
        game = position(builder)
        assert draws(game, 0) == 1

    def test_a_draw_becomes_two(self, builder):
        game = position(builder, (PLAIN,))
        assert draws(game, 0) == 2

    def test_draw_two_becomes_four(self, builder):
        """121.2: each card of "draw two" is its own draw, and each is replaced."""
        game = position(builder, (PLAIN,))
        assert draws(game, 0, 2) == 4

    def test_the_turn_based_draw_is_doubled(self, builder):
        game = position(builder, (PLAIN,), step=Step.UPKEEP)
        assert run_draw_step(game) == 2

    def test_every_card_is_a_draw_event(self, builder):
        """Two cards drawn are two DRAW events -- "whenever you draw" sees both."""
        game = position(builder, (PLAIN,))
        start = len(game.state.events)
        draws(game, 0)
        fired = [e for e in game.state.events[start:] if e.type == EventType.DRAW]
        assert [e.data["nth"] for e in fired] == [1, 2]

    def test_the_bare_primitive_is_not_replaced(self, builder):
        """`draw_cards` is below the replacement, as it is for dredge -- the
        opening hand goes through it and must stay seven cards."""
        game = position(builder, (PLAIN,))
        assert len(draw_cards(game.state, 0, 1)) == 1


class TestTheDrawStepExemption:
    """Bard: "except the first one you draw in each of your draw steps"."""

    def test_the_draw_steps_first_draw_is_not_doubled(self, builder):
        game = position(builder, (BARD,), step=Step.UPKEEP)
        assert run_draw_step(game) == 1

    def test_the_second_draw_in_the_draw_step_is_doubled(self, builder):
        game = position(builder, (BARD,), step=Step.UPKEEP)
        run_draw_step(game)
        assert game.state.step is Step.DRAW
        assert draws(game, 0) == 2

    def test_draw_two_in_the_draw_step_is_one_then_two(self, builder):
        """The exemption moves between the two cards of one instruction."""
        game = position(builder, (BARD,))
        game.state.step = Step.DRAW
        game.state.cards_drawn_this_draw_step.clear()
        assert draws(game, 0, 2) == 3

    def test_an_upkeep_draw_is_doubled(self, builder):
        game = position(builder, (BARD,), step=Step.UPKEEP)
        assert draws(game, 0) == 2

    def test_a_main_phase_draw_is_doubled(self, builder):
        game = position(builder, (BARD,))
        assert draws(game, 0) == 2

    def test_an_upkeep_draw_does_not_use_up_the_exemption(self, builder):
        """Per draw step, not per turn: after two cards in upkeep the per-turn
        tally is 2, and the turn-based draw is still the draw step's first."""
        game = position(builder, (BARD,), step=Step.UPKEEP)
        draws(game, 0)
        assert game.state.cards_drawn_this_turn[0] == 2
        assert run_draw_step(game) == 1

    def test_the_exemption_is_fresh_every_draw_step(self, builder):
        game = position(builder, (BARD,), step=Step.UPKEEP)
        assert run_draw_step(game) == 1
        draws(game, 0)
        game.state.step = Step.UPKEEP
        assert run_draw_step(game) == 1

    def test_a_real_turn_draws_one(self, builder):
        """Through the turn walk end to end, from main phase to main phase."""
        game = (
            builder(players=2)
            .battlefield(0, [BARD])
            .hand(0, ["forest"])
            .hand(1, ["forest"])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 20)
            .build()
        )
        pass_until(game, lambda g: g.state.active_player == 1)
        pass_until(
            game,
            lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        before = len(game.state.players[0].library)
        pass_until(game, lambda g: g.state.active_player == 1)
        pass_until(
            game,
            lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert before - len(game.state.players[0].library) == 1


class TestItIsTheControllersReplacement:
    """"If **you** would draw" -- `affects_player: "you"`."""

    def test_the_opponent_is_unaffected(self, builder):
        game = position(builder, (PLAIN, BARD))
        assert draw_replacements(game.state, 1) == []
        assert draws(game, 1) == 1

    def test_the_opponents_draw_step_is_not_your_draw_step(self, builder):
        """"Your draw steps": the controller's first draw during an opponent's
        draw step is not exempt."""
        game = position(builder, (), (BARD,), step=Step.DRAW, active=0)
        assert draws(game, 1) == 2

    def test_it_wears_off_when_the_source_leaves(self, builder):
        from commanderblitz.engine.zones import move_object

        game = position(builder, (PLAIN,))
        source = game.state.battlefield[0]
        move_object(game.state, source, Zone.GRAVEYARD)
        assert draws(game, 0) == 1


class TestTwoDoublersCompound:
    """614.5 per replacement, 616.1 between them."""

    def test_two_plain_doublers_make_four(self, builder):
        game = position(builder, (PLAIN, PLAIN))
        assert draws(game, 0) == 4

    def test_two_bards_outside_the_draw_step_make_four(self, builder):
        game = position(builder, (BARD, BARD), step=Step.UPKEEP)
        assert draws(game, 0) == 4

    def test_two_bards_leave_the_first_draw_step_draw_alone(self, builder):
        game = position(builder, (BARD, BARD), step=Step.UPKEEP)
        assert run_draw_step(game) == 1

    def test_a_plain_doubler_and_a_bard_in_the_draw_step_make_three(self, builder):
        """The plain doubler turns the first draw into two draws; the first of
        those is the draw step's first card and Bard leaves it alone, the
        second is not and Bard doubles it. 1 + 2."""
        game = position(builder, (PLAIN, BARD), step=Step.UPKEEP)
        assert run_draw_step(game) == 3


class TestAnEmptyLibrary:
    """121.3 and 104.3c: drawing more cards than you have."""

    def test_a_doubled_draw_from_one_card_draws_it_and_fails_the_other(self, builder):
        game = position(builder, (PLAIN,), library=1)
        assert draws(game, 0) == 1
        assert game.state.players[0].attempted_draw_from_empty

    def test_a_doubled_draw_from_two_cards_is_safe(self, builder):
        game = position(builder, (PLAIN,), library=2)
        assert draws(game, 0) == 2
        assert not game.state.players[0].attempted_draw_from_empty

    def test_the_exempt_draw_from_an_empty_library_is_one_attempt(self, builder):
        game = position(builder, (BARD,), step=Step.UPKEEP, library=0)
        assert run_draw_step(game) == 0
        assert game.state.players[0].attempted_draw_from_empty


class TestAgainstDredge:
    """616.1: the affected player orders dredge against the doubler."""

    def test_dredging_the_original_draw_skips_the_doubling(self, builder):
        game = position(builder, (PLAIN,), graveyard=(TROLL,))
        troll = game.state.players[0].graveyard[0]
        before = len(game.state.players[0].library)
        assert draws(game, 0, answers=[[0]]) == 1
        assert game.state.objects[troll].zone is Zone.HAND
        assert before - len(game.state.players[0].library) == 3, "milled, drew nothing"

    def test_declining_then_dredging_one_of_the_two_draws(self, builder):
        game = position(builder, (PLAIN,), graveyard=(TROLL,))
        troll = game.state.players[0].graveyard[0]
        before = len(game.state.players[0].library)
        # decline on the original draw, dredge the first of the two it became
        assert draws(game, 0, answers=[[], [0]]) == 2
        assert game.state.objects[troll].zone is Zone.HAND
        assert before - len(game.state.players[0].library) == 4, "milled three, drew one"


class TestTheLoaderRefusesWhatIsNotACard:
    @pytest.mark.parametrize("bad", [0, 1, -2])
    def test_multiplier_below_two_is_refused(self, bad):
        with pytest.raises(DslError, match="draw_multiplier"):
            compile_card(CardModel.model_validate(_card(draw_multiplier=bad)))

    def test_multiplier_is_required(self):
        card = _card()
        card["abilities"][0].pop("draw_multiplier")
        with pytest.raises(DslError, match="draw_multiplier"):
            compile_card(CardModel.model_validate(card))

    def test_affects_player_is_required(self):
        card = _card()
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    def test_the_keys_mean_nothing_on_another_static(self):
        card = _card(except_first_in_draw_step=True)
        card["abilities"][0]["effect"] = "skip_draw_step"
        card["abilities"][0].pop("draw_multiplier")
        with pytest.raises(DslError, match="except_first_in_draw_step"):
            compile_card(CardModel.model_validate(card))

    def test_the_exemption_is_compiled_onto_the_static(self):
        compiled = compile_card(CardModel.model_validate(_card(except_first_in_draw_step=True)))
        static = compiled.abilities[0].static
        assert static["draw_multiplier"] == 2
        assert static["except_first_in_draw_step"] is True


def _card(**overrides) -> dict:
    ability = {
        "kind": "static",
        "text": "If you would draw a card, draw two cards instead.",
        "effect": "replace_draw",
        "affects_player": "you",
        "draw_multiplier": 2,
        **overrides,
    }
    return {
        "id": "t_bad_reflection",
        "name": "Test Bad Reflection",
        "oracle_text": "If you would draw a card, draw two cards instead.",
        "mana_cost": "{4}{U}{U}",
        "types": ["Enchantment"],
        "colors": ["U"],
        "color_identity": ["U"],
        "abilities": [ability],
    }
