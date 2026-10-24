"""The root game state and the accessors everything else is built on."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .actions import PendingDecision
from .carddef import CardDef
from .characteristics import chars
from .enums import STEP_PHASE, Phase, Step, Zone
from .events import EventType, GameEvent
from .objects import GameObject
from .player import PlayerState
from .rng import Rng
from .structs import (
    AttackRestriction,
    BlockProhibition,
    CastLock,
    CombatState,
    DamageShield,
    DelayedTrigger,
    EnteredPermanent,
    FlashPermission,
    GraveyardCastGrant,
    LifeFloor,
    LifeLock,
    OutcomeLock,
    PlayerProtection,
    SacrificeRestriction,
    StackItem,
    TriggerInstance,
    TurnLedger,
    Unblockable,
)

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.cards.registry import CardRegistry

#: Hard cap on turns; a game that reaches it is scored as a draw.  Without this a
#: self-play run can stall forever on two durdling boards.
DEFAULT_MAX_TURNS = 60

#: Guard against infinite trigger loops within a single step.
MAX_TRIGGERS_PER_STEP = 200

#: How many extra phases one turn may actually run (`turn.grant_extra_phases`).
#:
#: Sibling of `max_turns` and `MAX_TRIGGERS_PER_STEP` rather than a rules
#: statement: "untap all creatures, there is an additional combat phase" plus a
#: way to recur it is a real and printed infinite combo (Aggravated Assault with
#: enough mana), and the rules let it run for ever. A self-play run cannot, and
#: an unbounded turn is a hang rather than a loss. Twenty is far past anything a
#: game decides on and far short of a wedged process.
MAX_EXTRA_PHASES_PER_TURN = 20


@dataclass
class GameState:
    """Everything about a game in progress.

    Zones are flat, id-keyed lists; there are no object cycles, so serialization
    and inspection are trivial.  Nothing in here is ever deep-copied: undo and
    env resets replay from ``rng.seed`` plus the action tape instead.
    """

    registry: CardRegistry
    players: list[PlayerState]
    rng: Rng

    objects: dict[int, GameObject] = field(default_factory=dict)
    battlefield: list[int] = field(default_factory=list)
    stack: list[StackItem] = field(default_factory=list)

    turn: int = 0
    #: Full cycles of the table, incremented when the active seat wraps.
    #:
    #: Deliberately *parallel* to ``turn`` rather than replacing it.  ``turn``
    #: counts player-turns and is load-bearing for summoning sickness
    #: (:meth:`GameObject.summoning_sick`), the first-draw skip, the ``max_turns``
    #: cap and the RL encoding.  But a player counting their own turns says "this
    #: is my second turn" while ``turn`` reads 3 in a two-player game, so the UI
    #: needs the round and cannot derive it: eliminations make
    #: ``turn // num_players`` drift.  A cycle-2 playtest finding.
    round: int = 0
    active_idx: int = 0
    step: Step = Step.UNTAP
    starting_player: int = 0

    priority_idx: int | None = None
    passes_in_row: int = 0
    #: Something resolved in this step and the table has not yet passed in
    #: succession on the empty stack since. The window auto-pass must not skip:
    #: a creature spell cannot be Swords'd while it is on the stack, only once
    #: it has resolved -- and by then the stack is empty again.
    just_resolved: bool = False

    combat: CombatState | None = None
    #: How many combat phases have *begun* in this game, ever.  The identity of
    #: the current one: `combat` is the phase's contents and is thrown away at
    #: its end, so it cannot say *which* combat something belonged to.
    #:
    #: Needed by "at end of combat" (`turn.DELAY_STEPS`), which has to mean the
    #: end of the combat the delay was created in and not merely the next
    #: `END_OF_COMBAT` step that happens -- a distinction with no content until
    #: `extra_combat` made two combats in one turn ordinary.
    #:
    #: Monotonic for the whole game rather than reset per turn, so a number is
    #: never reused: a delay scheduled in a postcombat main names the combat
    #: after this one, which may be an extra combat this turn or the first one
    #: next turn, and either way is the same integer.  Bumped by
    #: `combat.start_combat`, the one place a combat begins.
    combat_number: int = 0
    pending_decision: PendingDecision | None = None
    #: A suspended effect generator waiting on ``pending_decision``.  Never
    #: serialized -- replay reconstructs it by re-running the same actions.
    pending_generator: Any = field(default=None, repr=False)
    pending_triggers: list[TriggerInstance] = field(default_factory=list)
    #: Effects arranged for a later step, or for an event -- see
    #: `structs.DelayedTrigger`.
    delayed_triggers: list[DelayedTrigger] = field(default_factory=list)
    #: Event-watching delayed triggers whose event has just happened, waiting to
    #: resolve.  `pending_triggers` for the other half of 603.7, and it exists
    #: for the same reason: `triggers.collect` runs deep inside a primitive that
    #: cannot ask a question, so what it *can* do is say the ability has fired
    #: and let the advance loop resolve it at the next safe moment.  Copies, not
    #: the subscriptions themselves -- the subscription stays armed for the rest
    #: of the turn and a second combat fires it again.
    armed_delays: list[DelayedTrigger] = field(default_factory=list)
    #: The permanents a cost tapped **and named** -- `tap_permanents` with
    #: ``as`` -- keyed by a serial the ability's binding carries. Station is
    #: the witness: "put charge counters equal to **the tapped creature's**
    #: power". The rules read that power as the ability resolves, and as the
    #: creature last existed on the battlefield if it has gone (the Edge of
    #: Eternities release notes), so the binding cannot be a snapshot taken at
    #: payment -- a pump in response has to count -- and it cannot be a bare
    #: oid either, because an oid outlives its permanent here and a graveyard
    #: card answers with its printed power. Each record is ``{"oid", "power",
    #: "toughness"}`` with ``None`` while the permanent is still on the
    #: battlefield; `zones.move_object` fills the two numbers in at the moment
    #: it leaves, which is the one moment they are still there to read.
    #: Pruned when the ability that owns the record resolves.
    paid_objects: dict[int, dict[str, Any]] = field(default_factory=dict)
    next_paid_object: int = 1

    events: list[GameEvent] = field(default_factory=list)
    game_over: bool = False
    winners: list[int] = field(default_factory=list)
    result: str = ""

    next_oid: int = 1
    next_sid: int = 1
    #: A game-wide counter for the timestamps rules ask to compare (613.7) that
    #: arrival order on the battlefield cannot answer -- an Aura re-attached
    #: after it arrived is newer than one that arrived later and never moved.
    next_timestamp: int = 1

    #: Bumped whenever anything that could change derived characteristics changes.
    char_version: int = 0
    char_cache: dict[int, Any] = field(default_factory=dict, repr=False)
    char_cache_version: int = -1
    #: `characteristics._ability_statics`, cached against `char_version`. Its
    #: own field rather than a row in `char_cache`, because it is keyed by
    #: nothing -- it is one list for the whole battlefield, and it is read while
    #: `char_cache` is being filled.
    ability_static_cache: list[Any] = field(default_factory=list, repr=False)
    ability_static_version: int = -1

    triggers_this_step: int = 0
    #: Which "simultaneous" group the moves happening right now belong to.
    #: Bumped once per effect op and once per cost payment -- the two places a
    #: card can move several cards at once -- so a trigger that reads "one or
    #: more cards" can fire once for the whole group. See `triggers._queue`.
    event_batch: int = 0
    #: (oid, ability index, batch) triples a batched trigger has already queued,
    #: so "one or more" fires once per simultaneous group. Never cleared during
    #: a game: the batch counter only increases, so an old triple can never be
    #: matched again, and the set is bounded by how many batched triggers
    #: actually fired rather than by the length of the game.
    batched_triggers: set = field(default_factory=set)
    #: `replace_dies` statics whose permanent has just left the battlefield, as
    #: ``(event_batch, source as it last existed, static)``. Kalitas's ruling:
    #: if it dies at the same time as a nontoken creature an opponent controls,
    #: its ability still applies to that creature -- but the engine moves a
    #: wrath's creatures one at a time, so Kalitas may already be gone when the
    #: next one is moved. Read by `zones._dies_replacement` only while the batch
    #: is unchanged, and emptied by every state-based-action pass, which is one
    #: simultaneous event of its own (704.3) and shares the batch counter with
    #: whatever ran before it.
    leaving_dies_replacers: list[tuple[int, Any, Any]] = field(default_factory=list)
    #: "Whenever a creature dealt damage by this creature this turn dies…"
    #:
    #: victim oid -> the oids of everything that has damaged it this turn.
    #: Cleared during cleanup.
    #:
    #: It lives on the state rather than on the damaged object because the whole
    #: question is asked *about a creature that has just died*: an entry on the
    #: object would be wiped by `reset_permanent_state` on the way to the
    #: graveyard, which is exactly the moment it is needed.
    damage_ledger: dict[int, set[int]] = field(default_factory=dict)
    #: Who struck the killing blow: victim oid -> the *most recent* thing to
    #: damage it. Cleared with `damage_ledger`, which it shadows.
    #:
    #: Presentation only -- the UI captions a death "Killed by Ulamog" -- and it
    #: is deliberately a second map rather than an ordering imposed on
    #: `damage_ledger`, which is rules-facing (the `damaged_by` card filter reads
    #: it) and must not change shape for the sake of a caption.
    #:
    #: Only meaningful when its victim's ledger entry has exactly one damager.
    #: A gang block writes three sources and last-writer-wins would name an
    #: arbitrary blocker, so `sba` declines to attribute in that case rather
    #: than blaming one of them.
    last_damager: dict[int, int] = field(default_factory=dict)
    #: "…for each card you've drawn this turn." (Kydele, Chosen of Kruphix.)
    #:
    #: player id -> how many cards they have drawn during the current turn,
    #: whatever caused the draw. Cleared by the untap step, not by cleanup --
    #: see `turn._untap_step` for why the opening hand forces that.
    #:
    #: Alongside `damage_ledger` rather than on `PlayerState` because it is the
    #: same shape of thing: a tally of *events* that the current turn owns and
    #: the next turn must not see. `PlayerState` holds what a player *is* --
    #: life, zones, the city's blessing -- and `lands_played` is the one
    #: per-turn counter there, reset by the active player's own untap. This one
    #: cannot live by that rule, because you draw on other players' turns too.
    cards_drawn_this_turn: dict[int, int] = field(default_factory=dict)
    #: "…except the first one you draw in each of your draw steps." (Bard, King
    #: of Dale; Alhammarret's Archive.)
    #:
    #: player id -> cards drawn since the current draw step began. Counted only
    #: while ``step is Step.DRAW`` and cleared as each draw step is entered, so
    #: it is meaningful only while a draw step is running -- which is the only
    #: time anything reads it.
    #:
    #: Not derivable from `cards_drawn_this_turn`: a card drawn during upkeep
    #: moves the per-turn tally, and the draw step's first draw is then the
    #: turn's *second*. A replacement keyed on the per-turn count would double
    #: the turn-based draw on exactly those turns.
    cards_drawn_this_draw_step: dict[int, int] = field(default_factory=dict)
    #: "This ability triggers only once each turn." Keyed by
    #: ``(source_oid, ability_index)`` -- per *permanent*, not per card, because
    #: two Welcoming Vampires each get their own draw. Counted where triggers
    #: are queued rather than where they resolve: the printed word is
    #: "triggers", and a capped ability that queued and then fizzled has still
    #: used its one for the turn.
    #:
    #: On the state beside `cards_drawn_this_turn` and for the same reason --
    #: an ability can trigger on somebody else's turn, so this cannot live on
    #: the active player.
    triggers_this_turn: dict[tuple[int, int], int] = field(default_factory=dict)
    #: "…if a creature died this turn", "…if you attacked this turn". See
    #: `structs.TurnLedger`: the other per-turn tallies, folded from the event
    #: stream in `emit` rather than counted at six separate primitives.
    turn_ledger: TurnLedger = field(default_factory=TurnLedger)
    #: Every spell each player has cast **this game**, by the card id of the face
    #: that was cast, in cast order.
    #:
    #: "…and you've cast another spell named Approach of the Second Sun this
    #: game" (Approach of the Second Sun) is the sentence, and it cannot be
    #: answered from `TurnLedger.spells_cast_ids`: that tally is cleared at every
    #: turn boundary, so on the turn that matters it reads empty and the card
    #: could never win. Nothing else in the engine keeps cast history -- object
    #: flags die with the object on a zone change, and `set_turn_flag` is
    #: explicitly one turn.
    #:
    #: On the state rather than on a player for the reason `turn_ledger` is:
    #: it is folded from the event stream in one place (`emit`'s SPELL_CAST arm),
    #: so no cast path can forget it.
    spells_cast_this_game: dict[int, list[str]] = field(default_factory=dict)
    #: Day / night (726). ``None`` until a daybound permanent makes it day, then
    #: ``"day"`` or ``"night"`` for the rest of the game.
    #:
    #: On the *state* rather than on any player, because it is one designation
    #: the whole table shares -- the same shape `turn` and `step` have, and the
    #: reason daybound was called "a game-wide designated state" when it was
    #: refused. There was no place to keep it; this is the place.
    day_night: str | None = None
    #: The monarch (721). ``None`` until a spell or ability makes somebody the
    #: monarch (721.2), then the player id of whoever holds it.
    #:
    #: Beside `day_night` and for the same reason: it belongs to the **table**
    #: rather than to a player or a permanent, and `rules-coverage.md` called it
    #: "a designated-player mechanic the engine has no place to keep". This is
    #: the place.
    #:
    #: **One field is the whole of 721.4** ("only one player can be the monarch
    #: at a time; if a player becomes the monarch, the current monarch ceases to
    #: be"). A per-player boolean -- `has_city_s_blessing`'s shape -- would let
    #: two players hold it, and exclusivity would then be a rule somebody has to
    #: remember to enforce at every write. Here it is arithmetic.
    #:
    #: ``None`` is a *third* state and not the absence of one, which is why this
    #: is not a plain int: "if there is no monarch" (Crown of Gondor) is not the
    #: negation of "if you're the monarch", since that negation is also true
    #: while an opponent holds it.
    monarch: int | None = None
    #: "You can't attack that player this turn"; "they can't attack you this
    #: combat". One entry per (attacking player, defending player) pair under a
    #: prohibition -- see :class:`structs.AttackRestriction`.
    #:
    #: On the state for the reason `monarch` is: it is a fact about a pair of
    #: *seats*, and there may be no permanent anywhere that it belongs to. Every
    #: other attack prohibition in the engine is a fact about one creature and
    #: lives on that creature, which is why none of them could carry a defending
    #: player.
    #:
    #: A list rather than a set of pairs because two effects may impose the same
    #: pair with different durations, and the shorter one wearing off must not
    #: take the longer one with it. Normally empty, which is why
    #: `combat.attack_target_forbidden` short-circuits on it.
    attack_restrictions: list[AttackRestriction] = field(default_factory=list)
    #: "That creature can't block this turn"; "until your next turn, those
    #: creatures can't block" -- see :class:`structs.BlockProhibition`.
    #:
    #: Beside `attack_restrictions` and on the table for the same reason: the
    #: restriction outlives whatever imposed it and may have been imposed by a
    #: sorcery, so there is no permanent to hang it off. The engine's other
    #: "can't block" is a *static* on a permanent, which is precisely the shape
    #: that cannot say "the creature you targeted, until the end of this turn".
    #:
    #: A list rather than a set because the entries have different clocks and the
    #: shorter one wearing off must not take the longer one with it, and because
    #: an entry with ``objects=None`` ("every creature") does not merge with one
    #: naming a set. Normally empty, which is why `combat.block_prohibited`
    #: short-circuits on it.
    block_prohibitions: list[BlockProhibition] = field(default_factory=list)
    #: "Until end of turn, you may cast instant and sorcery spells from any
    #: graveyard." On the table beside `block_prohibitions` and for its reason:
    #: the permission belongs to no permanent, and the Saga chapter that grants
    #: it exiles the Saga in the same breath. Turn-scoped, so entries are read
    #: only while `turn` matches and are dropped in cleanup.
    graveyard_cast_grants: list[GraveyardCastGrant] = field(default_factory=list)
    #: "Target creature can't be blocked this turn" -- see
    #: :class:`structs.Unblockable`.
    #:
    #: The mirror of `block_prohibitions` above and stored the same way for the
    #: same reason, but a *separate* list because it points the other way: an
    #: entry here names an attacker and stops every block against it, an entry
    #: there names a blocker and stops it blocking anything. Merging them into
    #: one list with a side flag would only make both predicates filter it.
    #:
    #: The engine's other "can't be blocked" is the `block_restriction` static,
    #: which is precisely the shape that cannot say "the creature this activated
    #: ability targeted, until the end of this turn". Normally empty, which is
    #: why `combat.unblockable` short-circuits on it.
    unblockables: list[Unblockable] = field(default_factory=list)
    #: "Prevent all damage that would be dealt to you this turn" -- see
    #: :class:`structs.DamageShield`.
    #:
    #: The third timed table, here for the reason the two above it are: the
    #: effect belongs to no permanent (Fog is an instant, and Selfless Squire's
    #: shield outlives the Squire) and it ends at a fixed moment rather than when
    #: a source leaves the battlefield. The engine's other two preventions --
    #: the `prevent_damage` static (absorb N) and `protection` -- are both keyed
    #: to an *object id* and read off `_battlefield_statics`, so neither can be
    #: aimed at a seat at all.
    #:
    #: A list rather than a per-player flag because two shields over the same
    #: player are two effects and deduplicating them into one would be wrong the
    #: moment a second duration exists. Normally empty, which is why
    #: `primitives.damage_player` short-circuits on it before doing any work.
    damage_shields: list[DamageShield] = field(default_factory=list)
    #: "You gain protection from everything until your next turn" -- see
    #: :class:`structs.PlayerProtection`.
    #:
    #: A timed table for the reason the ones above it are: Teferi's Protection
    #: is an Instant and leaves no permanent behind to own the effect, and the
    #: protection ends at a fixed moment rather than when a source leaves the
    #: battlefield. `protection_from` is keyed to an *object id* throughout and
    #: reads `_battlefield_statics`, so it cannot be aimed at a seat.
    #:
    #: One entry per quality, so the readers get the same flat set of strings
    #: the object side already hands them. Normally empty, which is why both
    #: readers short-circuit on it before doing any work.
    player_protections: list[PlayerProtection] = field(default_factory=list)
    #: "Until your next turn, your life total can't change" -- see
    #: :class:`structs.LifeLock`.
    #:
    #: The timed table beside `player_protections`, installed by the same
    #: Instant and cleared in the same untap step. A list rather than a
    #: per-player flag because two locks over one seat are two effects, and the
    #: three life-changing sites short-circuit on the empty list, which is what
    #: it is in every game that plays none of these cards.
    life_locks: list[LifeLock] = field(default_factory=list)
    #: "You can't lose the game this turn and your opponents can't win the
    #: game this turn" -- see :class:`structs.OutcomeLock`.
    #:
    #: The timed table beside `life_locks`, on the same clock and cleared in
    #: the same cleanup step. A list for the reason that one is: two locks over
    #: one seat are two effects, and `sba`'s two readers short-circuit on the
    #: empty list -- which is what it is in every game that plays none of these
    #: cards, and both are read on every state-based-action sweep.
    outcome_locks: list[OutcomeLock] = field(default_factory=list)
    #: "Damage that would reduce your life total to less than 1 reduces it to
    #: 1 instead" -- see :class:`structs.LifeFloor`. The timed table beside
    #: `outcome_locks`, installed by the same Instant and swept in the same
    #: cleanup step, and read only by `primitives.damage_player`.
    life_floors: list[LifeFloor] = field(default_factory=list)
    #: "Until your next turn, you may cast sorcery spells as though they had
    #: flash" -- see :class:`structs.FlashPermission`. Read by
    #: `casting._timing_ok`; empty in every game that plays none of these.
    flash_permissions: list[FlashPermission] = field(default_factory=list)
    #: "Until your next turn, your opponents can't cast spells from anywhere
    #: other than their hands" -- see :class:`structs.CastLock`.
    #:
    #: The timed table beside `life_locks`, on the same clock and cleared in
    #: the same untap step. A list rather than a per-player field because two
    #: locks over one seat are two effects, and every reader short-circuits on
    #: the empty list -- which is what it is in every game that plays none of
    #: these cards, and this one is read on every legality build.
    cast_locks: list[CastLock] = field(default_factory=list)
    #: "You can't sacrifice those creatures this turn" -- see
    #: :class:`structs.SacrificeRestriction`.
    #:
    #: The fourth timed table, here for the reason the three above it are: Call
    #: for Aid is a sorcery and leaves no permanent behind to own the effect,
    #: and the prohibition ends at a fixed moment rather than when a source
    #: leaves the battlefield. Nothing else in the engine expresses a sacrifice
    #: prohibition at all -- `lock_abilities` gates a permanent's *own*
    #: activated abilities (not an outlet somebody else controls, and not the
    #: `sacrifice` op), and `replace_deaths` redirects a death that has already
    #: happened.
    #:
    #: A list rather than a per-object flag because two effects may protect the
    #: same permanent and the shorter one wearing off must not take the longer
    #: one with it, and because the mark has to survive a permanent it names
    #: changing controller. Normally empty, which is why
    #: `primitives.sacrifice_forbidden` short-circuits on it before doing any
    #: work -- it is asked once per candidate in every sacrifice pool.
    sacrifice_restrictions: list[SacrificeRestriction] = field(default_factory=list)
    max_turns: int = DEFAULT_MAX_TURNS
    #: Phases this turn has been granted and not yet begun, in the order they
    #: will run: `"combat"` or `"main"` (see `turn.EXTRA_PHASE_STEPS`).
    #:
    #: "After this phase, there is an additional combat phase" (Combat
    #: Celebrant); "after this main phase, there is an additional combat phase
    #: followed by an additional main phase" (Relentless Assault). A queue rather
    #: than a counter because the second sentence grants a *main* phase
    #: explicitly, and a bare combat count could not say which of the two came
    #: next.
    #:
    #: On the state rather than on a player, because a phase belongs to the
    #: **turn**: Seize the Day is an instant, and cast on an opponent's turn its
    #: extra combat is that opponent's. Cleared at the turn boundary, so an
    #: unspent grant -- Aggravated Assault activated in an end step, which has no
    #: main phase left to come after -- expires rather than leaking into the next
    #: player's turn.
    extra_phases: list[str] = field(default_factory=list)
    #: Where the ordinary turn resumes once the extra phases are done.
    #:
    #: An extra phase is *inserted*, so the phase the turn was about to enter is
    #: still owed. One slot and not a stack: every grant made during a detour is
    #: inserted inside that same detour (the queue above), so there is only ever
    #: one place to come back to. See `turn.next_step`.
    resume_step: Step | None = None
    #: Extra phases actually entered this turn, against `MAX_EXTRA_PHASES_PER_TURN`.
    #: Counted rather than measured off the queue because the queue drains.
    extra_phases_taken: int = 0
    #: Extra turns scheduled and not yet begun, as player ids. **Taken from the
    #: end**: rule 500.7 adds each extra turn directly after the current one, so
    #: the most recently created is taken first -- a stack, not a queue. A turn
    #: created *during* an extra turn lands on top and comes straight after it,
    #: ahead of the ones still waiting, which is the same sentence applied again.
    #:
    #: On the state rather than on a player because the order *between* players
    #: is the point: Perch Protection hands its turn to an opponent, and it has
    #: to interleave with whatever Time Warp its caster already had waiting.
    #: Unlike `extra_phases` it survives the turn boundary -- crossing it is what
    #: an extra turn is for. See `turn._begin_next_turn`.
    extra_turns: list[int] = field(default_factory=list)
    #: True while the current turn is an extra one. Read by the untap step, which
    #: says so on `TURN_BEGAN`; nothing in the rules asks, since an extra turn is
    #: a turn in every respect (500.7).
    extra_turn: bool = False
    #: The seat whose **ordinary** turn the table resumes after, while extra
    #: turns are being taken; `None` otherwise, when `active_idx` is that seat.
    #:
    #: An extra turn moves the active player without moving the turn order.
    #: Player 0 casts Perch Protection and player 1 takes the gift: the next
    #: ordinary turn is still the one after *player 0's*, which in a pod is not
    #: the seat after the player whose extra turn just ended.
    turn_order_idx: int | None = None
    #: The player whose turn most recently ended, or `None` before the first one
    #: has. Day and night (726.2) ask about "the previous turn's active player",
    #: which stopped being the seat to the right once turns could be extra.
    previous_active: int | None = None
    #: Set when cleanup performed an action and must repeat (rule 514.3a).
    cleanup_repeat: bool = False
    #: False until the current step's turn-based actions have been performed.
    step_started: bool = False
    started: bool = False

    # ------------------------------------------------------------------
    # lookups
    # ------------------------------------------------------------------

    def obj(self, oid: int) -> GameObject:
        return self.objects[oid]

    def card(self, oid: int) -> CardDef:
        """The :class:`CardDef` behind an object id -- the face it is showing.

        Delegates to :meth:`card_of` rather than reading `def_id` straight out
        of the registry, because the two must not be able to disagree about
        which card an object *is*. They did: `costs._sources_of` planned a mana
        payment through `card_of` and `costs.activate_mana_ability` executed it
        through here, so a modal DFC played as its land half was planned as a
        land and paid as an instant -- and `abilities[0]` on a card with no
        abilities is an IndexError, not a wrong answer.

        The same seam every other "one helper, two callers" note in this repo is
        about, and the same fix: one helper.
        """
        return self.card_of(self.objects[oid])

    def card_of(self, obj: GameObject) -> CardDef:
        """The face this object is currently showing.

        The one place transforming double-faced cards are implemented. Every
        other reader of a card -- the characteristics layers, legality, combat,
        the serializer -- goes through here, so a transformed permanent shows
        its back face everywhere at once and none of them needed changing.
        """
        # Mutate (702.140b): a merged permanent **is** the card on top, plus the
        # abilities of everything under it. Asked first and answered outright,
        # because it is not a face of the printed card at all -- it is a card
        # synthesised at merge time, and the printed `def_id` is only one of the
        # several cards in the pile.
        if obj.merged_card is not None:
            return obj.merged_card
        # An emblem (114) is not a face of the card that made it: it is one of
        # that card's `emblems`, a definition with abilities and nothing else.
        if obj.emblem is not None:
            return self.registry.get(obj.def_id).emblems[obj.emblem]
        # A copy effect (706) applied in place -- Gogo. Asked before the printed
        # card is even fetched, because while it is copying, the copied card
        # *is* what this permanent is: its name, types, power, abilities and
        # everything else follow from here, which is the whole reason this
        # method exists as the single funnel.
        if obj.copying is not None:
            copied = self.registry.get(obj.copying)
            if obj.copying_name is not None and obj.copying_name != copied.name:
                # "…except its name is Gogo, Mysterious Mime." A copy may
                # override individual characteristics (706.2), and the name is
                # the one this cycle overrides.
                copied = replace(copied, name=obj.copying_name)
            if obj.renamed_to is not None:
                copied = replace(copied, name=obj.renamed_to)
            return copied
        card = self.registry.get(obj.def_id)
        # "…become a legendary Equipment artifact **named Everflame, Heroes'
        # Legacy**" (The Irencrag). Here, for the reason the copy above is here:
        # this method is the single funnel every reader of a permanent's face
        # goes through, so a rename shows up in the characteristics layers, in
        # `selector.name`, in the legend rule and in the serializer at once.
        #
        # After the copy branch and applied to it as well, because a permanent
        # that is both copying something and renamed answers to the rename --
        # 706.2's override and this are the same kind of claim, and the later
        # effect wins.
        if obj.renamed_to is not None:
            card = replace(card, name=obj.renamed_to)
        # A second castable face -- adventure, aftermath, a split half -- is
        # asked first, because it is the face the card is *currently being cast
        # as* and that is a narrower window than being transformed. Nothing
        # prints both, and if anything did, the spell on the stack is the more
        # specific claim.
        if obj.showing_second_face and card.second_face is not None:
            return self.registry.get(card.second_face)
        if obj.transformed and card.back_face is not None:
            return self.registry.get(card.back_face)
        return card

    def player(self, pid: int) -> PlayerState:
        return self.players[pid]

    @property
    def num_players(self) -> int:
        return len(self.players)

    @property
    def phase(self) -> Phase:
        return STEP_PHASE[self.step]

    @property
    def active_player(self) -> int:
        return self.players[self.active_idx].pid

    @property
    def priority_player(self) -> int | None:
        return None if self.priority_idx is None else self.players[self.priority_idx].pid

    # ------------------------------------------------------------------
    # players and turn order
    # ------------------------------------------------------------------

    def alive(self) -> list[int]:
        """Player ids still in the game, in seat order."""
        return [p.pid for p in self.players if not p.has_lost]

    def is_alive(self, pid: int) -> bool:
        return not self.players[pid].has_lost

    def opponents(self, pid: int) -> list[int]:
        return [p for p in self.alive() if p != pid]

    def next_alive_index(self, idx: int) -> int:
        """The next seat clockwise that is still in the game."""
        n = self.num_players
        for offset in range(1, n + 1):
            candidate = (idx + offset) % n
            if not self.players[candidate].has_lost:
                return candidate
        return idx

    def turn_order(self, start_pid: int | None = None) -> list[int]:
        """Alive players in APNAP order starting from ``start_pid`` (default: active)."""
        start = self.active_idx if start_pid is None else start_pid
        n = self.num_players
        return [
            self.players[(start + i) % n].pid
            for i in range(n)
            if not self.players[(start + i) % n].has_lost
        ]

    # ------------------------------------------------------------------
    # zones
    # ------------------------------------------------------------------

    def zone_list(self, zone: Zone, pid: int | None = None) -> list[int]:
        """The ordered oid list backing a zone."""
        if zone is Zone.BATTLEFIELD:
            return self.battlefield
        if zone is Zone.STACK:
            return [it.oid for it in self.stack if it.oid is not None]
        if pid is None:
            raise ValueError(f"{zone} requires a player id")
        return self.players[pid].zone_list(zone)

    def battlefield_objects(self, controller: int | None = None) -> list[GameObject]:
        """Permanents in a stable order (battlefield list order = arrival order)."""
        out = []
        for oid in self.battlefield:
            o = self.objects.get(oid)
            if o is None:
                continue
            if controller is None or o.controller == controller:
                out.append(o)
        return out

    def creatures(self, controller: int | None = None) -> list[GameObject]:
        return [
            o
            for o in self.battlefield_objects(controller)
            if "Creature" in chars(self, o.oid).types
        ]

    # ------------------------------------------------------------------
    # stack
    # ------------------------------------------------------------------

    def stack_item(self, sid: int) -> StackItem | None:
        for item in self.stack:
            if item.sid == sid:
                return item
        return None

    @property
    def stack_empty(self) -> bool:
        return not self.stack

    # ------------------------------------------------------------------
    # ids, events and cache invalidation
    # ------------------------------------------------------------------

    def alloc_oid(self) -> int:
        oid = self.next_oid
        self.next_oid += 1
        return oid

    def alloc_timestamp(self) -> int:
        stamp = self.next_timestamp
        self.next_timestamp += 1
        return stamp

    def alloc_sid(self) -> int:
        sid = self.next_sid
        self.next_sid += 1
        return sid

    def emit(
        self,
        event_type: str,
        *,
        player: int | None = None,
        source: int | None = None,
        **data: Any,
    ) -> GameEvent:
        """Append an event to the log and return it.

        The caller is responsible for handing the event to the trigger bus; this
        method only records it.
        """
        event = GameEvent(
            type=event_type,
            turn=self.turn,
            step=int(self.step),
            player=player,
            source=source,
            data=data,
        )
        self.events.append(event)
        self._tally(event)
        return event

    def _tally(self, event: GameEvent) -> None:
        """Fold one event into :attr:`turn_ledger`.

        Every branch reads the event that was going to be logged anyway, so no
        emitter had to change and none can route around it.  It runs while the
        object the event is about is still in ``self.objects`` -- ``emit`` is
        called synchronously from inside the zone change, before anything is
        forgotten -- which is why the controller of a dead creature and the
        tokenhood of a card reaching a graveyard are both still askable here and
        neither needed adding to a payload.
        """

        ledger = self.turn_ledger
        data = event.data
        pid = event.player

        if event.type == EventType.DIES:
            if data.get("was_creature"):
                obj = self.objects.get(data.get("oid"))
                # The *controller*, not `event.player`, which is the owner:
                # a creature stolen with `gain_control` and then killed died
                # under the thief, and "a creature you controlled died" has to
                # agree with who was attacking with it a moment earlier.
                who = obj.controller if obj is not None else pid
                if who is not None:
                    ledger.creatures_died[who] = ledger.creatures_died.get(who, 0) + 1
        elif event.type == EventType.ATTACKERS_DECLARED:
            if pid is not None:
                # The oids come off the event payload, which `finish_attackers`
                # fills from the *locked-in* declaration -- after requirements
                # discharge and after banding -- rather than off `self.combat`,
                # which is `None` by the time either card that reads this back
                # resolves. Same argument every other branch here makes.
                #
                # `setdefault` first, so the player's entry exists even for a
                # payload that names no attackers: `TurnLedger.attacked` is
                # derived from the *keys*, and raid must not depend on a future
                # emitter remembering to list them.
                attacked = ledger.creatures_attacked.setdefault(pid, set())
                attacked.update(int(oid) for oid in data.get("attackers") or ())
        elif event.type == EventType.ATTACKS:
            # Angel of Destiny's "each player this creature attacked this turn".
            # Only an attack on a seat: one aimed at a planeswalker or a battle
            # names its controller as `defender` (that is who blocks), but the
            # creature attacked the permanent, not the player (506.2).
            attacker, defender = data.get("attacker"), data.get("defender")
            if attacker is not None and defender is not None and not data.get("attacked_permanent"):
                ledger.players_attacked_by.setdefault(int(attacker), set()).add(int(defender))
        elif event.type == EventType.ENTERS_BATTLEFIELD:
            # "…if another Human entered the battlefield under your control this
            # turn." Snapshotted here rather than counted, because the question
            # is *which* permanents entered and the answer has to survive them
            # leaving: `chars` reads printed characteristics off a card in a
            # graveyard and cannot be asked at all about a token, which the
            # token state-based action pops out of `self.objects`.
            #
            # Derived characteristics, read while the permanent is on the
            # battlefield -- `_enter_battlefield` has already applied its
            # replacements and called `bump_chars`, and fires this event before
            # anything else can move it. Same moment and same argument as
            # `combat_damage_types` below.
            obj = self.objects.get(data.get("oid"))
            if obj is not None:
                c = chars(self, obj.oid)
                ledger.permanents_entered.append(
                    EnteredPermanent(
                        oid=obj.oid,
                        # Controller *at entry*: "under your control" is a fact
                        # about the arrival, and a permanent stolen afterwards
                        # must not retroactively have entered under the thief.
                        controller=obj.controller,
                        types=frozenset(c.types),
                        subtypes=frozenset(c.subtypes),
                        colors=frozenset(c.colors),
                        batch=int(data.get("batch", -1)),
                    )
                )
                # The ledger is now a *static* magnitude too -- Kinbinding's
                # "+X/+X, where X is the number of creatures that entered the
                # battlefield under your control this turn". `_enter_battlefield`
                # bumped the cache a moment ago, before this entry existed, so
                # the arriving permanent would read the anthem one short of what
                # its own arrival made it: every other permanent on the board
                # correct and the new one stale, which is the hardest kind of
                # wrong number to see.
                self.bump_chars()
        elif event.type == EventType.DAMAGE_DEALT:
            # Two shapes share this event, and they say which they are: `to` is
            # "player" or "permanent".  Only the first is life loss, and on the
            # second `player` is the *controller of the creature that was hit*,
            # so counting it would charge a player for their own bear taking a
            # Shock.
            if data.get("to") == "player" and pid is not None:
                amount = int(data.get("amount") or 0)
                ledger.damage_taken[pid] = ledger.damage_taken.get(pid, 0) + amount
                # `life_lost` is *not* added here any more. `damage_player` now
                # fires LIFE_LOST itself, so folding it from both events would
                # count every burn spell twice -- and doing it only here was
                # already wrong for infect, which deals damage to a player and
                # costs them no life at all.
        elif event.type == EventType.COMBAT_DAMAGE_TO_PLAYER:
            # Prowl. Recorded here rather than at the primitive for the reason
            # every other tally is, and read off *derived* subtypes while the
            # creature is still on the battlefield -- by the time a prowl spell
            # is cast the attacker may be dead, bounced, or no longer a Faerie.
            attacker = data.get("source") or event.source
            if attacker is not None and attacker in self.objects:
                ledger.combat_damage_types.update(chars(self, attacker).subtypes)
        elif event.type == EventType.LIFE_LOST:
            if pid is not None:
                amount = int(data.get("amount") or 0)
                ledger.life_lost[pid] = ledger.life_lost.get(pid, 0) + amount
        elif event.type == EventType.LIFE_GAINED:
            # Witch of the Moors. Off the event rather than in `gain_life`, for
            # the reason every other tally here is: lifelink and the op both
            # fire it, and a gain that was forbidden or locked fires nothing.
            if pid is not None:
                amount = int(data.get("amount") or 0)
                ledger.life_gained[pid] = ledger.life_gained.get(pid, 0) + amount
        elif event.type == EventType.SPELL_CAST:
            if pid is not None:
                ledger.spells_cast[pid] = ledger.spells_cast.get(pid, 0) + 1
                # And what it was, for the conditions that ask about types
                # rather than about a count. `card` is the face that was cast.
                if (cast_id := data.get("card")) is not None:
                    ledger.spells_cast_ids.setdefault(pid, []).append(str(cast_id))
                    # The same fact with no turn boundary on it, for "…this
                    # game". Written beside the per-turn list rather than in a
                    # second fold, so the two cannot disagree about what counted
                    # as a cast.
                    self.spells_cast_this_game.setdefault(pid, []).append(str(cast_id))
                # "Whenever an opponent casts their **second** spell each turn."
                # The ordinal is a fact about this cast, so it goes on the event
                # -- the one thing a trigger reads at queue time and never again
                # -- exactly as `draw_cards` writes `nth` on a DRAW. Written here
                # rather than at the three places that fire SPELL_CAST (a normal
                # cast, an alternative-cost cast, suspend's free cast) because
                # this fold is the one place all of them pass through, and a cast
                # path that forgot it would be a trigger that silently never
                # fires. The ids list above is the same length at this moment, so
                # `spells_cast_ids[pid][:nth]` is the run up to and including
                # this spell however many are cast before a trigger reads it.
                data["nth"] = ledger.spells_cast[pid]
        elif event.type == EventType.ZONE_CHANGE:
            obj = self.objects.get(data.get("oid"))
            # 400.7: the oid survives a zone change and the object does not. A
            # creature that left the battlefield and came back attacked nobody
            # this turn, so the record of whom it attacked goes with it.
            if data.get("from") == Zone.BATTLEFIELD.value:
                ledger.players_attacked_by.pop(data.get("oid"), None)
            if data.get("to") == Zone.GRAVEYARD.value and obj is not None and not obj.is_token:
                ledger.cards_to_graveyard += 1
            # The departure half. Keyed by the graveyard's **owner** rather than
            # by whoever moved the card: "a card left *your* graveyard" is a
            # fact about the yard, and a Reanimate cast by an opponent on your
            # creature still emptied your graveyard by one.
            if (
                data.get("from") == Zone.GRAVEYARD.value
                and data.get("to") != Zone.GRAVEYARD.value
                and obj is not None
                and not obj.is_token
                and pid is not None
            ):
                ledger.cards_from_graveyard[pid] = (
                    ledger.cards_from_graveyard.get(pid, 0) + 1
                )

    def bump_chars(self) -> None:
        """Invalidate the derived-characteristics cache."""
        self.char_version += 1

    # ------------------------------------------------------------------
    # misc
    # ------------------------------------------------------------------

    def empty_all_mana_pools(self, keep_for_turn: int | None = None) -> None:
        """Empty every pool, sparing mana that says it survives this turn.

        ``keep_for_turn`` is the current turn at an ordinary step or phase
        boundary and ``None`` at the end of the turn, which is where "until end
        of turn" runs out.
        """
        for p in self.players:
            lost = p.mana_pool.clear(keep_for_turn)
            if lost:
                self.emit("mana_emptied", player=p.pid, amount=lost)

    def commanders_of(self, pid: int) -> list[int]:
        return list(self.players[pid].commanders)

    def describe(self) -> str:  # pragma: no cover - debug helper
        bits = [f"T{self.turn} {self.step.name} AP=p{self.active_player}"]
        for p in self.players:
            tag = "OUT" if p.has_lost else f"{p.life}life"
            bits.append(f"p{p.pid}:{tag} h={len(p.hand)} bf={len(self.battlefield_objects(p.pid))}")
        if self.stack:
            bits.append(f"stack={len(self.stack)}")
        return " | ".join(bits)


def new_object(
    state: GameState,
    def_id: str,
    owner: int,
    zone: Zone,
    *,
    controller: int | None = None,
    is_token: bool = False,
    is_commander: bool = False,
) -> GameObject:
    """Create a game object and register it (without placing it in a zone list)."""
    obj = GameObject(
        oid=state.alloc_oid(),
        def_id=def_id,
        owner=owner,
        controller=owner if controller is None else controller,
        zone=zone,
        is_token=is_token,
        is_commander=is_commander,
    )
    state.objects[obj.oid] = obj
    return obj
