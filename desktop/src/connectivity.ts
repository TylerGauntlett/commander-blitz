/**
 * Is the hosted site reachable? Asked every half-minute, announced on change.
 *
 * The sidecar asks the same question for `/api/config`, and the client polls
 * that; this is the faster path. The shell notices the moment the answer
 * flips and tells the page through the bridge, which refetches -- so a Deck
 * that just joined the Wi-Fi sees the Online card come back without waiting
 * out a poll.
 */

import { EventEmitter } from "node:events";
import type { Logger } from "./logging.js";

export interface ConnectivityOptions {
  origin: string;
  log: Logger;
  fetch?: typeof fetch;
  intervalMs?: number;
  timeoutMs?: number;
  setTimer?: typeof setTimeout;
  clearTimer?: typeof clearTimeout;
}

export class ConnectivityWatcher extends EventEmitter<{ change: [boolean] }> {
  private readonly url: string;
  private readonly log: Logger;
  private readonly fetchFn: typeof fetch;
  private readonly intervalMs: number;
  private readonly timeoutMs: number;
  private readonly setTimer: typeof setTimeout;
  private readonly clearTimer: typeof clearTimeout;
  private handle: ReturnType<typeof setTimeout> | null = null;
  private last: boolean | null = null;

  constructor(options: ConnectivityOptions) {
    super();
    this.url = `${options.origin.replace(/\/$/, "")}/health`;
    this.log = options.log;
    this.fetchFn = options.fetch ?? fetch;
    this.intervalMs = options.intervalMs ?? 30_000;
    this.timeoutMs = options.timeoutMs ?? 3_000;
    this.setTimer = options.setTimer ?? setTimeout;
    this.clearTimer = options.clearTimer ?? clearTimeout;
  }

  /** The last answer, or `null` before the first probe. */
  get online(): boolean | null {
    return this.last;
  }

  async probe(): Promise<boolean> {
    let online = false;
    try {
      const response = await this.fetchFn(this.url, {
        signal: AbortSignal.timeout(this.timeoutMs),
        cache: "no-store",
      });
      online = response.ok;
    } catch {
      online = false;
    }
    if (online !== this.last) {
      this.log.info(`connectivity: ${online ? "online" : "offline"}`);
      this.last = online;
      this.emit("change", online);
    }
    return online;
  }

  start(): void {
    if (this.handle) return;
    const tick = async () => {
      await this.probe();
      this.handle = this.setTimer(() => void tick(), this.intervalMs);
    };
    this.handle = this.setTimer(() => void tick(), 0);
  }

  stop(): void {
    if (this.handle) this.clearTimer(this.handle);
    this.handle = null;
  }
}
