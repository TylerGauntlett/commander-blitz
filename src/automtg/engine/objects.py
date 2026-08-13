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
    #: Which zone this card was cast from, recorded by `stack.push_spell`.
    #: Rebound is "if you cast this spell **from your hand**", and that clause
    #: is the loop guard: a rebounded spell is cast from exile, so without it
    #: the card would rebound again every upkeep for ever.
    cast_from_hand: bool = False
    #: Which **colours of mana were actually spent** casting this -- sunburst
    #: (702.43a) and converge. Recorded by `pay_mana`, which is the only moment
    #: it is knowable: `ManaPool.spend` decrements six integers and afterwards
    #: one blue mana is indistinguishable from another. Counts mana spent on the
    #: *generic* part too, which is what both keywords say -- a Sunburst artifact
    #: cast for `{4}` off five different lands enters with five counters.
    colors_spent: frozenset[str] = frozenset()
    #: The player owed a free cast at their next upkeep -- rebound (702.87a).
    #: Written on the *exiled card* rather than anywhere else, the way
    #: `suspended_by` is, because the thing waiting is the card itself.
    rebound_by: int | None = None
    #: Regeneration shields (701.15): "the **next** time this permanent would be
    #: destroyed this turn, instead …". A count rather than a boolean, because
    #: "regenerate it twice" is two shields and each is spent by one
    #: destruction. Cleared at cleanup with the rest of the until-end-of-turn
    #: state -- it is one of the few things whose whole content is that it
    #: expires.
    regeneration_shields: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    attached_to: int | None = None
    until_eot: list[TempEffect] = field(default_factory=list)
    #: Set once "it becomes monstrous"; the whole point of the word is that it
    #: only happens once, so the ability checks this before doing anything.
    monstrous: bool = False
    #: One-way words a permanent has become: ``renowned``, and whatever the next
    #: set prints. Generic where `monstrous` is a field of its own, because the
    #: pattern turned out to repeat and each new adjective would otherwise be a
    #: boolean, a condition leaf and an op -- three edits to say one word.
    #:
    #: `monstrous` is deliberately *not* folded in here: it carries a
    #: `became_monstrous` event and an op that reads it, and rewriting a shipped
    #: mechanic to prove a point about tidiness is not what this is for.
    flags: set[str] = field(default_factory=set)
    #: "Those creatures don't untap during their controllers' untap steps for as
    #: long as you control this creature" -- the oid of the permanent holding
    #: them down.  The untap step clears it once that permanent is gone, which is
    #: what makes the lock end with its source rather than lasting forever.
    frozen_by: int | None = None
    #: Whose suspended card this is, while it waits in exile with time counters.
    #: Survives zone changes only in the sense that it is cleared when the card
    #: is finally cast -- see `engine/suspend.py`.
    suspended_by: int | None = None
    #: Whose foretold card this is, while it waits face down in exile, and the
    #: turn it was put there. Both are needed: 702.143a says "on a **later**
    #: turn", so a card foretold and cast on the same turn would be the printed
    #: cost paid in two instalments with the discount thrown in.
    foretold_by: int | None = None
    foretold_turn: int = -1
    #: A creature cast off suspend has haste.  Not an until-end-of-turn effect:
    #: it lasts as long as the permanent does, which is the only reason suspend
    #: is ever better than simply waiting.
    hasted_by_suspend: bool = False
    #: Keywords granted for as long as this permanent lasts -- riot's "or with
    #: haste". Deliberately *not* an `until_eot` `TempEffect`: those are wiped
    #: at cleanup, and a riot creature that lost its haste at end of turn would
    #: be indistinguishable from one that took the counter. Reset with the rest
    #: of the battlefield state, because a permanent that leaves and returns
    #: makes the choice again.
    granted_keywords: set[str] = field(default_factory=set)
    #: "That land doesn't untap during its controller's next untap step."  A
    #: *one-shot*, cleared by the untap step it skips -- unlike `frozen_by`,
    #: which holds for as long as its source is on the battlefield.  Two
    #: different lifetimes, so two different fields.
    skip_next_untap: bool = False
    #: Seats that have been *shown* this card while it sits in a hidden zone.
    #: "Look at target player's hand" (Glasses of Urza) is private information:
    #: it is not `reveal`, which is public and tells the whole table. Recorded
    #: on the card rather than as an event, because what a player is entitled to
    #: see has to be answerable every time `player_view` is built, not only in
    #: the instant the ability resolved.
    #:
    #: Cleared by `reset_permanent_state`: a card that changes zones is a new
    #: object, and having seen a card in somebody's hand does not entitle you to
    #: keep seeing it after it has been played and bounced back.
    revealed_to: set[int] = field(default_factory=set)

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
    #: Whether this object was cast from a graveyard for its flashback cost.
    #: Same contract as the two above, and it does two jobs: Increasing
    #: Devotion's "if this spell was cast from a graveyard" reads it, and the
    #: once-only rider reads it to send the card to exile instead of back to
    #: the graveyard.
    #:
    #: `zone_is` cannot answer either question: it reports the source's
    #: *current* zone, which for any resolving sorcery is the stack, identically
    #: whether it was cast from hand or from the graveyard.
    cast_from_graveyard: bool = False
    #: Whether this object was cast for its **overload** cost. Same contract as
    #: `cast_kicked`: the flag has to outlive the spell, because an overloaded
    #: permanent's own enters trigger may read it.
    cast_overloaded: bool = False
    #: How many times this object's additional cost was paid as it was cast --
    #: casualty and replicate. On the object rather than only the StackItem,
    #: because a "when you cast this spell" trigger reads it while the spell is
    #: still on the stack and a permanent's enters trigger may read it after.
    cast_additional: int = 0
    #: Whether this object was cast **transformed** -- disturb. Kept beside the
    #: other `cast_*` flags rather than relying on `transformed`, because
    #: `reset_permanent_state` clears that on the way onto the battlefield
    #: (712.13a, "enters front face up") and disturb is the one case that must
    #: survive it.
    cast_transformed: bool = False
    #: An attack *requirement* placed on this creature -- the duration, one
    #: of ``"this_turn"`` or ``"next_combat"``, or None.  Not a TempEffect:
    #: "attacks during its controller's next combat phase" has to survive
    #: the cleanup step, and often a whole turn, because the trigger that
    #: places it fires on *your* turn and binds *their* combat.
    must_attack: str | None = None
    #: The turn the requirement was placed, which is what makes
    #: ``"this_turn"`` expire.
    must_attack_turn: int = 0
    #: The mirror: which attacker this creature must block, if able (provoke,
    #: and the lure family).  An oid rather than a bool, because a block
    #: requirement always names *what* to block -- "blocks this creature if
    #: able" -- where an attack requirement names nothing.  Scoped to one
    #: combat and cleared when blockers are locked in, so unlike
    #: ``must_attack`` there is no duration to carry.
    must_block: int | None = None
    #: Detain (701.30a): "until **your** next turn, that permanent can't attack
    #: or block and its activated abilities can't be activated". The pid of the
    #: player who detained it, cleared by that player's own untap step.
    #:
    #: Not a `TempEffect`, for the reason `must_attack` is not: `until_eot` is
    #: wiped at cleanup, and detain has to outlive the turn it was cast in --
    #: usually by a whole turn cycle. Not a turn *number* either, because
    #: "your next turn" moves when a player is eliminated; the player is the
    #: durable thing to name, exactly as `frozen_by` names a permanent.
    detained_by: int | None = None

    #: "As this artifact enters, choose a creature type." The type this
    #: permanent's controller named, read back by its own abilities through
    #: ``{"chosen_type_of": "self"}``.
    #:
    #: Reset with the rest of the battlefield state: a permanent that leaves and
    #: comes back is a new object as far as the rules are concerned, and chooses
    #: again.
    chosen_type: str | None = None

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

    #: "It becomes a Vampire in addition to its other types." Captivating
    #: Vampire — a *one-shot* type change with no duration, which is a different
    #: thing from the `add_subtype` **static** even though they read alike: the
    #: static applies continuously to whatever currently matches its filter,
    #: while this is written onto one object and stays there.
    #:
    #: Object state rather than a static's output, which is what makes it safe
    #: for a static's `affects` filter to read: nothing in the characteristics
    #: pipeline can change it, so no static comes to depend on another static.
    #: That matters for the card it was built for — Captivating Vampire's own
    #: "other Vampire creatures you control get +1/+1" has to see the creature
    #: it just converted.
    #:
    #: Reset with the rest of the battlefield state: a permanent that leaves and
    #: comes back is a new object, and arrives with its printed type line.
    added_subtypes: tuple[str, ...] = ()

    #: Which face of a transforming double-faced card this permanent is showing.
    #:
    #: The whole of the mechanic, because `GameState.card_of` is a single choke
    #: point: flip this and every reader of the card's characteristics -- the
    #: layers, legality, combat, the serializer -- sees the other face with no
    #: change of its own.
    #:
    #: Reset with the rest of the battlefield state, which is rule 712.13a: a
    #: permanent that leaves and comes back is a new object and enters with its
    #: **front** face up. Getting this wrong hands somebody a 5/5 lord for a
    #: blink.
    transformed: bool = False

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
        self.must_block = None
        self.detained_by = None
        self.granted_keywords = set()
        self.tapped = False
        self.damage = 0
        self.deathtouched = False
        self.regeneration_shields = 0
        self.counters = {}
        self.attached_to = None
        self.until_eot = []
        self.monstrous = False
        # A permanent that left and came back is a new object as far as the
        # rules are concerned, so it is no longer renowned either.
        self.flags = set()
        self.frozen_by = None
        self.skip_next_untap = False
        self.exiled_by = None
        self.chosen_type = None
        self.added_subtypes = ()
        self.transformed = False
        self.revealed_to = set()
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
        return self.detained_by is not None or any(
            t.kind == "lock_abilities" for t in self.until_eot
        )

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
            "added_subtypes": list(self.added_subtypes),
            "transformed": self.transformed,
            "attached_to": self.attached_to,
            "is_token": self.is_token,
            "is_commander": self.is_commander,
            "entered_turn": self.entered_turn,
            "until_eot": [t.to_dict() for t in self.until_eot],
            "monstrous": self.monstrous,
            "flags": sorted(self.flags),
            "detained_by": self.detained_by,
            "granted_keywords": sorted(self.granted_keywords),
            "frozen_by": self.frozen_by,
            "skip_next_untap": self.skip_next_untap,
            "suspended_by": self.suspended_by,
            "hasted_by_suspend": self.hasted_by_suspend,
        }
