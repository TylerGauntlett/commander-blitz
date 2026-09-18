""""You may activate loyalty abilities of Teferi on any player's turn any time you
could cast an instant."

Teferi, Master of Time is the witness. 606.3 is **two** rules in one sentence — a
loyalty ability may be activated only during your own main phase with an empty
stack, *and* only if no loyalty ability of that permanent has been activated this
turn — and the printed line lifts exactly the first of them. A waiver that took
both would be three cards' worth of Teferi every turn, so
`TestTheOncePerTurnLimitStands` is as much the point of this as the permission is.

It could not be authored. The loader forces the flag on for every loyalty
ability::

    sorcery_speed_only = model.sorcery_speed_only or (cost is not None and cost.loyalty is not None)

so `sorcery_speed_only: false` written on the card is swallowed by the `or` and
changes nothing — there is no spelling that reaches the flag. The permission had
to arrive from the board instead, which is why this is a static and not an
ability key.

The near misses, each a different wrong card:

- **`activate_steps`** and **`once_each_turn`** are the only ability keys about
  timing, and both are *restrictions*. Naming every step in `activate_steps`
  still leaves `sorcery_speed_only` true, so the ability stays refused.
- **`flash`, granted or printed**, is read only by the spell-casting timing check
  and says nothing about activating an ability. `cast_as_though_flash` — the
  neighbouring static built for Tidal Barracuda — is the same distinction from the
  other side: that one widens the *casting* window for spells, this one the
  *activation* window for abilities, and closing either leaves the other shut.
  `TestTheSpellPermissionIsADifferentDoor` pins that they do not leak into one
  another.
- **Dropping the sentence.** A Teferi whose loyalty abilities are sorcery-speed
  only is a materially weaker card, which is why the gap record wrote no partial
  answer.

`affects` says whose loyalty abilities are freed, in the ordinary permanent-filter
language: `{"self_only": true}` is the printed "of Teferi", and the filter is
required rather than defaulted, because a missing one matches every permanent and
would hand the whole table instant-speed loyalty in silence.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import legality
from automtg.engine.characteristics import loyalty_activation_timing_waived
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import only_oid

TEFERI = "t_instant_walker"  # the permission, self_only
NARSET = "t_patient_walker"  # the same walker without it -- the control
ORRERY = "t_walker_orrery"  # the permission aimed at other permanents
TAMIYO = "t_tapper_walker"  # the permission, plus a non-loyalty sorcery-speed line
ISLAND = "island"


def position(builder, *board: str, active: int = 0, step: Step = Step.PRECOMBAT_MAIN):
    """Player 0 controls everything named; ``active`` is whose turn it is.

    Four Islands so mana is never the reason an ability is missing, and player 1
    holds the other seat so "any player's turn" has one to be.
    """
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * 4 + list(board))
        .battlefield(1, [ISLAND] * 4)
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(step)
        .active(active)
        .build(advance=False)
    )


def loyalty_actions(game, card_id: str) -> list:
    oid = only_oid(game, card_id)
    return [
        a
        for a in legality._priority_actions(game.state, 0)
        if a.kind is ActionKind.ACTIVATE and a.source == oid
    ]


class TestTheSorcerySpeedWindowIsTheBaseline:
    """Without the line, a loyalty ability is your-main-phase-only. 606.3."""

    def test_offered_on_your_own_main_phase(self, builder):
        game = position(builder, NARSET, active=0)
        assert len(loyalty_actions(game, NARSET)) == 2

    def test_not_on_the_opponents_turn(self, builder):
        game = position(builder, NARSET, active=1)
        assert loyalty_actions(game, NARSET) == []

    def test_not_in_your_own_combat(self, builder):
        """Sorcery speed is a main phase as well as a turn."""
        game = position(builder, NARSET, active=0, step=Step.DECLARE_BLOCKERS)
        assert loyalty_actions(game, NARSET) == []


class TestThePermissionLiftsTheWindow:
    def test_on_the_opponents_turn(self, builder):
        game = position(builder, TEFERI, active=1)
        assert len(loyalty_actions(game, TEFERI)) == 2, "both loyalty abilities"

    def test_in_a_step_that_is_not_a_main_phase(self, builder):
        game = position(builder, TEFERI, active=0, step=Step.DECLARE_BLOCKERS)
        assert len(loyalty_actions(game, TEFERI)) == 2

    def test_on_the_opponents_combat(self, builder):
        """Both halves of the window at once, which is the printed sentence."""
        game = position(builder, TEFERI, active=1, step=Step.DECLARE_BLOCKERS)
        assert len(loyalty_actions(game, TEFERI)) == 2

    def test_it_still_works_on_your_own_main_phase(self, builder):
        """A permission cannot take anything away."""
        game = position(builder, TEFERI, active=0)
        assert len(loyalty_actions(game, TEFERI)) == 2

    def test_the_reader_agrees(self, builder):
        """The drift test: the predicate and the action list are one claim, and
        the walker without the line is the control."""
        game = position(builder, TEFERI, NARSET, active=1)
        assert loyalty_activation_timing_waived(game.state, only_oid(game, TEFERI))
        assert not loyalty_activation_timing_waived(game.state, only_oid(game, NARSET))


class TestTheOncePerTurnLimitStands:
    """606.3's *other* half, which this line does not touch.

    The failure mode that matters: a waiver written as "skip the 606.3 check"
    rather than "skip the timing check" passes every test above and quietly turns
    one planeswalker into three cards a turn.
    """

    @pytest.mark.parametrize("active", [0, 1], ids=["your-turn", "their-turn"])
    def test_a_second_loyalty_ability_is_not_offered_after_the_first(self, builder, active):
        game = position(builder, TEFERI, active=active)
        offered = loyalty_actions(game, TEFERI)
        assert len(offered) == 2, "both are offered before either is used"
        # Written straight into the ledger, which is the counter 606.3's second
        # half actually reads -- the same one `game.apply` would bump. Driving a
        # real activation would also resolve it, and what is being pinned here is
        # the offer, not the gain of 2 life.
        game.state.turn_ledger.activated(only_oid(game, TEFERI), offered[0].ability_index)
        assert loyalty_actions(game, TEFERI) == [], (
            "one loyalty ability per permanent per turn, permission or not"
        )


class TestOnlyLoyaltyAbilitiesAreFreed:
    """The static names loyalty abilities, and a sorcery-speed line that is not
    one stays refused — Teferi's permission is not a general timing waiver."""

    def test_the_loyalty_line_is_offered_off_turn(self, builder):
        game = position(builder, TAMIYO, active=1)
        offered = {a.ability_index for a in loyalty_actions(game, TAMIYO)}
        assert 1 in offered, "the +1 is a loyalty ability"

    def test_the_other_sorcery_speed_line_is_not(self, builder):
        game = position(builder, TAMIYO, active=1)
        offered = {a.ability_index for a in loyalty_actions(game, TAMIYO)}
        assert 2 not in offered, "a {T} ability marked sorcery-speed is not loyalty"


class TestTheFilterIsRead:
    """`affects` is not assumed to mean "self"."""

    def test_the_orrery_frees_a_walker_it_does_not_share_a_card_with(self, builder):
        game = position(builder, ORRERY, NARSET, active=1)
        assert len(loyalty_actions(game, NARSET)) == 2

    def test_without_the_orrery_that_same_walker_is_refused(self, builder):
        game = position(builder, NARSET, active=1)
        assert loyalty_actions(game, NARSET) == []

    def test_a_self_only_permission_does_not_reach_its_neighbour(self, builder):
        """Teferi's line says "of Teferi", and the other walker is not Teferi."""
        game = position(builder, TEFERI, NARSET, active=1)
        assert len(loyalty_actions(game, TEFERI)) == 2
        assert loyalty_actions(game, NARSET) == []

    def test_the_wearing_off(self, builder):
        game = position(builder, ORRERY, NARSET, active=1)
        game.state.battlefield.remove(only_oid(game, ORRERY))
        game.state.bump_chars()
        assert loyalty_actions(game, NARSET) == []


class TestTheSpellPermissionIsADifferentDoor:
    """`cast_as_though_flash` and this one do not leak into each other."""

    def test_flash_for_spells_does_not_free_a_loyalty_ability(self, builder):
        game = position(builder, NARSET, "t_orrery", active=1)
        assert loyalty_actions(game, NARSET) == []

    def test_and_this_one_does_not_let_a_sorcery_be_cast(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ISLAND] * 4 + [TEFERI])
            .battlefield(1, [ISLAND] * 4)
            .hand(0, ["t_sorcery"])
            .library(0, ["forest"] * 10)
            .library(1, ["forest"] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .active(1)
            .build(advance=False)
        )
        assert not any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "t_sorcery"
            for a in legality._priority_actions(game.state, 0)
        )


class TestTheLoaderGuards:
    def card(self, **extra):
        return {
            "id": "t_probe_walker_timing",
            "name": "Probe Walker Timing",
            "mana_cost": "{4}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "You may activate loyalty abilities any time you could cast an instant.",
                    "effect": "activate_loyalty_as_though_instant",
                    **extra,
                }
            ],
        }

    def test_it_needs_a_filter(self):
        """A missing `affects` matches every permanent — the loudest over-grant."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(CardModel.model_validate(self.card()))

    def test_it_takes_no_player(self):
        with pytest.raises(DslError, match="no 'affects_player' or 'amount'"):
            compile_card(
                CardModel.model_validate(
                    self.card(affects={"self_only": True}, affects_player="you")
                )
            )

    def test_it_takes_no_amount(self):
        with pytest.raises(DslError, match="no 'affects_player' or 'amount'"):
            compile_card(
                CardModel.model_validate(
                    self.card(affects={"self_only": True}, amount={"const": 1})
                )
            )

    def test_a_filter_is_enough(self):
        card = compile_card(CardModel.model_validate(self.card(affects={"self_only": True})))
        assert card.abilities[0].static["effect"] == "activate_loyalty_as_though_instant"
