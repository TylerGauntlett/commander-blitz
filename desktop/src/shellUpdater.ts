/**
 * Updates to the shell itself, which are rare and never restart anything.
 *
 * `electron-updater` reads the GitHub release feed that `electron-builder`
 * wrote into the package, downloads a newer AppImage in the background, and
 * -- with `autoInstallOnAppQuit` -- swaps it in when the app quits. That is
 * the whole of it. `quitAndInstall` is deliberately never called: it would
 * relaunch the process under Steam, which is the one thing this build does
 * not do (see `orchestrator.ts`). The page is told, so it can say "installs
 * when you quit", and the player quits when they like.
 *
 * Nothing happens outside a packaged build: there is no feed to read.
 */

import { app } from "electron";
import type { Logger } from "./logging.js";

export function watchShellUpdates(options: {
  log: Logger;
  onReady: (version: string) => void;
}): () => void {
  if (!app.isPackaged) return () => undefined;
  let stopped = false;
  void (async () => {
    const { autoUpdater } = await import("electron-updater");
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.logger = {
      info: (m: unknown) => options.log.info(`shell-update: ${String(m)}`),
      warn: (m: unknown) => options.log.warn(`shell-update: ${String(m)}`),
      error: (m: unknown) => options.log.error(`shell-update: ${String(m)}`),
      debug: () => undefined,
    };
    autoUpdater.on("update-downloaded", (info) => {
      if (!stopped) options.onReady(info.version);
    });
    autoUpdater.on("error", (error) => {
      // Offline is the common cause and not worth more than a line.
      options.log.info(`shell-update: ${error.message}`);
    });
    const check = () => {
      if (!stopped) void autoUpdater.checkForUpdates().catch(() => undefined);
    };
    setTimeout(check, 30_000);
    setInterval(check, 6 * 60 * 60 * 1000);
  })();
  return () => {
    stopped = true;
  };
}
