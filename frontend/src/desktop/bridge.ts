/**
 * What the desktop shell puts on `window`, and nothing else.
 *
 * The Electron preload script exposes `window.commanderblitz` with exactly this
 * shape, on the local origin and on the hosted one. Types only: this file is
 * the contract both packages compile against (`desktop/` includes it), so a
 * method renamed on one side fails the other side's build rather than a
 * player's Restart button.
 *
 * In a browser there is no bridge, and every caller treats that as the normal
 * case -- the site has no updates to apply and no sidecar to report on.
 */

export interface DesktopDiagnostics {
  shellVersion: string;
  contentVersion: string;
  contentDir: string;
  serverPort: number;
  serverPid: number;
  logsDir: string;
  /** What the last content update did, in a sentence, or `null` for never. */
  lastUpdate: string | null;
}

export interface UpdateReady {
  /** The version that is downloaded and waiting. */
  version: string;
  /**
   * `true` for a shell update, which installs when the app quits and never
   * restarts anything; `false` for a content update, which `restartToUpdate`
   * applies in place.
   */
  appliesOnQuit: boolean;
}

export interface CommanderBlitzBridge {
  version: { shell: string; content: string };
  /** Called when an update is downloaded. Returns the unsubscribe. */
  onUpdate(listener: (update: UpdateReady) => void): () => void;
  /** Stop the sidecar, swap the content, start it again, reload. */
  restartToUpdate(): Promise<void>;
  /** Take the window to the hosted site, for a pod with friends. */
  openOnline(url: string): Promise<void>;
  /** Come back from the hosted site to the local app. */
  returnLocal(): Promise<void>;
  /** Called whenever reachability of the hosted server changes. */
  onConnectivity(listener: (online: boolean) => void): () => void;
  diagnostics(): Promise<DesktopDiagnostics>;
}

declare global {
  interface Window {
    commanderblitz?: CommanderBlitzBridge;
  }
}

/** The bridge, or `undefined` in a browser. */
export function bridge(): CommanderBlitzBridge | undefined {
  return typeof window === "undefined" ? undefined : window.commanderblitz;
}
