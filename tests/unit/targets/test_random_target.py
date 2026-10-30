"""A target chosen at random -- still a target, chosen by nobody.

    Power Pack -- "Whenever Power Pack deals combat damage to a player, exile
    target instant or sorcery card from your graveyard chosen at random."

115.1 and 603.3d: the target is chosen as the trigger goes on the stack, and
re-checked on resolution (608.2b); with no legal candidate the trigger is not
put on the stack with one. "Chosen at random" changes only the chooser. The
near miss is an untargeted `exile` with `random` in its `objects`, which picks
on resolution, never fizzles when the card leaves the graveyard in response,
and is not a target for anything that cares. And without this the selector's
`random` on a target spec was read by nobody, so the controller chose -- a
strictly better card.

`stack._random_trigger_targets` draws uniformly off the seeded `state.rng`
among the candidates `enumerate_target_tuples` offers, so a replay draws the
same card. The loader allows it only as a triggered ability's one fixed-size
spec.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_triggered_ability
from commanderblitz.engine.structs import TriggerInstance
from tests.conftest import only_oid

DIGGER = "t_rt_digger"
SPELLS = ["t_draw_spell", "t_bolt", "t_draw_spell", "t_bolt"]


def board(builder, graveyard=tuple(SPELLS), seed: int = 0):
    return (
        builder(players=2, seed=seed)
        .battlefield(0, [DIGGER])
        .graveyard(0, [*graveyard, "t_bear"])
        .build(advance=False)
    )


def fire(game):
    """Put the Digger's trigger on the stack; a random target asks nothing."""
    trig = TriggerInstance(source_oid=only_oid(game, DIGGER, 0), ability_index=0, controller=0)
    for decision in push_triggered_ability(game.state, trig):
        raise AssertionError(f"a random target asked {decision.prompt!r}")
    return game.state.stack[-1]


class TestTheDraw:
    def test_one_legal_card_is_targeted(self, builder):
        game = board(builder)
        item = fire(game)

        assert len(item.targets) == 1
        target = game.state.objects[item.targets[0].id]
        assert target.def_id in SPELLS  # never the creature card

    def test_different_seeds_draw_different_cards(self, builder):
        picked = {
            fire(board(builder, seed=seed)).targets[0].id for seed in range(12)
        }
        assert len(picked) > 1, "the same card every time is a choice, not a draw"

    def test_the_same_seed_draws_the_same_card(self, builder):
        assert fire(board(builder, seed=3)).targets == fire(board(builder, seed=3)).targets

    def test_no_legal_card_no_target(self, builder):
        game = board(builder, graveyard=())
        assert fire(game).targets == ()


class TestTheLoader:
    def _card(self, *, kind="triggered", target=None, extra_targets=()) -> CardModel:
        spec = target or {
            "id": "t1",
            "kind": "card_in_graveyard",
            "count": 1,
            "selector": {"owner": "you", "zone": "graveyard", "random": True},
        }
        ability = {
            "kind": kind,
            "text": "x",
            "targets": [spec, *extra_targets],
            "effects": [{"op": "exile", "objects": {"target": "t1"}}],
        }
        if kind == "triggered":
            ability["trigger"] = {"event": "upkeep", "controller": "you"}
        else:
            ability["cost"] = {"tap": True}
        return CardModel.model_validate(
            {
                "id": "t_rt_probe",
                "name": "Random Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [ability],
            }
        )

    def test_it_loads_on_a_trigger(self):
        compile_card(self._card())

    def test_an_activated_ability_is_refused(self):
        with pytest.raises(DslError, match="random"):
            compile_card(self._card(kind="activated"))

    def test_a_spell_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "t_rt_spell",
                "name": "Random Spell",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "targets": [
                    {
                        "id": "t1",
                        "kind": "card_in_graveyard",
                        "selector": {"zone": "graveyard", "random": True},
                    }
                ],
                "spell_effects": [{"op": "exile", "objects": {"target": "t1"}}],
            }
        )
        with pytest.raises(DslError, match="random"):
            compile_card(model)

    def test_optional_is_refused(self):
        with pytest.raises(DslError, match="random"):
            compile_card(
                self._card(
                    target={
                        "id": "t1",
                        "kind": "card_in_graveyard",
                        "optional": True,
                        "selector": {"zone": "graveyard", "random": True},
                    }
                )
            )

    def test_a_sibling_target_is_refused(self):
        with pytest.raises(DslError, match="random"):
            compile_card(
                self._card(extra_targets=[{"id": "p1", "kind": "player"}])
            )
