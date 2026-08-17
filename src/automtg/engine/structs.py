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
    another permanent), ``"animate"`` ("becomes a 4/4 creature until end of
    turn"), or ``"control"`` ("gain control of target permanent until end of
    turn").  The lock is not a keyword because it is not a characteristic: it is
    a permission, read by legality and by the mana solver rather than by
    ``chars``, and showing it in a card's keyword list would be a lie.

    ``animate`` is the only kind that touches *base* characteristics, which is
    why ``power``/``toughness`` mean something different for it than they do for
    a pump: a pump's are a delta, an animation's are the value itself.

    ``control`` is the odd one out in the other direction: every other kind is
    read by ``chars`` while it lasts and does nothing when it ends, and this one
    is read by nobody and does all its work *at the end*.  ``change_control``
    has already moved the permanent by the time the entry exists; what the entry
    holds is the two seats the cleanup step needs in order to give it back, and
    it is stored here rather than in a list of its own because ``until_eot`` is
    already emptied by ``reset_permanent_state`` when a permanent leaves the
    battlefield -- which is exactly the handback that must not happen.
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
    #: For ``kind == "control"``: who controlled the permanent before the steal,
    #: and who the steal handed it to.  **Both**, because the handback is
    #: conditional on the second: an effect that gave control to A has nothing
    #: to end if B has since taken the permanent off A permanently, and handing
    #: it to the original controller then would undo somebody else's card.
    previous_controller: int | None = None
    new_controller: int | None = None

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
            "previous_controller": self.previous_controller,
            "new_controller": self.new_controller,
        }


#: The two durations an :class:`AttackRestriction` can carry, and the printed
#: sentence each one is.  Kept beside the class rather than as an enum because
#: every other duration in the DSL is a bare string a card file writes.
ATTACK_RESTRICTION_DURATIONS = ("this_turn", "this_combat")

#: The two durations a control change can carry -- Captivating Vampire's steal
#: and Act of Treason's.  Spelled the way ``grant_keyword``'s pair is, because
#: it is the same distinction on a different field, and enumerated rather than
#: defaulted for a harsher reason than most: a misread ``"until_end_of_turn"``
#: is a *permanent* steal, which is the strictly better card the loader has
#: always refused to let anybody write by accident.
CONTROL_DURATIONS = ("permanent", "until_end_of_turn")


@dataclass(frozen=True)
class AttackRestriction:
    """"That player can't attack you." A prohibition naming **both** sides.

    The engine's other attack prohibitions are facts about one creature --
    `cant_attack`, `defender`, being tapped -- and every one of them is stored on
    the creature, because that is what they are about.  This one is about a
    *pair of players*, and neither of them need own a permanent for it to exist:
    Call for Aid is a sorcery that restricts its own caster.  So it lives on the
    table (:attr:`GameState.attack_restrictions`) beside `monarch` and
    `day_night`, and for the same reason those do.

    ``attacker`` may not declare an attacker against ``defender``.  Both are
    recorded, rather than one plus "the other guy", because the two printed
    shapes point opposite ways: Call for Aid restricts the spell's controller
    from attacking the player it targeted, Champions of Minas Tirith restricts
    the triggering opponent from attacking the ability's controller.  One field
    each is the whole of that difference.

    ``duration`` is ``"this_turn"`` (cleared by the cleanup step) or
    ``"this_combat"`` (cleared when the combat phase ends).  They are not
    interchangeable and neither is the safe default: a turn-scoped restriction
    read as combat-scoped misses the extra combat a Relentless Assault hands
    out, and a combat-scoped one read as turn-scoped taxes that extra combat for
    free.  That is why the op requires the word.
    """

    #: The player who may not attack.
    attacker: int
    #: The player who may not be attacked.
    defender: int
    duration: str = "this_turn"
    #: The permanent or spell that installed it, for the log.  Not part of the
    #: lifetime: unlike `frozen_by` this outlives its source leaving the
    #: battlefield, because a resolved one-shot effect does not care what
    #: happens to the card that made it.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attacker": self.attacker,
            "defender": self.defender,
            "duration": self.duration,
            "source": self.source,
        }


#: The two durations a :class:`BlockProhibition` can carry.  Neither is the one
#: `AttackRestriction` uses, and that is not an oversight -- see the class.
BLOCK_PROHIBITION_DURATIONS = ("this_turn", "until_your_next_turn")


@dataclass(frozen=True)
class BlockProhibition:
    """"That creature can't block this turn." A "can't block" with a **clock**.

    The engine already had "can't block" as a static (`cant_block`, read by
    `characteristics.block_forbidden` off `_battlefield_statics`), and it is the
    wrong shape three ways over for a one-shot effect: it needs a permanent
    source sitting on the battlefield, it lasts exactly as long as that source is
    there, and its `affects` filter may read only printed characteristics -- so
    it can neither name a creature chosen when a trigger resolves nor end at a
    fixed moment.  This is the same sentence with those three properties
    inverted, so it lives on the table (:attr:`GameState.block_prohibitions`)
    beside `attack_restrictions`, for the reason given there: the effect belongs
    to no permanent, and a sorcery leaves none behind to own it.

    **"Prohibition" rather than "restriction"** only to keep two different things
    apart: `block_restriction` is already the *attacker*-side static ("this
    creature can't be blocked by Humans", read by
    `characteristics.block_restrictions`).  That one narrows who may block a
    given attacker; this one stops a given creature blocking at all.

    Two forms, and the difference is whether the set is fixed at resolution:

    ``objects``  a tuple of oids -- "up to one target creature can't block this
                 turn", "those creatures can't block".  The set is chosen when
                 the effect resolves and never grows; a creature that enters
                 afterwards was not one of them.
    ``None``     **every** creature -- Aragorn's "creatures can't block this
                 turn".  Deliberately not a snapshot of the battlefield: that
                 sentence is a turn-scoped continuous effect and catches
                 creatures that enter later in the turn, which is exactly why an
                 op writing a mark onto each creature could not express it.

    ``duration`` is ``"this_turn"`` (cleared by the cleanup step) or
    ``"until_your_next_turn"`` (cleared in :attr:`player`'s untap step, where
    detain is already cleared).  The second is not a turn *number*: eliminate a
    player and "your next turn" moves, which is why the player is recorded and
    the deadline is not.  `AttackRestriction`'s ``this_combat`` is absent because
    no printed "can't block" is scoped to one combat -- a blocking restriction
    that ended with the combat would be indistinguishable from one that never
    existed, since blockers are declared inside it.
    """

    #: The creatures restricted, or ``None`` for "every creature".  A tuple
    #: rather than a set so the record stays hashable and comparable, which is
    #: what lets the primitive deduplicate on the whole entry.
    objects: tuple[int, ...] | None = None
    duration: str = "this_turn"
    #: Whose next turn ends it.  Meaningful only for ``until_your_next_turn``;
    #: recorded for both because it is also who imposed the restriction, which is
    #: what `sba` needs to drop the entries whose clock can never come again.
    player: int | None = None
    #: The permanent or spell that installed it, for the log.  Not part of the
    #: lifetime: a resolved one-shot effect does not care what happens to the
    #: card that made it.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objects": None if self.objects is None else list(self.objects),
            "duration": self.duration,
            "player": self.player,
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
    #: Whether the kicker cost was paid as this spell was cast.  Decided at cast
    #: time and read on resolution, because that is the only place it can be
    #: known: nothing about the object afterwards records what was paid for it.
    kicked: bool = False
    evoked: bool = False
    #: Cast for its **bestow** cost, which makes it an Aura spell with enchant
    #: creature. Read on resolution to decide which target list the spell has:
    #: the printed card declares none, and "enchant creature" comes from the
    #: rule rather than from the card.
    bestowed: bool = False
    #: Cast for its **mutate** cost. Read on resolution both for the target list
    #: (`MUTATE_TARGET`) and because such a spell does not become a permanent of
    #: its own -- it merges into the one it targeted.
    mutated: bool = False
    #: Cast **fused**: both halves at once. Read on resolution for the target
    #: list (both halves' together) and for the effects (both halves', through
    #: one context -- the same shape `spliced` uses, and for the same reason).
    fused: bool = False
    #: Cast from a graveyard for its flashback cost. Read on
    #: resolution both by the `cast_from_graveyard` condition and by
    #: the once-only rider that exiles the card instead of
    #: returning it to the graveyard.
    flashback: bool = False
    #: Cast for the card's overload cost, read on resolution by the
    #: `{"overloaded": true}` condition the card branches on.
    overloaded: bool = False
    #: Card ids spliced onto this spell as it was cast. Their `spell_effects`
    #: run after the host's, in the order they were spliced on -- which is what
    #: "add this card's effects to that spell" means, and why they are recorded
    #: here rather than executed at cast time.
    #: Cast face down for {3} -- morph. Read on resolution, where the permanent
    #: is marked before it enters.
    face_down: bool = False
    spliced: tuple[str, ...] = ()
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
    #: Which card the ability is printed on, snapshotted when the trigger fired.
    #:
    #: A **token** that triggers on its own death is gone by the time the
    #: trigger is drained: the token state-based action pops it out of
    #: `state.objects` rather than moving it to a graveyard, so unlike every
    #: other permanent there is no object left to read the card off. The engine's
    #: explicit-LKI pattern, in the one place a card cannot reach with a
    #: `snapshot` op of its own.
    def_id: str = ""
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
    #: Which creatures each player has **declared as attackers** this turn:
    #: player id -> the oids they attacked with.  Two questions, one record.
    #:
    #: Raid asks only *whether* you attacked, and for six mechanics a
    #: `set[int]` of player ids was the whole answer -- which is what this field
    #: used to be.  Relentless Assault ("untap all creatures that attacked this
    #: turn") and Windbrisk Heights ("if you attacked with three or more
    #: creatures this turn") ask **which** creatures, and neither can be
    #: answered from the board or from live combat state: `end_combat` sets
    #: `state.combat = None`, and both cards are used in the main phase *after*
    #: the combat they are talking about.  `tapped` is the tempting stand-in and
    #: is wrong in both directions -- it catches creatures tapped for mana and
    #: misses vigilant attackers.
    #:
    #: Oids rather than a recount of live permanents, because an attacker that
    #: died in combat still attacked: Windbrisk Heights unlocked by three
    #: attackers, one of which traded, has to stay unlocked in the postcombat
    #: main phase.  A `{"count": {"zone": "battlefield", ...}}` over the board
    #: has forgotten the dead one, which is why the count is read off here.
    #:
    #: The two spellings of the question cannot disagree, because `attacked`
    #: below is derived rather than stored.
    creatures_attacked: dict[int, set[int]] = field(default_factory=dict)
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
    #: Every creature **subtype** that has dealt combat damage to a player this
    #: turn -- prowl, and the one tally here that is not a number.
    #:
    #: "A player was dealt combat damage by a Faerie or a Rogue" cannot be
    #: recovered from any of the tallies above: `damage_taken` says how much and
    #: to whom and nothing about the source, and the source itself may be dead,
    #: bounced or no longer a Faerie by the time a prowl spell is cast. Read off
    #: **derived** subtypes at the moment the damage lands, so a changeling and
    #: a creature granted the type both count -- which is most of what the decks
    #: printing prowl are built on.
    combat_damage_types: set[str] = field(default_factory=set)
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

    #: How many times each ability has been **activated** this turn, keyed the
    #: same way `ability_resolutions` is. Forecast's "only once each turn"
    #: restricts *activating*, not resolving: an ability whose first activation
    #: was countered has still had its go, and a resolution count would hand it
    #: back.
    ability_activations: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def attacked(self) -> set[int]:
        """The players who declared an attacker this turn -- raid's question.

        Derived from `creatures_attacked` rather than stored beside it.  A player
        is in this set exactly when they have an entry there, so "did you attack"
        and "which creatures did you attack with" are one fact read two ways and
        no write can leave them disagreeing.
        """
        return set(self.creatures_attacked)

    def has_attacked(self, oid: int) -> bool:
        """Was this object declared as an attacker this turn, by anybody?

        Asked of an object rather than of a seat, and deliberately not scoped by
        controller: "creatures that attacked this turn" is every attacker in the
        turn, and a creature stolen after combat still attacked.  Callers that
        care whose creature it is now say so with `controller`, which is an
        ordinary clause of the same selector.
        """
        return any(oid in oids for oids in self.creatures_attacked.values())

    def activations(self, oid: int, ability_index: int) -> int:
        return self.ability_activations.get((oid, ability_index), 0)

    def activated(self, oid: int, ability_index: int) -> None:
        key = (oid, ability_index)
        self.ability_activations[key] = self.ability_activations.get(key, 0) + 1

    def resolving(self, oid: int, ability_index: int) -> int:
        """Count this resolution and return how many there have now been."""
        key = (oid, ability_index)
        count = self.ability_resolutions.get(key, 0) + 1
        self.ability_resolutions[key] = count
        return count

    def clear(self) -> None:
        self.creatures_died.clear()
        self.creatures_attacked.clear()
        self.damage_taken.clear()
        self.life_lost.clear()
        self.spells_cast.clear()
        self.combat_damage_types.clear()
        self.ability_activations.clear()
        self.cards_to_graveyard = 0
        self.ability_resolutions.clear()


@dataclass
class CombatState:
    """Everything about the current combat phase."""

    #: attacker oid -> the player being attacked
    attackers: dict[int, int] = field(default_factory=dict)
    #: attacker oid -> the **planeswalker** it is attacking, when it is
    #: attacking one. A parallel map rather than a union in `attackers`, which
    #: is read in about fifteen places: a planeswalker's controller *is* the
    #: defending player (506.2), so every existing read of `attackers[oid]`
    #: keeps meaning what it meant and stays true. Only declaration, damage
    #: assignment and serialization have to know the difference.
    attacking_planeswalker: dict[int, int] = field(default_factory=dict)
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
    #: Bands declared this combat (702.21b): each is a list of attacker oids,
    #: "one or more attacking creatures with banding and up to one without".
    #: A list of lists rather than a map, because a creature is in at most one
    #: band and the band itself is the thing damage is assigned across.
    bands: list[list[int]] = field(default_factory=list)
    #: staged during incremental declaration, before FINISH_DECLARATION validates it
    declaring_player: int | None = None

    def band_of(self, oid: int) -> list[int]:
        """The band this attacker is in, or just itself.

        Returning the singleton rather than ``None`` is what lets the damage
        code treat banded and unbanded attackers with one expression: a
        creature is always assigned across "its band", which is usually a band
        of one.
        """
        for band in self.bands:
            if oid in band:
                return [b for b in band if b not in self.removed]
        return [oid]

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
