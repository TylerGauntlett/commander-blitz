"""`commander_casts_this_game` -- the commander-tax tally, read as a number.

    Hatut Zeraze Strike Force -- "When you cast this spell, copy it for each
    time you've cast your commander from the command zone this game."

Rule 903.8: a commander cast from the command zone costs {2} more "for each
previous time the player casting it has cast it from the command zone that
game". The engine already keeps that count, one entry per commander in
`Player.commander_tax`, but only the cost computation could read it, so the
Strike Force's copy count was unsayable. The near miss, `spells_cast_this_game`,
counts every spell from every zone: the Strike Force itself, a commander cast
from hand, and the rest of the game's spells would all add copies the card does
not print.

What must hold, and what this file pins:

- a cast from the command zone counts, once per cast, across the commander
  coming home and being cast again;
- "your commander" with partners is either of them, so both tallies are summed;
- a commander put onto the battlefield by an effect was not cast and adds
  nothing, and an opponent's commander is theirs;
- only the player's *commanders* are read, never some other tax entry;
- on the printed trigger, the count is the number of copies, each of which
  resolves as a token (706.10).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, settle

STRIKE_FORCE = "t_ccc_strike_force"
SMALL = "t_commander_two"       # {1}{W}
BIG = "t_commander_five"        # {3}{W}{W}
YOURS = {"commander_casts_this_game": "you"}


def value(game, expr=YOURS, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def position(builder, *, commanders=(SMALL,), opponent_commanders=()):
    """Player 0 with ``commanders`` at home and enough land to cast one twice.

    The Strike Force waits in hand throughout: with a castable card the seat
    keeps priority after a resolution instead of auto-passing the turn away.
    """
    b = (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + ["forest"] * 7)
        .hand(0, [STRIKE_FORCE])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
    )
    if commanders:
        b = b.commander(0, list(commanders))
    if opponent_commanders:
        b = b.commander(1, list(opponent_commanders))
    return b.build()


def cast_commander_home_and_back(game, card_id: str = SMALL) -> int:
    """Cast the commander from the command zone, then send it home (903.9a)."""
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == card_id)
    move_object(game.state, oid, Zone.GRAVEYARD)
    assert oid in game.state.players[0].command
    return oid


class TestItCountsCastsFromTheCommandZone:
    def test_none_yet_is_zero(self, builder):
        assert value(position(builder)) == 0

    def test_one_cast_is_one(self, builder):
        game = position(builder)
        cast_commander_home_and_back(game)

        assert value(game) == 1

    def test_a_recast_after_it_came_home_counts_again(self, builder):
        game = position(builder)
        cast_commander_home_and_back(game)
        cast_commander_home_and_back(game)

        assert value(game) == 2

    def test_it_agrees_with_the_tax(self, builder):
        game = position(builder)
        oid = cast_commander_home_and_back(game)
        cast_commander_home_and_back(game)

        assert value(game) == game.state.players[0].commander_tax[oid]


class TestWhatIsNotACommanderCast:
    def test_put_onto_the_battlefield_by_an_effect_is_not_cast(self, builder):
        game = position(builder)
        commander = game.state.players[0].commanders[0]
        move_object(game.state, commander, Zone.BATTLEFIELD, to_player=0)

        assert value(game) == 0

    def test_an_opponents_commander_is_theirs(self, builder):
        game = position(builder, opponent_commanders=[BIG])
        theirs = game.state.players[1].commanders[0]
        game.state.players[1].commander_tax[theirs] = 3

        assert value(game) == 0
        assert value(game, {"commander_casts_this_game": "each_opponent"}) == 3

    def test_a_tax_entry_for_something_else_is_not_read(self, builder):
        """Keyed by `commanders_of`, so an object that is not the player's
        commander never counts, whatever ends up in the tax ledger."""
        game = position(builder)
        game.state.players[0].commander_tax[10_000] = 4

        assert value(game) == 0


class TestPartnersAreBothYourCommander:
    def test_the_two_tallies_are_summed(self, builder):
        game = position(builder, commanders=(SMALL, BIG))
        small, big = game.state.players[0].commanders
        game.state.players[0].commander_tax[small] = 2
        game.state.players[0].commander_tax[big] = 1

        assert value(game) == 3


class TestThePrintedTrigger:
    def _cast_strike_force(self, game):
        game.apply(action_for_card(game, ActionKind.CAST, STRIKE_FORCE))
        settle(game)
        return sum(
            1 for o in game.state.battlefield_objects(0) if o.def_id == STRIKE_FORCE
        )

    def test_no_commander_cast_means_no_copy(self, builder):
        game = position(builder)

        assert self._cast_strike_force(game) == 1

    def test_two_commander_casts_make_two_token_copies(self, builder):
        game = position(builder)
        cast_commander_home_and_back(game)
        cast_commander_home_and_back(game)

        assert self._cast_strike_force(game) == 3
        tokens = [
            o for o in game.state.battlefield_objects(0)
            if o.def_id == STRIKE_FORCE and o.is_token
        ]
        assert len(tokens) == 2

    def test_the_commander_on_the_battlefield_still_counts_its_cast(self, builder):
        """Counted casts are history: the commander need not be home."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, SMALL))
        settle(game)

        assert self._cast_strike_force(game) == 2


class TestTheLoader:
    def test_the_witness_shape_validates(self):
        validate_value(YOURS, "probe")

    @pytest.mark.parametrize("bad", ["yours", 3, True, None])
    def test_a_non_player_spec_is_refused(self, bad):
        with pytest.raises(DslError, match="commander_casts_this_game: needs a player spec"):
            validate_value({"commander_casts_this_game": bad}, "probe")

    def test_the_fixture_card_compiles(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_ccc_probe",
                    "name": "Commander Cast Probe",
                    "mana_cost": "{G}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "abilities": [
                        {
                            "kind": "triggered",
                            "active_zones": ["stack"],
                            "trigger": {
                                "event": "spell_cast",
                                "source": "self",
                                "controller": "you",
                            },
                            "effects": [{"op": "copy_spell", "amount": YOURS}],
                        }
                    ],
                }
            )
        )
