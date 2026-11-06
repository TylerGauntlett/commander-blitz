"""An anthem sized by how many times you've cast your commander.

    Commander's Insignia -- "Creatures you control get +1/+1 for each time
    you've cast your commander from the command zone this game."

Rule 903.8 already makes the engine keep this count: commander tax is {2} "for
each previous time the player casting it has cast it from the command zone that
game", and `Game` bumps `Player.commander_tax` once per such cast. The effect
side has read it as `commander_casts_this_game` since Hatut Zeraze Strike Force,
but a *static* magnitude could not, and the near misses are wrong: a `pump` on a
cast trigger wears off and misses every creature that enters later, and
`spells_cast_this_turn` counts every spell and forgets them at cleanup.

The tally is a pipeline input -- no layer writes it -- so it is safe in
`STATIC_VALUE_KEYS`. What must hold, and what this file pins:

- the anthem grows the moment a cast from the command zone is made, through the
  `char_version` cache, and again on a recast after the commander came home;
- it covers creatures that enter afterwards and keeps counting after the
  commander has left the battlefield, because counted casts are history;
- a commander put onto the battlefield by an effect, and an opponent's
  commander, add nothing; partners are summed;
- the loader admits the leaf for "you" only, alone or inside `times`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, oids_of, settle

INSIGNIA = "t_ccc_insignia"
WAITING = "t_ccc_strike_force"   # keeps priority with a castable card in hand
BEAR = "t_bear"
SMALL = "t_commander_two"        # {1}{W}
BIG = "t_commander_five"         # {3}{W}{W}


def board(builder, *, commanders=(SMALL,), opponent_commanders=()):
    """Player 0 with the Insignia, a Bear and enough land to cast a commander twice."""
    b = (
        builder(players=2)
        .battlefield(0, [INSIGNIA, BEAR] + ["plains"] * 6 + ["forest"] * 7)
        .hand(0, [WAITING])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
    )
    if commanders:
        b = b.commander(0, list(commanders))
    if opponent_commanders:
        b = b.commander(1, list(opponent_commanders))
    game = b.build()
    return game, oids_of(game, BEAR, 0)[0]


def cast_commander(game, card_id: str = SMALL) -> int:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == card_id)


def send_home(game, oid: int) -> None:
    move_object(game.state, oid, Zone.GRAVEYARD)
    assert oid in game.state.players[0].command


def pt(game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestTheAnthemGrowsWithEachCast:
    def test_no_cast_yet_is_no_bonus(self, builder):
        game, bear = board(builder)

        assert pt(game, bear) == (2, 2)

    def test_a_cast_from_the_command_zone_is_read_at_once(self, builder):
        """The Bear was read (and cached) before the cast; the tax write must
        invalidate that, or the anthem lags a cast behind."""
        game, bear = board(builder)
        assert pt(game, bear) == (2, 2)

        cast_commander(game)

        assert pt(game, bear) == (3, 3)

    def test_a_recast_after_it_came_home_counts_again(self, builder):
        game, bear = board(builder)
        send_home(game, cast_commander(game))
        cast_commander(game)

        assert pt(game, bear) == (4, 4)

    def test_the_commander_itself_is_a_creature_you_control(self, builder):
        game, _ = board(builder)
        commander = cast_commander(game)

        base = game.state.card_of(game.state.objects[commander])
        assert pt(game, commander) == (base.power + 1, base.toughness + 1)


class TestItIsContinuous:
    def test_a_creature_entering_later_gets_it(self, builder):
        game, _ = board(builder)
        cast_commander(game)
        token = create_token(game.state, "soldier_1_1_w", 0, 1)[0]

        assert pt(game, token) == (2, 2)

    def test_the_count_survives_the_commander_leaving(self, builder):
        game, bear = board(builder)
        send_home(game, cast_commander(game))

        assert pt(game, bear) == (3, 3)


class TestWhatDoesNotCount:
    def test_put_onto_the_battlefield_by_an_effect_is_not_cast(self, builder):
        game, bear = board(builder)
        commander = game.state.players[0].commanders[0]
        move_object(game.state, commander, Zone.BATTLEFIELD, to_player=0)

        assert pt(game, bear) == (2, 2)

    def test_an_opponents_commander_casts_are_theirs(self, builder):
        game, bear = board(builder, opponent_commanders=[BIG])
        theirs = game.state.players[1].commanders[0]
        game.state.players[1].commander_tax[theirs] = 3
        game.state.bump_chars()

        assert pt(game, bear) == (2, 2)

    def test_partners_are_both_your_commander(self, builder):
        game, bear = board(builder, commanders=(SMALL, BIG))
        small, big = game.state.players[0].commanders
        game.state.players[0].commander_tax[small] = 2
        game.state.players[0].commander_tax[big] = 1
        game.state.bump_chars()

        assert pt(game, bear) == (5, 5)


def _insignia(power) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_ccc_insignia_probe",
            "name": "Insignia Probe",
            "mana_cost": "{2}{W}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "effect": "buff",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "power": power,
                    "toughness": power,
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_bare_leaf_compiles(self):
        compile_card(_insignia({"commander_casts_this_game": "you"}))

    def test_a_bigger_step_through_times_compiles(self):
        compile_card(
            _insignia({"times": [{"const": 2}, {"commander_casts_this_game": "you"}]})
        )

    @pytest.mark.parametrize("bad", ["each_opponent", "all", 3, None])
    def test_anyone_but_you_is_refused(self, bad):
        with pytest.raises(DslError, match="commander_casts_this_game: a static can only ask"):
            compile_card(_insignia({"commander_casts_this_game": bad}))
