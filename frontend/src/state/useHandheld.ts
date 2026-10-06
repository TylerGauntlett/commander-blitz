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
import { HANDHELD_QUERY, isHandheld, isPhone, PHONE_QUERY } from "../logic/breakpoints";

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

/**
 * Whether the viewport is a phone -- a handheld whose floors are too big for it.
 * See `logic/breakpoints.ts`. Always a subset of `useHandheld()`.
 */
export function usePhone(): boolean {
  return useSyncExternalStore(subscribePhone, isPhone, () => false);
}

/**
 * The same question, asked the way the STYLESHEET answers it.
 *
 * `handheld.css` is compact when the media query matches **or** when
 * `<html>` carries `data-handheld` -- the query re-values the rail tokens, the
 * attribute drives every structural rule. `App.tsx` stamps the attribute from
 * `useHandheld()` above, so in the running app the two are the same fact.
 *
 * They are not the same fact in Storybook. The layout toolbar sets the
 * attribute directly, because the alternative is resizing the browser, and a
 * component that consulted only `matchMedia` would then disagree with the CSS
 * around it -- the sheet would draw the compact board while the component still
 * rendered the desktop structure, which is exactly the "does not match the
 * game" failure the toolbar exists to let a reviewer catch.
 *
 * So anything that moves a NODE rather than a pixel reads this one, and it
 * matches the sheet by construction: attribute OR query, the same `or` the
 * stylesheet is written with.
 */
export function useHandheldLayout(): boolean {
  const byQuery = useHandheld();
  const stamped = useSyncExternalStore(subscribeAttr, readAttr, () => null);
  // An explicit choice beats the viewport. See `readAttr`.
  return stamped ?? byQuery;
}

/**
 * The layout the document has been TOLD it is, or `null` for "ask the query".
 *
 * `data-handheld` is stamped by `App.tsx` from the query itself, so in the
 * running client this and `byQuery` are the same fact and this branch never
 * decides anything.
 *
 * `data-desktop` exists for Storybook alone, and it is not symmetry for its own
 * sake. The Vitest tester canvas is 1200x900 whatever the project declares, and
 * 1200 is inside `(max-width: 1366px)` -- so without it every story in the
 * DESKTOP project matched the handheld query and rendered the compact body.
 * The toolbar has to be able to say "review this as the wide board" and be
 * believed, or a review surface that exists to compare the two layouts can only
 * ever show one of them.
 */
function readAttr(): boolean | null {
  if (typeof document === "undefined") return null;
  const root = document.documentElement;
  if (root.hasAttribute("data-handheld")) return true;
  if (root.hasAttribute("data-desktop")) return false;
  return null;
}

function subscribeAttr(onChange: () => void): () => void {
  if (typeof MutationObserver === "undefined" || typeof document === "undefined") {
    return () => undefined;
  }
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-handheld", "data-desktop"],
  });
  return () => observer.disconnect();
}
