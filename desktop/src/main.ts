/**
 * The shell: one window, one server, and the wiring between them.
 *
 * Everything that decides something lives in the modules beside this file
 * and is tested there; this is the Electron glue, kept thin enough to read in
 * one sitting. On launch:
 *
 *   1. work out where things are (`paths`), open the logs;
 *   2. find the current content (`ContentManager`) -- the bundled package on a
 *      fresh install, an installed update afterwards;
 *   3. show the splash, start the server from that content, wait for READY and
 *      `/health`, then point the window at `http://127.0.0.1:<port>/`;
 *   4. watch the connection, check for updates, and answer the page's bridge.
 *
 * It never relaunches itself (`orchestrator.ts` says why), and it never waits
 * on the network: an offline launch is the normal launch.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow, ipcMain, session } from "electron";
import type { DesktopDiagnostics, UpdateReady } from "../../frontend/src/desktop/bridge.js";
import { ConnectivityWatcher } from "./connectivity.js";
import { type ActiveContent, ContentManager, type ContentManifest } from "./content.js";
import { IPC } from "./ipc.js";
import { fileLogger } from "./logging.js";
import { restartInPlace } from "./orchestrator.js";
import { appPaths } from "./paths.js";
import { watchShellUpdates } from "./shellUpdater.js";
import { type Ready, SidecarManager, type SidecarSpec } from "./sidecar.js";
import { ContentUpdater, scheduleChecks } from "./updater.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Where pods with friends are. */
const REMOTE_ORIGIN = process.env.COMMANDERBLITZ_REMOTE ?? "https://commanderblitz.com";

/** Where releases are published; `content-latest.json` lives here. */
const RELEASES_BASE =
  process.env.COMMANDERBLITZ_RELEASES ??
  "https://github.com/TylerGauntlett/commander-blitz-releases/releases/latest/download";

const SHELL_VERSION = app.getVersion();
const SMOKE = process.argv.includes("--smoke");
const paths = appPaths();
const log = fileLogger(paths.logs, "shell");
const sidecarLog = fileLogger(paths.logs, "sidecar");

/*
 * Chromium under gamescope. Inside an AppImage there is no usable SUID
 * sandbox helper, and on SteamOS Chromium aborts over it BEFORE THIS FILE
 * RUNS -- so `--no-sandbox` has to arrive on the command line, which the
 * launcher `install.sh` writes provides. The switch below is for a launch
 * that got this far some other way, and it is not what saves the first one.
 * And X11, EXPLICITLY: the first build hinted
 * `ozone-platform-hint=auto`, which under gamescope's Wayland picked the
 * Wayland backend, and the result on a real Deck was Steam's spinner forever
 * -- no window ever reached the compositor, and the stuck client could not
 * even be force-closed. Gamescope always provides XWayland, and X11 is the
 * route every working Electron-on-Deck app takes. A `flags` file in the
 * per-user directory adds switches (`--disable-gpu` is the documented
 * fallback when the board draws nothing), one per line, and an explicit
 * `--ozone-platform=...` there would override this one.
 */
if (process.env.APPIMAGE) {
  app.commandLine.appendSwitch("no-sandbox");
  app.commandLine.appendSwitch("ozone-platform", "x11");
}
const flagsFile = join(paths.home, "flags");
if (existsSync(flagsFile)) {
  for (const line of readFileSync(flagsFile, "utf8").split("\n")) {
    const flag = line.trim().replace(/^--/, "");
    if (!flag || flag.startsWith("#")) continue;
    const [name, value] = flag.split("=", 2);
    app.commandLine.appendSwitch(name, value);
    log.info(`flags: --${flag}`);
  }
}

/** The bundled content: inside the AppImage, or the dev directory. */
function bundledDir(): string {
  if (app.isPackaged) return join(process.resourcesPath, "content");
  return process.env.COMMANDERBLITZ_CONTENT ?? join(HERE, "..", "dev-content");
}

const content = new ContentManager({
  root: paths.content,
  bundledDir: bundledDir(),
  statePath: paths.state,
  log,
});
const sidecar = new SidecarManager({ log, sidecarLog });
const connectivity = new ConnectivityWatcher({ origin: REMOTE_ORIGIN, log });
const updater = new ContentUpdater({
  releasesBase: RELEASES_BASE,
  shellVersion: SHELL_VERSION,
  content,
  downloadsDir: paths.downloads,
  log,
});

let win: BrowserWindow | null = null;
let running: ActiveContent | null = null;
let ready: Ready | null = null;
/** A content update downloaded and installed, waiting for Restart. */
let pending: ContentManifest | null = null;
let lastUpdate: string | null = null;
let stopping = false;

/**
 * How to start the server from a content directory.
 *
 * `COMMANDERBLITZ_SIDECAR_PYTHON` is the development override: the path to
 * an interpreter with the package installed (the repo's venv), which runs
 * `-m automtg.server.desktop` in the checkout. With it the data and client
 * come from the checkout too (`COMMANDERBLITZ_DATA_DIR`,
 * `COMMANDERBLITZ_CLIENT_DIR`) rather than from a content package. A path,
 * not a command line: this checkout's own path has a space in it.
 */
function specFor(contentDir: string): SidecarSpec {
  const dev = process.env.COMMANDERBLITZ_SIDECAR_PYTHON;
  const data = process.env.COMMANDERBLITZ_DATA_DIR ?? join(contentDir, "data");
  const client = process.env.COMMANDERBLITZ_CLIENT_DIR ?? join(contentDir, "client");
  const args = [
    "--port",
    "0",
    "--data-dir",
    data,
    "--client-dir",
    client,
    "--generated-dir",
    paths.generated,
    "--remote-origin",
    REMOTE_ORIGIN,
    "--content-version",
    running?.version ?? SHELL_VERSION,
  ];
  if (dev) {
    return {
      command: dev,
      args: ["-m", "automtg.server.desktop", ...args],
      cwd: join(HERE, "..", ".."),
    };
  }
  const binary = join(
    contentDir,
    "server",
    process.platform === "win32" ? "commanderblitz-server.exe" : "commanderblitz-server",
  );
  return { command: binary, args, cwd: join(contentDir, "server") };
}

function localUrl(): string {
  if (!ready) throw new Error("the server is not running");
  return `http://127.0.0.1:${ready.port}/`;
}

function isLocal(url: string): boolean {
  return ready !== null && url.startsWith(localUrl());
}

function isRemote(url: string): boolean {
  try {
    return new URL(url).origin === REMOTE_ORIGIN;
  } catch {
    return false;
  }
}

async function startServer(): Promise<Ready> {
  running = await content.current();
  log.info(
    `content: ${running.version} at ${running.dir}${running.bundled ? " (bundled)" : ""}`,
  );
  const started = await sidecar.start(specFor(running.dir));
  await sidecar.waitHealthy(started.port);
  ready = started;
  return started;
}

function createWindow(): BrowserWindow {
  const fullscreen = Boolean(process.env.SteamDeck) || process.argv.includes("--fullscreen");
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    fullscreen,
    autoHideMenuBar: true,
    backgroundColor: "#0b0a16",
    title: "Commander Blitz",
    /*
     * SHOWN AT ONCE, never on `ready-to-show`. That event fires on the first
     * paint, and on a Steam Deck the GPU process segfaults three times
     * before Chromium gives up and draws in software -- so the first paint
     * came late or never, the hidden window was never shown, and Game Mode
     * sat on its spinner with no window to hand the compositor. The
     * background colour is what a visible window shows until the splash
     * paints, which is all `ready-to-show` was buying.
     */
    show: true,
    webPreferences: {
      preload: join(HERE, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--cb-shell=${SHELL_VERSION}`, `--cb-remote=${REMOTE_ORIGIN}`],
    },
  });
  // The window goes two places and no further: the local server and the
  // hosted site. Anything else -- a link in a deck note, a redirect -- is
  // refused rather than turning the game into a browser.
  window.webContents.on("will-navigate", (event, url) => {
    if (!isLocal(url) && !isRemote(url)) {
      log.warn(`navigation refused: ${url}`);
      event.preventDefault();
    }
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

  // The hosted site went away mid-visit (the Wi-Fi dropped): back home.
  window.webContents.on("did-fail-load", (_event, code, description, url) => {
    if (isRemote(url) && code !== -3 /* aborted */) {
      log.warn(`hosted site failed to load (${code} ${description}); returning local`);
      void window.loadURL(`${localUrl()}?offline=1`);
    }
  });
  return window;
}

function send(channel: string, payload: unknown): void {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

async function showSplash(message: string): Promise<void> {
  if (!win) return;
  await win.loadFile(join(HERE, "..", "splash.html"));
  await win.webContents.executeJavaScript(`window.setStatus(${JSON.stringify(message)})`);
}

async function showFailure(message: string): Promise<void> {
  if (!win) return;
  const tail = sidecarLog.tail(40).join("\n");
  await win.webContents.executeJavaScript(
    `window.setFailure(${JSON.stringify(message)}, ${JSON.stringify(tail)}, ${JSON.stringify(paths.logs)})`,
  );
}

function diagnostics(): DesktopDiagnostics {
  return {
    shellVersion: SHELL_VERSION,
    contentVersion: running?.version ?? "",
    contentDir: running?.dir ?? "",
    serverPort: ready?.port ?? 0,
    serverPid: ready?.pid ?? 0,
    logsDir: paths.logs,
    lastUpdate,
  };
}

/** One check: find, download, install, and tell the page. Never throws. */
async function checkForContent(): Promise<void> {
  if (pending) return;
  const verdict = await updater.check();
  if (verdict.kind !== "available") {
    if (verdict.kind === "needs-shell") {
      lastUpdate = `${verdict.manifest.content_version} needs a newer app (installs on quit once downloaded)`;
    }
    return;
  }
  try {
    await updater.download(verdict.manifest, (received, total) => {
      if (total && received === total) log.info("update: download complete");
    });
    pending = verdict.manifest;
    lastUpdate = `${pending.content_version} downloaded, waiting for Restart`;
    const message: UpdateReady = { version: pending.content_version, appliesOnQuit: false };
    send(IPC.updateReady, message);
  } catch (error) {
    lastUpdate = `download of ${verdict.manifest.content_version} failed: ${String(error)}`;
    log.error(`update: ${lastUpdate}`);
  }
}

async function applyPendingUpdate(): Promise<void> {
  if (!pending || !win) return;
  const target = pending.content_version;
  pending = null;
  await showSplash(`Updating to ${target}…`);
  const outcome = await restartInPlace({
    sidecar,
    content,
    target,
    specFor,
    reloadWindow: async (fresh) => {
      ready = fresh;
      running = await content.current();
      await win?.loadURL(localUrl());
    },
    log,
  });
  lastUpdate = outcome.ok
    ? `updated to ${outcome.version}`
    : outcome.rolledBack
      ? `${target} failed to start; back on ${outcome.version} (${outcome.error})`
      : `${target} failed and so did the rollback: ${outcome.error}`;
  if (outcome.ok) void content.prune();
  if (!outcome.ok && !outcome.rolledBack) await showFailure(lastUpdate);
}

ipcMain.handle(IPC.diagnostics, () => diagnostics());
ipcMain.handle(IPC.openOnline, async (_event, url: string) => {
  if (!isRemote(url)) throw new Error(`refused: ${url} is not ${REMOTE_ORIGIN}`);
  log.info(`online: ${url}`);
  await win?.loadURL(url);
});
ipcMain.handle(IPC.returnLocal, async () => {
  await win?.loadURL(localUrl());
});
ipcMain.handle(IPC.restartToUpdate, async (event) => {
  // Only the local page may ask, and only at the door: the page enforces
  // "not mid-game"; this enforces "not from the hosted site".
  if (!isLocal(event.sender.getURL())) throw new Error("refused: not the local page");
  await applyPendingUpdate();
});

async function smoke(): Promise<number> {
  try {
    const started = await startServer();
    const response = await fetch(`http://127.0.0.1:${started.port}/api/config`);
    process.stdout.write(`${JSON.stringify(await response.json())}\n`);
    await sidecar.stop();
    return 0;
  } catch (error) {
    process.stderr.write(`smoke failed: ${String(error)}\n`);
    await sidecar.stop().catch(() => undefined);
    return 1;
  }
}

app.whenReady().then(async () => {
  if (SMOKE) {
    app.exit(await smoke());
    return;
  }
  // No permission prompts: nothing in the game asks for a camera or a
  // location, and a prompt under gamescope is a dialog nobody can reach.
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) =>
    callback(false),
  );

  win = createWindow();
  await showSplash("Starting the engine…");
  try {
    const started = await startServer();
    await win.loadURL(`http://127.0.0.1:${started.port}/`);
  } catch (error) {
    await showFailure(error instanceof Error ? error.message : String(error));
    return;
  }

  connectivity.on("change", (online) => send(IPC.connectivity, online));
  connectivity.start();
  const stopChecks = scheduleChecks(checkForContent);
  const stopShellUpdates = watchShellUpdates({
    log,
    onReady: (version) => {
      lastUpdate = `app ${version} downloaded; installs when you quit`;
      const message: UpdateReady = { version, appliesOnQuit: true };
      send(IPC.updateReady, message);
    },
  });
  sidecar.on("exited", (code) => {
    if (stopping) return;
    log.error(`the server exited unexpectedly with ${code}`);
    void showSplash("The engine stopped.").then(() =>
      showFailure(`The server exited with code ${code}.`),
    );
  });
  app.once("will-quit", () => {
    stopChecks();
    stopShellUpdates();
    connectivity.stop();
  });
});

// Stop the server before the window goes, and only once: `before-quit` fires
// again from the `app.quit()` below.
app.on("before-quit", (event) => {
  if (stopping) return;
  stopping = true;
  event.preventDefault();
  void sidecar
    .stop()
    .catch((error) => log.error(`stop: ${String(error)}`))
    .finally(() => app.quit());
});

app.on("window-all-closed", () => app.quit());
