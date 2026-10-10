/**
 * Where the desktop app keeps what it writes.
 *
 * The AppImage is read-only, so everything that changes at runtime -- content
 * updates, imported decks and fetched art, logs, the download in progress --
 * lives in one per-user directory. On a Steam Deck that is
 * `~/.local/share/commanderblitz/`; `COMMANDERBLITZ_HOME` overrides it, which
 * is how a test (and `install.test.sh`) runs the whole thing in a scratch
 * directory.
 */

import { homedir } from "node:os";
import { join } from "node:path";

export interface AppPaths {
  /** The per-user root. Everything below is inside it. */
  home: string;
  /** `content/<version>/` -- installed content packages, one directory each. */
  content: string;
  /** What the server writes: imports, cached art. `COMMANDERBLITZ_GENERATED_DIR`. */
  generated: string;
  logs: string;
  /** A content tarball on its way in. */
  downloads: string;
  /** `{ current, previous }`: which content directory is live. */
  state: string;
}

export function defaultHome(
  platform: NodeJS.Platform = process.platform,
  env: NodeJS.ProcessEnv = process.env,
): string {
  if (env.COMMANDERBLITZ_HOME) return env.COMMANDERBLITZ_HOME;
  if (platform === "win32") {
    return join(env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "CommanderBlitz");
  }
  if (platform === "darwin") {
    return join(homedir(), "Library", "Application Support", "CommanderBlitz");
  }
  return join(env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "commanderblitz");
}

export function appPaths(home: string = defaultHome()): AppPaths {
  return {
    home,
    content: join(home, "content"),
    generated: join(home, "generated"),
    logs: join(home, "logs"),
    downloads: join(home, "downloads"),
    state: join(home, "state.json"),
  };
}
