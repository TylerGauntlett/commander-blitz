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
    #: "Whenever one or more cards leave your graveyard…" -- Spirit Mascot,
    #: Cyan. `ZONE_CHANGE` already records every move and is deliberately *not*
    #: on the trigger bus: routing every zone change through `fire` would run
    #: the trigger scan on every draw, discard, shuffle and land drop in the
    #: game. This is the one departure worth watching, fired narrowly from
    #: `zones.move_object` so nothing else pays for it.
    #:
    #: Carries the graveyard's **owner** as `player` (400.3), so
    #: `controller: "you"` restricts it to your own yard, and `batch` so the
    #: "one or more" batching in `triggers._queue` can fire it once for a
    #: single move of several cards.
    LEAVES_GRAVEYARD = "leaves_graveyard"

    # cards and the stack
    #: One card drawn. ``data["nth"]`` is that draw's **ordinal** for its player
    #: this turn -- 1 for the draw step's card, 2 for the next one -- which is
    #: what "whenever you draw your second card each turn" is about. Written by
    #: `draw_cards` from the tally it has just bumped, and read only by
    #: `triggers._matches`: an ordinal is true of the *event*, and the tally it
    #: came from has usually moved on by the time anything else looks.
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
    #: A Saga's lore counters **reached** a chapter number (714.2c). ``source``
    #: and ``data["oid"]`` are the Saga, ``data["chapter"]`` the number reached.
    #:
    #: Deliberately not `COUNTER_PLACED`, which is fired beside it by the same
    #: `add_counters` call and is the near miss the gap record for Oath of Eorl
    #: named: that event says a counter was *put on*, and a chapter ability
    #: triggers when the count **becomes** N. The two come apart in both
    #: directions. Proliferate on a Saga at two lore counters is one placement
    #: that reaches chapter III; a lore counter removed and put back is two
    #: placements that reach nothing new the second time but re-trigger under
    #: 714.2c, which only a before/after comparison can tell. And a Saga
    #: **enters** with its first lore counter as part of entering (714.2b), where
    #: `add_counters` is never called at all and no COUNTER_PLACED exists to
    #: hang chapter I on.
    #:
    #: One event per chapter number crossed, not per counter and not per
    #: ability: two abilities printed on the same chapter line both fire off the
    #: one event, and a Saga jumped from I to III fires II and then III in that
    #: order.
    CHAPTER_REACHED = "chapter_reached"
    #: The monarch designation moved to a player (721.2, 721.4). ``player`` is
    #: the **new** monarch and ``data["previous"]`` whoever held it before, or
    #: ``None`` if nobody did.
    #:
    #: Its own type for the reason CONTROL_CHANGED and TRANSFORMED have theirs:
    #: nothing moves, so nothing else in the log would say that the table's most
    #: valuable designation just changed hands. Fired only when it *changes* --
    #: becoming the monarch while already the monarch is a no-op, so "an opponent
    #: becomes the monarch" (Palace Jailer's duration) means what it says.
    BECAME_MONARCH = "became_monarch"
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
    #: "Whenever one or more creatures **you control** deal combat damage to one
    #: or more players…" One of these per combat-damage step per *damaging
    #: player*, fired beside the per-creature COMBAT_DAMAGE_TO_PLAYER above
    #: rather than instead of it, carrying ``damagers`` (the creatures) and
    #: ``damaged`` (the players they connected with).
    #:
    #: Its own type rather than a filtered COMBAT_DAMAGE_TO_PLAYER, because that
    #: one is a fact about *one creature hitting one player* and there are as
    #: many of them as there were connections: a card built on it pays once per
    #: Knight that got through, where the printed line pays once. The batch is
    #: the same shape CREATURES_ATTACKED_PLAYER is one phase earlier -- coarser
    #: than a creature, finer than the game -- and it is drawn from the very
    #: assignment list rule 510.2 makes simultaneous, which is why it can be
    #: counted at all.
    #:
    #: Per damaging **player** and not per (player, defender) pair, because the
    #: printed clause says "to one or more players": one seat's creatures
    #: connecting with two opponents in one step is one event. The seats hit are
    #: on ``damaged`` for anything that needs to ask.
    CREATURES_DEALT_COMBAT_DAMAGE = "creatures_dealt_combat_damage"

    # combat
    ATTACKERS_DECLARED = "attackers_declared"
    #: "Whenever one or more creatures attack **one of your opponents**…" One of
    #: these per (declaration, defending player) pair, fired beside the single
    #: ATTACKERS_DECLARED above rather than instead of it, carrying ``defender``
    #: and the ``attackers`` declared against *that* player.
    #:
    #: Its own type rather than a second ATTACKERS_DECLARED, because that event
    #: means "the declaration closed" and there is exactly one of those per
    #: combat: firing it per defender would make Clavileño's "whenever you
    #: attack" pay twice on a split attack, and would tell the client the attack
    #: was declared N times. The pair is the same shape as BECAME_BLOCKED and
    #: ATTACKED_UNBLOCKED -- one instant, two facts, told separately because
    #: cards ask for them separately.
    CREATURES_ATTACKED_PLAYER = "creatures_attacked_player"
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
    #: ``data["extra"]`` is present, and True, only on an extra turn (500.7).
    TURN_BEGAN = "turn_began"
    #: A scheduled extra turn that did not happen, because its player skipped it
    #: (614.10) -- Trouble in Pairs. Emitted where the turn would have begun, and
    #: the only trace of it: a skipped turn takes no turn number and fires no
    #: `turn_began`, so without this the log shows a spell that promised a turn
    #: and a table that silently moved on.
    TURN_SKIPPED = "turn_skipped"
    STEP_BEGAN = "step_began"
    STEP_ENDED = "step_ended"
    UPKEEP = "upkeep"
    DRAW_STEP = "draw_step"
    BEGIN_COMBAT = "begin_combat"
    #: The beginning of a **precombat** main phase -- "at the beginning of your
    #: first main phase". Exactly once a turn, because an extra main phase
    #: inserted after a combat is a *postcombat* one by 505.1b, so the word
    #: "first" needs no ordinal of its own.
    PRECOMBAT_MAIN = "precombat_main"
    #: The beginning of a **postcombat** main phase. Distinct from BEGIN_COMBAT,
    #: which is the other side of combat and reads a life-loss tally that has
    #: not happened yet -- Florian, Voldaren Scion counts what your opponents
    #: lost *this turn*, which is mostly what the combat just before it did.
    POSTCOMBAT_MAIN = "postcombat_main"
    END_STEP = "end_step"

    # mana
    MANA_ADDED = "mana_added"
    MANA_SPENT = "mana_spent"
    MANA_EMPTIED = "mana_emptied"

    # randomness
    #: Dice were rolled (rule 705.1) -- one event per `roll_dice`, however many
    #: dice it threw, because "roll X six-sided dice" is one act and the printed
    #: cards that care say "whenever you roll **one or more** dice".
    #:
    #: ``data["results"]`` is every face in the order it came up and
    #: ``data["sides"]`` the kind of die, so the log line can say what was
    #: rolled. Nothing else in the log could: a roll moves no card, changes no
    #: characteristic and touches no zone, so without this the Treasures a
    #: Bobblehead makes appear out of nowhere and the number of them looks
    #: arbitrary. Not emitted for a roll of **zero** dice -- "roll X dice" with
    #: X at 0 rolls nothing, and a line saying so would be noise.
    DICE_ROLLED = "dice_rolled"

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
