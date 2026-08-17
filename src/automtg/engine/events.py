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
    #: "Whenever you sacrifice a token…" -- a sacrifice told apart from every
    #: other way of leaving the battlefield. `move_object` already tags the move
    #: `cause="sacrificed"`, but that tag reached only the ZONE_CHANGE payload;
    #: `dies` and `leaves_battlefield` carry no cause, so no trigger could tell a
    #: sacrifice from a removal spell, which is most of what the printed line is
    #: about.
    SACRIFICED = "sacrificed"

    # cards and the stack
    DRAW = "draw"
    DISCARD = "discard"
    #: "When you cycle this card…". Distinct from DISCARD, which every discard
    #: emits: cycling is one specific activated ability, and a trigger reading
    #: the broader event would fire on hand-size discards too.
    CYCLED = "cycled"
    #: A player got the city's blessing. Once per player per game.
    CITY_S_BLESSING = "city_s_blessing"
    MILL = "mill"
    SPELL_CAST = "spell_cast"
    SPELL_RESOLVED = "spell_resolved"
    SPELL_COUNTERED = "spell_countered"
    #: A spell was copied on the stack (706.10) -- storm, replicate, conspire,
    #: casualty. Its own event because a copy is never *cast*, so `SPELL_CAST`
    #: would be a lie, and a log built from casts alone would show a storm
    #: count of nine as one spell.
    SPELL_COPIED = "spell_copied"
    SPELL_FIZZLED = "spell_fizzled"
    ABILITY_ACTIVATED = "ability_activated"
    ABILITY_TRIGGERED = "ability_triggered"
    ABILITY_RESOLVED = "ability_resolved"
    #: Something was chosen as a target, as the spell or ability went on the
    #: stack (rule 603.2d) -- heroic and ward, which both fire *then* and not on
    #: resolution, because the whole point of ward is to answer before the spell
    #: does anything. Fired once per target, so a spell hitting two creatures
    #: wakes both. ``player`` is the **caster**, not the target's controller:
    #: "an opponent casts a spell that targets this" asks about whose spell it
    #: is, and the target's controller is already known from the target.
    BECAME_TARGET = "became_target"

    # permanents
    LAND_PLAYED = "land_played"
    TAPPED = "tapped"
    UNTAPPED = "untapped"
    COUNTER_PLACED = "counter_placed"
    COUNTER_REMOVED = "counter_removed"
    ATTACHED = "attached"
    #: A permanent changed controller without changing zones. Its own type,
    #: because every other way a permanent arrives on somebody's side of the
    #: board is a ZONE_CHANGE and this one is not: the object never moves, so a
    #: log built from zone changes alone would show a creature silently swapping
    #: sides. ``data`` carries ``from`` and ``to`` player ids.
    CONTROL_CHANGED = "control_changed"
    #: A double-faced permanent turned over. Its own type for the same reason
    #: CONTROL_CHANGED is: no zone change happens, so nothing else in the log
    #: would say that the card on the board is now a different card.
    TRANSFORMED = "transformed"
    BECAME_MONSTROUS = "became_monstrous"
    #: A permanent's power/toughness or keywords changed without a counter and
    #: without a zone change -- a pump, an animated land, a granted keyword.
    #:
    #: Its own type for the same reason CONTROL_CHANGED and TRANSFORMED have
    #: theirs: nothing else in the log records it. ``pump`` mutates ``until_eot``
    #: and calls ``bump_chars()`` in silence, so "target creature gets +3/+3
    #: until end of turn" was invisible to every consumer of the log -- the
    #: client could not animate a trick it had no way of knowing had happened,
    #: and the play-by-play skipped the whole combat trick.
    #:
    #: ``data`` carries ``power``, ``toughness`` and ``keyword`` as applicable.
    #: Emitted through ``state.emit`` rather than ``triggers.fire``: see the
    #: warning in ``zones.py`` about new keys in a fired event's ``data``
    #: colliding with the bindings a card's trigger reads.
    STATS_CHANGED = "stats_changed"
    SUSPENDED = "suspended"
    TIME_COUNTER_REMOVED = "time_counter_removed"

    # life and damage
    LIFE_GAINED = "life_gained"
    LIFE_LOST = "life_lost"
    #: Poison counters given to a player (704.5c). Its own event rather than a
    #: life-loss: poison is a counter on the player, and ten of them end the
    #: game at any life total.
    POISON_ADDED = "poison_added"
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_PREVENTED = "damage_prevented"
    COMBAT_DAMAGE_TO_PLAYER = "combat_damage_to_player"

    # combat
    ATTACKERS_DECLARED = "attackers_declared"
    BLOCKERS_DECLARED = "blockers_declared"
    ATTACKS = "attacks"
    BLOCKS = "blocks"
    #: Rule 509.1h. An attacker became blocked, or was declared and nobody
    #: blocked it -- flanking, rampage, bushido and frenzy, which is every
    #: combat keyword the engine had no event for. Both are decided at the same
    #: instant, when blockers are declared, so they are one pair and not two
    #: features: "isn't blocked" is only knowable once the declaration closes.
    #: ``blockers`` carries how many, for rampage.
    BECAME_BLOCKED = "became_blocked"
    ATTACKED_UNBLOCKED = "attacked_unblocked"

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
