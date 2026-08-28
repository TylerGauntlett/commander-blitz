/**
 * Turning the server's event log into playable animation beats.
 *
 * One HTTP response can carry three opponents' entire turns, because
 * `GameSession.drive_ai` runs every AI seat until a human must decide. The
 * state therefore *snaps*, and nothing about it is watchable. This module
 * converts that flat log into a timed queue -- floating numerals, spotlights,
 * banners, departing cards -- which the narration layer plays over the top of
 * the new state.
 *
 * "Over the top of the new state" is why `exits` carries as much as it does.
 * Every other beat anchors to something the board is still drawing; a card that
 * has just been destroyed is by definition one the board has stopped drawing,
 * so the beat has to name it well enough to be reconstructed from nothing.
 *
 * Pure: no timers, no React. The queue is data; `state/narration.ts` runs it.
 */

import type { GameEvent } from "../api/types";
import type { SoundName } from "../audio/sfx";
import type { PresetName } from "../fx/presets";
import { planCombat } from "./choreography";
import { type NameLookup, describeEvent, exitPhrase, prettyCardName } from "./labels";

export type { NameLookup };

export type BeatAnchor = { kind: "player"; pid: number } | { kind: "object"; oid: number };

/**
 * Where on the board an effect goes.
 *
 * `between` is the one that earns its keep: a collision does not happen at the
 * attacker and it does not happen at the blocker, it happens at the point they
 * meet. Resolving that in the FX layer rather than in the choreography means
 * the contact point is measured from where the cards actually are when the
 * beat plays, which is the only place it is knowable -- both of them may still
 * be mid-flight from a layout animation.
 */
export type FxPoint =
  | BeatAnchor
  | { kind: "between"; a: BeatAnchor; b: BeatAnchor; t?: number };

export type Tone = "neutral" | "damage" | "gain" | "loss" | "danger" | "good";

/**
 * One effect, scheduled inside a beat.
 *
 * This is the field that lets the board get more physical without getting
 * slower. A combat exchange used to be nine consecutive beats, each holding the
 * board for its own `hold` -- 3.3 seconds of slideshow for three attackers. The
 * same exchange is now *one* beat whose effects are stamped with offsets and
 * fire concurrently: everything lunges at 0ms, everything connects at 140ms,
 * everything recoils at 260ms. Denser, and a third of the wall clock.
 *
 * `at` is relative to the start of the beat and is *not* bounded by its `hold`.
 * Effects deliberately outlive the queue -- a burst thrown at 260ms is still
 * settling while the next beat plays, which is what makes a turn read as
 * continuous rather than as a sequence of slides.
 */
export type TimedFx = { at: number } & (
  | { kind: "emit"; preset: PresetName; at_point: FxPoint; angle?: number; scale?: number }
  | {
      kind: "actuate";
      oid: number;
      move: "lunge" | "recoil" | "shudder" | "pulse";
      toward?: FxPoint;
      power?: number;
    }
  | { kind: "float"; at_point: FxPoint; value: string; tone: Tone }
  | { kind: "flash"; at_point: FxPoint; tone: Tone }
  | { kind: "shake"; power: number }
  | { kind: "vignette"; pid: number; tone: Tone }
  | { kind: "sound"; sound: SoundName }
);

/**
 * One permanent leaving the battlefield, with everything needed to draw it.
 *
 * Carries the *identity* of the card rather than the card itself: the FX layer
 * resolves a face when the beat plays, by which point the card is in the
 * destination zone -- or, for a token, nowhere at all.
 */
export interface ExitFx {
  oid: number;
  /** The definition id, for the token fallback. See `FxLayer`. */
  cardId: string;
  name: string;
  /** Whose pile it lands in. `zone_change` reports the owner as `player`. */
  owner: number;
  /**
   * The destination the engine actually used, never one inferred from `cause`:
   * rule 903.9a sends a *destroyed commander* to the command zone.
   */
  to: string;
  cause: string;
  /** Ready-made prose, so the layer that draws it owns no words. */
  caption: string;
}

export interface Beat {
  id: string;
  /** Milliseconds to hold after showing this beat, before the next one. */
  hold: number;
  /** Play-by-play line, or null to leave the ticker alone. */
  text: string | null;
  /** A number that floats up off a player or a permanent. */
  float?: { anchor: BeatAnchor; value: string; tone: Tone };
  /**
   * A card thrown up in the middle of the screen while it is being cast, or an
   * ability announced as it goes on the stack. `kind` lets the two read
   * differently: a trigger is something happening *to* you and is not a card
   * leaving anyone's hand.
   */
  spotlight?: {
    cardId: string;
    name: string;
    controller: number;
    kind?: "spell" | "trigger";
  };
  /** A brief highlight ring on a permanent. */
  flash?: { anchor: BeatAnchor; tone: Tone };
  /**
   * Permanents leaving the battlefield, drawn as cards flying into their pile.
   *
   * Plural, and that is the point: a wrath emits one `zone_change` per
   * permanent, and a beat each would hold the board for six seconds. A run of
   * them collapses into one beat and the FX layer staggers the ghosts inside
   * it, which is what that layer says it exists for.
   */
  exits?: ExitFx[];
  /** A full-width sweep: turn changes, eliminations. */
  banner?: { text: string; tone: Tone };
  /** 0..1 screen shake intensity. */
  shake?: number;
  /**
   * Effects scheduled within this beat, played concurrently on their own
   * offsets. See `TimedFx` -- this is what a combat exchange is made of.
   */
  fx?: TimedFx[];
  /**
   * A sound to play with this beat.
   *
   * Named here rather than chosen by the effects layer so the mapping stays in
   * the pure module with the rest of the beat's meaning -- and so it is
   * testable without a Web Audio context. Only `FxLayer` ever plays it.
   */
  sound?: SoundName;
}

function nameOf(event: GameEvent, lookup?: NameLookup): string | null {
  const cardId = typeof event.data.card === "string" ? event.data.card : null;
  if (!cardId) return null;
  return lookup?.(cardId) ?? prettyCardName(cardId);
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/**
 * Events that are bookkeeping rather than drama.
 *
 * `combat_damage_to_player` is skipped because `damage_player` fires
 * `damage_dealt` first for the very same hit -- animating both would double
 * every combat numeral.
 */
const SILENT = new Set([
  "combat_damage_to_player",
  "step_ended",
  "step_began",
  // `mana_added` fires per source during auto-payment and `tapped` already
  // flashes the same permanent -- narrating both would double every land.
  "mana_added",
  "mana_emptied",
  // `zone_change` now owns every departure -- it knows the destination *and*
  // the cause, and `move_object` emits it alongside both of these for the same
  // card. Leaving `dies` audible would toll twice for one creature and flash an
  // oid that is no longer in the DOM, which is what it did for its whole life.
  "dies",
  // Fired *beside* `dies` for the very same card, so that a trigger can tell a
  // sacrifice from a removal spell. Narrating it would toll a third time for
  // one creature, on top of the `zone_change` that already owns the departure.
  "sacrificed",
  "leaves_battlefield",
  // The graveyard's counterpart, and silent for the identical reason: fired
  // beside the `zone_change` that already owns the departure, for the very same
  // card, so that "whenever one or more cards leave your graveyard" has
  // something to hear. A beat here would toll a second time for one card and
  // flash an oid that has already left the graveyard pile in the DOM.
  "leaves_graveyard",
  "untapped",
  "ability_resolved",
  // Fired beside `attackers_declared` for the very same declaration -- one per
  // defending seat, so a batch attack trigger can be told which seat. The
  // declaration already owns the "Attack!" banner and the surge, so a beat here
  // would sound it again once per opponent swung at; and being *silent* is also
  // what keeps it from closing the declaration run in `planCombat`, which would
  // split one swing into two animations.
  "creatures_attacked_player",
  // The same arrangement one phase later: fired beside the per-creature
  // `combat_damage_to_player` above -- itself already silent here -- for the
  // very same hits, so a delayed "whenever one or more creatures you control
  // deal combat damage to one or more players this turn" can be told the whole
  // batch at once. `damage_dealt` owns the numeral for each hit; a beat for the
  // summary would sound the combat a second time.
  "creatures_dealt_combat_damage",
]);

/**
 * A battlefield departure, or null for any other zone change.
 *
 * The guard is doing two jobs. Anything that did not start on the battlefield
 * has no ghost to draw -- there is no card on screen to fly anywhere. And a
 * zone change out of a *library* carries a card id to every seat, so animating
 * one would show the table an opponent's tutor target.
 */
function exitFor(event: GameEvent, lookup?: NameLookup): ExitFx | null {
  if (event.type !== "zone_change" || event.data.from !== "battlefield") return null;
  const oid = typeof event.data.oid === "number" ? event.data.oid : null;
  const cardId = typeof event.data.card === "string" ? event.data.card : "";
  if (oid === null) return null;
  const cause = typeof event.data.cause === "string" ? event.data.cause : "";
  const to = typeof event.data.to === "string" ? event.data.to : "graveyard";
  const byId = typeof event.data.by_card === "string" ? event.data.by_card : null;
  const by = byId ? (lookup?.(byId) ?? prettyCardName(byId)) : null;
  return {
    oid,
    cardId,
    name: cardId ? (lookup?.(cardId) ?? prettyCardName(cardId)) : "A permanent",
    owner: event.player ?? 0,
    to,
    cause,
    caption: exitPhrase(cause, by, to),
  };
}

/** Destinations worth a funeral toll. A bounced creature is not one. */
const SOLEMN_ZONES = new Set(["graveyard", "exile"]);

/**
 * Group each *consecutive run* of departures onto its leading event.
 *
 * Consecutive, not global: "a creature dies, a trigger resolves, another
 * creature dies" is two moments and collapsing them would put the second death
 * on screen before the trigger that caused it. A run survives intervening
 * events that produce no beat of their own -- which is what lets a wrath, whose
 * every death also fires a silent `dies` and `leaves_battlefield`, still read as
 * one sweep.
 */
function groupExits(
  events: GameEvent[],
  lookup?: NameLookup,
): { leaders: Map<number, ExitFx[]>; absorbed: Set<number> } {
  const leaders = new Map<number, ExitFx[]>();
  const absorbed = new Set<number>();
  let openRun: number | null = null;

  events.forEach((event, index) => {
    const exit = exitFor(event, lookup);
    if (exit) {
      if (openRun === null) {
        openRun = index;
        leaders.set(index, [exit]);
      } else {
        leaders.get(openRun)?.push(exit);
        absorbed.add(index);
      }
      return;
    }
    // Only something that would itself be narrated closes a run.
    if (!SILENT.has(event.type)) openRun = null;
  });

  return { leaders, absorbed };
}

/**
 * How long the board holds while a run of departures plays.
 *
 * Deliberately sublinear. Ten deaths at a readable single-death pace would stall
 * the turn for six seconds; the ghosts are staggered inside the FX layer
 * instead, and keep flying after the queue has moved on -- floats already work
 * exactly this way.
 */
function exitHold(count: number): number {
  return Math.min(820, 420 + (count - 1) * 100);
}

/**
 * A permanent hitting the table.
 *
 * Dust under the card and a short squash, so an arrival has some mass to it.
 * Nothing here adds to the beat's `hold` -- both effects outlive it, exactly as
 * a floating numeral does, so the board gets heavier without getting slower.
 */
function arrival(source: number | null): TimedFx[] {
  if (source === null) return [];
  return [
    { at: 0, kind: "emit", preset: "dust", at_point: { kind: "object", oid: source } },
    { at: 0, kind: "actuate", oid: source, move: "pulse", power: 0.8 },
    /*
     * A permanent hitting the table is the single most frequent thing that
     * happens in a game of Magic, and until now it made no sound and threw no
     * light -- a puff of dust and a scale pulse, both of which are easy to miss
     * on a busy board and impossible to notice if you happened to be reading
     * your hand.
     *
     * `thump` already exists for exactly this ("a card landing on the table:
     * low, dull, over immediately") and was never wired to an arrival. The
     * flash is the same beat in the visual channel, for a player with sound off
     * -- which on a handheld is most of them.
     */
    { at: 0, kind: "sound", sound: "thump" },
    { at: 20, kind: "flash", at_point: { kind: "object", oid: source }, tone: "neutral" },
  ];
}

/**
 * Build the beat queue for one batch of events.
 *
 * `names[pid]` are the player names; `lookup` resolves a card id such as
 * `"sol_ring"` to its printed name, falling back to a prettified id.
 * `viewerSeat` is for verb agreement in the prose -- see `describeEvent`.
 *
 * This module owns *timing, sound and effects*. It used to own words as well,
 * in a switch that ran parallel to `describeEvent` over the same event types --
 * which is how triggers ended up missing from both at once, and why payment
 * narrated "You pays {2}{G}". `push` now fills `text` from the one shared
 * switch, so a new event kind gets its line in exactly one place.
 */
export function beatsFor(
  events: GameEvent[],
  names: string[],
  lookup?: NameLookup,
  viewerSeat?: number,
): Beat[] {
  const beats: Beat[] = [];
  const { leaders, absorbed } = groupExits(events, lookup);
  // Combat is collapsed the same way departures are, and for the same reason:
  // the interesting unit is the exchange, not the individual hit. See
  // `logic/choreography.ts` -- this is what turned a 3.3-second slideshow into
  // one motion.
  const combat = planCombat(events, (type) => SILENT.has(type), viewerSeat);

  events.forEach((event, index) => {
    if (SILENT.has(event.type)) return;
    // Folded into the run its leader carries.
    if (absorbed.has(index)) return;
    if (combat.absorbed.has(index)) return;

    const id = `${index}-${event.type}`;
    const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
    const card = nameOf(event, lookup);
    const amount = num(event.data.amount);
    const text = describeEvent(event, names, viewerSeat, lookup);
    const push = (beat: Omit<Beat, "id" | "text">, override?: string | null) =>
      beats.push({ id, text: override === undefined ? text : override, ...beat });

    /*
     * A combat run replaces every beat its events would have produced.
     *
     * The prose is still `describeEvent`'s: a declaration says who is swinging,
     * and the strike stays wordless because the ticker already lists every hit
     * and a beat-level line would repeat it.
     */
    const exchange = combat.leaders.get(index);
    if (exchange) {
      beats.push({ ...exchange, text: combat.wordless.has(index) ? null : text });
      return;
    }

    /** A flash on whatever this event came from, or nothing to flash. */
    const onSource = (tone: Tone) =>
      event.source === null
        ? undefined
        : ({ anchor: { kind: "object", oid: event.source }, tone } as const);

    const exits = leaders.get(index);
    if (exits) {
      const solemn = exits.some((exit) => SOLEMN_ZONES.has(exit.to));
      push(
        {
          hold: exitHold(exits.length),
          exits,
          sound: solemn ? "toll" : undefined,
          // A wrath is a big enough moment to feel; a single death is not.
          shake: exits.length >= 4 ? Math.min(0.7, exits.length / 10) : undefined,
        },
        // The ticker lists every departure independently, so the beat only
        // needs the headline. Past a pair, naming one of them would be odd.
        exits.length > 2 ? `${exits.length} permanents leave the battlefield` : text,
      );
      return;
    }

    switch (event.type) {
      case "turn_began":
        push({
          hold: 620,
          banner: {
            text: event.player === viewerSeat ? "Your Turn" : `${who}'s Turn`,
            tone: "neutral",
          },
        });
        return;

      case "spell_cast":
        push({
          hold: 520,
          sound: "chime",
          spotlight: {
            cardId: typeof event.data.card === "string" ? event.data.card : "",
            name: card ?? "a spell",
            controller: event.player ?? 0,
          },
        });
        return;

      case "spell_resolved":
        push({ hold: 180 });
        return;

      case "spell_countered":
        push({
          hold: 650,
          banner: { text: "Countered", tone: "danger" },
        });
        return;

      case "spell_fizzled":
        push({
          hold: 650,
          banner: { text: "Fizzled", tone: "danger" },
        });
        return;

      /*
       * Something arriving on the battlefield.
       *
       * All three used to be a ring flash and nothing else -- a permanent
       * landed by fading a circle over itself, which reads as a highlight
       * rather than as weight. They now land: a puff of dust under the card and
       * a small squash, on top of the flash the tests already assert.
       */
      case "land_played":
        push({
          hold: 260,
          sound: "thump",
          flash: onSource("neutral"),
          fx: arrival(event.source),
        });
        return;

      case "enters_battlefield":
        push({
          hold: 220,
          sound: "thump",
          flash: onSource("good"),
          fx: arrival(event.source),
        });
        return;

      case "token_created":
        push({
          hold: 200,
          flash: onSource("good"),
          fx: arrival(event.source),
        });
        return;

      /*
       * Dice (rule 705.1). Anchored to the permanent that rolled and floating
       * the faces themselves, because the beats that follow are the payoff --
       * a Treasure per even result -- and a player who did not see what came up
       * cannot tell whether the number of them is right.
       *
       * Held longer than a token arrival: the tokens land immediately after, and
       * the two running together is exactly what hides the roll. No beat when
       * the source is gone, which is the same guard every anchored beat carries.
       */
      case "dice_rolled": {
        if (event.source === null) return;
        const results = Array.isArray(event.data.results) ? event.data.results : [];
        const anchor = { kind: "object", oid: event.source } as const;
        push({
          hold: 420,
          sound: "chime",
          float: { anchor, value: results.join(" "), tone: "good" },
          fx: [{ at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 }],
        });
        return;
      }

      // Both of these change what a card *is* without moving it, so the frame
      // redraws in place. Held longer than an ETB so the change reads as a play
      // rather than as a rendering glitch.
      case "transformed":
      case "control_changed":
        push({
          hold: 480,
          sound: "chime",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      /*
       * Damage has no case here any more.
       *
       * Every `damage_dealt` -- combat or not -- is collected by `planCombat`
       * into a run and animated as one concurrent burst, so an event that
       * reaches this switch is one that produced no hit at all: zero damage, or
       * a form with no anchor to put a numeral on. Both are correctly silent.
       */

      /*
       * A fog landing. The counterpart of the note just above: `planCombat`
       * collects the hits, and a prevented swing produces no hit for it to
       * collect, so without a beat here the attack simply plays out and nothing
       * moves. That silence is fine for absorb -- the reduced damage still
       * animates -- and is not fine for a shield over a player, which is the
       * whole of the turn.
       *
       * Scoped to the player shape for the reason `describeEvent` scopes its
       * line: the permanent shape has no anchor this can put a numeral on
       * without first resolving an `oid` the payload does not promise.
       */
      case "damage_prevented":
        if (amount === null || amount <= 0 || event.data.to !== "player") return;
        push({
          hold: 280,
          float: {
            anchor: { kind: "player", pid: event.player ?? 0 },
            value: `${amount} prevented`,
            tone: "good",
          },
        });
        return;

      case "life_gained":
        if (amount === null) return;
        push({
          hold: 280,
          float: {
            anchor: { kind: "player", pid: event.player ?? 0 },
            value: `+${amount}`,
            tone: "gain",
          },
        });
        return;

      case "life_lost":
        if (amount === null) return;
        push({
          hold: 280,
          float: {
            anchor: { kind: "player", pid: event.player ?? 0 },
            value: `-${amount}`,
            tone: "loss",
          },
        });
        return;

      /*
       * A combat trick landing.
       *
       * The engine used to change a creature's power in complete silence --
       * `pump` mutated `until_eot` and called `bump_chars()` and that was all --
       * so a creature would survive lethal damage for no reason the board ever
       * gave. It now says so: the numbers swell off the card, and the card
       * itself takes a pulse so the eye is pointed at the right creature before
       * the damage arrives.
       */
      case "stats_changed": {
        if (event.source === null) return;
        const power = num(event.data.power);
        const toughness = num(event.data.toughness);
        const keyword = typeof event.data.keyword === "string" ? event.data.keyword : null;
        const anchor = { kind: "object", oid: event.source } as const;
        const value = keyword
          ? keyword
          : `${power !== null && power >= 0 ? "+" : ""}${power ?? 0}/${
              toughness !== null && toughness >= 0 ? "+" : ""
            }${toughness ?? 0}`;
        push({
          hold: 200,
          fx: [
            { at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 },
            { at: 0, kind: "emit", preset: "motes", at_point: anchor },
            { at: 0, kind: "float", at_point: anchor, value, tone: "good" },
          ],
        });
        return;
      }

      case "counter_placed": {
        const kind = typeof event.data.counter === "string" ? event.data.counter : "counter";
        push({
          hold: 220,
          float:
            event.source === null
              ? undefined
              : {
                  anchor: { kind: "object", oid: event.source },
                  value: `+${amount ?? 1} ${kind}`,
                  tone: "good",
                },
        });
        return;
      }

      /*
       * A Saga reaching a chapter.
       *
       * A board moment rather than a table one -- there is a permanent, and it is
       * the permanent the player wants their eye drawn to -- so it floats off the
       * Saga rather than taking a banner. The `counter_placed` beat fires beside
       * it and floats "+1 lore", which is the bookkeeping; this is the chapter,
       * and the two read as one gesture on the same card.
       *
       * Worth a beat because a Saga's whole clock is invisible otherwise. Nothing
       * on the board changes when a chapter *triggers*: the ability goes on the
       * stack and its consequences arrive later, so without this the tokens simply
       * appear a moment afterwards with nothing having announced them. And the
       * chapter that ends the story is followed by the Saga going to the graveyard
       * for no reason a viewer can see.
       */
      case "chapter_reached": {
        if (event.source === null) return;
        const n = num(event.data.chapter) ?? 0;
        const roman = ["I", "II", "III", "IV"][n - 1] ?? String(n);
        const anchor = { kind: "object", oid: event.source } as const;
        push({
          hold: 320,
          sound: "chime",
          float: { anchor, value: roman, tone: "good" },
          fx: [{ at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 }],
        });
        return;
      }

      /*
       * The crown changing hands, which is a table-level moment and not a board
       * one: no permanent to flash, no number to float, nothing on screen that
       * changed. A banner is the only shape that fits, and it is the same shape
       * the other two table-level moments use -- the turn change and an
       * elimination.
       *
       * Worth a beat at all because the consequence is invisible: the monarch
       * draws at every one of their end steps, and the usual way it moves is a
       * creature connecting, so without this the player who just lost it sees
       * only their opponent quietly drawing more cards. Held about as long as a
       * transform, and toned "good" or "danger" from the viewer's side, since
       * gaining and losing the crown are the same event told two ways.
       */
      case "became_monarch": {
        const mine = event.player === viewerSeat;
        push({
          hold: 520,
          sound: "chime",
          banner: {
            text: mine ? "You are the monarch" : `${who} is the monarch`,
            tone: mine ? "good" : "danger",
          },
        });
        return;
      }

      case "attackers_declared":
        push({
          hold: 520,
          sound: "hit",
          banner: { text: "Attack!", tone: "damage" },
        });
        return;

      case "blockers_declared":
        push({ hold: 420 });
        return;

      case "draw":
        push({ hold: 90, sound: "shuffle" });
        return;

      case "discard":
        push({ hold: 200 });
        return;

      /*
       * Cycling reads as one action even though it is a discard, a draw and
       * often a trigger. A slightly longer hold than a plain discard, because
       * what usually follows it is a trigger going on the stack and the two
       * running together is what makes "(Do this before you draw)" invisible.
       */
      case "cycled":
        push({ hold: 260 });
        return;

      case "mill":
        push({ hold: 200 });
        return;

      /*
       * Triggers get the same spotlight a cast gets.
       *
       * In Commander triggers are most of what happens, and a trigger going on
       * the stack is the moment the player most needs to notice -- it used to
       * be a 300ms pause with nothing on screen at all, since the text this
       * beat carried was never rendered and the ticker had no case for it.
       */
      case "ability_triggered":
        push({
          hold: 460,
          sound: "chime",
          spotlight: {
            cardId: typeof event.data.card === "string" ? event.data.card : "",
            name: card ?? "An ability",
            controller: event.player ?? 0,
            kind: "trigger",
          },
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "good" },
        });
        return;

      /*
       * A copy going on the stack. Short, because storm puts several up at
       * once and a full cast-length beat each would stall the turn -- but not
       * silent, since a copy is the difference between one bolt and nine.
       */
      case "spell_copied":
        push({ hold: 120, sound: "chime" });
        return;

      case "ability_activated":
        push({
          hold: 320,
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      /*
       * Targeting, which is where ward happens.
       *
       * The flash is on the permanent being *targeted*, not on the spell doing
       * it, and the tone is "danger" because from the board's point of view
       * this is a thing being aimed at. It matters more than a normal beat: ward
       * raises a payment prompt off this event, so without a flash the dialog
       * arrives with nothing on screen saying which creature it is about.
       */
      case "became_target": {
        const oid = typeof event.data.oid === "number" ? event.data.oid : null;
        if (oid === null) return; // the player-target form; the cast beat covers it
        push({
          hold: 300,
          flash: { anchor: { kind: "object", oid }, tone: "danger" },
        });
        return;
      }

      /*
       * The outcome of the block declaration, per attacker. Short holds: these
       * fire in a batch, one per attacker, immediately after the per-blocker
       * `blocks` beats, and a full-length hold each would stall the step on a
       * wide board. The tones are from the attacking player's point of view --
       * getting through is good, being blocked is not.
       */
      case "became_blocked":
      case "attacked_unblocked": {
        const oid = typeof event.data.oid === "number" ? event.data.oid : null;
        push({
          hold: 160,
          flash:
            oid === null
              ? undefined
              : {
                  anchor: { kind: "object", oid },
                  tone: event.type === "became_blocked" ? "danger" : "good",
                },
        });
        return;
      }

      /*
       * Mana payment, which used to be entirely invisible: lands tapped during
       * auto-payment with no indication of what was spent. `tapped` flashes the
       * specific permanent that paid; `mana_spent` names the total.
       */
      case "tapped":
        push({
          hold: 70,
          sound: "tap",
          flash:
            event.source === null
              ? undefined
              : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
        });
        return;

      case "mana_spent":
        push({ hold: 120 });
        return;

      case "mulligan_taken":
        push({ hold: 200 });
        return;

      case "hand_kept":
        push({ hold: 200 });
        return;

      case "player_lost":
        push({
          hold: 1100,
          sound: "toll",
          banner: { text: `${who} is eliminated`, tone: "danger" },
          shake: 0.6,
        });
        return;

      case "game_over":
        push({ hold: 400 });
        return;

      default:
        return;
    }
  });

  return beats;
}

/** Total wall-clock time a queue will take at a given speed multiplier. */
export function queueDuration(beats: Beat[], speed: number): number {
  return beats.reduce((total, beat) => total + beat.hold / speed, 0);
}
