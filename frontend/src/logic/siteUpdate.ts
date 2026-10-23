/**
 * Whether the site has moved to a build this page did not load.
 *
 * A deploy hands the site to a new process without dropping a game (ADR 0023),
 * so the page keeps working; it is simply running yesterday's client against
 * today's server. `index.html` is never cached and the bundles are hashed, so a
 * reload is all it takes -- this only decides when to say one is due.
 *
 * The version a page loaded is the first one `/api/config` answered with. A
 * page loaded in the instant between the old build's `index.html` and the new
 * build's first answer would not notice, and would pick up the next deploy.
 */

import type { AppConfig } from "../api/types";

/** The version the site now runs, when it is not the one this page loaded. */
export function siteUpdate(loaded: string, config: AppConfig): string | null {
  if (config.mode !== "hosted") return null;
  if (!loaded || !config.app_version) return null;
  return config.app_version === loaded ? null : config.app_version;
}
