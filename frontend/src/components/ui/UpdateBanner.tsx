/**
 * "Update ready — Restart", the desktop's one line about itself.
 *
 * The shell downloads updates on its own and says so through the bridge; this
 * is the only place the player hears about it. Two kinds, told apart by
 * `appliesOnQuit`:
 *
 * - A **content** update (the engine, the client, the cards) is applied in
 *   place: the shell stops its server, swaps the content, starts it again and
 *   reloads this page. The Restart button does that -- but NEVER MID-GAME.
 *   Games live only in the server's memory, so a restart at the table is a
 *   lost game, and the button waits at the door instead.
 * - A **shell** update (Electron itself, rare) installs when the app quits and
 *   never restarts anything. There is nothing to press, only something to
 *   know.
 *
 * Renders nothing on the site, and nothing on the desktop until an update has
 * actually arrived. Like Chrome's: it waits, and it never interrupts.
 */

import { useEffect, useState } from "react";
import { useMatch } from "react-router";
import type { UpdateReady } from "../../desktop/bridge";
import { bridge } from "../../desktop/bridge";
import { useAppConfig } from "../../state/useAppConfig";

export function UpdateBanner() {
  const config = useAppConfig();
  const [update, setUpdate] = useState<UpdateReady | null>(null);
  const [restarting, setRestarting] = useState(false);
  const atTheTable = useMatch("/games/:gameId") !== null;

  useEffect(() => bridge()?.onUpdate(setUpdate), []);

  if (config.mode !== "desktop" || !update) return null;

  const restart = () => {
    if (restarting || atTheTable) return;
    setRestarting(true);
    void bridge()
      ?.restartToUpdate()
      .finally(() => setRestarting(false));
  };

  return (
    <div className="toast toast--update" data-testid="update-banner" role="status">
      {update.appliesOnQuit ? (
        <span>Version {update.version} installs the next time you quit.</span>
      ) : atTheTable ? (
        <span>Version {update.version} is ready — it restarts after this game.</span>
      ) : (
        <span>Version {update.version} is ready.</span>
      )}
      {!update.appliesOnQuit && (
        <button
          type="button"
          className="toast__act"
          data-testid="update-restart"
          onClick={restart}
          aria-disabled={atTheTable || restarting ? true : undefined}
          disabled={restarting}
        >
          {restarting ? "Restarting…" : "Restart"}
        </button>
      )}
    </div>
  );
}
