"""Giada, Font of Hope: Giada first, then an air force that gets bigger each cast.

Choir Practice is mono-white angels. Giada costs two and every Angel after
her enters with a +1/+1 counter for each Angel already on the table, so she
is the first creature this deck wants and the order after her is "as many
angels as possible". Lifegain is the second engine -- Lyra Dawnbringer gives
the team lifelink, Archangel of Thune and Lyra, Archangel of Dawn turn each
life gained into counters, and Angel of Destiny wins outright from 55 life.
See docs/cpus/giada_font_of_hope.md for how the deck plays and what this plan
encodes.
"""

from __future__ import annotations

from ..archetypes import Tribal, cast_card
from ..base import Combo, DeckPlan

GIADA = "giada_font_of_hope"
#: The turn after which a rock or a cost reducer is no better than a body.
SETUP_UNTIL = 6


def sets_up(card) -> bool:
    """A mana rock or an Angel cost reducer -- what the curve is built on."""
    if card.is_land or card.is_creature:
        return False
    if card.mana_abilities():
        return True
    return any(
        ability.static and "affects_spells" in ability.static for ability in card.abilities
    )


class ChoirPractice(Tribal):
    """Tribal angels, with Giada ahead of the choir.

    Giada's counters count the Angels already there, so every Angel cast
    before her is a counter thrown away. Her key-card bonus puts her over any
    Angel in hand; `setup` puts the rocks and Herald's Horn / Urza's Incubator
    ahead of a three-drop while the game is young, because each one is an
    extra Angel a turn for the rest of it.
    """

    tribe = "Angel"

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is None or value <= 0:
            return value
        if sets_up(card) and state.turn <= SETUP_UNTIL:
            value = max(value, 440.0 - 10.0 * state.turn)
        return value


STRATEGY = ChoirPractice(
    DeckPlan(
        deck_id="giada_font_of_hope",
        archetype="tribal",
        commanders=frozenset({GIADA}),
        key_cards={
            # Over any Angel in hand: a 3-drop Angel scores about 390 here,
            # Giada about 530.
            GIADA: 150.0,
            "lyra_dawnbringer": 60.0,
            "archangel_of_thune": 70.0,
            "angel_of_destiny": 40.0,
            "lyra_archangel_of_dawn": 40.0,
            "cathars_crusade": 150.0,
            "court_of_grace": 150.0,
            "vanquishers_banner": 120.0,
            "elesh_norn_grand_cenobite": 50.0,
            "avacyn_angel_of_hope": 50.0,
        },
        combos=(
            # Every lifelinking Angel's damage is a Thune trigger: the whole
            # team grows on each hit.
            Combo(
                "Lyra and Thune",
                frozenset({"lyra_dawnbringer", "archangel_of_thune"}),
                150.0,
            ),
            # Lifelink on every Angel is how Destiny's 55-life clock is reached.
            Combo(
                "Lyra and Destiny",
                frozenset({"lyra_dawnbringer", "angel_of_destiny"}),
                120.0,
            ),
        ),
        win_cons=frozenset({"angel_of_destiny", "archangel_of_thune", "cathars_crusade"}),
        protect=frozenset({"lyra_dawnbringer", "herald_s_horn", "urza_s_incubator"}),
        keep_lands=(2, 5),
        aggression=0.6,
    )
)
