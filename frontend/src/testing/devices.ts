/**
 * The screens the gates run on, named once.
 *
 * ADR 0025: devices are named, not measured. The Storybook viewport global
 * (`.storybook/preview.tsx`) and the Playwright projects (`playwright.config.ts`)
 * both read this list, so a story and an e2e spec "on the iPhone 15" are on the
 * same size, and a phone is added to both gates by adding it here.
 *
 * A phone that Playwright ships a descriptor for names it in `descriptor`, and
 * `tests/devices.test.ts` holds the sizes below to that descriptor: Storybook
 * runs in the browser and cannot import Playwright, so the numbers are repeated
 * here and the test is what makes repeating them safe.
 *
 * A phone Playwright does not ship is held BY HAND from its maker's published
 * screen, with `descriptor: null` and the derivation beside it.
 */

import { type LayoutMode, layoutModeForSize } from "../logic/breakpoints";

export interface Size {
  width: number;
  height: number;
}

export interface Device {
  /** The key the Storybook viewport global and the Playwright project use. */
  id: string;
  /** What a reviewer sees in the toolbar. */
  name: string;
  /** Playwright's descriptor name, or `null` for one held by hand. */
  descriptor: string | null;
  portrait: Size;
  landscape: Size;
  /** The panel, as the descriptor reports it: portrait, whatever the orientation. */
  screen: Size;
  deviceScaleFactor: number;
  userAgent: string;
}

/**
 * Playwright's `iPhone 15` landscape viewport, against its screen: the Safari
 * chrome a phone held each way loses. The hand-written iPhone Duo takes its
 * viewport from its screen by the same subtraction.
 */
const IOS_SAFARI_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6 Mobile/15E148 Safari/604.1";

const IPHONE_15: Device = {
  id: "iphone15",
  name: "iPhone 15",
  descriptor: "iPhone 15",
  portrait: { width: 393, height: 659 },
  landscape: { width: 734, height: 343 },
  screen: { width: 393, height: 852 },
  deviceScaleFactor: 3,
  userAgent: IOS_SAFARI_UA,
};

const SAFARI_CHROME = {
  portrait: {
    width: IPHONE_15.screen.width - IPHONE_15.portrait.width,
    height: IPHONE_15.screen.height - IPHONE_15.portrait.height,
  },
  landscape: {
    width: IPHONE_15.screen.height - IPHONE_15.landscape.width,
    height: IPHONE_15.screen.width - IPHONE_15.landscape.height,
  },
};

/**
 * The iPhone Duo, folded: the outer display Apple publishes as 1398 by 2034
 * pixels at @3x, which is 466 by 678 CSS pixels exactly.
 */
const DUO_SCREEN: Size = { width: 1398 / 3, height: 2034 / 3 };

export const PHONES: readonly Device[] = [
  IPHONE_15,
  {
    id: "pixel7",
    name: "Pixel 7",
    descriptor: "Pixel 7",
    portrait: { width: 412, height: 839 },
    landscape: { width: 863, height: 360 },
    screen: { width: 412, height: 915 },
    deviceScaleFactor: 2.625,
    userAgent:
      "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.8010.12 Mobile Safari/537.36",
  },
  {
    id: "iphoneduo",
    name: "iPhone Duo (folded)",
    descriptor: null,
    portrait: {
      width: DUO_SCREEN.width - SAFARI_CHROME.portrait.width,
      height: DUO_SCREEN.height - SAFARI_CHROME.portrait.height,
    },
    landscape: {
      width: DUO_SCREEN.height - SAFARI_CHROME.landscape.width,
      height: DUO_SCREEN.width - SAFARI_CHROME.landscape.height,
    },
    screen: DUO_SCREEN,
    deviceScaleFactor: 3,
    userAgent: IOS_SAFARI_UA,
  },
];

/** The two larger screens, which have no descriptor to be held to. */
export const DESKTOP: Size = { width: 1600, height: 950 };
export const DECK: Size = { width: 1280, height: 800 };

export type Orientation = "portrait" | "landscape";

/** A viewport the gates run at: a device held one way, with the layout it gets. */
export interface Viewport {
  /** `<device id>` for portrait, `<device id>-landscape` for landscape. */
  id: string;
  name: string;
  size: Size;
  layout: LayoutMode;
}

function phoneViewport(device: Device, orientation: Orientation): Viewport {
  const size = device[orientation];
  return {
    id: orientation === "portrait" ? device.id : `${device.id}-landscape`,
    name: `${device.name}, ${orientation}`,
    size,
    layout: layoutModeForSize(size.width, size.height),
  };
}

/** Every viewport the Storybook toolbar offers, the wide board first. */
export const VIEWPORTS: readonly Viewport[] = [
  { id: "desktop", name: "Desktop", size: DESKTOP, layout: "desktop" },
  { id: "deck", name: "Steam Deck", size: DECK, layout: "handheld" },
  ...PHONES.flatMap((device) => [
    phoneViewport(device, "portrait"),
    phoneViewport(device, "landscape"),
  ]),
];

export function viewportById(id: string | undefined): Viewport | undefined {
  return VIEWPORTS.find((viewport) => viewport.id === id);
}

/** The phone viewports, for a story or spec that runs on each. */
export const PHONE_VIEWPORTS: readonly Viewport[] = VIEWPORTS.filter(
  (viewport) => viewport.layout === "phone",
);
