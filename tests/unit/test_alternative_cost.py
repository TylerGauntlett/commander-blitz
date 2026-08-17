"""Spectacle and prowl: an alternative cost you may only sometimes pay.

The engine already had two alternative costs — `evoke` from hand and
`graveyard_cost` from a graveyard — and both are *unconditional*: if the card
is where it needs to be, the line is offered. Spectacle and prowl are the same
shape with a gate on the front: "you may cast this for its spectacle cost **if
an opponent lost life this turn**".

The ledger those conditions read shipped earlier; this is the other half.

**A field of its own rather than a condition bolted onto `evoke`.** Evoke's flag
is written onto the permanent and read back by "it's sacrificed when it enters",
so a spectacle spell reusing it would be a card quietly claiming to have been
evoked. `Action.alternative` is a separate flag for the same reason it is part
of the action's identity at all: the same card offered at two prices is two
different things to do.

**The condition is checked when the line is offered, not when it is paid.** It
is permission to cast the card this way at all (601.2b), so offering the line
and then refusing the payment would show a price the player can never pay. The
loader refuses an `alternative_cost` with no condition, because that is exactly
`evoke` and a card spelling it this way would be offered twice at two prices
with nothing to choose between them.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player, lose_life
from tests.conftest import _default_answer

SPECTACLE = "t_spectacle"  # {2}{R} instant, 2 damage; spectacle {R}


def position(builder, *, lands: int = 3):
    return (
        builder(players=2)
        .hand(0, [SPECTACLE])
        .battlefield(0, ["mountain"] * lands)
        .build()
    )


def cast_lines(game) -> list[str]:
    return [a.label for a in game.legal_actions() if a.kind is ActionKind.CAST]


def spectacle_lines(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.alternative
    ]


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def untapped_lands(game, pid: int = 0) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(pid)
        if not o.tapped and "Land" in game.state.card_of(o).types
    )


class TestWhenItIsOffered:
    def test_it_is_not_offered_before_the_condition_holds(self, builder):
        game = position(builder)
        assert spectacle_lines(game) == []
        assert cast_lines(game), "the printed cost is still offered"

    def test_it_appears_once_an_opponent_loses_life(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 2)
        assert spectacle_lines(game)

    def test_damage_to_an_opponent_counts(self, builder):
        """Rule 118.2, and the case spectacle is actually printed for: you cast
        it after burning somebody, not after draining them."""
        game = position(builder)
        damage_player(game.state, 1, 3, None)
        assert spectacle_lines(game)

    def test_your_own_life_loss_does_not_count(self, builder):
        """The condition says *an opponent*."""
        game = position(builder)
        lose_life(game.state, 0, 5)
        assert spectacle_lines(game) == []

    def test_both_prices_are_offered_at_once(self, builder):
        """The player chooses. Two prices for one card are two actions, which
        is why `alternative` is part of the action's identity."""
        game = position(builder)
        lose_life(game.state, 1, 1)
        printed = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and not a.alternative
        ]
        assert printed and spectacle_lines(game)


class TestWhatItCosts:
    def test_the_alternative_price_is_paid(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 1)
        before = untapped_lands(game)
        game.apply(spectacle_lines(game)[0])
        settle(game)
        assert before - untapped_lands(game) == 1, "{R}, not {2}{R}"

    def test_the_printed_price_is_still_the_printed_price(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 1)
        printed = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and not a.alternative
        ]
        before = untapped_lands(game)
        game.apply(printed[0])
        settle(game)
        assert before - untapped_lands(game) == 3

    def test_it_is_castable_when_the_printed_cost_is_not(self, builder):
        """The whole point: a spell you could not otherwise afford.

        Built with three lands and then tapped down to one, rather than built
        with one. A position where the holder can cast nothing hands priority
        straight to the opponent, so `legal_actions` would be answering a
        different player's question and the test would pass for the wrong
        reason.
        """
        game = position(builder)
        lands = [
            o
            for o in game.state.battlefield_objects(0)
            if "Land" in game.state.card_of(o).types
        ]
        for land in lands[:2]:
            land.tapped = True
        assert cast_lines(game) == [], "{2}{R} is out of reach on one land"
        lose_life(game.state, 1, 1)
        assert spectacle_lines(game), "but {R} is not"

    def test_the_spell_still_does_what_it_says(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 1)
        before = sum(p.life for p in game.state.players)
        game.apply(spectacle_lines(game)[0])
        settle(game)
        assert before - sum(p.life for p in game.state.players) == 2


class TestItIsNotEvoke:
    def test_the_spell_does_not_report_itself_as_evoked(self, builder):
        """Reusing evoke's flag would make a spectacle spell claim to have been
        evoked, which "it's sacrificed when it enters" reads."""
        game = position(builder)
        lose_life(game.state, 1, 1)
        action = spectacle_lines(game)[0]
        assert action.alternative
        assert not action.evoked

    def test_the_two_prices_are_different_actions(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 1)
        keys = {a.key() for a in game.legal_actions() if a.kind is ActionKind.CAST}
        assert len(keys) == len(
            [a for a in game.legal_actions() if a.kind is ActionKind.CAST]
        ), "two prices for one card must not collapse into one action"


class TestTheLoaderGuardsIt:
    def base(self, **alt) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Draw a card.",
            "mana_cost": "{2}{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            "alternative_cost": alt,
        }

    def test_no_mana_is_refused(self):
        with pytest.raises(DslError, match="needs 'mana'"):
            compile_card(
                CardModel.model_validate(self.base(condition={"is_your_turn": True}))
            )

    def test_no_condition_is_refused(self):
        """An unconditional alternative cost is `evoke`, and a card spelling it
        this way would be offered twice at two prices with nothing between."""
        with pytest.raises(DslError, match="needs a 'condition'"):
            compile_card(CardModel.model_validate(self.base(mana="{U}")))

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                CardModel.model_validate(
                    self.base(mana="{U}", condition={"is_your_turn": True}, sacrifice=True)
                )
            )

    def test_a_malformed_condition_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.base(mana="{U}", condition={"nonsense_leaf": 1})
                )
            )

    def test_the_spectacle_card_compiles(self, registry):
        card = registry.get(SPECTACLE)
        assert card.alternative_cost is not None
        assert card.alternative_condition is not None
