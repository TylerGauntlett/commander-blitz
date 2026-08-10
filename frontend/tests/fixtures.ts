/**
 * Moved to `src/testing/fixtures.ts` so stories can import them too -- `src/` is
 * the only tree the app, these tests and the Storybook glob all share.
 *
 * Re-exported from here rather than rewriting sixteen import lines, and because
 * `./fixtures` is the spelling every test in this directory already knows.
 */

export * from "../src/testing/fixtures";
