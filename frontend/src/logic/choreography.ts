/**
 * Combat, as one motion instead of nine slides.
 *
 * ## What was wrong
 *
 * `beatsFor` used to give every combat event its own beat, and the queue plays
 * beats one at a time. A three-attacker swing was therefore: a 520ms "Attack!"
 * banner, three 160ms flashes, a 420ms pause, then a 340ms numeral per hit --
 * nine consecutive holds, 3.3 seconds, during which the board was frozen and
 * uninteractable and *nothing moved*. The creatures involved sat perfectly
 * still the entire time. Combat was an arrow, a word, and some arithmetic.
 *
 * ## What replaces it
 *
 * Two beats, whose contents are stamped with offsets and play concurrently:
 *
 *   **Declare** -- every attacker surges forward toward the player it is
 *   attacking, staggered a few frames apart so a wide board reads as a line
 *   advancing rather than a single lurch.
 *
 *   **Strike** -- everything lunges at once, everything connects at once.
 *   Sparks at each point of contact, numerals thrown off those same points
 *   rather than off the cards, defenders knocked backwards, the screen kicked
 *   in proportion to what got through.
 *
 * Together they are about a third of the wall clock the nine beats cost. That
 * is the whole design: the way to make a board feel like more is happening is
 * to stop making the moments queue up behind each other.
 *
 * ## Pairing needs no engine change
 *
 * Every combat `damage_dealt` already carries `source` (the creature dealing
 * it) and either `oid` (the permanent taking it) or `to: "player"`. That *is*
 * the pairing -- there is no need to reconstruct it from `state.combat`, and no
 * need for the engine to emit anything new. `attacks` tells us which side of
 * each pair is the attacker, which is the only other thing the choreography
 * wants to know.
 *
 * Pure, like `events.ts`: no timers, no DOM, no React. Positions are resolved
 * by `FxLayer` when the beat plays, because both cards may still be mid-flight
 * from a layout animation and there is no earlier moment at which the point
 * where they meet is knowable.
 */

import type { GameEvent } from "../api/types";
import type { Beat, BeatAnchor, FxPoint, TimedFx } from "./beats/types";

/** Events that make up the declaration half of a combat step. */
const DECLARE = new Set([
  "attackers_declared",
  "attacks",
  "blockers_declared",
  "blocks",
  "became_blocked",
  "attacked_unblocked",
]);

/**
 * When contact happens, relative to the start of the strike beat.
 *
 * The lunge curve in `fx/actuators.ts` reaches full extension at 32% of its
 * 340ms and holds there until 46%. 140ms lands inside that window, so the
 * sparks appear at the moment the cards are actually touching rather than
 * before they have set off or after they have started back.
 */
const CONTACT = 140;

/** How far apart consecutive attackers set off, so a wide board reads as a line. */
const STAGGER = 45;

/** The declaration beat's hold. Was 520 + 160/attacker + 420. */
const DECLARE_HOLD = 420;
/** The strike beat's hold. Was 340 per hit. */
const STRIKE_HOLD = 560;

interface Hit {
  /** The thing dealing it, or null when the source is not on the board. */
  from: number | null;
  /** What it lands on. */
  on: BeatAnchor;
  amount: number;
  combat: boolean;
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/** Any `damage_dealt` worth animating, or null. */
function hitFor(event: GameEvent): Hit | null {
  if (event.type !== "damage_dealt") return null;
  const amount = num(event.data.amount);
  if (amount === null || amount <= 0) return null;
  const combat = event.data.combat === true;
  const from = event.source;
  const on: BeatAnchor | null =
    event.data.to === "player"
      ? { kind: "player", pid: event.player ?? 0 }
      : (() => {
          const oid = num(event.data.oid);
          return oid === null ? null : ({ kind: "object", oid } as const);
        })();
  if (!on) return null;
  // Combat needs a dealer to lunge; a burn spell does not, and its source is
  // usually a card on the stack with no box on the battlefield to move.
  if (combat && from === null) return null;
  return { from, on, amount, combat };
}

/**
 * Where a hit is felt.
 *
 * For combat that is the point the two cards *meet*, which is neither of them.
 * For a burn spell there is no second card on the battlefield to meet, so it
 * lands on the victim itself.
 */
function contactPoint(hit: Hit): FxPoint {
  if (hit.from === null || !hit.combat) return hit.on;
  return { kind: "between", a: { kind: "object", oid: hit.from }, b: hit.on };
}

/** One creature committing to something, and what it committed against. */
interface Pairing {
  oid: number;
  toward: BeatAnchor;
}

/**
 * The declaration: a line of creatures stepping forward.
 *
 * A surge rather than a move, because where a card *sits* is the layout's
 * business -- `card.attacking` already gives it a red rim and `CombatArrows`
 * already draws who it is pointed at. What was missing was any sense that the
 * creatures had committed to something.
 *
 * Blocks get the same treatment aimed the other way, and no banner: interposing
 * is a reaction, and announcing it as loudly as the attack made the two read as
 * equally weighted when only one of them starts the exchange.
 */
export function declareBeat(id: string, kind: "attack" | "block", pairs: Pairing[]): Beat {
  const fx: TimedFx[] = [];

  pairs.forEach(({ oid, toward }, i) => {
    fx.push({ at: i * STAGGER, kind: "actuate", oid, move: "lunge", toward });
  });

  if (pairs.length > 0) {
    fx.push({ at: 0, kind: "sound", sound: "whoosh" });
    // A wide swing is a bigger commitment than one creature poking, and the
    // board should say so before any damage is dealt.
    if (kind === "attack" && pairs.length >= 3) fx.push({ at: 60, kind: "shake", power: 0.18 });
  }

  return {
    id,
    hold: pairs.length > 0 ? (kind === "attack" ? DECLARE_HOLD : DECLARE_HOLD * 0.7) : 160,
    text: null,
    banner:
      kind === "attack" && pairs.length > 0 ? { text: "Attack!", tone: "damage" } : undefined,
    fx,
  };
}

/**
 * The exchange itself.
 *
 * `viewerSeat` decides the vignette: a hit landing on you should be felt at the
 * edge of the screen, and a hit landing on somebody else should not.
 */
export function strikeBeat(
  id: string,
  hits: Hit[],
  attackers: Set<number>,
  viewerSeat?: number,
): Beat {
  const fx: TimedFx[] = [];

  /*
   * Only attackers lunge, and that is a correctness constraint rather than a
   * stylistic one. A blocker in a trade both deals and takes damage, so it
   * would be told to lunge *and* to recoil -- and an actuator cancels whatever
   * the card was already doing, so the recoil would fire at 140ms and snap the
   * card back from full extension. One side moves; the other gets moved.
   */
  const lunged = new Set<number>();
  for (const hit of hits) {
    if (hit.from === null || !attackers.has(hit.from) || lunged.has(hit.from)) continue;
    lunged.add(hit.from);
    fx.push({
      at: (lunged.size - 1) * 22,
      kind: "actuate",
      oid: hit.from,
      move: "lunge",
      toward: hit.on,
    });
  }
  if (lunged.size > 0) fx.push({ at: 0, kind: "sound", sound: "whoosh" });

  let toPlayers = 0;
  hits.forEach((hit, i) => {
    // A few frames of scatter, so eight simultaneous hits sound and look like
    // a melee rather than one very loud noise.
    const at = CONTACT + Math.min(4, i) * 18;
    const point = contactPoint(hit);

    fx.push({
      kind: "emit",
      at,
      preset: "impact",
      at_point: point,
      // Bigger hits throw more. Capped, or a 20-point trampler fills the board.
      scale: Math.min(1.9, 0.75 + hit.amount * 0.12),
    });
    fx.push({ kind: "float", at, at_point: point, value: `-${hit.amount}`, tone: "damage" });

    if (hit.on.kind === "object") {
      // Knocked back if it was standing still, rattled if it was mid-swing --
      // and rattled too when there is nothing on the board to be knocked away
      // *from*, which is every burn spell.
      const knockable = hit.from !== null && hit.combat && !attackers.has(hit.on.oid);
      fx.push(
        knockable && hit.from !== null
          ? {
              kind: "actuate",
              at,
              oid: hit.on.oid,
              move: "recoil",
              toward: { kind: "object", oid: hit.from },
              power: hit.amount / 6,
            }
          : { kind: "actuate", at, oid: hit.on.oid, move: "shudder", power: hit.amount / 6 },
      );
    } else {
      toPlayers += hit.amount;
      if (hit.on.pid === viewerSeat) {
        fx.push({ kind: "vignette", at, pid: hit.on.pid, tone: "damage" });
      }
    }
  });

  if (hits.length > 0) {
    fx.push({ kind: "sound", at: CONTACT, sound: hits.length > 2 ? "impact" : "hit" });
    // Damage to a *player* is what shakes the screen. Creatures trading is
    // loud but it is not the thing that moves the game toward an ending.
    const power = Math.min(1, toPlayers / 10);
    if (power > 0) fx.push({ kind: "shake", at: CONTACT, power });
    if (toPlayers >= 6) fx.push({ kind: "sound", at: CONTACT + 40, sound: "boom" });
  }

  return {
    id,
    /*
     * A combat exchange needs the whole lunge; a burn spell does not.
     *
     * The second case is what nine Grapeshot copies are, and at a fixed hold
     * they used to cost three seconds of the board sitting still counting to
     * one, nine times. They are simultaneous now, so the hold only has to cover
     * enough of the burst for the eye to register it.
     */
    hold: hits.some((hit) => hit.combat) ? STRIKE_HOLD : Math.min(520, 240 + hits.length * 32),
    // The ticker still lists every hit, so the beat itself stays wordless --
    // a line per point of damage was most of what made the old log unreadable.
    text: null,
    fx,
  };
}

export interface CombatPlan {
  /** Event index → the beat that replaces the whole run starting there. */
  leaders: Map<number, Beat>;
  /** Event indices folded into a leader, which `beatsFor` must skip. */
  absorbed: Set<number>;
  /**
   * Leaders whose prose no single sentence can carry.
   *
   * A run of one hit keeps its event's line -- "You take 3 damage" is exactly
   * right for a Lightning Bolt, and dropping it would leave `beatsFor` and
   * `describeEvent` disagreeing about an event they both handle. A run of
   * *four* has no such sentence: it is four different creatures hitting four
   * different things, and picking one of them to narrate would be a lie.
   */
  wordless: Set<number>;
}

/**
 * Find the combat runs in a batch and build one beat for each.
 *
 * A run is closed by any event that would itself be narrated, exactly as
 * `groupExits` does -- "damage, a trigger resolves, more damage" is two
 * exchanges, and merging them would put the second one on screen before the
 * trigger that caused it. Events that are silent anyway do not break a run.
 *
 * Runs are collected first and turned into beats afterwards, because a run's
 * beat depends on the whole of it: the strike cannot know how hard to shake
 * until it has seen every hit, and the declaration cannot stagger its surge
 * until it knows how many creatures are in the line.
 */
export function planCombat(
  events: GameEvent[],
  silent: (type: string) => boolean,
  viewerSeat?: number,
): CombatPlan {
  const leaders = new Map<number, Beat>();
  const absorbed = new Set<number>();
  const wordless = new Set<number>();

  /*
   * Who is attacking, gathered across the whole batch rather than per run.
   *
   * First strike is why. It splits the exchange across two damage steps, and
   * the second one arrives with no `attacks` event in front of it -- so a run
   * that looked only at itself would not know which side of each pair to move,
   * and the creature with first strike would get hit by its own victim.
   */
  const attackers = new Set<number>();
  for (const event of events) {
    if (event.type !== "attacks") continue;
    const attacker = num(event.data.attacker) ?? event.source;
    if (attacker !== null) attackers.add(attacker);
  }

  type Run =
    | { kind: "attack" | "block"; at: number; pairs: Pairing[] }
    | { kind: "strike"; at: number; hits: Hit[] };

  const runs: Run[] = [];
  let open: Run | null = null;

  /** The pairing a declaration event contributes, if any. */
  const pairingFor = (event: GameEvent): Pairing | null => {
    if (event.type === "attacks") {
      const oid = num(event.data.attacker) ?? event.source;
      const defender = num(event.data.defender);
      if (oid === null || defender === null) return null;
      return { oid, toward: { kind: "player", pid: defender } };
    }
    if (event.type === "blocks") {
      const oid = num(event.data.blocker) ?? event.source;
      const attacker = num(event.data.attacker);
      if (oid === null || attacker === null) return null;
      return { oid, toward: { kind: "object", oid: attacker } };
    }
    return null;
  };

  events.forEach((event, index) => {
    if (DECLARE.has(event.type)) {
      // `blocks` opens a block run; everything else in the declaration family
      // belongs to whichever run is already open, or opens an attack run.
      const kind: "attack" | "block" =
        event.type === "blocks" || event.type === "blockers_declared" ? "block" : "attack";
      let run: Extract<Run, { kind: "attack" | "block" }>;
      if (open === null || open.kind !== kind) {
        run = { kind, at: index, pairs: [] };
        open = run;
        runs.push(run);
      } else {
        run = open;
        absorbed.add(index);
      }
      const pairing = pairingFor(event);
      if (pairing) run.pairs.push(pairing);
      return;
    }

    const hit = hitFor(event);
    if (hit) {
      if (open === null || open.kind !== "strike") {
        open = { kind: "strike", at: index, hits: [hit] };
        runs.push(open);
      } else {
        open.hits.push(hit);
        absorbed.add(index);
      }
      return;
    }

    if (!silent(event.type)) open = null;
  });

  for (const run of runs) {
    const id = `combat-${run.kind}-${run.at}`;
    if (run.kind === "strike") {
      leaders.set(run.at, strikeBeat(id, run.hits, attackers, viewerSeat));
      if (run.hits.length > 1) wordless.add(run.at);
    } else {
      leaders.set(run.at, declareBeat(id, run.kind, run.pairs));
    }
  }

  return { leaders, absorbed, wordless };
}
