"""A triggered ability riding the mana it is printed beside.

    "{1}, {T}: Add one mana of any color. **When you spend this mana to cast
    your commander, scry X, where X is the number of times it's been cast from
    the command zone this game.**"                          -- Study Hall

Rule 106.6: a mana ability may "create a delayed triggered ability (see rule
603.7a) that triggers when that mana is spent". So the trigger belongs to the
**mana**, not to the permanent and not to the cast:

* not to the permanent -- Study Hall's plain ``{T}: Add {C}`` must not scry, so
  a per-permanent record (Path of Ancestry's `paid_by: "self"`) is a strictly
  better land;
* not to the cast -- a `spell_cast` trigger cannot say which mana paid, and
  mana that floats in the pool and empties at the end of the step was never
  spent at all;
* it outlives its source: mana from a Study Hall that has since been destroyed
  is still "this mana".

It is a real triggered ability (603): it goes on the stack above the spell it
paid for, controlled by whoever activated the mana ability, and it resolves
after the cast is complete -- which is why X, read on resolution off the
commander-tax tally (903.8), counts **this** cast.

The mechanism, beside `mana_grant` one field over: `Ability.mana_spent_trigger`
is a compiled triggered ability, `costs.activate_mana_ability` puts one
`ManaSpendTrigger` tag on every pip of an activation, `ManaPool.spend` reports
the tags a payment consumed (by identity, so one activation is one trigger and
two activations are two), `costs.pay_mana` matches each against the spell and
queues it, and `stack.ability_of` follows the queued trigger's `mana_spent`
flag from the mana ability to the ability riding it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaPool, ManaSpendTrigger, Pip, Requirement
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, oids_of, only_oid, settle

HALL = "t_study_hall"
COMMANDER = "t_commander_two"  # {1}{W}
NOT_A_COMMANDER = "t_commander_five"  # {3}{W}{W}, cast from hand here

PLAIN_MANA = 0  # {T}: Add {C}.
RIDER_MANA = 1  # {1}, {T}: Add one mana of any color. When you spend this mana...
WHITE = 0  # the rider ability's first option


def white(n: int = 1) -> Requirement:
    colored = [0] * 6
    colored[SYMBOL_INDEX["W"]] = n
    return Requirement(colored=tuple(colored))


def tag(source: int = 1) -> ManaSpendTrigger:
    return ManaSpendTrigger(
        source=source, ability_index=RIDER_MANA, def_id=HALL, controller=0, ability=None
    )


class TestThePipCarriesIt:
    def test_a_pip_defaults_to_no_trigger(self):
        assert Pip().spend_trigger is None

    def test_spending_a_plain_pool_reports_nothing(self):
        pool = ManaPool()
        pool.add_tuple(white().colored, source=1)
        assert pool.spend(white()).spend_triggers == ()

    def test_two_pips_of_one_activation_report_it_once(self):
        """One activation is one "this mana", however many pips it made."""
        pool = ManaPool()
        one = tag()
        pool.add_tuple(white(2).colored, source=1, spend_trigger=one)
        reported = pool.spend(white(2)).spend_triggers
        assert len(reported) == 1 and reported[0] is one

    def test_two_activations_report_twice_though_their_tags_are_equal(self):
        """Two Study Halls -- or one untapped and tapped again -- are two."""
        pool = ManaPool()
        first, second = tag(), tag()
        assert first == second, "equal by value: identity is what tells them apart"
        pool.add_tuple(white().colored, source=1, spend_trigger=first)
        pool.add_tuple(white().colored, source=1, spend_trigger=second)
        assert len(pool.spend(white(2)).spend_triggers) == 2

    def test_untagged_mana_of_the_same_colour_does_not_carry_it(self):
        """The tag is on the pip, not on the colour: the Plains' white is spent
        (newest first) and the Hall's stays in the pool, still tagged."""
        pool = ManaPool()
        pool.add_tuple(white().colored, source=1, spend_trigger=tag())
        pool.add_tuple(white().colored, source=2)
        assert pool.spend(white()).spend_triggers == ()
        assert pool.tags[SYMBOL_INDEX["W"]][0].spend_trigger is not None


def position(builder, *, halls: int = 1, hand=()):
    """Player 0 with ``halls`` Study Halls, five Plains and a commander at home.

    Ten cards in each library so a scry of X looks at X cards, and the
    non-commander in hand keeps the seat from auto-passing the turn away.
    """
    return (
        builder(players=2)
        .battlefield(0, [HALL] * halls + ["plains"] * 5)
        .hand(0, [NOT_A_COMMANDER, *hand])
        .commander(0, [COMMANDER])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )


def rider_mana(game, hall: int) -> None:
    """Tap ``hall`` for its rider mana. The ``{1}`` is not charged: what is
    under test is the mana, and paying would let the solver pick which Plains."""
    activate_mana_ability(game.state, hall, RIDER_MANA, 0, WHITE)


def scries(game) -> list[int]:
    return [e.data["looked"] for e in game.state.events if e.type == "scry"]


def cast(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    return action.source


class TestOneCardTwoAbilities:
    def test_the_rider_ability_tags_its_mana(self, builder):
        game = position(builder)
        rider_mana(game, only_oid(game, HALL, 0))
        pips = [p for row in game.state.players[0].mana_pool.tags for p in row]
        assert pips and all(p.spend_trigger is not None for p in pips)

    def test_the_plain_ability_on_the_same_permanent_does_not(self, builder):
        game = position(builder)
        activate_mana_ability(game.state, only_oid(game, HALL, 0), PLAIN_MANA, 0)
        pips = [p for row in game.state.players[0].mana_pool.tags for p in row]
        assert pips and not any(p.spend_trigger for p in pips)

    def test_spending_the_plain_mana_on_the_commander_does_not_trigger(self, builder):
        """Recorded per permanent, Study Hall's `{C}` would scry too."""
        game = position(builder)
        activate_mana_ability(game.state, only_oid(game, HALL, 0), PLAIN_MANA, 0)
        cast(game, COMMANDER)
        assert game.state.players[0].mana_pool.total() == 0, "the Hall's mana was spent"
        settle(game)
        assert scries(game) == []


class TestSpendingItOnTheCommander:
    def test_it_triggers_above_the_spell_it_paid_for(self, builder):
        """603.3: on the stack when a player next receives priority, which is
        after the cast -- so above the commander, and respondable."""
        game = position(builder)
        rider_mana(game, only_oid(game, HALL, 0))
        commander = cast(game, COMMANDER)

        # Both seats pass and the trigger resolves first: its scry is being
        # asked of its controller while the commander is still on the stack.
        decision = game.pending()
        assert decision.context.get("purpose") == "scry_bottom"
        assert decision.player == 0
        assert [item.oid for item in game.state.stack] == [commander]
        triggered = next(e for e in game.state.events if e.type == "ability_triggered")
        assert triggered.data["trigger"] == "mana_spent" and triggered.player == 0

    def test_x_counts_this_cast(self, builder):
        """"…the number of times it's been cast": the trigger resolves after the
        tax tally was bumped for this cast, so the first cast scries 1."""
        game = position(builder)
        rider_mana(game, only_oid(game, HALL, 0))
        cast(game, COMMANDER)
        settle(game)
        assert scries(game) == [1]

    def test_x_counts_every_cast_from_the_command_zone(self, builder):
        """Two earlier casts on the 903.8 tally, and this one makes three. The
        tally is seeded rather than played out: the commander tax it implies
        ({4} more) is paid by the five Plains beside the Hall's white."""
        game = position(builder)
        commander = game.state.players[0].commanders[0]
        game.state.players[0].commander_tax[commander] = 2
        rider_mana(game, only_oid(game, HALL, 0))
        cast(game, COMMANDER)
        settle(game)
        assert scries(game) == [3]

    def test_two_halls_paying_one_commander_trigger_twice(self, builder):
        game = position(builder, halls=2)
        for hall in oids_of(game, HALL, 0):
            rider_mana(game, hall)
        cast(game, COMMANDER)
        settle(game)
        assert scries(game) == [1, 1]

    def test_it_outlives_its_source(self, builder):
        """106.6: the trigger is the mana's. A Study Hall destroyed with its
        mana floating still scries when that mana is spent."""
        game = position(builder)
        hall = only_oid(game, HALL, 0)
        rider_mana(game, hall)
        move_object(game.state, hall, Zone.GRAVEYARD)
        cast(game, COMMANDER)
        settle(game)
        assert scries(game) == [1]


class TestWhatDoesNotTriggerIt:
    def test_a_spell_that_is_not_your_commander(self, builder):
        game = position(builder)
        rider_mana(game, only_oid(game, HALL, 0))
        cast(game, NOT_A_COMMANDER)
        assert game.state.players[0].mana_pool.total() == 0, "the Hall's mana was spent"
        settle(game)
        assert scries(game) == []

    def test_mana_left_in_the_pool_and_emptied(self, builder):
        """Never spent, so never "this mana is spent" -- and the commander cast
        afterwards with other mana is cast with none of it."""
        game = position(builder)
        rider_mana(game, only_oid(game, HALL, 0))
        game.state.empty_all_mana_pools(keep_for_turn=game.state.turn)
        assert game.state.players[0].mana_pool.total() == 0
        cast(game, COMMANDER)
        settle(game)
        assert scries(game) == []


def hall_with(rider: dict, *, mana_ability: bool = True) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe_hall",
            "name": "Probe Hall",
            "types": ["Land"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {G}. When you spend this mana to cast ...",
                    "is_mana_ability": mana_ability,
                    "cost": {"tap": True},
                    "effects": [{"op": "add_mana", "mana": "{G}"}],
                    "mana_spent_trigger": rider,
                }
            ],
        }
    )


GAIN = [{"op": "gain_life", "player": "you", "amount": {"const": 2}}]


class TestTheLoader:
    def test_the_witness_compiles_to_a_triggered_ability(self, registry):
        rider = registry.get(HALL).abilities[RIDER_MANA].mana_spent_trigger
        assert rider is not None and rider.is_triggered
        assert rider.trigger.filter == {"is_commander": True, "owner": "you"}
        assert registry.get(HALL).abilities[PLAIN_MANA].mana_spent_trigger is None

    def test_a_spell_filter_may_be_omitted(self):
        card = compile_card(hall_with({"effects": GAIN}))
        assert card.abilities[0].mana_spent_trigger is not None

    def test_it_needs_a_mana_ability(self):
        with pytest.raises(DslError, match="'mana_spent_trigger' needs 'is_mana_ability'"):
            compile_card(hall_with({"effects": GAIN}, mana_ability=False))

    def test_it_needs_effects(self):
        with pytest.raises(DslError, match="non-empty 'effects'"):
            compile_card(hall_with({"spell": {"types": ["Creature"]}}))

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unknown keys"):
            compile_card(hall_with({"effects": GAIN, "filter": {}}))

    @pytest.mark.parametrize("key", ["paid_by", "self_only", "shares_a_creature_type_with"])
    def test_a_source_relative_filter_key_is_refused(self, key):
        with pytest.raises(DslError, match="ask about the ability's source"):
            compile_card(hall_with({"spell": {key: "self"}, "effects": GAIN}))

    def test_the_spell_filter_is_validated_as_a_trigger_filter(self):
        with pytest.raises(DslError):
            compile_card(hall_with({"spell": {"no_such_key": 1}, "effects": GAIN}))

    def test_its_effects_are_validated(self):
        with pytest.raises(DslError, match="unknown effect op"):
            compile_card(hall_with({"effects": [{"op": "no_such_op"}]}))
