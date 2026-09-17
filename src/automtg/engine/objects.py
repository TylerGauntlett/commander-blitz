"""Game objects -- one class for a card in any zone.

A card in hand, a permanent on the battlefield and a spell on the stack are all
the same :class:`GameObject`.  The ``oid`` is *preserved* across zone changes,
where the comprehensive rules would create a brand new object.  Permanent-only
state is reset on every zone change instead.  This is a documented simplification
(``docs/rules-coverage.md``); it only differs from real Magic for effects that
track "the new object", which the curated decks avoid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .enums import Step, Zone
from .structs import TempEffect

#: Counter kinds the engine understands specially.  Anything else is inert data.
PLUS_ONE = "+1/+1"
MINUS_ONE = "-1/-1"
#: A **shield counter** (122.1c): "If this permanent would be dealt damage or
#: destroyed, remove a shield counter from it instead."
#:
#: A rules-defined counter kind rather than a keyword, and the distinction is the
#: whole reason it is a constant here beside the P/T counters instead of a member
#: of `enums.Keyword`. A keyword counter grants a keyword and the characteristics
#: pipeline reads it off `enums.KEYWORD_COUNTERS`; a shield counter grants
#: nothing and is *spent*, once per event, by two replacements that live where
#: every damage and every destruction already passes -- `primitives.
#: damage_permanent` and `zones.destroy`. Named here because both of them, and
#: the loader's near-miss guard, have to agree on the exact string: it is stored
#: in `GameObject.counters` like any other kind, so `move_counters` carries it
#: onto a creature the shielding card never mentions and it keeps working there.
SHIELD = "shield"


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
    #: Whether **this** arrival on the battlefield was a spell its controller
    #: cast -- rule 603.6e's "when this permanent enters, **if it was cast**".
    #:
    #: Stamped by `zones._enter_battlefield` on *every* entry, so it always
    #: describes the trip the permanent is on rather than anything it did
    #: earlier. That is the whole of why it exists beside `cast_step`: the cast
    #: stamps are written once by `stack.push_spell` and deliberately outlive
    #: the spell, so a permanent that was cast, died and was reanimated still
    #: answers `cast_step is not None` -- and a card that read the clause that
    #: way would hand out its enters payload again off every reanimation and
    #: every blink, which is a strictly cheaper card than the printed one.
    #:
    #: Both halves are required and neither alone is the sentence. The arrival
    #: cause says the object got here as a *resolving spell*, which a token, a
    #: reanimation and a Show and Tell all fail; `cast_step` says a player
    #: actually **cast** it, which a copy of a permanent spell fails (707.10 --
    #: a copy on the stack was never cast) even though it does resolve.
    #:
    #: Deliberately **not** cleared by `reset_permanent_state`. Nothing off the
    #: battlefield may read it -- the loader confines the clause to an enters
    #: trigger -- except the 603.4 re-check of that trigger's own intervening-if
    #: after the permanent has already left, and there 603.6e wants the
    #: last-known answer, which is the one it kept.
    entered_by_cast: bool = False
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
    #: How much mana was actually **spent** casting this spell, written by
    #: `pay_mana` beside `colors_spent` and at the same instant, for the same
    #: reason: it is knowable exactly once, while the payment is happening.
    #:
    #: "…if **at least four mana was spent** to cast it" -- The Emperor of
    #: Palamecia. Not the printed mana value: a cost reduction, an alternative
    #: cost, a free cast and an additional cost all move what was paid without
    #: moving what is printed, and the card asks about the payment.
    mana_spent: int = 0
    #: "If a creature dealt damage this way would die this turn, exile it
    #: instead." A zone name, replacing the graveyard as this permanent's
    #: destination when it would die. Per-object and turn-scoped -- cleared at
    #: cleanup with the other until-end-of-turn effects, and by
    #: `reset_permanent_state`, so it cannot ride the card out of the zone it
    #: was redirected into.
    dies_to: str | None = None
    #: "Exile it ... **if it would leave the battlefield**" -- unearth, and
    #: embalm's cousins. A zone name replacing this permanent's destination
    #: whichever way it leaves: destroyed, sacrificed, bounced to hand, exiled
    #: by removal, shuffled into a library, sent to the command zone.
    #:
    #: Deliberately **not** `dies_to` with a wider gate, because the lifetimes
    #: differ and that is the whole point. `dies_to` is turn-scoped -- "would
    #: die **this turn**" -- and is cleared at cleanup. This one lasts exactly
    #: as long as the permanent is on the battlefield, so it is cleared only by
    #: `reset_permanent_state`, on the zone change that consumes it. An unearth
    #: replacement that expired at end of turn would let the card be unearthed
    #: again next turn, which is the loop the printed clause exists to close.
    leaves_to: str | None = None
    #: "…become a copy of another target creature you control, **except its name
    #: is Gogo, Mysterious Mime**." A layer-1 copy effect applied *in place*.
    #:
    #: The def id this permanent is currently copying, read by `state.card_of`
    #: -- the one place a permanent's current face is decided, so a copy shows
    #: everywhere at once exactly as a transform does, and no reader of a card
    #: needed changing. `copy_permanent` is a different thing entirely: it makes
    #: a new **token** and never alters the object it points at.
    copying: str | None = None
    #: The name the copy keeps, for the "except its name is…" clause. `None`
    #: takes the copied card's own name, which is the ordinary case.
    copying_name: str | None = None
    #: Whether the copy above expires at cleanup. Clone copies permanently;
    #: Gogo copies "until end of turn", and only that form is cleared.
    copying_until_eot: bool = False
    #: When this card reached a graveyard, and from where -- Banon, the
    #: Returners' Leader: "cards in your graveyard that were put there **from
    #: anywhere other than the battlefield this turn**".
    #:
    #: Per card, which is the whole point: `TurnLedger.cards_to_graveyard` is a
    #: bare integer across every graveyard at the table and retains neither
    #: which cards arrived nor where they came from, so a selector reading it
    #: could only ever see the whole yard -- and Banon would recur a creature
    #: that died in combat five turns ago.
    #:
    #: Set by `zones.move_object` on the way in and left alone afterwards.
    #: `reset_permanent_state` does not clear it, because a card that leaves the
    #: graveyard has no use for it and one that comes back is written again.
    graveyard_turn: int = -1
    graveyard_from: str | None = None
    #: Which **permanents' mana abilities made the mana that paid for this** --
    #: Path of Ancestry, Opal Palace, "when that mana is spent". Recorded by
    #: `pay_mana` alongside `colors_spent`, for the same reason and at the same
    #: instant: the pool holds six integers and the permanent that made a pip is
    #: unrecoverable the moment the pip is gone.
    mana_sources_spent: frozenset[int] = frozenset()
    #: Rebound **granted to a spell that does not print it** -- Ojer Pakpatiq's
    #: "whenever you cast an instant spell from your hand, it gains rebound".
    #: Read beside `card.rebound` in `_place_after_resolution`, exactly as
    #: `playable_exiles` is read beside `card.graveyard_cast_exiles`: the card
    #: field is what a spell says about itself and this is what somebody else
    #: said about it, and the resolution rider cannot tell the difference.
    #:
    #: Set on the **spell's object while it is still on the stack**, which is
    #: the only window there is -- the rider is consulted during resolution and
    #: the stack list is popped by the time an effect could reach it afterwards.
    granted_rebound: bool = False
    #: "Exile that spell instead of putting it into your graveyard as it
    #: resolves. If you do, it becomes plotted." (Lilah, Undefeated Slickshot.)
    #:
    #: The same slot and the same window as `granted_rebound`: written on the
    #: spell's object while it is still on the stack, read by
    #: `_place_after_resolution`, and turned into the plotted permission after
    #: the move -- because `reset_permanent_state` runs on the way to exile and
    #: would wipe a permission set before it, which is what `rebound_by` and
    #: `exiled_by` both discovered first.
    granted_plot: bool = False
    #: "As this land enters, you may pay 3 life." Whether the controller took
    #: that offer, answered just before the move and read by the enters
    #: replacements a moment later. Deliberately survives
    #: `reset_permanent_state` -- see the note there -- and is cleared by
    #: `_enter_battlefield` once it has been read.
    enters_cost_paid: bool = False
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
    #: What this was attached to a moment ago -- last-known information for the
    #: leave-the-battlefield events. `zones.move_object` calls `_detach_all`
    #: *before* it fires LEAVES_BATTLEFIELD and DIES, so by the time a "whenever
    #: equipped creature dies" trigger is matched the Equipment is attached to
    #: nothing and `attached_to` can never be the answer. Written only by
    #: `_detach_all` and cleared by `attach`; a stale value is harmless because
    #: oids are never reused, so it can only ever match the object it named.
    last_attached_to: int | None = None
    #: **The player this Aura enchants** -- "Enchant opponent" (Overencumbered),
    #: "Enchant player" (Sleeper's Robe). 303.4a lets an Aura's enchant ability
    #: name a *player*, and 704.5n is the state-based action that follows: an
    #: Aura attached to an illegal **object or player**, or to nothing at all, is
    #: put into its owner's graveyard.
    #:
    #: A field of its own rather than a second meaning for `attached_to`, and
    #: that is forced rather than tidy: a player id and an oid are both `int`,
    #: so one field holding either could not be read without a discriminator on
    #: every single reader. `attached_to` is consulted by the characteristics
    #: layer, the `attached` selector and trigger filters, `_detach_all`, the
    #: phasing rules and bestow, and each of those means "the *permanent* I am
    #: on"; a seat number arriving in that field would be an oid pointing at
    #: some unrelated object -- silently, and differently in every game.
    #:
    #: The two are mutually exclusive: an Aura is attached to exactly one thing
    #: (301.5c's shape for Equipment, 303.4 for Auras), so `attach` and
    #: `attach_to_player` each clear the other's link.
    #:
    #: There is no `last_attached_to_player`. That field exists for the
    #: leave-the-battlefield events, which `_detach_all` clears the link before
    #: firing; a player does not leave the battlefield, so nothing detaches this
    #: on the way out and `attached_to_player` is still readable when the Aura's
    #: own dies trigger is matched.
    attached_to_player: int | None = None
    until_eot: list[TempEffect] = field(default_factory=list)
    #: What ``until_eot`` held a moment before this object left the battlefield.
    #: Last-known information, in the same style as `last_attached_to`:
    #: `move_object` calls `reset_permanent_state` -- which empties `until_eot` --
    #: *before* it fires LEAVES_BATTLEFIELD and DIES, so a triggered ability
    #: granted until end of turn is gone by the time its own death event goes
    #: out. Malakir Rebirth is the whole card: "that creature gains 'when this
    #: creature dies, return it to the battlefield'".
    #:
    #: Written by `move_object` and cleared as the object next enters the
    #: battlefield, so it can only ever answer for the departure it describes.
    left_with: tuple[TempEffect, ...] = ()
    #: Set once "it becomes monstrous"; the whole point of the word is that it
    #: only happens once, so the ability checks this before doing anything.
    monstrous: bool = False
    #: **A Class's level** (716). Every permanent enters at level 1 (716.3) and
    #: only a "{cost}: Level N" ability raises it -- through the `become_level`
    #: op -- so on anything that is not a Class it is 1 for ever and gates
    #: nothing.
    #:
    #: A property of the permanent, and **not a counter**: proliferate cannot
    #: reach it, `move_counters` cannot take it, and "remove all counters" leaves
    #: it alone. Not a copiable value either (707.2), so a token copy of a
    #: level-3 Class is a fresh object at level 1.
    #:
    #: Set back to 1 as the object *enters* the battlefield
    #: (`zones._enter_battlefield`) rather than cleared by
    #: `reset_permanent_state` on the way out. The difference is last known
    #: information: a leaves-the-battlefield trigger is collected off the object
    #: after it has left (603.10a), and it has to see the abilities the Class had
    #: at the level it had.
    class_level: int = 1
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
    #: Soulbond (702.94a): the creature this one is paired with. Symmetric --
    #: both objects carry the link -- because "as long as this creature is
    #: paired" is asked of *either* of them, and a one-sided link would make
    #: only one of the two buffed.
    #:
    #: Not `attached_to`, which is one-way, is read by `attached` filters as
    #: "the thing I am on", and carries the state-based action that bins an Aura
    #: attached to nothing. A pair is neither attached nor doomed by breaking.
    paired_with: int | None = None
    #: **Face down** (707.2). A permanent whose *derived* characteristics are a
    #: 2/2 colourless creature with no name, no other types and no abilities,
    #: with the real card still underneath -- morph, megamorph and manifest.
    #:
    #: Distinct from a card hidden **in exile**, which is `revealed_to` and is
    #: what foretell needed: hiding a card nobody can interact with is not
    #: showing it, while a face-down permanent is a characteristics problem.
    #:
    #: Cleared by `reset_permanent_state`: a face-down permanent that leaves the
    #: battlefield is revealed, and one that comes back is a new object.
    face_down: bool = False
    #: Cloaked (701.61a) rather than merely manifested. The shell is the same
    #: 2/2 in both, and the only difference is the **ward {2}** the cloak rule
    #: puts on it -- which comes from the rule, not from the card underneath, so
    #: it cannot live on either and has to be a flag the engine reads.
    cloaked: bool = False
    #: Set on the resolving spell and read a moment later by
    #: `_place_after_resolution`, because `reset_permanent_state` clears
    #: `face_down` on the way onto the battlefield. Identity state, like
    #: `cast_kicked`, so it survives that reset.
    pending_face_down: bool = False
    #: Cipher (702.97a): the creature this exiled card is **encoded on**. Haunt's
    #: link pointed a third way -- the card in exile names a creature, and the
    #: card is what has to notice that creature connecting. The two are separate
    #: fields rather than one "linked_to", because a card could in principle be
    #: both and because the triggers that read them ask different questions.
    encoded_on: int | None = None
    #: Haunt (702.55a): the creature this exiled card is haunting. The link
    #: points at the **victim**, which is the opposite direction from
    #: `exiled_by`, and it has to: haunt's second trigger fires when the
    #: *haunted* creature dies, and the haunting card is the thing that has to
    #: still be somewhere to notice.
    haunting: int | None = None
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
    #: The same thing for a whole ability: "It gains 'when this creature dies,
    #: draw a card'", with no printed duration -- Clavileño. Stored as the same
    #: `TempEffect` pointer `until_eot` holds, so `granted_abilities` reads both
    #: alike, but kept out of the list `clear_until_eot` sweeps. A grant with no
    #: "until end of turn" on it lasts as long as the permanent does, and one
    #: that wore off at cleanup would be a strictly weaker card.
    granted_abilities_permanent: list[TempEffect] = field(default_factory=list)
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
    #: Exiled **face down** (Necropotence): in exile, and shown to nobody but
    #: the seats in `revealed_to`.
    #:
    #: A separate flag rather than "empty `revealed_to` means hidden", because
    #: an empty set is the default for every card in every zone and exile is
    #: otherwise a **public** zone -- `player_view` sends it in full to the whole
    #: table. Without a flag saying which of the two an empty set means, a
    #: face-down exile is indistinguishable from an ordinary one and the words
    #: are inert.
    #:
    #: Distinct from `face_down`, which is the 707 morph/manifest state of a
    #: permanent on the battlefield: a card in exile has no characteristics to
    #: hide behind, so what this buys is privacy and not identity.
    #:
    #: Cleared by `reset_permanent_state` with `revealed_to`, for its reason: the
    #: card that comes back to hand is a new object and carries none of this.
    hidden_in_exile: bool = False

    # -- identity flags, preserved across zone changes ------------------------
    is_token: bool = False
    is_commander: bool = False
    #: Set on an **emblem** (114): the index into ``emblems`` of the card named
    #: by ``def_id``, which is the card whose effect created it. An emblem is an
    #: object in its owner's command zone with abilities and no other
    #: characteristics; `GameState.card_of` returns that entry, so its triggers,
    #: its name and its text reach every reader through the one funnel. Nothing
    #: moves an emblem and nothing removes one, so this is never cleared.
    emblem: int | None = None

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
    #: **Gift** (702.164a): which opponent was promised a gift as this object was
    #: cast, or ``None`` if none was. Same contract as `cast_kicked`, and it does
    #: two jobs rather than one: a permanent's own enters trigger reads whether
    #: the promise was made (`{"gift_promised": …}`), and any effect that runs
    #: after the spell has left the stack -- a delayed trigger it scheduled, an
    #: ability of the permanent it became -- reads *whom* it was made to, which a
    #: bool could not say.
    cast_gift_to: int | None = None
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
    #: A `grant_playable` permission on this card is **flashback**: cast it and
    #: it is exiled rather than returning to the zone it came from.
    #:
    #: "Each instant and sorcery card in your graveyard gains flashback until
    #: end of turn" -- Will of the Jeskai. Needed here where Lier's static needs
    #: nothing, and the difference is which path the cast took: a
    #: `cast_from_graveyard` permission sets `cast_from_graveyard` and the
    #: existing `graveyard_cast_exiles` default already exiles it, while a
    #: `grant_playable` cast sets neither and would leave the card in the
    #: graveyard -- repeatable for the rest of the turn, and strictly better
    #: than the printed card.
    playable_exiles: bool = False
    #: Whether this object was cast for its **overload** cost. Same contract as
    #: `cast_kicked`: the flag has to outlive the spell, because an overloaded
    #: permanent's own enters trigger may read it.
    cast_overloaded: bool = False
    #: Which of `additional_cost_options` was paid, by index, or ``None`` for a
    #: card that offers no such choice.
    #:
    #: **Tiered** (Fire Magic, Ice Magic): "Choose one additional cost", where
    #: each tier buys a *different effect* rather than a bigger number. Bitter
    #: Triumph's two prices lead to one effect and never needed reading back;
    #: a tiered card cannot resolve at all without knowing which was paid.
    cast_cost_option: int | None = None
    #: **Which step this object was cast in** -- addendum's "if you cast this
    #: spell during your main phase". Recorded by `stack.push_spell`, because
    #: that is the moment 608.2 is talking about: the spell can be cast in a
    #: main phase and resolve after something on the stack above it has moved
    #: the game on, so a phase read at resolution is a different question and
    #: often a different answer.
    #:
    #: ``None`` on anything that was never cast -- a token, a permanent put onto
    #: the battlefield by an effect -- which is the honest reading of a clause
    #: about how the card was *cast*.
    cast_step: Step | None = None
    #: Whether the caster was the **active player** when it was cast, which is
    #: the other half of "your main phase". Stored as the relation rather than
    #: as a player id so that a later change of control cannot rewrite history:
    #: the sentence is about who cast it, and that is settled at cast time.
    cast_on_own_turn: bool = False
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
    #: **Phasing** (702.26c): this permanent is phased out and "treated as
    #: though it does not exist". It is out of `state.battlefield` while this is
    #: set, so nothing has to consult the flag -- it is here so the untap step
    #: can find it again, and so the log can say which it is.
    phased_out: bool = False
    #: Set on a permanent that phased out only because what it was attached to
    #: did (702.26e, "indirectly phases out"). It phases back in with its host
    #: rather than on its own schedule, which is the whole of the difference.
    phased_out_indirectly: bool = False
    #: Which permanent phased this one out "until it leaves the battlefield" --
    #: Oubliette. The phasing twin of `exiled_by`, and it does the same two
    #: jobs: it suspends the ordinary return, since the untap walk skips a
    #: permanent that is waiting on a source rather than on a clock, and it is
    #: what a `{"phased_out_with": "self"}` selector reads back, since a
    #: phased-out permanent is out of `state.battlefield` and no ordinary
    #: selector can otherwise name it.
    #:
    #: ``None`` is the plain printed one-shot, which really does come back at
    #: its controller's next untap step.
    phased_out_by: int | None = None
    #: **Mutate** (702.140a): the synthesised card this merged permanent *is* --
    #: the card on top, carrying the abilities of everything under it.
    #:
    #: A whole ``CardDef`` rather than a pair of ids, because `card_of` is the
    #: single place derived card identity is decided and every reader already
    #: goes through it. Building the union once, here, means legality, triggers,
    #: `chars` and the serializer all see one ability list with one set of
    #: indices, and none of them needed changing.
    merged_card: Any = None
    #: The oids of the cards **underneath** this permanent. They stay in
    #: ``state.objects`` and in no zone list -- the same place a card on the
    #: stack lives -- so nothing that walks the battlefield sees them, and
    #: `zones.move_object` sends the whole pile wherever the permanent goes.
    merged_under: tuple[int, ...] = ()
    #: Set on a card that is *part of* another permanent: the oid of the pile it
    #: was merged into. The back-link, so a card in limbo can say why.
    merged_into: int | None = None
    #: Whether this object was cast for its **bestow** cost (702.103a). Beside
    #: the other `cast_*` flags and, like them, deliberately *not* cleared by
    #: `reset_permanent_state`: it is what makes the permanent an Aura once it
    #: has landed, so a flag wiped on the way onto the battlefield would leave
    #: an ordinary creature attached to something.
    cast_bestowed: bool = False
    #: Whether this object is currently showing its **second castable face** --
    #: the Adventure half, the Aftermath half, one half of a split card.
    #: ``GameState.card_of`` reads it, exactly as it reads ``transformed``, so
    #: the cost, the type line, the targets, the effects and the name in the log
    #: are all that face's with nothing else changed.
    #:
    #: True only while the card is a *spell*: it is set as the spell is put on
    #: the stack and cleared as it leaves, because a card that showed one face
    #: on the stack and another wherever it landed would be two cards to
    #: everyone watching.
    showing_second_face: bool = False
    #: **Adventure** (715.3d): this card is in exile having gone on an
    #: adventure, and its owner may cast the *front* face from there.
    #:
    #: A flag rather than a reuse of ``exiled_by``: nothing exiled it, the card
    #: put itself there on resolution, and there is no permanent for the link to
    #: point at.
    on_adventure: bool = False
    #: "You may play the exiled card this turn." Florian, and the impulse-draw
    #: family generally. The player who may play it, and the turn on which they
    #: may -- both, because the permission expires and a card left in exile with
    #: a bare boolean would be castable for the rest of the game.
    #:
    #: Distinct from `on_adventure`, which is permanent and free of a turn, and
    #: from `play_exiled`, which casts *without paying* and does it immediately.
    #: This one is a permission with a duration, and the cost is still owed.
    playable_by: int | None = None
    playable_turn: int = -1
    #: How long the permission lasts. ``"this_turn"`` is the impulse-draw
    #: default and is read off `playable_turn`; the other two outlive the turn
    #: they were granted in and are ended by a hook in the turn structure
    #: instead, which sets `playable_by` back to None.
    #:
    #: Keyed to the *player* and cleared when their step arrives, never computed
    #: as a future turn number -- the same choice detain, goad and "until your
    #: next turn" all made, and for their reason: eliminating a player moves
    #: everybody else's next turn, and extra turns move it again.
    #:
    #: - ``"your_next_end_step"`` -- "You may play it until your next end step."
    #:   (Haste Magic.) Cleared as that end step begins, so a card exiled during
    #:   your own end step survives to the following turn's, which is what "your
    #:   **next**" says.
    #: - ``"end_of_your_next_turn"`` -- "Until the end of your next turn, you may
    #:   play that card." (Light Up the Stage.) Cleared in the cleanup of the
    #:   first of your turns to *start* after the grant, so a card exiled on your
    #:   own turn lives through the whole of the next one.
    playable_duration: str = "this_turn"
    #: "…without paying its mana cost." Plot and foretell are the two shapes
    #: that pay something other than the printed price out of exile, and
    #: foretell has a printed cost of its own -- this is the half that has none.
    playable_free: bool = False
    #: "…**as a sorcery**." A restriction on the permission rather than on the
    #: card, which is what makes it different from `_timing_ok`: a plotted
    #: *instant* may only be cast at sorcery speed, and its own type line still
    #: says instant.
    playable_sorcery_only: bool = False
    #: Which permanent's permission made this card playable, when that
    #: permission caps how many of its cards may be cast -- Locke, Treasure
    #: Hunter: "you may cast **a spell** from among those cards", singular, out
    #: of however many were milled. The cap is counted per granting permanent in
    #: the turn ledger, so the group has to say which one granted it.
    playable_group: int | None = None
    #: "…and mana of any type can be spent to cast that spell" -- Summon: Esper
    #: Valigarmanda. A relaxation of what may be *spent*, riding along with the
    #: permission that made the card castable and expiring with it, so it is
    #: kept on the card rather than on the player: the same turn's other spells
    #: are paid for normally.
    playable_any_type: bool = False
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
    #: Goad (701.38a): "until **your** next turn, that creature attacks each
    #: combat if able and attacks a player other than you if able". The pids of
    #: the players who goaded it, each cleared by that player's own untap step.
    #:
    #: Detain's field with two differences, and both are forced by the rule.
    #:
    #: A **set**, not one pid: two opponents may goad the same creature, each
    #: clock runs from their own next turn, and each of them is a player the
    #: creature must attack around. Detain can be a single pid because a second
    #: detain says nothing the first does not; a second goad does.
    #:
    #: And it is a *requirement plus a target restriction* where detain is a
    #: prohibition, which is why it could not be spelled as `must_attack`: that
    #: field is one-shot and `combat.discharge_attack_requirements` spends it
    #: when attackers lock in, so it compels one combat where goad compels every
    #: combat until the goader untaps. This is read live in
    #: `combat.attack_required` and never spent.
    goaded_by: set[int] = field(default_factory=set)

    #: "…exile all other tokens **created with this creature**" -- Faerie
    #: Artisans. The tokens an effect whose source is *this object* created,
    #: written by `primitives.create_token` for `create_token` and
    #: `copy_permanent` alike and read back by the `created_with` selector key.
    #:
    #: On the creator rather than on the token, because the link is to this
    #: *object* and not to the card (607.2a's linked-ability shape): a creator
    #: that leaves the battlefield and comes back is a new object (400.7), and
    #: the tokens its previous incarnation made are no longer "created with
    #: this creature". An oid survives every zone change, so a pointer on the
    #: token could not tell the two incarnations apart without a generation
    #: stamp the engine does not keep -- here `reset_permanent_state` ends the
    #: link at exactly the moment the object ends.
    #:
    #: Never pruned as tokens leave: a token that left the battlefield has
    #: ceased to exist (111.7), is in no zone a selector searches, and its oid
    #: is never reused.
    created_tokens: set[int] = field(default_factory=set)

    #: "As this artifact enters, choose a creature type." The type this
    #: permanent's controller named, read back by its own abilities through
    #: ``{"chosen_type_of": "self"}``.
    #:
    #: Reset with the rest of the battlefield state: a permanent that leaves and
    #: comes back is a new object as far as the rules are concerned, and chooses
    #: again.
    chosen_type: str | None = None

    #: "As this artifact enters, choose a color." Heraldic Banner. The colour
    #: letter (``"W"``…``"G"``) this permanent's controller named, read back by
    #: its own abilities through ``{"chosen_color_of": "self"}``.
    #:
    #: A separate slot rather than a second use of ``chosen_type``, because a
    #: card may print both questions and because a colour and a creature type
    #: are read by different code -- ``colors`` in a static filter and
    #: ``mana_options_of`` for the mana ability, neither of which would know
    #: what to do with a subtype name sitting in the same field.
    #:
    #: Reset with the rest of the battlefield state, for the same reason
    #: ``chosen_type`` is: a permanent that leaves and comes back is a new
    #: object as far as the rules are concerned, and chooses again.
    chosen_color: str | None = None

    #: "…a token that's a copy of it, **except** it's a white Zombie Angel with
    #: no mana cost." Embalm and eternalize.
    #:
    #: A copy is a token whose ``def_id`` is the original's, so the "except"
    #: clause has nowhere to live on the card -- it is a property of this one
    #: object. The copiable values 707.9b lets an exception rewrite: replacement
    #: colours, card types and base power/toughness; added card types,
    #: subtypes and supertypes; and whether the mana cost is gone. Anything
    #: richer belongs in a real copiable-values layer, which this engine does
    #: not have.
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

    #: Text-changing effects on this object (613.1c, layer 3): ``(old, new)``
    #: creature-type pairs, in timestamp order. "Change the text of that
    #: creature by replacing all instances of one creature type with Vampire"
    #: -- New Blood.
    #:
    #: **Not** `added_subtypes`, which is the layer *above* and the opposite
    #: reading: that one is "it becomes a Vampire **in addition to** its other
    #: types" and leaves the printed word in place, so a Goblin under it answers
    #: to Goblin lords and Goblin removal still. This replaces the word, and
    #: replaces it everywhere -- the subtype line *and* every instance inside
    #: the object's own rules text, which is what turns a stolen Goblin lord
    #: into a Vampire lord. See `engine/text_change.py`.
    #:
    #: A tuple applied in order rather than a mapping, because 612.4 applies
    #: text changes in timestamp order and the second one reads the first one's
    #: output: Goblin→Vampire then Vampire→Zombie is a Zombie.
    #:
    #: A pipeline *input* like `added_subtypes` above -- nothing in the
    #: characteristics pipeline can write it -- so reading it in `_compute`,
    #: `_matches` and `abilities_of` alike creates no dependency between layers.
    #:
    #: Reset with the rest of the battlefield state, for `added_subtypes`'
    #: reason: a permanent that leaves and comes back is a new object and
    #: arrives with its printed text.
    text_changes: tuple[tuple[str, str], ...] = ()

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
    #: Which zone this card was in when it was exiled -- "return it to the zone
    #: it came from" (Cloak and Dagger, Entwined, whose one exile can take a
    #: card out of a hand *or* a permanent off the battlefield). Recorded as the
    #: zone's name rather than the enum so it serializes with the rest of the
    #: object.
    #:
    #: Written by `zones.exile`, and after the move: `move_object` runs
    #: `reset_permanent_state` on the way, which clears this for the reason it
    #: clears `exiled_by` -- a card that has since left exile came from nowhere.
    exiled_from: str | None = None
    #: **Prepared** (Emeritus of Woe // Demonic Tutor). "This creature enters
    #: prepared. (While it's prepared, you may cast a copy of its spell. Doing
    #: so unprepares it.)"
    #:
    #: A state on the permanent and not a counter, because the reminder text is
    #: the whole of the mechanic and says nothing about a number: a permanent is
    #: prepared or it is not, and preparing an already-prepared one changes
    #: nothing. It is not `flags` either -- a flag is inert bookkeeping, and
    #: this is read by the casting-permission path.
    #:
    #: Cleared by `reset_permanent_state`, so a permanent that left the
    #: battlefield and came back is not still prepared: 400.7 makes it a new
    #: object, and the printed line is what puts the state on in the first
    #: place.
    prepared: bool = False

    def playable_live(self, turn: int) -> bool:
        """Is the "you may play it" permission still standing?

        One question asked in seven places -- legality, both cast paths, the
        any-type relaxation, the group ledger and the flashback rider -- which
        used to be spelled `obj.playable_turn == state.turn` at each of them.
        That spelling *is* the "this turn" duration, so generalising it meant
        replacing all seven rather than adding an eighth.

        The longer durations answer True until their hook in the turn structure
        clears `playable_by`; there is no arithmetic on future turn numbers
        here, deliberately.
        """
        if self.playable_by is None:
            return False
        if self.playable_duration == "this_turn":
            return self.playable_turn == turn
        if self.playable_duration == "later_turns":
            # Plot's "on a later turn", and the only duration with a *start*
            # rather than an end. Nothing expires it, so there is no hook: the
            # card leaves exile by being cast.
            return turn > self.playable_turn
        return True

    def reset_permanent_state(self) -> None:
        """Wipe everything that only means something on the battlefield."""
        self.must_attack = None
        self.must_block = None
        self.detained_by = None
        # A permanent that left and came back is a new object (400.7), so it is
        # no longer the creature anybody goaded -- blink your own goaded
        # creature and it owes nothing, which is the printed answer.
        self.goaded_by = set()
        # The same new object: the tokens the old one made were not made by
        # this one, so "tokens created with this creature" is none of them.
        self.created_tokens = set()
        self.granted_keywords = set()
        self.granted_abilities_permanent = []
        self.tapped = False
        self.damage = 0
        self.deathtouched = False
        self.regeneration_shields = 0
        self.counters = {}
        self.attached_to = None
        self.last_attached_to = None
        # Cleared with `attached_to` and for its reason: a permanent that left
        # the battlefield and came back is a new object (400.7), and an Aura
        # that arrives without being cast enchants nobody until something
        # attaches it. This is why `stack._attach_aura` runs *after* the move.
        self.attached_to_player = None
        self.paired_with = None
        self.face_down = False
        self.cloaked = False
        self.until_eot = []
        self.dies_to = None
        self.leaves_to = None
        self.copying = None
        self.copying_name = None
        self.copying_until_eot = False
        self.monstrous = False
        # A permanent that left and came back is a new object as far as the
        # rules are concerned, so it is no longer renowned either.
        self.flags = set()
        self.frozen_by = None
        self.skip_next_untap = False
        self.exiled_by = None
        self.phased_out_by = None
        self.chosen_type = None
        self.chosen_color = None
        self.added_subtypes = ()
        self.text_changes = ()
        self.transformed = False
        # A permanent that left the battlefield is no longer a pile: the cards
        # under it were sent along by `move_object` before this ran.
        self.merged_card = None
        self.merged_under = ()
        self.merged_into = None
        # The creature came back off its adventure and is on the battlefield;
        # there is nothing left in exile for anyone to cast.
        self.on_adventure = False
        # A card that changed zones is a new object (400.7), so a rebound
        # somebody granted the *spell* does not follow the card into its next
        # life. Read before the move that runs this, so clearing it here costs
        # the grant nothing and stops it outliving the spell it was given to.
        self.granted_rebound = False
        self.granted_plot = False
        self.playable_by = None
        self.playable_turn = -1
        self.playable_duration = "this_turn"
        self.playable_free = False
        self.playable_sorcery_only = False
        self.playable_group = None
        self.playable_any_type = False
        self.exiled_from = None
        self.prepared = False
        self.revealed_to = set()
        # `enters_cost_paid` is deliberately *not* reset either, and for the
        # same reason as `hasted_by_suspend` below: it is the answer to a
        # question asked a moment before the move, and this runs on the way in
        # -- clearing it here would throw away the payment and tap a land its
        # controller had just paid 3 life to untap. `_enter_battlefield` clears
        # it once the replacements have read it.
        self.hidden_in_exile = False
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
            "text_changes": [list(pair) for pair in self.text_changes],
            "transformed": self.transformed,
            "attached_to": self.attached_to,
            "attached_to_player": self.attached_to_player,
            "is_token": self.is_token,
            "is_commander": self.is_commander,
            "entered_turn": self.entered_turn,
            "until_eot": [t.to_dict() for t in self.until_eot],
            "monstrous": self.monstrous,
            "class_level": self.class_level,
            "flags": sorted(self.flags),
            "detained_by": self.detained_by,
            # Sorted rather than the set itself, so the snapshot is JSON and is
            # comparable between two runs of the same game.
            "goaded_by": sorted(self.goaded_by),
            "granted_keywords": sorted(self.granted_keywords),
            "frozen_by": self.frozen_by,
            "skip_next_untap": self.skip_next_untap,
            "suspended_by": self.suspended_by,
            "hasted_by_suspend": self.hasted_by_suspend,
            # Only on an emblem, so every other object's snapshot is unchanged.
            **({"emblem": self.emblem} if self.emblem is not None else {}),
        }


#: The durations a "you may play it" permission may carry. ``this_turn`` is the
#: impulse-draw default and was the only one the engine had; the other two
#: outlive the turn they were granted in and are ended by hooks in
#: `turn.begin_step` rather than by arithmetic on a turn number.
PLAYABLE_DURATIONS = (
    "this_turn",
    "your_next_end_step",
    "end_of_your_next_turn",
    #: Plot (702.171a): "you may cast it as a sorcery on a **later turn**
    #: without paying its mana cost." No end at all -- a plotted card waits in
    #: exile until it is cast -- and a start that is not now: the turn it was
    #: plotted on is the one turn it may *not* be cast.
    "later_turns",
)


def playable_duration_of(spec: Mapping[str, Any]) -> str | None:
    """An effect spec's permission duration, or None when it grants none.

    Two spellings of one key. ``playable_this_turn: true`` is what every card
    written before durations existed says, and it means ``"this_turn"``; the
    general form is ``playable: "<duration>"``. The loader refuses both on one
    effect, so this never has to choose between them.
    """
    if spec.get("playable_this_turn"):
        return "this_turn"
    duration = spec.get("playable")
    if duration in PLAYABLE_DURATIONS:
        return str(duration)
    return None
