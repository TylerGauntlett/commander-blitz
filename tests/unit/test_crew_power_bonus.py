"""Crewing as though power were greater — a bonus that exists inside one sum.

    "Create a 1/1 colorless Pilot creature token with "This token crews Vehicles
    as though its power were 2 greater."" -- Shorikai, Genesis Engine

Crew (702.122a) is "tap any number of untapped creatures you control with total
power N or greater", and this line changes what one creature adds to *that*
total and to nothing else. Shorikai is the witness, and the reason the line is
the whole of its token: a Pilot plus a 5/5 crews Shorikai's Crew 8 (1 + 2 + 5),
and a vanilla 1/1 plus the same 5/5 does not.

The near miss is `buff`, and it is a strictly different card. A +2/+0 anthem on
the token makes a 3/1 that attacks for three, blocks for three, and counts three
for Ghalta's cost reduction and every other "total power" on the board. The
printed Pilot is a 1/1 in all of those places. So the bonus is a static read by
`costs._crew_power` alone -- the one sum a crew cost takes -- and never by the
characteristics pipeline.

It is not a token-only rider either: Hotshot Mechanic prints the same line on a
nontoken creature, and the static is ordinary enough to sit on either.

Saddle (702.171) is the other half of the "saddles Mounts and crews Vehicles"
wording some Pilots print. The engine has no saddle, so nothing here can
reach it; the token defined for Shorikai is the crew-only Pilot, and the
saddling one is a different token id when saddle exists.
"""

from __future__ import annotations

import pytest

from automtg.cards.authoring.packet import _token_ids
from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars, crew_power_bonus
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from tests.conftest import only_oid
from tests.unit.test_combat import attack_with, done, resolve_combat, to_attackers

PILOT = "pilot_1_1_c_crew2"        # 1/1, crews as though its power were 2 greater
CREW_8 = "t_crew8_vehicle"         # Shorikai's Crew 8
CREW_3 = "t_vehicle"               # crew 3, becomes a 4/4
FIVE = "t_five_five"               # 5/5
DORK = "t_dork"                    # a vanilla-sized 1/1 -- the Pilot minus its line
MECHANIC = "t_hotshot_mechanic"    # 2/1, the same line on a nontoken creature
ANTHEM = "t_anthem"                # creatures you control get +1/+1
ISLAND = "island"


def position(builder, vehicle: str, *crewers: str, tapped: tuple[str, ...] = ()):
    b = (
        builder(players=2)
        .battlefield(0, [vehicle])
        .battlefield(0, list(crewers))
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
    )
    if tapped:
        b = b.battlefield(0, list(tapped), tapped=True)
    game = b.build()
    return game, only_oid(game, vehicle)


def crew_action(game, vehicle: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == vehicle
        ),
        None,
    )


def pick(game, oid: int) -> None:
    """Choose ``oid`` to tap for crew, if the question is still being asked.

    A pool narrowed to one creature is not a question, and the engine answers it
    itself -- so a missing choice is not a failure; what was tapped is asserted.
    """
    choose = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and oid in [t.id for t in a.targets]
        ),
        None,
    )
    if choose is not None:
        game.apply(choose)


class TestWhoCanCrew:
    def test_a_pilot_and_a_five_five_crew_eight(self, builder):
        """Shorikai's own board: 1 + 2 + 5 = 8."""
        game, vehicle = position(builder, CREW_8, PILOT, FIVE)
        assert crew_action(game, vehicle) is not None

    def test_a_vanilla_one_one_and_the_same_five_five_do_not(self, builder):
        """The counterfactual. Without the line the board is 6 power, not 8."""
        game, vehicle = position(builder, CREW_8, DORK, FIVE)
        assert crew_action(game, vehicle) is None

    def test_a_pilot_alone_crews_three(self, builder):
        game, vehicle = position(builder, CREW_3, PILOT)
        assert crew_action(game, vehicle) is not None

    def test_a_vanilla_one_one_alone_does_not(self, builder):
        game, vehicle = position(builder, CREW_3, DORK)
        assert crew_action(game, vehicle) is None

    def test_the_bonus_belongs_to_the_pilot_alone(self, builder):
        """3 + 1 + 1 = 5. A bonus handed to every crewing creature, or taken off
        the crew number, would have reached eight."""
        game, vehicle = position(builder, CREW_8, PILOT, DORK, DORK)
        assert crew_action(game, vehicle) is None

    def test_a_nontoken_creature_with_the_line_counts_it(self, builder):
        """Hotshot Mechanic: 2 + 2 = 4, crew 3 needs no second creature."""
        game, vehicle = position(builder, CREW_3, MECHANIC)
        assert crew_action(game, vehicle) is not None

    def test_a_tapped_pilot_adds_nothing(self, builder):
        """The bonus rides on the creature, and a tapped creature cannot crew at all."""
        game, vehicle = position(builder, CREW_8, FIVE, tapped=(PILOT,))
        assert crew_action(game, vehicle) is None


class TestItStacksWithDerivedPower:
    def test_an_anthem_and_the_bonus_both_count(self, builder):
        """A Pilot under an anthem is a 2/2 that crews as a 4: 4 + 2 + 2 + 2 = 10."""
        game, vehicle = position(builder, CREW_8, PILOT, DORK, DORK, DORK, ANTHEM)
        assert crew_action(game, vehicle) is not None

    def test_the_same_board_without_the_anthem_cannot(self, builder):
        game, vehicle = position(builder, CREW_8, PILOT, DORK, DORK, DORK)
        # 3 + 1 + 1 + 1 = 6.
        assert crew_action(game, vehicle) is None


class TestPayingIt:
    def test_the_pilot_and_the_five_five_are_both_tapped(self, builder):
        game, vehicle = position(builder, CREW_8, PILOT, FIVE)
        pilot, five = only_oid(game, PILOT), only_oid(game, FIVE)

        game.apply(crew_action(game, vehicle))
        pick(game, pilot)
        pick(game, five)

        assert game.state.objects[pilot].tapped
        assert game.state.objects[five].tapped
        assert "Creature" in chars(game.state, vehicle).types
        assert chars(game.state, vehicle).power == 8

    def test_the_pilot_counts_three_toward_what_is_still_needed(self, builder):
        """The payment loop subtracts crew power, not power: after the Pilot a
        crew 3 is met and nothing else is asked for."""
        game, vehicle = position(builder, CREW_3, PILOT, DORK)
        pilot, dork = only_oid(game, PILOT), only_oid(game, DORK)

        game.apply(crew_action(game, vehicle))
        pick(game, pilot)

        assert game.state.objects[pilot].tapped
        assert not game.state.objects[dork].tapped, "the Vehicle was already crewed"
        assert "Creature" in chars(game.state, vehicle).types


class TestItIsNotPower:
    def test_the_pilot_is_still_a_one_one(self, builder):
        game, _ = position(builder, CREW_8, PILOT)
        pilot = only_oid(game, PILOT)

        assert (chars(game.state, pilot).power, chars(game.state, pilot).toughness) == (1, 1)
        assert crew_power_bonus(game.state, pilot) == 2

    def test_it_attacks_for_one(self, builder):
        """What a `buff` would have got wrong: the defending player loses 1, not 3."""
        game = builder().battlefield(0, [PILOT]).build()
        to_attackers(game)
        attack_with(game, only_oid(game, PILOT, 0))
        done(game)
        resolve_combat(game)

        assert game.state.players[1].life == 39

    def test_a_creature_without_the_line_has_no_bonus(self, builder):
        game, _ = position(builder, CREW_8, FIVE)
        assert crew_power_bonus(game.state, only_oid(game, FIVE)) == 0


class TestTheToken:
    def test_it_is_the_printed_pilot(self, builder):
        game, _ = position(builder, CREW_8, FIVE)
        (pilot,) = create_token(game.state, PILOT, 0)
        game.state.bump_chars()
        c = chars(game.state, pilot)

        assert (c.power, c.toughness) == (1, 1)
        assert set(c.types) == {"Creature"}
        assert set(c.subtypes) == {"Pilot"}
        assert not c.colors
        assert game.state.objects[pilot].is_token

    def test_a_created_pilot_crews_shorikai(self, builder):
        """Summoning sickness does not stop a creature crewing (702.122 taps
        other permanents; 302.6 is about the {T} symbol), so the Pilot
        Shorikai makes this turn crews it this turn.

        Created on the builder's state, before the game advances: made after, a
        board that cannot crew has already auto-passed out of the main phase."""
        b = (
            builder(players=2)
            .battlefield(0, [CREW_8, FIVE])
            .library(0, [ISLAND] * 20)
            .library(1, [ISLAND] * 20)
        )
        (pilot,) = create_token(b.state, PILOT, 0)
        game = b.build()
        vehicle = only_oid(game, CREW_8)

        assert game.state.objects[pilot].summoning_sick(game.state.turn)
        assert crew_action(game, vehicle) is not None

    def test_the_authoring_packet_offers_it(self):
        assert PILOT in _token_ids()


class TestTheLoaderGuard:
    def _card(self, **static) -> CardModel:
        base = {"kind": "static", "effect": "crew_power_bonus"}
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_crew_bonus_probe",
                "name": "Crew Bonus Probe",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [base],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._card(affects={"self_only": True}, amount={"const": 2}))

    def test_omitting_the_amount_is_refused(self):
        """A bonus of nothing prints the line and crews as a vanilla creature."""
        with pytest.raises(DslError, match="crew_power_bonus' needs an 'amount'"):
            compile_card(self._card(affects={"self_only": True}))

    def test_omitting_affects_is_refused(self):
        """A missing filter matches nothing, so the line would bind no creature."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(amount={"const": 2}))
