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
