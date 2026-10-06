""""At least 7 life more than your starting life total" -- a relative threshold.

Rule 103.4: each player begins the game with a starting life total (40 in
Commander, 903.7), and Righteous Valkyrie and Angel of Destiny measure from it.
The engine had a module constant, `STARTING_LIFE`, and nothing recorded on the
seat, so the only way to write either card was a `const` 47 or 55 -- a format
assumption written into the card, which is a different card in any game that
began anywhere but 40. `PlayerState.starting_life` records the number per seat,
and `{"starting_life_of": "you"}` reads it, in the effect language and in a
static's condition alike.

The static half needed `sum` in the static value language: the printed
sentence is `life >= starting + 7`, a comparison against a sum, and the static
language could multiply (`times`) but not add. It also relies on a life change
invalidating the characteristics cache (`primitives._move_life`), so the
threshold is crossed here through `gain_life`, `lose_life` and damage with no
manual bump.

Righteous Valkyrie is the shipped witness for the static, Angel of Destiny for
the effect side.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.effects.conditions import evaluate
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.errors import DslError
from automtg.engine.player import STARTING_LIFE
from automtg.engine.primitives import damage_player, gain_life, lose_life

ANTHEM = "t_valkyrie_anthem"


def position(builder, *, life: int = STARTING_LIFE, starting: int = STARTING_LIFE):
    """Player 0 with the anthem and a Grizzly Bears, at ``life`` from ``starting``."""
    game = builder(players=2).battlefield(0, [ANTHEM, "grizzly_bears"]).build()
    game.state.players[0].starting_life = starting
    game.state.players[0].life = life
    game.state.bump_chars()
    bear = next(
        o for o in game.state.battlefield if game.state.objects[o].def_id == "grizzly_bears"
    )
    return game, bear


def pt(game, oid) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestTheSeatRecordsIt:
    def test_a_new_game_starts_every_seat_at_the_commander_total(self, builder):
        game = builder(players=4).build()
        assert [p.starting_life for p in game.state.players] == [40] * 4

    def test_changing_life_does_not_move_it(self, builder):
        game, _ = position(builder)
        gain_life(game.state, 0, 12)
        lose_life(game.state, 0, 3)
        assert game.state.players[0].starting_life == 40
        assert game.state.players[0].life == 49

    def test_it_is_serialized_with_the_seat(self, builder):
        game, _ = position(builder, starting=30)
        assert game.state.players[0].to_dict()["starting_life"] == 30


class TestTheStaticCondition:
    def test_off_at_the_starting_total(self, builder):
        game, bear = position(builder, life=40)
        assert pt(game, bear) == (2, 2)

    def test_the_boundary_is_seven_not_six(self, builder):
        game, bear = position(builder, life=46)
        assert pt(game, bear) == (2, 2), "6 more is not 'at least 7 more'"
        game, bear = position(builder, life=47)
        assert pt(game, bear) == (4, 4), "7 more is"

    def test_it_is_relative_to_the_seat_not_to_forty(self, builder):
        # A game begun at 20: 27 is 7 more than the starting total. A card that
        # had hard-coded 47 would read this board as nowhere near.
        game, bear = position(builder, life=27, starting=20)
        assert pt(game, bear) == (4, 4)
        game, bear = position(builder, life=47, starting=50)
        assert pt(game, bear) == (2, 2), "47 is not 7 more than 50"


class TestALifeChangeIsSeen:
    """The cache: crossing the threshold through the real paths, no manual bump."""

    def test_gaining_across_the_line_switches_it_on(self, builder):
        game, bear = position(builder, life=40)
        assert pt(game, bear) == (2, 2)
        gain_life(game.state, 0, 7)
        assert pt(game, bear) == (4, 4)

    def test_losing_life_wears_it_off(self, builder):
        game, bear = position(builder, life=47)
        assert pt(game, bear) == (4, 4)
        lose_life(game.state, 0, 1)
        assert pt(game, bear) == (2, 2)

    def test_damage_wears_it_off_too(self, builder):
        game, bear = position(builder, life=47)
        assert pt(game, bear) == (4, 4)
        damage_player(game.state, 0, 1, None)
        assert pt(game, bear) == (2, 2)


class TestTheEffectLanguage:
    def ctx(self, game, controller: int = 0) -> EffectContext:
        return EffectContext(state=game.state, controller=controller)

    def test_it_reads_the_seat(self, builder):
        game, _ = position(builder, starting=25)
        assert evaluate_value(self.ctx(game), {"starting_life_of": "you"}) == 25
        assert evaluate_value(self.ctx(game, 1), {"starting_life_of": "you"}) == 40

    def test_the_angel_of_destiny_threshold(self, builder):
        cond = {
            "cmp": ">=",
            "left": {"life_of": "you"},
            "right": {"sum": [{"starting_life_of": "you"}, {"const": 15}]},
        }
        game, _ = position(builder, life=54)
        assert not evaluate(self.ctx(game), cond)
        game, _ = position(builder, life=55)
        assert evaluate(self.ctx(game), cond)


class TestTheLoader:
    def probe(self, right) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Probe.",
                        "effect": "buff",
                        "affects": {"controller": "you", "types": ["Creature"]},
                        "power": {"const": 2},
                        "toughness": {"const": 2},
                        "condition": {
                            "cmp": ">=",
                            "left": {"min_life_of": "you"},
                            "right": right,
                        },
                    }
                ],
            }
        )

    def test_the_printed_shape_loads(self):
        compile_card(self.probe({"sum": [{"starting_life_of": "you"}, {"const": 7}]}))

    def test_a_static_may_only_ask_about_you(self):
        with pytest.raises(DslError, match="starting_life_of"):
            compile_card(self.probe({"starting_life_of": "each_opponent"}))

    def test_a_sum_term_is_held_to_the_static_language(self):
        with pytest.raises(DslError, match="static values may only use"):
            compile_card(self.probe({"sum": [{"life_of": "you"}, {"const": 7}]}))

    def test_a_sum_needs_two_terms(self):
        with pytest.raises(DslError, match="sum"):
            compile_card(self.probe({"sum": [{"const": 7}]}))

    def test_the_effect_side_refuses_a_plural_seat(self):
        from automtg.engine.effects.values import validate_value

        with pytest.raises(DslError, match="one player's"):
            validate_value({"starting_life_of": "each_opponent"}, "probe")
        validate_value({"starting_life_of": "you"}, "probe")
        validate_value({"starting_life_of": {"target": "t1"}}, "probe")
