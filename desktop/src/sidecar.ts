/**
 * The server, as a child process.
 *
 * `commanderblitz.server.desktop` (frozen as `commanderblitz-server`) prints one
 * line -- `READY {"port": …, "pid": …}` -- once its socket is bound and its
 * registry compiled, and nothing else on stdout. This module starts it, waits
 * for that line, pipes its stderr into `sidecar.log`, and stops it cleanly:
 * SIGTERM, a grace period, then SIGKILL. The shell never relaunches itself;
 * this is the only process that ever restarts, and it restarts inside the one
 * Steam is watching.
 *
 * `spawn`, `fetch` and the clock are injected so the tests can drive every
 * path -- early exit, no READY, a crash after READY, a stop that needs the
 * kill -- without a Python interpreter.
 */

import type { ChildProcess, SpawnOptions } from "node:child_process";
import { spawn as nodeSpawn } from "node:child_process";
import { EventEmitter } from "node:events";
import type { Logger } from "./logging.js";

export const READY_PREFIX = "READY ";

export interface SidecarSpec {
  /** The binary, or `python`; see `COMMANDERBLITZ_SIDECAR_CMD`. */
  command: string;
  args: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

export interface Ready {
  port: number;
  pid: number;
}

export type Spawn = (command: string, args: string[], options: SpawnOptions) => ChildProcess;

export interface SidecarOptions {
  log: Logger;
  sidecarLog: Logger;
  spawn?: Spawn;
  fetch?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  /** How long READY may take. The registry compile is the slow part. */
  readyTimeoutMs?: number;
  /** How long SIGTERM gets before SIGKILL. */
  graceMs?: number;
}

export class SidecarManager extends EventEmitter<{ exited: [number | null] }> {
  private child: ChildProcess | null = null;
  private ready: Ready | null = null;
  private readonly spawn: Spawn;
  private readonly fetchFn: typeof fetch;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly readyTimeoutMs: number;
  private readonly graceMs: number;
  private readonly log: Logger;
  private readonly sidecarLog: Logger;

  constructor(options: SidecarOptions) {
    super();
    this.log = options.log;
    this.sidecarLog = options.sidecarLog;
    this.spawn = options.spawn ?? nodeSpawn;
    this.fetchFn = options.fetch ?? fetch;
    this.sleep = options.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.readyTimeoutMs = options.readyTimeoutMs ?? 90_000;
    this.graceMs = options.graceMs ?? 8_000;
  }

  get current(): Ready | null {
    return this.ready;
  }

  get running(): boolean {
    return this.child !== null && this.child.exitCode === null;
  }

  /** Spawn and resolve with the READY line's contents. */
  async start(spec: SidecarSpec): Promise<Ready> {
    if (this.running) throw new Error("the sidecar is already running");
    this.log.info(`sidecar: ${spec.command} ${spec.args.join(" ")}`);
    const child = this.spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: spec.env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child = child;
    this.ready = null;

    const stderrTail: string[] = [];
    child.stderr?.setEncoding("utf8");
    child.stderr?.on("data", (chunk: string) => {
      for (const line of chunk.split(/\r?\n/)) {
        if (!line) continue;
        this.sidecarLog.raw(line);
        stderrTail.push(line);
        if (stderrTail.length > 40) stderrTail.shift();
      }
    });

    const ready = new Promise<Ready>((resolve, reject) => {
      let buffer = "";
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        this.log.error(`sidecar: no READY within ${this.readyTimeoutMs}ms`);
        child.kill("SIGKILL");
        reject(new Error(`the server did not start within ${this.readyTimeoutMs / 1000}s`));
      }, this.readyTimeoutMs);

      child.stdout?.setEncoding("utf8");
      child.stdout?.on("data", (chunk: string) => {
        if (settled) return;
        buffer += chunk;
        let newline = buffer.indexOf("\n");
        while (newline >= 0) {
          const line = buffer.slice(0, newline).replace(/\r$/, "");
          buffer = buffer.slice(newline + 1);
          if (line.startsWith(READY_PREFIX)) {
            try {
              const parsed = JSON.parse(line.slice(READY_PREFIX.length)) as Ready;
              settled = true;
              clearTimeout(timer);
              this.ready = parsed;
              this.log.info(`sidecar: ready on port ${parsed.port} (pid ${parsed.pid})`);
              resolve(parsed);
              return;
            } catch (error) {
              settled = true;
              clearTimeout(timer);
              reject(new Error(`unreadable READY line: ${line} (${String(error)})`));
              return;
            }
          }
          // Anything else on stdout is noise, but noise worth keeping.
          if (line) this.sidecarLog.raw(line);
          newline = buffer.indexOf("\n");
        }
      });

      child.once("error", (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.log.error(`sidecar: could not start: ${error.message}`);
        reject(error);
      });

      child.once("exit", (code) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        const why = stderrTail.slice(-10).join("\n");
        this.log.error(`sidecar: exited with ${code} before READY\n${why}`);
        reject(new Error(`the server exited with code ${code} before it was ready\n${why}`));
      });
    });

    child.once("exit", (code) => {
      this.log.info(`sidecar: exited with ${code}`);
      this.ready = null;
      this.emit("exited", code);
    });

    return ready;
  }

  /** Poll `/health` on `port` until it answers 200. */
  async waitHealthy(port: number, timeoutMs = 30_000): Promise<void> {
    const url = `http://127.0.0.1:${port}/health`;
    const started = Date.now();
    let lastError = "";
    while (Date.now() - started < timeoutMs) {
      try {
        const response = await this.fetchFn(url, { signal: AbortSignal.timeout(3_000) });
        if (response.ok) return;
        lastError = `status ${response.status}`;
      } catch (error) {
        lastError = String(error);
      }
      if (!this.running) throw new Error("the server exited while being checked");
      await this.sleep(250);
    }
    throw new Error(`the server did not answer /health within ${timeoutMs}ms (${lastError})`);
  }

  /** SIGTERM, wait, SIGKILL. Resolves once the process has exited. */
  async stop(): Promise<void> {
    const child = this.child;
    if (!child || child.exitCode !== null) {
      this.child = null;
      this.ready = null;
      return;
    }
    const exited = new Promise<void>((resolve) => child.once("exit", () => resolve()));
    this.log.info("sidecar: stopping");
    child.kill("SIGTERM");
    const graceful = await Promise.race([
      exited.then(() => true),
      this.sleep(this.graceMs).then(() => false),
    ]);
    if (!graceful) {
      this.log.warn(`sidecar: still running after ${this.graceMs}ms, killing`);
      child.kill("SIGKILL");
      await exited;
    }
    this.child = null;
    this.ready = null;
  }
}
