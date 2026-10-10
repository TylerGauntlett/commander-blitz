"""Vivi Ornitier: every noncreature spell is a counter on Vivi and a ping to the table.

Vivi is the engine and the mana: each noncreature spell grows her and deals 1
to every opponent, and her {0} ability turns that power back into mana. So the
plan is Vivi on turn three, Curiosity or Ophidian Eye on *her* (each ping is
then a card per opponent), Winged Boots to keep her alive, and a stream of
cheap cantrips. The magecraft creatures and the trigger doublers (Harmonic
Prodigy, Veyran) multiply it; Aetherflux Reservoir or Chandra's Ignition off a
huge Vivi ends it.

See docs/cpus/vivi_ornitier.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind

from ..archetypes import Spellslinger, activated_ability, cast_card, target_objects
from ..base import Combo, DeckPlan
from ..board import commander_oids, power, walk_effects

VIVI = "vivi_ornitier"
#: "Whenever enchanted creature deals damage to an opponent, draw": on Vivi,
#: every noncreature spell draws a card per opponent. On anything else, a
#: fraction of that.
PINGER_AURAS = frozenset({"curiosity", "ophidian_eye"})
#: Ops that are bad news for the permanent they point at.
HARMFUL_OPS = frozenset({"damage", "destroy", "exile", "return_to_hand", "put_on_library", "shuffle_into_library"})
#: What a noncreature spell is worth on top of its own effect while Vivi is
#: out: a +1/+1 counter, a point to each opponent, and a mana next turn.
VIVI_TRIGGER = 25.0
#: Chandra's Ignition is only a finisher off a big creature.
IGNITION_FLOOR = 4


class ViviSpellslinger(Spellslinger):
    """Spellslinger, built around a commander that rewards *every* noncreature spell."""

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        if value <= 0:
            return value
        if action.kind is ActionKind.CAST:
            return self._cast_value(state, seat, action, value)
        ability = activated_ability(state, action)
        if ability is None:
            return value
        card = state.card_of(state.objects[action.source])
        if ability.is_equip:
            return self._equip_value(state, seat, action, card.id, value)
        if card.id == "aetherflux_reservoir" and ability.cost is not None and ability.cost.pay_life:
            # Fifty damage: the base agent fires it at whatever came first. It
            # is only ever a kill on an opponent; at a creature it is a waste
            # of the deck's win condition.
            players = [ref.id for ref in action.targets if ref.kind == "player"]
            return value + 1000.0 if players and players[0] != seat else 0.0
        return value

    def _cast_value(self, state, seat, action, value):
        card = cast_card(state, action)
        vivi = _vivi(state, seat)
        if _hurts_own(state, seat, action, card):
            # "Deals 3 damage to target creature" with only our own creatures
            # to point at is a pass, not a Lightning Bolt to the face of Vivi.
            return 0.0
        if card.id in PINGER_AURAS:
            targets = target_objects(state, action)
            if vivi is None or not targets or targets[0] != vivi:
                return 0.0  # held until Vivi is out to wear it
            value += 120.0
        if card.id == "chandra_s_ignition":
            targets = target_objects(state, action)
            hitter = power(state, targets[0]) if targets else 0
            if hitter < IGNITION_FLOOR:
                return 0.0
            value += hitter * 10.0
        if vivi is not None and not card.is_creature:
            value += VIVI_TRIGGER
        return value

    def _equip_value(self, state, seat, action, card_id, value):
        if card_id != "winged_boots":
            return value
        vivi = _vivi(state, seat)
        targets = target_objects(state, action)
        if vivi is None or not targets:
            return value
        boots = state.objects.get(action.source)
        if targets[0] != vivi or (boots is not None and boots.attached_to == vivi):
            # Ward 4 is the deck's only protection for its engine: it belongs
            # on Vivi and stays there.
            return 0.0
        return value + 100.0


def _vivi(state, seat: int) -> int | None:
    for oid in commander_oids(state, seat):
        if state.objects[oid].def_id == VIVI:
            return oid
    return None


def _hurts_own(state, seat: int, action, card) -> bool:
    """Is this spell pointing something harmful at one of our own permanents?

    Removal is already vetoed at our board by the agent; burn and bounce are
    not, because they classify as "other". Spells that *ask* for our creature
    (Chandra's Ignition) say so in their target spec and are left alone.
    """
    if any((spec.selector or {}).get("controller") == "you" for spec in card.targets):
        return False
    ops = {effect.get("op") for effect in walk_effects(card.spell_effects)}
    if not ops & HARMFUL_OPS:
        return False
    return any(state.objects[oid].controller == seat for oid in target_objects(state, action))


STRATEGY = ViviSpellslinger(
    DeckPlan(
        deck_id="vivi_ornitier",
        archetype="spellslinger",
        commanders=frozenset({VIVI}),
        key_cards={
            # The commander is the engine and the mana: out on turn three.
            VIVI: 120.0,
            "curiosity": 60.0,
            "ophidian_eye": 50.0,
            "winged_boots": 40.0,
            # Card advantage that keeps the spells coming.
            "rhystic_study": 60.0,
            "archmage_emeritus": 40.0,
            "archmage_of_runes": 40.0,
            # Each one doubles every Vivi trigger an instant or sorcery causes.
            "harmonic_prodigy": 40.0,
            "veyran_voice_of_duality": 50.0,
            # Pingers and payoffs that turn the spell count into damage.
            "exalted_flamer_of_tzeentch": 30.0,
            "caldera_pyremaw": 30.0,
            "storm_kiln_artist": 30.0,
            "aetherflux_reservoir": 40.0,
        },
        combos=(
            # Vivi's ping is damage to an opponent: with Curiosity on her each
            # noncreature spell draws a card per opponent.
            Combo(name="Vivi draws off her own pings", pieces=frozenset({VIVI, "curiosity"}), bonus=200.0),
            Combo(name="Vivi with Ophidian Eye", pieces=frozenset({VIVI, "ophidian_eye"}), bonus=150.0),
            # Vivi is a Wizard: Prodigy doubles her trigger -- two counters and
            # two damage to each opponent per spell.
            Combo(name="doubled Vivi", pieces=frozenset({VIVI, "harmonic_prodigy"}), bonus=120.0),
            Combo(name="Veyran doubles Vivi", pieces=frozenset({VIVI, "veyran_voice_of_duality"}), bonus=120.0),
        ),
        win_cons=frozenset({"aetherflux_reservoir", "chandra_s_ignition", "crackle_with_power"}),
        protect=frozenset({"rhystic_study", "winged_boots"}),
        keep_lands=(2, 5),
        aggression=0.4,
    )
)
