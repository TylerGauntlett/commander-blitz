"""How a kind of deck plays, on top of the baseline.

Each archetype overrides only the hooks its plan cares about and defers to
:class:`DefaultStrategy` for everything else, so a Voltron deck still never
walks its commander into a bigger blocker -- it just wants to equip it first.

A deck's own module (``decks/<id>.py``) picks one of these, gives it a
:class:`DeckPlan` naming the cards that matter, and occasionally subclasses it
for a rule only that deck has.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.enums import ActionKind, Step

from .board import (
    EVASION,
    blockers_for,
    card_ops,
    classify,
    commander_oids,
    crack_back,
    creatures,
    is_token_maker,
    power,
)
from .default import DefaultStrategy

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.actions import Action
    from automtg.engine.carddef import Ability, CardDef
    from automtg.engine.state import GameState


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def cast_card(state: GameState, action: Action) -> CardDef | None:
    if action.kind is not ActionKind.CAST or action.source is None:
        return None
    return state.card(action.source)


def activated_ability(state: GameState, action: Action) -> Ability | None:
    if action.kind is not ActionKind.ACTIVATE or action.source is None or action.ability_index is None:
        return None
    abilities = abilities_of(state, action.source)
    if not 0 <= action.ability_index < len(abilities):
        return None
    return abilities[action.ability_index]


def _attaches(ability: Ability) -> bool:
    """Equip, or an attach that is not flagged as one (reconfigure)."""
    return ability.is_equip or any(effect.get("op") == "attach" for effect in ability.effects)


def target_objects(state: GameState, action: Action) -> list[int]:
    return [ref.id for ref in action.targets if ref.kind == "object" and ref.id in state.objects]


def main_phase_mine(state: GameState, seat: int) -> bool:
    return state.active_player == seat and state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)


def is_evasive(state: GameState, oid: int) -> bool:
    return bool(EVASION & chars(state, oid).keywords)


# ----------------------------------------------------------------------
# creature decks
# ----------------------------------------------------------------------


class Aggro(DefaultStrategy):
    """Pressure first: creatures early, trades accepted, the weakest seat attacked."""

    name = "aggro"
    #: Extra weight on a creature cast, scaled down as the game goes long.
    creature_bonus = 30.0

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and card.is_creature:
            value += max(0.0, self.creature_bonus - state.turn)
        return value


class GoWide(Aggro):
    """Many bodies, then an anthem, then everybody swings.

    Token makers outrank a lone big creature; once the board is wide enough
    that the blockers cannot stop most of it, the swing is on even without
    lethal.
    """

    name = "go_wide"
    #: How many creatures make "wide".
    wide = 5

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and is_token_maker(card):
            value += 40.0
        return value

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        if value > 0 or power(state, oid) <= 0:
            return value
        ours = creatures(state, seat)
        theirs = blockers_for(state, oid, defender)
        if len(ours) >= self.wide and len(ours) >= 2 * max(1, len(theirs)):
            # The blockers can stop a few; the rest gets through. A small body
            # lost to a block is the price of the swing -- unless the swing
            # leaves nothing home for theirs.
            declared = set(state.combat.attackers) if state.combat is not None else set()
            if crack_back(state, seat, declared | {oid}) >= state.players[seat].life:
                return value
            return 0.5
        return value


class Aristocrats(GoWide):
    """Tokens are fodder: sacrifice them first, drain the lowest life total."""

    name = "aristocrats"

    def junk_value(self, state, seat, oid, base):
        value = super().junk_value(state, seat, oid, base)
        obj = state.objects.get(oid)
        if obj is not None and state.card_of(obj).is_token:
            value += 3.0
        return value


class Voltron(DefaultStrategy):
    """One big threat: the commander, suited up, aimed at one player.

    Equipment and Auras go on the commander; the commander attacks whenever it
    survives the block; the rest of the board stays home to defend it.
    """

    name = "voltron"
    equip_bonus = 150.0
    aura_bonus = 120.0

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        commanders = set(commander_oids(state, seat))
        ability = activated_ability(state, action)
        if ability is not None and _attaches(ability):
            targets = target_objects(state, action)
            equipment = state.objects.get(action.source)
            if not targets or value <= 0:
                return value
            if equipment is not None and equipment.attached_to == targets[0]:
                # Re-equipping onto the creature already wearing it is legal and
                # does nothing; scored above zero, it is an infinite loop.
                return 0.0
            if targets[0] in commanders:
                return value + self.equip_bonus
            if equipment is not None and equipment.attached_to in commanders:
                return 0.0  # never strip the commander
            return value if commanders else value + 10.0
        card = cast_card(state, action)
        if card is not None and value > 0 and "Aura" in card.subtypes:
            targets = target_objects(state, action)
            if targets and targets[0] in commanders:
                value += self.aura_bonus
            elif targets and state.objects[targets[0]].controller == seat:
                value += 10.0
        if card is not None and value > 0 and "Equipment" in card.subtypes:
            value += 40.0
        return value

    def defender(self, state, seat, default):
        commanders = commander_oids(state, seat)
        if not commanders:
            return super().defender(state, seat, default)
        lead = commanders[0]
        opponents = state.opponents(seat)
        # Who has taken the most from it already, then who can block it least.
        return min(
            opponents,
            key=lambda pid: (
                -state.players[pid].commander_damage_taken.get(seat, 0),
                len(blockers_for(state, lead, pid)),
                state.players[pid].life,
                pid,
            ),
        )

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        obj = state.objects[oid]
        if obj.is_commander:
            return value + 10.0 if value > 0 else value
        # The rest of the team guards the commander's back unless free.
        if value > 0 and blockers_for(state, oid, defender):
            return 0.0
        return value

    def block_value(self, state, seat, blocker, attacker, base):
        obj = state.objects.get(blocker)
        if obj is not None and obj.is_commander and base < 10:
            return 0.0
        return super().block_value(state, seat, blocker, attacker, base)


class Tribal(GoWide):
    """A creature type that rewards more of itself."""

    name = "tribal"
    tribe = ""
    tribe_bonus = 35.0

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and self.tribe and self.tribe in card.subtypes:
            value += self.tribe_bonus
        return value


class Dragons(Tribal):
    """Ramp hard, land big fliers, let them do the work."""

    name = "dragons"
    tribe = "Dragon"
    wide = 4

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and classify(card) == "ramp" and state.turn <= 12:
            value += 80.0
        return value


# ----------------------------------------------------------------------
# value and engine decks
# ----------------------------------------------------------------------


class Landfall(DefaultStrategy):
    """Lands are the spells: extra drops, fetches and ramp come first."""

    name = "landfall"

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0:
            ops = card_ops(card)
            if ops & {"extra_land_drop", "search_library", "put_onto_battlefield"}:
                value += 60.0
        return value

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        # Landfall creatures grow on our turn and block on theirs: only swing
        # with what the defender cannot block.
        if value > 0 and blockers_for(state, oid, defender) and self.plan.aggression < 0.5:
            return 0.0
        return value


class Superfriends(DefaultStrategy):
    """Planeswalkers first, loyalty up, minus abilities when they matter."""

    name = "superfriends"

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and "Planeswalker" in card.types:
            value += 120.0
        ability = activated_ability(state, action)
        if ability is not None and ability.cost is not None and ability.cost.loyalty is not None:
            value = self._loyalty_value(state, seat, action, ability, value)
        return value

    def _loyalty_value(self, state, seat, action, ability, value):
        if value <= 0:
            return value
        cost = ability.cost.loyalty
        obj = state.objects.get(action.source)
        loyalty = obj.counters.get("loyalty", 0) if obj is not None else 0
        if cost >= 0:
            return value + 20.0 + cost
        remaining = loyalty + cost
        if remaining <= 0:
            return 0.0  # never kill our own walker for one activation
        # A minus is worth it when it hits something of theirs, or it is the
        # big one and the walker survives it.
        hits_theirs = any(state.objects[t].controller != seat for t in target_objects(state, action))
        if hits_theirs or -cost >= 6:
            return value + 30.0 - cost
        return value  # a plain minus ranks below a plus

    def block_value(self, state, seat, blocker, attacker, base):
        value = super().block_value(state, seat, blocker, attacker, base)
        combat = state.combat
        if combat is not None and attacker in combat.attacking_permanent:
            walker = state.objects.get(combat.attacking_permanent[attacker])
            if walker is not None and walker.controller == seat:
                value = max(value, 3.0)
        return value


class Punisher(DefaultStrategy):
    """Make the table pay for what it does -- and keep the punisher alive."""

    name = "punisher"


class Mill(DefaultStrategy):
    """The opponents' libraries are the life totals."""

    name = "mill"

    def player_score(self, state, seat, pid, intent):
        score = super().player_score(state, seat, pid, intent)
        if intent == "mill":
            # Finish the shortest library first: one decked player is a win in a
            # duel and one fewer opponent in a pod.
            score += max(0.0, 20.0 - len(state.players[pid].library) / 2.0)
        return score


class Spellslinger(DefaultStrategy):
    """Instants and sorceries are the engine; creatures are the payoff."""

    name = "spellslinger"
    spell_bonus = 40.0

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value > 0 and card.types & {"Instant", "Sorcery"}:
            value += self.spell_bonus
            if state.step is Step.PRECOMBAT_MAIN:
                value += 10.0  # triggers that pump attackers want the spell first
        return value


class Control(DefaultStrategy):
    """Answer what matters, attack only where nobody can block."""

    name = "control"
    #: The cheapest opposing spell worth a counterspell (the classic agent: 3).
    counter_floor = 2

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None and value <= 0 and classify(card) == "counter":
            value = self._cheap_counter(state, seat, action)
        return value

    def _cheap_counter(self, state, seat, action) -> float:
        for ref in action.targets:
            if ref.kind != "stack":
                continue
            item = state.stack_item(ref.id)
            if item is None or item.controller == seat:
                continue
            if state.registry.get(item.def_id).mana_value >= self.counter_floor:
                return 450.0
        return 0.0

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        if value > 0 and not is_evasive(state, oid) and blockers_for(state, oid, defender):
            return 0.0
        return value
