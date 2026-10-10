/**
 * The channel names, in one place, so main and preload cannot disagree.
 *
 * Requests go renderer -> main (`ipcRenderer.invoke`); events go main ->
 * renderer (`webContents.send`). The shapes are the bridge's
 * (`frontend/src/desktop/bridge.ts`).
 */

export const IPC = {
  /** -> `DesktopDiagnostics` */
  diagnostics: "cb:diagnostics",
  /** `(url: string)` -> void. Only the hosted origin is allowed. */
  openOnline: "cb:online:open",
  /** -> void. Back to the local server. */
  returnLocal: "cb:online:return",
  /** -> void. Apply the downloaded content update by restarting the server. */
  restartToUpdate: "cb:update:restart",
  /** event: `UpdateReady` */
  updateReady: "cb:update:ready",
  /** event: `boolean` */
  connectivity: "cb:connectivity",
} as const;
