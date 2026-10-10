/**
 * Fakes for the process, the network and the clock.
 *
 * A fake child process is an `EventEmitter` with two `PassThrough` streams
 * and a `kill` that records the signal; the test writes to its stdout to say
 * READY and emits `exit` to end it. A fake `fetch` answers from a table. Both
 * are what the real modules take as options, so nothing is mocked at the
 * module level.
 */

import type { ChildProcess, SpawnOptions } from "node:child_process";
import { EventEmitter } from "node:events";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PassThrough } from "node:stream";
import type { Spawn } from "../src/sidecar.js";

export class FakeChild extends EventEmitter {
  stdout = new PassThrough();
  stderr = new PassThrough();
  exitCode: number | null = null;
  pid = 4242;
  signals: string[] = [];
  spawnargs: string[];

  constructor(command: string, args: string[]) {
    super();
    this.spawnargs = [command, ...args];
  }

  kill(signal?: NodeJS.Signals | number): boolean {
    this.signals.push(String(signal ?? "SIGTERM"));
    return true;
  }

  /** What the server prints once its socket is bound. */
  ready(port = 8123, pid = 4242): void {
    this.stdout.write(`READY ${JSON.stringify({ port, pid })}\n`);
  }

  exit(code: number | null): void {
    this.exitCode = code;
    this.emit("exit", code, null);
  }
}

export function fakeSpawn(): { spawn: Spawn; children: FakeChild[]; options: SpawnOptions[] } {
  const children: FakeChild[] = [];
  const options: SpawnOptions[] = [];
  const spawn: Spawn = (command, args, opts) => {
    const child = new FakeChild(command, args);
    children.push(child);
    options.push(opts);
    return child as unknown as ChildProcess;
  };
  return { spawn, children, options };
}

export type Answer = { status?: number; body?: unknown; bytes?: Uint8Array } | Error;

/** A `fetch` that answers by exact URL, recording every call. */
export function fakeFetch(table: Record<string, Answer>): {
  fetch: typeof fetch;
  calls: string[];
} {
  const calls: string[] = [];
  const fetchFn = (async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const answer = table[url];
    if (answer === undefined) return new Response("not in the table", { status: 404 });
    if (answer instanceof Error) throw answer;
    if (answer.bytes) {
      // A fresh, exactly-sized buffer: a view's `.buffer` may be larger.
      const body = answer.bytes.slice().buffer as ArrayBuffer;
      return new Response(body, { status: answer.status ?? 200 });
    }
    return new Response(JSON.stringify(answer.body ?? {}), {
      status: answer.status ?? 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return { fetch: fetchFn, calls };
}

export async function scratch(): Promise<{ dir: string; done: () => Promise<void> }> {
  const dir = await mkdtemp(join(tmpdir(), "cb-desktop-"));
  return { dir, done: () => rm(dir, { recursive: true, force: true }) };
}

/** A sleep that resolves on the next macrotask, whatever `ms` says. */
export const instantSleep = () => new Promise<void>((resolve) => setImmediate(resolve));
