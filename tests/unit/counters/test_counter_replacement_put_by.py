"""A counter replacement keyed on who puts the counters, reaching players.

    "If **you** would put one or more counters on a permanent **or player**,
    put twice that many of each of those kinds of counters on that permanent
    or player instead."                      -- Innkeeper's Talent, level 3

Every `replace_counters` card before this one named the *recipient* -- "a
creature you control", "a permanent you control" -- and took a required
`affects`. This sentence names the *putter* instead (122.6a: the controller of
the spell or ability putting them, or for a cost or an arrival the permanent's
controller), and reaches two things `affects` cannot: an opponent's permanent,
and a player. So:

- ``put_by: "you"`` -- `add_counters` now knows who is putting (`_putter`), and
  a static with this key applies only to that player's placements, on any
  permanent. Doubling Season is the contrast: it doubles counters an opponent
  puts on *your* permanent, and none you put on theirs.
- ``affects_player`` -- a player is not a permanent, so the static reaches
  poison counters only by naming players. Poison had two writers, the
  `add_poison` op and infect damage, each doing ``player.poison +=`` by hand;
  both now go through `primitives.add_poison`, the one funnel the replacement
  is read in.
- No ``effects_only``: "if you would put" includes a cost, so a planeswalker's
  +1 under the Talent puts two loyalty counters on it (the card's ruling,
  as for Vorinclex, Monstrous Raider).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import add_counters, add_poison, damage_player
from tests.conftest import action_for_card, only_oid, pass_until

TALENT = "t_pb_talent"  # put_by you, every permanent and every player, doubled
VENOM = "t_pb_venom"  # target opponent gets two poison counters
SEASON = "t_rc_season"  # recipient-keyed: "a permanent you control"
BEAR = "t_rc_bear"
WALKER = "t_ceo_walker"  # loyalty 3, +1: gain 2 life
HYDRA = "t_ceo_hydra"  # enters with two +1/+1 counters
INFECT = "t_infecter"


def position(builder, mine=(), theirs=(), hand=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 4 + ["forest"] * 4 + list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def plus_ones(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


class TestKeyedOnThePutter:
    def test_my_counter_on_my_creature_is_doubled(self, builder):
        game = position(builder, mine=[TALENT, BEAR])
        oid = only_oid(game, BEAR, 0)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert plus_ones(game, oid) == 2

    def test_my_counter_on_an_opponents_creature_is_doubled(self, builder):
        """"On a permanent" -- any permanent. Doubling Season would not."""
        game = position(builder, mine=[TALENT], theirs=[BEAR])
        oid = only_oid(game, BEAR, 1)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert plus_ones(game, oid) == 2

    def test_an_opponents_counter_on_my_creature_is_not(self, builder):
        """They are putting it, not you -- the boundary Doubling Season draws
        the other way."""
        game = position(builder, mine=[TALENT, BEAR])
        oid = only_oid(game, BEAR, 0)
        add_counters(game.state, oid, "+1/+1", 1, by=1)
        assert plus_ones(game, oid) == 1

    def test_the_putter_defaults_to_the_sources_controller(self, builder):
        game = position(builder, mine=[TALENT], theirs=[BEAR])
        mine = only_oid(game, TALENT, 0)
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "+1/+1", 1, source=mine)
        assert plus_ones(game, theirs) == 2
        add_counters(game.state, theirs, "+1/+1", 1, source=theirs)
        assert plus_ones(game, theirs) == 3

    def test_a_permanent_entering_under_my_control_is_doubled(self, builder):
        game = position(builder, mine=[TALENT], hand=[HYDRA])
        game.apply(action_for_card(game, ActionKind.CAST, HYDRA))
        pass_until(game, lambda g: not g.state.stack)
        assert plus_ones(game, only_oid(game, HYDRA, 0)) == 4

    def test_a_loyalty_cost_is_doubled(self, builder):
        """"If you would put" includes a cost -- no ``effects_only`` here."""
        game = position(builder, mine=[TALENT, WALKER])
        oid = only_oid(game, WALKER, 0)
        before = game.state.objects[oid].counter("loyalty")
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == oid
            )
        )
        assert game.state.objects[oid].counter("loyalty") == before + 2


class TestPlayersToo:
    def test_the_add_poison_op_is_doubled(self, builder):
        game = position(builder, mine=[TALENT], hand=[VENOM])
        game.apply(action_for_card(game, ActionKind.CAST, VENOM))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[1].poison == 4

    def test_infect_damage_from_my_creature_is_doubled(self, builder):
        game = position(builder, mine=[TALENT, INFECT])
        damage_player(game.state, 1, 2, only_oid(game, INFECT, 0))
        assert game.state.players[1].poison == 4

    def test_infect_damage_from_their_creature_is_not(self, builder):
        game = position(builder, mine=[TALENT], theirs=[INFECT])
        damage_player(game.state, 0, 2, only_oid(game, INFECT, 1))
        assert game.state.players[0].poison == 2

    def test_a_recipient_keyed_replacement_never_reaches_a_player(self, builder):
        """Doubling Season names "a permanent you control"; a player is not
        one."""
        game = position(builder, mine=[SEASON])
        add_poison(game.state, 1, 2, by=0)
        assert game.state.players[1].poison == 2

    def test_the_event_reports_what_arrived(self, builder):
        game = position(builder, mine=[TALENT])
        mark = len(game.state.events)
        add_poison(game.state, 1, 1, by=0)
        added = [e for e in game.state.events[mark:] if e.type == "poison_added"]
        assert [e.data["amount"] for e in added] == [2]


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "If you would put one or more counters…",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "If you would put one or more counters…",
                        **extra,
                    }
                ],
            }
        )

    def test_put_by_stands_in_for_affects(self):
        compiled = compile_card(
            self._card(
                effect="replace_counters",
                counter_multiplier=2,
                put_by="you",
                affects_player="any",
            )
        )
        static = compiled.abilities[0].static
        assert static["put_by"] == "you"
        assert static["affects_player"] == "any"

    def test_neither_put_by_nor_affects_is_refused(self):
        with pytest.raises(DslError, match="put_by"):
            compile_card(self._card(effect="replace_counters", counter_multiplier=2))

    def test_it_is_refused_on_another_static(self):
        with pytest.raises(DslError, match="put_by"):
            compile_card(
                self._card(
                    effect="replace_draw",
                    draw_multiplier=2,
                    affects_player="you",
                    put_by="you",
                )
            )
