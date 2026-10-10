"""Edgar Markov: every Vampire spell is two bodies, and every body is a point of drain.

Eminence makes a 1/1 Vampire whenever the deck casts a Vampire, even with Edgar
still in the command zone, so the cheap Vampires come down first and the board
is wide before Edgar arrives with haste to put a counter on all of it. The
bodies are fuel: Blood Artist, Cruel Celebrant and Bastion of Remembrance drain
on every death, Grave Pact and Anowon turn the sacrifices into removal, and
Bloodthirsty Conqueror with Vito or Marauding Blight Priest drains the table
out in one loop.

See docs/cpus/edgar_markov.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars, creature_types_of

from ..archetypes import Tribal, activated_ability, cast_card, target_objects
from ..base import Combo, DeckPlan
from ..board import creatures

TRIBE = "Vampire"


class VampireAristocrats(Tribal):
    """Vampire tribal that treats its tokens as ammunition."""

    tribe = TRIBE
    clamp_bonus = 60.0
    #: Olivia's Wrath waits for a board it is one-sided against: this many
    #: more non-Vampire creatures across the table than on our side.
    wrath_margin = 3

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and card.id == "olivia_s_wrath" and value > 0:
            theirs = sum(_outsiders(state, pid) for pid in state.opponents(seat))
            if theirs - _outsiders(state, seat) < self.wrath_margin:
                return 0.0
            return value + 150.0
        ability = activated_ability(state, action)
        if (
            ability is not None
            and ability.is_equip
            and value > 0
            and state.objects[action.source].def_id == "skullclamp"
        ):
            targets = target_objects(state, action)
            # +1/-1 on an X/1 token is two cards for a body that was going to
            # be sacrificed anyway (and a drain trigger on the way out).
            if targets and state.objects[targets[0]].is_token and chars(state, targets[0]).toughness <= 1:
                value += self.clamp_bonus
        return value

    def junk_value(self, state, seat, oid, base):
        value = super().junk_value(state, seat, oid, base)
        obj = state.objects.get(oid)
        if obj is not None and (obj.is_token or state.card_of(obj).is_token):
            # The 1/1s eminence makes are the sacrifice fodder; a token that
            # is not a Vampire misses the lords and goes before one that is.
            value += 3.0 if TRIBE in creature_types_of(state, oid) else 4.0
        return value


def _outsiders(state, pid: int) -> int:
    """Creatures Olivia's Wrath shrinks: everything that is not a Vampire."""
    return sum(1 for o in creatures(state, pid) if TRIBE not in creature_types_of(state, o.oid))


STRATEGY = VampireAristocrats(
    DeckPlan(
        deck_id="edgar_markov",
        archetype="tribal",
        commanders=frozenset({"edgar_markov"}),
        key_cards={
            "sol_ring": 80.0,
            # Lords: every eminence token is a 2/2 or better.
            "legion_lieutenant": 40.0,
            "stromkirk_captain": 50.0,
            "captivating_vampire": 40.0,
            "edgar_charmed_groom_edgar_markov_s_coffin": 40.0,
            # Drain on death: the sacrifice half of the deck.
            "blood_artist": 50.0,
            "cruel_celebrant": 50.0,
            "bastion_of_remembrance": 40.0,
            "vein_ripper": 60.0,
            "grave_pact": 60.0,
            "bloodline_keeper": 60.0,
            "skullclamp": 50.0,
            "impact_tremors": 30.0,
            "sanctum_seeker": 40.0,
        },
        combos=(
            # Each opponent losing life gains us life; each gain drains again.
            # Either pairing loops until the table is dead.
            Combo(
                name="Vito and the Conqueror",
                pieces=frozenset({"vito_thorn_of_the_dusk_rose", "bloodthirsty_conqueror"}),
            ),
            Combo(
                name="Blight Priest and the Conqueror",
                pieces=frozenset({"marauding_blight_priest", "bloodthirsty_conqueror"}),
            ),
        ),
        win_cons=frozenset({"vein_ripper", "grave_pact", "bloodthirsty_conqueror"}),
        protect=frozenset({"blood_artist", "cruel_celebrant", "bastion_of_remembrance", "skullclamp"}),
        keep_lands=(2, 5),
        aggression=0.7,
    )
)
