"""Station -- a tap cost that names the creature it tapped.

    Station (702.184a): "Tap another untapped creature you control: Put a number
    of charge counters on this permanent equal to the tapped creature's power.
    Activate only as a sorcery."

The witnesses are the two Planets in the Bard, King of Dale deck, Uthros, Titanic
Godcore and Adagia, Windswept Bastion; `t_station_planet` is their shape with the
threshold line left off.

`tap_permanents` already charged "tap another creature you control" -- crew is
built on it -- but it was write-only: the creature was tapped and then forgotten,
so nothing the ability did could ask how big it was. The capability is `as` on
that cost, which binds the tapped permanent for the effects.

What the binding holds is the whole design, and the Edge of Eternities release
notes settle it in two sentences:

- **The power is read as the ability resolves.** A pump in response counts, so a
  snapshot taken at payment would be wrong.
- **If the creature has left the battlefield, its power as it last existed there
  is used.** A bare oid would be wrong too: the oid outlives the permanent here,
  and the graveyard card behind it answers with its printed power.

So the binding is a reference to a record the zone change fills in as the
permanent leaves. And 107.1b makes a negative power put no counters rather than
remove some -- the notes say that outright as well.

The alternative spelling -- `choose_permanents`, then the `tap` op, then
`add_counters` -- is not Station: the tap would happen on resolution, so the
ability could be activated with no creature to tap and responded to before
anything was tapped.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import pump
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid, pass_until

PLANET = "t_station_planet"
BEAR = "t_bear"  # 2/2
GIANT = "t_big"  # 6/6
STATION_INDEX = 1


def position(builder, *creatures: str, step: Step = Step.PRECOMBAT_MAIN, active: int = 0):
    """The Planet and its crew, and an opponent holding a Bolt it can cast.

    The Bolt is never cast. It is there so the opponent has something to do
    with priority while Station is on the stack -- a window with nothing in it
    but "pass" is passed automatically, and the ability would resolve before a
    test could respond to it.
    """
    game = (
        builder(players=2)
        .battlefield(0, [PLANET])
        .battlefield(0, list(creatures))
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(step)
        .active(active)
        .build()
    )
    return game, only_oid(game, PLANET)


def station_action(game, planet: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == planet
            and a.ability_index == STATION_INDEX
        ),
        None,
    )


def activate(game, planet: int, creature: int) -> None:
    """Activate Station, tapping ``creature`` if the engine asks which."""
    action = station_action(game, planet)
    assert action is not None, "Station was not offered"
    game.apply(action)
    choose = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and creature in [t.id for t in a.targets]
        ),
        None,
    )
    if choose is not None:
        game.apply(choose)


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


def charge(game, planet: int) -> int:
    return game.state.objects[planet].counter("charge")


class TestWhenItIsOffered:
    def test_another_creature_makes_it_offered(self, builder):
        game, planet = position(builder, BEAR)
        assert station_action(game, planet) is not None

    def test_with_no_creature_it_is_not_offered(self, builder):
        """A cost, so it gates the activation: nothing to tap, nothing to station."""
        game, planet = position(builder)
        assert station_action(game, planet) is None

    def test_a_tapped_creature_does_not_pay(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLANET])
            .battlefield(0, [BEAR], tapped=True)
            .build()
        )
        assert station_action(game, only_oid(game, PLANET)) is None

    def test_only_as_a_sorcery(self, builder):
        game, planet = position(builder, BEAR, step=Step.BEGIN_COMBAT)
        assert station_action(game, planet) is None


class TestPayingIt:
    def test_the_creature_is_tapped_on_activation(self, builder):
        """Before the ability resolves -- which is what makes it a cost."""
        game, planet = position(builder, BEAR)
        bear = only_oid(game, BEAR)

        activate(game, planet, bear)

        assert game.state.stack, "the ability should still be on the stack"
        assert game.state.objects[bear].tapped

    def test_it_puts_counters_equal_to_the_tapped_creatures_power(self, builder):
        game, planet = position(builder, GIANT)

        activate(game, planet, only_oid(game, GIANT))
        resolve(game)

        assert charge(game, planet) == 6

    def test_it_reads_the_creature_that_was_tapped_not_another(self, builder):
        """The Bear was tapped; the Giant beside it has nothing to do with it."""
        game, planet = position(builder, BEAR, GIANT)

        activate(game, planet, only_oid(game, BEAR))
        resolve(game)

        assert charge(game, planet) == 2

    def test_stationing_again_adds_to_the_count(self, builder):
        game, planet = position(builder, BEAR, GIANT)

        activate(game, planet, only_oid(game, BEAR))
        resolve(game)
        activate(game, planet, only_oid(game, GIANT))
        resolve(game)

        assert charge(game, planet) == 8


class TestThePowerIsReadOnResolution:
    def test_a_pump_in_response_counts(self, builder):
        """A snapshot at payment would put two counters here."""
        game, planet = position(builder, BEAR)
        bear = only_oid(game, BEAR)

        activate(game, planet, bear)
        pump(game.state, bear, 3, 3)
        resolve(game)

        assert charge(game, planet) == 5

    def test_a_creature_that_left_uses_its_last_known_power(self, builder):
        """Pumped to 5/5 and then destroyed in response: five, as it last
        existed -- not two off the printed card in the graveyard, and not zero."""
        game, planet = position(builder, BEAR)
        bear = only_oid(game, BEAR)

        activate(game, planet, bear)
        pump(game.state, bear, 3, 3)
        destroy(game.state, bear)
        assert not game.state.objects[bear].on_battlefield
        resolve(game)

        assert charge(game, planet) == 5

    def test_a_negative_power_puts_no_counters_and_removes_none(self, builder):
        """107.1b. Handed -3, the primitive would *remove* three counters."""
        game, planet = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        game.state.objects[planet].counters["charge"] = 4

        activate(game, planet, bear)
        pump(game.state, bear, -5, 0)
        resolve(game)

        assert charge(game, planet) == 4

    def test_the_record_is_let_go_once_the_ability_resolves(self, builder):
        game, planet = position(builder, BEAR)

        activate(game, planet, only_oid(game, BEAR))
        assert game.state.paid_objects
        resolve(game)

        assert not game.state.paid_objects


PLANET_MODEL = {
    "id": "t_planet_guard",
    "name": "Test Planet Guard",
    "oracle_text": "Station",
    "types": ["Land"],
    "abilities": [
        {
            "kind": "activated",
            "text": "Station",
            "cost": {"tap_permanents": {"types": ["Creature"], "as": "stationed"}},
            "sorcery_speed_only": True,
            "effects": [
                {
                    "op": "add_counters",
                    "counter": "charge",
                    "amount": {"power_of": {"binding": "stationed"}},
                    "objects": {"self_only": True},
                }
            ],
        }
    ],
}


def _with_cost(tap_permanents: dict) -> dict:
    card = copy.deepcopy(PLANET_MODEL)
    card["abilities"][0]["cost"]["tap_permanents"] = tap_permanents
    return card


class TestLoadTimeGuards:
    def test_the_named_cost_loads(self):
        card = compile_card(CardModel.model_validate(PLANET_MODEL))
        assert card.abilities[0].cost.tap_permanents["as"] == "stationed"

    def test_an_empty_name_is_refused(self):
        with pytest.raises(DslError, match="a binding name"):
            compile_card(CardModel.model_validate(_with_cost({"types": ["Creature"], "as": ""})))

    def test_naming_one_of_several_tapped_permanents_is_refused(self):
        """"The tapped creature" is one creature; a name bound to the first of
        five would read one power where the card meant none."""
        with pytest.raises(DslError, match="exactly one"):
            compile_card(
                CardModel.model_validate(
                    _with_cost({"types": ["Creature"], "count": 2, "as": "stationed"})
                )
            )

    def test_naming_a_crew_payment_is_refused(self):
        with pytest.raises(DslError, match="exactly one"):
            compile_card(
                CardModel.model_validate(
                    _with_cost({"types": ["Creature"], "total_power": 3, "as": "crew"})
                )
            )
