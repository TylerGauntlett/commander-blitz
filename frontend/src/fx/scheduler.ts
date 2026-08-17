/**
 * One frame loop for the whole board.
 *
 * There were two independent `requestAnimationFrame` loops before this: screen
 * shake in `FxLayer`, and the settle burst in `CombatArrows`. Adding particles
 * and card actuators would have made four, each starting and stopping on its
 * own schedule, each measuring `performance.now()` separately, and each free to
 * keep running after the thing it was animating had gone.
 *
 * So there is one, and it obeys two rules:
 *
 *   - **It does not run when nothing is subscribed.** The board is idle most of
 *     the time -- a Commander turn is mostly a human reading their hand -- and
 *     an idle rAF loop on a 90-card pod board is exactly the cost `CombatArrows`
 *     was rewritten to stop paying.
 *   - **A subscriber that returns `false` is dropped.** Effects here are
 *     finite: a burst, a lunge, a shake decay. Making "I am finished" the return
 *     value means no effect has to remember to unsubscribe itself, which is the
 *     bug that leaks a frame loop.
 *
 * `dt` is clamped. A backgrounded tab resumes with a multi-second gap, and an
 * unclamped step would teleport every particle off screen and fire every
 * follow-through at once on the frame the player comes back.
 */

/**
 * Called once per frame. Return `false` to unsubscribe, `true` to keep going.
 *
 * Required rather than optional. "Returns nothing" would have to mean one of
 * the two, and either reading is a trap: silence meaning *stop* drops any
 * ticker whose last statement happens to be a call, and silence meaning
 * *continue* leaks a frame loop for every effect that forgets. Saying so is one
 * word at each call site.
 */
export type Ticker = (dt: number, now: number) => boolean;

/**
 * The longest step any subscriber will see, in milliseconds.
 *
 * Four frames at 60Hz. Long enough that a dropped frame or two integrates
 * smoothly, short enough that a tab restored after a minute does not advance
 * a 600ms burst to its end in a single step.
 */
const MAX_DT = 64;

const tickers = new Set<Ticker>();
let frame = 0;
let last = 0;

function pump(now: number): void {
  const dt = Math.min(MAX_DT, now - last);
  last = now;

  // Iterate a copy: a ticker may subscribe another one (an impact spawning its
  // own follow-through is the normal case), and mutating the live set during
  // iteration would either skip a subscriber or run a brand-new one a frame
  // early with a `dt` measured before it existed.
  for (const ticker of [...tickers]) {
    let alive = false;
    try {
      alive = ticker(dt, now);
    } catch {
      // A thrown effect must not take the frame loop -- and therefore every
      // other effect on the board -- down with it. Drop it and carry on.
      alive = false;
    }
    if (!alive) tickers.delete(ticker);
  }

  frame = tickers.size > 0 ? requestAnimationFrame(pump) : 0;
}

/** Subscribe until the ticker returns `false`. Returns a manual unsubscribe. */
export function onFrame(ticker: Ticker): () => void {
  tickers.add(ticker);
  if (frame === 0) {
    // Seed `last` from the same clock rAF will report, so the first `dt` is one
    // frame rather than the milliseconds since the page loaded.
    last = performance.now();
    frame = requestAnimationFrame(pump);
  }
  return () => tickers.delete(ticker);
}

/**
 * A ticker that runs for a fixed duration and reports its own progress.
 *
 * Most effects on the board are this shape: a shake decaying over 320ms, a
 * lunge, a burst fading out. `t` runs 0 → 1 and the ticker is dropped on the
 * frame it reaches 1, so callers write the easing and nothing else.
 */
export function overTime(ms: number, step: (t: number) => void): () => void {
  if (ms <= 0) {
    step(1);
    return () => {};
  }
  let elapsed = 0;
  return onFrame((dt): boolean => {
    elapsed += dt;
    const t = Math.min(1, elapsed / ms);
    step(t);
    return t < 1;
  });
}

/** How many tickers are live. For tests and the perf trace. */
export function tickerCount(): number {
  return tickers.size;
}

/**
 * Drop every subscriber and stop the loop.
 *
 * For teardown between games and between tests -- `Table` already forgets card
 * rects on unmount for the same reason, and a shake left running across a
 * rematch would drive an element the new table does not have.
 */
export function stopAll(): void {
  tickers.clear();
  if (frame !== 0) {
    cancelAnimationFrame(frame);
    frame = 0;
  }
}
