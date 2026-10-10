"""Atraxa, Praetors' Voice ("Superfriends"): a table of planeswalkers, proliferated to their ultimates.

Thirty-odd planeswalkers, and Atraxa proliferates every end step: each one
ticks up a loyalty for free, so the deck lands walkers early, plusses them, and
lets proliferate carry them to the ultimates. Doubling Season, Inexorable Tide,
Flux Channeler and Tekuthal multiply that. The plan is the Superfriends
archetype with proliferate priced by what it would grow, and one guard the
archetype lacks: Jace, Memory Adept's ultimate is a win aimed at short
libraries and a loss aimed at ourselves.

See docs/cpus/atraxa_praetors_voice.md for how the deck plays and what this
plan encodes.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars

from ..archetypes import Superfriends, activated_ability, cast_card
from ..base import Combo, DeckPlan
from ..board import card_ops, incoming_unblocked

#: Counter kinds that hurt the permanent they are on (the agent's own list).
HARMFUL_COUNTERS = frozenset({"-1/-1", "stun"})
#: Permanents that turn every spell or end step into more proliferate.
ENGINES = frozenset(
    {"doubling_season", "inexorable_tide", "flux_channeler", "tekuthal_inquiry_dominus", "brokers_ascendancy"}
)
JACE_ADEPT = "jace_memory_adept"
PROTECTION = "teferi_s_protection"
JACE_DRAW = 20


def growing(state, seat: int) -> int:
    """How many things one proliferate would grow for us right now.

    Our permanents carrying only helpful counters, plus each opponent with
    poison (Ajani's emblem and Viral Drake put it there).
    """
    mine = sum(
        1
        for o in state.battlefield_objects(seat)
        if any(n > 0 for n in o.counters.values())
        and not any(o.counters.get(kind, 0) > 0 for kind in HARMFUL_COUNTERS)
    )
    poisoned = sum(1 for pid in state.opponents(seat) if state.players[pid].poison > 0)
    return mine + poisoned


def walkers(state, seat: int) -> int:
    return sum(1 for o in state.battlefield_objects(seat) if "Planeswalker" in chars(state, o.oid).types)


class Proliferate(Superfriends):
    """Superfriends, with proliferate and its engines priced by the board."""

    walker_bonus = 150.0

    def priority_value(self, state, seat, action, base):
        source = state.objects.get(action.source) if action.source is not None else None
        if source is not None and source.def_id == JACE_ADEPT and action.ability_index == 2:
            return self._jace_ultimate(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and card.id == PROTECTION:
            # The agent would cast it at sorcery speed for nothing. It is the
            # answer to the swing that kills us, so it waits for that swing.
            lethal = incoming_unblocked(state, seat) >= state.players[seat].life
            return 600.0 if lethal else 0.0
        value = super().priority_value(state, seat, action, base)
        if value <= 0:
            return value
        if card is not None:
            if "Planeswalker" in card.types:
                # The archetype's bonus still loses to a creature of the same
                # cost (the agent scores creatures from 300); in this deck the
                # walker is the threat and the creature is the support.
                value += self.walker_bonus
            if card.id in ENGINES:
                # Better the more walkers are already out to feed.
                value += 25.0 * walkers(state, seat)
            if "proliferate" in card_ops(card):
                value += 15.0 * growing(state, seat)
        ability = activated_ability(state, action)
        if ability is not None and any(e.get("op") == "proliferate" for e in ability.effects):
            # Karn's Bastion and Viral Drake: four mana to grow nothing is four
            # mana wasted.
            grows = growing(state, seat)
            return value + 15.0 * grows if grows else 0.0
        return value

    def _jace_ultimate(self, state, seat, action, base) -> float:
        """-7: target players draw twenty. Only at opponents it decks."""
        players = [ref.id for ref in action.targets if ref.kind == "player"]
        if base <= 0 or not players or seat in players:
            return 0.0
        if any(len(state.players[pid].library) > JACE_DRAW for pid in players):
            return 0.0  # twenty free cards for somebody with a deep library
        obj = state.objects[action.source]
        if obj.counters.get("loyalty", 0) < 7:
            return 0.0
        # More decked opponents is a better ultimate.
        return 300.0 + 50.0 * len(players)


STRATEGY = Proliferate(
    DeckPlan(
        deck_id="atraxa_praetors_voice",
        archetype="superfriends",
        commanders=frozenset({"atraxa_praetors_voice"}),
        key_cards={
            "atraxa_praetors_voice": 80.0,
            "doubling_season": 120.0,
            "inexorable_tide": 70.0,
            "flux_channeler": 50.0,
            "tekuthal_inquiry_dominus": 60.0,
            "oath_of_gideon": 40.0,
            "oath_of_ajani": 40.0,
            "brokers_ascendancy": 50.0,
            "sol_ring": 80.0,
            "chromatic_lantern": 40.0,
            "call_the_gatewatch": 40.0,
            "deploy_the_gatewatch": 60.0,
        },
        combos=(
            # Teferi's -1 untaps the Veil and three lands, the Veil lets every
            # walker activate again -- the deck's one real loop, given mana.
            Combo("Chain Veil + Teferi", frozenset({"the_chain_veil", "teferi_temporal_archmage"}), 250.0),
        ),
        win_cons=frozenset(
            {
                "vraska_the_unseen",
                "vraska_relic_seeker",
                "elspeth_sun_s_champion",
                "jace_memory_adept",
                "ajani_sleeper_agent",
                "gideon_of_the_trials",
            }
        ),
        protect=frozenset({"doubling_season", "inexorable_tide", PROTECTION}),
        keep_lands=(3, 5),
        aggression=0.4,
    )
)
