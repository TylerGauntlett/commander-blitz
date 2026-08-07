"""Effect execution context and the decision-asking helpers.

An op that needs input from a player does::

    picked = yield from ask_objects(ctx, "Sacrifice a creature", options, 1, 1, pid)

which suspends the whole resolution until a driver answers.
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..actions import DecisionOption, PendingDecision
from ..enums import DecisionKind
from ..structs import TargetRef

if TYPE_CHECKING:  # pragma: no cover
    from ..state import GameState


@dataclass
class EffectContext:
    """Everything an effect needs to know about why it is running."""

    state: GameState
    controller: int
    source_oid: int | None = None
    #: target spec id -> the refs chosen when the spell/ability was put on the stack
    targets: dict[str, tuple[TargetRef, ...]] = field(default_factory=dict)
    #: snapshots (from the ``snapshot`` op) and trigger bindings
    bindings: dict[str, Any] = field(default_factory=dict)
    x: int = 0
    modes: tuple[int, ...] = ()
    #: Set by ``for_each`` so nested effects can read the current iteration value.
    loop_value: Any = None
    #: Card id of the source, for log messages.
    source_name: str = ""

    def target_refs(self, target_id: str) -> tuple[TargetRef, ...]:
        return self.targets.get(target_id, ())

    def target_oids(self, target_id: str) -> list[int]:
        return [t.id for t in self.target_refs(target_id) if t.kind == "object"]

    def target_players(self, target_id: str) -> list[int]:
        return [t.id for t in self.target_refs(target_id) if t.kind == "player"]

    def target_sids(self, target_id: str) -> list[int]:
        return [t.id for t in self.target_refs(target_id) if t.kind == "stack"]

    def opponents(self) -> list[int]:
        return self.state.opponents(self.controller)

    def name_of(self, oid: int | None) -> str:
        if oid is None:
            return "?"
        obj = self.state.objects.get(oid)
        return self.state.card_of(obj).name if obj else f"#{oid}"


def ask_objects(
    ctx: EffectContext,
    prompt: str,
    oids: Sequence[int],
    min_count: int,
    max_count: int,
    chooser: int,
    purpose: str = "choose",
) -> Generator[PendingDecision, list[int], list[int]]:
    """Ask ``chooser`` to pick between ``min_count`` and ``max_count`` of ``oids``.

    Returns the chosen oids.  Resolves immediately without asking when the choice
    is forced (everything must be chosen, or there is nothing to choose).

    ``purpose`` is a machine-readable tag ("sacrifice", "search", "discard", ...)
    carried in the decision's context.  Agents and the UI branch on it; without
    it they would have to pattern-match on the human-readable prompt.
    """
    available = list(oids)
    if not available or max_count <= 0:
        return []
    if len(available) <= min_count:
        return available[: max(min_count, 0)] if min_count else available
    if min_count == max_count == len(available):
        return available

    options = tuple(
        DecisionOption(label=ctx.name_of(oid), ref=TargetRef.obj(oid), value=oid)
        for oid in available
    )
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_OBJECTS,
        player=chooser,
        prompt=prompt,
        options=options,
        min_count=min(min_count, len(available)),
        max_count=min(max_count, len(available)),
        context={
            "source": ctx.source_oid,
            "source_name": ctx.source_name,
            "purpose": purpose,
        },
    )
    answer = yield decision
    return [available[i] for i in answer]


def ask_yes_no(
    ctx: EffectContext, prompt: str, chooser: int
) -> Generator[PendingDecision, list[int], bool]:
    """Ask an optional ("you may") question."""
    decision = PendingDecision(
        kind=DecisionKind.MAY,
        player=chooser,
        prompt=prompt,
        options=(DecisionOption(label="Yes", value=True), DecisionOption(label="No", value=False)),
        min_count=1,
        max_count=1,
        context={"source": ctx.source_oid, "source_name": ctx.source_name},
    )
    answer = yield decision
    return bool(answer) and answer[0] == 0


def ask_mode(
    ctx: EffectContext, prompt: str, labels: Sequence[str], chooser: int, count: int = 1
) -> Generator[PendingDecision, list[int], list[int]]:
    """Ask the controller to choose one or more modes of a modal spell."""
    if len(labels) <= count:
        return list(range(len(labels)))
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_MODE,
        player=chooser,
        prompt=prompt,
        options=tuple(DecisionOption(label=label, value=i) for i, label in enumerate(labels)),
        min_count=count,
        max_count=count,
        context={"source": ctx.source_oid, "source_name": ctx.source_name},
    )
    answer = yield decision
    return list(answer)


def ask_player(
    ctx: EffectContext, prompt: str, pids: Sequence[int], chooser: int
) -> Generator[PendingDecision, list[int], int | None]:
    """Ask the controller to choose one player."""
    choices = list(pids)
    if not choices:
        return None
    if len(choices) == 1:
        return choices[0]
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_PLAYER,
        player=chooser,
        prompt=prompt,
        options=tuple(
            DecisionOption(
                label=ctx.state.players[pid].name or f"Player {pid}",
                ref=TargetRef.player(pid),
                value=pid,
            )
            for pid in choices
        ),
        min_count=1,
        max_count=1,
        context={"source": ctx.source_oid, "source_name": ctx.source_name},
    )
    answer = yield decision
    return choices[answer[0]] if answer else None
