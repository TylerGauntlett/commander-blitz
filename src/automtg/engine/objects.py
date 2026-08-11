"""Game objects -- one class for a card in any zone.

A card in hand, a permanent on the battlefield and a spell on the stack are all
the same :class:`GameObject`.  The ``oid`` is *preserved* across zone changes,
where the comprehensive rules would create a brand new object.  Permanent-only
state is reset on every zone change instead.  This is a documented simplification
(``docs/rules-coverage.md``); it only differs from real Magic for effects that
track "the new object", which the curated decks avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import Zone
from .structs import TempEffect

#: Counter kinds the engine understands specially.  Anything else is inert data.
PLUS_ONE = "+1/+1"
MINUS_ONE = "-1/-1"


@dataclass
class GameObject:
    """A single card, token, or copy, wherever it currently is."""

    oid: int
    def_id: str
    owner: int
    controller: int
    zone: Zone
    #: Position within its zone's ordered list (library order matters; hand does not).
    zone_index: int = 0

    # -- permanent state, reset whenever the object changes zones -------------
    tapped: bool = False
    #: Turn number this object arrived on the battlefield; drives summoning sickness.
    entered_turn: int = -1
    damage: int = 0
    #: Set when damage from a deathtouch source was dealt this turn.
    deathtouched: bool = False
    counters: dict[str, int] = field(default_factory=dict)
    attached_to: int | None = None
    until_eot: list[TempEffect] = field(default_factory=list)
    #: Set once "it becomes monstrous"; the whole point of the word is that it
    #: only happens once, so the ability checks this before doing anything.
    monstrous: bool = False
    #: "Those creatures don't untap during their controllers' untap steps for as
    #: long as you control this creature" -- the oid of the permanent holding
    #: them down.  The untap step clears it once that permanent is gone, which is
    #: what makes the lock end with its source rather than lasting forever.
    frozen_by: int | None = None
    #: Whose suspended card this is, while it waits in exile with time counters.
    #: Survives zone changes only in the sense that it is cleared when the card
    #: is finally cast -- see `engine/suspend.py`.
    suspended_by: int | None = None
    #: A creature cast off suspend has haste.  Not an until-end-of-turn effect:
    #: it lasts as long as the permanent does, which is the only reason suspend
    #: is ever better than simply waiting.
    hasted_by_suspend: bool = False
    #: "That land doesn't untap during its controller's next untap step."  A
    #: *one-shot*, cleared by the untap step it skips -- unlike `frozen_by`,
    #: which holds for as long as its source is on the battlefield.  Two
    #: different lifetimes, so two different fields.
    skip_next_untap: bool = False

    # -- identity flags, preserved across zone changes ------------------------
    is_token: bool = False
    is_commander: bool = False

    # -- stack state ----------------------------------------------------------
    #: Set while this object is a spell on the stack (its StackItem id).
    stack_id: int | None = None
    #: The X paid when this object was cast.  Survives resolution so that
    #: "enters with X counters" triggers can read it; reset only on a new cast.
    cast_x: int = 0
    #: Whether the kicker was paid when this object was cast.  Same contract
    #: as ``cast_x`` and for the same reason: Slinn Voda's "When this
    #: creature enters, **if it was kicked**" is an ETB trigger, and by then
    #: the StackItem is gone.  Without this the condition is silently False
    #: on every permanent -- an inert card that loads clean.
    cast_kicked: bool = False
    #: Whether this object was cast for its evoke cost.  Same contract again:
    #: "it's sacrificed when it enters" is an ETB trigger, so the flag has to
    #: outlive the spell.
    cast_evoked: bool = False
    #: An attack *requirement* placed on this creature -- the duration, one
    #: of ``"this_turn"`` or ``"next_combat"``, or None.  Not a TempEffect:
    #: "attacks during its controller's next combat phase" has to survive
    #: the cleanup step, and often a whole turn, because the trigger that
    #: places it fires on *your* turn and binds *their* combat.
    must_attack: str | None = None
    #: The turn the requirement was placed, which is what makes
    #: ``"this_turn"`` expire.
    must_attack_turn: int = 0

    #: "…a token that's a copy of it, **except** it's a white Zombie Angel with
    #: no mana cost." Embalm and eternalize.
    #:
    #: A copy is a token whose ``def_id`` is the original's, so the "except"
    #: clause has nowhere to live on the card -- it is a property of this one
    #: object. Kept deliberately small: added subtypes, replacement colours, and
    #: whether the mana cost is gone. Anything richer belongs in a real
    #: copiable-values layer, which this engine does not have.
    #:
    #: Preserved across zone changes for the same reason ``is_token`` is: it is
    #: part of what the object *is*, not something that happened to it.
    copy_overrides: dict[str, Any] | None = None

    #: "…exile it until this permanent leaves the battlefield." The oid of the
    #: permanent that exiled *this* card, so its own leaves-trigger can find it
    #: again.
    #:
    #: It lives on the exiled card rather than on the exiler because the exiler
    #: is the thing that goes away: Oblivion Ring is in a graveyard by the time
    #: the return happens. The exiled card is sitting in exile, unchanged, and
    #: an oid survives every zone change, so this is the end of the link that
    #: still exists when it is needed.
    #:
    #: Set *after* the move to exile, since `reset_permanent_state` runs during
    #: it. Cleared by that same reset when the card comes back, which is right:
    #: the link is spent once it has been followed.
    exiled_by: int | None = None

    def reset_permanent_state(self) -> None:
        """Wipe everything that only means something on the battlefield."""
        self.must_attack = None
        self.tapped = False
        self.damage = 0
        self.deathtouched = False
        self.counters = {}
        self.attached_to = None
        self.until_eot = []
        self.monstrous = False
        self.frozen_by = None
        self.skip_next_untap = False
        self.exiled_by = None
        # `hasted_by_suspend` is deliberately *not* reset: it is set as the card
        # leaves exile to be cast, and this runs on the way onto the battlefield
        # a moment later. Clearing it here would take the haste straight back.
        self.entered_turn = -1
        self.stack_id = None

    # -- counters -------------------------------------------------------------

    def counter(self, kind: str) -> int:
        return self.counters.get(kind, 0)

    def add_counter(self, kind: str, amount: int = 1) -> int:
        """Add (or with a negative amount, remove) counters; returns the new total."""
        new = self.counters.get(kind, 0) + amount
        if new <= 0:
            self.counters.pop(kind, None)
            return max(new, 0) if amount > 0 else 0
        self.counters[kind] = new
        return new

    def remove_counter(self, kind: str, amount: int = 1) -> int:
        have = self.counters.get(kind, 0)
        taken = min(have, amount)
        if have - taken <= 0:
            self.counters.pop(kind, None)
        else:
            self.counters[kind] = have - taken
        return taken

    # -- convenience ----------------------------------------------------------

    @property
    def on_battlefield(self) -> bool:
        return self.zone is Zone.BATTLEFIELD

    def summoning_sick(self, turn: int) -> bool:
        """True if this creature has not been controlled since the turn began."""
        return self.entered_turn >= turn

    @property
    def abilities_locked(self) -> bool:
        """"Its activated abilities can't be activated this turn."

        Covers mana abilities too, which is why the mana solver has to ask as
        well as legality: a locked land that still taps for mana would make the
        whole effect worth nothing against the only decks that mind it.
        """
        return any(t.kind == "lock_abilities" for t in self.until_eot)

    def to_dict(self) -> dict[str, Any]:
        return {
            "oid": self.oid,
            "def_id": self.def_id,
            "owner": self.owner,
            "controller": self.controller,
            "zone": self.zone.value,
            "tapped": self.tapped,
            "damage": self.damage,
            "counters": dict(self.counters),
            "attached_to": self.attached_to,
            "is_token": self.is_token,
            "is_commander": self.is_commander,
            "entered_turn": self.entered_turn,
            "until_eot": [t.to_dict() for t in self.until_eot],
            "monstrous": self.monstrous,
            "frozen_by": self.frozen_by,
            "skip_next_untap": self.skip_next_untap,
            "suspended_by": self.suspended_by,
            "hasted_by_suspend": self.hasted_by_suspend,
        }
