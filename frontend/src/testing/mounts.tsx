/**
 * Where a component actually hangs in the app.
 *
 * A story that renders a component bare, or in a generic full-height box, is not
 * showing you the component -- it is showing you the component somewhere the app
 * never puts it. `PlayerOrb` declares no width at all; in the game it is whatever
 * `.mat__side`'s 190px grid column gives it, and full-bleed across a canvas it is
 * a different design wearing the same class names.
 *
 * So a mount is the app's own wrapper chain, by class name, and every size comes
 * out of the app's stylesheets rather than being restated here. **A layer may not
 * state a size.** There are exactly two things a layer is allowed to say for
 * itself:
 *
 *   1. Grid placement. Every layout container here is a grid whose tracks are
 *      filled by siblings a story does not render, so a lone child auto-places
 *      into track 1 -- `.table__body` is `232px | 1fr | 304px`, and a right rail
 *      that forgot to say `gridColumn: 3` renders at 232px, silently, looking
 *      entirely plausible. That is the trap this whole file exists to avoid.
 *   2. A value the app itself sets from JavaScript, which no stylesheet holds.
 *      `--card-w` on `.lane` is the only one, and it is set by calling the same
 *      `cardWidthVar(CARD_SCALE.own)` that `Lane.tsx` calls.
 *
 * `fill` is the third mechanism: an empty stand-in for a sibling whose box this
 * component is sized *against*. It carries that sibling's own class, so its size
 * still comes from the stylesheet -- the story is supplying the neighbour, not
 * the number.
 *
 * A note on `vh`. Eight sizes here are viewport-relative and there is one media
 * query (`theme.css`, `min-height: 1051px`), and in Storybook those resolve
 * against the *preview iframe* rather than the window. So the docs page and the
 * canvas legitimately draw different card sizes. The test runner is pinned to
 * 1600x950 (`vite.config.ts`), which is what makes the numbers stable there.
 */

import type { CSSProperties, ReactNode } from "react";
import { CARD_SCALE, cardWidthVar } from "../logic/cardSize";

interface Layer {
  /** The app's class on this element, verbatim. */
  className: string;
  /** Grid placement, or a value the app sets from JS. Never a size. */
  style?: CSSProperties;
  /** An empty stand-in sibling whose box this component is sized against. */
  fill?: string;
}

interface Mount {
  /** Where this is, in words. Shown on the docs page. */
  where: string;
  layers: Layer[];
}

/*
 * `.screen { height: 100% }` needs a definite ancestor. `preview-head.html` gives
 * `#storybook-root` one; this is belt and braces for the docs iframe, which sizes
 * to its content.
 */
const SCREEN: Layer = {
  className: "screen",
  style: { height: "100vh", width: "100%", overflow: "hidden" },
};
const SCREEN_CENTER: Layer = { ...SCREEN, className: "screen screen--center" };

const TABLE: Layer = { className: "table" };
const TABLE_BODY: Layer = { className: "table__body", style: { gridRow: 2 } };
const PLAY: Layer = { className: "play", style: { gridColumn: 2 } };
const MAT: Layer = { className: "mat" };
const MAT_COMPACT: Layer = { className: "mat mat--compact" };
const POD: Layer = { className: "pod" };
const TABLEWRAP: Layer = { className: "tablewrap", style: { gridRow: 2 } };
const CAT: Layer = { className: "cat" };
const DOS: Layer = { className: "dos" };

const board = [SCREEN, TABLE];
const tableBody = [...board, TABLE_BODY];
const play = [...tableBody, PLAY];
const playMine = [...play, { className: "play__mine", style: { gridRow: 2 } }];
const playOpponents = [...play, { className: "play__opponents" }];
const matSide = [...playMine, MAT, { className: "mat__side" }];
const matSideCompact = [...playOpponents, MAT_COMPACT, { className: "mat__side" }];
const matLanes = [...playMine, MAT, { className: "mat__lanes", style: { gridColumn: 2 } }];
const matLanesCompact = [
  ...playOpponents,
  MAT_COMPACT,
  { className: "mat__lanes", style: { gridColumn: 2 } },
];
const pod = [SCREEN, POD];
const podHand = [...pod, TABLEWRAP, { className: "podhand", style: { gridRow: 2 } }];
const catalog = [SCREEN, CAT];
const catalogBody = [...catalog, { className: "cat__body", style: { gridRow: 3 } }];
const dossier = [SCREEN, DOS];
const dossierBody = [...dossier, { className: "dos__body", style: { gridRow: 2 } }];

export const MOUNTS = {
  /** Nothing. For atoms with no layout contract -- a mana pip, a run of text. */
  bare: { where: "on its own", layers: [] },

  /** A whole route. `Table` and `PodLobby` get exactly this from `Screen`. */
  screen: { where: "a route root", layers: [SCREEN] },
  screenCenter: { where: "a centred route root", layers: [SCREEN_CENTER] },

  /* ---- the board ---- */
  trackRow: { where: "the phase ribbon's row of .table", layers: board },
  tableBody: { where: "the board's three-column body", layers: tableBody },
  tableFoot: {
    where: "the foot, under the board",
    layers: [...board, { className: "table__foot", style: { gridRow: 3 } }],
  },
  railLeft: {
    where: "the left rail (232px)",
    layers: [...tableBody, { className: "rail rail--left", style: { gridColumn: 1 } }],
  },
  railRight: {
    where: "the right rail (304px)",
    layers: [...tableBody, { className: "rail rail--right", style: { gridColumn: 3 } }],
  },
  /*
   * The right rail with the card preview above it, as a stand-in.
   *
   * `.acts { flex: 1 1 auto }`, `.acts__list`'s 74px floor and `.tools`'
   * no-wrap budget are all about the rail being *short*. Without the preview's
   * clamp above it the panel gets the whole 930px column instead of ~600px and
   * none of those constraints bind -- so the story would show a panel that
   * cannot demonstrate the thing it is designed around.
   */
  railRightUnderPreview: {
    where: "the right rail, under the card preview",
    layers: [
      ...tableBody,
      { className: "rail rail--right", style: { gridColumn: 3 }, fill: "preview" },
    ],
  },
  play: { where: "the middle column", layers: play },
  playMine: { where: "your half of the middle column", layers: playMine },
  playOpponents: { where: "the opponents' row", layers: playOpponents },

  /* ---- one player's mat ---- */
  matSide: { where: "your mat's info column (190px)", layers: matSide },
  matSideCompact: { where: "an opponent's info column (112px)", layers: matSideCompact },
  orbBody: {
    where: "inside your player orb",
    layers: [...matSide, { className: "orb" }, { className: "orb__body" }],
  },
  orbBodyCompact: {
    where: "inside an opponent's player orb",
    layers: [...matSideCompact, { className: "orb orb--compact" }, { className: "orb__body" }],
  },
  matLanes: { where: "your mat's battlefield column", layers: matLanes },
  bandFront: {
    where: "your front band (creatures 2fr, globals 1fr)",
    layers: [...matLanes, { className: "band band--front" }],
  },
  bandBack: {
    where: "your back band (lands, label in a 74px column)",
    layers: [...matLanes, { className: "band band--back" }],
  },
  bandFrontCompact: {
    where: "an opponent's front band",
    layers: [...matLanesCompact, { className: "band band--front" }],
  },
  /*
   * `--card-w` is the one value a layer sets, because no stylesheet holds it:
   * `Lane.tsx` writes it inline from its `cardScale` prop. Same call, so the two
   * cannot drift.
   */
  laneCards: {
    where: "a lane on your mat",
    layers: [
      ...matLanes,
      { className: "band band--front" },
      {
        className: "lane lane--creatures",
        style: { ["--card-w" as string]: cardWidthVar(CARD_SCALE.own) },
      },
      { className: "lane__cards" },
    ],
  },

  /* ---- the lobby ---- */
  pod: { where: "the pod screen", layers: pod },
  podHand: { where: "the row of seats", layers: podHand },
  podSlot: {
    where: "one seat's card",
    layers: [...podHand, { className: "slot" }, { className: "slot__card" }],
  },
  podRail: {
    where: "the pod's bottom rail",
    layers: [...pod, { className: "podrail", style: { gridRow: 3 } }],
  },
  door: { where: "the front door", layers: [SCREEN_CENTER, { className: "door" }] },
  homeFan: {
    where: "the fan of card backs on the front door",
    layers: [
      SCREEN_CENTER,
      { className: "door" },
      { className: "door__mid" },
      { className: "hero" },
      { className: "fan" },
    ],
  },

  /* ---- the two full-screen lobby overlays ---- */
  catalog: { where: "the deck catalogue", layers: catalog },
  catalogBody: { where: "the catalogue's scrolling body", layers: catalogBody },
  catalogPick: {
    where: "one deck's tile in the catalogue",
    layers: [
      ...catalogBody,
      { className: "rack" },
      { className: "pick" },
      { className: "pick__card" },
    ],
  },
  catalogFoot: {
    where: "the catalogue's footer strip",
    layers: [...catalog, { className: "cat__foot", style: { gridRow: 4 } }],
  },
  dossier: { where: "the deck dossier", layers: dossier },
  dossierBody: { where: "the dossier's scrolling body", layers: dossierBody },
  dossierCard: {
    where: "the dossier's commander card",
    layers: [...dossierBody, { className: "dos__top" }, { className: "dos__card" }],
  },
} satisfies Record<string, Mount>;

export type MountId = keyof typeof MOUNTS;

/** Wrap `children` in the chain the app would have around them. */
export function Mounted({ mount, children }: { mount: MountId; children: ReactNode }) {
  const found: Mount | undefined = MOUNTS[mount];
  if (!found) {
    throw new Error(
      `unknown mount "${mount}". Add it to src/testing/mounts.tsx, naming the chain ` +
        "the app actually renders -- do not reach for `bare`.",
    );
  }
  return found.layers.reduceRight<ReactNode>(
    (inner, layer) => (
      <div className={layer.className} style={layer.style}>
        {layer.fill ? <div className={layer.fill} aria-hidden="true" /> : null}
        {inner}
      </div>
    ),
    children,
  );
}
