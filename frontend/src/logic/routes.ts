/**
 * The addresses, and the one decision that is not "match a path".
 *
 * Paths are shaped like the API resources they read -- `/pods/:code` beside
 * `/api/pods/{code}`, `/games/:id` beside `/api/games/{id}`. Plural collection,
 * identifier, nothing else. Two naming rules that disagree by an `s` is the kind
 * of thing that is free to get right once and expensive to notice later.
 *
 * Nothing here imports react-router. These are string functions, so the
 * decisions can be tested without a DOM, and a component that needs a path asks
 * for one rather than interpolating a template at the call site -- which is how
 * `/pods/gyre 8412` gets into somebody's address bar.
 */

import { normaliseCode } from "./lobby";

export function podPath(code: string): string {
  return `/pods/${encodeURIComponent(normaliseCode(code))}`;
}

export function gamePath(gameId: string): string {
  return `/games/${encodeURIComponent(gameId)}`;
}

export function deckPath(deckId: string): string {
  return `/decks/${encodeURIComponent(deckId)}`;
}

/**
 * The front door with a code in the field.
 *
 * Where a cold `/pods/CODE` lands: a link that arrives on a machine holding no
 * token for that pod cannot show the lobby, and the join flow already exists.
 */
export function joinPath(code: string): string {
  return `/?join=${encodeURIComponent(normaliseCode(code))}`;
}

/**
 * Which *screen* a path is, which is not the same as which path it is.
 *
 * This is the key on `<Routes>`, and `AnimatePresence` swaps whenever it
 * changes -- so it has to name the thing the player sees, not the URL. A
 * dossier opening over the catalogue is one screen with something on top of it:
 * giving `/decks/aesi` its own key would fade the catalogue out from under the
 * dossier, and lose the filters somebody just set. A different pod, on the other
 * hand, is a different room, so the code is part of the key.
 */
export function screenKey(pathname: string): string {
  if (pathname === "/") return "home";
  if (pathname === "/decks" || pathname.startsWith("/decks/")) return "decks";
  const pod = /^\/pods\/([^/]+)/.exec(pathname);
  if (pod) return `pod:${pod[1]}`;
  const game = /^\/games\/([^/]+)/.exec(pathname);
  if (game) return `game:${game[1]}`;
  return "404";
}

/** The name, in one place, because it is now in a tab as well as on a screen. */
export const BRAND = "Commander Blitz";

/**
 * What the tab says, which is not the same as which screen it is.
 *
 * `screenKey` answers "is this a different room" for `AnimatePresence`; this
 * answers "what would somebody call this in their history". The difference is
 * the dossier: it is the same *screen* as the catalogue and would be the same
 * key, but a tab reading "Decks" while a specific deck is open is fine, so the
 * two questions happen to agree here. They are still two questions.
 *
 * The pod's code is in the title on purpose. Four people with four tabs open on
 * four pods is the case this exists for.
 */
export function titleFor(pathname: string): string {
  const pod = /^\/pods\/([^/]+)/.exec(pathname);
  // No `decodeURIComponent`: a normalised code is letters, digits and a hyphen,
  // so `podPath`'s encode is a no-op on it and there is nothing to undo. It
  // would also throw on a hand-typed `/pods/%`, and a title must not throw.
  if (pod) return `Pod ${normaliseCode(pod[1])} · ${BRAND}`;
  if (pathname === "/") return BRAND;
  if (pathname === "/decks" || pathname.startsWith("/decks/")) return `Decks · ${BRAND}`;
  if (/^\/games\/[^/]+/.test(pathname)) return `At the table · ${BRAND}`;
  return `Not found · ${BRAND}`;
}
