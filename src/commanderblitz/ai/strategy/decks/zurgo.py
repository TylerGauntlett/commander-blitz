"""Zurgo Stormrender: attack every turn, let the tokens die, drain the table.

Zurgo makes a token every time he attacks, and every creature token that
leaves draws a card (if it was attacking) or drains each opponent (if it was
not). So tokens are never worth protecting: they attack into blockers because a
dead attacker is a card, they are the first thing sacrificed, and the death
payoffs (Bastion of Remembrance, Zulaport Cutthroat, Blood Artist and friends)
turn the whole board into reach. The real creatures stay home unless the
attack is good.

See docs/cpus/zurgo.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind

from ..archetypes import Aristocrats, activated_ability
from ..base import Combo, DeckPlan
from ..board import commander_oids, crack_back, creatures, power

ZURGO = "zurgo_stormrender"


class ZurgoAristocrats(Aristocrats):
    """Aristocrats where an attacking token that dies is a card, not a loss."""

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        obj = state.objects[oid]
        if obj.is_commander and value > 0:
            return value + 5.0  # first in: the mobilize token joins whatever follows
        if value > 0 or power(state, oid) <= 0 or not _zurgo_out(state, seat):
            return value
        if state.card_of(obj).is_token:
            # A token blocked and killed draws a card off Zurgo and fires every
            # death payoff on the way out; unblocked it deals its damage. The
            # only reason to keep it home is the crack-back.
            declared = set(state.combat.attackers) if state.combat is not None else set()
            if crack_back(state, seat, declared | {oid}) < state.players[seat].life:
                return 0.5
        return value

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        ability = activated_ability(state, action)
        if (
            value > 0
            and action.kind is ActionKind.ACTIVATE
            and ability is not None
            and ability.cost is not None
            and _sacrifices_a_creature(ability.cost.sacrifice)
            and not _has_token(state, seat)
        ):
            # Vampiric Rites and Indulgent Aristocrat are fed tokens. With none
            # out the "cheapest" creature is a real card, and a card for a card
            # is no trade at all.
            return 0.0
        return value


def _zurgo_out(state, seat: int) -> bool:
    return any(state.objects[oid].def_id == ZURGO for oid in commander_oids(state, seat))


def _sacrifices_a_creature(selector) -> bool:
    """A cost of "sacrifice a creature", not "sacrifice this" (Evolving Wilds, Mind Stone)."""
    if not selector or selector.get("self_only"):
        return False
    return "Creature" in (selector.get("types") or ())


def _has_token(state, seat: int) -> bool:
    return any(state.card_of(o).is_token for o in creatures(state, seat))


STRATEGY = ZurgoAristocrats(
    DeckPlan(
        deck_id="zurgo",
        archetype="aristocrats",
        commanders=frozenset({ZURGO}),
        key_cards={
            # Three mana, and every turn he is not attacking is a card lost.
            ZURGO: 120.0,
            # Death payoffs: each token that dies becomes a drain.
            "bastion_of_remembrance": 60.0,
            "zulaport_cutthroat": 50.0,
            "cruel_celebrant": 50.0,
            "blood_artist": 50.0,
            "falkenrath_noble": 40.0,
            "dictate_of_erebos": 40.0,
            # Entering is damage too, and the mobilize token enters every attack.
            "impact_tremors": 50.0,
            "hellrider": 40.0,
            "intangible_virtue": 30.0,
            # Lifegain that drains: every Blood Artist trigger doubles up.
            "sanguine_bond": 40.0,
            "epicure_of_blood": 30.0,
        },
        combos=(
            # Each drain gains a life; each life gained is another drain.
            Combo(
                name="every gain is a drain",
                pieces=frozenset({"sanguine_bond", "epicure_of_blood"}),
                bonus=120.0,
            ),
        ),
        win_cons=frozenset(
            {"bastion_of_remembrance", "zulaport_cutthroat", "cruel_celebrant", "blood_artist", "impact_tremors"}
        ),
        protect=frozenset({"falkenrath_noble", "dictate_of_erebos"}),
        keep_lands=(2, 5),
        aggression=0.8,
    )
)
