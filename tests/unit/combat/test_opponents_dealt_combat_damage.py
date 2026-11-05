"""A combat-damage trigger keyed on the damaged side, once per batch.

    Mindblade Render — "Whenever your opponents are dealt combat damage, if any
    of that damage was dealt by a Warrior, you draw a card and you lose 1 life."

The rulings read it as one trigger per combat damage step: it fires once when
one or more of its controller's opponents are dealt combat damage, by anyone's
creatures, and only if at least one source of **that** damage -- damage dealt to
an opponent -- was a Warrior. 510.2 makes the step's combat damage one event,
and only attacking creatures, all the active player's (506.2, 506.4), deal
combat damage to players, so the step's player damage is one batch.

`creatures_deal_combat_damage` with `defending: "opponent"` and no
`per_player` is that reading: `triggers._defending_batch` narrows the batch to
the seats `defending` names and the creatures that hit them, then hears it once.
Each near miss is a different card:

- `controller: "you"` drops an opponent's Warrior hitting another opponent;
- no `defending` fires when an opponent's Warrior hits **you**;
- `per_player` draws twice when Warriors hit two opponents.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, pass_until

RENDER = "t_odc_render"
WARRIOR = "t_odc_warrior"  # 2/2 Human Warrior
ELF = "t_bcd_elf"  # 1/1 Elf, which the Warrior filter does not name


def pod(builder, *, active: int, attackers=()):
    """Three seats. Seat 0 controls the Render; ``active`` swings ``attackers``."""
    return (
        builder(players=3)
        .battlefield(0, [RENDER])
        .battlefield(active, ["swamp", *attackers])
        .hand(0, [])
        .library(0, ["swamp"] * 20)
        .library(active, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )


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


def drew(game, before: int) -> int:
    return len(game.state.players[0].hand) - before


class TestYourWarriors:
    def test_a_warrior_hitting_an_opponent_draws_and_drains_you(self, builder):
        game = pod(builder, active=0, attackers=[WARRIOR])
        before = len(game.state.players[0].hand)
        swing(game, {only_oid(game, WARRIOR, 0): 1})
        assert drew(game, before) == 1
        assert game.state.players[0].life == 40 - 1

    def test_two_opponents_hit_is_still_one_firing(self, builder):
        """"Your opponents are dealt": once for the step, not once per seat."""
        game = pod(builder, active=0, attackers=[WARRIOR, WARRIOR])
        first, second = oids_of(game, WARRIOR, 0)
        before = len(game.state.players[0].hand)
        swing(game, {first: 1, second: 2})
        assert drew(game, before) == 1
        assert game.state.players[0].life == 40 - 1

    def test_no_warrior_among_the_damagers_is_no_firing(self, builder):
        game = pod(builder, active=0, attackers=[ELF])
        before = len(game.state.players[0].hand)
        swing(game, {only_oid(game, ELF, 0): 1})
        assert drew(game, before) == 0
        assert game.state.players[0].life == 40


class TestAnOpponentsCombat:
    def test_an_opponents_warrior_hitting_another_opponent_fires_it(self, builder):
        """By anyone: seat 1's Warrior hitting seat 2 is your opponent dealt
        combat damage by a Warrior."""
        game = pod(builder, active=1, attackers=[WARRIOR])
        before = len(game.state.players[0].hand)
        swing(game, {only_oid(game, WARRIOR, 1): 2})
        assert drew(game, before) == 1
        assert game.state.players[0].life == 40 - 1

    def test_a_warrior_that_hit_you_does_not_count(self, builder):
        """Seat 1's Warrior hits you and its Elf hits seat 2: an opponent was
        dealt combat damage, but none of *that* damage was a Warrior's."""
        game = pod(builder, active=1, attackers=[WARRIOR, ELF])
        before = len(game.state.players[0].hand)
        swing(game, {only_oid(game, WARRIOR, 1): 0, only_oid(game, ELF, 1): 2})
        assert drew(game, before) == 0
        assert game.state.players[0].life == 40 - 2

    def test_only_you_being_hit_is_no_firing(self, builder):
        game = pod(builder, active=1, attackers=[WARRIOR])
        before = len(game.state.players[0].hand)
        swing(game, {only_oid(game, WARRIOR, 1): 0})
        assert drew(game, before) == 0
        assert game.state.players[0].life == 40 - 2


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
                            "effects": [
                                {"op": "draw", "player": "you", "amount": {"const": 1}}
                            ],
                        }
                    ],
                }
            )
        )

    def test_defending_on_the_whole_batch_is_accepted(self):
        assert self.compile(
            {"event": "creatures_deal_combat_damage", "controller": "any", "defending": "opponent"}
        )

    def test_defending_beside_or_battle_is_refused(self):
        """The narrowed batch carries no battles, so the battle half of the
        sentence would never fire."""
        with pytest.raises(DslError, match="or_battle"):
            self.compile(
                {
                    "event": "creatures_deal_combat_damage",
                    "defending": "opponent",
                    "or_battle": True,
                }
            )
