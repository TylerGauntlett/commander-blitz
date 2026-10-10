"""Isperia, Supreme Judge: fly over, and make attacking this seat a mistake.

Isperia draws a card for every creature that attacks her controller, so the
deck is built to survive being attacked: counterspells for the big threats,
two wraths and Evacuation for a board that gets out of hand, Angel of the Dire
Hour for the alpha strike, and Bident of Thassa to *force* the attacks that
draw the cards. The fliers win the game while that happens -- ground
creatures stay home, where they block.

See docs/cpus/isperia.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step

from ..archetypes import Control, activated_ability, cast_card, main_phase_mine
from ..base import Combo, DeckPlan
from ..board import can_attack_soon, commander_oids, creatures, power

ISPERIA = "isperia_supreme_judge"
#: One-sided only when the other side has more on it.
SWEEPERS = frozenset({"wrath_of_god", "day_of_judgment", "evacuation"})
#: How far behind on board before a sweeper is worth our own creatures.
SWEEP_MARGIN = 8
#: Attacking power across the table that makes Angel of the Dire Hour (or
#: Evacuation) worth flashing in mid-combat.
BLOWOUT_POWER = 5
#: Steps of an opponent's turn when Bident's "attack this turn" still applies.
BEFORE_COMBAT = frozenset({Step.UPKEEP, Step.DRAW, Step.PRECOMBAT_MAIN, Step.BEGIN_COMBAT})


class IsperiaControl(Control):
    """Control that wants the table to attack it, and punishes the attack."""

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None:
            if card.id in SWEEPERS:
                return self._sweeper_value(state, seat, card.id, value)
            if card.id == "angel_of_the_dire_hour":
                return self._dire_hour_value(state, seat, value)
        ability = activated_ability(state, action)
        if (
            ability is not None
            and action.kind is ActionKind.ACTIVATE
            and state.card_of(state.objects[action.source]).id == "bident_of_thassa"
            and any(effect.get("op") == "must_attack" for effect in ability.effects)
        ):
            return self._bident_value(state, seat)
        return value

    def _sweeper_value(self, state, seat, card_id, value):
        if card_id == "evacuation" and _blowout(state, seat):
            return 600.0  # every attacker back to hand, mid-swing
        if value <= 0:
            return value
        theirs = sum(_worth(state, o) for pid in state.opponents(seat) for o in creatures(state, pid))
        ours = sum(_worth(state, o) for o in creatures(state, seat))
        # The base agent casts a wrath whenever nothing scores higher -- which
        # is often "our board of fliers and nothing on theirs". It is only a
        # good card when it kills more of theirs than ours.
        if theirs < ours + SWEEP_MARGIN:
            return 0.0
        return max(value, 380.0) + (theirs - ours)

    def _dire_hour_value(self, state, seat, value):
        if _blowout(state, seat):
            return 900.0  # flashed in: exile every attacking creature
        if main_phase_mine(state, seat) and value > 0:
            # A 5/4 flier is fine; the same card exiling a whole alpha strike is
            # game-winning. Hold it while the table has creatures that could
            # make that attack.
            threats = [
                o for pid in state.opponents(seat) for o in creatures(state, pid) if can_attack_soon(state, o)
            ]
            if len(threats) >= 2:
                return 0.0
        return value

    def _bident_value(self, state, seat):
        # Forced attacks are only good on an opponent's turn (on ours they do
        # nothing), only with Isperia out to draw off them, and only when the
        # active player's whole team cannot kill us.
        active = state.active_player
        if active == seat or state.step not in BEFORE_COMBAT:
            return 0.0
        if not any(state.objects[oid].def_id == ISPERIA for oid in commander_oids(state, seat)):
            return 0.0
        swing = sum(power(state, o.oid) for o in creatures(state, active) if can_attack_soon(state, o))
        if swing * 2 >= state.players[seat].life:
            return 0.0
        return 60.0


def _blowout(state, seat: int) -> bool:
    """Is an opponent's attack big enough to answer with the whole board?"""
    combat = state.combat
    if combat is None or state.active_player == seat:
        return False
    if state.step not in (Step.DECLARE_ATTACKERS, Step.DECLARE_BLOCKERS):
        return False
    swinging = sum(power(state, oid) for oid in combat.attackers)
    return swinging >= BLOWOUT_POWER


def _worth(state, obj) -> float:
    """Rough creature value for a sweeper: power plus cost, double a commander."""
    value = power(state, obj.oid) + state.card_of(obj).mana_value
    return value * 2 if obj.is_commander else value


STRATEGY = IsperiaControl(
    DeckPlan(
        deck_id="isperia",
        archetype="control",
        commanders=frozenset({ISPERIA}),
        key_cards={
            ISPERIA: 100.0,
            # Card advantage that ends games by itself.
            "consecrated_sphinx": 80.0,
            "windreader_sphinx": 40.0,
            "reconnaissance_mission": 40.0,
            # The air force and what makes it bigger and cheaper.
            "empyrean_eagle": 50.0,
            "watcher_of_the_spheres": 40.0,
            "warden_of_evos_isle": 30.0,
            "lyra_dawnbringer": 40.0,
            "archangel_of_thune": 40.0,
            "sphinx_of_magosi": 30.0,
            "bident_of_thassa": 40.0,
        },
        combos=(
            # Lyra gives Thune lifelink; every hit grows the whole team.
            Combo(
                name="lifelinking Thune",
                pieces=frozenset({"lyra_dawnbringer", "archangel_of_thune"}),
                bonus=150.0,
            ),
            # Bident forces the attacks; Isperia draws a card off each.
            Combo(
                name="forced attacks draw cards",
                pieces=frozenset({ISPERIA, "bident_of_thassa"}),
                bonus=100.0,
            ),
        ),
        win_cons=frozenset({"consecrated_sphinx", "lyra_dawnbringer", "windreader_sphinx", "sphinx_of_magosi"}),
        protect=frozenset({"wrath_of_god", "day_of_judgment", "angel_of_the_dire_hour"}),
        keep_lands=(2, 5),
        aggression=0.3,
    )
)
