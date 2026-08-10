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
 *   3. Motion is off. `layoutId` transitions and hover springs are the reason a
 *      `getByTestId` immediately after a click can genuinely miss.
 *   4. The board has a height. This one is subtle and is explained at
 *      `withFrame` below.
 *
 * A story configures the harness through `parameters.automtg`, never by
 * reaching into the store itself -- that way the reset above stays the only
 * thing that has to know how to undo it.
 */

import type { Decorator, Preview } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useState } from "react";

import "../src/theme.css";
import "../src/styles/cards.css";
import "../src/styles/board.css";
import "../src/styles/ui.css";
import "../src/styles/lobby.css";

import { useUiStore } from "../src/state/uiStore";
import type { ArtMode } from "../src/testing/art";
import { artFor } from "../src/testing/art";

/** What a story may ask the harness for. */
export interface AutomtgParameters {
  /** Seed the UI store: selection, hover, staged combat, the open zone modal. */
  ui?: Partial<ReturnType<typeof useUiStore.getState>>;
  /** Override the art toolbar for one story -- `none` poses the plate. */
  art?: ArtMode;
  /** Entries pre-loaded into react-query, as `[queryKey, data]` pairs. */
  query?: [readonly unknown[], unknown][];
  /** `screen` gives a full-height board; `bare` is for atoms. */
  frame?: "screen" | "bare";
  /** Let the progressive zoom actually measure. Off by default; see below. */
  zoomLock?: boolean;
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
 * Motion, held still.
 *
 * `transition={{ duration: 0 }}` alone is not enough, and the reason is by
 * design: `motion/springs.ts` exists so that "components import a preset; they
 * never inline a transition", and those presets are passed as explicit
 * `transition={ease}` props, which beat `MotionConfig`'s default every time.
 * `reducedMotion="always"` is the one that wins -- it snaps transforms and
 * layout animations, `layoutId` cross-fades included, and leaves only opacity
 * animating.
 *
 * That residual opacity is why play functions still use `findBy*` rather than
 * `getBy*`. No amount of configuration removes that rule.
 */
const withMotion: Decorator = (Story) => (
  <MotionConfig reducedMotion="always" transition={{ duration: 0 }}>
    <Story />
  </MotionConfig>
);

/**
 * The box the story is drawn in.
 *
 * The height is not decoration. `board.css` gives `.table` `height: 100%`, and
 * `theme.css` only sets a height on `#root` -- but Storybook's canvas root is
 * `#storybook-root`. Left alone the chain resolves against auto height,
 * `useZoomFit` measures a table 0px tall, and `solveHandCardWidth` clamps every
 * card in the story to its 52px floor. The symptom is a board of postage
 * stamps and it looks like a CSS bug anywhere but here. `preview-head.html`
 * fixes the root; this fixes the wrapper.
 *
 * `--card-w-base` is deliberately *not* set here. It lives on `:root`, which is
 * the iframe's own `html`, and Chromium resolves its `clamp()` for real --
 * seeding it by hand would override the exact cascade these stories exist to
 * check.
 */
const withFrame: Decorator = (Story, context) => {
  const frame =
    (context.parameters.automtg as AutomtgParameters | undefined)?.frame ?? "screen";
  if (frame === "bare") {
    return (
      <div className="sb-frame-bare" style={{ padding: "1rem" }}>
        <Story />
      </div>
    );
  }
  return (
    <div className="screen" style={{ height: "100vh", width: "100%", overflow: "hidden" }}>
      <Story />
    </div>
  );
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

  decorators: [withFrame, withMotion, withQueryClient],

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

  initialGlobals: { art: "stub" },

  tags: ["autodocs"],
};

export default preview;
