"""Reading, while a spell resolves, whether its alternative cost was paid.

    Baleful Mastery — "You may pay {1}{B} rather than pay this spell's mana
    cost. If the {1}{B} cost was paid, an opponent draws a card. Exile target
    creature or planeswalker."

`evoke` was already the whole mechanism: an unconditional alternative mana cost
(118.9) offered beside the printed one, plus the `evoked` condition that reads
which of the two was paid, and `evoke_label` for what the card calls the price.
Dash proved it was not "the evoke keyword". What it had never been asked is the
question *during* `spell_effects`: every card that read it was a creature whose
enters trigger asks the permanent, and `stack.resolve` wrote `cast_evoked` onto
the object only after the effects ran. On an instant the `if` therefore read
False every time, and Baleful Mastery became a two-mana exile with no drawback —
a strictly better card than the printed one, which is worse than no card.

So the flag is now written before the effects, beside `cast_overloaded` and
`cast_cost_option`, which were moved for the same reason. And a copy carries it:
707.10 says a copy copies "additional or alternative costs" paid for the
original, so a copied Mastery cast for {1}{B} hands out a second card.

"An opponent" is not "each opponent": in a pod the caster chooses one, as the
spell resolves, and only that seat draws. That is `choose_player`, which asks
nobody when there is a single opponent.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import _default_answer

MASTERY = "t_baleful_probe"  # {3}{B}, or {1}{B} and an opponent draws
GIANT = "t_big"
SWAMP = "swamp"


def position(builder, *, players: int = 2, lands: int = 8):
    """You hold two Masteries over `lands` Swamps; every opponent has three Giants.

    The second copy is not decoration: with nothing left to do in your own main
    phase the engine auto-passes on into the opponent's turn, whose draw step
    would muddy every library count below. Holding a castable spell -- with a
    Giant still left to point it at -- is what stops it there.
    """
    b = builder(players=players).battlefield(0, [SWAMP] * lands).hand(0, [MASTERY, MASTERY])
    for pid in range(players):
        b = b.library(pid, [SWAMP] * 20)
    for pid in range(1, players):
        b = b.battlefield(pid, [GIANT] * 3)
    game = b.build()
    return game, game.state.players[0].hand[0]


def lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == MASTERY
    ]


def giants(game, pid: int):
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == GIANT]


def cast(game, *, paid_alternative: bool, at: int = 1):
    action = next(
        a
        for a in lines(game)
        if a.evoked is paid_alternative
        and a.targets
        and game.state.objects[a.targets[0].id].controller == at
    )
    game.apply(action)
    return action.targets[0].id


def libraries(game) -> list[int]:
    return [len(p.library) for p in game.state.players]


def resolve(game, chosen: int | None = None) -> list:
    """Pass until the stack is empty, answering "which opponent?" with `chosen`."""
    asked = []
    for _ in range(200):
        decision = game.pending()
        # Not `not stack` alone: the item is popped before its effects run, so
        # "which opponent?" is asked with the stack already empty.
        if not game.state.stack and decision.kind is DecisionKind.PRIORITY:
            return asked
        if decision.kind is DecisionKind.CHOOSE_PLAYER:
            asked.append(decision)
            game.apply(next(a for a in game.legal_actions() if a.targets[0].id == chosen))
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


class TestTheTwoCastLines:
    def test_both_prices_are_offered(self, builder):
        game, _ = position(builder)
        assert {a.evoked for a in lines(game)} == {False, True}

    def test_two_lands_reach_only_the_alternative(self, builder):
        game, _ = position(builder, lands=2)
        assert {a.evoked for a in lines(game)} == {True}

    def test_the_line_names_the_price_the_card_prints(self, builder):
        """The card calls it no keyword, so the chip says what is being paid."""
        game, _ = position(builder)
        cheap = next(a for a in lines(game) if a.evoked)
        assert "(paying {1}{B})" in cheap.label
        assert "evoked" not in cheap.label

    def test_mana_value_is_what_is_printed(self, builder):
        game, oid = position(builder)
        assert game.state.card(oid).mana_cost.mana_value() == 4


class TestIfTheAlternativeWasPaid:
    def test_the_opponent_draws_and_the_target_is_exiled(self, builder):
        """The regression: written after `spell_effects`, nobody ever drew."""
        game, _ = position(builder)
        before = libraries(game)
        victim = cast(game, paid_alternative=True)
        resolve(game)
        assert game.state.objects[victim].zone is Zone.EXILE
        after = libraries(game)
        assert after[1] == before[1] - 1, "the opponent draws a card"
        assert after[0] == before[0], "the caster does not"

    def test_a_two_player_game_asks_nobody(self, builder):
        game, _ = position(builder)
        cast(game, paid_alternative=True)
        assert resolve(game) == [], "one opponent is not a choice"


class TestIfThePrintedCostWasPaid:
    def test_nobody_draws(self, builder):
        """The pair. A rider that fires either way is a drawback the card does
        not print on its full-price line."""
        game, _ = position(builder)
        before = libraries(game)
        victim = cast(game, paid_alternative=False)
        asked = resolve(game)
        assert game.state.objects[victim].zone is Zone.EXILE
        assert libraries(game) == before
        assert asked == []


class TestAnOpponentInAPod:
    @pytest.mark.parametrize("chosen", [1, 2])
    def test_the_caster_chooses_exactly_one_opponent(self, builder, chosen):
        game, _ = position(builder, players=3)
        before = libraries(game)
        cast(game, paid_alternative=True, at=1)
        asked = resolve(game, chosen=chosen)

        assert len(asked) == 1 and asked[0].player == 0, "the caster chooses"
        assert {o.value for o in asked[0].options} == {1, 2}, "opponents only"
        after = libraries(game)
        assert after[chosen] == before[chosen] - 1
        other = 3 - chosen
        assert after[other] == before[other], "not each opponent"
        assert after[0] == before[0]

    def test_the_target_s_controller_need_not_be_the_one_who_draws(self, builder):
        """The draw is untargeted and unrelated to the exile."""
        game, _ = position(builder, players=3)
        before = libraries(game)
        victim = cast(game, paid_alternative=True, at=1)
        resolve(game, chosen=2)
        assert game.state.objects[victim].zone is Zone.EXILE
        assert libraries(game)[2] == before[2] - 1


class TestWhenItDoesNotResolve:
    def test_a_fizzled_mastery_hands_out_nothing(self, builder):
        """608.2b: with its only target gone the spell does nothing at all, the
        rider included."""
        game, _ = position(builder)
        before = libraries(game)
        victim = cast(game, paid_alternative=True)
        move_object(game.state, victim, Zone.GRAVEYARD, to_player=1, cause="test")
        resolve(game)
        assert libraries(game) == before


class TestACopy:
    def test_a_copy_of_the_alternative_cast_draws_again(self, builder):
        """707.10: a copy copies the alternative cost paid for the original."""
        from automtg.engine.effects.ops_stack import put_copy_on_stack

        game, _ = position(builder)
        before = libraries(game)
        victim = cast(game, paid_alternative=True)
        original = game.state.stack[-1]
        # Pointed at the *other* Giant: sharing the target, the copy would exile
        # it first and the original would fizzle -- correctly, and with no draw.
        other = next(o.oid for o in giants(game, 1) if o.oid != victim)
        duplicate = put_copy_on_stack(game.state, 0, original, [TargetRef.obj(other)])
        assert duplicate.evoked is True
        resolve(game)
        assert libraries(game)[1] == before[1] - 2, "one card per resolution"

    def test_a_copy_of_the_printed_cast_does_not(self, builder):
        from automtg.engine.effects.ops_stack import put_copy_on_stack

        game, _ = position(builder)
        before = libraries(game)
        cast(game, paid_alternative=False)
        duplicate = put_copy_on_stack(game.state, 0, game.state.stack[-1])
        assert duplicate.evoked is False
        resolve(game)
        assert libraries(game)[1] == before[1]


class TestTheLoader:
    def _mastery(self) -> dict:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "data" / "alternative_cost_paid.cards.json"
        return copy.deepcopy(json.loads(path.read_text(encoding="utf-8"))["cards"][0])

    def test_the_instant_loads(self):
        card = compile_card(CardModel.model_validate(self._mastery()))
        assert card.evoke is not None and card.evoke_label == "paying {1}{B}"

    def test_the_rider_with_no_alternative_is_refused(self):
        """It could never be true."""
        card = self._mastery()
        card.pop("evoke")
        with pytest.raises(DslError, match="reads the 'evoked' condition"):
            compile_card(CardModel.model_validate(card))

    def test_the_alternative_with_no_rider_is_refused(self):
        """A cheaper Mastery with no drawback is a different, better card."""
        card = self._mastery()
        card["spell_effects"] = card["spell_effects"][1:]
        with pytest.raises(DslError, match="no effect reads via 'evoked'"):
            compile_card(CardModel.model_validate(card))
