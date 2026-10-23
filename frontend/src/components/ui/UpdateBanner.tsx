/**
 * "Update ready", the one line the app says about itself.
 *
 * On the **desktop** the shell downloads updates on its own and says so
 * through the bridge. Two kinds, told apart by `appliesOnQuit`:
 *
 * - A **content** update (the engine, the client, the cards) is applied in
 *   place: the shell stops its server, swaps the content, starts it again and
 *   reloads this page. The Restart button does that -- but NEVER MID-GAME. A
 *   restart at the table pulls the player out of the game, so the button waits
 *   at the door instead.
 * - A **shell** update (Electron itself, rare) installs when the app quits and
 *   never restarts anything. There is nothing to press, only something to
 *   know.
 *
 * On the **site** a deploy hands over to the new build without dropping a game
 * (ADR 0023), and what is left is this page running the old client. The banner
 * says so once `/api/config` answers with a version this page did not load,
 * and Reload is the player's to press: an automatic one could land in the
 * middle of a choice the client is still holding, so it never happens on its
 * own. At the table the line says the game carries over, because it does.
 *
 * Renders nothing until there is an update to talk about. Like Chrome's: it
 * waits, and it never interrupts.
 */

import { useEffect, useRef, useState } from "react";
import { useMatch } from "react-router";
import type { UpdateReady } from "../../desktop/bridge";
import { bridge } from "../../desktop/bridge";
import { siteUpdate } from "../../logic/siteUpdate";
import { useAppConfig } from "../../state/useAppConfig";

export function UpdateBanner() {
  const config = useAppConfig();
  const [update, setUpdate] = useState<UpdateReady | null>(null);
  const [restarting, setRestarting] = useState(false);
  const atTheTable = useMatch("/games/:gameId") !== null;
  // The first version the server answered with is the build this page loaded.
  const loaded = useRef("");
  if (!loaded.current && config.app_version) loaded.current = config.app_version;

  useEffect(() => bridge()?.onUpdate(setUpdate), []);

  const live = siteUpdate(loaded.current, config);
  if (live) return <SiteUpdate version={live} atTheTable={atTheTable} />;

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

/** The site moved on; a reload picks the new client up. */
function SiteUpdate({ version, atTheTable }: { version: string; atTheTable: boolean }) {
  return (
    <div className="toast toast--update" data-testid="update-banner" role="status">
      {atTheTable ? (
        <span>Version {version} is live — reload when you like; this game carries over.</span>
      ) : (
        <span>Version {version} is live.</span>
      )}
      <button
        type="button"
        className="toast__act"
        data-testid="update-reload"
        onClick={() => window.location.reload()}
      >
        Reload
      </button>
    </div>
  );
}
