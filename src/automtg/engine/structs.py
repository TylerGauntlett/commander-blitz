"""Plain data containers shared by the engine modules.

These live in their own module purely to keep the import graph acyclic:
``state`` needs :class:`CombatState` and :class:`StackItem`, while ``combat`` and
``stack`` need ``GameState``.  Putting the dumb containers here breaks the cycle
without any ``TYPE_CHECKING`` gymnastics.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover
    # Type-only, so this module keeps the no-runtime-imports property its
    # docstring is about: `carddef` is a leaf, but the point of `structs` is
    # that it needs nothing.
    from .carddef import TriggerSpec

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
    #: For ``kind == "keyword"``: the keyword is granted only while it is its
    #: controller's turn. Restless Spire and the rest of the *Restless* cycle
    #: animate into a creature "with \"During your turn, this creature has first
    #: strike\"" -- a quoted ability on the animated body, live for half the
    #: turn cycle.
    #:
    #: A named flag rather than a general `condition`, deliberately. Evaluating
    #: an arbitrary condition inside the characteristics layer is how a static
    #: comes to read another static's output, which the loader forbids
    #: everywhere else; "is it my turn" is a pipeline *input* the way a counter
    #: or a tapped flag is, so it can be read without opening that door.
    only_your_turn: bool = False

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
    #: Does it also stop an attack on ``defender``'s **planeswalkers** -- and,
    #: since battles joined them, on 506.2's third defender kind generally?
    #: The DSL key keeps the name it was written with, because the sentence that
    #: sets it ("creatures can't attack this combat") names no defender at all
    #: and so reaches every kind; the one card that *does* name walkers by hand
    #: is `attack_defender_forbidden`'s, not this.
    #:
    #: ``False`` on every card that names a player, and that is 506.2: "you
    #: can't attack that player this turn" restricts attacking the *seat*, and
    #: attacking a planeswalker they control is not attacking them -- which is
    #: why Ghostly Prison taxes nothing when the attack goes at a walker.
    #:
    #: ``True`` is for the sentence that names **no defender at all**:
    #: "creatures can't attack this combat" (Overencumbered). There is no seat
    #: in that sentence to read narrowly, so it forbids every attack a creature
    #: could declare, and 506.2's three attack targets are all of them. Written
    #: as a flag on the pair rather than a fourth prohibition, because the pair
    #: is already the shape a whole-table lock takes: `each_player` against
    #: `each_player` installs the cross-product, and `restrict_attack` drops the
    #: self-pairs nobody could declare anyway.
    #:
    #: The same divergence, in the same predicate, that goad and the
    #: `cant_attack_you` static already carry, and it is decided the same way
    #: each time: by what the printed sentence names, never by a house rule
    #: about walkers.
    planeswalkers: bool = False
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
            "planeswalkers": self.planeswalkers,
            "source": self.source,
        }


#: The two durations a :class:`BlockProhibition` can carry.  Neither is the one
#: `AttackRestriction` uses, and that is not an oversight -- see the class.
BLOCK_PROHIBITION_DURATIONS = ("this_turn", "until_your_next_turn")



@dataclass(frozen=True)
class GraveyardCastGrant:
    """"Until end of turn, you may cast instant and sorcery spells from any graveyard."

    Urabrask's third chapter, and Yawgmoth's Will before it. The engine's only
    graveyard-cast permission is `cast_from_graveyard`, a **static** read off a
    permanent on the battlefield -- which is the wrong shape three ways for this
    sentence, the same three ways `BlockProhibition` inverted for "can't block":

    - It needs a permanent still on the battlefield, and this chapter exiles the
      Saga in the same breath that grants the permission.
    - It has no clock; this one ends with the turn.
    - It reaches its controller's own graveyard, and this one reaches the table.

    So the grant lives on the table (:attr:`GameState.graveyard_cast_grants`)
    beside `block_prohibitions`, for the reason given there: the effect belongs
    to no permanent, and a Saga that exiles itself leaves none behind to own it.

    ``source`` is kept anyway, and it is not decoration. The rate limit is
    counted per granting object in the turn ledger, and `graveyard_cast_allows`
    resolves `chosen_type`/`chosen_color` against the granter -- both still work
    for an object in exile, because a `GameObject` outlives the zone it was in.

    ``static`` is an ordinary `cast_from_graveyard` static dict, so everything
    downstream -- the `affects_spells` filter, `grants_flashback`,
    `max_per_turn`, and the `cast_from_graveyard` mark that makes the spell
    exile as it resolves -- is the code that already existed rather than a
    second implementation of it.
    """

    player: int
    turn: int
    source: int
    static: Mapping[str, Any]

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


#: The two durations an :class:`Unblockable` can carry -- the same pair
#: :data:`BLOCK_PROHIBITION_DURATIONS` carries, and cleared by the same two
#: hooks.  Both are printed: "target creature can't be blocked **this turn**"
#: (Rogue's Passage, Slip Through Space, Thassa) and "**until your next turn**,
#: target creature an opponent controls can't be blocked" (Sly Instigator).
UNBLOCKABLE_DURATIONS = ("this_turn", "until_your_next_turn")


@dataclass(frozen=True)
class Unblockable:
    """"Target creature can't be blocked this turn." The mirror of
    :class:`BlockProhibition`, pointing the other way down the same wire.

    The two sentences meet in `combat.can_block(state, blocker, attacker)` and
    are otherwise unrelated: a `BlockProhibition` names a would-be **blocker**
    and takes it out of every block; this names an **attacker** and takes every
    blocker out of the block against it.  Neither subsumes the other -- a
    prohibited blocker facing an ordinary attacker still cannot block, and an
    unblockable attacker is unblockable by creatures under no prohibition at all
    -- so they are two lists and two predicates, both consulted, in either order.

    The engine's existing "can't be blocked" is the `block_restriction` static
    (`characteristics.block_restrictions`, "can't be blocked by Humans"), and it
    is the wrong shape for this sentence three ways -- the three the gap record
    for Rogue's Passage names.  A static needs a permanent standing on the
    battlefield to own it, it lasts exactly as long as that permanent is there,
    and its `blockers`/`affects` filters may read only *printed* characteristics.
    So it can say "creatures with flying can't block me, while I am here" and it
    can say nothing about the creature an activated ability targeted, nor about
    the end of this turn.  This is that sentence with the source and the clock
    swapped round, so it lives on the table (:attr:`GameState.unblockables`)
    beside `block_prohibitions`, for the reason given there.

    ``objects`` is the set chosen **at resolution** and it is never empty and
    never a wildcard.  There is deliberately no counterpart of
    `BlockProhibition`'s ``objects=None`` ("every creature", live for the rest of
    the turn): no printed one-shot makes an unrestricted *everything*
    unblockable, and the plural forms that come close are controller-scoped
    ("creatures you control can't be blocked this turn" -- Keeper of Keys), which
    a global sentinel would read as making the opponent's creatures unblockable
    too.  Getting that wrong is a strictly better card, so the shape is refused
    rather than approximated; see `docs/rules-coverage.md`.

    ``duration`` is ``"this_turn"`` (cleared by the cleanup step) or
    ``"until_your_next_turn"`` (cleared in :attr:`player`'s untap step, beside
    detain and block prohibitions).  The second is not a turn *number*: eliminate
    a player and "your next turn" moves, which is why the player is recorded and
    the deadline is not.
    """

    #: The creatures that can't be blocked.  A tuple rather than a set so the
    #: record stays hashable, which is what lets the primitive deduplicate on the
    #: whole entry.
    objects: tuple[int, ...] = ()
    duration: str = "this_turn"
    #: Whose next turn ends it.  Meaningful only for ``until_your_next_turn``;
    #: recorded for both because it is also who granted the evasion, which is
    #: what `sba` needs to drop the entries whose clock can never come again.
    player: int | None = None
    #: The permanent or spell that granted it, for the log.  Not part of the
    #: lifetime: Rogue's Passage may be destroyed in response and the creature it
    #: targeted is still unblockable for the turn.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objects": list(self.objects),
            "duration": self.duration,
            "player": self.player,
            "source": self.source,
        }


#: The durations a :class:`DamageShield` can carry.  One word, and only one, is
#: printed: "prevent all damage that would be dealt to you **this turn**"
#: (Selfless Squire, Fog, Holy Day, Awe Strike).  A tuple of one rather than a
#: bare constant so the loader can name the implemented set in its error the way
#: it does for the two lists above, and so a second word -- if a card ever prints
#: one -- is added here rather than smuggled in as a default nobody clears.
DAMAGE_SHIELD_DURATIONS = ("this_turn",)


@dataclass(frozen=True)
class DamageShield:
    """"Prevent all damage that would be dealt to you this turn."

    A prevention effect over a **player**, which is the shape the engine's two
    existing preventions cannot take.  `prevent_damage` the *static* (absorb N,
    read by `characteristics.prevented_damage`) and `protection` are both keyed
    to an object id: they walk `_battlefield_statics` and match each entry's
    `affects` filter against a *permanent*, and `static_filter_keys` has no way
    to name a seat.  Both are also continuous while their source stands on the
    battlefield, so a creature carrying one would prevent damage on every future
    turn as well -- which is a Worship, not a one-turn fog.

    So this lives on the table (:attr:`GameState.damage_shields`) beside
    `block_prohibitions` and `unblockables`, for the reason given there: the
    effect belongs to no permanent and outlives whatever installed it.  Selfless
    Squire's shield is up for the turn whether or not the Squire survives the
    combat it was flashed into, and Fog leaves no permanent behind at all.

    **All the damage, not N of it.**  There is deliberately no ``amount``: the
    printed sentence this record exists for prevents *all* damage to the player
    for the turn, and absorb-N over a player ("prevent the next 3 damage that
    would be dealt to any target this turn" -- Healing Salve) is a different
    effect with a pool that drains and a target that may be a creature instead.
    Writing it as a shield with a number would be that card's shape and not its
    behaviour, so `loader.py` refuses an ``amount`` on this op outright rather
    than reading one and preventing everything anyway -- which loads clean and
    plays a strictly better card.  See `docs/rules-coverage.md`.

    Not consumed by use.  A shield is a fact about the turn, so it prevents every
    instance of damage that would reach the player until cleanup drops it: three
    attackers get through and all three are prevented, and each one fires its own
    `DAMAGE_PREVENTED`.  That per-instance firing is what makes the Squire's
    "put that many +1/+1 counters" add up to the whole swing.
    """

    #: The seat protected.  Not "whose next turn ends it" -- the only duration is
    #: ``this_turn`` and it ends in the active player's cleanup step whoever is
    #: shielded, which is why `clear_damage_shields` filters on duration alone
    #: rather than reusing `primitives._expired`, whose ``player`` means the
    #: other thing.
    player: int
    duration: str = "this_turn"
    #: The permanent or spell that installed it, for the log.  Not part of the
    #: lifetime: the Squire may be killed in response to its own ETB trigger and
    #: the shield still covers the turn.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "duration": self.duration,
            "source": self.source,
        }


#: The two clocks a :class:`PermanentShield` can run on.  Both are printed:
#: "prevent all damage that would be dealt to him **this turn**" (Gideon Jura,
#: Gideon, Champion of Justice) and "**until your next turn**, prevent all damage
#: target permanent would deal" (Gideon of the Trials, Kiora, the Crashing Wave).
PERMANENT_SHIELD_DURATIONS = ("this_turn", "until_your_next_turn")

#: Which way a :class:`PermanentShield` faces.  ``to`` stops damage dealt **to**
#: the permanent, ``by`` stops damage the permanent **deals**, and ``to_and_by``
#: is Kiora's "dealt to and dealt by" -- one printed clause, so one record.
PERMANENT_SHIELD_DIRECTIONS = ("to", "by", "to_and_by")


@dataclass(frozen=True)
class PermanentShield:
    """"Prevent all damage that would be dealt to him this turn." / "…target
    permanent would deal."

    :class:`DamageShield` aimed at a **permanent** instead of a seat, and able to
    face either way.  Neither existing prevention could say it: the
    `prevent_damage` *static* is continuous for as long as its source stands on
    the battlefield (so as a printed line on Gideon it would shield him on every
    turn, not the one he animated in), and the `prevent_damage` *op* is keyed to
    a player.  Neither can stop damage a permanent *deals* at all.

    Lives **on the object** (:attr:`GameObject.damage_shields`), not on a state
    table, because the effect names that object and 400.7 ends it when the
    object leaves: an oid survives every zone change, so a table entry would
    follow a blinked creature into its next life, while
    `reset_permanent_state` clears this list on the way out.  Goad and detain
    are on the object for the same reason.

    ``duration`` is ``"this_turn"`` (cleared by the cleanup step) or
    ``"until_your_next_turn"`` (cleared in :attr:`player`'s untap step, beside
    detain, goad and the other "until your next turn" tables, and dropped when
    that player leaves the game -- their untap step is never coming).

    Not consumed by use, like `DamageShield`: every instance of damage in the
    window is prevented, and each fires its own `DAMAGE_PREVENTED`.
    """

    #: ``to``, ``by`` or ``to_and_by`` -- see `PERMANENT_SHIELD_DIRECTIONS`.
    dealt: str = "to"
    duration: str = "this_turn"
    #: Whose next turn ends it.  Meaningful only for ``until_your_next_turn``;
    #: recorded for both because it is also who installed the shield.
    player: int | None = None
    #: The permanent or spell that installed it, for the log.
    source: int | None = None

    @property
    def stops_damage_to(self) -> bool:
        return self.dealt in ("to", "to_and_by")

    @property
    def stops_damage_by(self) -> bool:
        return self.dealt in ("by", "to_and_by")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dealt": self.dealt,
            "duration": self.duration,
            "player": self.player,
            "source": self.source,
        }


#: The quality "protection from **everything**" (Teferi's Protection, The One
#: Ring, Progenitus).  A sentinel in the same flat set of strings every other
#: protection quality lives in, rather than a second field: four rules already
#: ask "is this source one of the qualities?" and a boolean beside the set would
#: mean adding a second question to all four, which is exactly how one of them
#: comes to be forgotten.  It cannot collide -- no card type, subtype or colour
#: is called "everything".
PROTECTION_EVERYTHING = "everything"

#: The durations a :class:`PlayerProtection` can carry.  Both printed sentences
#: say "until your next turn"; ``this_turn`` is here because the cleanup step
#: already sweeps every other timed table on that word and a protection that
#: could not say it would be the one exception.
PLAYER_PROTECTION_DURATIONS = ("this_turn", "until_your_next_turn")


@dataclass(frozen=True)
class PlayerProtection:
    """"You gain protection from everything until your next turn."

    Protection over a **player**, which the existing protection cannot be.
    `characteristics.protection_from` walks `_battlefield_statics` and matches
    each static's `affects` against a *permanent*; `static_filter_keys` has no
    way to name a seat, and `grant_protection` resolved its recipients through
    `choose_objects` and skipped anything not `on_battlefield`. So a player
    could never receive it from either end.

    Lives on the table (:attr:`GameState.player_protections`) beside
    `damage_shields`, for that record's reason: the effect belongs to no
    permanent and outlives whatever installed it. Teferi's Protection is an
    Instant that leaves nothing behind at all.

    **One entry per quality**, the way granted object protection is one
    `TempEffect` per quality -- so `player_protection_from` returns the same flat
    set of strings `protection_from` does and the rules that read protection do
    not learn a second shape. :data:`PROTECTION_EVERYTHING` is one of those
    strings.

    ``duration`` is ``"this_turn"`` (cleared by the cleanup step) or
    ``"until_your_next_turn"`` (cleared in :attr:`player`'s untap step, beside
    detain, block prohibitions and unblockables). The second is not a turn
    *number*: eliminate a player and "your next turn" moves, which is why the
    player is recorded and the deadline is not.
    """

    #: The protected seat. Also whose next turn ends it -- both printed cards
    #: say "**you** gain protection … until **your** next turn", one sentence
    #: about one player, so splitting recipient from clock would be inventing a
    #: card.
    player: int
    quality: str = PROTECTION_EVERYTHING
    duration: str = "until_your_next_turn"
    #: The spell or permanent that granted it, for the log. Not part of the
    #: lifetime: Teferi's Protection is in the graveyard before its protection
    #: has done anything at all.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "quality": self.quality,
            "duration": self.duration,
            "source": self.source,
        }


#: The durations a :class:`LifeLock` can carry.  Both are here for the reason
#: :data:`PLAYER_PROTECTION_DURATIONS` carries both: the printed sentence says
#: "until your next turn", and a table the cleanup step cannot sweep on
#: ``this_turn`` would be the one exception among the timed tables.
#: The durations an `OutcomeLock` may carry.  "This turn" is the only one any
#: printed card in this family uses -- Angel's Grace is an Instant and says it
#: outright -- and the list exists so a typo in a card file fails at load time
#: like every other piece of DSL vocabulary.
OUTCOME_LOCK_DURATIONS = ("this_turn",)


@dataclass(frozen=True)
class OutcomeLock:
    """"You can't lose the game this turn and your opponents can't win the game
    this turn." -- Angel's Grace.  Rules 104.2a, 104.3b and 614.

    ``sba._eliminate`` and ``sba.declare_win`` were the engine's only two writers
    of a game result, and `sba.declare_win`'s own docstring listed this among the
    things "deliberately not modelled, because no card in the pool needs it yet",
    adding that it "is replacement-shaped and belongs beside the other continuous
    prohibitions". Angel's Grace is the first card in the pool to need it.

    A **timed table** rather than a static, for `LifeLock`'s three reasons, which
    apply here unchanged: Angel's Grace is an Instant, so no permanent is left
    behind to carry a static; the prohibition ends at a fixed moment rather than
    when a source leaves; and the effect belongs to no object at all. Platinum
    Angel and Abyssal Persecutor want the *continuous* form of the same
    sentence, which is a static and is not built here -- see
    `docs/rules-coverage.md`.

    **Two fields, not one, because they are two sentences.** Angel's Grace prints
    both halves and most cards print only one: Platinum Angel says "you can't
    lose the game and your opponents can't win the game", but Abyssal Persecutor
    says only "you can't win the game". Folding them together would make every
    card in the family symmetric, which none of them is.

    104.3b is why ``cant_lose`` is not the same as setting life to 1: a player
    under it keeps playing at zero or negative life and loses the moment the lock
    ends. That is the whole of what Angel's Grace buys -- a turn at 1 life or
    less to find an answer -- and it is why this is a check inside
    `_player_losses` rather than a rewrite of the life total.
    """

    #: The seat the prohibition is about.
    player: int
    #: "**You** can't lose the game this turn."
    cant_lose: bool = False
    #: "Your opponents can't **win** the game this turn." Recorded against each
    #: named seat rather than as "everyone but the caster", so a one-sided
    #: printing reads the same way a symmetric one does.
    cant_win: bool = False
    duration: str = "this_turn"
    #: What installed it, for the log.
    source: int | None = None


#: The durations a `LifeFloor` may carry.
LIFE_FLOOR_DURATIONS = ("this_turn",)


@dataclass(frozen=True)
class LifeFloor:
    """"Until end of turn, damage that would reduce your life total to less than 1
    reduces it to 1 instead." -- Angel's Grace.  Rule 614.

    A **floor on the total**, not a prevention, and that distinction is the card.
    `DamageShield` is a Fog: the damage never happens, so a player at 40 ends the
    turn at 40. Angel's Grace lets the damage through and stops the total passing
    1, which is why it is normally cast *to survive at 1 life* -- and why it pairs
    with `OutcomeLock` on the same card, since surviving at 1 is useless if the
    next point kills you.

    Its own table rather than a field on `OutcomeLock`, because they are separate
    sentences that separate cards print separately, and one timed table per
    rules-relevant thing is the shape every other table here already has.

    It floors **damage only**, which is the printed word. An ordinary `lose_life`
    walks straight past it, so a Phyrexian cost or a Bitterblossom still takes
    you below 1 under Angel's Grace -- which is correct, and is the reason this is
    read in `damage_player` and nowhere else.
    """

    player: int
    #: The total the damage may not take this player below. 1 on every printed
    #: card, and a field rather than a constant because nothing about the rule
    #: requires that number.
    floor: int = 1
    duration: str = "this_turn"
    source: int | None = None


LIFE_LOCK_DURATIONS = ("this_turn", "until_your_next_turn")


@dataclass(frozen=True)
class LifeLock:
    """"Until your next turn, your life total can't change." -- 118.5, 614.

    A prohibition on the *change*, in **both** directions, and that is what
    separates it from everything the engine already had. `replace_life_loss` is
    the nearest miss and misses three ways: it is a `static_effect`, so only a
    permanent can carry one and an Instant's `spell_effects` cannot install it;
    it multiplies a loss rather than forbidding a change, and a multiplier of
    zero would still be a downward-only rewrite; and it is wired into
    `lose_life` and the loss half of `damage_player` only, so `gain_life` walks
    straight past it. `DamageShield` is player-scoped but stops only damage.

    Damage is still **dealt** while this stands. The lock is on the life total,
    not on the damage: lifelink still gains nothing (that gain is a life change
    too, on whoever has the lock), commander damage is still tallied, and
    `DAMAGE_DEALT` still fires. Only the life total holds still. Protection is
    the effect that stops the damage itself, and Teferi's Protection prints both
    sentences precisely because they are two different things.

    Paying life becomes impossible rather than free (118.4 makes paying life a
    loss of life, and a cost that cannot be paid cannot be paid), so `can_pay`
    refuses it -- which is the difference between a War Room that draws for
    nothing and one that cannot be activated.

    Lives on the table (:attr:`GameState.life_locks`) beside `player_protections`
    and `damage_shields`, for their reason, and shares their clock: cleared in
    :attr:`player`'s untap step, keyed by the seat and never by a turn number.
    """

    #: The seat whose life total is frozen. Also whose next turn ends it: the
    #: printed sentence is one sentence about one player.
    player: int
    duration: str = "until_your_next_turn"
    #: The spell that installed it, for the log. Not part of the lifetime.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "duration": self.duration,
            "source": self.source,
        }


#: The durations a :class:`CastLock` can carry.  Both, for the reason
#: :data:`LIFE_LOCK_DURATIONS` carries both: the printed sentence says "until
#: your next turn", and a timed table the cleanup step could not sweep on
#: ``this_turn`` would be the one exception among them.
CAST_LOCK_DURATIONS = ("this_turn", "until_your_next_turn")


@dataclass(frozen=True)
class CastLock:
    """"Until your next turn, your opponents can't cast spells from anywhere
    other than their hands." -- Avatar's Wrath.

    A prohibition on casting **from named zones**, over named seats, with a
    clock. Three things at once, and the engine had none of them together.

    **Not the `cant_cast_spells` static.** That one is player-wide and total:
    the loader refuses an `affects` or an `amount` beside it (see
    `loader.__init__`) precisely so a narrower printed line cannot load as a
    strictly stronger lock, and written bare here it would forbid the
    opponents' **hand** casts too -- a far harsher card than the one printed.
    It is also a `static_effect`, so only a permanent can carry one, and
    Avatar's Wrath is a sorcery that exiles itself.

    **Not a `set_turn_flag`.** A turn flag is read by `has_turn_flag`
    conditions and by nothing in the legality path, so a player "flagged"
    locked would go on casting; and it expires at the turn boundary rather than
    at the locking player's next turn, which is one turn too soon at a
    four-player table.

    Lives on the table (:attr:`GameState.cast_locks`) beside `life_locks` and
    `player_protections`, for their reason, and shares their clock: cleared in
    :attr:`player`'s untap step, keyed by a seat and never by a turn number,
    because eliminating a player moves everybody else's "next turn".

    :attr:`player` is the seat whose next turn **ends** it -- the `_expired`
    contract every timed table here shares -- and :attr:`affects` is who is
    *locked*. The first table where the two differ, and they have to: the
    printed sentence is "until **your** next turn, **your opponents** can't
    cast", one clock and several other seats. `DamageShield` overloads
    ``player`` the other way and is the reason `clear_damage_shields` cannot
    use `_expired`; splitting the two fields here keeps this table on the
    shared helper.
    """

    #: Whose next turn ends this. Never a turn number.
    player: int
    #: The seats that can't cast. A tuple rather than a set so the record stays
    #: hashable and `==` deduplicates two copies of one sentence.
    affects: tuple[int, ...] = ()
    #: The zones a locked player can't cast from, as `Zone` values. Named
    #: positively rather than as "everywhere except the hand", because the
    #: reader compares against `costs.zone_of` and a positive list needs no
    #: inversion at the point of use -- and because a card that locks exactly
    #: one zone ("can't cast spells from graveyards") is then the same record
    #: with a shorter list.
    zones: tuple[str, ...] = ()
    duration: str = "until_your_next_turn"
    #: The spell that installed it, for the log. Not part of the lifetime:
    #: Avatar's Wrath exiles itself on resolution and the lock stands anyway.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "affects": list(self.affects),
            "zones": list(self.zones),
            "duration": self.duration,
            "source": self.source,
        }


#: The durations a :class:`SacrificeRestriction` can carry.  One word, and only
#: one, is printed: "you can't sacrifice those creatures **this turn**" (Call for
#: Aid).  A tuple of one for the reason :data:`DAMAGE_SHIELD_DURATIONS` is one --
#: so the loader can name the implemented set in its error the way the lists
#: above do, and so a second word, if a card ever prints one, is added here
#: rather than smuggled in as a default nobody clears.
#:
#: `BlockProhibition`'s ``until_your_next_turn`` is deliberately absent: no
#: printed one-shot forbids a sacrifice past this turn, and a duration with a
#: clock nothing ever winds would be a permanent prohibition wearing a
#: temporary one's clothes.
SACRIFICE_RESTRICTION_DURATIONS = ("this_turn",)


@dataclass(frozen=True)
class SacrificeRestriction:
    """"You can't sacrifice those creatures this turn." (701.17b.)

    The engine had **no** sacrifice prohibition at all, and the three things that
    look like one are each a different game action:

    * `lock_abilities` stops a permanent's own activated abilities being
      activated.  A sacrifice outlet is somebody *else's* ability -- an Altar,
      a Bloodthrone Vampire -- and the fodder's abilities have nothing to do
      with it.  It also says nothing about the `sacrifice` op or an edict.
    * `replace_deaths` redirects a permanent's death *after* it has been
      sacrificed.  The creature still leaves the battlefield and the cost is
      still paid, which is not what "can't" means.
    * `indestructible` explicitly does not prevent sacrifice (701.17a), and
      neither does any prevention or protection: a sacrifice is not damage and
      not destruction.

    So it lives on the table (:attr:`GameState.sacrifice_restrictions`) beside
    `attack_restrictions`, `block_prohibitions`, `unblockables` and
    `damage_shields`, for the reason given there: a resolving sorcery leaves no
    permanent behind to own the effect, and the restriction outlives whatever
    installed it.

    **Keyed on the objects, not on a player**, even though the printed sentence
    says "*you* can't sacrifice those creatures".  Only a permanent's controller
    ever sacrifices it (701.17a), and Call for Aid has just handed that
    controller-ship to the spell's own caster -- so "you" and "whoever could
    sacrifice these" name the same seat, and a `player` field would be a second
    way to say the first.  A prohibition that a later control change could slip
    out of would be a strictly better card than the printed one.

    ``objects`` is the set chosen **at resolution** and is never a wildcard.
    "Those creatures" is the set the same spell just gained control of; a
    creature that enters afterwards was not one of them.  There is no
    ``objects=None`` counterpart of `BlockProhibition`'s "every creature": no
    printed one-shot forbids sacrificing the whole board, and a global sentinel
    would read the one-sided printed forms as two-sided ones.
    """

    #: The permanents that can't be sacrificed.  A tuple rather than a set so
    #: the record stays hashable, which is what lets the primitive deduplicate
    #: on the whole entry.
    objects: tuple[int, ...] = ()
    duration: str = "this_turn"
    #: The permanent or spell that installed it, for the log.  Not part of the
    #: lifetime: Call for Aid is a sorcery and is in a graveyard by the time the
    #: opponent reaches for their sacrifice outlet.
    source: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objects": list(self.objects),
            "duration": self.duration,
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
    #: Were :attr:`modes` *asked* as this was cast (601.2b), or is the empty
    #: tuple merely "nobody has chosen yet"?  The two are different answers and
    #: the tuple cannot tell them apart: "choose up to two" is allowed to choose
    #: none, and without this flag `op_choose_mode` reads that as unanswered and
    #: asks again on resolution -- a second question the player already answered,
    #: and one whose modes could no longer declare the targets they own.
    modes_answered: bool = False
    #: Whether the kicker cost was paid as this spell was cast.  Decided at cast
    #: time and read on resolution, because that is the only place it can be
    #: known: nothing about the object afterwards records what was paid for it.
    kicked: bool = False
    #: **Gift** (702.164a): which opponent was promised a gift as this spell was
    #: cast, or ``None`` if none was. Decided at cast time and read on
    #: resolution, exactly as `kicked` is -- and a seat rather than a bool,
    #: because the card's reward effect has to know *whose* it is.
    gift_to: int | None = None
    evoked: bool = False
    #: Cast for its **warp** cost. Read on resolution, and it is the only cast
    #: flag here whose riders are the *rule's* rather than the card's: a warped
    #: permanent is exiled at the beginning of the next end step and may then be
    #: cast from exile on a later turn, and no warp card prints a sentence
    #: saying so. See `_place_after_resolution`.
    warped: bool = False
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
    #: Cast out of a graveyard under a **permission granted by a permanent** --
    #: Edgar, Master Machinist -- rather than by the card's own flashback. The
    #: granting permanent's oid, so the per-turn use is billed to the one the
    #: line was offered under, and `None` for everything else.
    graveyard_permission: int | None = None
    #: "…that artifact **enters tapped**", the rider on that permission. Carried
    #: on the item rather than the object because `reset_permanent_state` runs
    #: on the way onto the battlefield and would wipe a flag set beforehand.
    enters_tapped: bool = False
    #: Cast for the card's overload cost, read on resolution by the
    #: `{"overloaded": true}` condition the card branches on.
    overloaded: bool = False
    #: Which of the card's `additional_cost_options` was paid, by index. Read on
    #: resolution by the `{"cost_option": n}` condition a tiered card branches
    #: on -- the tier that was bought decides which effect happens.
    cost_option: int | None = None
    #: **Spree** (702.166a): which priced modes were bought as this spell was
    #: cast, by index, ascending. Read on resolution by the
    #: `{"spree_mode": n}` condition each printed mode is an `if` on.
    #:
    #: A tuple rather than `cost_option`'s single index, and that is the whole
    #: mechanic: "choose one or more" buys a subset, so a card that recorded
    #: only the first chosen mode would run one effect having charged for three.
    spree_modes: tuple[int, ...] = ()
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
    #: The granter's card id, snapshotted as a granted ability is activated.
    #: Read only when the granter object itself is gone -- a token popped by the
    #: token state-based action -- so the ability still resolves (608.2).
    granted_def_id: str = ""

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
            "gift_to": self.gift_to,
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
    """An effect scheduled to happen later -- at a named step, or on an event.

    "At the beginning of the next end step, return it to the battlefield." The
    engine's ordinary triggers all fire *from* an event that has just happened;
    this is the other shape -- an effect that has already resolved arranging for
    something to happen later, with no object left to hang a trigger on.

    ``turn`` is the turn it was created on, so "the *next* upkeep" is not this
    one when the card is cast during an upkeep.

    ``combat`` is set only by ``step == "end_of_combat"`` and is the
    :attr:`GameState.combat_number` this must fire at.  Every other step happens
    once a turn, so its name is enough to say *when*; a combat phase does not,
    since `extra_combat` shipped, and "at end of combat" means the end of the
    combat the delay was created in rather than the next one to come round.

    ``trigger`` is the **other half of 603.7**, and the two are exclusive: a
    delayed ability waits either for a moment ("at the beginning of the next end
    step") or for an event ("whenever one or more creatures you control deal
    combat damage to one or more players **this turn**").  When it is set,
    ``step`` is ``""`` -- there is no step to be due at, `turn._delay_due` says
    so out loud, and `triggers.collect` is what wakes this one instead.  It
    lives on the same list and in the same struct as the step-scoped form
    because everything else about the two is identical: the bindings are
    captured when it is created, the controller is captured with them, and it
    resolves with no permanent to hang itself on.

    ``duration`` is how long an event-watching subscription is good for, and it
    is the one thing the two printed shapes of it disagree about.  See
    :data:`DELAYED_DURATIONS`.

    ``your_turn`` is the difference between "at the beginning of the next end
    step" and "at the beginning of **your** next end step" -- 16 cards print the
    second, Necropotence among them.  A step name alone cannot tell them apart,
    because every seat has an end step: a delay created at instant speed during
    an opponent's turn is due at *that* opponent's end step under the first
    reading and a full turn later under the second, which for Necropotence is
    the difference between exiling a card and getting it back on the same turn
    somebody else is taking.  `turn._delay_due` compares
    ``state.active_player`` against :attr:`controller` when this is set.
    """

    step: str
    controller: int
    effects: tuple[dict[str, Any], ...] = ()
    bindings: dict[str, Any] = field(default_factory=dict)
    source_oid: int | None = None
    description: str = ""
    turn: int = 0
    combat: int | None = None
    #: "at the beginning of **your** next end step" -- due only on a turn this
    #: trigger's own controller is taking.
    your_turn: bool = False
    trigger: TriggerSpec | None = None
    #: "Whenever **that creature** deals combat damage to a player or
    #: planeswalker this turn" -- Hunter's Insight. The one object this
    #: subscription is about, resolved to an oid *as the delayed ability is
    #: created* and compared against the event's subject when it fires.
    #:
    #: An oid rather than the target spec it came from, for the reason the
    #: bindings and the controller are captured here rather than re-read: the
    #: spell is in a graveyard before the first blow lands, so there is nothing
    #: left to resolve "that creature" against. `TriggerSpec.source` cannot
    #: stand in either -- it says "self", and a delayed ability has no self.
    #:
    #: ``None`` is every delayed trigger printed before this one: Forth
    #: Eorlingas! watches *any* creature you control, so a scope would be a
    #: strictly narrower card.
    subject_oid: int | None = None
    #: Only read when ``trigger`` is set; see :data:`DELAYED_DURATIONS`.
    duration: str = "this_turn"


#: How long an event-watching delayed ability stays subscribed, and what firing
#: does to it.  Two printed shapes, and they differ on both counts at once:
#:
#: ``this_turn``
#:     "**Whenever** one or more creatures you control deal combat damage to one
#:     or more players **this turn**, you become the monarch" (Forth Eorlingas!).
#:     A subscription with a stated lifetime, firing **every** time: an extra
#:     combat this turn is a second batch and a second trigger, so a "fired" flag
#:     would be the wrong shape.  `turn._cleanup_step` is what ends it.
#:
#: ``until_it_fires``
#:     "Exile target creature an opponent controls **until** an opponent becomes
#:     the monarch" (Palace Jailer).  The delayed ability *is* the end of a
#:     duration somewhere else, so it fires **once** and the subscription is then
#:     spent -- and it must outlive the turn, because the crown may not move for
#:     six of them.  `triggers._arm_delayed` strikes it off as it arms, and
#:     `turn._cleanup_step` leaves it alone.
#:
#: ``once_this_turn``
#:     "Copy the **next** instant or sorcery spell with mana value 2 or less you
#:     cast **this turn**" (Sea Gate Stormcaller).  The card the note below used
#:     to say did not exist: it separates the two axes, firing **once** like
#:     `until_it_fires` and expiring at cleanup like `this_turn`.  Struck off by
#:     `triggers._arm_delayed` as it arms, and dropped by `turn._cleanup_step`
#:     whether or not it ever fired.
#:
#: The two axes -- repeating-or-once, and turn-scoped-or-not -- are correlated in
#: the first two printed shapes, which is why this is one field rather than two
#: booleans.  They are **not** the same question, and `once_this_turn` is the
#: combination the other two cannot express: `this_turn` re-arms on every
#: matching spell, which on Sea Gate Stormcaller is a Thousand-Year Storm, and
#: `until_it_fires` outlives the turn, so a Stormcaller whose controller casts
#: nothing cheap copies a spell on some later turn instead.  Both were measured
#: in a real game rather than reasoned about.
DELAYED_DURATIONS = ("this_turn", "until_it_fires", "once_this_turn")


@dataclass(frozen=True)
class EnteredPermanent:
    """One permanent as it was **at the moment it entered the battlefield**.

    "If another Human entered the battlefield under your control this turn"
    (Éowyn, Shieldmaiden).  A past-tense question about an *event*, and the
    board cannot answer it in either direction: `exists` over the battlefield is
    true when a Human has sat there since turn three and nothing entered, and
    false when a Human entered this turn and died before combat.  Both are
    ordinary lines of play, which is why the ledger has to remember the arrival
    itself.

    A **snapshot** rather than a bare oid, and that is the whole design.  The
    record has to be readable after the object has left -- the entered-and-died
    case is exactly what the clause is for -- and once it has, nothing can be
    asked of it: a token is popped out of `state.objects` entirely, a card in a
    graveyard reports *printed* characteristics rather than derived ones, and
    `reset_permanent_state` has emptied whatever a continuous effect had granted
    it.  `creatures_attacked` above stores oids because its readers only count
    them and reach for the ones still on the battlefield; this one is asked
    *which*, filtered by subtype and controller, so the answer has to travel
    with the record.

    Read off **derived** characteristics at the moment of entry, which is the
    call `combat_damage_types` makes one field down and for the same reason: a
    changeling and a creature a static has made a Human both entered as Humans,
    and by the time the trigger is checked the static may be gone.

    ``controller`` is likewise controller-at-entry.  "Entered the battlefield
    under your control" is a fact about the arrival (rule 109.5 / 400.7): a
    creature that entered under an opponent and was stolen afterwards did not
    enter under yours, and one that entered under yours and was stolen away
    still did.
    """

    oid: int
    controller: int
    types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    colors: frozenset[str] = frozenset()

    def matches(
        self,
        *,
        controllers: Iterable[int],
        types: Iterable[str] = (),
        subtypes: Iterable[str] = (),
        colors: Iterable[str] = (),
    ) -> bool:
        """Does this arrival answer a card's filter?

        Spelled exactly as `selectors.matches` spells the same four clauses, so
        a card author who knows one knows the other: ``types`` is all-of ("an
        artifact creature" is both), ``subtypes`` and ``colors`` are any-of ("a
        Human or an Elf").  A clause left out filters nothing.
        """
        if self.controller not in set(controllers):
            return False
        if types and not set(types).issubset(self.types):
            return False
        if subtypes and not (set(subtypes) & self.subtypes):
            return False
        if colors and not (set(colors) & self.colors):
            return False
        return True


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
    #: How many combat phases have **begun** this turn, counting the one in
    #: progress. "If it's the first combat phase of the turn" (Genji Glove,
    #: Aggravated Assault's cousins) is this being 1.
    #:
    #: Not `GameState.combat_number`, which is monotonic for the whole game on
    #: purpose -- a delayed trigger names the combat it must fire in by that
    #: integer, so resetting it per turn would make "at end of combat" fire in
    #: the wrong one. Two counters because they answer two questions: one
    #: identifies a combat for ever, this one counts them within a turn.
    #:
    #: Written by `combat.start_combat` rather than folded in `emit`, unlike
    #: every other tally here: beginning a combat emits no event, and inventing
    #: one to carry a counter would put a new entry on the trigger bus that no
    #: card subscribes to.
    combats: int = 0
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
    #: Life *gained* by each player this turn -- Witch of the Moors' "if you
    #: gained life this turn". Folded off `LIFE_GAINED`, so it counts every
    #: gain the engine makes (the op, lifelink) whatever was on the battlefield
    #: at the time, and it counts the replaced amount the event carries. A gain
    #: that did not happen -- a locked life total, a player who can't gain life
    #: -- fires no event and is not counted. Not derivable from the life total:
    #: gaining 2 and losing 2 leaves it where it was.
    life_gained: dict[int, int] = field(default_factory=dict)
    #: Spells cast this turn, per caster.  Storm counts every spell cast before
    #: it by anybody, which is the sum.
    spells_cast: dict[int, int] = field(default_factory=dict)
    #: **What** was cast, per caster -- the printed id of each spell, in cast
    #: order. Beside the count rather than replacing it, because storm asks only
    #: "how many" and paying a list's length for every storm copy is worse than
    #: keeping both.
    #:
    #: Urabrask is why it exists: "only if you've cast **three or more instant
    #: and/or sorcery spells** this turn" cannot be read off a flat integer, and
    #: the count alone would let three creature spells turn the ability on --
    #: strictly better than the printed card, and silently.
    #:
    #: The id is the face that was **cast**, which is what the event carries: a
    #: disturb cast turns the card over inside `push_spell`, and the half that
    #: was cast is the half the condition is asking about.
    spells_cast_ids: dict[int, list[str]] = field(default_factory=dict)
    #: Cards put into any graveyard from anywhere this turn (gravestorm).
    #: Tokens are excluded because they are not cards, and a token dying is the
    #: single most common way this number would otherwise be wrong.
    cards_to_graveyard: int = 0
    #: Cards that **left** a graveyard this turn, per graveyard owner -- Gau,
    #: Feral Youth: "if a card left your graveyard this turn". The mirror of
    #: `cards_to_graveyard` above and deliberately not folded into it: that one
    #: counts the opposite direction, so it is true in exactly the wrong cases,
    #: and it is a single total across every graveyard at the table where this
    #: has to be answered about *your* graveyard alone.
    #:
    #: Tokens are excluded for the same reason they are there: a token in a
    #: graveyard ceases to exist as a state-based action, and counting that as
    #: "a card left" would make the condition true every turn anything died.
    cards_from_graveyard: dict[int, int] = field(default_factory=dict)
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

    #: Words written onto a permanent that wear off at the turn boundary:
    #: object id -> the flags it has been given **this turn**.  "If this creature
    #: hasn't been **exerted this turn**" (Combat Celebrant, 701.40b).
    #:
    #: The turn-scoped twin of `GameObject.flags`, and a separate store rather
    #: than a second lifetime on that set, for the reason `skip_untap` and
    #: `freeze` are two ops: the two lifetimes are different rules objects and
    #: using either for the other is wrong in both directions.  `obj.flags` is
    #: one-way on purpose -- renown must never be re-earned -- so nothing in the
    #: engine ever removes from it and a guard written there would silently read
    #: "hasn't been exerted this **game**".
    #:
    #: Keyed by oid and cleared with the rest of the ledger, so it needs no
    #: sweep of its own and cannot outlive the turn that wrote it.  Living here
    #: rather than on the object also means the record survives the permanent
    #: leaving the battlefield, which is what "has been exerted this turn" says:
    #: the same argument `creatures_attacked` makes above.
    object_flags: dict[int, set[str]] = field(default_factory=dict)

    #: Every permanent that has **entered the battlefield** this turn, in the
    #: order it arrived, as :class:`EnteredPermanent` snapshots.
    #:
    #: A list rather than a map keyed by player or by oid, because both keys
    #: lose something a card asks for.  Keyed by player it could not answer
    #: "*another* **Human**", which is the filter Éowyn prints and the reason
    #: the snapshot carries characteristics at all.  Keyed by oid it would
    #: collapse the permanent that entered, left and entered again into one
    #: arrival -- and a flicker really is two of them (400.7: a new object each
    #: time), so a card counting arrivals must see both.
    #:
    #: Nothing is ever removed while the turn lasts.  A permanent that entered
    #: and then died still entered, exactly as an attacker that died still
    #: attacked, and that is the case the board-shaped near miss (`exists`)
    #: gets wrong.  Cleared at cleanup with everything else here.
    permanents_entered: list[EnteredPermanent] = field(default_factory=list)

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

    def entered_this_turn(self, oid: int) -> bool:
        """Did **this** permanent enter the battlefield this turn?

        "Zurgo and Ojutai has hexproof as long as **it** entered this turn";
        "If a creature you control **that entered this turn** would deal
        damage…" (Neriv, Heart of the Storm).  The same ledger the
        `permanents_entered_this_turn` value counts, asked of one object instead
        of summed over a filter -- which is the whole difference between the two
        sentences.  Counting cannot say it: the narrowest filter writable over
        the snapshots is a list of *characteristics*, so "an Orc Dragon you
        control entered this turn" is satisfied by any other Orc Dragon and by a
        second copy of the card itself.

        Asked by oid, and asked of the ledger rather than of `entered_turn` on
        the object.  `entered_turn` is the field `summoning_sick` reads and means
        something else on purpose: `change_control` stamps it, because 302.6 says
        a permanent has not been under its new controller since their turn began.
        Stealing a creature is not that creature entering the battlefield, so a
        filter reading that field would double an Act of Treason'd attacker under
        Neriv and hand a stolen commander hexproof.  The ledger records
        *arrivals* and nothing else.

        Nothing is removed while the turn lasts, so a permanent that entered,
        left and came back still answers yes -- it has an entry for the trip it
        is currently on, which is the one the printed line asks about.
        """
        return any(entry.oid == oid for entry in self.permanents_entered)

    def set_object_flag(self, oid: int, flag: str) -> None:
        """Write a word onto an object for the rest of this turn."""
        self.object_flags.setdefault(oid, set()).add(flag)

    def has_object_flag(self, oid: int, flag: str) -> bool:
        """Has this object been given that word **this turn**?"""
        return flag in self.object_flags.get(oid, ())

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
        self.life_gained.clear()
        self.spells_cast.clear()
        self.spells_cast_ids.clear()
        self.combat_damage_types.clear()
        self.ability_activations.clear()
        self.cards_to_graveyard = 0
        self.cards_from_graveyard.clear()
        self.ability_resolutions.clear()
        self.object_flags.clear()
        self.permanents_entered.clear()
        self.combats = 0


@dataclass
class CombatState:
    """Everything about the current combat phase."""

    #: attacker oid -> the player being attacked
    attackers: dict[int, int] = field(default_factory=dict)
    #: attacker oid -> the **permanent** it is attacking, when it is attacking
    #: one rather than a seat. A parallel map rather than a union in
    #: `attackers`, which is read in about fifteen places: the permanent's
    #: controller *is* the defending player (506.2), so every existing read of
    #: `attackers[oid]` keeps meaning what it meant and stays true. Only
    #: declaration, damage assignment and serialization have to know the
    #: difference.
    #:
    #: Named for the *kind of thing* rather than for planeswalkers, because
    #: 506.2 has three attack targets and this map holds two of them: a
    #: planeswalker and a **battle** (310.7) are the same slot in the
    #: declaration, differing only in which counter the damage comes off. It
    #: was `attacking_planeswalker` while a walker was the only one.
    attacking_permanent: dict[int, int] = field(default_factory=dict)
    #: blocker oid -> the attacker it is blocking
    blockers: dict[int, int] = field(default_factory=dict)
    #: attacker oid -> ordered list of blocker oids (damage assignment order)
    block_order: dict[int, list[int]] = field(default_factory=dict)
    #: creatures that left combat (destroyed, bounced, removed)
    removed: set[int] = field(default_factory=set)
    #: which defending players still have to declare blocks, in APNAP order
    pending_blockers: list[int] = field(default_factory=list)
    #: The seat declaring blocks **for** every defender this combat, when one
    #: effect has taken that choice over: "you choose which creatures block this
    #: combat and how those creatures block" (Odric, Master Tactician).
    #:
    #: On the combat rather than on a player, because the printed duration is
    #: "this combat" -- it dies with `state.combat` and needs no separate clock,
    #: and a second combat granted the same turn correctly starts free of it.
    #: The defenders' creatures and every block-legality check are unchanged;
    #: only who answers the DECLARE_BLOCKERS decision moves.
    blocker_chooser: int | None = None
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
