"""A mana ability that arranges something for the next creature spell.

    "Grand Summon -- {T}: Add one mana of any color. **When you next cast a
    creature spell this turn, that creature enters with two additional +1/+1
    counters on it.**"                           -- Yuna, Grand Summoner

Two halves, and each one closes a different wrong reading.

**The rider is a delayed trigger, installed off the stack.** 605.1a makes the
ability a mana ability -- no target, could add mana, not a loyalty ability -- so
it resolves inside payment with no stack and no priority window. What it
*creates* is a delayed triggered ability (603.7): it triggers when the next
creature spell is cast and resolves while that spell is still on the stack (off
the stack itself, the divergence `triggers.run_armed_delays` and
`docs/rules-coverage.md` record for every delayed trigger). Installing a
subscription asks nothing, which is why
`delayed_trigger` is in `loader.MANA_RIDER_OPS`. Its duration is
`once_this_turn`: the first creature spell spends it, and an unspent one is gone
at cleanup.

**"Enters with" is a replacement on the arrival, not counters added after.**
614.1c: the creature is never on the battlefield without them, so they join the
one placement (122.6) everything else it enters with makes. An `add_counters`
on the spell would act on an object on the stack, and one after the arrival
would be a second placement -- Hardened Scales adding two instead of one. The
promise is staged on the spell (`GameObject.cast_enters_with`) by
`spell_enters_with_counters`, carried by `move_object` only to the battlefield,
and cashed by `zones._enter_battlefield`.

Unlike Arena of Glory's rider (`test_mana_granted_keyword.py`) the trigger does
not care which mana paid: per the card's ruling it fires on the next creature
spell you cast this turn whether or not Yuna's mana was spent on it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pass_until, settle

SUMMONER = "t_grand_summoner"
SPRINTER = "t_glory_sprinter"  # vanilla 2/2 Creature for {2}
RELIC = "t_glory_relic"  # vanilla Artifact for {2}
SCALES = "hardened_scales"
RIDER = "When you next cast a creature spell this turn, that creature enters with two additional +1/+1 counters on it."


def position(builder, hand: list[str], extra: tuple[str, ...] = ()):
    """The Summoner untapped, two Forests, ``hand`` in hand, at our main phase."""
    game = (
        builder(players=2)
        .hand(0, hand)
        .battlefield(0, [SUMMONER, "forest", "forest", *extra])
        .library(0, ["island"] * 20)
        .build()
    )
    return game, only_oid(game, SUMMONER, 0)


def cast(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    return action.source


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


class TestTheRiderIsInstalledOffTheStack:
    def test_activation_installs_one_subscription(self, builder):
        game, summoner = position(builder, [])
        before = len(game.state.delayed_triggers)
        activate_mana_ability(game.state, summoner, 0, 0)
        assert len(game.state.delayed_triggers) == before + 1
        assert game.state.delayed_triggers[-1].duration == "once_this_turn"

    def test_the_mana_arrives_and_nothing_goes_on_the_stack(self, builder):
        game, summoner = position(builder, [])
        activate_mana_ability(game.state, summoner, 0, 0)
        assert game.state.players[0].mana_pool.total() == 1
        assert not game.state.stack

    def test_it_is_gone_at_end_of_turn(self, builder):
        game, summoner = position(builder, [])
        activate_mana_ability(game.state, summoner, 0, 0)
        pass_until(game, lambda g: g.state.turn >= 2 and g.state.step >= Step.UPKEEP)
        assert not game.state.delayed_triggers


class TestThatCreatureEntersWithTheCounters:
    def test_the_next_creature_spell_arrives_with_two(self, builder):
        game, summoner = position(builder, [SPRINTER])
        activate_mana_ability(game.state, summoner, 0, 0)
        oid = cast(game, SPRINTER)
        settle(game)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert counters(game, oid) == 2

    def test_without_the_activation_it_arrives_bare(self, builder):
        """The control: same creature, paid by the Forests alone."""
        game, _ = position(builder, [SPRINTER])
        oid = cast(game, SPRINTER)
        settle(game)
        assert counters(game, oid) == 0

    def test_it_fires_once(self, builder):
        """"When you **next** cast": the second creature spell gets nothing."""
        game, summoner = position(builder, [SPRINTER, SPRINTER], extra=("forest", "forest"))
        activate_mana_ability(game.state, summoner, 0, 0)
        first = cast(game, SPRINTER)
        settle(game)
        second = cast(game, SPRINTER)
        settle(game)
        assert (counters(game, first), counters(game, second)) == (2, 0)

    def test_a_noncreature_spell_does_not_spend_it(self, builder):
        """"…a **creature** spell": the artifact neither takes the counters nor
        uses up the trigger the creature after it is owed."""
        game, summoner = position(builder, [RELIC, SPRINTER], extra=("forest", "forest"))
        activate_mana_ability(game.state, summoner, 0, 0)
        relic = cast(game, RELIC)
        settle(game)
        sprinter = cast(game, SPRINTER)
        settle(game)
        assert (counters(game, relic), counters(game, sprinter)) == (0, 2)


class TestOnePlacement:
    def test_hardened_scales_adds_one_to_the_total(self, builder):
        """122.6: one placement of two, plus one -- three, not four. Counters put
        on after the arrival would be a placement Scales sees separately."""
        game, summoner = position(builder, [SPRINTER], extra=(SCALES,))
        activate_mana_ability(game.state, summoner, 0, 0)
        oid = cast(game, SPRINTER)
        settle(game)
        assert counters(game, oid) == 3


class TestTheStagingFieldIsNotAKeepsake:
    def test_it_is_emptied_by_the_arrival(self, builder):
        game, summoner = position(builder, [SPRINTER])
        activate_mana_ability(game.state, summoner, 0, 0)
        oid = cast(game, SPRINTER)
        settle(game)
        assert game.state.objects[oid].cast_enters_with == {}

    def test_a_spell_that_never_arrives_does_not_keep_it(self, builder):
        """A countered creature spell is in a graveyard owing nobody counters."""
        game, summoner = position(builder, [SPRINTER])
        activate_mana_ability(game.state, summoner, 0, 0)
        oid = cast(game, SPRINTER)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].cast_enters_with == {}


def _summoner_model(rider: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_bad_summoner",
            "name": "Bad Summoner",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{T}: Add {G}. " + RIDER,
                    "is_mana_ability": True,
                    "cost": {"tap": True},
                    "effects": [{"op": "add_mana", "mana": "{G}"}, rider],
                }
            ],
        }
    )


def _rider(trigger_extra: dict | None = None, effect: dict | None = None) -> dict:
    return {
        "op": "delayed_trigger",
        "duration": "once_this_turn",
        "trigger": {"event": "spell_cast", "controller": "you", **(trigger_extra or {})},
        "effects": [effect or {"op": "spell_enters_with_counters", "counters": {"+1/+1": 2}}],
    }


class TestTheLoaderRefuses:
    def test_the_rider_loads(self):
        compile_card(_summoner_model(_rider()))

    def test_a_rider_scoped_to_a_subject(self):
        """A mana ability has no targets and no bindings: "that creature" at
        activation names nothing, and the subscription would never fire."""
        with pytest.raises(DslError, match="subject"):
            compile_card(_summoner_model(_rider({"subject": {"binding": "it"}})))

    def test_spell_enters_with_counters_without_a_map(self):
        with pytest.raises(DslError, match="counters"):
            compile_card(_summoner_model(_rider(effect={"op": "spell_enters_with_counters"})))

    def test_spell_enters_with_counters_with_a_near_miss_kind(self):
        """A keyword counter misspelled is an inert tally; refused as anywhere."""
        with pytest.raises(DslError):
            compile_card(
                _summoner_model(
                    _rider(effect={"op": "spell_enters_with_counters", "counters": {"Vigilance counter": 1}})
                )
            )
