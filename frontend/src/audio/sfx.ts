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

export type SoundName = "thump" | "hit" | "tap" | "shuffle" | "chime" | "toll";

type Ctx = AudioContext & { _master?: GainNode };

let ctx: Ctx | null = null;
let failed = false;

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
    ctx._master = master;
    return ctx;
  } catch {
    // No Web Audio (jsdom, a locked-down browser). Sound is a luxury; carry on.
    failed = true;
    return null;
  }
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

  source
    .connect(filter)
    .connect(envelope)
    .connect(c._master ?? c.destination);
  source.start(now);
  source.stop(now + duration);
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

  osc.connect(envelope).connect(c._master ?? c.destination);
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
