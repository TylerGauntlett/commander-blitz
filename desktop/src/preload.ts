/**
 * `window.commanderblitz`, as the page sees it.
 *
 * Implements `CommanderBlitzBridge` from `frontend/src/desktop/bridge.ts` and
 * nothing more: the renderer gets a handful of named calls over IPC, never a
 * Node API. Exposed on the local page and on the hosted site, where the only
 * thing it is for is the way back; everywhere else the window never goes.
 */

import { contextBridge, ipcRenderer } from "electron";
import type {
  CommanderBlitzBridge,
  DesktopDiagnostics,
  UpdateReady,
} from "../../frontend/src/desktop/bridge.js";
import { IPC } from "./ipc.js";

function arg(name: string): string {
  const found = process.argv.find((a) => a.startsWith(`--${name}=`));
  return found ? found.slice(name.length + 3) : "";
}

const shellVersion = arg("cb-shell");
const remoteOrigin = arg("cb-remote");
const origin = window.location.origin;
const local = /^http:\/\/127\.0\.0\.1:\d+$/.test(origin);
const remote = origin === remoteOrigin;

if (local || remote) {
  let contentVersion = "";
  void ipcRenderer.invoke(IPC.diagnostics).then((d: DesktopDiagnostics) => {
    contentVersion = d.contentVersion;
  });

  const bridge: CommanderBlitzBridge = {
    get version() {
      return { shell: shellVersion, content: contentVersion };
    },
    onUpdate(listener) {
      if (!local) return () => undefined;
      const handler = (_event: unknown, update: UpdateReady) => listener(update);
      ipcRenderer.on(IPC.updateReady, handler);
      return () => ipcRenderer.off(IPC.updateReady, handler);
    },
    restartToUpdate() {
      if (!local) return Promise.resolve();
      return ipcRenderer.invoke(IPC.restartToUpdate);
    },
    openOnline(url) {
      return ipcRenderer.invoke(IPC.openOnline, url);
    },
    returnLocal() {
      return ipcRenderer.invoke(IPC.returnLocal);
    },
    onConnectivity(listener) {
      const handler = (_event: unknown, online: boolean) => listener(online);
      ipcRenderer.on(IPC.connectivity, handler);
      return () => ipcRenderer.off(IPC.connectivity, handler);
    },
    diagnostics() {
      return ipcRenderer.invoke(IPC.diagnostics);
    },
  };

  contextBridge.exposeInMainWorld("commanderblitz", bridge);
}
