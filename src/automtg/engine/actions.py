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
    #: **Gift** (702.164a): which opponent was promised the gift as this spell
    #: was cast, or ``None`` for the line that promised nobody.  A seat rather
    #: than a bool, and part of the identity for a reason `kicked` does not have
    #: to make: the two promised lines of a three-player game cost the same and
    #: are not the same thing to do, because a 1/1 handed to the player on your
    #: left is not a 1/1 handed to the player on your right.
    gift_to: int | None = None
    #: Whether this cast pays the card's *evoke* cost instead of its printed
    #: one.  Part of the identity for the same reason ``kicked`` is: a
    #: Mulldrifter cast for {2}{U} and one cast for {4}{U} are two different
    #: things to do with the same card, and only one of them dies on arrival.
    evoked: bool = False
    #: Cast from a graveyard for its flashback cost. Part of the
    #: action's identity like ``kicked`` and ``evoked``: the same card
    #: may be castable from hand and from the graveyard at once, and
    #: they are different actions at different prices.
    flashback: bool = False
    #: Cast for the card's **overload** cost. Part of the identity for the
    #: reason `kicked` is, and more so: an overloaded spell is a different
    #: action *and* has different targets -- none.
    overloaded: bool = False
    #: How many times this cast pays the card's additional cost -- 0, 1, or any
    #: number for replicate. Part of the identity for the reason `kicked` is:
    #: the count changes both the price and what the spell does.
    additional_times: int = 0
    #: Which branch of a modal additional cost this cast pays -- "discard a card
    #: or pay 3 life". Part of the action's identity for the reason `kicked` is:
    #: the two branches are two prices for the same spell and the player is
    #: choosing between them. `None` when the card has no modal cost.
    additional_choice: int | None = None
    #: Cast out of the exile it was foretold to, for the foretell cost. Part of
    #: the identity like `flashback`: the same card can be nowhere else, but the
    #: price is not the printed one and the action must not compare equal to a
    #: hand cast of the same card.
    foretold: bool = False
    #: Cast **face down** for {3} -- morph. Part of the identity like `kicked`:
    #: a Morph creature cast face down and cast normally are two different
    #: things to do with one card, and they cost differently.
    face_down: bool = False
    #: Cast as the card's **second face** -- the Adventure half, the Aftermath
    #: half, the other half of a split card. Part of the identity for the reason
    #: `face_down` is, and more so than any of them: the two lines are not two
    #: prices for one spell, they are two different spells with different names,
    #: different type lines and different effects.
    second_face: bool = False
    #: Cast **fused** -- both halves of a split card as one spell (702.102a).
    #: Part of the identity like `second_face`, and a third thing again: it is
    #: not either half, it is both, at both prices and with both target lists.
    fused: bool = False
    #: Cast for the card's **bestow** cost, which makes it an Aura spell with
    #: enchant creature. Part of the identity like `evoked`, and more so: the
    #: bestowed line is the only cast variant that carries a *target*, so the
    #: two lines for one card do not even point at the same things.
    bestowed: bool = False
    #: Cast for the card's **mutate** cost. Part of the identity like `bestowed`,
    #: and it carries a target for the same reason: the mutating line names the
    #: permanent the card is merging with, and the ordinary creature line names
    #: nothing.
    mutated: bool = False
    #: Cast for a *conditional* alternative cost -- prowl and spectacle. A
    #: separate flag from ``evoked`` rather than a reuse of it, because
    #: ``evoked`` is read back on the permanent by the "it's sacrificed when it
    #: enters" condition: a spectacle spell reporting `cast_evoked` would be a
    #: card quietly claiming to have been evoked.
    alternative: bool = False
    #: How much of the generic cost is paid with something other than mana --
    #: convoke (creatures tapped) and delve (cards exiled from the graveyard).
    #: Part of the action's identity: convoking two creatures and convoking
    #: three are two different things to do with the same card, at two
    #: different prices.
    pay_generic: int = 0
    #: The creature sacrificed to emerge, chosen as part of the action: how
    #: much the spell costs depends on which one, so two emerge lines with
    #: different sacrifices are two different things to do.
    emerge_oid: int | None = None
    #: Which of a mana ability's ``mana_options`` this activation takes -- the
    #: colour, for "Add one mana of any colour". Part of the identity: tapping
    #: Commander's Sphere for {U} and for {R} are two different things to do.
    #:
    #: Deliberately not folded into ``choice``, which is the ordinal into a
    #: :class:`PendingDecision`'s options and is read as such by the client.
    mana_option: int | None = None
    label: str = field(default="", compare=False)
    #: ``label`` with the ``" -> target, target"`` suffix removed: what this
    #: action *is*, without which of its legal targets this copy aims at.  The
    #: client groups the action list by it, so one card offering six targets is
    #: one row with six chips rather than six identical-looking rows.  Display
    #: -only, like ``label``.
    base_label: str = field(default="", compare=False)
    #: What *this* copy says on its chip when the row is a group -- "{R}" for
    #: one yield of "Add one mana of any colour".  Empty when the only thing
    #: separating a row's actions is which target they aim at, which the client
    #: already names from ``targets``.  Display-only, like ``label``.
    option_label: str = field(default="", compare=False)
    #: Permanents the mana solver would tap to pay for this, for the UI's
    #: "what will this leave me with" preview.  Display-only, like ``label``:
    #: excluded from equality and from :meth:`key`, so an action reconstructed
    #: by the RL decoder still compares equal to the one legality produced.
    #: Payment is never taken from an action -- :func:`costs.pay_mana` re-solves
    #: at resolution time, and this is only ever a forecast.
    pays: tuple[int, ...] = field(default=(), compare=False)

    def with_label(self, label: str, base_label: str | None = None) -> Action:
        return Action(
            kind=self.kind,
            source=self.source,
            ability_index=self.ability_index,
            targets=self.targets,
            choice=self.choice,
            x=self.x,
            kicked=self.kicked,
            gift_to=self.gift_to,
            evoked=self.evoked,
            flashback=self.flashback,
            alternative=self.alternative,
            pay_generic=self.pay_generic,
            emerge_oid=self.emerge_oid,
            mana_option=self.mana_option,
            label=label,
            base_label=label if base_label is None else base_label,
            option_label=self.option_label,
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
            -1 if self.gift_to is None else self.gift_to,
            self.evoked,
            self.flashback,
            self.alternative,
            self.pay_generic,
            -1 if self.emerge_oid is None else self.emerge_oid,
            -1 if self.mana_option is None else self.mana_option,
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
            "gift_to": self.gift_to,
            "evoked": self.evoked,
            "alternative": self.alternative,
            "pay_generic": self.pay_generic,
            "emerge_oid": self.emerge_oid,
            "mana_option": self.mana_option,
            "label": self.label,
            "base_label": self.base_label,
            "option_label": self.option_label,
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
        DecisionKind.CHOOSE_X,
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
