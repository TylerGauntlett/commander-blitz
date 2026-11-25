"""Up to one card of each card type: a choice constrained as a *set*.

Grime Gorger: "Whenever this creature attacks, exile up to one card of each
card type from defending player's graveyard. Put a +1/+1 counter on this
creature for each card exiled this way." The constraint is on the chosen set,
not on any one card, so no per-candidate selector clause can state it.

A multi-typed card is *one* card of *one* type, at the chooser's assignment: an
artifact creature beside a creature card is legal (it is the artifact), and an
artifact creature beside an artifact card and a creature card is not -- three
cards with two card types between them (rule 300.1 lists the card types; the
sentence asks for at most one card per type). So the set is legal iff there is
an injective assignment of chosen cards to card types each card has, a
bipartite matching. Both simpler readings are wrong in opposite directions:

- "no type seen twice" refuses the legal artifact creature + creature pair,
  making the card weaker;
- one `for_each` over the card types, exiling one card per type, accepts the
  artifact creature as the artifact and a second creature card as the creature
  *and* an artifact card -- three cards for two types -- making it stronger.

`one_of_each_card_type: true` beside `count: "any"` stages the choice one card at
a time (`selectors._pick_one_of_each_card_type`), each stage offering only the
cards that keep the set assignable (`selectors.card_types_assignable`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import (
    card_types_assignable,
    choose_objects,
    validate_selector,
)
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until, plus_one_counters, settle

GORGER = "t_ooe_gorger"
ARTIFACT_CREATURE = "t_artifact_blocker"
ARTIFACT = "sol_ring"
CREATURE = "t_bear"
INSTANT = "t_bolt"
LAND = "forest"

SELECTOR = {"zone": "graveyard", "player": "each_opponent", "count": "any",
            "one_of_each_card_type": True}


def position(builder, graveyard):
    """Player 1's ``graveyard``, player 0 choosing among it. ``(game, by_id)``.

    ``by_id`` maps each card id to its oids in the graveyard, in order.
    """
    game = builder(players=2).graveyard(1, list(graveyard)).build()
    by_id: dict[str, list[int]] = {}
    for oid in game.state.players[1].graveyard:
        by_id.setdefault(game.state.objects[oid].def_id, []).append(oid)
    return game, by_id


class Chooser:
    """Drives `choose_objects` stage by stage, by oid."""

    def __init__(self, game, selector=SELECTOR):
        ctx = EffectContext(state=game.state, controller=0)
        self.gen = choose_objects(ctx, selector, "Exile", "exile")
        self.result: list[int] | None = None
        self.decision = self._step(None)

    def _step(self, answer):
        try:
            return self.gen.send(answer) if answer is not None else next(self.gen)
        except StopIteration as stop:
            self.result = list(stop.value)
            return None

    def offered(self) -> set[int]:
        assert self.decision is not None, "the choice already ended"
        return {o.value for o in self.decision.options}

    def take(self, oid: int) -> None:
        index = next(i for i, o in enumerate(self.decision.options) if o.value == oid)
        self.decision = self._step([index])

    def decline(self) -> None:
        self.decision = self._step([])


class TestTheMatching:
    """`card_types_assignable` alone: the rules argument as set arithmetic."""

    @pytest.mark.parametrize(
        ("type_sets", "legal"),
        [
            ([], True),
            ([{"Creature"}], True),
            ([{"Creature"}, {"Creature"}], False),
            ([{"Artifact", "Creature"}, {"Creature"}], True),
            ([{"Artifact", "Creature"}, {"Artifact"}], True),
            ([{"Artifact", "Creature"}, {"Artifact", "Creature"}], True),
            ([{"Artifact", "Creature"}, {"Artifact"}, {"Creature"}], False),
            ([{"Artifact", "Creature"}, {"Artifact", "Creature"}, {"Creature"}], False),
            ([{"Creature"}, {"Artifact", "Creature"}, {"Artifact", "Land"}], True),
            ([set()], False),
        ],
    )
    def test_legal_iff_cards_take_distinct_types(self, type_sets, legal):
        assert card_types_assignable(type_sets) is legal

    def test_a_later_card_can_move_an_earlier_one(self):
        """The augmenting path: the artifact creature was tentatively the
        creature, and a creature card arriving moves it to artifact."""
        assert card_types_assignable([{"Artifact", "Creature"}, {"Land"}, {"Creature"}])


class TestTheStagedChoice:
    def test_the_first_stage_offers_the_whole_graveyard_up_to_one(self, builder):
        game, _ = position(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        chooser = Chooser(game)
        assert chooser.decision.player == 0
        assert (chooser.decision.min_count, chooser.decision.max_count) == (0, 1)
        assert chooser.offered() == set(game.state.players[1].graveyard)

    def test_an_artifact_creature_leaves_both_its_types_open_to_one_more(self, builder):
        game, ids = position(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        chooser = Chooser(game)
        chooser.take(ids[ARTIFACT_CREATURE][0])
        assert chooser.offered() == {ids[ARTIFACT][0], ids[CREATURE][0], ids[INSTANT][0]}

    def test_after_artifact_creature_and_artifact_no_creature_fits(self, builder):
        """The boundary: the artifact creature is now the creature."""
        game, ids = position(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        chooser = Chooser(game)
        chooser.take(ids[ARTIFACT_CREATURE][0])
        chooser.take(ids[ARTIFACT][0])
        assert chooser.offered() == {ids[INSTANT][0]}

    def test_the_order_of_the_picks_does_not_matter(self, builder):
        """Creature first, then the artifact creature: it takes the artifact
        slot, and a plain artifact no longer fits."""
        game, ids = position(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        chooser = Chooser(game)
        chooser.take(ids[CREATURE][0])
        assert ids[ARTIFACT_CREATURE][0] in chooser.offered()
        chooser.take(ids[ARTIFACT_CREATURE][0])
        assert chooser.offered() == {ids[INSTANT][0]}

    def test_two_cards_of_one_type_are_never_both_taken(self, builder):
        game, ids = position(builder, [CREATURE, CREATURE, LAND])
        chooser = Chooser(game)
        chooser.take(ids[CREATURE][0])
        assert chooser.offered() == {ids[LAND][0]}

    def test_it_ends_when_nothing_else_fits(self, builder):
        game, ids = position(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        chooser = Chooser(game)
        for oid in (ids[ARTIFACT_CREATURE][0], ids[ARTIFACT][0], ids[INSTANT][0]):
            chooser.take(oid)
        assert chooser.decision is None
        assert sorted(chooser.result) == sorted(
            [ids[ARTIFACT_CREATURE][0], ids[ARTIFACT][0], ids[INSTANT][0]]
        )

    def test_declining_ends_it_at_any_size(self, builder):
        game, ids = position(builder, [CREATURE, LAND])
        chooser = Chooser(game)
        chooser.take(ids[LAND][0])
        chooser.decline()
        assert chooser.result == [ids[LAND][0]]

    def test_declining_at_once_takes_nothing(self, builder):
        game, _ = position(builder, [CREATURE])
        chooser = Chooser(game)
        assert chooser.decision is not None, "up to one: a lone card is still a choice"
        chooser.decline()
        assert chooser.result == []

    def test_an_empty_graveyard_asks_nothing(self, builder):
        game, _ = position(builder, [])
        chooser = Chooser(game)
        assert chooser.decision is None
        assert chooser.result == []


class TestTheLoadTimeRefusals:
    @pytest.mark.parametrize(
        "extra",
        [
            {"count": "all"},
            {"count": 2},
            {"count": {"const": 3}},
            {"one_of_each_card_type": "yes"},
        ],
    )
    def test_it_needs_a_free_choice(self, extra):
        with pytest.raises(DslError, match="one_of_each_card_type"):
            validate_selector({**SELECTOR, **extra}, "test")

    @pytest.mark.parametrize("extra", [{"random": True}, {"chooser": "none"}])
    def test_it_cannot_resolve_without_a_chooser(self, extra):
        """`count: "any"` refuses both already, so the staging is never skipped."""
        with pytest.raises(DslError, match="count 'any'"):
            validate_selector({**SELECTOR, **extra}, "test")

    def test_the_plain_form_loads(self):
        validate_selector(SELECTOR, "test")

    def test_a_declared_target_refuses_it(self):
        card = {
            "id": "t_ooe_bad", "name": "Bad", "oracle_text": "", "types": ["Creature"],
            "mana_cost": "{B}", "power": 1, "toughness": 1,
            "abilities": [{
                "kind": "triggered", "text": "",
                "trigger": {"event": "attacks", "source": "self"},
                "targets": [{"id": "t1", "kind": "card_in_graveyard", "count": 1,
                             "selector": {"zone": "graveyard",
                                          "one_of_each_card_type": True,
                                          "count": "any"}}],
                "effects": [{"op": "exile", "objects": {"target": "t1"}}],
            }],
        }
        with pytest.raises(DslError, match="declared target"):
            compile_card(CardModel.model_validate(card))


class TestGrimeGorger:
    """The witness end to end: the attack trigger, the exile and the counters."""

    def attack(self, builder, graveyard):
        game = (
            builder(players=2)
            .battlefield(0, [GORGER])
            .graveyard(1, list(graveyard))
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .active(0)
            .step(Step.UNTAP)
            .build()
        )
        gorger = only_oid(game, GORGER, 0)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=gorger, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS,
        )
        return game, gorger

    def pick(self, game, card_id):
        decision = game.pending()
        index = next(
            i for i, o in enumerate(decision.options)
            if game.state.objects[o.value].def_id == card_id
        )
        game.apply(
            next(
                a for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )
        if game.pending() is decision:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))

    def test_three_types_three_counters_and_the_creature_stays(self, builder):
        game, gorger = self.attack(builder, [ARTIFACT_CREATURE, ARTIFACT, CREATURE, INSTANT])
        assert game.pending().player == 0
        self.pick(game, ARTIFACT_CREATURE)
        self.pick(game, ARTIFACT)
        offered = {game.state.objects[o.value].def_id for o in game.pending().options}
        assert offered == {INSTANT}, "the artifact creature is the creature now"
        self.pick(game, INSTANT)
        settle(game)
        left = [game.state.objects[o].def_id for o in game.state.players[1].graveyard]
        assert left == [CREATURE]
        assert plus_one_counters(game, gorger) == 3
        exiled = [o for o in game.state.objects.values()
                  if o.zone is Zone.EXILE and o.owner == 1]
        assert len(exiled) == 3
