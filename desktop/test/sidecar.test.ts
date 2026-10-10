/**
 * The sidecar's lifecycle against a fake child process.
 */

import { describe, expect, it, vi } from "vitest";
import { memoryLogger } from "../src/logging.js";
import { SidecarManager } from "../src/sidecar.js";
import { fakeFetch, fakeSpawn, instantSleep } from "./helpers.js";

const SPEC = { command: "commanderblitz-server", args: ["--port", "0"] };

function manager(overrides: Partial<ConstructorParameters<typeof SidecarManager>[0]> = {}) {
  const spawned = fakeSpawn();
  const log = memoryLogger();
  const sidecarLog = memoryLogger();
  const sidecar = new SidecarManager({
    log,
    sidecarLog,
    spawn: spawned.spawn,
    sleep: instantSleep,
    readyTimeoutMs: 200,
    graceMs: 50,
    ...overrides,
  });
  return { sidecar, spawned, log, sidecarLog };
}

describe("start", () => {
  it("resolves with the READY line's port and pid", async () => {
    const { sidecar, spawned } = manager();
    const starting = sidecar.start(SPEC);
    const child = spawned.children[0];
    child.ready(8123, 99);
    await expect(starting).resolves.toEqual({ port: 8123, pid: 99 });
    expect(sidecar.current).toEqual({ port: 8123, pid: 99 });
    expect(sidecar.running).toBe(true);
    expect(spawned.options[0].stdio).toEqual(["ignore", "pipe", "pipe"]);
  });

  it("ignores chatter before READY, and keeps it in the sidecar log", async () => {
    const { sidecar, spawned, sidecarLog } = manager();
    const starting = sidecar.start(SPEC);
    const child = spawned.children[0];
    child.stderr.write("INFO:     Started server process\n");
    child.stdout.write('not ready yet\nREADY {"port": 1, "pid": 2}\n');
    await expect(starting).resolves.toEqual({ port: 1, pid: 2 });
    expect(sidecarLog.lines).toContain("INFO:     Started server process");
    expect(sidecarLog.lines).toContain("not ready yet");
  });

  it("rejects when the process exits first, quoting its stderr", async () => {
    const { sidecar, spawned } = manager();
    const starting = sidecar.start(SPEC);
    const child = spawned.children[0];
    child.stderr.write("ModuleNotFoundError: No module named 'automtg'\n");
    await new Promise((r) => setImmediate(r));
    child.exit(1);
    await expect(starting).rejects.toThrow(/exited with code 1[\s\S]*ModuleNotFoundError/);
    expect(sidecar.running).toBe(false);
  });

  it("rejects, and kills, when READY never comes", async () => {
    const { sidecar, spawned } = manager({ readyTimeoutMs: 30 });
    const starting = sidecar.start(SPEC);
    await expect(starting).rejects.toThrow(/did not start/);
    expect(spawned.children[0].signals).toEqual(["SIGKILL"]);
  });

  it("rejects an unreadable READY line rather than guessing a port", async () => {
    const { sidecar, spawned } = manager();
    const starting = sidecar.start(SPEC);
    spawned.children[0].stdout.write("READY not json\n");
    await expect(starting).rejects.toThrow(/unreadable READY/);
  });

  it("refuses to start twice", async () => {
    const { sidecar, spawned } = manager();
    const starting = sidecar.start(SPEC);
    spawned.children[0].ready();
    await starting;
    await expect(sidecar.start(SPEC)).rejects.toThrow(/already running/);
  });

  it("announces a crash after READY", async () => {
    const { sidecar, spawned } = manager();
    const exited = vi.fn();
    sidecar.on("exited", exited);
    const starting = sidecar.start(SPEC);
    spawned.children[0].ready();
    await starting;
    spawned.children[0].exit(137);
    expect(exited).toHaveBeenCalledWith(137);
    expect(sidecar.current).toBeNull();
  });
});

describe("waitHealthy", () => {
  it("polls until /health answers", async () => {
    let attempts = 0;
    const fetchFn = (async () => {
      attempts += 1;
      if (attempts < 3) throw new Error("ECONNREFUSED");
      return new Response("{}", { status: 200 });
    }) as typeof fetch;
    const { sidecar, spawned } = manager({ fetch: fetchFn });
    const starting = sidecar.start(SPEC);
    spawned.children[0].ready(8123);
    await starting;
    await sidecar.waitHealthy(8123, 5_000);
    expect(attempts).toBe(3);
  });

  it("gives up when the process dies while being checked", async () => {
    const { fetch: fetchFn } = fakeFetch({
      "http://127.0.0.1:8123/health": new Error("ECONNREFUSED"),
    });
    const { sidecar, spawned } = manager({ fetch: fetchFn });
    const starting = sidecar.start(SPEC);
    spawned.children[0].ready(8123);
    await starting;
    spawned.children[0].exit(1);
    await expect(sidecar.waitHealthy(8123, 5_000)).rejects.toThrow(/exited while/);
  });

  it("times out with the last error in hand", async () => {
    const { fetch: fetchFn } = fakeFetch({
      "http://127.0.0.1:8123/health": { status: 503 },
    });
    const { sidecar, spawned } = manager({ fetch: fetchFn });
    const starting = sidecar.start(SPEC);
    spawned.children[0].ready(8123);
    await starting;
    await expect(sidecar.waitHealthy(8123, 20)).rejects.toThrow(/status 503/);
  });
});

describe("stop", () => {
  it("sends SIGTERM and resolves when the process exits", async () => {
    const { sidecar, spawned } = manager();
    const starting = sidecar.start(SPEC);
    const child = spawned.children[0];
    child.ready();
    await starting;
    const stopping = sidecar.stop();
    expect(child.signals).toEqual(["SIGTERM"]);
    child.exit(0);
    await stopping;
    expect(sidecar.running).toBe(false);
    expect(sidecar.current).toBeNull();
  });

  it("escalates to SIGKILL after the grace period", async () => {
    const { sidecar, spawned } = manager({
      graceMs: 10,
      sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    });
    const starting = sidecar.start(SPEC);
    const child = spawned.children[0];
    child.ready();
    await starting;
    const stopping = sidecar.stop();
    // The process ignores SIGTERM; after the grace period it is killed, and
    // the fake obliges by exiting then.
    await new Promise((r) => setTimeout(r, 30));
    expect(child.signals).toEqual(["SIGTERM", "SIGKILL"]);
    child.exit(null);
    await stopping;
  });

  it("is a no-op with nothing running", async () => {
    const { sidecar } = manager();
    await expect(sidecar.stop()).resolves.toBeUndefined();
  });
});
