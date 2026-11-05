"""A discount for the first matching activation of your turn.

    "The first activated ability you activate during your turn that targets a
    creature you control costs {2} less to activate."
                                                    -- Professor Hojo

`ability_cost_reduction` could name only the equip class, and nothing on it
counted. This adds the two halves Hojo prints: ``affects_abilities: {"any":
true}`` reaches every activated ability, and ``first_during_your_turn`` limits
the discount to one activation -- the price is determined at 601.2f, so the
question is asked of each activation as it is priced.

**The count is of matching activations.** "The first activated ability … that
targets a creature you control" is one noun phrase: an activation aimed at an
opponent's creature, or at nothing, is not that ability and leaves the discount
for the next one that is. The Scryfall ruling reads it the same way -- the
discount goes to "the first activated ability you activate during your turn
that targets a creature" -- and its second half fixes the other boundary: the
{2} "will have no effect on an activation cost of {G}", so a {G} ability is
still the first and spends the turn's use.

**Every activation of the turn counts, including one made before Hojo
arrived**: "the first" is a fact about the activation, the reading the rulings
give Esper Sentinel's "the first noncreature spell". So the earlier ones are
asked of `TurnLedger.targeted_activations`, a snapshot `Game._activate` files
as each is paid -- the creature it targeted may since have died.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import ability_mana
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, only_oid, settle

HOJO = "t_fac_hojo"  # the first matching activation of your turn costs {2} less
ROD = "t_fac_green_rod"  # {G}: target creature can't be blocked
PASSAGE = "t_passage"  # {4}, {T}: target creature can't be blocked
BEAR = "t_bear"


def position(builder, *, mine=(HOJO,), theirs=(BEAR,), active=0, hand=()):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 8 + ["forest", PASSAGE, PASSAGE, BEAR, *mine])
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )


def aim(game, source_oid: int, target_oid: int):
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.ACTIVATE
            and action.source == source_oid
            and TargetRef.obj(target_oid) in action.targets
        ):
            return action
    return None


def price(game, source_oid: int, target_oid: int, pid: int = 0) -> int:
    """The generic half of what aiming ``source_oid`` at ``target_oid`` costs."""
    action = aim(game, source_oid, target_oid)
    assert action is not None, "the activation is not offered"
    ability = game.state.card_of(game.state.objects[source_oid]).abilities[-1]
    return ability_mana(
        game.state, pid, ability.cost, 0, source_oid, ability=ability, targets=action.targets
    ).generic


def activate(game, source_oid: int, target_oid: int) -> None:
    action = aim(game, source_oid, target_oid)
    assert action is not None, "the activation is not offered"
    game.apply(action)
    settle(game)


class TestTheFirstMatchingActivation:
    def test_it_costs_two_less(self, builder):
        game = position(builder)
        passage = oids_of(game, PASSAGE, 0)[0]
        assert price(game, passage, only_oid(game, BEAR, 0)) == 2

    def test_the_second_costs_full(self, builder):
        game = position(builder)
        first, second = oids_of(game, PASSAGE, 0)
        activate(game, first, only_oid(game, BEAR, 0))
        assert price(game, second, only_oid(game, HOJO, 0)) == 4

    def test_it_is_charged_at_the_discount(self, builder):
        """Two lands pay for a {4} ability, and only aimed where it is
        discounted -- the offer and the charge agree."""
        game = (
            builder(players=2)
            .battlefield(0, ["mountain", "mountain", PASSAGE, BEAR, HOJO])
            .battlefield(1, [BEAR])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        passage = only_oid(game, PASSAGE, 0)
        assert aim(game, passage, only_oid(game, BEAR, 1)) is None
        activate(game, passage, only_oid(game, BEAR, 0))
        assert all(game.state.objects[o].tapped for o in oids_of(game, "mountain", 0))
        assert game.state.objects[only_oid(game, BEAR, 0)].def_id == BEAR


class TestOnlyMatchingActivationsAreCounted:
    def test_an_ability_aimed_at_an_opponents_creature_is_not_discounted(self, builder):
        game = position(builder)
        passage = oids_of(game, PASSAGE, 0)[0]
        assert price(game, passage, only_oid(game, BEAR, 1)) == 4

    def test_nor_does_it_spend_the_use(self, builder):
        """"The first … that targets a creature you control": an activation that
        is not that ability leaves the discount for the next one that is."""
        game = position(builder)
        first, second = oids_of(game, PASSAGE, 0)
        activate(game, first, only_oid(game, BEAR, 1))
        assert price(game, second, only_oid(game, BEAR, 0)) == 2

    def test_a_coloured_cost_still_spends_it(self, builder):
        """The ruling: the {2} "will have no effect on an activation cost of
        {G}" -- and that activation was still the first."""
        game = position(builder, mine=(HOJO, ROD))
        activate(game, only_oid(game, ROD, 0), only_oid(game, BEAR, 0))
        passage = oids_of(game, PASSAGE, 0)[0]
        assert price(game, passage, only_oid(game, BEAR, 0)) == 4

    def test_an_activation_before_it_arrived_counts(self, builder):
        """"The first" is a fact about the activation, not about Hojo."""
        game = position(builder, mine=(), hand=(HOJO,))
        first, second = oids_of(game, PASSAGE, 0)
        activate(game, first, only_oid(game, BEAR, 0))
        (in_hand,) = game.state.players[0].hand
        move_object(game.state, in_hand, Zone.BATTLEFIELD)
        settle(game)
        assert price(game, second, only_oid(game, HOJO, 0)) == 4

    def test_without_one_it_would_be_discounted(self, builder):
        """The control for the test above: the same arrival, nothing activated
        first."""
        game = position(builder, mine=(), hand=(HOJO,))
        (in_hand,) = game.state.players[0].hand
        move_object(game.state, in_hand, Zone.BATTLEFIELD)
        settle(game)
        passage = oids_of(game, PASSAGE, 0)[0]
        assert price(game, passage, only_oid(game, HOJO, 0)) == 2

    def test_the_target_leaving_does_not_unmake_it(self, builder):
        """Matched on the snapshot filed at the activation: the Bear it aimed
        at has died since, and it was still the first."""
        game = position(builder)
        first, second = oids_of(game, PASSAGE, 0)
        activate(game, first, only_oid(game, BEAR, 0))
        move_object(game.state, only_oid(game, BEAR, 0), Zone.GRAVEYARD)
        assert price(game, second, only_oid(game, HOJO, 0)) == 4


class TestDuringYourTurn:
    def test_not_on_an_opponents_turn(self, builder):
        game = position(builder, active=1)
        passage = oids_of(game, PASSAGE, 0)[0]
        ability = game.state.card_of(game.state.objects[passage]).abilities[-1]
        target = (TargetRef.obj(only_oid(game, BEAR, 0)),)
        assert (
            ability_mana(
                game.state, 0, ability.cost, 0, passage, ability=ability, targets=target
            ).generic
            == 4
        )

    def test_the_next_turn_rearms_it(self, builder):
        """The ledger is the turn's; cleanup clears it."""
        game = position(builder)
        first, second = oids_of(game, PASSAGE, 0)
        activate(game, first, only_oid(game, BEAR, 0))
        game.state.turn_ledger.clear()
        assert price(game, second, only_oid(game, HOJO, 0)) == 2

    def test_an_opponents_activation_is_not_yours(self, builder):
        """"…you activate": their activation is neither discounted by your
        Hojo nor counted against it."""
        game = position(builder, theirs=(BEAR, PASSAGE))
        theirs = only_oid(game, PASSAGE, 1)
        ability = game.state.card_of(game.state.objects[theirs]).abilities[-1]
        target = (TargetRef.obj(only_oid(game, BEAR, 1)),)
        assert (
            ability_mana(
                game.state, 1, ability.cost, 0, theirs, ability=ability, targets=target
            ).generic
            == 4
        )
        game.state.turn_ledger.targeted_activations.setdefault(1, []).append(
            (False, ((1, frozenset({"Creature"}), frozenset({"Bear"})),))
        )
        mine = oids_of(game, PASSAGE, 0)[0]
        assert price(game, mine, only_oid(game, BEAR, 0)) == 2


class TestTheLoaderPlacesIt:
    TEXT = (
        "The first activated ability you activate during your turn that targets "
        "a creature you control costs {2} less to activate."
    )

    def _card(self, ability):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": self.TEXT,
                "mana_cost": "{B}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [ability],
            }
        )

    def _static(self, **extra):
        base = {
            "kind": "static",
            "text": self.TEXT,
            "effect": "ability_cost_reduction",
            "affects_abilities": {"any": True},
            "targeting": {"controller": "you", "types": ["Creature"]},
            "first_during_your_turn": True,
            "amount": {"const": 2},
        }
        base.update(extra)
        return base

    def test_a_well_formed_static_loads(self):
        compile_card(self._card(self._static()))

    def test_any_class_without_targeting_is_refused(self):
        """A mana ability is priced where this static is never read, so "every
        activated ability" unqualified would quietly skip them."""
        with pytest.raises(DslError, match="'any' needs a 'targeting' clause"):
            compile_card(
                self._card(self._static(targeting=None, first_during_your_turn=False))
            )

    def test_first_without_targeting_is_refused(self):
        with pytest.raises(DslError, match="needs 'targeting'"):
            compile_card(
                self._card(self._static(affects_abilities={"equip": True}, targeting=None))
            )

    def test_first_for_an_opponents_activation_is_refused(self):
        with pytest.raises(DslError, match="'activated_by' must be 'you'"):
            compile_card(self._card(self._static(activated_by="opponent")))

    def test_a_key_the_snapshot_does_not_keep_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                self._card(self._static(targeting={"controller": "you", "tapped": True}))
            )

    def test_it_is_refused_on_another_static(self):
        with pytest.raises(DslError, match="'first_during_your_turn' only means"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creatures you control get +1/+1.",
                        "effect": "buff",
                        "affects": {"controller": "you"},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "first_during_your_turn": True,
                    }
                )
            )
