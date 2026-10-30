"""Read-only facts about a position, shared by the agent and every strategy.

Nothing here mutates the state or looks ahead: ADR 0005 rules out cloning, so a
strategy can only reason about the board in front of it. Every helper is a
cheap walk of the battlefield, recomputed per question rather than cached --
a decision is a few dozen actions, and a stale cache across ``Game.apply``
would be a much worse bug than a slow one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

from commanderblitz.engine.characteristics import chars, protected_from
from commanderblitz.engine.combat import block_prohibited, can_block, unblockable
from commanderblitz.engine.costs import produced_symbols
from commanderblitz.engine.enums import Keyword
from commanderblitz.engine.player_statics import block_forbidden

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.engine.carddef import CardDef
    from commanderblitz.engine.objects import GameObject
    from commanderblitz.engine.state import GameState

#: Keywords that make a creature hard to block, for "does this get through".
EVASION = frozenset({"flying", "menace", "shadow", "horsemanship", "fear", "intimidate", "skulk"})

#: What an effect does to the player it is pointed at, by op.
HARMFUL_TO_PLAYER = {
    "mill": "mill",
    "damage": "damage",
    "lose_life": "damage",
    "discard": "discard",
    "add_poison": "damage",
    "sacrifice": "edict",
    "gain_control": "steal",
    "exchange_control": "steal",
    "look_at_hand": "discard",
}
HELPFUL_TO_PLAYER = frozenset(
    {
        "draw",
        "gain_life",
        "create_token",
        "search_library",
        "add_counters",
        "add_energy",
        "untap",
        "extra_turn",
    }
)


# ----------------------------------------------------------------------
# cards
# ----------------------------------------------------------------------


def walk_effects(effects: Iterable[Mapping[str, Any]]) -> Iterator[Mapping[str, Any]]:
    """Every effect, nested ones included (``then``/``else``/modes)."""
    for effect in effects:
        yield effect
        for key in ("then", "else", "effects"):
            yield from walk_effects(effect.get(key) or [])
        for mode in effect.get("modes", []) or []:
            yield from walk_effects(mode.get("effects") or [])


def card_effects(card: CardDef) -> Iterator[Mapping[str, Any]]:
    """A card's spell effects and every ability's effects, walked."""
    yield from walk_effects(card.spell_effects)
    for ability in card.abilities:
        yield from walk_effects(ability.effects)


def card_ops(card: CardDef) -> set[str]:
    return {str(effect.get("op")) for effect in card_effects(card)}


def classify(card: CardDef) -> str:
    """Bucket a card by what it is for, from the ops its spell actually uses."""
    ops = {effect.get("op") for effect in walk_effects(card.spell_effects)}
    if "counter" in ops:
        return "counter"
    if ops & {"destroy", "exile"} and card.targets:
        return "removal"
    if "search_library" in ops:
        return "ramp"
    if ops & {"pump", "grant_keyword"} and card.targets:
        return "pump"
    if "draw" in ops and not card.is_permanent:
        return "draw"
    if card.is_creature:
        return "creature"
    return "other"


def intent_of(effects: Iterable[Mapping[str, Any]]) -> str | None:
    """What these effects mean for a player they are pointed at.

    ``mill``, ``damage``, ``discard``, ``edict`` or ``steal`` for the harmful
    ones, ``help`` for a gift, ``None`` when nothing touches a player.
    Harm wins over help: "target player mills three, then you draw" is aimed at
    an opponent.
    """
    helpful = False
    for effect in walk_effects(effects):
        op = str(effect.get("op"))
        if op in HARMFUL_TO_PLAYER:
            return HARMFUL_TO_PLAYER[op]
        if op in HELPFUL_TO_PLAYER:
            helpful = True
    return "help" if helpful else None


def is_token_maker(card: CardDef) -> bool:
    return "create_token" in card_ops(card)


# ----------------------------------------------------------------------
# board
# ----------------------------------------------------------------------


def creatures(state: GameState, pid: int) -> list[GameObject]:
    return [o for o in state.battlefield_objects(pid) if "Creature" in chars(state, o.oid).types]


def has_keyword(state: GameState, oid: int, keyword: str) -> bool:
    return keyword in chars(state, oid).keywords


def power(state: GameState, oid: int) -> int:
    return max(0, chars(state, oid).power)


def can_attack_soon(state: GameState, obj: GameObject) -> bool:
    """Could this creature swing on its controller's next turn (ignoring tapping)?"""
    return power(state, obj.oid) > 0 and not has_keyword(state, obj.oid, Keyword.DEFENDER.value)


def ready_attackers(state: GameState, pid: int) -> list[GameObject]:
    """Creatures that could be declared as attackers right now."""
    return [
        o
        for o in creatures(state, pid)
        if not o.tapped
        and power(state, o.oid) > 0
        and not has_keyword(state, o.oid, Keyword.DEFENDER.value)
        and (not o.summoning_sick(state.turn) or has_keyword(state, o.oid, Keyword.HASTE.value))
    ]


def untapped_blockers(state: GameState, pid: int) -> list[GameObject]:
    return [o for o in creatures(state, pid) if not o.tapped]


def could_block(state: GameState, blocker: int, attacker: int, defender: int) -> bool:
    """Could ``blocker`` block ``attacker`` if it were declared at ``defender``?

    `combat.can_block` answers only for an attacker already in the declaration,
    so asked while attackers are still being *chosen* it says "no" to every
    blocker -- which is why the classic agent saw an empty board in front of
    every attack and swung into whatever was waiting. This is the same set of
    questions about the two creatures, without the declaration: tapped, can't
    block, unblockable, protection, and the evasion keywords. Landwalk and
    card-specific "can't be blocked by Humans" are left out; they are rare, and
    getting them wrong only makes the agent a little more careful.
    """
    combat = state.combat
    if combat is not None and attacker in combat.attackers:
        return can_block(state, blocker, attacker, defender)
    obj = state.objects.get(blocker)
    if obj is None or obj.tapped or obj.controller != defender:
        return False
    bc, ac = chars(state, blocker), chars(state, attacker)
    if "Creature" not in bc.types:
        return False
    if block_forbidden(state, blocker) or block_prohibited(state, blocker):
        return False
    if Keyword.DECAYED.value in bc.keywords:
        return False
    if unblockable(state, attacker, blocker) or protected_from(state, attacker, blocker):
        return False
    if Keyword.FLYING.value in ac.keywords and not (
        Keyword.FLYING.value in bc.keywords or Keyword.REACH.value in bc.keywords
    ):
        return False
    if Keyword.HORSEMANSHIP.value in ac.keywords and Keyword.HORSEMANSHIP.value not in bc.keywords:
        return False
    if (Keyword.SHADOW.value in ac.keywords) != (Keyword.SHADOW.value in bc.keywords):
        return False
    if Keyword.SKULK.value in ac.keywords and bc.power > ac.power:
        return False
    if "Artifact" not in bc.types:
        if Keyword.FEAR.value in ac.keywords and "B" not in bc.colors:
            return False
        if Keyword.INTIMIDATE.value in ac.keywords and not (ac.colors & bc.colors):
            return False
    return True


def blockers_for(state: GameState, attacker: int, defender: int) -> list[GameObject]:
    """The defender's creatures that could block this attacker.

    Menace needs two of them, so a lone possible blocker does not count.
    """
    found = [o for o in creatures(state, defender) if could_block(state, o.oid, attacker, defender)]
    if Keyword.MENACE.value in chars(state, attacker).keywords and len(found) < 2:
        return []
    return found


def absorbed(attack_powers: list[int], blockers: int) -> int:
    """Damage that gets through when ``blockers`` creatures each stop one attacker.

    Blockers are assumed to take the biggest hits, which is what a defender
    would do with chump blocks -- an optimistic read for the defender, so a
    "this is lethal" built on it is a safe one.
    """
    ordered = sorted(attack_powers, reverse=True)
    return sum(ordered[blockers:])


def lethal_on_board(state: GameState, seat: int, defender: int) -> bool:
    """Do our ready attackers kill this player through every blocker they have?"""
    powers = [power(state, o.oid) for o in ready_attackers(state, seat)]
    if not powers:
        return False
    blockers = len(untapped_blockers(state, defender))
    return absorbed(powers, blockers) >= state.players[defender].life


def crack_back(state: GameState, seat: int, leaving: Iterable[int] = ()) -> int:
    """The most damage one opponent could swing back at us next turn.

    ``leaving`` are our creatures that will be tapped by attacking; vigilance
    ones still block. Each opponent is assumed to send everything at us, which
    is pessimistic in a pod -- the right direction for a veto.
    """
    gone = {
        oid for oid in leaving if not has_keyword(state, oid, Keyword.VIGILANCE.value)
    }
    # Ours untap in our own untap step, which comes after their swing: whatever
    # is tapped now, or taps to attack, is not there to block it.
    ours = [o for o in creatures(state, seat) if not o.tapped and o.oid not in gone]
    worst = 0
    for pid in state.opponents(seat):
        powers = [power(state, o.oid) for o in creatures(state, pid) if can_attack_soon(state, o)]
        worst = max(worst, absorbed(powers, len(ours)))
    return worst


def incoming_unblocked(state: GameState, seat: int) -> int:
    """Combat damage headed at this player from attackers nobody has blocked yet."""
    combat = state.combat
    if combat is None:
        return 0
    blocked = set(combat.blockers.values())
    return sum(
        power(state, oid)
        for oid, defender in combat.attackers.items()
        if defender == seat and oid not in blocked and oid not in combat.attacking_permanent
    )


def mana_symbols_on_board(state: GameState, seat: int) -> set[str]:
    """Every mana symbol this player's permanents can make."""
    out: set[str] = set()
    for obj in state.battlefield_objects(seat):
        out.update(produced_symbols(state.card_of(obj)))
    return out


def colours_needed(state: GameState, seat: int) -> set[str]:
    """Colours the spells in hand ask for that no permanent of ours makes yet."""
    have = mana_symbols_on_board(state, seat)
    want: set[str] = set()
    for oid in state.players[seat].hand:
        card = state.card(oid)
        if card.is_land:
            continue
        want.update(c.value for c in card.mana_cost.colors)
    return want - have


def threat(state: GameState, pid: int) -> float:
    """How dangerous a player looks: board power, commander damage dealt, life."""
    board = sum(power(state, o.oid) for o in creatures(state, pid))
    walkers = sum(1 for o in state.battlefield_objects(pid) if "Planeswalker" in chars(state, o.oid).types)
    return board + 4 * walkers + state.players[pid].life * 0.1


def commander_oids(state: GameState, seat: int) -> list[int]:
    return [o.oid for o in state.battlefield_objects(seat) if o.is_commander]


def card_id_of(state: GameState, oid: int) -> str:
    obj = state.objects.get(oid)
    return obj.def_id if obj is not None else ""
