/**
 * The shape of an animation beat: what the narration layer plays over a new state.
 *
 * Built by `logic/events.ts`, played by `state/narration.ts` and drawn by `FxLayer`.
 */

import type { SoundName } from "../../audio/sfx";
import type { PresetName } from "../../fx/presets";

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
