"""The root game state and the accessors everything else is built on."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .actions import PendingDecision
from .carddef import CardDef
from .enums import STEP_PHASE, Phase, Step, Zone
from .events import GameEvent
from .objects import GameObject
from .player import PlayerState
from .rng import Rng
from .structs import CombatState, DelayedTrigger, StackItem, TriggerInstance

if TYPE_CHECKING:  # pragma: no cover
    from automtg.cards.registry import CardRegistry

#: Hard cap on turns; a game that reaches it is scored as a draw.  Without this a
#: self-play run can stall forever on two durdling boards.
DEFAULT_MAX_TURNS = 60

#: Guard against infinite trigger loops within a single step.
MAX_TRIGGERS_PER_STEP = 200


@dataclass
class GameState:
    """Everything about a game in progress.

    Zones are flat, id-keyed lists; there are no object cycles, so serialization
    and inspection are trivial.  Nothing in here is ever deep-copied: undo and
    env resets replay from ``rng.seed`` plus the action tape instead.
    """

    registry: CardRegistry
    players: list[PlayerState]
    rng: Rng

    objects: dict[int, GameObject] = field(default_factory=dict)
    battlefield: list[int] = field(default_factory=list)
    stack: list[StackItem] = field(default_factory=list)

    turn: int = 0
    #: Full cycles of the table, incremented when the active seat wraps.
    #:
    #: Deliberately *parallel* to ``turn`` rather than replacing it.  ``turn``
    #: counts player-turns and is load-bearing for summoning sickness
    #: (:meth:`GameObject.summoning_sick`), the first-draw skip, the ``max_turns``
    #: cap and the RL encoding.  But a player counting their own turns says "this
    #: is my second turn" while ``turn`` reads 3 in a two-player game, so the UI
    #: needs the round and cannot derive it: eliminations make
    #: ``turn // num_players`` drift.  See docs/playtest-feedback-02.md.
    round: int = 0
    active_idx: int = 0
    step: Step = Step.UNTAP
    starting_player: int = 0

    priority_idx: int | None = None
    passes_in_row: int = 0

    combat: CombatState | None = None
    pending_decision: PendingDecision | None = None
    #: A suspended effect generator waiting on ``pending_decision``.  Never
    #: serialized -- replay reconstructs it by re-running the same actions.
    pending_generator: Any = field(default=None, repr=False)
    pending_triggers: list[TriggerInstance] = field(default_factory=list)
    #: Effects arranged for a later step -- see `structs.DelayedTrigger`.
    delayed_triggers: list[DelayedTrigger] = field(default_factory=list)

    events: list[GameEvent] = field(default_factory=list)
    game_over: bool = False
    winners: list[int] = field(default_factory=list)
    result: str = ""

    next_oid: int = 1
    next_sid: int = 1

    #: Bumped whenever anything that could change derived characteristics changes.
    char_version: int = 0
    char_cache: dict[int, Any] = field(default_factory=dict, repr=False)
    char_cache_version: int = -1

    triggers_this_step: int = 0
    #: "Whenever a creature dealt damage by this creature this turn dies…"
    #:
    #: victim oid -> the oids of everything that has damaged it this turn.
    #: Cleared during cleanup.
    #:
    #: It lives on the state rather than on the damaged object because the whole
    #: question is asked *about a creature that has just died*: an entry on the
    #: object would be wiped by `reset_permanent_state` on the way to the
    #: graveyard, which is exactly the moment it is needed.
    damage_ledger: dict[int, set[int]] = field(default_factory=dict)
    max_turns: int = DEFAULT_MAX_TURNS
    #: Set when cleanup performed an action and must repeat (rule 514.3a).
    cleanup_repeat: bool = False
    #: False until the current step's turn-based actions have been performed.
    step_started: bool = False
    started: bool = False

    # ------------------------------------------------------------------
    # lookups
    # ------------------------------------------------------------------

    def obj(self, oid: int) -> GameObject:
        return self.objects[oid]

    def maybe_obj(self, oid: int | None) -> GameObject | None:
        if oid is None:
            return None
        return self.objects.get(oid)

    def card(self, oid: int) -> CardDef:
        """The :class:`CardDef` behind an object id."""
        return self.registry.get(self.objects[oid].def_id)

    def card_of(self, obj: GameObject) -> CardDef:
        return self.registry.get(obj.def_id)

    def player(self, pid: int) -> PlayerState:
        return self.players[pid]

    @property
    def num_players(self) -> int:
        return len(self.players)

    @property
    def phase(self) -> Phase:
        return STEP_PHASE[self.step]

    @property
    def active_player(self) -> int:
        return self.players[self.active_idx].pid

    @property
    def priority_player(self) -> int | None:
        return None if self.priority_idx is None else self.players[self.priority_idx].pid

    # ------------------------------------------------------------------
    # players and turn order
    # ------------------------------------------------------------------

    def alive(self) -> list[int]:
        """Player ids still in the game, in seat order."""
        return [p.pid for p in self.players if not p.has_lost]

    def is_alive(self, pid: int) -> bool:
        return not self.players[pid].has_lost

    def opponents(self, pid: int) -> list[int]:
        return [p for p in self.alive() if p != pid]

    def next_alive_index(self, idx: int) -> int:
        """The next seat clockwise that is still in the game."""
        n = self.num_players
        for offset in range(1, n + 1):
            candidate = (idx + offset) % n
            if not self.players[candidate].has_lost:
                return candidate
        return idx

    def turn_order(self, start_pid: int | None = None) -> list[int]:
        """Alive players in APNAP order starting from ``start_pid`` (default: active)."""
        start = self.active_idx if start_pid is None else start_pid
        n = self.num_players
        return [
            self.players[(start + i) % n].pid
            for i in range(n)
            if not self.players[(start + i) % n].has_lost
        ]

    # ------------------------------------------------------------------
    # zones
    # ------------------------------------------------------------------

    def zone_list(self, zone: Zone, pid: int | None = None) -> list[int]:
        """The ordered oid list backing a zone."""
        if zone is Zone.BATTLEFIELD:
            return self.battlefield
        if zone is Zone.STACK:
            return [it.oid for it in self.stack if it.oid is not None]
        if pid is None:
            raise ValueError(f"{zone} requires a player id")
        return self.players[pid].zone_list(zone)

    def battlefield_objects(self, controller: int | None = None) -> list[GameObject]:
        """Permanents in a stable order (battlefield list order = arrival order)."""
        out = []
        for oid in self.battlefield:
            o = self.objects.get(oid)
            if o is None:
                continue
            if controller is None or o.controller == controller:
                out.append(o)
        return out

    def creatures(self, controller: int | None = None) -> list[GameObject]:
        from .characteristics import chars  # local import: avoids a cycle at module load

        return [
            o
            for o in self.battlefield_objects(controller)
            if "Creature" in chars(self, o.oid).types
        ]

    def objects_in(self, zone: Zone, pid: int | None = None) -> Iterator[GameObject]:
        for oid in self.zone_list(zone, pid):
            o = self.objects.get(oid)
            if o is not None:
                yield o

    # ------------------------------------------------------------------
    # stack
    # ------------------------------------------------------------------

    def stack_item(self, sid: int) -> StackItem | None:
        for item in self.stack:
            if item.sid == sid:
                return item
        return None

    @property
    def stack_empty(self) -> bool:
        return not self.stack

    # ------------------------------------------------------------------
    # ids, events and cache invalidation
    # ------------------------------------------------------------------

    def alloc_oid(self) -> int:
        oid = self.next_oid
        self.next_oid += 1
        return oid

    def alloc_sid(self) -> int:
        sid = self.next_sid
        self.next_sid += 1
        return sid

    def emit(
        self,
        event_type: str,
        *,
        player: int | None = None,
        source: int | None = None,
        **data: Any,
    ) -> GameEvent:
        """Append an event to the log and return it.

        The caller is responsible for handing the event to the trigger bus; this
        method only records it.
        """
        event = GameEvent(
            type=event_type,
            turn=self.turn,
            step=int(self.step),
            player=player,
            source=source,
            data=data,
        )
        self.events.append(event)
        return event

    def bump_chars(self) -> None:
        """Invalidate the derived-characteristics cache."""
        self.char_version += 1

    # ------------------------------------------------------------------
    # misc
    # ------------------------------------------------------------------

    def empty_all_mana_pools(self) -> None:
        for p in self.players:
            lost = p.mana_pool.clear()
            if lost:
                self.emit("mana_emptied", player=p.pid, amount=lost)

    def commanders_of(self, pid: int) -> list[int]:
        return list(self.players[pid].commanders)

    def describe(self) -> str:  # pragma: no cover - debug helper
        bits = [f"T{self.turn} {self.step.name} AP=p{self.active_player}"]
        for p in self.players:
            tag = "OUT" if p.has_lost else f"{p.life}life"
            bits.append(f"p{p.pid}:{tag} h={len(p.hand)} bf={len(self.battlefield_objects(p.pid))}")
        if self.stack:
            bits.append(f"stack={len(self.stack)}")
        return " | ".join(bits)


def new_object(
    state: GameState,
    def_id: str,
    owner: int,
    zone: Zone,
    *,
    controller: int | None = None,
    is_token: bool = False,
    is_commander: bool = False,
) -> GameObject:
    """Create a game object and register it (without placing it in a zone list)."""
    obj = GameObject(
        oid=state.alloc_oid(),
        def_id=def_id,
        owner=owner,
        controller=owner if controller is None else controller,
        zone=zone,
        is_token=is_token,
        is_commander=is_commander,
    )
    state.objects[obj.oid] = obj
    return obj


def sorted_oids(oids: Iterable[int]) -> list[int]:
    """Deterministic ordering helper used wherever iteration order is observable."""
    return sorted(oids)
