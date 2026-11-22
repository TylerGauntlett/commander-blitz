""""…if one or more permanents were sacrificed to activate it."

Ashnod the Uncaring is the witness: "Whenever you activate an ability of an
artifact or creature that isn't a mana ability, if one or more permanents were
sacrificed to activate it, you may copy that ability. (Sacrificing an artifact
for mana to activate an ability doesn't count.)" Rule 602.2b applies 601.2h to
abilities: the cost is paid as part of activating, so "sacrificed to activate
it" is a fact about the activation's own cost. The reminder text draws the line
the rules draw: a Treasure sacrificed for mana pays its own mana ability's cost
(605.3a), which is a different ability, so it is not counted.

Without the clause the trigger is every non-mana activation, which turns a
sacrifice-payoff into a payoff for pumping a creature with {G}.

`TriggerSpec.sacrificed_to_activate` reads the event's ``sacrificed`` count,
which `Game._activate` takes from `costs.cost_sacrifice_count` -- the ability's
``sacrifice``, list-form ``sacrifice`` and ``sacrifice_x`` (at the announced
X) -- and the loader allows it only beside ``mana_ability: false``.
`t_sta_watcher` stands in for Ashnod with the copy replaced by a life loss, so
whether it fired is visible on a total the fodder never touches.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, oids_of, only_oid, pt, settle

WATCHER = "t_sta_watcher"
UNSACRIFICED = "t_sta_unsacrificed"
#: {B}, {T}, Sacrifice another creature -- the plain ``sacrifice`` cost.
GISA = "t_gisa_outlet"
#: Sacrifice a Swamp and a Forest -- list-form ``sacrifice``.
JARAD = "t_sp_lands"
#: {1}, Sacrifice X Foods -- ``sacrifice_x``.
FRUGIVORE = "t_sx_engine"
FOOD = "food_token"
#: {G}: +1/+1 -- no sacrifice anywhere in the cost.
MUTATOR = "t_mutator"
TREASURE = "treasure_token"


def position(builder, mine, *, watcher=WATCHER):
    """The watcher and ``mine`` under player 0, in their main phase."""
    return (
        builder(players=2)
        .battlefield(0, [watcher, *mine])
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def activate(game, card_id, *, x=None):
    """Activate ``card_id``'s first ability, answer X if asked, and settle."""
    game.apply(activations(game, only_oid(game, card_id, 0))[0])
    if x is not None:
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == x
            )
        )
    settle(game)


def their_life(game) -> int:
    return game.state.players[1].life


class TestASacrificeCostCounts:
    def test_a_sacrifice_cost_fires_it(self, builder):
        game = position(builder, [GISA, "t_bear", "swamp"])
        activate(game, GISA)
        assert not oids_of(game, "t_bear", 0), "the bear paid the cost"
        assert their_life(game) == 37

    def test_list_form_sacrifice_fires_it(self, builder):
        game = position(builder, [JARAD, "swamp", "forest"])
        activate(game, JARAD)
        assert their_life(game) == 37

    def test_sacrifice_x_fires_it_once_however_many(self, builder):
        """"One or more" is a threshold, not a count: two Foods, one trigger."""
        game = position(builder, [FRUGIVORE, FOOD, FOOD, "swamp"])
        activate(game, FRUGIVORE, x=2)
        assert not oids_of(game, FOOD, 0)
        assert their_life(game) == 37


class TestNoSacrificeDoesNotCount:
    def test_an_ability_without_a_sacrifice_cost(self, builder):
        game = position(builder, [MUTATOR, "forest"])
        activate(game, MUTATOR)
        assert their_life(game) == 40

    def test_sacrifice_x_at_zero_sacrificed_nothing(self, builder):
        """X = 0 is a ``sacrifice_x`` cost that took no permanent."""
        game = position(builder, [FRUGIVORE, FOOD, "swamp"])
        activate(game, FRUGIVORE, x=0)
        assert len(oids_of(game, FOOD, 0)) == 1
        assert their_life(game) == 40

    def test_a_treasure_sacrificed_for_the_mana_does_not_count(self, builder):
        """The reminder text: the Treasure paid its own mana ability's cost
        (605.3a), and the {G} it made then paid the Mutator's. The Sac Outlet
        is an anchor -- without a non-mana offer the position auto-passes."""
        game = position(builder, [MUTATOR, TREASURE, "t_sac_outlet"])
        treasure = only_oid(game, TREASURE, 0)
        green = [
            a
            for a in game.legal_actions()
            if a.source == treasure and (a.label or "").endswith("({G})")
        ]
        assert green, "the Treasure's mana ability is offered by hand"
        game.apply(green[0])
        settle(game)
        assert not oids_of(game, TREASURE, 0), "the Treasure was sacrificed"
        assert their_life(game) == 40, "a mana ability is not watched"
        activate(game, MUTATOR)
        assert pt(game, only_oid(game, MUTATOR, 0)) == (5, 5), "the {G} paid for it"
        assert their_life(game) == 40


class TestTheOtherReading:
    def test_false_fires_only_without_a_sacrifice(self, builder):
        game = position(
            builder,
            [MUTATOR, GISA, "t_bear", "forest", "swamp"],
            watcher=UNSACRIFICED,
        )
        activate(game, MUTATOR)
        assert their_life(game) == 39
        activate(game, GISA)
        assert their_life(game) == 39


def probe(**trigger) -> dict:
    spec = {"event": "ability_activated", "controller": "you"}
    spec.update(trigger)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Whenever you activate an ability, ...",
        "mana_cost": "{1}{B}",
        "types": ["Creature"],
        "power": 2,
        "toughness": 2,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever you activate an ability, ...",
                "trigger": spec,
                "effects": [
                    {"op": "lose_life", "player": "each_opponent", "amount": {"const": 1}}
                ],
            }
        ],
    }


class TestTheLoader:
    def test_it_compiles_beside_mana_ability_false(self):
        card = compile_card(
            CardModel.model_validate(probe(mana_ability=False, sacrificed_to_activate=True))
        )
        assert card.abilities[0].trigger.sacrificed_to_activate is True

    def test_omitted_is_either_way(self):
        card = compile_card(CardModel.model_validate(probe(mana_ability=False)))
        assert card.abilities[0].trigger.sacrificed_to_activate is None

    def test_refused_without_mana_ability_false(self):
        """The mana path announces X after the event and the solver's taps fire
        nothing, so the count would be missing there."""
        with pytest.raises(DslError, match="sacrificed_to_activate"):
            compile_card(CardModel.model_validate(probe(sacrificed_to_activate=True)))

    def test_refused_on_another_event(self):
        payload = probe()
        payload["abilities"][0]["trigger"] = {
            "event": "spell_cast",
            "controller": "you",
            "mana_ability": False,
            "sacrificed_to_activate": True,
        }
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(payload))
