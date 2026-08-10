"""Actions and pending decisions -- the engine's entire input surface.

Everything a player can ever do is one :class:`Action`.  Everything the engine
can ever ask is one :class:`PendingDecision`.  The HTTP layer and the RL action
space are both just encodings of these two types, which is why a human and a
policy exercise identical rules code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import ActionKind, DecisionKind
from .structs import TargetRef


@dataclass(frozen=True)
class Action:
    """One decision answer from one player.

    ``label`` is display-only and deliberately excluded from equality and
    hashing, so an action reconstructed by the RL decoder compares equal to the
    one legality produced.
    """

    kind: ActionKind
    source: int | None = None
    ability_index: int | None = None
    targets: tuple[TargetRef, ...] = ()
    choice: int | None = None
    x: int = 0
    #: Whether this cast pays the card's kicker cost.  Part of the identity, not
    #: display: "Into the Roil" and "Into the Roil (kicked)" are two different
    #: things to do with the same card and must not compare equal.
    kicked: bool = False
    label: str = field(default="", compare=False)
    #: Permanents the mana solver would tap to pay for this, for the UI's
    #: "what will this leave me with" preview.  Display-only, like ``label``:
    #: excluded from equality and from :meth:`key`, so an action reconstructed
    #: by the RL decoder still compares equal to the one legality produced.
    #: Payment is never taken from an action -- :func:`costs.pay_mana` re-solves
    #: at resolution time, and this is only ever a forecast.
    pays: tuple[int, ...] = field(default=(), compare=False)

    def with_label(self, label: str) -> Action:
        return Action(
            kind=self.kind,
            source=self.source,
            ability_index=self.ability_index,
            targets=self.targets,
            choice=self.choice,
            x=self.x,
            kicked=self.kicked,
            label=label,
            pays=self.pays,
        )

    def key(self) -> tuple:
        """A hashable identity used for deterministic sorting and lookup."""
        return (
            self.kind.value,
            -1 if self.source is None else self.source,
            -1 if self.ability_index is None else self.ability_index,
            tuple((t.kind, t.id) for t in self.targets),
            -1 if self.choice is None else self.choice,
            self.x,
            self.kicked,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": self.source,
            "ability_index": self.ability_index,
            "targets": [t.to_dict() for t in self.targets],
            "choice": self.choice,
            "x": self.x,
            "kicked": self.kicked,
            "label": self.label,
            "pays": list(self.pays),
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Action({self.label or self.kind.value})"


@dataclass(frozen=True)
class DecisionOption:
    """One selectable option presented by a :class:`PendingDecision`."""

    label: str
    ref: TargetRef | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "ref": self.ref.to_dict() if self.ref else None,
            "value": self.value,
        }


@dataclass
class PendingDecision:
    """What the engine is currently waiting on.

    For choice-style decisions the player answers with repeated
    ``CHOOSE`` actions carrying an ordinal into :attr:`options`, plus a final
    ``FINISH_DECLARATION`` when fewer than ``max_count`` selections are allowed.
    """

    kind: DecisionKind
    player: int
    prompt: str = ""
    options: tuple[DecisionOption, ...] = ()
    min_count: int = 1
    max_count: int = 1
    #: Ordinals already chosen for this decision.
    selected: list[int] = field(default_factory=list)
    #: Extra payload (e.g. the source card id) for display and for the encoder.
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def allow_done(self) -> bool:
        """Can the player stop choosing right now?"""
        return len(self.selected) >= self.min_count

    @property
    def is_complete(self) -> bool:
        return len(self.selected) >= self.max_count

    @property
    def remaining_options(self) -> list[int]:
        """Ordinals not yet chosen, in order."""
        taken = set(self.selected)
        return [i for i in range(len(self.options)) if i not in taken]

    def chosen_refs(self) -> list[TargetRef]:
        return [self.options[i].ref for i in self.selected if self.options[i].ref]

    def chosen_values(self) -> list[Any]:
        return [self.options[i].value for i in self.selected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "player": self.player,
            "prompt": self.prompt,
            "options": [o.to_dict() for o in self.options],
            "min_count": self.min_count,
            "max_count": self.max_count,
            "selected": list(self.selected),
            "allow_done": self.allow_done,
            "context": self.context,
        }


#: Decisions that are driven by a suspended effect generator rather than by the
#: turn machine.  Answering one of these resumes ``state.pending_generator``.
GENERATOR_DECISIONS = frozenset(
    {
        DecisionKind.CHOOSE_OBJECTS,
        DecisionKind.CHOOSE_MODE,
        DecisionKind.MAY,
        DecisionKind.CHOOSE_PLAYER,
        DecisionKind.COMMANDER_ZONE_CHANGE,
    }
)

PASS_ACTION = Action(kind=ActionKind.PASS, label="Pass")
DONE_ACTION = Action(kind=ActionKind.FINISH_DECLARATION, label="Done")
YES_ACTION = Action(kind=ActionKind.YES, label="Yes")
NO_ACTION = Action(kind=ActionKind.NO, label="No")
MULLIGAN_ACTION = Action(kind=ActionKind.MULLIGAN, label="Mulligan")
KEEP_ACTION = Action(kind=ActionKind.KEEP, label="Keep")
