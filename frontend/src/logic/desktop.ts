/**
 * The desktop's decisions, as string and boolean functions.
 *
 * The desktop build runs the game from a local server and goes to the hosted
 * site only to play with friends. Everything that follows from that -- what to
 * grey out when there is no connection, what address to hand the shell, how a
 * deck imported at home gets to the table -- is decided here, with no DOM and
 * no React, the same way `logic/routes.ts` decides addresses.
 */

import type { AppConfig, DeckSummary } from "../api/types";

/**
 * What the client assumes until `/api/config` answers, and what every component
 * sees when nothing provides a config at all (a story, a bare test). Hosted and
 * online: the site's behaviour, unchanged.
 */
export const HOSTED_DEFAULT: AppConfig = {
  mode: "hosted",
  online: true,
  remote_origin: null,
  app_version: "",
  content_version: "",
};

/** The hosted site, which the desktop treats as "where the friends are". */
export const HOSTED_ORIGIN = "https://commanderblitz.com";

/**
 * Whether a pod with other people is possible right now.
 *
 * On the site the answer is always yes: it cannot know, and a greyed-out Join
 * on the server you are already talking to would be nonsense. On the desktop
 * it is whether the hosted server answered the sidecar's last probe.
 */
export function canPlayOnline(config: AppConfig): boolean {
  return config.mode === "hosted" || config.online;
}

/**
 * Whether a Moxfield import can work. Same question: the import needs the
 * network, and on the desktop the sidecar's probe is the best proxy there is.
 */
export function canImport(config: AppConfig): boolean {
  return canPlayOnline(config);
}

/**
 * The imported decks whose art is not known to be all on this device.
 *
 * The desktop door finishes these before it draws, whenever the site answers:
 * an import the app was closed in the middle of, or one from before the
 * server kept count. Nothing on the site, nothing offline -- there is nobody
 * to fetch from -- and nothing at all once every deck says it is complete, so
 * an ordinary launch costs no request.
 */
export function decksToFinish(
  config: AppConfig,
  decks: readonly DeckSummary[] | undefined,
): string[] {
  if (config.mode !== "desktop" || !config.online || decks === undefined) return [];
  return decks
    .filter((deck) => deck.source === "moxfield" && deck.complete !== true)
    .map((deck) => deck.id);
}

/** At most this many imported decks ride along to the hosted site. */
export const MAX_HANDOFF_DECKS = 10;

/**
 * Where the shell takes the window for a pod with friends.
 *
 * `from=desktop` tells the hosted client it was sent, so it can offer a way
 * back. `join` is a code to land in. `import` is the Moxfield ids of the decks
 * imported here, so the hosted server can import them too -- a pod only seats
 * decks that server already has.
 */
export function onlineUrl(
  remoteOrigin: string | null,
  options: { join?: string; importIds?: readonly string[] } = {},
): string {
  const url = new URL("/", remoteOrigin ?? HOSTED_ORIGIN);
  url.searchParams.set("from", "desktop");
  if (options.join) url.searchParams.set("join", options.join);
  const ids = (options.importIds ?? []).filter(Boolean).slice(0, MAX_HANDOFF_DECKS);
  if (ids.length > 0) url.searchParams.set("import", ids.join(","));
  return url.toString();
}

/** Whether this page load was the desktop sending someone over. */
export function isHandoff(search: string): boolean {
  return new URLSearchParams(search).get("from") === "desktop";
}

/** The Moxfield ids the desktop asked the hosted server to import. */
export function handoffImports(search: string): string[] {
  const raw = new URLSearchParams(search).get("import") ?? "";
  return raw
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean)
    .slice(0, MAX_HANDOFF_DECKS);
}

/** The address `POST /api/decks/import` expects for a public id. */
export function moxfieldUrl(publicId: string): string {
  return `https://moxfield.com/decks/${encodeURIComponent(publicId)}`;
}
