"""A static "you may play cards exiled with this" gated on an opponent's life loss.

    At the beginning of your upkeep, exile the top card of your library.
    **During your turn, if an opponent lost life this turn, you may play lands
    and cast spells from among cards exiled with this enchantment.**
                                                     -- Theater of Horrors

The exiled cards wait in exile with a `while_exiled` permission that is shut
except while `playable_condition:
"your_turn_opponent_lost_life_exiled_with_source"` holds, read where the play
is offered (`objects.playable_condition_met`) and so rechecked every time:

- it is the permission holder's turn -- "during your turn";
- some opponent's `TurnLedger.life_lost` is nonzero -- "an opponent lost life
  this turn", so the holder's own loss opens nothing, and a loss earlier in the
  same turn (an upkeep drain) counts as much as one in the main phase;
- the card is still exiled with the enchantment, which is on the battlefield
  under the holder's control. The permission is the enchantment's static
  ability, which works only while it is on the battlefield (113.6); a
  returned enchantment is a new object with nothing exiled with it (400.7).

Without the condition the nearest spelling, `while_exiled` alone, lets the
cards be played on any turn with no life lost and after the enchantment is
gone: a strictly stronger card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import playable_condition_met
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until, settle

THEATER = "t_horror_theater"         # upkeep: exile the top card, linked, gated
DRAIN = "t_horror_drain"             # {0} instant: each opponent loses 1 life
SELF_DRAIN = "t_horror_self_drain"   # {0} instant: you lose 1 life
GIFT = "t_cmdr_free_gift"            # {0} instant: the cast path
CONDITION = "your_turn_opponent_lost_life_exiled_with_source"


def position(builder, top: str = "forest"):
    """Seat 0 controls the theater and reaches its own main phase.

    The game starts in seat 1's end step, so seat 0's upkeep trigger fires for
    real and exiles ``top`` (a Forest for the land path, a {0} instant for the
    cast path): neither needs mana, so the permission is the only thing that
    makes playing it legal and `legal_actions` answers whether it is open.
    """
    game = (
        builder(players=2)
        .battlefield(0, [THEATER])
        .library(0, [top] + ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, [DRAIN, SELF_DRAIN])
        .active(1)
        .step(Step.END_STEP)
        .build()
    )
    to_my_main(game)
    (exiled,) = game.state.players[0].exile
    return game, only_oid(game, THEATER, 0), exiled


def to_my_main(game) -> None:
    pass_until(
        game, lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == 0
    )


def cast(game, def_id: str) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
            and game.state.objects[a.source].zone is Zone.HAND
        )
    )
    settle(game)


def playable(game, oid: int) -> bool:
    return any(
        a.source == oid and a.kind in (ActionKind.CAST, ActionKind.PLAY_LAND)
        for a in game.legal_actions()
    )


class TestTheUpkeepExile:
    def test_the_top_card_is_exiled_and_linked(self, builder):
        game, theater, forest = position(builder)
        card = game.state.objects[forest]
        assert card.zone is Zone.EXILE
        assert card.exiled_by == theater
        assert card.playable_condition == CONDITION


class TestShutUntilAnOpponentLosesLife:
    def test_nothing_is_playable_before_any_life_is_lost(self, builder):
        game, _, forest = position(builder)
        assert not playable(game, forest)

    def test_an_opponent_losing_life_opens_the_land_half(self, builder):
        game, _, forest = position(builder)
        cast(game, DRAIN)
        assert game.state.turn_ledger.life_lost.get(1) == 1
        assert playable(game, forest), "the land is played under the permission"

    def test_an_opponent_losing_life_opens_the_cast_half(self, builder):
        game, _, gift = position(builder, top=GIFT)
        assert not playable(game, gift)
        cast(game, DRAIN)
        assert playable(game, gift), "the spell is cast under the permission"

    def test_your_own_life_loss_does_not(self, builder):
        game, _, forest = position(builder)
        cast(game, SELF_DRAIN)
        assert game.state.turn_ledger.life_lost.get(0) == 1
        assert not playable(game, forest)

    def test_damage_to_an_opponent_is_life_loss_too(self, builder):
        """The ledger counts every loss, damage included (119.3)."""
        game, _, forest = position(builder)
        game.state.turn_ledger.life_lost[1] = 3
        assert playable(game, forest)


class TestOnlyDuringYourTurn:
    def test_an_opponents_turn_stays_shut_whoever_lost_life(self, builder):
        game, _, gift = position(builder, top=GIFT)
        pass_until(
            game, lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN
        )
        game.state.turn_ledger.life_lost[1] = 2
        game.state.turn_ledger.life_lost[0] = 2
        # Asked directly, so the answer does not hang on who holds priority.
        assert not playable_condition_met(game.state, game.state.objects[gift])

    def test_the_same_loss_on_your_turn_opens_it(self, builder):
        game, _, gift = position(builder, top=GIFT)
        game.state.turn_ledger.life_lost[1] = 2
        assert playable_condition_met(game.state, game.state.objects[gift])

    def test_the_loss_is_this_turns_and_the_card_waits(self, builder):
        game, _, forest = position(builder)
        cast(game, DRAIN)
        assert playable(game, forest)
        pass_until(
            game, lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN
        )
        to_my_main(game)
        assert forest in game.state.players[0].exile, "it waited in exile"
        assert not playable(game, forest), "a new turn, and nobody has lost life in it"
        game.state.turn_ledger.life_lost[1] = 1
        assert playable(game, forest)


class TestOnlyWhileExiledWithTheEnchantment:
    def test_the_enchantment_leaving_shuts_it(self, builder):
        game, theater, forest = position(builder)
        cast(game, DRAIN)
        assert playable(game, forest)
        move_object(game.state, theater, Zone.GRAVEYARD)
        assert not playable(game, forest)
        assert forest in game.state.players[0].exile

    def test_a_returned_enchantment_is_a_new_object(self, builder):
        """400.7: nothing is exiled with the object that came back."""
        game, theater, forest = position(builder)
        cast(game, DRAIN)
        move_object(game.state, theater, Zone.GRAVEYARD)
        move_object(game.state, theater, Zone.BATTLEFIELD)
        assert not playable(game, forest)

    def test_a_card_exiled_by_something_else_is_not_among_them(self, builder):
        game, theater, forest = position(builder)
        cast(game, DRAIN)
        game.state.objects[theater].exiled_cards.remove(forest)
        assert not playable(game, forest)

    def test_leaving_exile_ends_it(self, builder):
        game, _, forest = position(builder)
        move_object(game.state, forest, Zone.GRAVEYARD)
        assert game.state.objects[forest].playable_condition is None


def _card(effect: dict) -> dict:
    return {
        "id": "t_probe",
        "name": "Probe",
        "mana_cost": "{R}",
        "types": ["Sorcery"],
        "spell_effects": [effect],
    }


LOOK = {
    "op": "look_at_top",
    "player": "you",
    "amount": {"const": 1},
    "objects": {"count": "all"},
    "destination": "exile",
    "playable": "while_exiled",
    "playable_condition": CONDITION,
}


class TestTheLoader:
    def test_it_loads_on_a_linked_exile(self):
        compile_card(CardModel.model_validate(_card({**LOOK, "link": True})))
        compile_card(
            CardModel.model_validate(
                _card({"op": "exile", "objects": {"zone": "graveyard", "controller": "you"},
                       "link": True, "playable": "while_exiled",
                       "playable_condition": CONDITION})
            )
        )

    def test_it_needs_the_link(self):
        with pytest.raises(DslError, match="link"):
            compile_card(CardModel.model_validate(_card(LOOK)))

    def test_it_is_refused_on_grant_playable(self):
        with pytest.raises(DslError, match="link"):
            compile_card(
                CardModel.model_validate(
                    _card({"op": "grant_playable", "playable_condition": CONDITION,
                           "objects": {"zone": "exile", "exiled_with": "self", "count": "all"}})
                )
            )
