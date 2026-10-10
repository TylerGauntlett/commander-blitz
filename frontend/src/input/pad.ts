/**
 * The controller, polled.
 *
 * A gamepad is not evented -- there is no `buttondown` -- so this is a loop that
 * reads the pad every frame and turns edges into callbacks. Consumers bind named
 * intents (`pad.on("a", fn)`) and never an index, so a keyboard press and a pad
 * press arrive at the same place and nothing downstream has two code paths.
 *
 * Six things here are load-bearing and each cost somebody real time to find:
 *
 * 1. **`navigator.getGamepads()` is re-read every frame.** The array it returns
 *    is a SNAPSHOT. Caching the `Gamepad` object gives you buttons frozen at
 *    the moment you cached it, which is the single most common way to write a
 *    gamepad loop that half-works -- it responds once and then never again.
 *
 *    It is read ONCE PER FRAME and passed around, not re-read per question. The
 *    version that asked `pads()[0]` inside `padDown`, `trigger`, `stick` and
 *    `pushFor` called `getGamepads()` more than twenty times a frame -- 1,200
 *    whole-buffer copies a second at 60Hz, on a handheld, to answer questions
 *    that all have the same answer within one frame.
 *
 * 2. **EVERY connected pad is read, not `pads()[0]`.** A Windows desktop
 *    routinely enumerates more than one: Steam Input publishes a virtual pad
 *    beside the physical one, a wheel or a flight stick occupies a slot, and a
 *    controller that reconnects comes back at a new index. `getGamepads()` is
 *    SPARSE and indexed by slot, so "the first non-null entry" is not "the pad
 *    in the player's hands" -- and when it guessed wrong every button read came
 *    back neutral and the controller did nothing at all, which from outside is
 *    indistinguishable from the loop being dead. Buttons are OR-ed across the
 *    set and the stick pushed hardest wins, so whichever pad the player picks
 *    up is the one driving.
 *
 * 3. **A pad the browser will not call `standard` is remapped, not misread.**
 *    The W3C indices in `buttons.ts` mean something only when the browser says
 *    the layout is standard. When it cannot vouch for one -- an Xbox pad over
 *    Bluetooth that XInput did not claim, most third-party pads, Firefox on a
 *    Deck in desktop mode -- it hands over the raw HID report order instead,
 *    where the d-pad is a HAT AXIS rather than buttons 12-15 and the face
 *    buttons sit at 0/1/3/4 with gaps. Read through `BTN` such a pad looks
 *    almost completely inert: no direction works at all, and half the face
 *    buttons press the wrong thing. See `HID` in `padRead.ts`, which is where
 *    points 1 to 3 live.
 *
 * 4. **This owns its own rAF, not `fx/scheduler.ts`'s.** The FX scheduler is
 *    torn down between games (`stopAll`), and input must not be droppable by an
 *    effects reset.
 *
 *    THE LOOP NEVER STOPS ITSELF WHILE IT IS LISTENING, and that is a fix
 *    rather than an oversight. It used to return to `raf = 0` on any frame with
 *    no pad, no held key and no frame subscriber -- which is *every* frame on a
 *    fresh page, because Chrome reports four nulls from `getGamepads()` until
 *    the pad's first gesture. So `startPad()` ran one frame, saw nothing, and
 *    died, leaving the `gamepadconnected` listener as the only way back. The
 *    prototype this was ported from binds that same listener with an EMPTY BODY
 *    on purpose (`the handheld round's 06 'One Thumb' (`docs/design-record.md#handheld`):2313`) and polls
 *    unconditionally; the port inverted it and made the decorative listener
 *    load-bearing. A controller that was plugged in before the tab existed, or
 *    whose event landed before React mounted `Screen`, was then never seen at
 *    all.
 *
 *    It idles at `IDLE_MS` rather than at full rAF so a desktop with a keyboard
 *    still pays almost nothing: one `getGamepads()` call every ~100ms, and full
 *    frame rate from the moment there is anything to read.
 *
 * 5. **A rAF handle is not proof the loop is alive** -- see `wake`. No browser
 *    runs rAF for a hidden, minimised or occluded window, so a handle taken
 *    just before the window went away outlives the loop that owns it. `wake()`
 *    used to read a non-zero handle as "already running" and return, which made
 *    the one call that exists to recover a stalled loop the one call guaranteed
 *    not to. `lastTick` is what tells the two apart.
 *
 * 6. **The key latch.** A key tapped faster than a frame is a key the poll never
 *    sees: `keydown` and `keyup` can both land inside one 16ms gap and the press
 *    is silently dropped. A pad cannot do this to you because it *is* the poll,
 *    which is why the bug only ever appears on the keyboard fallback -- and why
 *    it would have been blamed on the key map rather than found here.
 *
 * ...and **stick hysteresis and the analog repeat ramp**, both in `repeat.ts`. A
 * stick held toward a corner sits on a sector boundary and chatters without the
 * first; the second is what makes a nudge step once and a shove sweep.
 */

import { KEYS, type PadButton, REPEATS, SWALLOW } from "./buttons";
import { ARROWS, fieldKeeps, isField, isSelect } from "./fieldKeys";
import { noteInput, notePadConnected } from "./inputMode";
import { hatSeen, livePads, NAMES, type Reading, read, TRIGGER_ON } from "./padRead";
import { type Dir, deadzone, pushOf, repeatMs, STICK, sector } from "./repeat";

export interface PadFrame {
  lstick: { x: number; y: number };
  rstick: { x: number; y: number };
  /** Analog trigger positions, 0..1. */
  l2: number;
  r2: number;
  connected: boolean;
}

type Handler = () => void;
type AnyHandler = (button: PadButton) => void;
type FrameHandler = (frame: PadFrame) => void;

const handlers = new Map<PadButton, Set<Handler>>();
const anyHandlers = new Set<AnyHandler>();
const frameHandlers = new Set<FrameHandler>();
const connectionHandlers = new Set<(connected: boolean) => void>();

const keyDown = new Set<PadButton>();
const keyLatch = new Set<PadButton>();
const prev = new Map<PadButton, boolean>();
const dueAt = new Map<PadButton, number>();
const runs = new Map<PadButton, number>();

let latched: Dir | null = null;
let connected = false;
let raf = 0;
let idle: ReturnType<typeof setTimeout> | null = null;
let listening = false;
let lastTick = 0;

/**
 * How often the loop looks for a pad when there is nothing to read.
 *
 * ~10Hz. Fast enough that plugging a controller in feels immediate, slow enough
 * that a desktop mouse player is not paying for a 60Hz poll of an empty array.
 */
const IDLE_MS = 100;

/**
 * How long without a tick means the loop has stalled rather than idled.
 *
 * Comfortably past `IDLE_MS` plus a frame, so a healthy idling loop is never
 * mistaken for a dead one, and far under anything a human would sit through.
 */
const STALL_MS = 1000;

// -------------------------------------------------------------------- edges

/**
 * Where this direction sits on the ramp.
 *
 * ONLY A DIRECTION COMING FROM THE STICK IS ANALOG, and it takes three checks
 * to be sure of that rather than one: `latched` holds the direction whatever
 * its source, because the keyboard fallback and the d-pad write into it too.
 * With a pad connected and the keyboard driving, reading the stick's magnitude
 * here would be measuring a stick at rest -- and would hand every key press the
 * slowest rate on the ramp.
 */
function pushFor(name: PadButton, live: Reading): number {
  if (keyDown.has(name) || keyLatch.has(name)) return pushOf(null);
  if (live.count === 0 || latched !== name) return pushOf(null);
  return pushOf(live.mag);
}

function fire(name: PadButton): void {
  noteInput(keyDown.has(name) || keyLatch.has(name) ? "keyboard" : "pad");
  const bound = handlers.get(name);
  if (bound) for (const handler of [...bound]) handler();
  for (const handler of [...anyHandlers]) handler(name);
}

function frame(now: number): void {
  lastTick = now;
  const live = read();
  const isLive = live.count > 0;
  if (isLive !== connected) {
    connected = isLive;
    notePadConnected(connected);
    for (const handler of [...connectionHandlers]) handler(connected);
  }

  /*
   * `latched` is THE STICK'S sector, and deliberately not the d-pad's.
   *
   * It is what `pushFor` reads to decide whether a direction is analog, so a
   * d-pad hold must not appear in it -- a d-pad is digital and stands at
   * `RAMP.keyT` like the keyboard. The d-pad still fires and still repeats: it
   * arrives through `live.down` below, which is the same path every other
   * button takes. The keyboard writes here only so that a held key has a
   * direction to be, which `repeat.ts` documents.
   */
  /*
   * ANALOG MOTION IS INPUT, even before it becomes a direction.
   *
   * `fire` below notes the mode on a button EDGE, which meant two things a
   * player does constantly did not: pushing a stick short of the fire threshold,
   * and holding `L2` to keep the region dial up. Both left the hint bar
   * advertising `Enter`/`Esc` to somebody visibly holding a controller -- and
   * the second is worse than it sounds, because a hold produces no edges at all
   * for as long as it lasts.
   *
   * Cheap: `noteInput` returns immediately unless the resolved mode changes.
   */
  if (isLive) {
    const moving =
      Math.hypot(live.lx, live.ly) > STICK.dead ||
      Math.hypot(live.rx, live.ry) > STICK.dead ||
      live.l2 > TRIGGER_ON ||
      live.r2 > TRIGGER_ON;
    if (moving) noteInput("pad");
  }

  latched = isLive ? sector(live.lx, live.ly, latched) : null;
  if (!latched) {
    for (const dir of REPEATS) {
      if (keyDown.has(dir) || keyLatch.has(dir)) latched = dir as Dir;
    }
  }

  for (const name of NAMES) {
    // Sticks stand in for the d-pad, so a direction is either.
    const down =
      keyDown.has(name) || keyLatch.has(name) || live.down.has(name) || latched === name;
    const was = prev.get(name) ?? false;
    if (down && !was) {
      fire(name);
      if (REPEATS.has(name)) {
        runs.set(name, 0);
        dueAt.set(name, now + repeatMs(pushFor(name, live), 0, true));
      }
    } else if (
      down &&
      was &&
      REPEATS.has(name) &&
      now >= (dueAt.get(name) ?? Number.MAX_VALUE)
    ) {
      fire(name);
      const run = (runs.get(name) ?? 0) + 1;
      runs.set(name, run);
      dueAt.set(name, now + repeatMs(pushFor(name, live), run, false));
    } else if (!down) {
      dueAt.delete(name);
      runs.delete(name);
    }
    prev.set(name, down);
  }

  if (frameHandlers.size > 0) {
    const snapshot: PadFrame = {
      lstick: deadzone(live.lx, live.ly),
      rstick: deadzone(live.rx, live.ry),
      l2: keyDown.has("l2") ? 1 : live.l2,
      r2: keyDown.has("r2") ? 1 : live.r2,
      connected,
    };
    for (const handler of [...frameHandlers]) handler(snapshot);
  }

  // One frame has now observed every latched key, so a key still physically
  // held survives in `keyDown` and a tapped one is released here.
  for (const name of [...keyLatch]) if (!keyDown.has(name)) keyLatch.delete(name);

  /*
   * The loop does not stop while it is listening -- see header point 4.
   *
   * It drops to `IDLE_MS` when there is nothing to read, which is the whole of
   * the cost saving the self-terminating version was after, without the failure
   * mode: a pad that appears later is seen within ~100ms rather than never.
   */
  /*
   * A BUTTON STILL RECORDED AS DOWN KEEPS THE LOOP AWAKE, and that is a fix for
   * a press the keyboard fallback silently ate.
   *
   * `prev` is written above, in the same frame the latch is cleared below it --
   * so the frame that observes a tapped key observes it as DOWN, and only the
   * NEXT frame can record the release. With nothing else to poll, that next
   * frame was 100ms away on the idle timer, and `wake()` cancels that timer the
   * moment another key arrives: the second press then read `down && was` and
   * produced no edge at all. Two taps of A inside a tenth of a second were one
   * press, every time, and only on a keyboard -- a real pad keeps `connected`
   * true and gets the release frame for free, which is why nothing on a desk
   * ever saw it.
   *
   * One more frame is the whole cost, and only after a tap.
   */
  let held = false;
  for (const down of prev.values()) if (down) held = true;
  const busy =
    connected || held || keyDown.size > 0 || keyLatch.size > 0 || frameHandlers.size > 0;
  if (!listening) {
    raf = 0;
    return;
  }
  if (busy) {
    raf = requestAnimationFrame(frame);
  } else {
    // `raf = 0` because this handle has already fired. Leaving a spent handle
    // in place is what let `wake()` believe a frame was pending when the only
    // thing pending was a timer -- see `wake`.
    raf = 0;
    idle = setTimeout(() => {
      idle = null;
      raf = requestAnimationFrame(frame);
    }, IDLE_MS);
  }
}

/**
 * Get the loop running, from any of the several things that should.
 *
 * A NON-ZERO HANDLE IS NOT PROOF THE LOOP IS ALIVE, and treating it as one made
 * this function -- the only route back from a stalled loop -- the one call
 * guaranteed not to take it. No browser runs rAF for a hidden, minimised or
 * occluded window: a handle taken just before the window went away sits there
 * un-run, and every later `wake()` saw it, concluded a frame was queued, and
 * returned. The player alt-tabs back to a controller that has stopped working
 * and only a reload brings it back.
 *
 * So the handle is trusted only while the loop has actually ticked recently.
 * Past `STALL_MS` it is cancelled and replaced, which cannot stack two loops
 * precisely because the old one is cancelled first.
 */
function wake(): void {
  if (typeof requestAnimationFrame !== "function") return;
  // An idle timer counts as running; promote it to a real frame rather than
  // stacking a second loop on top of it.
  if (idle !== null) {
    clearTimeout(idle);
    idle = null;
  } else if (raf) {
    const now = typeof performance !== "undefined" ? performance.now() : 0;
    if (lastTick !== 0 && now - lastTick < STALL_MS) return;
    cancelAnimationFrame(raf);
  }
  raf = requestAnimationFrame(frame);
}

function onKeyDown(event: KeyboardEvent): void {
  if (fieldKeeps(event.target, event.key)) return;
  const name = KEYS[event.key];
  if (!name) return;
  if (SWALLOW.has(event.key)) {
    /*
     * THE CAPTURE PHASE IS THE POINT, AND `Enter` IS WHY.
     *
     * `useCursorNav` implements A as "click the element the ring is on", which
     * is what stops the pad from ever drifting from the mouse. Several stops
     * are divs wearing `role="button"` -- a board card, a chair's card, a deck
     * tile -- because a `<button>` may not contain the divs a card face is made
     * of, and each carries its own `Enter`/`Space` handler so a keyboard can
     * press it. With the ring mounted on every screen those are two paths to
     * one action, and they run in order: React's handler fires first and takes
     * the deck, the ring re-resolves onto the control that opened the
     * catalogue, and our click a frame later presses THAT. One Enter chose a
     * deck and reopened the catalogue on top of the result.
     *
     * Listening in the capture phase and stopping propagation is what makes the
     * ring's path the only path -- for those three divs, for the native
     * activation a real `<button>` would have done, and for any control added
     * later that reaches for the same shortcut. It costs nothing anybody wanted:
     * `fieldKeeps` has already returned for anything with a caret in it, so
     * Enter still commits a name and still submits a pod code.
     */
    event.preventDefault();
    event.stopPropagation();
  }
  /*
   * An arrow the ring took off a field must not also move the caret.
   *
   * Without this the last press does both: focus leaves for the next stop and
   * the caret jumps to the other end of the text on the way out, so coming
   * back to the field finds it in a place nobody put it.
   */
  /*
   * ...and the same for the Left/Right a `<select>` no longer keeps: Chrome and
   * Firefox both change the selected option on those, so taking the key for the
   * ring without this would re-sort the catalogue on the way out of the box.
   */
  if (ARROWS.has(event.key) && (isField(event.target) || isSelect(event.target))) {
    event.preventDefault();
  }
  // The OS autorepeat would race our own ramp and win, so the ramp would never
  // be what the player is feeling.
  if (event.repeat) return;
  /*
   * A SECOND TAP BEFORE THE LOOP SAW THE FIRST ONE LET GO.
   *
   * The frame that fires a press records the key as down; only the NEXT frame
   * can record its release. "A button still recorded as down keeps the loop
   * awake", below in `frame`, makes sure that frame comes; it cannot make it
   * come sooner -- and a frame is a long time on
   * a slow machine, longer still when the press just opened something heavy.
   * Enter on "Change deck" opened the catalogue; Enter on the tile the ring
   * landed on arrived before the loop had drawn a frame since, so the loop
   * read it as the same key still held -- `down && was` -- and took no deck.
   * Measured on a CI runner at eleven frames a second, six presses in six
   * (`e2e/pod.spec.ts`, "puts the ring back on the control that opened it");
   * never on a developer machine, where the release frame lands in 16ms.
   *
   * The key was not held: it is not in `keyDown`, and its earlier latch was
   * already consumed. So this is a new press, and the record of the old one
   * is what the next frame must compare against.
   */
  if (!keyDown.has(name) && !keyLatch.has(name) && prev.get(name)) prev.set(name, false);
  keyDown.add(name);
  keyLatch.add(name);
  wake();
}

function onKeyUp(event: KeyboardEvent): void {
  const name = KEYS[event.key];
  if (!name) return;
  keyDown.delete(name);
  /*
   * A RELEASE IS AN EVENT THE LOOP HAS TO SEE.
   *
   * This did not wake, and the loop idles after 100ms of nothing changing --
   * so a key held on its own put the loop to sleep and the release was never
   * observed at all. Everything driven by a HOLD then stuck: the `R2` opponent
   * reader stayed up after `v` was let go, and the region dial stayed up after
   * `L2`.
   *
   * It only ever bit the keyboard fallback, for the same reason the key latch
   * exists: a real pad IS the poll, so its buttons cannot change without the
   * loop being the thing that notices.
   */
  wake();
}

/*
 * A pad is only readable by a focused document.
 *
 * No browser hands `getGamepads()` anything while the tab is in the background,
 * so a player who alt-tabs away and back would return to a loop idling against
 * an empty array. `pointerdown` is in the set as well as `focus` because a
 * click inside an already-focused window fires no `focus` event, and clicking
 * the page is exactly what somebody does when the controller "stopped working".
 * Cheap to re-arm, and it costs nothing when the loop is already busy.
 */
function onFocus(): void {
  wake();
}

/** Start listening. Idempotent; several roots may mount over a session. */
export function startPad(): void {
  if (listening || typeof window === "undefined") return;
  listening = true;
  // Capture, so the swallowed keys never reach a React handler. See `onKeyDown`.
  window.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("keyup", onKeyUp);
  /*
   * Bound because it is free, NOT because anything depends on it.
   *
   * See header point 4: this listener being the only wake-up is what made a
   * real controller undetectable. The loop now polls on its own, so this is
   * what it is in the prototype -- a way to notice a beat sooner.
   */
  window.addEventListener("gamepadconnected", wake);
  window.addEventListener("gamepaddisconnected", wake);
  window.addEventListener("focus", onFocus);
  window.addEventListener("pointerdown", onFocus);
  document.addEventListener("visibilitychange", onFocus);
  wake();
}

export function stopPad(): void {
  if (!listening) return;
  listening = false;
  window.removeEventListener("keydown", onKeyDown, true);
  window.removeEventListener("keyup", onKeyUp);
  window.removeEventListener("gamepadconnected", wake);
  window.removeEventListener("gamepaddisconnected", wake);
  window.removeEventListener("focus", onFocus);
  window.removeEventListener("pointerdown", onFocus);
  document.removeEventListener("visibilitychange", onFocus);
  if (raf) cancelAnimationFrame(raf);
  if (idle !== null) clearTimeout(idle);
  raf = 0;
  idle = null;
  lastTick = 0;
}

/**
 * What the input layer thinks is true, for a human holding a controller.
 *
 * There was no way to tell "the loop is dead" from "the browser never saw a
 * gamepad" from "the pad is seen and the ring is suppressed", and those three
 * want three completely different fixes. Every one of them is one call away
 * now. Dev only, and named like `window.__COMMANDERBLITZ_RING` beside it.
 *
 * `supported`, `secure` and `focused` are the three that separate an app
 * problem from an environment one, and they are here because on a desktop the
 * commonest failure is otherwise invisible. The Gamepad API is SECURE-CONTEXT
 * ONLY, so the app served over plain http to anything but localhost has no
 * `getGamepads` at all; no browser hands out a pad until it has seen a button
 * pressed while the page was FOCUSED; and a running Steam client with a desktop
 * layout bound to the controller swallows it before any browser sees it. All
 * three look identical from inside the app -- an empty `pads` -- and none of
 * them is fixable in this file.
 */
export function padDiagnostics(): {
  listening: boolean;
  connected: boolean;
  polling: boolean;
  supported: boolean;
  secure: boolean;
  focused: boolean;
  pads: string[];
  /**
   * How many listeners each button carries.
   *
   * Published because a DOUBLED listener is invisible from the outside and
   * behaves like a completely different bug: two `A` handlers make one press
   * two clicks, and the second lands on whatever the first click moved the ring
   * onto -- so pressing "Choose a deck" opened the catalogue AND took the first
   * deck in it, which reads as the catalogue flickering rather than as anything
   * to do with input. One number would have found it in a minute.
   */
  bound: Record<string, number>;
} {
  return {
    listening,
    connected,
    polling: raf !== 0 || idle !== null,
    supported: typeof navigator !== "undefined" && !!navigator.getGamepads,
    secure: typeof window === "undefined" || window.isSecureContext !== false,
    focused: typeof document !== "undefined" && document.hasFocus(),
    bound: Object.fromEntries(
      [...handlers.entries()].map(([button, set]) => [button, set.size]),
    ),
    pads: livePads().map(
      (pad) =>
        `#${pad.index} ${pad.id} [${pad.mapping || "non-standard"}] ` +
        `(${pad.buttons.length} buttons, ${pad.axes.length} axes)`,
    ),
  };
}

/**
 * Bind one intent. Returns an unsubscribe.
 *
 * Several listeners on one button coexist deliberately: `Table`, the wheel and
 * the game-over screen are independent React effects that mount and unmount on
 * their own schedules, and a single handler table -- which is what the
 * prototype had -- would have them overwrite each other.
 */
export function on(button: PadButton, handler: Handler): () => void {
  const bound = handlers.get(button) ?? new Set<Handler>();
  bound.add(handler);
  handlers.set(button, bound);
  wake();
  return () => bound.delete(handler);
}

/**
 * Which buttons currently have a listener.
 *
 * For one assertion and it is worth its keep: the hint bar advertises what each
 * button does, and for several rounds it advertised `L1 Zone`, `L2 Menu` and
 * `Y Read` with **nothing bound to any of the three**. An advertised button
 * that does nothing is worse than an unadvertised one -- it teaches the player
 * that the bar is not to be trusted, and nothing in the suite could see it,
 * because the bar renders spans and a span cannot fail to work.
 *
 * `tests/hintsBound.test.ts` compares every button `NAVIGATION_HINTS` names and
 * `verbsFor` can return against the bindings in the source. It would rather ask
 * this function, and cannot: `Table` is not mountable in that suite. See its
 * header.
 */
export function boundButtons(): PadButton[] {
  return [...handlers.entries()].filter(([, set]) => set.size > 0).map(([button]) => button);
}

/** Every press, whatever it was. Used to mean "get on with it" to narration. */
export function onAny(handler: AnyHandler): () => void {
  anyHandlers.add(handler);
  wake();
  return () => anyHandlers.delete(handler);
}

/** Per-frame state, for the holds: L2 opens the wheel, R2 expands a board. */
export function onFrame(handler: FrameHandler): () => void {
  frameHandlers.add(handler);
  wake();
  return () => {
    frameHandlers.delete(handler);
  };
}

export function onConnection(handler: (connected: boolean) => void): () => void {
  connectionHandlers.add(handler);
  handler(connected);
  return () => connectionHandlers.delete(handler);
}

export function isConnected(): boolean {
  return connected;
}

/**
 * Haptics, for an illegal move, a wall, damage taken, and the end of the game.
 *
 * THE RULE IS THAT RUMBLE IS ALWAYS REDUNDANT WITH SOMETHING VISIBLE. Firefox
 * in the Deck's desktop mode has no `vibrationActuator` at all, so haptics can
 * never be the only channel carrying a fact -- every call site here also draws
 * or says something.
 *
 * It rumbles the first pad that can, rather than pad zero, for the same reason
 * reading takes the whole set: pad zero may be a virtual device with no motors
 * sitting in front of the one in the player's hands.
 */
export function rumble(ms = 90, strong = 0.4): void {
  const pads = livePads() as (Gamepad & {
    vibrationActuator?: GamepadHapticActuator;
  })[];
  for (const pad of pads) {
    const actuator = pad.vibrationActuator;
    if (!actuator || typeof actuator.playEffect !== "function") continue;
    try {
      actuator.playEffect("dual-rumble", {
        duration: ms,
        strongMagnitude: strong,
        weakMagnitude: strong * 0.6,
      });
      return;
    } catch {
      // A pad that does not do haptics is not an error.
    }
  }
}

/** Test seam. */
export function resetPad(): void {
  stopPad();
  handlers.clear();
  anyHandlers.clear();
  frameHandlers.clear();
  connectionHandlers.clear();
  keyDown.clear();
  keyLatch.clear();
  prev.clear();
  dueAt.clear();
  runs.clear();
  hatSeen.clear();
  latched = null;
  connected = false;
}
