"""Effect execution context and the decision-asking helpers.

An op that needs input from a player does::

    picked = yield from ask_objects(ctx, "Sacrifice a creature", options, 1, 1, pid)

which suspends the whole resolution until a driver answers.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
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
    #: Whether the spell being resolved paid its kicker cost.
    kicked: bool = False
    #: **Gift** (702.164a): which opponent was promised a gift as the spell being
    #: resolved was cast, or ``None`` if none was. Read by the
    #: ``{"gift_promised": …}`` condition and by the ``"gift_recipient"`` player
    #: spec, which is how the card aims the promised reward at the right seat.
    gift_to: int | None = None
    modes: tuple[int, ...] = ()
    #: Whether :attr:`modes` is an *answer* rather than an empty default. See
    #: `structs.StackItem.modes_answered`: "choose up to two" may choose none,
    #: and `ops_control.op_choose_mode` must not mistake that for unasked.
    #: Consumed with `modes`, so a nested `choose_mode` still asks its own.
    modes_answered: bool = False
    #: Set by ``for_each`` so nested effects can read the current iteration value.
    loop_value: Any = None
    #: Card id of the source, for log messages.
    source_name: str = ""
    #: The id of the card the resolving spell or ability was put on the stack
    #: from -- `StackItem.def_id`, snapshotted then. Read where an effect needs
    #: something written on its own card after the source may have gone: a
    #: planeswalker's ultimate usually takes its last loyalty, so by the time
    #: "you get an emblem" resolves the planeswalker is in a graveyard or, as a
    #: token copy, nowhere.
    source_def_id: str = ""
    #: How many times this ability has resolved this turn, *counting this one*.
    #: Set by ``stack.resolve_top``; 0 for a spell, which has no ability index
    #: and cannot ask.  Carried here rather than looked up from the ledger
    #: because the ability index is not otherwise part of an effect's world.
    resolutions: int = 0
    #: The first timestamp (613.7) this resolution may hand out. Everything
    #: granted from here on happened *as part of* this spell or ability, which
    #: is how "it gains X and loses all other abilities" keeps its X: the loss
    #: removes only grants older than this. Filled from the state on
    #: construction, and carried along by `dataclasses.replace`.
    began_at: int = -1

    def __post_init__(self) -> None:
        if self.began_at < 0:
            self.began_at = self.state.next_timestamp

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


def ask_targets(
    ctx: EffectContext,
    prompt: str,
    refs: Sequence[tuple[str, TargetRef]],
    min_count: int,
    max_count: int,
    chooser: int,
    purpose: str = "target",
) -> Generator[PendingDecision, list[int], list[TargetRef]]:
    """Declare targets as a **decision** rather than as part of an action.

    Every other target in the engine is chosen by picking one of the cast
    actions legality enumerated, which fixes the targets before the spell has
    been started at all.  A mode-owned target cannot work that way: it is not
    known to be needed until its mode has been chosen, and its mode is chosen
    inside the cast (601.2b).  So this is the same question asked one step
    later, in the printed order.

    ``refs`` is ``(label, ref)`` pairs -- labelled by the caller because naming
    a target is `targeting.describe_ref`'s job and `targeting` imports this
    module, not the other way round.

    Reuses :attr:`DecisionKind.CHOOSE_OBJECTS` on purpose: the answer is an
    ordinal into ``options`` either way, so every seat that can already answer
    "choose a creature to sacrifice" -- the RL encoder, the heuristic agent,
    the client's prompt dialog and the authoring verifier -- answers this with
    no change.  The ``purpose`` tag is what tells them apart.

    ``purpose`` is overridable because a mixed player-or-permanent pick is not
    always a target: a token put onto the battlefield "attacking that player or
    a planeswalker they control" chooses between exactly these two kinds of ref
    (508.4) and targets nothing, so it says ``"attack"`` instead.
    """
    available = list(refs)
    if not available or max_count <= 0:
        return []
    if len(available) <= min_count:
        return [ref for _, ref in available]
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_OBJECTS,
        player=chooser,
        prompt=prompt,
        options=tuple(
            DecisionOption(label=label, ref=ref, value=i)
            for i, (label, ref) in enumerate(available)
        ),
        min_count=min(min_count, len(available)),
        max_count=min(max_count, len(available)),
        context={
            "source": ctx.source_oid,
            "source_name": ctx.source_name,
            "purpose": purpose,
        },
    )
    answer = yield decision
    return [available[i][1] for i in answer]


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
    ctx: EffectContext,
    prompt: str,
    labels: Sequence[str],
    chooser: int,
    count: int = 1,
    up_to: int | None = None,
    purpose: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Generator[PendingDecision, list[int], list[int]]:
    """Ask the controller to choose one or more modes of a modal spell.

    ``purpose`` tags the decision the way `ask_objects`' does, for a seat that
    answers a label question differently by what it is for -- a card name
    (`choose_card_name`) is not a mode, and its first label is no better a guess.

    ``up_to`` makes ``count`` a floor rather than an exact number: "Choose one.
    If you control a commander as you cast this spell, you may choose both
    instead" -- Akroma's Will. Without it a range is unsayable, and the
    short-circuit below turns "choose up to two of two" into "take both", which
    is a different card every time taking one was the better line.

    ``extra`` is merged into the decision's ``context`` -- a ``purpose`` tag and
    whatever the heuristic agent needs to answer it (Aminatou's left-or-right
    names the seat each direction takes from).
    """
    maximum = count if up_to is None else max(count, up_to)
    # Nothing to ask when every mode has to be taken anyway.
    if len(labels) <= count:
        return list(range(len(labels)))
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_MODE,
        player=chooser,
        prompt=prompt,
        options=tuple(DecisionOption(label=label, value=i) for i, label in enumerate(labels)),
        min_count=count,
        max_count=min(maximum, len(labels)),
        context={
            "source": ctx.source_oid,
            "source_name": ctx.source_name,
            **({"purpose": purpose} if purpose else {}),
            **(extra or {}),
        },
    )
    answer = yield decision
    return list(answer)


def ask_x(
    ctx: EffectContext,
    prompt: str,
    max_x: int,
    chooser: int,
    *,
    per_point: int = 1,
    loyalty_cost: bool = False,
    min_x: int = 0,
) -> Generator[PendingDecision, list[int], int]:
    """Ask how big to make ``X`` before the cost is paid.

    ``X`` used to be pinned to :func:`mana.max_affordable_x` by legality, so a
    Blue Sun's Zenith was always cast for everything the player had.  The
    maximum is now only the ceiling of this question.

    Returns ``0`` without asking when there is nothing to choose between, the
    way :func:`ask_mode` declines to ask a forced question.  The ordinal into
    ``options`` is ``X`` itself by construction, which is what lets the RL
    encoder read the slot number as the value.

    ``per_point`` is how much one point of ``X`` actually costs -- ``{X}{X}``
    charges twice -- and is passed through ``context`` so the client can say so
    rather than making the player work it out from the mana row.

    ``loyalty_cost`` marks a planeswalker's -X (606.4): X is paid in the
    source's own loyalty and the ceiling is all of it, so the maximum is the
    one answer that always kills the planeswalker. Carried in ``context`` for
    the agents that would otherwise take the largest X on offer.

    ``min_x`` is a floor under the question: Brisela's "can't cast spells with
    mana value 3 or less" leaves a Fireball castable only for X = 3 or more
    (202.3e). The options start there, so the ordinal is ``X - min_x``, and
    ``min_x`` rides in ``context`` beside ``max_x`` for the client's stepper.
    It is 0 for every question but that one, which keeps the ordinal X itself.
    """
    if max_x <= min_x:
        return min_x
    decision = PendingDecision(
        kind=DecisionKind.CHOOSE_X,
        player=chooser,
        prompt=prompt,
        options=tuple(
            DecisionOption(label=f"X = {i}", value=i) for i in range(min_x, max_x + 1)
        ),
        min_count=1,
        max_count=1,
        context={
            "purpose": "choose_x",
            "max_x": max_x,
            "per_point": per_point,
            "source": ctx.source_oid,
            "source_name": ctx.source_name,
            **({"loyalty_cost": True} if loyalty_cost else {}),
            **({"min_x": min_x} if min_x else {}),
        },
    )
    answer = yield decision
    return min_x + (int(answer[0]) if answer else 0)


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
