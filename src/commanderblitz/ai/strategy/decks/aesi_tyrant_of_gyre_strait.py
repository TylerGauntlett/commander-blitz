"""Aesi, Tyrant of Gyre Strait: extra land drops, landfall payoffs, one huge turn.

Lander Commander turns lands into everything else: Exploration, Azusa and
Oracle of Mul Daya multiply the drops, Aesi draws a card off each one, and the
payoffs -- Rampaging Baloths, Greensleeves, Scute Swarm, Avenger of Zendikar --
turn each drop into a body. The game ends on Craterhoof Behemoth or
Overwhelming Stampede over a board that grew without attacking. So the CPU
casts the drop multipliers early, gets a landfall payoff down *before* the
land drop when it can, and saves the overrun for a board worth pumping. See
docs/cpus/aesi_tyrant_of_gyre_strait.md for how the deck plays and what this
plan encodes.
"""

from __future__ import annotations

from commanderblitz.engine.costs import available_mana
from commanderblitz.engine.enums import ActionKind, Step

from ..archetypes import Landfall, cast_card
from ..base import Combo, DeckPlan
from ..board import creatures

#: The overruns: a pump for the whole team, worthless on an empty board.
OVERRUNS = frozenset({"craterhoof_behemoth", "overwhelming_stampede"})
#: How many creatures make an overrun worth casting.
OVERRUN_BOARD = 4


def extra_drops(card) -> bool:
    """Exploration, Azusa, Dryad, Oracle: a static that adds land drops."""
    return any(
        ability.static and ability.static.get("effect") == "extra_land_drops"
        for ability in card.abilities
    )


def landfall_payoff(card) -> bool:
    """A permanent with a "whenever a land you control enters" trigger."""
    for ability in card.abilities:
        trigger = ability.trigger
        if (
            trigger is not None
            and trigger.event == "permanent_enters"
            and trigger.controller == "you"
            and "Land" in ((trigger.filter or {}).get("types") or ())
        ):
            return True
    return False


class LanderCommander(Landfall):
    """Landfall, with the sequencing the deck lives on."""

    #: Over the "other" floor so a one-mana Exploration goes down before a
    #: three-drop eats the mana -- every turn without it is a lost land.
    drop_bonus = 120.0
    payoff_bonus = 50.0

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        if action.kind is ActionKind.PLAY_LAND and value > 0:
            return self._land_value(state, seat, value)
        card = cast_card(state, action)
        if card is None or value <= 0:
            return value
        if card.id in OVERRUNS:
            return self._overrun_value(state, seat, card, value)
        if extra_drops(card):
            value += self.drop_bonus
        if landfall_payoff(card):
            value += self.payoff_bonus
        return value

    def _land_value(self, state, seat, value):
        # A payoff cast first sees this land enter: Lotus Cobra pays for
        # itself, Tatyova draws, Baloths makes a 4/4. Hold the drop (it stays
        # the best play once nothing affordable is left to cast first).
        # Only an approximation of "castable" -- if colours rule the payoff
        # out, its cast is not legal and the land is still the best action.
        mana = available_mana(state, seat)
        if any(
            landfall_payoff(card) and self._cost(state, seat, oid, card) <= mana
            for oid, card in self._castable_cards(state, seat)
        ):
            return min(value, 250.0)
        return value

    def _castable_cards(self, state, seat):
        player = state.players[seat]
        for oid in (*player.hand, *player.command):
            obj = state.objects.get(oid)
            if obj is not None:
                yield oid, state.card_of(obj)

    def _cost(self, state, seat, oid, card):
        tax = state.players[seat].commander_tax.get(oid, 0)
        return card.mana_value + 2 * tax

    def _overrun_value(self, state, seat, card, value):
        board = len(creatures(state, seat))
        wide = board >= OVERRUN_BOARD
        if card.id == "overwhelming_stampede":
            # A sorcery that only matters before attackers are declared.
            if not wide or state.step is not Step.PRECOMBAT_MAIN:
                return 0.0
            return value + 300.0
        # Craterhoof is still a hasty 5/5 -- cast it late as a body, but on a
        # wide board it is the turn the game ends.
        return value + 250.0 if wide else value - 150.0


STRATEGY = LanderCommander(
    DeckPlan(
        deck_id="aesi_tyrant_of_gyre_strait",
        archetype="landfall",
        commanders=frozenset({"aesi_tyrant_of_gyre_strait"}),
        key_cards={
            # The engine itself: an extra drop and a card per land.
            "aesi_tyrant_of_gyre_strait": 100.0,
            "tatyova_benthic_druid": 60.0,
            "ancient_greenwarden": 60.0,
            "avenger_of_zendikar": 60.0,
            "rampaging_baloths": 40.0,
            "lotus_cobra": 40.0,
            "rhystic_study": 120.0,
            "burgeoning": 80.0,
            "sol_ring": 250.0,
            "simic_signet": 150.0,
        },
        combos=(
            # A board of plants that grows with each land, then pumped by X.
            Combo(
                "Avenger into Craterhoof",
                frozenset({"avenger_of_zendikar", "craterhoof_behemoth"}),
                150.0,
            ),
            # Greenwarden doubles every landfall trigger the deck owns.
            Combo(
                "Greenwarden and Avenger",
                frozenset({"ancient_greenwarden", "avenger_of_zendikar"}),
                100.0,
            ),
        ),
        win_cons=frozenset({"craterhoof_behemoth", "overwhelming_stampede", "avenger_of_zendikar"}),
        protect=frozenset({"tatyova_benthic_druid", "ancient_greenwarden"}),
        # Six lands and a drop multiplier is a hand this deck wants.
        keep_lands=(2, 6),
        aggression=0.4,
    )
)
