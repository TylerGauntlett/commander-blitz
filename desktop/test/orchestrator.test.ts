/**
 * Restart in place, with the server faked at the process level: the new
 * content's server either says READY or does not, and the pointer follows.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BUNDLED, ContentManager } from "../src/content.js";
import { memoryLogger } from "../src/logging.js";
import { restartInPlace } from "../src/orchestrator.js";
import { type Ready, SidecarManager, type SidecarSpec } from "../src/sidecar.js";
import { type FakeChild, fakeSpawn, instantSleep, scratch } from "./helpers.js";

let dir: string;
let done: () => Promise<void>;
let content: ContentManager;
let log: ReturnType<typeof memoryLogger>;

async function contentDir(version: string, at: string) {
  await mkdir(at, { recursive: true });
  await writeFile(
    join(at, "manifest.json"),
    JSON.stringify({ content_version: version, min_shell_version: "1.0.0" }),
  );
}

beforeEach(async () => {
  ({ dir, done } = await scratch());
  log = memoryLogger();
  await contentDir("1.0.0", join(dir, "bundled"));
  await contentDir("1.1.0", join(dir, "content", "1.1.0"));
  content = new ContentManager({
    root: join(dir, "content"),
    bundledDir: join(dir, "bundled"),
    statePath: join(dir, "state.json"),
    log,
  });
});

afterEach(() => done());

/**
 * A spawn whose children behave by the content directory they were started
 * from: `behaviour[dir]` says whether that server comes up.
 */
function world(behaviour: Record<string, "ready" | "dies" | "hangs">) {
  const spawned = fakeSpawn();
  const sidecar = new SidecarManager({
    log,
    sidecarLog: memoryLogger(),
    spawn: (command, args, options) => {
      const child = spawned.spawn(command, args, options) as unknown as FakeChild;
      const contentDir = args[args.indexOf("--content-dir") + 1];
      const how = behaviour[contentDir] ?? "ready";
      setImmediate(() => {
        if (how === "ready") child.ready(8000 + spawned.children.length);
        else if (how === "dies") child.exit(1);
      });
      // A signal ends the process, as it does the real server: `stop` waits
      // on the exit, and a fake that shrugged at SIGTERM would wait forever.
      const kill = child.kill.bind(child);
      child.kill = (signal) => {
        kill(signal);
        if (child.exitCode === null) setImmediate(() => child.exit(0));
        return true;
      };
      return child as unknown as import("node:child_process").ChildProcess;
    },
    fetch: (async () => new Response("{}", { status: 200 })) as typeof fetch,
    sleep: instantSleep,
    readyTimeoutMs: 50,
    graceMs: 5,
  });
  const specFor = (contentDir: string): SidecarSpec => ({
    command: "server",
    args: ["--content-dir", contentDir],
  });
  const reloads: Ready[] = [];
  const reloadWindow = (ready: Ready) => {
    reloads.push(ready);
  };
  return { sidecar, specFor, reloads, reloadWindow, spawned };
}

async function startOn(
  sidecar: SidecarManager,
  specFor: (d: string) => SidecarSpec,
  dir: string,
) {
  const ready = await sidecar.start(specFor(dir));
  return ready;
}

describe("restartInPlace", () => {
  it("stops, activates, starts the new content, waits, reloads", async () => {
    const w = world({});
    await startOn(w.sidecar, w.specFor, join(dir, "bundled"));
    const outcome = await restartInPlace({
      sidecar: w.sidecar,
      content,
      target: "1.1.0",
      specFor: w.specFor,
      reloadWindow: w.reloadWindow,
      log,
    });
    expect(outcome).toEqual({ ok: true, version: "1.1.0", rolledBack: false });
    expect(await content.state()).toEqual({ current: "1.1.0", previous: BUNDLED });
    expect(w.spawned.children.map((c) => c.spawnargs.at(-1))).toEqual([
      join(dir, "bundled"),
      join(dir, "content", "1.1.0"),
    ]);
    expect(w.reloads).toHaveLength(1);
    expect(w.sidecar.running).toBe(true);
  });

  it("rolls back when the new server never comes up, and the old one returns", async () => {
    const w = world({ [join(dir, "content", "1.1.0")]: "dies" });
    await startOn(w.sidecar, w.specFor, join(dir, "bundled"));
    const outcome = await restartInPlace({
      sidecar: w.sidecar,
      content,
      target: "1.1.0",
      specFor: w.specFor,
      reloadWindow: w.reloadWindow,
      log,
    });
    expect(outcome.ok).toBe(false);
    expect(outcome.rolledBack).toBe(true);
    expect(outcome.version).toBe(BUNDLED);
    expect(outcome.error).toMatch(/exited with code 1/);
    expect(await content.state()).toEqual({ current: BUNDLED, previous: null });
    // Three starts: the original, the failed new one, the restored old one.
    expect(w.spawned.children.map((c) => c.spawnargs.at(-1))).toEqual([
      join(dir, "bundled"),
      join(dir, "content", "1.1.0"),
      join(dir, "bundled"),
    ]);
    expect(w.reloads).toHaveLength(1);
    expect(w.sidecar.running).toBe(true);
    expect(log.lines.some((l) => /rolled back/.test(l))).toBe(true);
  });

  it("reports both failures when the rollback cannot start either", async () => {
    // The behaviour changes under the running server: it came up fine from
    // 1.1.0, and now neither 1.1.0 nor the bundled content will.
    const behaviour: Record<string, "ready" | "dies" | "hangs"> = {};
    const w = world(behaviour);
    await content.activate("1.1.0");
    await startOn(w.sidecar, w.specFor, join(dir, "content", "1.1.0"));
    behaviour[join(dir, "content", "1.1.0")] = "hangs";
    behaviour[join(dir, "bundled")] = "dies";

    const outcome = await restartInPlace({
      sidecar: w.sidecar,
      content,
      target: "1.1.0",
      specFor: w.specFor,
      reloadWindow: w.reloadWindow,
      log,
    });
    expect(outcome.ok).toBe(false);
    expect(outcome.rolledBack).toBe(false);
    expect(outcome.version).toBe(BUNDLED);
    expect(outcome.error).toMatch(/did not start[\s\S]*then[\s\S]*exited/);
    expect(w.reloads).toHaveLength(0);
    expect(log.lines.some((l) => /also failed/.test(l))).toBe(true);
    expect(w.sidecar.running).toBe(false);
  });

  it("never touches the Electron process: nothing here can", () => {
    // A structural guarantee, stated as a test so a future import of
    // `app.relaunch` is a visible change rather than a quiet one.
    expect(restartInPlace.toString()).not.toMatch(/relaunch|app\.exit|process\.exit/);
  });
});
