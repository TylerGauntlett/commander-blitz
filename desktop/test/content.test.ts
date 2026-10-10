/**
 * Content packages on disk: real files in a scratch directory, so the rename
 * semantics the atomicity argument rests on are the real ones.
 */

import { createHash } from "node:crypto";
import { existsSync, readdirSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import * as tar from "tar";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BUNDLED, ContentManager, type ContentManifest, sha256Of } from "../src/content.js";
import { memoryLogger } from "../src/logging.js";
import { scratch } from "./helpers.js";

let dir: string;
let done: () => Promise<void>;
let log: ReturnType<typeof memoryLogger>;
let content: ContentManager;

/** A content directory with a manifest and a marker file saying which it is. */
async function contentDir(at: string, version: string): Promise<ContentManifest> {
  const manifest: ContentManifest = {
    content_version: version,
    app_version: "0.1.0",
    min_shell_version: "1.0.0",
    asset: `content-${version}.tar.gz`,
    sha256: "",
    size: 0,
    built: "2026-10-09T00:00:00Z",
  };
  await mkdir(join(at, "server"), { recursive: true });
  await writeFile(join(at, "manifest.json"), JSON.stringify(manifest));
  await writeFile(join(at, "server", "commanderblitz-server"), `#!/bin/sh\necho ${version}\n`);
  return manifest;
}

/** A tarball of a content directory, with its true checksum in the manifest. */
async function tarball(
  version: string,
  lie?: string,
): Promise<{ file: string; manifest: ContentManifest }> {
  const src = join(dir, "src", version);
  const manifest = await contentDir(src, lie ?? version);
  const file = join(dir, `content-${version}.tar.gz`);
  await tar.c({ gzip: true, file, cwd: src }, ["."]);
  manifest.content_version = version;
  manifest.sha256 = await sha256Of(file);
  return { file, manifest };
}

beforeEach(async () => {
  ({ dir, done } = await scratch());
  log = memoryLogger();
  await contentDir(join(dir, "bundled"), "1.0.0");
  content = new ContentManager({
    root: join(dir, "content"),
    bundledDir: join(dir, "bundled"),
    statePath: join(dir, "state.json"),
    log,
  });
});

afterEach(() => done());

describe("first launch", () => {
  it("runs the bundled content in place, with no state file", async () => {
    const current = await content.current();
    expect(current).toEqual({ version: "1.0.0", dir: join(dir, "bundled"), bundled: true });
    expect(await content.state()).toEqual({ current: BUNDLED, previous: null });
    expect(existsSync(join(dir, "state.json"))).toBe(false);
  });

  it("treats an unreadable state file as first launch", async () => {
    await writeFile(join(dir, "state.json"), "{not json");
    expect((await content.current()).bundled).toBe(true);
  });
});

describe("install", () => {
  it("verifies, extracts, and records the new version", async () => {
    const { file, manifest } = await tarball("1.1.0");
    const installed = await content.install(file, manifest);
    expect(installed).toBe(join(dir, "content", "1.1.0"));
    expect(await readFile(join(installed, "manifest.json"), "utf8")).toContain("1.1.0");
    expect(readdirSync(join(dir, "content"))).toEqual(["1.1.0"]);
    // Not yet current: install and activate are two steps, because the
    // restart is what decides when the switch happens.
    expect((await content.current()).version).toBe("1.0.0");
  });

  it("refuses a tarball whose checksum is wrong, leaving nothing behind", async () => {
    const { file, manifest } = await tarball("1.1.0");
    manifest.sha256 = "0".repeat(64);
    await expect(content.install(file, manifest)).rejects.toThrow(/checksum/);
    expect(existsSync(join(dir, "content", "1.1.0"))).toBe(false);
  });

  it("refuses a tarball that says it is another version", async () => {
    const { file, manifest } = await tarball("1.1.0", "9.9.9");
    await expect(content.install(file, manifest)).rejects.toThrow(/says it is 9.9.9/);
    expect(existsSync(join(dir, "content"))).toBe(true);
    expect(readdirSync(join(dir, "content"))).toEqual([]);
  });

  it("cleans up an interrupted extraction on the next attempt", async () => {
    await mkdir(join(dir, "content", "1.1.0.partial"), { recursive: true });
    await writeFile(join(dir, "content", "1.1.0.partial", "junk"), "half");
    const { file, manifest } = await tarball("1.1.0");
    await content.install(file, manifest);
    expect(readdirSync(join(dir, "content"))).toEqual(["1.1.0"]);
    expect(existsSync(join(dir, "content", "1.1.0", "junk"))).toBe(false);
  });

  it("replaces an existing directory of the same version", async () => {
    await mkdir(join(dir, "content", "1.1.0"), { recursive: true });
    await writeFile(join(dir, "content", "1.1.0", "stale"), "old");
    const { file, manifest } = await tarball("1.1.0");
    await content.install(file, manifest);
    expect(existsSync(join(dir, "content", "1.1.0", "stale"))).toBe(false);
  });
});

describe("activate and rollback", () => {
  it("swaps the pointer, remembering what it was", async () => {
    const { file, manifest } = await tarball("1.1.0");
    await content.install(file, manifest);
    await content.activate("1.1.0");
    expect(await content.state()).toEqual({ current: "1.1.0", previous: BUNDLED });
    expect(await content.current()).toEqual({
      version: "1.1.0",
      dir: join(dir, "content", "1.1.0"),
      bundled: false,
    });
    // No half-written state ever remains.
    expect(existsSync(join(dir, "state.json.tmp"))).toBe(false);
  });

  it("activating what is already current changes nothing", async () => {
    await content.activate(BUNDLED);
    expect(existsSync(join(dir, "state.json"))).toBe(false);
  });

  it("rolls back to the previous, and below that to the bundled content", async () => {
    for (const v of ["1.1.0", "1.2.0"]) {
      const { file, manifest } = await tarball(v);
      await content.install(file, manifest);
      await content.activate(v);
    }
    expect(await content.rollback()).toBe("1.1.0");
    expect((await content.current()).version).toBe("1.1.0");
    expect(await content.rollback()).toBe(BUNDLED);
    expect((await content.current()).bundled).toBe(true);
  });

  it("falls back to the bundled content when the current one is gone", async () => {
    const { file, manifest } = await tarball("1.1.0");
    await content.install(file, manifest);
    await content.activate("1.1.0");
    await content.prune(); // keeps it
    const { rm } = await import("node:fs/promises");
    await rm(join(dir, "content", "1.1.0"), { recursive: true });
    expect((await content.current()).bundled).toBe(true);
    expect(await content.state()).toEqual({ current: BUNDLED, previous: null });
    expect(log.lines.some((l) => /missing on disk/.test(l))).toBe(true);
  });
});

describe("prune", () => {
  it("keeps current and previous, deletes the rest", async () => {
    for (const v of ["1.1.0", "1.2.0", "1.3.0"]) {
      const { file, manifest } = await tarball(v);
      await content.install(file, manifest);
      await content.activate(v);
    }
    await mkdir(join(dir, "content", "1.4.0.partial"));
    const removed = await content.prune();
    expect(removed.sort()).toEqual(["1.1.0", "1.4.0.partial"]);
    expect(readdirSync(join(dir, "content")).sort()).toEqual(["1.2.0", "1.3.0"]);
  });

  it("is a no-op before anything was installed", async () => {
    expect(await content.prune()).toEqual([]);
  });
});

describe("sha256Of", () => {
  it("agrees with node's own hash", async () => {
    const file = join(dir, "blob");
    await writeFile(file, "hello");
    expect(await sha256Of(file)).toBe(createHash("sha256").update("hello").digest("hex"));
  });
});
