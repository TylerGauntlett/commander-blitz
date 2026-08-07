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

    ``kind`` is ``"pump"`` (power/toughness modification) or ``"keyword"``.
    """

    kind: str
    power: int = 0
    toughness: int = 0
    keyword: str | None = None
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "power": self.power,
            "toughness": self.toughness,
            "keyword": self.keyword,
            "source": self.source,
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
    #: Values captured when the ability triggered (e.g. the land that was played).
    bindings: dict[str, Any] = field(default_factory=dict)
    description: str = ""

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
