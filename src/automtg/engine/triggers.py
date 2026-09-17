"""The event bus and triggered-ability matching.

Every mutating primitive calls :func:`fire`, which records a :class:`GameEvent`
and collects any triggered abilities that match it.  Collected triggers wait in
``state.pending_triggers`` and are put on the stack the next time a player would
receive priority, in APNAP order and auto-ordered within a player (a documented
simplification -- real Magic lets the controller choose the order).
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from typing import TYPE_CHECKING, Any

from .carddef import Ability, TriggerSpec
from .enums import Zone
from .errors import RulesLoopError
from .events import EventType, GameEvent
from .objects import GameObject
from .state import MAX_TRIGGERS_PER_STEP
from .structs import DelayedTrigger, TriggerInstance

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


#: DSL trigger name -> the engine event type it listens for.
TRIGGER_EVENTS: dict[str, str] = {
    "self_enters": EventType.ENTERS_BATTLEFIELD,
    "permanent_enters": EventType.ENTERS_BATTLEFIELD,
    "dies": EventType.DIES,
    "leaves_battlefield": EventType.LEAVES_BATTLEFIELD,
    "leaves_graveyard": EventType.LEAVES_GRAVEYARD,
    "land_played": EventType.LAND_PLAYED,
    "spell_cast": EventType.SPELL_CAST,
    #: "Magecraft -- Whenever you cast **or copy** an instant or sorcery spell…"
    #: Archmage Emeritus, Storm-Kiln Artist, Veyran.
    #:
    #: A separate event rather than a widening of `spell_cast`, because a copy
    #: is emphatically **not** cast (707.10a): storm, replicate, conspire,
    #: casualty, gravestorm and epic all copy the spell that made them, and a
    #: `spell_cast` that also fired on copies would make every one of them
    #: retrigger itself -- a storm count of nine firing prowess nine more times.
    #: So magecraft is two abilities claiming one printed line, the same shape
    #: Winged Boots uses for "has flying and ward {4}".
    #:
    #: `EventType.SPELL_COPIED` has been emitted by `put_copy_on_stack` since
    #: copying existed and simply had no listener; what was missing was this
    #: row, the `OBJECT_SUBJECT_TRIGGERS` membership that gives a filter
    #: something to read, and the `_actor` clause that makes `controller: "you"`
    #: mean the copy's controller.
    "spell_copied": EventType.SPELL_COPIED,
    "attacks": EventType.ATTACKS,
    "blocks": EventType.BLOCKS,
    "deals_combat_damage_to_player": EventType.COMBAT_DAMAGE_TO_PLAYER,
    "upkeep": EventType.UPKEEP,
    "draw_step": EventType.DRAW_STEP,
    "begin_combat": EventType.BEGIN_COMBAT,
    #: "At the beginning of your first main phase…" Black Market Connections.
    #: Not `upkeep`, which is a step earlier and before the draw -- a card hung
    #: there would hand its controller the turn's Treasure before they had seen
    #: the card they drew, and a "you lose 1 life" mode would be paid a step
    #: sooner than the printed one.
    "precombat_main": EventType.PRECOMBAT_MAIN,
    #: "At the beginning of each of your postcombat main phases…" Florian.
    #: `begin_combat` is the nearest existing phase event and is on the wrong
    #: side of combat -- a card hung on it would read a life-loss tally from
    #: before the damage it is counting.
    "postcombat_main": EventType.POSTCOMBAT_MAIN,
    "end_step": EventType.END_STEP,
    "you_gain_life": EventType.LIFE_GAINED,
    #: "Whenever **you** attack" -- Clavileño. Once per combat in which its
    #: controller declared one or more attackers, whatever the number. Not
    #: `attacks`, which is per creature and would fire three times on a
    #: three-creature swing. The event already existed and nothing listened.
    "you_attack": EventType.ATTACKERS_DECLARED,
    #: "Whenever one or more creatures attack **one of your opponents** or a
    #: planeswalker they control, those creatures gain menace" -- Frontier
    #: Warmonger. `you_attack` with a defending player attached, and one trigger
    #: per (declaration, defending player) pair: however many creatures were
    #: declared against that seat, the ability fires once and `{"binding":
    #: "attackers"}` names exactly them.
    #:
    #: Both existing attack triggers fail on a different half. `you_attack` is
    #: the right *shape* and carries no `defender` at all, so a `defending`
    #: clause on it never matches (`_defender_matches` returns False on an
    #: absent defender) and the ability is inert -- while dropping the clause is
    #: not a weaker card but a different one, since plain `you_attack` with
    #: `controller: "any"` also fires when an opponent swings at *you* and hands
    #: menace to the creatures you are about to block. `attacks` carries the
    #: defender and is per creature, which is the substitution the note on
    #: `you_attack` above already refused in writing: three attackers, three
    #: copies, and each copy can speak about one of them.
    #:
    #: The attacking side is `controller: "any"` on this card and that is not
    #: laziness: the creatures attacking an opponent need not be the Warmonger
    #: controller's, and in a pod they routinely are not.
    "creatures_attack_player": EventType.CREATURES_ATTACKED_PLAYER,
    #: "Whenever one or more creatures you control deal combat damage to one or
    #: more players…" -- Forth Eorlingas!, as a delayed ability installed for the
    #: rest of the turn. `creatures_attack_player` one phase later: coarser than
    #: a creature, finer than the game.
    #:
    #: `deals_combat_damage_to_player` is the near miss and is per *connection*.
    #: A card built on it pays once for every creature that got through, so X
    #: Knights connecting would hand out the monarchy X times over; and the
    #: printed line says "one or more creatures … one or more players", which is
    #: one ability whatever the numbers turn out to be. `max_per_turn: 1` on the
    #: per-creature form is the tempting repair and is wrong one step out:
    #: `extra_combat` gives a turn two combats, and the printed ability triggers
    #: in the second one as well.
    #:
    #: The subject is a **player** -- the one whose creatures connected -- so it
    #: is absent from `OBJECT_SUBJECT_TRIGGERS` and `event_player` is the
    #: damaging seat. That is what makes `controller: "you"` read "creatures
    #: **you control** deal combat damage".
    "creatures_deal_combat_damage": EventType.CREATURES_DEALT_COMBAT_DAMAGE,
    #: "Whenever an opponent loses life, you gain that much life." The amount is
    #: `{"binding": "amount"}`. Fired by `lose_life` *and* by `damage_player`,
    #: because the reminder text on every card of this shape says so out loud:
    #: "(Damage causes loss of life.)" Infect damage is the exception and fires
    #: nothing, since it costs no life.
    "life_lost": EventType.LIFE_LOST,
    "becomes_monstrous": EventType.BECAME_MONSTROUS,
    "counter_placed": EventType.COUNTER_PLACED,
    "creature_dies": EventType.DIES,
    #: "Whenever you **sacrifice** a token…" -- Mirkwood Bats. Not `dies`: a
    #: sacrifice is one specific way of leaving, and the printed line is about
    #: the choice rather than the death. Fired beside DIES rather than instead
    #: of it, so everything already listening for a death still hears one.
    "sacrificed": EventType.SACRIFICED,
    #: "Whenever you **create** a token…" -- the other half of the same card.
    #: `permanent_enters` with `{"is_token": true}` is the near miss and is close
    #: enough to be tempting (111.1 makes creating and entering one act), but it
    #: also fires for a token that changed zones and back, and it reads the
    #: entering permanent's controller rather than the creator's.
    "token_created": EventType.TOKEN_CREATED,
    "draw": EventType.DRAW,
    "discard": EventType.DISCARD,
    "cycle": EventType.CYCLED,
    #: Enrage (702.131): "Whenever this creature is dealt damage, …".  No new
    #: event -- `DAMAGE_DEALT` has always been fired through the trigger bus and
    #: nothing subscribed to it.  Sugar in the same sense `creature_dies` is:
    #: the event covers damage to players as well, and this half of it is the
    #: half with an object to hang a trigger on.
    "dealt_damage": EventType.DAMAGE_DEALT,
    #: "Whenever enchanted creature deals damage to an opponent, you may draw a
    #: card" -- Curiosity, Ophidian Eye, and Tandem Lookout's granted copy of the
    #: same line. The **other half** of DAMAGE_DEALT, and the half the note on
    #: `dealt_damage` above named without claiming: that one is scoped to damage
    #: dealt *to a permanent* and takes the victim as its subject, and this one
    #: is scoped to damage dealt *to a player* and takes the **dealer**.
    #:
    #: No new event type, for the reason `dealt_damage` needed none: every
    #: player-damage site in the engine goes through `primitives.damage_player`,
    #: which has fired DAMAGE_DEALT with `to="player"` through the trigger bus
    #: since damage existed. What it lacked was a name, a subject and the two
    #: payload keys a `controller`/`defending` clause compares against.
    #:
    #: `deals_combat_damage_to_player` is the near miss and is combat-only by
    #: construction -- COMBAT_DAMAGE_TO_PLAYER is fired inside `if is_combat`, so
    #: a pinger, a Fireball, a fight or a triggered burn spell under Curiosity
    #: draws nothing, and a pinger is precisely what the card is played with.
    #: The substitution is a different card rather than a weaker one. Combat
    #: damage still fires *this* event too, so nothing is lost by using it: a
    #: creature connecting fires both, one per printed reading.
    #:
    #: `life_lost` reaches the loss and not the dealer: its subject is a player,
    #: so nothing ties the loss back to the enchanted creature, and it fires for
    #: discards and taxes as readily as for damage while an infect hit deals
    #: damage and fires it not at all -- infect is why this is hung on the damage
    #: and not on the life total.
    "deals_damage_to_player": EventType.DAMAGE_DEALT,
    #: Heroic (702.109) and ward (702.21): "whenever this becomes the target of
    #: a spell…".  Fired as the spell goes on the stack (603.2d), which is the
    #: timing that makes ward mean anything.
    "becomes_target": EventType.BECAME_TARGET,
    #: Flanking (702.25), rampage (702.23), bushido (702.45) and frenzy
    #: (702.35), which between them are every combat keyword the engine had no
    #: event for. Both fire when blockers are declared, because that is the
    #: instant either becomes knowable.
    "becomes_blocked": EventType.BECAME_BLOCKED,
    "attacks_unblocked": EventType.ATTACKED_UNBLOCKED,
    #: Inspired (702.117): "Whenever this creature becomes untapped, …". The
    #: event existed; what did not was the untap *step* saying which permanents
    #: it untapped, which is where inspired fires nearly every time.
    "becomes_untapped": EventType.UNTAPPED,
    #: "…until an opponent becomes the monarch" (Palace Jailer). The one monarch
    #: card that must be *woken up* by the designation moving rather than merely
    #: asking about it with `is_monarch`.
    #:
    #: `deals_combat_damage_to_player` is the near miss and is the wrong
    #: abstraction: it fires on the damage rather than on the designation, so
    #: every watcher would have to re-derive "and that player was the monarch,
    #: so the crown just moved" -- and it would still miss the other route in,
    #: where an opponent's own card makes them the monarch with no damage
    #: anywhere. Both routes go through `primitives.become_monarch`, so this one
    #: name covers both.
    #:
    #: The subject is a **player**, so it is absent from
    #: `OBJECT_SUBJECT_TRIGGERS` and `event_player` is the new monarch. That is
    #: what makes `controller: "opponent"` read "an opponent becomes the
    #: monarch".
    "becomes_monarch": EventType.BECAME_MONARCH,
    #: "Whenever an opponent activates an ability of an artifact, creature, or
    #: land on the battlefield, **if it isn't a mana ability**…" -- Harsh Mentor.
    #: `EventType.ABILITY_ACTIVATED` had existed since activations did and was
    #: emitted by both activation paths; what it never had was a listener or a
    #: DSL name, so it was a log line and nothing more.
    #:
    #: `spell_cast` is the near miss and is a disjoint set of actions: it fires
    #: on a card leaving the hand for the stack, so a card built on it would
    #: punish every instant and never punish an equip or a cracked fetchland.
    #:
    #: The subject is the **permanent whose ability it was** (see
    #: `OBJECT_SUBJECT_TRIGGERS`) while the actor is the **player who activated
    #: it** (see `_actor`), and the two really do come apart -- an opponent
    #: equipping a creature you control activates their ability on your
    #: permanent, and the printed line says that triggers.
    "ability_activated": EventType.ABILITY_ACTIVATED,
    #: "Whenever damage that would be dealt to you is prevented, put that many
    #: +1/+1 counters on this creature." -- Selfless Squire. The amount is
    #: `{"binding": "amount"}`, carried by `EVENT_BINDING_KEYS` like every other
    #: "that much".
    #:
    #: `EventType.DAMAGE_PREVENTED` had existed since absorb and was emitted at
    #: two sites, both through `state.emit` -- a log line with no name in this
    #: dict and no listener if it had one. Adding the mapping alone would have
    #: produced a trigger that silently never fires, so all three sites now
    #: `fire` (see the "`fire`, not `emit`" comments in `primitives.py`).
    #:
    #: `dealt_damage` is the nearest existing trigger and is exactly inverted:
    #: prevented damage is damage that was *never* dealt, so `DAMAGE_DEALT` does
    #: not fire for it at all -- a Squire built on it gets counters only on the
    #: turns its own shield is down. `life_lost` fails the same way and is doubly
    #: wrong, since prevented damage costs no life, and the `damage_taken_this_turn`
    #: value key reads zero underneath a working shield by construction.
    #:
    #: The subject is a **player**, so it is absent from `OBJECT_SUBJECT_TRIGGERS`
    #: and `event_player` is the player whose damage was prevented. That is what
    #: makes `controller: "you"` read "damage that would be dealt to *you*", and
    #: it is why the scoping is not `source: "self"` -- the event's `source` is
    #: the creature that was swinging.
    #:
    #: Scoped to the **player** half of the event by `_matches` below, for the
    #: reason `dealt_damage` is scoped to the permanent half: one event covers two
    #: shapes, and without the check a blocked absorb creature would pay the
    #: Squire too.
    "damage_prevented": EventType.DAMAGE_PREVENTED,
    #: A Saga's chapter ability (714.1b, 714.2c). Never written in a card file --
    #: the loader supplies it for `kind: "chapter"`, the way it supplies
    #: `source: "self"` for `self_enters` -- because the printed line is "II --"
    #: and there is no word in it for a trigger name to be.
    #:
    #: `counter_placed` with `{"counter": "lore"}` is the near miss, and it is
    #: what the gap record for Oath of Eorl proposed and then refused. It fires
    #: on the placement rather than on the count *reaching* the number, so a
    #: proliferated Saga advances by the wrong pattern; and it fires not at all
    #: on the counter a Saga **enters** with, which is chapter I on every Saga in
    #: print.
    "chapter": EventType.CHAPTER_REACHED,
}

#: Triggers whose subject is an object rather than a player.
OBJECT_SUBJECT_TRIGGERS = frozenset(
    {
        "self_enters",
        "permanent_enters",
        "dies",
        "creature_dies",
        "sacrificed",
        "token_created",
        "leaves_battlefield",
        # The card that left the graveyard, so a filter may ask what it was --
        # Cyan, Vengeful Samurai's "whenever one or more **creature cards**
        # leave your graveyard". The card has already reached its new zone when
        # the event fires and `matches_card_filter` reads the printed face, so
        # the subject is still there to be asked about, exactly as it is for
        # `discard`. Without this the filter had no subject and matched nothing,
        # so the trigger silently never fired.
        "leaves_graveyard",
        "spell_cast",
        # The *original* spell, which is what `put_copy_on_stack` puts on the
        # event as `source`. A filter on a magecraft trigger therefore asks
        # "was the thing copied an instant or sorcery", which is the printed
        # question -- and it is answerable, because the original is still on
        # the stack when its copy is made.
        "spell_copied",
        "attacks",
        "blocks",
        "deals_combat_damage_to_player",
        "counter_placed",
        "land_played",
        "becomes_monstrous",
        # The cycled card itself, so `source: "self"` scopes the trigger to the
        # card that was cycled rather than to every cycling anywhere.
        "cycle",
        # The discarded card, so a filter may ask what it was -- "whenever an
        # opponent discards a *creature* card". It is in the graveyard by the
        # time the event fires and `matches_card_filter` reads the printed face,
        # so the subject is still there to be asked about.
        "discard",
        # The permanent that was dealt the damage, not the source dealing it:
        # enrage is a fact about the creature being hurt, and `source: "self"`
        # has to scope it to that creature rather than to everything it hits.
        "dealt_damage",
        # The permanent that **dealt** the damage -- the exact opposite of the
        # line above, off the same event. Damage to a player has no victim
        # object for the subject to be, and the whole point of the trigger is to
        # say which permanent connected: `filter: {"attached": true}` is how
        # Curiosity means "enchanted creature", and `source: "self"` is how
        # Tandem Lookout's granted copy means "this creature".
        #
        # Reached through the `event.source` fallthrough in `_subject_oid`,
        # because the player half of DAMAGE_DEALT carries no `oid` -- there is
        # no permanent on the receiving end to carry one.
        "deals_damage_to_player",
        # The permanent that was targeted, for the same reason: `source: "self"`
        # on heroic means "a spell targeting *me*", and the event's `source` is
        # the spell doing the targeting.
        "becomes_target",
        # The attacker. Both of these are told from the attacking creature's
        # side -- `blocks` already covers the blocker's -- so `source: "self"`
        # scopes them to the creature that was, or was not, blocked.
        "becomes_blocked",
        "attacks_unblocked",
        # The permanent that untapped.
        "becomes_untapped",
        # The permanent whose ability was activated, so a filter can ask what it
        # was -- "an ability of an artifact, creature, or land **on the
        # battlefield**". The emission passes `source=oid` and no `oid` key, so
        # `_subject_oid` reaches it through the `event.source` fallthrough.
        "ability_activated",
        # The Saga itself. Listed so `source: "self"` -- which the loader always
        # supplies for a chapter -- scopes the ability to *this* Saga rather than
        # to every Saga on the table, and so `_actor` reads the Saga's controller
        # and not the event's player. The two agree today, because the only thing
        # that fires CHAPTER_REACHED reads the controller off the same object; a
        # Saga that changed hands mid-chapter is where they would come apart, and
        # the object is the right answer there.
        "chapter",
    }
)

#: DSL trigger name -> which half of a two-shaped damage event it is about.
#:
#: `DAMAGE_DEALT` and `DAMAGE_PREVENTED` each cover two different sentences and
#: say which they are with a ``to`` key: damage to a **permanent** has an object
#: on the receiving end, and damage to a **player** does not. Three trigger names
#: take one half each, and every one of them is silently wrong on the other:
#:
#: * ``dealt_damage`` is enrage (702.131), "whenever **this creature** is dealt
#:   damage". Its subject is the victim, so on the player half there is no victim
#:   to be about and `player` is the seat that was hit rather than a controller
#:   -- letting it through fires every enrage on the board off a Lightning Bolt
#:   to the face.
#: * ``deals_damage_to_player`` is Curiosity, and takes the same event from the
#:   other end: its subject is the **dealer**, which on the permanent half would
#:   make a Shock aimed at a Bear draw a card.
#: * ``damage_prevented`` is Selfless Squire, "damage that would be dealt to
#:   **you**". Absorb and protection fire the same event about a *permanent*, so
#:   without the scoping a creature with absorb blocking a Grizzly Bears would
#:   pay the Squire, and so would protection turning aside a Shock aimed at a
#:   teammate's permanent.
#:
#: Compared with ``==`` against the required value rather than ``!=`` against the
#: other one, for the reason the ``mana_ability`` check in `_matches` spells out:
#: an emission that forgot to say would otherwise pass, and wider is the
#: dangerous direction.
EVENT_HALVES: dict[str, str] = {
    "dealt_damage": "permanent",
    "deals_damage_to_player": "player",
    "damage_prevented": "player",
}


def _half_matches(dsl_event: str, event: GameEvent) -> bool:
    """Whether this event is the half of itself that ``dsl_event`` is about.

    Shared by `_matches` and `_delayed_matches` so a delayed subscription cannot
    be wider than the hosted trigger of the same name -- which it was, because
    the delayed path compares only the event type and would have woken a
    ``deals_damage_to_player`` watcher on a Shock aimed at a creature.
    """
    half = EVENT_HALVES.get(dsl_event)
    return half is None or event.data.get("to") == half


#: Triggers that keep working while their source is in the graveyard, because the
#: source has just left the battlefield.
#:
#: ``cycle`` is deliberately absent. This set drives one special path, keyed on
#: DIES/LEAVES_BATTLEFIELD, for an object no zone list holds any more. A cycled
#: card *is* in a zone list -- the graveyard, which `_candidate_abilities`
#: already walks -- so it is found by declaring `active_zones: ["graveyard"]`
#: like any other graveyard trigger.
LEAVE_TRIGGERS = frozenset({"dies", "creature_dies", "leaves_battlefield"})


def fire(
    state: GameState,
    event_type: str,
    *,
    player: int | None = None,
    source: int | None = None,
    **data: Any,
) -> GameEvent:
    """Record an event and queue every triggered ability that matches it."""
    event = state.emit(event_type, player=player, source=source, **data)
    collect(state, event)
    return event


def collect(state: GameState, event: GameEvent) -> None:
    """Scan for triggered abilities matching ``event`` and queue them."""
    doubled = _land_trigger_doublers(state, event)
    doublers = _trigger_doublers(state, event)
    for obj, ability in _candidate_abilities(state, event):
        spec = ability.trigger
        if spec is None:
            continue
        if not _matches(state, obj, spec, event):
            continue
        _queue(state, obj, ability, event)
        if obj.controller in doubled:
            # Ancient Greenwarden: "that ability triggers an additional time".
            # Queued twice rather than resolved twice, because the two copies are
            # separate abilities on the stack and anything in between -- another
            # landfall trigger, a response -- goes between them.
            _queue(state, obj, ability, event)
        for source_obj, static in doublers:
            # `affects` asks about the permanent whose ability just triggered,
            # which is the axis Harmonic Prodigy scopes on ("a Shaman or another
            # Wizard you control"); the *cause* was already matched once, above
            # the loop, because it is a fact about the event and not about this
            # ability. Two doublers stack, and so does a doubler with Ancient
            # Greenwarden -- each queues one more copy, which is what "triggers
            # an additional time" says however many say it.
            if _static_matches(state, obj, source_obj, static.get("affects")):
                _queue(state, obj, ability, event)
    _arm_delayed(state, event)


def _arm_delayed(state: GameState, event: GameEvent) -> None:
    """Wake any event-watching delayed ability this event just satisfied (603.7).

    The second half of the walk above, and it is a separate one because the
    thing being scanned is a different kind of thing: not a permanent with an
    ability printed on it, but a **subscription with no permanent at all** --
    "Whenever one or more creatures you control deal combat damage to one or
    more players this turn, you become the monarch", installed by a sorcery that
    is in a graveyard by the time it can fire.

    It **arms** rather than resolves. `collect` is reached from inside
    `damage_player`, four frames below anything that can ask a question, so
    resolving here would forbid the delayed half from containing a decision --
    which the step-scoped half has always been allowed. So a copy goes on
    `state.armed_delays` with the event's payload folded into the captured
    bindings, and `game._advance` resolves it at the next moment the engine can
    suspend. `pending_triggers` earns its keep the same way.

    A **copy**, and for a ``this_turn`` subscription the original stays on
    `state.delayed_triggers`: the printed duration is the rest of the turn, so a
    second combat fires it again. That is also why a "fired" flag would be the
    wrong shape *there* -- the one-per-batch guarantee belongs to the **event**,
    which is fired once per damage batch, and not to a counter here.

    An ``until_it_fires`` subscription is struck off instead, and that is not the
    flag this docstring refuses. "Exile it **until** an opponent becomes the
    monarch" (Palace Jailer) is not a trigger with a duration; it is the *end* of
    a duration written on another effect, so the first crossing is the whole of
    it and there is nothing left to fire twice. It is discharged **here rather
    than after resolving**, so the exile ends exactly once even if the same
    crossing arms it again before the advance loop gets round to the copy --
    which `_delayed_bindings` has already snapshotted everything it needs from.

    See :data:`~automtg.engine.structs.DELAYED_DURATIONS` for why that is one
    field with two values rather than two booleans.
    """
    if not state.delayed_triggers:
        return
    from dataclasses import replace

    spent: list[DelayedTrigger] = []
    for delayed in list(state.delayed_triggers):
        spec = delayed.trigger
        if spec is None:
            continue
        if not _delayed_matches(state, delayed, spec, event):
            continue
        state.armed_delays.append(
            replace(delayed, bindings=_delayed_bindings(delayed, spec, event))
        )
        if delayed.duration == "until_it_fires":
            spent.append(delayed)
    if spent:
        # Identity, not equality: two Palace Jailers each holding a creature
        # differ only in their captured `bindings`, and a third that exiled
        # nothing would compare equal to another that did.
        state.delayed_triggers = [
            d for d in state.delayed_triggers if not any(d is s for s in spent)
        ]


def _delayed_matches(
    state: GameState, delayed: DelayedTrigger, spec: TriggerSpec, event: GameEvent
) -> bool:
    """Whether this event is the one a delayed ability is waiting for.

    `_matches` reads every answer off the :class:`GameObject` hosting the
    ability -- ``obj.controller`` for the ``controller`` clause, ``obj.oid`` for
    ``source`` and ``filter`` -- and a delayed ability has no such object. Its
    controller was captured when it was created (603.7: the *resolving ability*
    creates it, so "you" is the player who resolved the spell, fixed then and
    not re-read later), and the card the spell came from is sitting in a
    graveyard where its controller has been reset to its owner.

    So this is the narrow form of the same comparison: the event type, the
    ``controller`` clause against the captured player, and an intervening-if.
    The loader refuses every other clause rather than accepting one and reading
    it off a permanent that is not there -- see `_validate_delayed_trigger`.
    """
    expected = TRIGGER_EVENTS.get(spec.event)
    if expected is None or expected != event.type:
        return False

    # The one restriction here that is not read off a hosting permanent, and so
    # the one a delayed ability can still be asked. See `_half_matches`.
    if not _half_matches(spec.event, event):
        return False

    actor = _actor(state, spec.event, event, _subject_oid(spec.event, event))
    if actor is not None:
        if spec.controller == "you" and actor != delayed.controller:
            return False
        if spec.controller == "opponent" and actor == delayed.controller:
            return False

    if spec.condition is not None:
        from .effects.conditions import evaluate_condition

        return evaluate_condition(
            state,
            spec.condition,
            controller=delayed.controller,
            source=delayed.source_oid,
            bindings=_delayed_bindings(delayed, spec, event),
        )
    return True


def _delayed_bindings(
    delayed: DelayedTrigger, spec: TriggerSpec, event: GameEvent
) -> dict[str, Any]:
    """What a fired delayed ability resolves with.

    Two layers, and the order between them is the whole of it. Underneath are
    the bindings **captured when the delay was created** -- `op_delay`'s
    long-standing promise, and the reason `x` survives from a spell that has
    since left the stack. On top is what the *event* carried, because the
    delayed half is a triggered ability like any other and "those creatures" has
    to mean the ones that just did the thing.

    `event_bindings` is the sibling for a hosted ability and cannot be shared:
    it writes ``self`` and ``x`` off the permanent, and here there is no
    permanent -- reading `x` off one would overwrite the X that was actually
    paid with a zero.
    """
    bindings = dict(delayed.bindings)
    bindings["event_player"] = event.player
    bindings["event_type"] = event.type
    subject = _subject_oid(spec.event, event)
    if subject is not None:
        bindings["subject"] = subject
    for key in EVENT_BINDING_KEYS:
        if key in event.data:
            bindings[key] = event.data[key]
    return bindings


def run_armed_delays(state: GameState) -> Generator[Any, list[int], None]:
    """Resolve every delayed ability whose event has fired.

    Directly rather than on the stack, which is the divergence
    `turn._run_delayed` records for the step-scoped half and `docs/rules-coverage.md`
    records for both: a delayed trigger is a real triggered ability and should be
    respondable. The two halves of 603.7 diverge the same way on purpose --
    having only one of them go on the stack would be a stranger rule than having
    neither.

    Drained one at a time, and struck off **before** it runs rather than after,
    so an ability that arms another one during its own resolution is picked up
    on the next pass instead of being lost or run twice.
    """
    from .effects import execute
    from .effects.context import EffectContext

    while state.armed_delays:
        delayed = state.armed_delays.pop(0)
        ctx = EffectContext(
            state=state,
            controller=delayed.controller,
            source_oid=delayed.source_oid,
            targets={},
            bindings=dict(delayed.bindings),
            source_name=delayed.description,
        )
        yield from execute(ctx, list(delayed.effects))


def _trigger_doublers(state: GameState, event: GameEvent):
    """Every ``double_triggers`` static whose *cause* clause this event satisfies.

    Two shipped cards want this and they scope it on different axes, which is
    why the effect has two filters rather than one:

    - **Harmonic Prodigy** -- "if a triggered ability of a Shaman or another
      Wizard you control triggers". The scope is the *permanent whose ability
      fired*, and any event at all counts. That is ``affects``, applied per
      ability in `collect`.
    - **Veyran** -- "if you casting or copying an instant or sorcery spell
      causes a triggered ability of a permanent you control to trigger". The
      scope is the **cause**: which event, whose, and what it was. That is
      ``cause_events`` / ``cause_controller`` / ``cause_filter``, matched here
      once for the whole event rather than per ability.

    Either filter omitted means "any", so a card that says only one of the two
    writes only one of them.

    `double_land_triggers` stays where it is rather than being folded into this:
    it is player-wide with no `affects` at all, and it reads its "as long as"
    gate through `players_doubling_land_triggers`, which is the single place
    every player-wide static is gated.
    """
    from .characteristics import _battlefield_statics

    out = []
    for source_obj, static in _battlefield_statics(state):
        if static.get("effect") != "double_triggers":
            continue
        if not _cause_matches(state, source_obj, static, event):
            continue
        out.append((source_obj, static))
    return out


def _cause_matches(
    state: GameState, source_obj: GameObject, static: Mapping[str, Any], event: GameEvent
) -> bool:
    """Does ``event`` count as the cause this static names?"""
    names = static.get("cause_events")
    if names is None:
        return True
    dsl = next((n for n in names if TRIGGER_EVENTS.get(n) == event.type), None)
    if dsl is None:
        return False

    subject = _subject_oid(dsl, event)
    who = static.get("cause_controller")
    if who is not None:
        actor = _actor(state, dsl, event, subject)
        if who == "you" and actor != source_obj.controller:
            return False
        if who == "opponent" and (actor is None or actor == source_obj.controller):
            return False

    filt = static.get("cause_filter")
    if filt:
        if subject is None:
            return False
        if not matches_card_filter(state, subject, filt, source_obj):
            return False
    return True


def _static_matches(
    state: GameState, obj: GameObject, source_obj: GameObject, affects: Any
) -> bool:
    """`characteristics._matches`, imported late for the reason the rest are."""
    from .characteristics import _matches

    return _matches(state, obj, source_obj, affects)


def _land_trigger_doublers(state: GameState, event: GameEvent) -> frozenset[int]:
    """Players whose triggers this event should fire twice for.

    Only lands entering, which is what the one card that does this says. A
    general "double every trigger" would be a different and much larger claim.
    """
    if event.type is not EventType.ENTERS_BATTLEFIELD:
        return frozenset()
    entered = state.objects.get(event.data.get("oid"))
    if entered is None or "Land" not in state.card_of(entered).types:
        return frozenset()

    # Imported here rather than at module scope for the reason `costs` does the
    # same: `characteristics` is the wide end of the engine and this is the one
    # line of it triggers needs. `players_doubling_land_triggers` -- not a local
    # walk -- because it applies the static's "as long as…" gate, which every
    # player-wide static now goes through in exactly one place.
    from .characteristics import players_doubling_land_triggers

    return players_doubling_land_triggers(state)


def _candidate_abilities(state: GameState, event: GameEvent):
    """Every (object, triggered ability) pair that could be listening.

    Objects on the battlefield are always scanned.  Abilities that declare extra
    ``active_zones`` (Edgar Markov's eminence, which works from the command zone)
    are scanned there too.  Finally, an object that has just left the battlefield
    is scanned for its own leave-triggers using last-known information.
    """
    seen: set[int] = set()

    def emit_from(obj: GameObject, zone: Zone):
        if obj.face_down and zone is Zone.BATTLEFIELD:
            # A face-down permanent has no abilities (707.2), so the hidden
            # card's triggers do not listen. Checked here rather than at each
            # trigger, because this is the one place that walks a card's
            # abilities on behalf of an object.
            #
            # Except the one the *rules* put there. A cloaked permanent has ward
            # {2} (701.61a), which comes from the cloak rule and not from the
            # card underneath -- and must not come from the card, since that
            # card is usually not even a creature. So it is supplied here, in
            # the same breath as the sentence that says everything else is gone.
            if obj.cloaked:
                from .carddef import CLOAK_WARD

                yield obj, CLOAK_WARD
            return
        # Derived rather than printed: a permanent that has lost its
        # abilities has lost its triggered ones too, and this is the only place
        # that would otherwise go on listening -- an imprisoned Bloodghast
        # still seeing landfall.
        from .characteristics import abilities_of

        for ability in abilities_of(state, obj.oid):
            if not ability.is_triggered or ability.trigger is None:
                continue
            if zone not in ability.active_zones:
                continue
            yield obj, ability

    # "Each other Human you control ... has ward {1}." A continuous effect whose
    # product is a *triggered ability*, so this is where it is read -- once for
    # the whole battlefield, because `granted_wards` is asked on every event and
    # an ordinary board has no ward static at all.
    from .characteristics import granted_wards

    wards = granted_wards(state)

    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        seen.add(oid)
        yield from emit_from(obj, Zone.BATTLEFIELD)
        # Yielded with `obj` as the source, and that is the whole point of
        # granting ward this way rather than hosting one filtered trigger on the
        # granter: the ability belongs to the creature being targeted, so an
        # opponent who answers the trigger by killing the granter still pays.
        for ability in wards.get(oid, ()):
            yield obj, ability
        # Abilities granted by something else. Yielded with `obj` as the source,
        # so "whenever *this creature* deals combat damage" means the creature
        # that was granted the ability, not the permanent that granted it.
        from .primitives import granted_abilities

        for _granter, ability in granted_abilities(state, oid):
            if ability.is_triggered and ability.trigger is not None:
                yield obj, ability

    # The stack, for "When you cast this spell, …" -- an ability that fires
    # while its own card is the spell being cast, and is therefore never on the
    # battlefield when it matters. Scanned separately because the stack is not a
    # player zone: it is shared, ordered, and holds the spell under its own
    # trigger.
    for item in list(state.stack):
        if item.oid is None or item.oid in seen:
            continue
        obj = state.objects.get(item.oid)
        if obj is None:
            continue
        seen.add(item.oid)
        yield from emit_from(obj, Zone.STACK)

    for p in state.players:
        for zone in (Zone.COMMAND, Zone.GRAVEYARD, Zone.HAND, Zone.EXILE):
            for oid in list(p.zone_list(zone)):
                obj = state.objects.get(oid)
                if obj is None or oid in seen:
                    continue
                yield from emit_from(obj, zone)

    # Leave-the-battlefield triggers on the object that just left.
    subject = event.data.get("oid") if event.type in (EventType.DIES, EventType.LEAVES_BATTLEFIELD) else None
    if subject is not None and subject not in seen:
        obj = state.objects.get(subject)
        if obj is not None:
            # Printed abilities and granted ones both. Every other branch of
            # this generator pairs an abilities walk with `granted_abilities`;
            # this one did not, so an ability granted to a creature could never
            # fire on that creature's own death -- which is the whole of Malakir
            # Rebirth.
            #
            # The walk is over *derived* abilities for `emit_from`'s reason, and
            # here it reads the board as the permanent left it -- which is what
            # a leave-the-battlefield trigger is asking about (603.6c).
            from .characteristics import abilities_of
            from .primitives import granted_abilities

            granted = [a for _granter, a in granted_abilities(state, subject)]
            for ability in (*abilities_of(state, subject), *granted):
                if not ability.is_triggered or ability.trigger is None:
                    continue
                if ability.trigger.event in LEAVE_TRIGGERS and ability.trigger.source == "self":
                    yield obj, ability


def _matches(
    state: GameState, obj: GameObject, spec: TriggerSpec, event: GameEvent
) -> bool:
    expected = TRIGGER_EVENTS.get(spec.event)
    if expected is None or expected != event.type:
        return False

    subject_oid = _subject_oid(spec.event, event)

    if spec.source == "self" and subject_oid != obj.oid and event.source != obj.oid:
        return False

    # "creature_dies" is sugar for a dies trigger filtered to creatures.
    if spec.event == "creature_dies" and not event.data.get("was_creature", False):
        return False

    # Which half of a two-shaped damage event this trigger is about -- see
    # `EVENT_HALVES`. Three names take one half each, and letting the other one
    # through fires every enrage on the board off a Lightning Bolt to the face.
    if not _half_matches(spec.event, event):
        return False

    # `source: "self"` on `dealt_damage` means *this creature was dealt damage*,
    # never "this creature dealt it". The generic check above accepts either,
    # because for most events the subject and the source are the same object --
    # for this one they are the victim and the attacker, so a bear would trigger
    # its own enrage every time it hit something.
    if spec.event == "dealt_damage" and spec.source == "self" and subject_oid != obj.oid:
        return False

    if spec.event == "deals_damage_to_player" and subject_oid is None:
        # "Whenever **enchanted creature** deals damage" is a claim about a
        # permanent, and the subject is the only thing that names it. Damage can
        # reach a player with no source object at all (`source_oid=None`), and
        # such an event answers no filter and no `source: "self"` -- so an
        # unfiltered trigger would be the one shape that fires off it, which is
        # the wide direction. There is no card that means "whenever damage is
        # dealt to a player by nothing".
        return False

    # "…if it wasn't put onto the battlefield with this ability." The loop guard,
    # and it has to be checked here rather than as a condition, because by the
    # time the ability resolves the cause is no longer anywhere to be read.
    if spec.not_cause is not None and event.data.get("cause") == spec.not_cause:
        return False

    # "Whenever a +1/+1 counter is put on this creature". `add_counters` has
    # always put the kind on the event and nothing read it, so an unfiltered
    # trigger fires on charge and slumber counters too -- both of which the
    # shipped pool places.
    if spec.counter is not None and event.data.get("counter") != spec.counter:
        return False

    # "II --". One CHAPTER_REACHED event carries the number the Saga's lore
    # counters just reached, and every chapter ability on that Saga is a candidate
    # for it, so this comparison is the whole of which chapter runs. Without it a
    # three-chapter Saga would put all three chapters on the stack off its first
    # lore counter.
    if spec.chapter is not None and event.data.get("chapter") != spec.chapter:
        return False

    # "…**if it isn't a mana ability**." An intervening-if in the printed text
    # and a restriction here, because `condition` cannot reach it: every
    # condition key asks about the board or about the trigger's own card, and
    # this asks a property of the ability that fired. `filter` cannot reach it
    # either -- it reads the source permanent's printed face, and a fetchland's
    # sacrifice ability and its mana tap live on the same card.
    #
    # Both activation paths put the flag on the event, so this compares a real
    # answer rather than an absence: a `False` spec on an event that forgot to
    # say would otherwise pass, which is the wide direction.
    if spec.mana_ability is not None and bool(
        event.data.get("mana_ability")
    ) is not spec.mana_ability:
        return False

    # "Whenever you draw your **second** card each turn." An ordinal is a fact
    # about the draw that just happened, and `draw_cards` writes it onto the
    # event, so it is answered here -- once, where the ability queues -- and
    # never again.
    #
    # The condition form of the same clause is the near miss, and it is wrong in
    # the card's ordinary line of play rather than at an edge: intervening-ifs
    # are re-checked on resolution (603.4), and the draw-two spell that queued
    # the trigger with the tally at 2 has already pushed it to 3 by then, so the
    # ability resolves as `skipped="condition"` and Prince Imrahil makes no
    # token off a Divination. Written with `>=` and `max_per_turn: 1` it
    # survives the re-check and gains the opposite fault: a permanent entering
    # after two draws fires on the third card, where the printed card is silent
    # for the rest of the turn. This asks the only question that is stable.
    #
    # `spell_cast` asks the same question of a cast -- "an opponent casts their
    # second spell each turn" (Mangara) -- and, with a `filter`, of a *run* of
    # casts: see `_spell_ordinal`.
    if spec.nth is not None and _ordinal(state, spec, event) != spec.nth:
        return False

    actor = _actor(state, spec.event, event, subject_oid)
    if actor is not None:
        if spec.controller == "you" and actor != obj.controller:
            return False
        if spec.controller == "opponent" and actor == obj.controller:
            return False

    if spec.defending is not None and not _defender_matches(spec.defending, obj, event):
        return False

    if spec.filter is not None:
        if subject_oid is None:
            return False
        if not matches_card_filter(state, subject_oid, spec.filter, obj):
            return False

    if spec.condition is not None:
        from .effects.conditions import evaluate_condition

        if not evaluate_condition(
            state,
            spec.condition,
            controller=obj.controller,
            source=obj.oid,
            bindings=event_bindings(obj, spec, event),
        ):
            return False

    return True


#: The filter keys an ordinal can be counted over: exactly the ones
#: `characteristics._matches_printed` reads. The earlier spells of the run have
#: left the stack by the time a later one is cast, so only their printed faces
#: are left to ask -- a board-state key (`mana_value` of a paid X, `paid_by`,
#: `exclude_self`) would be answered for this spell and silently ignored for
#: every spell before it. The loader refuses the rest.
ORDINAL_FILTER_KEYS = frozenset(
    {
        "types",
        "any_types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "min_colors",
        "keywords",
        "not_keywords",
        "name",
    }
)


def _ordinal(state: GameState, spec: TriggerSpec, event: GameEvent) -> int | None:
    """The event's ordinal as ``spec`` counts it.

    A draw's is on the event. So is a cast's, and that answers an unfiltered
    `spell_cast` trigger; a filtered one is sent to `_spell_ordinal`.
    """
    nth = event.data.get("nth")
    if spec.event != "spell_cast" or spec.filter is None or nth is None:
        return nth
    return _spell_ordinal(state, spec.filter, event.player, int(nth))


def _spell_ordinal(state: GameState, filt: Mapping[str, Any], pid: int | None, nth: int) -> int:
    """This spell's place among the caster's spells **matching** ``filt`` this turn.

    "Whenever an opponent casts their first **noncreature** spell each turn"
    (Esper Sentinel) is not "their first spell, if it is noncreature": a player
    who casts a creature and then an artifact is casting their first noncreature
    spell with the artifact, and a flat ordinal of 2 would miss it. So the
    trigger's own `filter` says which run is being counted -- the printed
    family is always "their Nth <kind> spell", and the kinds are open-ended
    (noncreature, instant or sorcery, multicolored), which is why the event does
    not carry a fixed set of per-kind ordinals instead.

    Counted off `TurnLedger.spells_cast_ids`, cut at this cast's flat ordinal so
    that a spell cast later -- in response, before this trigger is read -- is not
    in the run. The earlier spells are matched on their printed faces (see
    `ORDINAL_FILTER_KEYS`); this spell itself counts as one because the trigger's
    `filter` is checked against it anyway, and a spell that fails it never
    fires the ability whatever this returns.
    """
    from .characteristics import _matches_printed

    registry = state.registry
    ids = state.turn_ledger.spells_cast_ids.get(pid, []) if pid is not None else []
    earlier = sum(
        1
        for cast_id in ids[: nth - 1]
        # `in` before `get`, as `values.py` does for the same list.
        if cast_id in registry and _matches_printed(registry.get(cast_id), filt)
    )
    return earlier + 1


def event_bindings(obj: GameObject, spec: TriggerSpec, event: GameEvent) -> dict[str, Any]:
    """What the event carried, for a condition or a queued trigger to read.

    Shared by `_matches` and `_queue` so an intervening-if and the ability it
    gates cannot disagree about what "that creature" means. They used to: the
    condition was evaluated with no bindings at all, so evolve's comparison
    against the creature that entered read zero and the ability never fired --
    quietly, and only for the conditions that ask about the event rather than
    about the board.
    """
    bindings: dict[str, Any] = {
        "self": obj.oid,
        "event_player": event.player,
        "event_type": event.type,
        "x": obj.cast_x,
    }
    subject = _subject_oid(spec.event, event)
    if subject is not None:
        bindings["subject"] = subject
    for key in EVENT_BINDING_KEYS:
        if key in event.data:
            bindings[key] = event.data[key]
    return bindings


#: Event payload keys carried into a trigger's bindings.
EVENT_BINDING_KEYS = (
    "amount",
    # Which zone the permanent came from -- Celes, Rune Knight: "if one or more
    # of them **entered from a graveyard**". `cause` names the *mechanism*
    # (`put_onto_battlefield`, `manifest`, `meld`) and the same mechanism
    # reaches the battlefield from any zone, so it cannot answer this. The
    # origin was on the separate ZONE_CHANGE event all along, which no trigger
    # maps to, so nothing could reach it.
    "from_zone",
    "damage",
    "life",
    "sid",
    "defender",
    "was_attacking",
    "counter",
    "blockers",
    # "…**those creatures** gain menace until end of turn." The set that caused
    # the trigger, and the one binding here that is a *list* of oids rather than
    # one: `resolve_pool` sends `{"binding": "attackers"}` through `_bound_oids`,
    # which has accepted a list since devour, so nothing downstream had to learn
    # a new shape -- the set was simply being dropped on the floor here.
    #
    # On `creatures_attack_player` it is the subset declared against *that*
    # defender; on `you_attack` it is the whole declaration, which is what
    # "whenever you attack" means. Both are written by `finish_attackers`.
    #
    # `{"zone": "battlefield", "attacking": true}` is the near miss and says
    # something strictly larger: `attacking` is a bare boolean with no notion of
    # whom, so on a split attack it also names the creatures attacking the
    # trigger's own controller.
    "attackers",
    # Persist and undying: what was on the creature before it died, which
    # nothing can read off the object afterwards.
    "had_counters",
    # "…equal to its power", asked about a creature that has just died
    # (Goldvein Hydra). Read off the event for the same reason `had_counters`
    # is: the object in the graveyard answers with its printed line, having lost
    # its counters and every anthem that was applying to it. Read through the
    # `power_had` / `toughness_had` value keys.
    "had_power",
    "had_toughness",
)


def _defender_matches(clause: str, obj: GameObject, event: GameEvent) -> bool:
    """Whether the player being attacked is the one the trigger asks about.

    ``defender`` is already on the ``attacks`` event -- combat records which
    player each attacker was declared against -- so this is a filter rather than
    new bookkeeping.  It exists because ``controller`` cannot answer the
    question: "whenever a creature attacks you" is about the *defending* player,
    and a two-player game hides the difference that a pod makes obvious.

    ``creatures_attack_player`` carries the same key for the same reason, one
    declaration coarser.  The absent-defender guard below is why that event had
    to exist at all: on a bare ``ATTACKERS_DECLARED`` there is nothing to
    compare, so a ``defending`` clause matches nothing, forever and silently.
    """
    defender = event.data.get("defender")
    if defender is None:
        return False
    if clause == "you":
        return int(defender) == obj.controller
    if clause == "opponent":
        return int(defender) != obj.controller
    return True


def _subject_oid(dsl_event: str, event: GameEvent) -> int | None:
    if dsl_event not in OBJECT_SUBJECT_TRIGGERS:
        return None
    for key in ("oid", "spell_oid", "attacker", "blocker", "land_oid"):
        value = event.data.get(key)
        if value is not None:
            return int(value)
    return event.source


def _actor(
    state: GameState, dsl_event: str, event: GameEvent, subject_oid: int | None
) -> int | None:
    """The player the ``controller`` clause is compared against."""
    # `discard` is listed here even though it also has an object subject. The
    # clause asks *who discarded*, and the discarded card is in a graveyard by
    # now -- reading the actor off the object would be reading a controller that
    # `reset_permanent_state` has already been through. `discard_cards` puts the
    # discarding player on the event, so take it from there.
    # `becomes_target` is listed here for the same reason `discard` is, and it
    # matters more: the clause asks *whose spell it is*. Heroic is "whenever you
    # cast a spell that targets this creature" and ward is "whenever an opponent
    # casts one", so reading the actor off the subject -- the creature being
    # targeted, whose controller is nearly always the trigger's own controller
    # -- would make heroic fire on everything and ward on nothing.
    # `becomes_monarch` is listed rather than left to the fallthrough, because
    # what it means is load-bearing: the actor is the player who *became* the
    # monarch, so `controller: "opponent"` reads "an opponent becomes the
    # monarch" -- which is the whole of Palace Jailer's duration and would be a
    # strictly better card if it read the crown's previous holder instead.
    # `ability_activated` is here for the same reason `becomes_target` is, and
    # the difference is the whole of "whenever an **opponent** activates": the
    # clause asks who activated the ability, not who controls the permanent it
    # was printed on. Reading it off the subject would let an opponent equip
    # your creature -- their ability, your permanent -- without triggering, and
    # would fire on your own Signet the moment you tapped it under an
    # opponent's Harsh Mentor.
    # `damage_prevented` is listed rather than left to the fallthrough for the
    # reason `becomes_monarch` is: what the clause means is load-bearing. The
    # actor is the player whose damage was prevented, so `controller: "you"`
    # reads "damage that would be dealt to **you**" -- and the fallthrough would
    # reach the same answer today only because the player half of the event
    # carries no `oid`. Saying it here means the answer does not depend on that.
    # `creatures_attack_player` is listed for the reason `damage_prevented` is:
    # the fallthrough would reach the same answer today only because the event
    # carries no `oid`, and the clause is load-bearing. The actor is the
    # **attacking** player -- so `controller: "you"` is "whenever you attack
    # somebody", and `controller: "any"` is Frontier Warmonger's "whenever one
    # or more creatures attack", whoever is swinging them. Who is being attacked
    # is the separate `defending` clause, and never this one.
    # `creatures_deal_combat_damage` is listed for the reason
    # `creatures_attack_player` is, and it is the whole of "creatures **you
    # control**": the actor is the player whose creatures connected, which
    # `_fire_damage_batch` puts on the event because it is the key the batch was
    # grouped by. Whom they hit is `damaged`, and never this.
    # `spell_copied` is listed for the reason `spell_cast` is, and the answer
    # differs from the fallthrough: the subject is the *original* spell, so
    # reading its controller would make "whenever **you** copy" fire on an
    # opponent copying your spell, and stay silent when you copy theirs.
    # `put_copy_on_stack` puts the copy's controller on the event, which is who
    # did the copying -- 706.10 gives the copy to whoever created it.
    if dsl_event in ("land_played", "spell_cast", "spell_copied", "upkeep", "draw_step", "end_step", "you_gain_life", "draw", "discard", "begin_combat", "becomes_target", "becomes_monarch", "ability_activated", "damage_prevented", "creatures_attack_player", "creatures_deal_combat_damage"):
        return event.player
    # `deals_damage_to_player` is here beside the combat-only trigger it
    # generalises, and for the same reason: `event.player` on a damage event is
    # the seat that was **hit**, so the fallthrough below would compare a
    # `controller` clause against the victim and make "a creature you control
    # deals damage" mean "…deals damage to you". `damage_player` puts the
    # dealing permanent's controller on the event, which is the answer, and the
    # separate `defending` clause is what asks who was hit.
    if dsl_event in ("deals_combat_damage_to_player", "deals_damage_to_player"):
        controller = event.data.get("controller")
        return int(controller) if controller is not None else None
    if subject_oid is not None:
        obj = state.objects.get(subject_oid)
        if obj is not None:
            return obj.controller
        return event.player
    return event.player


def matches_card_filter(
    state: GameState,
    oid: int,
    filt: Mapping[str, Any],
    ability_source: GameObject,
) -> bool:
    """Match a trigger filter against an object's *printed* card characteristics.

    Trigger subjects are frequently gone by the time we look (a creature that
    died, a spell that resolved), so this deliberately reads the card face plus
    the object's last-known controller rather than derived characteristics.
    """
    obj = state.objects.get(oid)
    if obj is None:
        return False
    card = state.card_of(obj)

    # "…a creature spell of the chosen type." The same substitution the static
    # filters do, because Vanquisher's Banner asks the question from both.
    from .characteristics import resolve_chosen_subtypes

    filt = resolve_chosen_subtypes(filt, ability_source)

    if filt.get("exclude_self") and oid == ability_source.oid:
        return False
    if filt.get("self_only") and oid != ability_source.oid:
        return False

    # "Whenever a creature dealt damage by this creature this turn dies…"
    # Sengir Vampire. A relationship rather than a characteristic, so it is
    # answered from the per-turn ledger on the state rather than from the card
    # face -- and it has to be, because the subject has already died and
    # anything stored on it is gone.
    # "When the creature this card haunts dies…" -- the mirror of the clause
    # below, and answered off the *ability source* rather than off the subject:
    # the haunted creature has just died and carries no record of who was
    # haunting it, while the haunting card is sitting in exile with the link.
    # "Whenever **equipped creature** dies…" -- Skullclamp. The same shape as
    # `haunted_by` below: answered off the *ability source's* link rather than
    # off the subject, because an Equipment knows what it is attached to and a
    # dying creature does not know what was attached to it.
    #
    # `last_attached_to` is why this works at all. `zones.move_object` calls
    # `_detach_all` before it fires LEAVES_BATTLEFIELD and DIES, so at match
    # time the Equipment is attached to nothing and a plain `attached_to == oid`
    # test could never be true for a dies trigger -- the exact failure this
    # capability's gap record predicted.
    if filt.get("attached") and oid not in (
        ability_source.attached_to,
        ability_source.last_attached_to,
    ):
        return False

    haunted_by = filt.get("haunted_by")
    if haunted_by is not None and (
        haunted_by != "self" or ability_source.haunting != oid
    ):
        return False

    # "Whenever the creature this card is encoded on deals combat damage…" --
    # cipher, and the same shape as `haunted_by` one line up: answered off the
    # ability source, which is the card sitting in exile with the link.
    encoded_by = filt.get("encoded_by")
    if encoded_by is not None and (
        encoded_by != "self" or ability_source.encoded_on != oid
    ):
        return False

    damaged_by = filt.get("damaged_by")
    if damaged_by is not None:
        who = ability_source.oid if damaged_by == "self" else damaged_by
        if who not in state.damage_ledger.get(oid, ()):
            return False

    controller = filt.get("controller")
    if controller == "you" and obj.controller != ability_source.controller:
        return False
    if controller == "opponent" and obj.controller == ability_source.controller:
        return False

    # "…an ability of an artifact, creature, or land **on the battlefield**."
    # `zone` has always been a legal `SELECTOR_KEYS` entry, so a trigger filter
    # carrying it loaded and then did nothing -- the silently-wider filter the
    # `not_supertypes` note below is about, and the direction that matters here:
    # without it Harsh Mentor fires when an opponent *cycles* a creature card,
    # which is an activated ability of a creature card in a hand.
    zone = filt.get("zone")
    if zone is not None:
        from .effects.selectors import ZONE_NAMES

        if obj.zone is not ZONE_NAMES.get(zone):
            return False

    types = filt.get("types")
    if types and not set(types).issubset(card.types):
        return False
    # The any-of form. `types` is a conjunction -- ["Artifact", "Creature"]
    # means a permanent that is both -- so "an artifact, creature, or land"
    # cannot be said with it, and saying it with `types` matches nothing at all.
    # `selectors.matches` has had this key since Acidic Slime; the trigger side
    # validated it and ignored it.
    any_types = filt.get("any_types")
    if any_types and not (set(any_types) & card.types):
        return False
    not_types = filt.get("not_types")
    if not_types and set(not_types) & card.types:
        return False
    subtypes = filt.get("subtypes")
    if subtypes and not (set(subtypes) & card.subtypes):
        return False
    supertypes = filt.get("supertypes")
    if supertypes and not set(supertypes).issubset(card.supertypes):
        return False
    # "…nonbasic land". Honoured here as well as in `selectors.matches` because a
    # trigger filter is validated against the same `SELECTOR_KEYS`, so a key that
    # loaded and then did nothing would be exactly the silently-wider filter this
    # key exists to prevent -- and wider is the dangerous direction for a
    # negation, where a typo or an unread key forbids nothing at all.
    not_supertypes = filt.get("not_supertypes")
    if not_supertypes and set(not_supertypes) & card.supertypes:
        return False
    # "…a creature spell that shares a creature type with your commander."
    # Path of Ancestry. Answered here as well as in `selectors.matches` because
    # this is the half a *trigger* filter reaches, and the printed subtypes are
    # the right side of the comparison for a spell on the stack.
    # "When **that mana** is spent to cast a spell…" -- Path of Ancestry, Opal
    # Palace. Answered off the *subject*, which is the spell: `pay_mana` wrote
    # onto it which permanents' mana abilities made the mana that paid for it,
    # at the one instant that was knowable. A `mana_spent` event of its own
    # would fire during cost payment, before the spell is on the stack and
    # before its filter has anything to match against.
    paid_by = filt.get("paid_by")
    if paid_by is not None:
        wanted = ability_source.oid if paid_by == "self" else paid_by
        if wanted not in obj.mana_sources_spent:
            return False
    # "Whenever a token created with this creature…" -- honoured here as well
    # as in `selectors.matches` for `not_supertypes`' reason: a trigger filter
    # is validated against the same keys, and one that loaded and did nothing
    # would fire on every token at the table.
    if filt.get("created_with") is not None and obj.oid not in ability_source.created_tokens:
        return False

    who = filt.get("shares_a_type_with_commander")
    if who is not None:
        from .characteristics import commander_subtypes

        seats = (
            [ability_source.controller]
            if who in ("you", "controller")
            else [p.pid for p in state.players if p.pid != ability_source.controller]
        )
        theirs: set[str] = set()
        for seat in seats:
            theirs |= commander_subtypes(state, seat)
        if not (card.subtypes & theirs):
            return False
    colors = filt.get("colors")
    if colors and not (set(colors) & card.colors):
        return False
    # "…a **multicolored** instant or sorcery spell" (202.2b: a card with two
    # or more colors). `colors` is a membership test and says something else
    # entirely -- `["U", "R"]` matches a mono-blue spell -- so this is its own
    # clause rather than a spelling of that one.
    if (least := filt.get("min_colors")) is not None and len(card.colors) < int(least):
        return False
    keywords = filt.get("keywords")
    if keywords and not set(keywords).issubset(card.keywords):
        return False
    if "is_token" in filt and bool(obj.is_token) != bool(filt["is_token"]):
        return False
    if "is_commander" in filt and bool(obj.is_commander) != bool(filt["is_commander"]):
        return False
    # "Whenever an artifact or creature an opponent controls enters **untapped**"
    # -- Charismatic Conqueror. The one clause here that reads object *state*
    # rather than a printed characteristic, and it is sound for the reason the
    # rest of this function is not: a trigger filter is evaluated once, when the
    # ability is collected, and `zones.enter_battlefield` sets `tapped` before it
    # fires ENTERS_BATTLEFIELD -- so at match time this is the permanent's
    # arrival state, which is exactly what the printed line asks about.
    #
    # It has to be here rather than in a trigger `condition`, which would be a
    # different card: 603.4 re-checks a condition on resolution, so an opponent
    # tapping the fresh artifact in response would make the ability do nothing --
    # the exact opposite of the printed ruling, which gives you the token
    # precisely when they cannot tap it.
    #
    # Until this existed the key **loaded and was silently dropped**:
    # `validate_selector` accepts `tapped` because it is in `SELECTOR_KEYS`, and
    # nothing here read it -- so the clause vanished and the card triggered on
    # permanents entering tapped as well, strictly wider than printed. Wider is
    # the dangerous direction, and no gate could see it.
    #
    # Only meaningful on an arrival; a `dies` filter writing it reads a
    # permanent whose state `reset_permanent_state` has already cleared.
    if "tapped" in filt and bool(obj.tapped) != bool(filt["tapped"]):
        return False
    # Honoured here for the reason `tapped` above is: a trigger filter is
    # validated against the same `SELECTOR_KEYS`, and a key that loaded and was
    # then ignored would be silently wider -- a creature attacking your
    # planeswalker would count as one attacking you.
    who = filt.get("attacking_player")
    if who is not None:
        from .effects.selectors import attacking_player_matches

        if not attacking_player_matches(
            state.combat, oid, str(who), ability_source.controller
        ):
            return False
    mv = filt.get("mana_value")
    if mv is not None and not _compare(card.mana_value, mv):
        return False
    # Power and toughness are read off the board when the subject is still on
    # it, and off the printed face otherwise. Everything above this line is a
    # characteristic no layer can change, which is why the rest of this function
    # can read the card face and be right about a creature that has already
    # died -- but P/T is the one thing anthems and counters move.
    #
    # Welcoming Vampire is the witness: "creatures you control with power 2 or
    # less enter". A printed 2/2 entering under an anthem is a 3/3 and must not
    # trigger it, and reading `card.power` says it does.
    from .characteristics import chars

    live = chars(state, oid) if obj.on_battlefield else None
    power = filt.get("power")
    if power is not None and not _compare(
        (live.power if live else card.power) or 0, power
    ):
        return False
    toughness = filt.get("toughness")
    return not (
        toughness is not None
        and not _compare((live.toughness if live else card.toughness) or 0, toughness)
    )


def _compare(value: int, spec: Mapping[str, Any]) -> bool:
    op = spec.get("op", ">=")
    other = spec.get("value", 0)
    if isinstance(other, Mapping):
        other = int(other.get("const", 0))
    if op == ">=":
        return value >= other
    if op == "<=":
        return value <= other
    if op == ">":
        return value > other
    if op == "<":
        return value < other
    return value == other


def _granter_of(state: GameState, obj: GameObject, ability: Ability) -> tuple[int | None, int]:
    """Where this ability's definition lives: ``(granter oid, index there)``.

    ``(None, ability.index)`` for one the permanent prints itself, which is
    nearly every trigger in the game.

    Identity, not equality, for the **op**-granted half: two grants of the same
    ability are the same object here, and that is fine -- resolution only needs
    somewhere to look the definition up. Their index needs no translation
    either, because `primitives.granted_abilities` yields straight out of the
    granter's pool and `Ability.index` is that pool position.

    The **statically** granted half is the one that needs both halves of the
    answer. `characteristics.abilities_of` appends such an ability to the
    recipient's list and renumbers it, so the index the trigger fired with is a
    position on the *recipient* -- 2 on Tandem Lookout, whose two statics come
    first -- while `stack.ability_of` will look it up in the granter's
    ``grantable_abilities``, where it is 0. Recording the recipient's number
    there resolves a different ability or, more often, none: the trigger goes on
    the stack, resolves, and does nothing, with no error anywhere.
    """
    from .primitives import granted_abilities

    for granter, granted in granted_abilities(state, obj.oid):
        if granted is ability:
            return granter.oid, ability.index

    from .characteristics import granted_ability_origin

    origin = granted_ability_origin(state, obj.oid, ability.index)
    if origin is not None:
        return origin
    return None, ability.index


def _queue(state: GameState, obj: GameObject, ability: Ability, event: GameEvent) -> None:
    # "This ability triggers only once each turn." Counted here, where the
    # ability *queues*, because that is the printed word: an ability that
    # triggered and then fizzled has still used its one for the turn.
    #
    # Keyed by (permanent, ability index) rather than by card, so two Welcoming
    # Vampires each get their own draw.
    spec_cap = ability.trigger.max_per_turn if ability.trigger is not None else None
    spec_batched = ability.trigger.batched if ability.trigger is not None else False
    if spec_cap is not None:
        key = (obj.oid, ability.index)
        if state.triggers_this_turn.get(key, 0) >= spec_cap:
            return
        state.triggers_this_turn[key] = state.triggers_this_turn.get(key, 0) + 1

    # "Whenever **one or more** cards leave your graveyard" -- one firing per
    # simultaneous group, not per card. `state.event_batch` is bumped once per
    # effect op and once per cost payment, which are the two places an effect
    # moves several cards at once, so an `exile` over a whole graveyard shares
    # one batch and queues this ability once.
    #
    # Keyed by (permanent, ability index, batch) for the reason the per-turn cap
    # is keyed by (permanent, ability index): two Spirit Mascots each get their
    # own counter from the same departure.
    if spec_batched:
        batch = event.data.get("batch")
        if batch is not None:
            key = (obj.oid, ability.index, batch)
            if key in state.batched_triggers:
                return
            state.batched_triggers.add(key)

    state.triggers_this_step += 1
    if state.triggers_this_step > MAX_TRIGGERS_PER_STEP:
        raise RulesLoopError(
            f"more than {MAX_TRIGGERS_PER_STEP} triggers in one step "
            f"(last: {state.card_of(obj).name})"
        )
    spec = ability.trigger
    assert spec is not None
    # The same bindings the intervening-if was evaluated against, so a
    # condition and the ability it gates cannot read "that creature"
    # differently. `x` is carried through so "enters with X counters" can read
    # what was paid.
    bindings = event_bindings(obj, spec, event)

    card = state.card_of(obj)
    # `ability_index` is read back against whichever list `granted_by` names, so
    # the two are settled together -- see `_granter_of`.
    granted_by, ability_index = _granter_of(state, obj, ability)
    state.pending_triggers.append(
        TriggerInstance(
            source_oid=obj.oid,
            ability_index=ability_index,
            controller=obj.controller,
            bindings=bindings,
            description=f"{card.name}: {ability.text or spec.event}",
            # Snapshotted now, while the object still exists -- see
            # `TriggerInstance.def_id`.
            def_id=obj.def_id,
            granted_by=granted_by,
        )
    )
    state.emit(
        EventType.ABILITY_TRIGGERED,
        player=obj.controller,
        source=obj.oid,
        # The client names the source from this; without it every trigger in
        # the log and the effects layer read "An ability triggers", which is
        # the least useful sentence available in a format made of triggers.
        card=card.id,
        ability=ability.index,
        trigger=spec.event,
    )


def drain_to_stack(state: GameState):
    """Put every pending trigger on the stack in APNAP order.

    Within a single player's triggers the order is the order they were
    collected (stable and deterministic).

    A generator, because a triggered ability with targets asks its controller
    to choose them as it goes on the stack (603.3d) and that is a decision like
    any other.

    Each trigger is struck off `state.pending_triggers` **after** it lands on
    the stack, one at a time, rather than the whole list being emptied up
    front. Mid-drain the game is neither quiescent nor finished, and emptying
    first made it look like both: with the list cleared and nothing on the
    stack yet, "no pending triggers and an empty stack" -- which is how the
    tests and the auto-pass check ask whether the board has settled -- was true
    while a player still owed an answer.

    The order is a snapshot, so a trigger that fires *while* the choice is
    being made (a `became_target` trigger, most likely) waits for the next
    pass, exactly as it did before.
    """
    if not state.pending_triggers:
        return
    from .stack import push_triggered_ability

    order = [
        trig
        for pid in state.turn_order()
        for trig in state.pending_triggers
        if trig.controller == pid
    ]
    # Triggers controlled by players who have left the game simply vanish.
    state.pending_triggers = list(order)
    for trig in order:
        yield from push_triggered_ability(state, trig)
        state.pending_triggers = [t for t in state.pending_triggers if t is not trig]
