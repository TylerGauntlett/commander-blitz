"""Blor the Impervious: ramp into an indestructible, hexproof frog and suit it up.

Blor cannot be targeted by the table and cannot die, so every Equipment and
Aura the deck draws goes on him and stays there. The plan is mana dorks and
land ramp into a turn-three-or-four Blor, then one equip a turn until a single
trampling attack is lethal commander damage. Because nothing kills him, he
blocks too -- the one Voltron commander that should.

See docs/cpus/blor_the_impervious.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword

from ..archetypes import Voltron
from ..base import Combo, DeckPlan

#: One-mana accelerants: a two-land hand with one of these is
#: a three-mana hand on turn two.
FAST_MANA = frozenset(
    {"llanowar_elves", "elvish_mystic", "fyndhorn_elves", "arbor_elf", "delighted_halfling", "sol_ring"}
)


class BlorVoltron(Voltron):
    """Voltron, minus the fear of losing the commander."""

    def block_value(self, state, seat, blocker, attacker, base):
        obj = state.objects.get(blocker)
        if obj is not None and obj.is_commander and _indestructible(state, blocker):
            # Voltron keeps its commander out of blocks so it lives to swing;
            # an indestructible Blor survives every block (deathtouch included)
            # and does not tap for it, so a block is free.
            return base
        return super().block_value(state, seat, blocker, attacker, base)

    def keep_hand(self, state, seat):
        verdict = super().keep_hand(state, seat)
        if verdict is False or state.players[seat].mulligans_taken >= 2:
            return verdict
        hand = [state.card(oid) for oid in state.players[seat].hand]
        lands = sum(1 for card in hand if card.is_land)
        # A five-drop commander: two lands is only a keep with a dork or Sol Ring to
        # accelerate it.
        if lands == 2 and not any(card.id in FAST_MANA for card in hand):
            return state.players[seat].mulligans_taken >= 1
        return verdict


def _indestructible(state, oid: int) -> bool:
    return Keyword.INDESTRUCTIBLE.value in chars(state, oid).keywords


STRATEGY = BlorVoltron(
    DeckPlan(
        deck_id="blor_the_impervious",
        archetype="voltron",
        commanders=frozenset({"blor_the_impervious"}),
        key_cards={
            # Ramp: Blor on turn three or four is the whole game plan.
            "sol_ring": 80.0,
            "nature_s_lore": 50.0,
            "three_visits": 50.0,
            "utopia_sprawl": 40.0,
            "wild_growth": 40.0,
            # The equipment that turns one hit into a kill.
            "commander_s_plate": 70.0,
            "sword_of_fire_and_ice": 70.0,
            "swordsman_s_steel": 60.0,
            "bone_sabres": 50.0,
            "genji_glove": 50.0,
            "inquisitor_s_flail": 50.0,
            "power_fist": 40.0,
            # Auras on an untargetable commander cannot be two-for-oned.
            "strong_back": 60.0,
            "bear_umbra": 50.0,
            "level_up": 40.0,
            # Berserk's "destroy it" clause does nothing to Blor.
            "berserk": 60.0,
            "rishkar_s_expertise": 40.0,
        },
        combos=(
            # Double strike and doubled damage: four times Blor's power in one
            # combat, which with two or three equipment is 21 commander damage.
            Combo(
                name="doubled double strike",
                pieces=frozenset({"genji_glove", "inquisitor_s_flail"}),
                bonus=120.0,
            ),
        ),
        win_cons=frozenset({"blor_the_impervious"}),
        protect=frozenset({"commander_s_plate", "strong_back", "sword_of_fire_and_ice"}),
        keep_lands=(2, 5),
        aggression=0.7,
    )
)
