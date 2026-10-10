"""`look_at_top` destinations with a per-step ``selector`` and ``up_to``.

Kiora, Master of the Depths' -2 is the witness: "Reveal the top four cards of
your library. You may put a creature card **and/or** a land card from among
them into your hand. Put the rest into your graveyard."

The near miss is one pick of count 2 over Creature-or-Land, and it is a
different card: it lets the player take two creatures, or two lands. The other
near miss, a count-1 step with no floor relaxed, forces a pick the card says
"may". So the claims are that each step offers only its own type, takes at
most one, may take none, never takes the same card twice (a creature land
answers one step, not both), and that everything not taken -- including cards
neither step could take -- goes to the graveyard.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card

BEAR = "t_bear"
RING = "sol_ring"
ARBOR = "dryad_arbor"
DIG = "t_depths_dig"
SPEC = {
    "op": "look_at_top",
    "amount": 4,
    "destinations": [
        {"to": "hand", "count": 1, "up_to": True, "selector": {"types": ["Creature"]}},
        {"to": "hand", "count": 1, "up_to": True, "selector": {"types": ["Land"]}},
    ],
    "rest_to": "graveyard",
}


def a_library(builder, top):
    game = (
        builder(players=2)
        .library(0, [*top, "island", "island"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, list(game.state.players[0].library[: len(top)])


def dig(game, pick=lambda decision: [0]):
    """Run the op; ``pick`` answers each step (indices into its options)."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [SPEC])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(pick(decision))
    except StopIteration:
        pass
    return asked


def def_ids(decision, game) -> list[str]:
    return [game.state.objects[o.value].def_id for o in decision.options]


def zone(game, oid) -> Zone:
    return game.state.objects[oid].zone


class TestEachStepOffersItsOwnType:
    def test_the_creature_step_then_the_land_step(self, builder):
        game, _top = a_library(builder, [BEAR, "forest", RING, BEAR])
        asked = dig(game)
        assert [def_ids(d, game) for d in asked] == [[BEAR, BEAR], ["forest"]]
        assert all(d.kind is DecisionKind.CHOOSE_OBJECTS for d in asked)
        assert all((d.min_count, d.max_count) == (0, 1) for d in asked)

    def test_one_creature_and_one_land_reach_the_hand(self, builder):
        game, (bear, forest, _ring, bear2) = a_library(builder, [BEAR, "forest", RING, BEAR])
        dig(game)
        assert zone(game, bear) is Zone.HAND
        assert zone(game, forest) is Zone.HAND
        assert zone(game, bear2) is Zone.GRAVEYARD, "never a second creature"

    def test_two_lands_are_never_both_taken(self, builder):
        game, top = a_library(builder, ["forest", "forest", RING, RING])
        asked = dig(game)
        assert len(asked) == 1, "no creature step with no creature to offer"
        assert [zone(game, o) for o in top].count(Zone.HAND) == 1


class TestItIsOptional:
    def test_both_steps_may_be_declined(self, builder):
        game, top = a_library(builder, [BEAR, "forest", RING, RING])
        dig(game, pick=lambda d: [])
        assert all(zone(game, o) is Zone.GRAVEYARD for o in top)

    def test_taking_only_the_land(self, builder):
        game, (bear, forest, *_rest) = a_library(builder, [BEAR, "forest", RING, RING])
        dig(game, pick=lambda d: [] if def_ids(d, game)[0] == BEAR else [0])
        assert zone(game, bear) is Zone.GRAVEYARD
        assert zone(game, forest) is Zone.HAND


class TestACreatureLandAnswersOneStep:
    def test_taken_as_the_creature_it_is_not_offered_as_the_land(self, builder):
        game, (arbor, forest, *_rest) = a_library(builder, [ARBOR, "forest", RING, RING])
        asked = dig(game)
        assert def_ids(asked[0], game) == [ARBOR]
        assert def_ids(asked[1], game) == ["forest"]
        assert zone(game, arbor) is Zone.HAND and zone(game, forest) is Zone.HAND

    def test_passed_over_as_the_creature_it_can_be_the_land(self, builder):
        game, (arbor, forest, *_rest) = a_library(builder, [ARBOR, "forest", RING, RING])
        dig(game, pick=lambda d: [] if len(d.options) == 1 else [0])
        assert zone(game, arbor) is Zone.HAND
        assert zone(game, forest) is Zone.GRAVEYARD


class TestTheRest:
    def test_everything_not_taken_goes_to_the_graveyard_and_no_deeper(self, builder):
        game, (_bear, _forest, ring, ring2) = a_library(builder, [BEAR, "forest", RING, RING])
        dig(game)
        assert zone(game, ring) is Zone.GRAVEYARD and zone(game, ring2) is Zone.GRAVEYARD
        assert len(game.state.players[0].library) == 2, "only four cards were revealed"

    def test_the_spell_resolves_end_to_end(self, builder):
        game = (
            builder(players=2)
            .hand(0, [DIG])
            .battlefield(0, ["island"])
            .library(0, [BEAR, "forest", RING, RING, "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, DIG))
        for _ in range(50):
            decision = game.pending()
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
                continue
            if not game.state.stack:
                break
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        hand = [game.state.objects[o].def_id for o in game.state.players[0].hand]
        assert BEAR in hand and "forest" in hand
        grave = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert grave.count(RING) == 2


class TestTheLoader:
    def card(self, step):
        return {
            "id": "t_bad_dig",
            "name": "Test Bad Dig",
            "oracle_text": "Dig.",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "look_at_top", "amount": 4, "destinations": [step]}],
        }

    def test_an_unknown_step_key_is_refused(self):
        with pytest.raises(DslError, match="unknown keys"):
            compile_card(CardModel.model_validate(self.card({"to": "hand", "filter": {}})))

    def test_up_to_is_a_boolean(self):
        with pytest.raises(DslError, match="'up_to' is a boolean"):
            compile_card(CardModel.model_validate(self.card({"to": "hand", "up_to": 1})))

    def test_an_unknown_destination_is_refused(self):
        with pytest.raises(DslError, match="unknown destination"):
            compile_card(CardModel.model_validate(self.card({"to": "sideboard"})))

    def test_the_step_selector_is_validated(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(self.card({"to": "hand", "selector": {"typez": ["Land"]}}))
            )
