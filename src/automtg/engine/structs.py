"""Plain data containers shared by the engine modules.

These live in their own module purely to keep the import graph acyclic:
``state`` needs :class:`CombatState` and :class:`StackItem`, while ``combat`` and
``stack`` need ``GameState``.  Putting the dumb containers here breaks the cycle
without any ``TYPE_CHECKING`` gymnastics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TargetKind = Literal["object", "player", "stack"]


@dataclass(frozen=True, order=True)
class TargetRef:
    """A reference to something a spell or ability targets."""

    kind: TargetKind
    id: int

    @staticmethod
    def obj(oid: int) -> TargetRef:
        return TargetRef("object", oid)

    @staticmethod
    def player(pid: int) -> TargetRef:
        return TargetRef("player", pid)

    @staticmethod
    def stack(sid: int) -> TargetRef:
        return TargetRef("stack", sid)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id}


@dataclass
class TempEffect:
    """A continuous effect that lasts until end of turn.

    ``kind`` is ``"pump"`` (power/toughness modification), ``"keyword"``,
    ``"lock_abilities"`` ("its activated abilities can't be activated this
    turn"), ``"ability"`` (a whole triggered or activated ability granted by
    another permanent), or ``"animate"`` ("becomes a 4/4 creature until end of
    turn").  The lock is not a keyword because it is not a characteristic: it is
    a permission, read by legality and by the mana solver rather than by
    ``chars``, and showing it in a card's keyword list would be a lie.

    ``animate`` is the only kind that touches *base* characteristics, which is
    why ``power``/``toughness`` mean something different for it than they do for
    a pump: a pump's are a delta, an animation's are the value itself.
    """

    kind: str
    power: int = 0
    toughness: int = 0
    keyword: str | None = None
    source: int | None = None
    #: For ``kind == "ability"``: which of the source card's
    #: ``grantable_abilities`` was handed over.
    ability_index: int | None = None
    #: For ``kind == "animate"``: what the permanent becomes.  Types and subtypes
    #: are *added* -- "it's still a land" is the default rather than a special
    #: case, because every printed animation says it.
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "power": self.power,
            "toughness": self.toughness,
            "keyword": self.keyword,
            "source": self.source,
            "types": list(self.types),
            "subtypes": list(self.subtypes),
            "colors": list(self.colors),
        }


@dataclass
class StackItem:
    """One object on the stack: a spell, or an activated/triggered ability."""

    sid: int
    kind: str  # "spell" | "ability"
    controller: int
    def_id: str
    oid: int | None = None  # the spell's GameObject (kind == "spell")
    source_oid: int | None = None  # the ability's source permanent
    ability_index: int | None = None
    targets: tuple[TargetRef, ...] = ()
    x: int = 0
    modes: tuple[int, ...] = ()
    #: Whether the kicker cost was paid as this spell was cast.  Decided at cast
    #: time and read on resolution, because that is the only place it can be
    #: known: nothing about the object afterwards records what was paid for it.
    kicked: bool = False
    evoked: bool = False
    #: Cast from a graveyard for its flashback cost. Read on
    #: resolution both by the `cast_from_graveyard` condition and by
    #: the once-only rider that exiles the card instead of
    #: returning it to the graveyard.
    flashback: bool = False
    #: Values captured when the ability triggered (e.g. the land that was played).
    bindings: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    #: See `TriggerInstance.granted_by`.
    granted_by: int | None = None

    @property
    def is_spell(self) -> bool:
        return self.kind == "spell"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "kind": self.kind,
            "controller": self.controller,
            "def_id": self.def_id,
            "oid": self.oid,
            "source_oid": self.source_oid,
            "ability_index": self.ability_index,
            "targets": [t.to_dict() for t in self.targets],
            "x": self.x,
            "kicked": self.kicked,
            "description": self.description,
        }


@dataclass
class TriggerInstance:
    """A triggered ability that has fired but is not yet on the stack."""

    source_oid: int
    ability_index: int
    controller: int
    bindings: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    #: Set when this ability was *granted* -- the oid of the permanent whose
    #: `grantable_abilities` it came from.  Resolution has to look there rather
    #: than at the source's own abilities, which do not include it.
    granted_by: int | None = None


@dataclass
class DelayedTrigger:
    """An effect scheduled to happen at a later step.

    "At the beginning of the next end step, return it to the battlefield." The
    engine's ordinary triggers all fire *from* an event that has just happened;
    this is the other shape -- an effect that has already resolved arranging for
    something to happen later, with no object left to hang a trigger on.

    ``turn`` is the turn it was created on, so "the *next* upkeep" is not this
    one when the card is cast during an upkeep.
    """

    step: str
    controller: int
    effects: tuple[dict[str, Any], ...] = ()
    bindings: dict[str, Any] = field(default_factory=dict)
    source_oid: int | None = None
    description: str = ""
    turn: int = 0


@dataclass
class TurnLedger:
    """Tallies of what has happened during the current turn.

    Morbid asks "did a creature die this turn", raid "did you attack", spectacle
    "did an opponent lose life", storm "how many spells have been cast".  Seven
    mechanics, and not one of them can be answered by looking at the board:
    every question is about an *event*, and the board keeps no record that one
    happened.  A creature that died is in a graveyard it may have reached six
    other ways, and a player who attacked looks exactly like one who did not
    once combat is over.

    Folded in :meth:`GameState.emit` rather than at each primitive.  Every tally
    here counts something that already emits an event, and ``emit`` is the one
    function all of them pass through, so a future effect that deals damage or
    kills a creature by some new route is counted without anybody remembering to
    count it.  That is the argument ``draw_cards`` makes for the draw tally,
    made once at the only choke point wide enough to carry all six.

    Cleared at cleanup alongside ``damage_ledger``, and deliberately *not* at
    untap where ``cards_drawn_this_turn`` clears: that one has to survive its
    own turn's cleanup because the opening hand is drawn before turn 1 exists.
    Nothing counted here can happen before the game starts.
    """

    #: How many creatures have died this turn, keyed by the player who
    #: controlled them.  "A creature died this turn" is the sum over every
    #: player; "a creature you controlled died" is one entry.
    creatures_died: dict[int, int] = field(default_factory=dict)
    #: Players who have declared at least one attacker this turn.  A set rather
    #: than a count because raid asks only whether it happened, and no printed
    #: card cares how many times you were the attacking player in one turn.
    attacked: set[int] = field(default_factory=set)
    #: Damage dealt to each player this turn.
    damage_taken: dict[int, int] = field(default_factory=dict)
    #: Life *lost* by each player this turn, which is the wider question: a
    #: drain, a Phyrexian payment and a card's own cost all lose life with no
    #: damage dealt anywhere.  Damage to a player counts towards both, because
    #: rule 118.2 says damage to a player causes that much life loss -- so
    #: spectacle triggers off a Lightning Bolt, which is the whole point of it.
    life_lost: dict[int, int] = field(default_factory=dict)
    #: Spells cast this turn, per caster.  Storm counts every spell cast before
    #: it by anybody, which is the sum.
    spells_cast: dict[int, int] = field(default_factory=dict)
    #: Cards put into any graveyard from anywhere this turn (gravestorm).
    #: Tokens are excluded because they are not cards, and a token dying is the
    #: single most common way this number would otherwise be wrong.
    cards_to_graveyard: int = 0
    #: How many times each ability has *resolved* this turn, keyed by the object
    #: it belongs to and its index on that card.  Scythecat Cub's "if this is the
    #: second time this ability has resolved this turn" is a question about one
    #: ability of one permanent, so two copies of the card count separately.
    #:
    #: The odd one out here, in two ways.  It is keyed by ability rather than by
    #: player, because "this ability" is not a fact about a seat.  And it is the
    #: only tally not folded in :meth:`GameState.emit`: ``ABILITY_RESOLVED`` is
    #: emitted *after* the effects run, and the card has to count the resolution
    #: it is in the middle of, so ``stack.resolve_top`` bumps it on the way in --
    #: past the fizzle and intervening-if returns, neither of which resolves.
    ability_resolutions: dict[tuple[int, int], int] = field(default_factory=dict)

    def resolving(self, oid: int, ability_index: int) -> int:
        """Count this resolution and return how many there have now been."""
        key = (oid, ability_index)
        count = self.ability_resolutions.get(key, 0) + 1
        self.ability_resolutions[key] = count
        return count

    def clear(self) -> None:
        self.creatures_died.clear()
        self.attacked.clear()
        self.damage_taken.clear()
        self.life_lost.clear()
        self.spells_cast.clear()
        self.cards_to_graveyard = 0
        self.ability_resolutions.clear()


@dataclass
class CombatState:
    """Everything about the current combat phase."""

    #: attacker oid -> the player being attacked
    attackers: dict[int, int] = field(default_factory=dict)
    #: blocker oid -> the attacker it is blocking
    blockers: dict[int, int] = field(default_factory=dict)
    #: attacker oid -> ordered list of blocker oids (damage assignment order)
    block_order: dict[int, list[int]] = field(default_factory=dict)
    #: creatures that left combat (destroyed, bounced, removed)
    removed: set[int] = field(default_factory=set)
    #: which defending players still have to declare blocks, in APNAP order
    pending_blockers: list[int] = field(default_factory=list)
    attackers_declared: bool = False
    blockers_declared: bool = False
    first_strike_done: bool = False
    #: staged during incremental declaration, before FINISH_DECLARATION validates it
    declaring_player: int | None = None

    def attacking(self, oid: int) -> bool:
        return oid in self.attackers and oid not in self.removed

    def blocking(self, oid: int) -> bool:
        return oid in self.blockers and oid not in self.removed

    def is_blocked(self, attacker_oid: int) -> bool:
        return bool([b for b in self.block_order.get(attacker_oid, []) if b not in self.removed])

    def remove(self, oid: int) -> None:
        self.removed.add(oid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attackers": dict(self.attackers),
            "blockers": dict(self.blockers),
            "block_order": {k: list(v) for k, v in self.block_order.items()},
            "removed": sorted(self.removed),
            "attackers_declared": self.attackers_declared,
            "blockers_declared": self.blockers_declared,
        }


@dataclass
class Characteristics:
    """Derived, cached characteristics of a permanent (see ``characteristics.py``)."""

    power: int = 0
    toughness: int = 0
    types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    supertypes: frozenset[str] = frozenset()
    keywords: frozenset[str] = frozenset()
    colors: frozenset[str] = frozenset()

    def has(self, keyword: str) -> bool:
        return keyword in self.keywords
