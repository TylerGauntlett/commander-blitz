/**
 * Sound, synthesised.
 *
 * There are no audio files in this repo and adding some would mean adding
 * binary assets to a project whose whole card database is readable JSON. Every
 * sound here is built from an oscillator or a noise burst instead: a few dozen
 * lines, no bytes on disk, and the parameters are legible as parameters.
 *
 * The palette is deliberately small and dry. These play behind a narration
 * queue that can fire a dozen beats in a second, so anything with a long tail
 * turns into mud.
 *
 * Nothing here runs until the player unmutes, and the context is created lazily
 * on the first sound: browsers refuse to start audio before a user gesture, and
 * constructing one on module load would log a warning on every page view and
 * every test run.
 */

export type SoundName =
  | "thump"
  | "hit"
  | "tap"
  | "shuffle"
  | "chime"
  | "toll"
  // Added with the combat choreography. `impact` and `boom` are the weight a
  // hit needs; `whoosh` is the sound of the swing that precedes it, and is the
  // first voice here that plays *before* anything has happened.
  | "impact"
  | "boom"
  | "whoosh"
  | "shatter"
  // Gesture voices. Every sound above answers the server; these answer the
  // player, which is most of what "responsive" means.
  | "pickup"
  | "drop"
  | "deny"
  // Ring voices. These answer a *cursor*, which is a different job again: they
  // fire far more often than anything above (up to twenty-six times a second
  // on a held direction), so they have to be short enough to layer over
  // themselves without turning into a drone.
  | "move"
  | "back";

type Ctx = AudioContext & {
  _master?: GainNode;
  _dry?: GainNode;
  _wet?: GainNode;
};

let ctx: Ctx | null = null;
let failed = false;

/**
 * A room, generated rather than loaded.
 *
 * The palette used to be deliberately tail-less because "anything with a long
 * tail turns into mud" behind a queue that can fire a dozen beats a second --
 * which was true, and the reason the board sounded like a spreadsheet. The
 * actual fix is a short shared space plus the duck below: the tails live on one
 * bus that gets pushed down whenever a new transient arrives, so a wrath's ten
 * bursts overlap into one big noise instead of ten muddy ones.
 *
 * Noise shaped by a decaying exponential is not a real impulse response, but at
 * 0.5s and 18% wet nothing about it needs to be. It costs one buffer, once.
 */
function impulse(c: Ctx, seconds = 0.5, decay = 3.2): AudioBuffer {
  const frames = Math.floor(c.sampleRate * seconds);
  const buffer = c.createBuffer(2, frames, c.sampleRate);
  for (let channel = 0; channel < 2; channel += 1) {
    const data = buffer.getChannelData(channel);
    for (let i = 0; i < frames; i += 1) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / frames) ** decay;
    }
  }
  return buffer;
}

function context(): Ctx | null {
  if (failed) return null;
  if (ctx) return ctx;
  try {
    const Ctor =
      window.AudioContext ??
      (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) {
      failed = true;
      return null;
    }
    ctx = new Ctor() as Ctx;
    const master = ctx.createGain();
    master.gain.value = 0.28;
    master.connect(ctx.destination);

    // Voices fan out to both busses. `dry` is the transient, `wet` is the
    // room -- keeping them separate is what lets the duck touch only the tail.
    const dry = ctx.createGain();
    dry.gain.value = 1;
    dry.connect(master);

    const wet = ctx.createGain();
    wet.gain.value = 0.18;
    try {
      const reverb = ctx.createConvolver();
      reverb.buffer = impulse(ctx);
      wet.connect(reverb).connect(master);
    } catch {
      // No convolver: fall through dry rather than losing the voice entirely.
      wet.connect(master);
    }

    ctx._master = master;
    ctx._dry = dry;
    ctx._wet = wet;
    return ctx;
  } catch {
    // No Web Audio (jsdom, a locked-down browser). Sound is a luxury; carry on.
    failed = true;
    return null;
  }
}

/**
 * Push the room down for a moment.
 *
 * Called by the loud voices. Without it, six simultaneous deaths put six
 * half-second tails on top of each other and the board turns to porridge at
 * exactly the moment it is trying to say something.
 */
function duck(c: Ctx, amount = 0.35, ms = 260): void {
  const wet = c._wet;
  if (!wet) return;
  const now = c.currentTime;
  wet.gain.cancelScheduledValues(now);
  wet.gain.setValueAtTime(wet.gain.value, now);
  wet.gain.linearRampToValueAtTime(0.18 * amount, now + 0.02);
  wet.gain.linearRampToValueAtTime(0.18, now + ms / 1000);
}

/**
 * A small random pitch offset, as a frequency multiplier.
 *
 * One voice per event class meant a five-land turn played the identical click
 * five times, which reads as a stuck loop rather than as five lands. Real
 * repeated sounds never match exactly; a few dozen cents of scatter is enough
 * for the ear to hear five events instead of one repeated sample.
 *
 * Applied to frequency rather than to `playbackRate` because every voice here is
 * generated, so there is no sample to resample -- and detuning the filter along
 * with the oscillator keeps the timbre intact instead of just shifting a pitch.
 */
const DETUNE_CENTS = 45;

function detuned(frequency: number): number {
  const cents = (Math.random() * 2 - 1) * DETUNE_CENTS;
  return frequency * 2 ** (cents / 1200);
}

/** A short burst of filtered white noise: card on felt, impact, shuffle. */
function noise(
  c: Ctx,
  {
    duration,
    gain,
    type,
    frequency,
    q = 1,
  }: {
    duration: number;
    gain: number;
    type: BiquadFilterType;
    frequency: number;
    q?: number;
  },
): void {
  const frames = Math.max(1, Math.floor(c.sampleRate * duration));
  const buffer = c.createBuffer(1, frames, c.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < frames; i += 1) data[i] = Math.random() * 2 - 1;

  const source = c.createBufferSource();
  source.buffer = buffer;

  const filter = c.createBiquadFilter();
  filter.type = type;
  filter.frequency.value = detuned(frequency);
  filter.Q.value = q;

  const envelope = c.createGain();
  const now = c.currentTime;
  envelope.gain.setValueAtTime(0, now);
  envelope.gain.linearRampToValueAtTime(gain, now + 0.004);
  envelope.gain.exponentialRampToValueAtTime(0.0001, now + duration);

  source.connect(filter).connect(envelope);
  route(c, envelope);
  source.start(now);
  source.stop(now + duration);
}

/** Every voice goes to the transient bus and the room, never straight out. */
function route(c: Ctx, node: AudioNode): void {
  if (c._dry) node.connect(c._dry);
  else node.connect(c.destination);
  if (c._wet) node.connect(c._wet);
}

/** A pitched blip, optionally sliding. */
function tone(
  c: Ctx,
  {
    from,
    to,
    duration,
    gain,
    type = "sine",
  }: {
    from: number;
    to?: number;
    duration: number;
    gain: number;
    type?: OscillatorType;
  },
): void {
  const osc = c.createOscillator();
  const envelope = c.createGain();
  const now = c.currentTime;

  // One offset for the whole glide, so a slide keeps its shape and only its
  // pitch moves. Detuning the endpoints independently would vary the interval.
  const cents = (Math.random() * 2 - 1) * DETUNE_CENTS;
  const shift = 2 ** (cents / 1200);

  osc.type = type;
  osc.frequency.setValueAtTime(from * shift, now);
  if (to !== undefined) {
    osc.frequency.exponentialRampToValueAtTime(to * shift, now + duration);
  }

  envelope.gain.setValueAtTime(0, now);
  envelope.gain.linearRampToValueAtTime(gain, now + 0.006);
  envelope.gain.exponentialRampToValueAtTime(0.0001, now + duration);

  osc.connect(envelope);
  route(c, envelope);
  osc.start(now);
  osc.stop(now + duration);
}

const VOICES: Record<SoundName, (c: Ctx) => void> = {
  /** A card landing on the table: low, dull, over immediately. */
  thump: (c) => {
    noise(c, { duration: 0.09, gain: 0.5, type: "lowpass", frequency: 420 });
    tone(c, { from: 150, to: 60, duration: 0.08, gain: 0.22, type: "triangle" });
  },
  /** Damage. Sharper and higher than a thump, with a bit of body. */
  hit: (c) => {
    noise(c, { duration: 0.14, gain: 0.55, type: "bandpass", frequency: 1500, q: 0.8 });
    tone(c, { from: 220, to: 70, duration: 0.13, gain: 0.28, type: "square" });
  },
  /** Tapping a permanent for mana: a small dry click. */
  tap: (c) => {
    noise(c, { duration: 0.035, gain: 0.3, type: "highpass", frequency: 2600 });
  },
  /*
   * The ring stepping one stop.
   *
   * Deliberately the quietest and shortest voice in the file. At a full stick
   * deflection this fires every 38ms, so anything with a tail becomes a
   * continuous tone -- and anything at `tap`'s level becomes exhausting inside
   * one turn. 8ms of filtered noise at a third of a tap reads as texture rather
   * than as a sound, which is exactly what a cursor wants.
   */
  move: (c) => {
    noise(c, { duration: 0.008, gain: 0.1, type: "highpass", frequency: 3800 });
  },
  /** Unwinding one level: the same tick, pitched down, so back reads as back. */
  back: (c) => {
    noise(c, { duration: 0.014, gain: 0.12, type: "lowpass", frequency: 900 });
  },
  /** Cards moving in bulk: draws, mills, shuffles. */
  shuffle: (c) => {
    noise(c, { duration: 0.16, gain: 0.22, type: "bandpass", frequency: 3400, q: 0.5 });
  },
  /** Something good resolving. */
  chime: (c) => {
    tone(c, { from: 660, duration: 0.16, gain: 0.16, type: "sine" });
    tone(c, { from: 990, duration: 0.22, gain: 0.1, type: "sine" });
  },
  /** Something final: an elimination, the end of the game. */
  toll: (c) => {
    tone(c, { from: 160, to: 110, duration: 0.7, gain: 0.24, type: "triangle" });
  },

  /*
   * Creatures connecting. Three layers, because a single burst of noise reads
   * as static: a bright transient for the contact, a body for the mass behind
   * it, and a short sub for the weight.
   */
  impact: (c) => {
    noise(c, { duration: 0.05, gain: 0.6, type: "highpass", frequency: 2400 });
    noise(c, { duration: 0.18, gain: 0.5, type: "bandpass", frequency: 900, q: 0.7 });
    tone(c, { from: 180, to: 48, duration: 0.19, gain: 0.34, type: "square" });
    duck(c, 0.5);
  },

  /** A player being hit hard. The one voice with real low end. */
  boom: (c) => {
    noise(c, { duration: 0.3, gain: 0.42, type: "lowpass", frequency: 700 });
    tone(c, { from: 120, to: 34, duration: 0.42, gain: 0.5, type: "sine" });
    tone(c, { from: 240, to: 70, duration: 0.2, gain: 0.2, type: "triangle" });
    duck(c, 0.3, 380);
  },

  /*
   * The swing, not the hit.
   *
   * Plays as the creatures set off, ~140ms before contact, which is what makes
   * the exchange feel like it has a windup rather than arriving all at once.
   * Bandpass sweeping down and quiet enough to sit under the impact.
   */
  whoosh: (c) => {
    noise(c, { duration: 0.16, gain: 0.2, type: "bandpass", frequency: 1100, q: 0.35 });
    tone(c, { from: 900, to: 300, duration: 0.14, gain: 0.06, type: "sine" });
  },

  /** Glass: a countered spell, and anything that breaks rather than burns. */
  shatter: (c) => {
    noise(c, { duration: 0.09, gain: 0.4, type: "highpass", frequency: 4200 });
    tone(c, { from: 2400, to: 1400, duration: 0.16, gain: 0.1, type: "triangle" });
    tone(c, { from: 3300, to: 1900, duration: 0.22, gain: 0.07, type: "sine" });
  },

  /* Gesture voices: quiet, instant, and never ducked. They answer the player's
     own hand, so anything that made them wait would defeat the point. */
  pickup: (c) => {
    noise(c, { duration: 0.03, gain: 0.16, type: "highpass", frequency: 3000 });
    tone(c, { from: 520, to: 700, duration: 0.05, gain: 0.05, type: "sine" });
  },
  drop: (c) => {
    noise(c, { duration: 0.07, gain: 0.34, type: "lowpass", frequency: 520 });
    tone(c, { from: 190, to: 90, duration: 0.07, gain: 0.14, type: "triangle" });
  },
  /** A gesture that maps to nothing legal. Dull and low: a refusal, not an alarm. */
  deny: (c) => {
    tone(c, { from: 150, to: 120, duration: 0.11, gain: 0.14, type: "square" });
  },
};

/**
 * Play a sound, or do nothing at all.
 *
 * Never throws and never awaits: a failure to make a noise must not interrupt
 * the narration queue that asked for it.
 */
export function play(name: SoundName): void {
  const c = context();
  if (!c) return;
  try {
    // Autoplay policy parks the context until a gesture; by the time anything
    // asks for a sound the player has clicked something, so this succeeds.
    if (c.state === "suspended") void c.resume();
    VOICES[name]?.(c);
  } catch {
    // A dropped sound is not worth a broken turn.
  }
}
