/**
 * Whether the viewport wants the compact layout.
 *
 * `useSyncExternalStore` over a `MediaQueryList`, so the answer comes from the
 * same query string the stylesheet uses and the two provably cannot disagree --
 * `tests/breakpoints.test.ts` asserts the stylesheet contains it verbatim.
 *
 * React needs this as a boolean, rather than leaving it all to CSS, because the
 * handheld layout changes *structure* and not only style: the log and the stack
 * move out of a rail that stops existing, and the commit dock is portalled into
 * the foot. A media query cannot move a component into a different parent.
 */

import { useSyncExternalStore } from "react";
import {
  HANDHELD_QUERY,
  isCompact,
  isHandheld,
  isPhone,
  type LayoutMode,
  PHONE_QUERY,
} from "../logic/breakpoints";

const lists = new Map<string, MediaQueryList | null>();

function media(text: string): MediaQueryList | null {
  if (lists.has(text)) return lists.get(text) ?? null;
  let list: MediaQueryList | null = null;
  try {
    list = window.matchMedia(text);
  } catch {
    // jsdom without the shim, or a server render. Desktop is the safe default:
    // it is the layout every existing story and spec was written against.
    list = null;
  }
  lists.set(text, list);
  return list;
}

function subscriber(text: string) {
  return (onChange: () => void): (() => void) => {
    const list = media(text);
    if (!list) return () => undefined;
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  };
}

const subscribeHandheld = subscriber(HANDHELD_QUERY);
const subscribePhone = subscriber(PHONE_QUERY);

export function useHandheld(): boolean {
  return useSyncExternalStore(subscribeHandheld, isHandheld, () => false);
}

/** Whether the viewport matches the phone query. See `logic/breakpoints.ts`. */
export function usePhoneQuery(): boolean {
  return useSyncExternalStore(subscribePhone, isPhone, () => false);
}

/**
 * The layout the viewport wants, asked the way `App.tsx` stamps it: the phone
 * query first, then the handheld one. See `logic/breakpoints.ts:layoutMode`.
 */
export function useLayoutByQuery(): LayoutMode {
  const handheld = useHandheld();
  const phone = usePhoneQuery();
  return phone ? "phone" : handheld ? "handheld" : "desktop";
}

/**
 * The layout, asked the way the STYLESHEETS answer it.
 *
 * `App.tsx` stamps `<html data-layout>` from `useLayoutByQuery()` above, so in
 * the running app the stamp and the query are the same fact and the stamp
 * never decides anything.
 *
 * They are not the same fact in Storybook. The viewport global stamps the
 * layout of the device it names, and a story with no viewport runs on a 1200px
 * canvas stamped `desktop` -- inside `(max-width: 1366px)`, so a component that
 * consulted only `matchMedia` would draw the compact structure while the sheet
 * around it drew the wide one. So anything that moves a NODE rather than a
 * pixel reads this, and it matches the sheets by construction: the stamp, and
 * the query when there is none.
 */
export function useLayoutMode(): LayoutMode {
  const byQuery = useLayoutByQuery();
  const stamped = useSyncExternalStore(subscribeAttr, readAttr, () => null);
  return stamped ?? byQuery;
}

/** Whether the layout is one of the two compact ones (ADR 0025). */
export function useCompactLayout(): boolean {
  return isCompact(useLayoutMode());
}

/** Whether the layout is the phone's. A peer of the handheld one, never a subset. */
export function usePhone(): boolean {
  return useLayoutMode() === "phone";
}

/** The layout the document has been TOLD it is, or `null` for "ask the query". */
function readAttr(): LayoutMode | null {
  if (typeof document === "undefined") return null;
  const value = document.documentElement.getAttribute("data-layout");
  return value === "desktop" || value === "handheld" || value === "phone" ? value : null;
}

function subscribeAttr(onChange: () => void): () => void {
  if (typeof MutationObserver === "undefined" || typeof document === "undefined") {
    return () => undefined;
  }
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-layout"],
  });
  return () => observer.disconnect();
}
