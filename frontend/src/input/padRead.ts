/**
 * Reading every connected pad, once a frame, into one `Reading`.
 *
 * Points 1 to 3 of `pad.ts`'s header are this file: the array is a snapshot
 * re-read each frame, every pad is read rather than the first, and a pad the
 * browser will not call `standard` is remapped through `HID` and `HAT`.
 */

import { BTN, type PadButton } from "./buttons";
import type { Dir } from "./repeat";

/** Every intent, in a fixed order, walked once rather than rebuilt per frame. */
export const NAMES = Object.keys(BTN) as PadButton[];

/**
 * Past this an analog control counts as pressed.
 *
 * The triggers are analog and SOME DRIVERS NEVER SET `pressed` ON THEM AT ALL,
 * so a digital-only read loses L2 and R2 entirely on those. Well past any
 * resting value and well short of the click.
 */
export const TRIGGER_ON = 0.5;

/**
 * The raw HID fallback layout, for a pad the browser will not call standard.
 *
 * Every index is from the Xbox Wireless Controller's Bluetooth HID report
 * descriptor, which is also what most third-party pads answer with -- SDL's
 * community mapping database agrees on it, and it is the layout a browser's
 * generic mapper produces when XInput did not claim the device.
 *
 * THE GAPS ARE THE POINT. A/B/X/Y sit at 0/1/3/4, not 0/1/2/3, so reading a
 * non-standard pad through `BTN` puts `X` on an unassigned index and `Y` on the
 * button marked X. Anything with no dependable raw equivalent is simply absent
 * here and stays unbound rather than being guessed at: a button that does
 * nothing is recoverable, a button that does the wrong thing is not.
 */
const HID: Partial<Record<PadButton, number>> = {
  a: 0,
  b: 1,
  x: 3,
  y: 4,
  l1: 6,
  r1: 7,
  view: 10,
  menu: 11,
  l3: 13,
  r3: 14,
};

/** ...and where its triggers live, as axes rather than as buttons. */
const HID_TRIGGER = { l2: 5, r2: 4 } as const;

/**
 * The eight positions of a hat switch, in report order.
 *
 * A d-pad on a non-standard pad is not four buttons -- it is one hat axis, and
 * its diagonals are single values rather than two directions at once, which is
 * why this is a table rather than arithmetic over x and y.
 */
const HAT: readonly (readonly Dir[])[] = [
  ["up"],
  ["up", "right"],
  ["right"],
  ["down", "right"],
  ["down"],
  ["down", "left"],
  ["left"],
  ["up", "left"],
];

function axisAt(pad: Gamepad, index: number): number {
  const value = index >= 0 && index < pad.axes.length ? pad.axes[index] : 0;
  return Number.isFinite(value) ? value : 0;
}

/**
 * Which directions a hat axis is reporting.
 *
 * Browsers rescale a hat's logical range onto -1..1, so the eight live
 * positions land on evenly spaced values and CENTRED LANDS OUTSIDE THE RANGE --
 * the null position is one step past the last real one. That is why the guard
 * is "outside -1..1" rather than a comparison against a specific number:
 * different descriptors put centre at different values, and all of them are
 * above 1.
 */
export function hatDirs(value: number): readonly Dir[] {
  if (!isHatLive(value)) return [];
  return HAT[Math.round((value + 1) * 3.5)] ?? [];
}

function isHatLive(value: number): boolean {
  return Number.isFinite(value) && value >= -1.05 && value <= 1.05;
}

/**
 * Pads whose last axis has been seen at a hat's centred value.
 *
 * THE LAST AXIS IS ONLY A GUESS AT A HAT, and guessing wrong held Down forever.
 * Plenty of non-standard pads end on a stick, a slider or a gyro axis instead
 * -- and one resting at 0 reads, through `hatDirs`, as position 4: Down. The
 * loop then saw Down held from the first frame: it auto-repeated and dragged
 * the ring to the bottom of every screen (the deck catalogue's import box, on
 * a Steam Deck), and no real Down could ever make an edge. Arrow keys "stopped
 * working" on a machine that merely had such a pad attached, with nobody
 * touching it.
 *
 * A real hat rests at CENTRE, which is outside -1..1 (see `hatDirs`), so it
 * shows that value on the very first frame the pad is read; an ordinary axis
 * never leaves -1..1 at all. Only a pad that has been seen centred has its last
 * axis read as a hat. Keyed by slot and id, because a `Gamepad` is a snapshot
 * and need not be the same object from one frame to the next.
 */
export const hatSeen = new Set<string>();

function hatOf(pad: Gamepad): readonly Dir[] {
  const value = axisAt(pad, pad.axes.length - 1);
  const key = `${pad.index}:${pad.id}`;
  if (!hatSeen.has(key)) {
    if (Number.isFinite(value) && !isHatLive(value)) hatSeen.add(key);
    return [];
  }
  return hatDirs(value);
}

/** A HID trigger axis rests at -1 and bottoms out at 1; callers want 0..1. */
function unipolar(value: number): number {
  return Math.min(1, Math.max(0, (value + 1) / 2));
}

/**
 * Every pad the browser will admit to, standard-mapping ones first.
 *
 * `getGamepads()` is sparse and indexed by SLOT, so the nulls are not padding
 * to be trimmed and re-indexed -- they are empty slots, and a pad's position in
 * the compacted array says nothing about which pad it is. Standard-mapping pads
 * sort first only so `rumble` and the diagnostics prefer one the browser could
 * vouch for; reading is unaffected, because reading takes the whole set.
 */
export function livePads(): Gamepad[] {
  if (typeof navigator === "undefined" || !navigator.getGamepads) return [];
  let all: (Gamepad | null)[];
  try {
    all = [...navigator.getGamepads()];
  } catch {
    // Some embedded webviews expose the method and then throw from it.
    return [];
  }
  const live = all.filter((pad): pad is Gamepad => pad !== null && pad.connected !== false);
  return live.sort(
    (a, b) => Number(b.mapping === "standard") - Number(a.mapping === "standard"),
  );
}

/** One frame's reading of every pad at once. */
export interface Reading {
  count: number;
  down: Set<PadButton>;
  l2: number;
  r2: number;
  lx: number;
  ly: number;
  rx: number;
  ry: number;
  /** Left-stick magnitude of whichever pad is pushing hardest. */
  mag: number;
}

function readOne(pad: Gamepad, into: Reading, rmag: { value: number }): void {
  const standard = pad.mapping === "standard";

  for (const name of NAMES) {
    const index = standard ? BTN[name] : HID[name];
    if (index === undefined) continue;
    const button = pad.buttons[index];
    // `value > TRIGGER_ON` as well as `pressed`, for the drivers that never set
    // `pressed` on an analog control at all.
    if (button && (button.pressed || button.value > TRIGGER_ON)) into.down.add(name);
  }

  if (standard) {
    into.l2 = Math.max(into.l2, pad.buttons[BTN.l2]?.value ?? 0);
    into.r2 = Math.max(into.r2, pad.buttons[BTN.r2]?.value ?? 0);
  } else {
    // A hat rather than four buttons, and triggers as axes rather than buttons.
    // Without this, half of a non-standard pad is inert and NO direction works.
    // ...but only once that last axis has shown it IS a hat -- see `hatSeen`.
    for (const dir of hatOf(pad)) into.down.add(dir);
    const l2 = unipolar(axisAt(pad, HID_TRIGGER.l2));
    const r2 = unipolar(axisAt(pad, HID_TRIGGER.r2));
    into.l2 = Math.max(into.l2, l2);
    into.r2 = Math.max(into.r2, r2);
    if (l2 > TRIGGER_ON) into.down.add("l2");
    if (r2 > TRIGGER_ON) into.down.add("r2");
  }

  /*
   * The stick pushed hardest is the one the player is holding.
   *
   * Comparing magnitudes rather than taking the first pad is what lets a second
   * controller sit idle in the room -- or a virtual one Steam publishes beside
   * the real one -- without its resting axes pinning the cursor.
   */
  const lx = axisAt(pad, 0);
  const ly = axisAt(pad, 1);
  const lm = Math.hypot(lx, ly);
  if (lm > into.mag) {
    into.mag = lm;
    into.lx = lx;
    into.ly = ly;
  }
  const rx = axisAt(pad, 2);
  const ry = axisAt(pad, 3);
  const rm = Math.hypot(rx, ry);
  if (rm > rmag.value) {
    rmag.value = rm;
    into.rx = rx;
    into.ry = ry;
  }
}

export function read(): Reading {
  const into: Reading = {
    count: 0,
    down: new Set<PadButton>(),
    l2: 0,
    r2: 0,
    lx: 0,
    ly: 0,
    rx: 0,
    ry: 0,
    mag: 0,
  };
  const rmag = { value: 0 };
  const all = livePads();
  into.count = all.length;
  for (const pad of all) readOne(pad, into, rmag);
  return into;
}
