/**
 * The content updater: a check that never throws, a download that installs,
 * and a schedule that can be run with a fake clock.
 */

import { existsSync, readdirSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import * as tar from "tar";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ContentManager, type ContentManifest, sha256Of } from "../src/content.js";
import { memoryLogger } from "../src/logging.js";
import { ContentUpdater, scheduleChecks } from "../src/updater.js";
import { type Answer, fakeFetch, scratch } from "./helpers.js";

const BASE = "https://github.com/x/commanderblitz-releases/releases/latest/download";

let dir: string;
let done: () => Promise<void>;
let content: ContentManager;
let log: ReturnType<typeof memoryLogger>;

function manifest(version: string, over: Partial<ContentManifest> = {}): ContentManifest {
  return {
    content_version: version,
    app_version: "0.1.0",
    min_shell_version: "1.0.0",
    asset: `content-${version}.tar.gz`,
    sha256: "",
    size: 0,
    built: "2026-10-09T00:00:00Z",
    ...over,
  };
}

async function bundled(version: string) {
  await mkdir(join(dir, "bundled"), { recursive: true });
  await writeFile(join(dir, "bundled", "manifest.json"), JSON.stringify(manifest(version)));
}

beforeEach(async () => {
  ({ dir, done } = await scratch());
  log = memoryLogger();
  await bundled("1.0.0");
  content = new ContentManager({
    root: join(dir, "content"),
    bundledDir: join(dir, "bundled"),
    statePath: join(dir, "state.json"),
    log,
  });
});

afterEach(() => done());

function updater(table: Record<string, Answer>, shellVersion = "1.0.0") {
  const net = fakeFetch(table);
  const up = new ContentUpdater({
    releasesBase: `${BASE}/`,
    shellVersion,
    content,
    downloadsDir: join(dir, "downloads"),
    log,
    fetch: net.fetch,
  });
  return { up, calls: net.calls };
}

describe("check", () => {
  it("is none when the latest is what is running", async () => {
    const { up, calls } = updater({
      [`${BASE}/content-latest.json`]: { body: manifest("1.0.0") },
    });
    expect((await up.check()).kind).toBe("none");
    expect(calls).toEqual([`${BASE}/content-latest.json`]);
  });

  it("is none when the latest is older (a yanked release)", async () => {
    const { up } = updater({ [`${BASE}/content-latest.json`]: { body: manifest("0.9.0") } });
    expect((await up.check()).kind).toBe("none");
  });

  it("is available when newer and this shell is enough", async () => {
    const { up } = updater({ [`${BASE}/content-latest.json`]: { body: manifest("1.1.0") } });
    const verdict = await up.check();
    expect(verdict.kind).toBe("available");
    expect(verdict.manifest?.content_version).toBe("1.1.0");
  });

  it("is needs-shell when the content wants a newer shell", async () => {
    const { up } = updater({
      [`${BASE}/content-latest.json`]: {
        body: manifest("1.1.0", { min_shell_version: "2.0.0" }),
      },
    });
    expect((await up.check()).kind).toBe("needs-shell");
    expect(log.lines.some((l) => /needs shell 2.0.0/.test(l))).toBe(true);
  });

  it("never throws: a 404, a network error, both are none", async () => {
    expect((await updater({}).up.check()).kind).toBe("none");
    const { up } = updater({ [`${BASE}/content-latest.json`]: new Error("offline") });
    expect((await up.check()).kind).toBe("none");
    expect(log.lines.some((l) => /offline/.test(l))).toBe(true);
  });
});

describe("download", () => {
  it("streams the tarball, installs it, and removes the download", async () => {
    const src = join(dir, "src");
    await mkdir(src, { recursive: true });
    await writeFile(join(src, "manifest.json"), JSON.stringify(manifest("1.1.0")));
    const file = join(dir, "content-1.1.0.tar.gz");
    await tar.c({ gzip: true, file, cwd: src }, ["."]);
    const bytes = new Uint8Array(await readFile(file));
    const m = manifest("1.1.0", { sha256: await sha256Of(file), size: bytes.byteLength });

    const { up } = updater({ [`${BASE}/content-1.1.0.tar.gz`]: { bytes } });
    const seen: number[] = [];
    const installed = await up.download(m, (received) => seen.push(received));
    expect(installed).toBe(join(dir, "content", "1.1.0"));
    expect(seen.at(-1)).toBe(bytes.byteLength);
    expect(existsSync(join(dir, "downloads", "content-1.1.0.tar.gz"))).toBe(false);
    expect(readdirSync(join(dir, "content"))).toEqual(["1.1.0"]);
  });

  it("fails on a bad checksum and still removes the download", async () => {
    const { up } = updater({
      [`${BASE}/content-1.1.0.tar.gz`]: { bytes: new Uint8Array([1, 2, 3]) },
    });
    await expect(up.download(manifest("1.1.0", { sha256: "ff" }))).rejects.toThrow(/checksum/);
    expect(existsSync(join(dir, "downloads", "content-1.1.0.tar.gz"))).toBe(false);
  });

  it("fails on a missing asset", async () => {
    const { up } = updater({});
    await expect(up.download(manifest("1.1.0"))).rejects.toThrow(/answered 404/);
  });
});

describe("scheduleChecks", () => {
  it("runs once after the first delay, then on the interval, until stopped", async () => {
    vi.useFakeTimers();
    try {
      const run = vi.fn(async () => undefined);
      const stop = scheduleChecks(run, { firstMs: 20, everyMs: 100 });
      expect(run).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(20);
      expect(run).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(100);
      expect(run).toHaveBeenCalledTimes(2);
      stop();
      await vi.advanceTimersByTimeAsync(1_000);
      expect(run).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps going when a run throws", async () => {
    vi.useFakeTimers();
    try {
      let n = 0;
      const run = vi.fn(async () => {
        n += 1;
        if (n === 1) throw new Error("download failed");
      });
      const stop = scheduleChecks(run, { firstMs: 1, everyMs: 1 });
      await vi.advanceTimersByTimeAsync(5);
      expect(run.mock.calls.length).toBeGreaterThan(1);
      stop();
    } finally {
      vi.useRealTimers();
    }
  });
});
