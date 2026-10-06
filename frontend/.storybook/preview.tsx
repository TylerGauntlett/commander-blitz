/**
 * The harness every story renders inside.
 *
 * Four things have to be true before a component of this app renders honestly
 * outside it, and each is handled once here rather than in a hundred stories:
 *
 *   1. The stylesheets exist. They are imported only by `main.tsx` in the app,
 *      so without this a story is unstyled markup and every visual claim it
 *      makes is meaningless.
 *   2. The UI store is pristine. It is module state, so one story's staged
 *      attackers are the next story's, and the failure looks like flake.
 *   3. Motion is held still *for the runner only*. A test needs determinism and
 *      a person needs to see the thing move; see `withMotion`.
 *   4. The component is where the app puts it. This is the one that matters most
 *      and is the easiest to get silently wrong -- see `withMount`.
 *
 * A story configures the harness through `parameters.automtg`, never by
 * reaching into the store itself -- that way the reset above stays the only
 * thing that has to know how to undo it.
 */

import type { Decorator, Preview } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useLayoutEffect, useState } from "react";

import "../src/theme.css";
// Before `board.css` and `room.css`, so either can tune the shared drifting
// layers it defines -- the same order `main.tsx` loads these in, which is the
// only reason a story looks like the app.
import "../src/styles/ambience.css";
import "../src/styles/cards.css";
import "../src/styles/board.css";
import "../src/styles/seat.css";
import "../src/styles/reader.css";
import "../src/styles/groups.css";
import "../src/styles/ui.css";
import "../src/styles/opening.css";
import "../src/styles/lobby.css";
import "../src/styles/room.css";
import "../src/styles/door.css";
import "../src/styles/pod.css";
import "../src/styles/shelf.css";
import "../src/styles/handheld.css";
import "../src/styles/phone.css";

import { setReducedMotionOverride } from "../src/fx/reducedMotion";
import { resetCursor, setCursor } from "../src/input/cursor";
import { stopRoot } from "../src/input/stops";
import { useUiStore } from "../src/state/uiStore";
import type { ArtMode } from "../src/testing/art";
import { artFor } from "../src/testing/art";
import type { MountId } from "../src/testing/mounts";
import { Mounted } from "../src/testing/mounts";

/** What a story may ask the harness for. */
export interface AutomtgParameters {
  /**
   * Where in the app this component hangs. Required -- see `withMount`.
   *
   * The chain is built from the app's own class names in `src/testing/mounts.tsx`,
   * so the component's size comes from the app's stylesheets rather than from
   * anything the story says.
   */
  mount?: MountId;
  /** Seed the UI store: selection, hover, staged combat, the open zone modal. */
  ui?: Partial<ReturnType<typeof useUiStore.getState>>;
  /** Override the art toolbar for one story -- `none` poses the plate. */
  art?: ArtMode;
  /** Entries pre-loaded into react-query, as `[queryKey, data]` pairs. */
  query?: [readonly unknown[], unknown][];
  /**
   * `real` lets this story animate under the runner too.
   *
   * The default holds motion still for tests and plays it in the browser. Opt in
   * only when the animation *is* the thing under test -- a hover that scales, for
   * instance, is a transform, and `reducedMotion` removes it.
   */
  motion?: "real" | "still";
  /** Let the progressive zoom actually measure. Off by default; see below. */
  zoomLock?: boolean;
  /**
   * Put the focus ring on a named stop before the story renders.
   *
   * For stories whose subject *is* the ring resting somewhere -- the hint bar's
   * verbs, FILL-IS-FOCUS on a control, the sheen on a card. In the app the
   * cursor is resolved by `FocusRing`'s layout effect; a story that renders a
   * fragment without one has to place it directly.
   */
  cursor?: string;
}

/*
 * Captured before any story runs. `getState()` returns the actions as well as
 * the data, so replacing the store with this restores the whole thing -- a
 * partial `setState` would leave a story's `selectedOid` behind.
 */
const PRISTINE = useUiStore.getState();

/*
 * `speed` and `muted` are read at store-*construction* time, not per render, so
 * by the time any `beforeEach` runs the store has already been built from
 * whatever this browser profile happened to hold. Writing them here, at module
 * scope, is what covers the very first story. The `beforeEach` covers the rest.
 *
 * Instant narration matters for the same reason motion does: a beat queue that
 * holds for 400ms per event is 400ms a play function has to wait for.
 */
try {
  localStorage.setItem("automtg.speed", "instant");
  localStorage.setItem("automtg.muted", "on");
} catch {
  // No storage in this context. The defaults are already what we want.
}

type ZoomWindow = Window & { __AUTOMTG_ZOOM_LOCK?: boolean };

/**
 * A fresh react-query client per story.
 *
 * Applied globally even though only the lobby uses react-query -- `Table` takes
 * its `game` as a prop and no `game/` component calls a hook. It costs nothing
 * where it is unused and removes the entire class of "why did this one story
 * explode with 'No QueryClient set'".
 *
 * `parameters.automtg.query` seeds the cache, which is what makes a lobby story
 * render its loaded state on first paint instead of a placeholder that resolves
 * a tick later and races the assertion.
 */
const withQueryClient: Decorator = (Story, context) => {
  // `useState` with an initializer rather than `useMemo` with a dependency on
  // the story id: what is actually wanted is one client per *mount*, and that is
  // what this expresses. A memo would have to name the things that identify a
  // story and would silently share a cache between any two that matched.
  const [client] = useState(() => {
    const fresh = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          refetchOnWindowFocus: false,
          staleTime: Number.POSITIVE_INFINITY,
        },
      },
    });
    const seeds = (context.parameters.automtg as AutomtgParameters | undefined)?.query ?? [];
    for (const [key, data] of seeds) fresh.setQueryData(key, data);
    return fresh;
  });

  return (
    <QueryClientProvider client={client}>
      <Story />
    </QueryClientProvider>
  );
};

/**
 * Motion, held still -- but only for the runner.
 *
 * A test needs determinism and a person needs to see the thing move. Holding
 * motion still for both meant the hand fan's lift, the card's hover and every
 * `layoutId` cross-fade simply did not happen when you opened Storybook to look
 * at them, which makes a visual suite that cannot show you the visuals.
 *
 * So the runner gets `reducedMotion="always"` and the browser gets the app's real
 * springs. `reducedMotion` is the setting that works because
 * `transition={{ duration: 0 }}` alone does not: `motion/springs.ts` exists so
 * that components import a preset and pass it as an explicit `transition={ease}`,
 * which beats `MotionConfig`'s default every time. `reducedMotion` overrides them.
 *
 * It still leaves opacity animating, which is why play functions use `findBy*`
 * rather than `getBy*`. That rule is now load-bearing rather than belt and
 * braces -- `Card.Tapped` has to wait for its transform because Motion writes it
 * on the first frame, not during render.
 *
 * `motion: "real"` opts a story back in, and a handful genuinely need it: a
 * hover that *scales* is a transform, so `reducedMotion` removes the very thing
 * under test. `ActionPanel.CommitSlabOnHover` is the case that found this -- it
 * asserted the slab stays inside its rail, and passed against the bug, because
 * the scale it was measuring had been configured away. An assertion that cannot
 * fail is worse than none.
 */
const inTestRunner = (): boolean =>
  (window as Window & { __STORY_TEST__?: boolean }).__STORY_TEST__ === true;

const withMotion: Decorator = (Story, context) => {
  const real = (context.parameters.automtg as AutomtgParameters | undefined)?.motion === "real";

  /*
   * The same decision, told to the effects layer.
   *
   * Particles, card actuators and screen shake are not Framer animations and
   * cannot read `MotionConfig` -- a canvas draw loop and a module-level
   * `burst()` have no React context around them. `fx/reducedMotion.ts` is the
   * channel they read instead, and it has to be set from the same place and on
   * the same rule, or a story would opt into real motion and still render an
   * empty canvas because headless Chromium asked for reduced motion.
   */
  setReducedMotionOverride(real ? false : inTestRunner() ? true : null);

  if (real) {
    /*
     * `never`, not "leave it alone". Headless Chromium reports
     * `prefers-reduced-motion: reduce` and Motion's default is to honour it, so
     * simply not wrapping would still leave the transforms switched off -- and a
     * story that opted in to test an animation would silently test nothing.
     */
    return (
      <MotionConfig reducedMotion="never">
        <Story />
      </MotionConfig>
    );
  }
  return inTestRunner() ? (
    <MotionConfig reducedMotion="always" transition={{ duration: 0 }}>
      <Story />
    </MotionConfig>
  ) : (
    <Story />
  );
};

/**
 * The chain of wrappers the app would have around this component.
 *
 * Required, and deliberately so. Every story used to inherit a generic
 * full-height `.screen` box by saying nothing, which is the wrapper the app gives
 * only `Table` and `PodLobby` -- so twelve components were drawn somewhere the app
 * never puts them, and `PlayerOrb`, which has no width of its own, spanned the
 * canvas instead of sitting in its 190px column. A default is how that happened,
 * so there is no default. `bare` and `screen` are still valid answers; they just
 * have to be chosen out loud.
 *
 * `--card-w-base` is deliberately not set anywhere in here. It lives on `:root`,
 * which is the iframe's own `html`, and Chromium resolves its `clamp()` for real
 * -- seeding it by hand would override the exact cascade these stories exist to
 * check. Same for every other size: see `src/testing/mounts.tsx`.
 */
const withMount: Decorator = (Story, context) => {
  const mount = (context.parameters.automtg as AutomtgParameters | undefined)?.mount;
  if (!mount) {
    // `bare` is a valid answer; it just has to be an answer. See mounts.tsx.
    throw new Error(`story "${context.title} / ${context.name}" declares no mount`);
  }
  if (mount === "bare") {
    return (
      <div className="sb-frame-bare" style={{ padding: "1rem" }}>
        <Story />
      </div>
    );
  }
  return (
    <Mounted mount={mount}>
      <Story />
    </Mounted>
  );
};

/**
 * The two attributes the controller layer reads, as toolbar switches.
 *
 * `data-input` decides whether the focus ring and the button glyphs are drawn
 * at all; `data-handheld` decides the compact layout. Both live on `<html>` in
 * the app -- no component subscribes to either -- so a decorator that stamps
 * them makes EVERY existing story reviewable in the new dimensions without one
 * of them being rewritten. Flipping "Input" to "Pad" on the action panel is the
 * review for "do the glyphs appear where they should".
 *
 * Stamped on the iframe's own `documentElement`, because that is where the app
 * puts them and where the stylesheet looks for them.
 *
 * ## `data-desktop` is stamped too, and it is not symmetry for its own sake
 *
 * The tester canvas is 1200x900, whatever `vite.config.ts` declares -- see the
 * note there for the four ways that were measured and reset. 1200 is inside
 * `HANDHELD_QUERY`'s `(max-width: 1366px)`, so **every story matched the
 * handheld query**, including every story in the project whose entire job is
 * proving the desktop board still works.
 *
 * So the toolbar is made authoritative rather than advisory: `data-desktop`
 * says "this story is being reviewed as the wide board, whatever the canvas
 * happens to be", and `styles/handheld.css` and `state/useHandheld.ts` both
 * treat an explicit choice as beating the query. Nothing in the app ever stamps
 * it, so the running client is untouched.
 */
const withInputMode: Decorator = (Story, context) => {
  const root = document.documentElement;
  const handheld = context.globals.handheld === "on";
  root.setAttribute("data-input", String(context.globals.input ?? "mouse"));
  // The hint bar is a setting, off by default in the app; stories review it
  // on, because several read it to know what the ring is standing on.
  root.setAttribute("data-hints", String(context.globals.hints ?? "on"));
  root.toggleAttribute("data-handheld", handheld);
  root.toggleAttribute("data-desktop", !handheld);
  return <Story />;
};

/**
 * Seed the cursor, for stories whose subject *is* the ring resting somewhere.
 *
 * `resolveCursor` runs from `FocusRing`'s layout effect in the app; a story
 * that renders a board fragment without one still wants the ring drawn, so this
 * places it directly. Cleared afterwards because the cursor is module state and
 * would otherwise leak into the next story.
 */
const withCursor: Decorator = (Story, context) => {
  const stop = (context.parameters.automtg as AutomtgParameters | undefined)?.cursor;
  useLayoutEffect(() => {
    if (!stop) return;
    /*
     * A stop has to EXIST before the cursor can be on it -- `setCursor`
     * validates against the document and refuses an id that is not there,
     * which is the behaviour the app depends on (a wheel spoke must not be
     * able to blank the ring by naming a control that is off screen).
     *
     * So a story naming a stop it does not itself render gets a stand-in,
     * appended inside `stopRoot()` so it is found whatever the mount chain
     * looks like. Zero-sized, so it never wins a navigation -- `candidatesIn`
     * drops empty boxes -- and removed with the story.
     */
    const root = stopRoot();
    let stub: HTMLElement | null = null;
    if (!root.querySelector("[data-stop]") || !setCursor(stop)) {
      stub = root.ownerDocument.createElement("div");
      stub.setAttribute("data-stop", stop);
      stub.setAttribute("data-story-stub", "");
      stub.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
      root.appendChild(stub);
      setCursor(stop);
    }
    return () => {
      resetCursor();
      stub?.remove();
    };
  }, [stop]);
  return <Story />;
};

const preview: Preview = {
  /*
   * Storybook's `beforeEach` runs before the story renders and can return a
   * cleanup, which is exactly the shape this needs. A `useEffect` in a decorator
   * would land after the first paint, so every story would flash its default
   * state before settling -- visible to the eye and, worse, occasionally
   * sampled by an assertion.
   */
  beforeEach: async ({ parameters, globals }) => {
    const automtg = (parameters.automtg ?? {}) as AutomtgParameters;
    const mode = (automtg.art ?? globals.art ?? "stub") as ArtMode;

    useUiStore.setState({ ...PRISTINE, speed: "instant", images: artFor(mode) }, true);
    if (automtg.ui) useUiStore.setState(automtg.ui);

    /*
     * Locked by default, for the reason `e2e/helpers.ts` locks it: a story
     * asserting the board holds still is asserting against a feature whose
     * entire job is to move it. The handful of stories that exist to exercise
     * the solver opt out with `zoomLock: false`.
     */
    const lock = automtg.zoomLock ?? true;
    (window as ZoomWindow).__AUTOMTG_ZOOM_LOCK = lock ? true : undefined;

    return () => {
      (window as ZoomWindow).__AUTOMTG_ZOOM_LOCK = undefined;
      useUiStore.setState({ ...PRISTINE }, true);
    };
  },

  decorators: [withCursor, withInputMode, withMount, withMotion, withQueryClient],

  parameters: {
    layout: "fullscreen",
    controls: { expanded: true },
    // Report, do not fail. The board has real contrast work to do and a gate
    // that fails on day one is a gate somebody switches off on day two.
    a11y: { test: "todo" },
    // `theme.css` owns the ground; a Storybook background would sit on top of
    // it and quietly change every contrast judgement.
    backgrounds: { disable: true },
  },

  globalTypes: {
    input: {
      description: "What the player is holding",
      toolbar: {
        title: "Input",
        icon: "browser",
        items: [
          { value: "mouse", title: "Mouse (no ring, no glyphs)" },
          { value: "keyboard", title: "Keyboard (ring, key labels)" },
          { value: "pad", title: "Gamepad (ring, A/B/X/Y)" },
        ],
        dynamicTitle: true,
      },
    },
    handheld: {
      description: "The compact 1280x800 layout",
      toolbar: {
        title: "Layout",
        icon: "mobile",
        items: [
          { value: "off", title: "Desktop" },
          { value: "on", title: "Handheld" },
        ],
        dynamicTitle: true,
      },
    },
    hints: {
      description: "The hint bar under the hand",
      toolbar: {
        title: "Hints",
        icon: "info",
        items: [
          { value: "on", title: "Hints shown" },
          { value: "off", title: "Hints hidden (the default)" },
        ],
        dynamicTitle: true,
      },
    },
    art: {
      description: "Where card art comes from",
      toolbar: {
        title: "Art",
        icon: "photo",
        items: [
          { value: "stub", title: "Stub (offline, deterministic)" },
          { value: "live", title: "Live /art (needs uvicorn)" },
          { value: "none", title: "No art (the plate)" },
        ],
        dynamicTitle: true,
      },
    },
  },

  initialGlobals: { art: "stub", input: "mouse", handheld: "off", hints: "on" },

  tags: ["autodocs"],
};

export default preview;
