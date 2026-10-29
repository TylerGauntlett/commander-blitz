"""The `goaded` filter key, on the batched combat-damage trigger.

    Puppet Master, String Puller — "Whenever you attack, goad target creature
    an opponent controls. It can't block this turn. … Whenever one or more
    goaded creatures deal combat damage to one of your opponents, create a
    Treasure token."

`goaded: true` matches a creature somebody has goaded right now (701.38), read
off `GameObject.goaded_by`; the printed word names no goader, so anybody's goad
counts. The payoff is

    {"event": "creatures_deal_combat_damage", "controller": "any",
     "per_player": true, "defending": "opponent", "filter": {"goaded": true}}

and each of its parts is pinned here against the near miss it rules out:

- `controller: "any"`, because the goaded creatures are nearly always an
  opponent's, and the schema's default `"you"` would never fire;
- `per_player` with `defending: "opponent"`: one Treasure per opponent dealt
  damage, none for damage to the trigger's controller;
- the filter is asked of the creatures that hit *that* seat, so a goaded
  creature's hit on you does not make an ungoaded creature's hit on an
  opponent count.

The first ability needs nothing new (`you_attack`, `goad`, `cant_block`); it is
pinned at the bottom so the card's other half is known to be expressible.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import goad_creature
from tests.conftest import oids_of, only_oid, pass_until

PAYOFF = "t_gdf_payoff"
PUPPETEER = "t_gdf_puppeteer"
WYRM = "t_bcd_wyrm"  # 2/2
ELF = "t_bcd_elf"  # 1/1
TREASURE = "treasure_token"


def table(builder, *, active: int, mine=(), attackers=()):
    """Four seats. We (0) hold the payoff; ``active`` swings with ``attackers``."""
    b = builder(players=4)
    for pid in range(4):
        cards = list(attackers) if pid == active else []
        if pid == 0:
            cards = [PAYOFF, *mine, *cards]
        b = b.battlefield(pid, cards).library(pid, ["swamp"] * 20)
    return b.step(Step.PRECOMBAT_MAIN).active(active).build()


def swing(game, plan: dict[int, int]) -> None:
    """Declare each attacker (oid) at its seat, then run past combat damage."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    for attacker, seat in plan.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == attacker
                and any(ref.kind == "player" and ref.id == seat for ref in a.targets)
            )
        )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def treasures(game) -> int:
    return len(oids_of(game, TREASURE, 0))


def goad(game, oid: int, by: int) -> None:
    assert goad_creature(game.state, oid, by)


class TestAnyGoadedCreature:
    def test_an_opponents_goaded_creature_hitting_an_opponent_pays(self, builder):
        """The printed case: seat 1's creature, goaded by us, swings at seat 2."""
        game = table(builder, active=1, attackers=[WYRM])
        wyrm = only_oid(game, WYRM, 1)
        goad(game, wyrm, 0)
        swing(game, {wyrm: 2})
        assert game.state.players[2].life == 40 - 2
        assert treasures(game) == 1

    def test_an_ungoaded_creature_pays_nothing(self, builder):
        game = table(builder, active=1, attackers=[WYRM])
        swing(game, {only_oid(game, WYRM, 1): 2})
        assert game.state.players[2].life == 40 - 2
        assert treasures(game) == 0

    def test_somebody_elses_goad_counts(self, builder):
        """"Goaded creatures" names no goader: seat 3's goad is as good as ours."""
        game = table(builder, active=1, attackers=[WYRM])
        wyrm = only_oid(game, WYRM, 1)
        goad(game, wyrm, 3)
        swing(game, {wyrm: 2})
        assert treasures(game) == 1

    def test_our_own_creature_goaded_by_an_opponent_counts(self, builder):
        """Whoever controls it: the filter is about the goad, and
        `controller: "any"` lets our own batch through as well."""
        game = table(builder, active=0, attackers=[WYRM])
        wyrm = only_oid(game, WYRM, 0)
        goad(game, wyrm, 1)
        swing(game, {wyrm: 2})
        assert treasures(game) == 1


class TestOneOfYourOpponents:
    def test_damage_to_us_pays_nothing(self, builder):
        """Goaded by seat 2, so free to swing at us; we are not our opponent."""
        game = table(builder, active=1, attackers=[WYRM])
        wyrm = only_oid(game, WYRM, 1)
        goad(game, wyrm, 2)
        swing(game, {wyrm: 0})
        assert game.state.players[0].life == 40 - 2
        assert treasures(game) == 0

    def test_two_opponents_hit_is_two_treasures(self, builder):
        """Once per opponent dealt damage, the per-seat reading."""
        game = table(builder, active=1, attackers=[WYRM, WYRM])
        first, second = oids_of(game, WYRM, 1)
        goad(game, first, 0)
        goad(game, second, 0)
        swing(game, {first: 2, second: 3})
        assert treasures(game) == 2

    def test_two_goaded_creatures_at_one_seat_are_one_treasure(self, builder):
        """"One or more": two connections with the same seat are one firing."""
        game = table(builder, active=1, attackers=[WYRM, WYRM])
        first, second = oids_of(game, WYRM, 1)
        goad(game, first, 0)
        goad(game, second, 0)
        swing(game, {first: 2, second: 2})
        assert treasures(game) == 1

    def test_the_goaded_creature_must_be_the_one_that_hit_the_opponent(self, builder):
        """A goaded Wyrm through to us and an ungoaded Elf through to seat 2:
        the seat-2 firing asks only about the Elf, and the Wyrm's firing is
        about us. Nothing pays."""
        game = table(builder, active=1, attackers=[WYRM, ELF])
        wyrm = only_oid(game, WYRM, 1)
        goad(game, wyrm, 3)
        swing(game, {wyrm: 0, only_oid(game, ELF, 1): 2})
        assert game.state.players[0].life == 40 - 2
        assert game.state.players[2].life == 40 - 1
        assert treasures(game) == 0


class TestTheLoader:
    def compile(self, trigger: dict):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "x",
                    "name": "X",
                    "types": ["Enchantment"],
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "…",
                            "trigger": trigger,
                            "effects": [{"op": "create_token", "token": TREASURE}],
                        }
                    ],
                }
            )
        )

    def test_the_payoff_shape_loads(self):
        assert self.compile(
            {
                "event": "creatures_deal_combat_damage",
                "controller": "any",
                "per_player": True,
                "defending": "opponent",
                "filter": {"goaded": True},
            }
        )

    @pytest.mark.parametrize("word", ["you", "opponent", 1])
    def test_a_goader_word_is_refused(self, word):
        """`bool("you")` is true, so a word would quietly mean "by anyone"."""
        with pytest.raises(DslError, match="goaded"):
            self.compile(
                {"event": "creatures_deal_combat_damage", "filter": {"goaded": word}}
            )


class TestTheSelector:
    def test_goaded_narrows_an_effect_side_pool(self, builder):
        """The same key on the effect side: `goaded: true` and `false` split
        the battlefield's creatures by `goaded_by`."""
        game = table(builder, active=1, attackers=[WYRM, ELF])
        wyrm = only_oid(game, WYRM, 1)
        elf = only_oid(game, ELF, 1)
        goad(game, wyrm, 2)
        ctx = EffectContext(game.state, controller=0, source_oid=only_oid(game, PAYOFF, 0))
        base = {"zone": "battlefield", "types": ["Creature"]}
        assert resolve_pool(ctx, {**base, "goaded": True}) == [wyrm]
        assert resolve_pool(ctx, {**base, "goaded": False}) == [elf]


class TestTheFirstAbility:
    def test_whenever_you_attack_goad_and_cant_block(self, builder):
        """Already expressible: `you_attack`, then `goad` and `cant_block`
        on the same target."""
        game = (
            builder(players=2)
            .battlefield(0, [PUPPETEER, WYRM])
            .battlefield(1, [ELF])
            .library(0, ["swamp"] * 20)
            .library(1, ["swamp"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        elf = only_oid(game, ELF, 1)
        pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == only_oid(game, WYRM, 0)
            )
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        pass_until(game, lambda g: g.state.step is Step.DECLARE_BLOCKERS)
        assert game.state.objects[elf].goaded_by == {0}
        assert not any(
            a.kind is ActionKind.ADD_BLOCKER and a.source == elf for a in game.legal_actions()
        )
