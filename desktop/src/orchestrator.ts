/**
 * Applying a content update: restart the server in place, or back out.
 *
 * THE ELECTRON PROCESS NEVER RESTARTS. Steam Game Mode watches the process it
 * launched, and what it does when that process is replaced by another cannot
 * be tested without a Deck -- so it is designed out. What restarts is the
 * server: stop it, point the state at the new content, start it from there,
 * wait for `/health`, reload the window. If any of that fails, the pointer
 * goes back, the old server comes up again, and the window reloads onto it.
 * The player sees a few seconds of splash either way.
 *
 * Everything this touches is injected, so the tests can make the new server
 * fail to start and watch the rollback happen.
 */

import type { ContentManager } from "./content.js";
import type { Logger } from "./logging.js";
import type { Ready, SidecarManager, SidecarSpec } from "./sidecar.js";

export interface RestartOutcome {
  ok: boolean;
  /** The content version the server is now running. */
  version: string;
  rolledBack: boolean;
  error?: string;
}

export interface RestartOptions {
  sidecar: SidecarManager;
  content: ContentManager;
  /** The content version to switch to. */
  target: string;
  /** How to start the server from a content directory. */
  specFor: (contentDir: string) => SidecarSpec;
  /** Point the window at the (new) port. */
  reloadWindow: (ready: Ready) => Promise<void> | void;
  log: Logger;
  healthTimeoutMs?: number;
}

export async function restartInPlace(options: RestartOptions): Promise<RestartOutcome> {
  const { sidecar, content, target, specFor, reloadWindow, log } = options;
  const healthTimeoutMs = options.healthTimeoutMs ?? 60_000;
  const was = await content.current();

  const bringUp = async (version: string): Promise<Ready> => {
    const dir = content.dirFor(version);
    const ready = await sidecar.start(specFor(dir));
    await sidecar.waitHealthy(ready.port, healthTimeoutMs);
    return ready;
  };

  log.info(`restart: ${was.version} -> ${target}`);
  await sidecar.stop();
  await content.activate(target);
  try {
    const ready = await bringUp(target);
    await reloadWindow(ready);
    log.info(`restart: running ${target}`);
    return { ok: true, version: target, rolledBack: false };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log.error(`restart: ${target} failed to start: ${message}`);
    await sidecar.stop().catch(() => undefined);
    const back = await content.rollback();
    try {
      const ready = await bringUp(back);
      await reloadWindow(ready);
      log.warn(`restart: rolled back to ${back}`);
      return { ok: false, version: back, rolledBack: true, error: message };
    } catch (second) {
      const again = second instanceof Error ? second.message : String(second);
      log.error(`restart: rollback to ${back} also failed: ${again}`);
      return {
        ok: false,
        version: back,
        rolledBack: false,
        error: `${message}; then ${again}`,
      };
    }
  }
}
