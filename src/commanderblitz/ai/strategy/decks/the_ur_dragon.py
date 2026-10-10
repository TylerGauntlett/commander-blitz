"""The Ur-Dragon: ramp off dorks and rocks, land big fliers, attack to draw.

Five colours of fast mana -- Hierarchs, Birds, Sol Ring, Mana Vault, the moxen
-- buy a dragon on turn three or four, eminence makes every dragon after it a
mana cheaper, and The Ur-Dragon's attack trigger turns each swing into cards
and a free permanent. The plan reads: mana first, then dragons, then the
damage multipliers (Terror of the Peaks, Scourge of Valkas, Twinflame Tyrant)
that turn every dragon landing into a burn spell. See docs/cpus/the_ur_dragon.md
for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from ..archetypes import Dragons, cast_card
from ..base import Combo, DeckPlan

#: The turn after which a mana rock stops being worth more than a threat.
RAMP_UNTIL = 8


def makes_mana(card) -> bool:
    """A nonland permanent that taps for mana: a rock, a dork, a mox."""
    return not card.is_land and bool(card.mana_abilities())


class UrDragon(Dragons):
    """Dragons, with the deck's real ramp counted as ramp.

    `Dragons` boosts the cards `classify` calls "ramp", which means land
    searches -- and this list runs none. Its acceleration is rocks and dorks,
    which the agent scores as a 100-point "other" or a 0/1 creature, so
    without this the CPU played a Birds of Paradise after the dragon it was
    meant to cast. Early on, a mana source is scored as the ramp it is.
    """

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and makes_mana(card) and state.turn <= RAMP_UNTIL:
            # Above a three-drop, falling away as the turns pass: turn-two
            # Signet beats anything, turn-seven Signet beats a vanilla body.
            value = max(value, 460.0 - 15.0 * state.turn)
        return value

    def keep_hand(self, state, seat):
        player = state.players[seat]
        if player.mulligans_taken >= 2:
            return True
        hand = [state.card(oid) for oid in player.hand]
        lands = sum(1 for card in hand if card.is_land)
        fast = sum(1 for card in hand if makes_mana(card) and card.mana_value <= 2)
        # One land and two cheap mana sources is a fast-mana hand, not a
        # mulligan: Sol Ring and a Hierarch cast the same dragons a land would.
        if lands == 1 and fast >= 2:
            return True
        return super().keep_hand(state, seat)


STRATEGY = UrDragon(
    DeckPlan(
        deck_id="the_ur_dragon",
        archetype="dragons",
        commanders=frozenset({"the_ur_dragon"}),
        key_cards={
            # The commander is the card-advantage engine; cast it as soon as
            # the mana is there.
            "the_ur_dragon": 120.0,
            "dracogenesis": 150.0,
            "tiamat": 80.0,
            "miirym_sentinel_wyrm": 70.0,
            "lathliss_dragon_queen": 60.0,
            "terror_of_the_peaks": 70.0,
            "scourge_of_valkas": 50.0,
            # Two-mana enchantments that score as filler: they want to be down
            # before the dragons they trigger off, not after.
            "dragon_tempest": 200.0,
            "up_the_beanstalk": 120.0,
            "rhythm_of_the_wild": 120.0,
            "temur_ascendancy": 120.0,
            "smothering_tithe": 100.0,
            "the_one_ring": 120.0,
        },
        combos=(
            # Each dragon that lands is X damage per enter trigger; Miirym's
            # copy is another dragon entering.
            Combo(
                "Terror and Miirym",
                frozenset({"terror_of_the_peaks", "miirym_sentinel_wyrm"}),
                150.0,
            ),
            # Lathliss makes a 5/5 dragon for each nontoken dragon: Terror
            # shoots five for every one of them.
            Combo(
                "Lathliss and Terror",
                frozenset({"lathliss_dragon_queen", "terror_of_the_peaks"}),
                150.0,
            ),
            # Draconic Visitor turns every Treasure into a 5/5 flier.
            Combo(
                "Visitor and Goldspan",
                frozenset({"draconic_visitor", "goldspan_dragon"}),
                120.0,
            ),
            Combo(
                "Visitor and Old Gnawbone",
                frozenset({"draconic_visitor", "old_gnawbone"}),
                120.0,
            ),
        ),
        win_cons=frozenset({"terror_of_the_peaks", "scourge_of_valkas", "dracogenesis"}),
        protect=frozenset({"miirym_sentinel_wyrm", "lathliss_dragon_queen"}),
        keep_lands=(2, 5),
        aggression=0.6,
    )
)
