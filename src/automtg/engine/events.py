"""The game event log.

Every mutating engine primitive emits a :class:`GameEvent`.  The log serves three
purposes at once:

1. It is what the trigger system matches against.
2. It is the human-readable play-by-play shown in the UI.
3. Combined with the seed and the action tape it is the *replay* mechanism used
   for undo and for env resets, which is why the engine needs no state cloning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class EventType:
    """Event type names.

    A plain namespace of string constants rather than an enum: card definitions
    reference a subset of these by name, and keeping them strings means the DSL
    and the event bus speak the same vocabulary without a conversion layer.
    """

    # zone / object lifecycle
    ZONE_CHANGE = "zone_change"
    ENTERS_BATTLEFIELD = "enters_battlefield"
    LEAVES_BATTLEFIELD = "leaves_battlefield"
    DIES = "dies"
    TOKEN_CREATED = "token_created"

    # cards and the stack
    DRAW = "draw"
    DISCARD = "discard"
    #: "When you cycle this card…". Distinct from DISCARD, which every discard
    #: emits: cycling is one specific activated ability, and a trigger reading
    #: the broader event would fire on hand-size discards too.
    CYCLED = "cycled"
    MILL = "mill"
    SPELL_CAST = "spell_cast"
    SPELL_RESOLVED = "spell_resolved"
    SPELL_COUNTERED = "spell_countered"
    SPELL_FIZZLED = "spell_fizzled"
    ABILITY_ACTIVATED = "ability_activated"
    ABILITY_TRIGGERED = "ability_triggered"
    ABILITY_RESOLVED = "ability_resolved"

    # permanents
    LAND_PLAYED = "land_played"
    TAPPED = "tapped"
    UNTAPPED = "untapped"
    COUNTER_PLACED = "counter_placed"
    COUNTER_REMOVED = "counter_removed"
    ATTACHED = "attached"
    BECAME_MONSTROUS = "became_monstrous"
    SUSPENDED = "suspended"
    TIME_COUNTER_REMOVED = "time_counter_removed"

    # life and damage
    LIFE_GAINED = "life_gained"
    LIFE_LOST = "life_lost"
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_PREVENTED = "damage_prevented"
    COMBAT_DAMAGE_TO_PLAYER = "combat_damage_to_player"

    # combat
    ATTACKERS_DECLARED = "attackers_declared"
    BLOCKERS_DECLARED = "blockers_declared"
    ATTACKS = "attacks"
    BLOCKS = "blocks"

    # turn structure
    TURN_BEGAN = "turn_began"
    STEP_BEGAN = "step_began"
    STEP_ENDED = "step_ended"
    UPKEEP = "upkeep"
    DRAW_STEP = "draw_step"
    BEGIN_COMBAT = "begin_combat"
    END_STEP = "end_step"

    # mana
    MANA_ADDED = "mana_added"
    MANA_SPENT = "mana_spent"
    MANA_EMPTIED = "mana_emptied"

    # game outcome
    PLAYER_LOST = "player_lost"
    GAME_OVER = "game_over"
    MULLIGAN_TAKEN = "mulligan_taken"
    HAND_KEPT = "hand_kept"


@dataclass(frozen=True)
class GameEvent:
    """One thing that happened, in order.

    ``data`` holds event-specific payload; the well-known keys are documented per
    event type in ``docs/engine-rules.md``.  ``source`` is the object that caused
    the event where one exists, ``player`` the player it happened to.
    """

    type: str
    turn: int
    step: int
    player: int | None = None
    source: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        """A compact one-line rendering, used by the CLI and the UI event log."""
        bits = [f"T{self.turn}", self.type]
        if self.player is not None:
            bits.append(f"p{self.player}")
        if self.source is not None:
            bits.append(f"#{self.source}")
        if self.data:
            payload = ",".join(f"{k}={v}" for k, v in sorted(self.data.items()))
            bits.append(f"({payload})")
        return " ".join(bits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "turn": self.turn,
            "step": self.step,
            "player": self.player,
            "source": self.source,
            "data": self.data,
        }
