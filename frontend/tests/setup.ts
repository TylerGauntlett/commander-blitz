/**
 * jsdom setup for the `unit` project.
 *
 * jsdom has no canvas. `HTMLCanvasElement.prototype.getContext` is a stub that
 * logs "Not implemented" to stderr and returns null, so any test that mounts the
 * board (`routing.test.tsx`'s rematch cases reach `ParticleLayer`) printed a stack
 * trace twice per run -- noise that would hide a real one. The component already
 * treats a null context as "no drawing surface, the sim still runs", so returning
 * null quietly is the behaviour the code expects; only the logging goes.
 */
Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  configurable: true,
  writable: true,
  value: () => null,
});

/*
 * jsdom has no ResizeObserver either. `useZoomFit` checks before it constructs
 * one and takes its pinned path; `CombatArrows` does not check, because it only
 * mounts once there is an attacker to draw an arrow for, which is exactly the
 * position `tableShape.test.tsx` renders. A no-op observer keeps the mount on
 * the same branch it takes in a real browser without a resize ever firing.
 */
class NoopResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
Object.defineProperty(globalThis, "ResizeObserver", {
  configurable: true,
  writable: true,
  value: NoopResizeObserver,
});

/*
 * And no `requestAnimationFrame` unless jsdom is told to pretend to be visual,
 * which vitest's environment does not. The pad poll loop and framer's own
 * scheduler both reach for it; two test files (`deckDossier`, `routing`) left
 * a frame request behind at teardown and vitest reported it as an unhandled
 * `ReferenceError` after every run. A timer-backed frame is what the tests that
 * already stub it per file (`lobbyBack.test.tsx`) use; this is the same thing,
 * once. Files that install their own on a fake clock still override it.
 */
if (typeof globalThis.requestAnimationFrame === "undefined") {
  globalThis.requestAnimationFrame = (cb: FrameRequestCallback) =>
    setTimeout(() => cb(performance.now()), 16) as unknown as number;
  globalThis.cancelAnimationFrame = (handle: number) =>
    clearTimeout(handle as unknown as ReturnType<typeof setTimeout>);
}

/*
 * Stop the pad after every test. The lobby and the table start its poll loop
 * on mount and nothing in a jsdom test unmounts the app, so the loop's idle
 * timer fired after an environment was torn down and reached for the
 * `requestAnimationFrame` above, which no longer existed -- an "unhandled
 * error" that failed whole runs in which every test had passed, from
 * whichever file happened to be last. Once, here, rather than per file.
 */
import { configure } from "@testing-library/react";
import { afterEach } from "vitest";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";

afterEach(() => {
  resetPad();
  resetInputMode();
});

/*
 * `waitFor` and `findBy*` give up after one second by default. That is a
 * budget, not an assertion: the desktop handoff in `handoff.test.tsx` runs an
 * import round trip and a navigation before the address it waits for appears,
 * and a CI runner carrying the whole vitest process in parallel took longer
 * than the default once. A wider budget changes nothing a passing test
 * observes and only costs time on a test that is already failing.
 */
configure({ asyncUtilTimeout: 5000 });
