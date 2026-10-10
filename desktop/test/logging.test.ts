import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { fileLogger, memoryLogger } from "../src/logging.js";
import { scratch } from "./helpers.js";

let cleanup: (() => Promise<void>) | null = null;

afterEach(async () => {
  await cleanup?.();
  cleanup = null;
});

describe("fileLogger", () => {
  it("writes stamped lines and raw lines, and reads back the tail", async () => {
    const { dir, done } = await scratch();
    cleanup = done;
    const log = fileLogger(dir, "shell", { now: () => new Date("2026-10-09T12:00:00Z") });
    log.info("one");
    log.warn("two");
    log.raw("three, as the server said it");
    expect(readFileSync(log.path, "utf8")).toBe(
      "2026-10-09T12:00:00.000Z info  one\n2026-10-09T12:00:00.000Z warn  two\nthree, as the server said it\n",
    );
    expect(log.tail(2)).toEqual([
      "2026-10-09T12:00:00.000Z warn  two",
      "three, as the server said it",
    ]);
  });

  it("rotates past the size limit and keeps a bounded number of files", async () => {
    const { dir, done } = await scratch();
    cleanup = done;
    const log = fileLogger(dir, "sidecar", { maxBytes: 50, keep: 2 });
    for (let i = 0; i < 20; i += 1) log.raw(`line ${i} ${"x".repeat(20)}`);
    expect(existsSync(join(dir, "sidecar.log"))).toBe(true);
    expect(existsSync(join(dir, "sidecar.log.1"))).toBe(true);
    expect(existsSync(join(dir, "sidecar.log.2"))).toBe(true);
    expect(existsSync(join(dir, "sidecar.log.3"))).toBe(false);
  });

  it("creates the directory, and reads an absent file as empty", async () => {
    const { dir, done } = await scratch();
    cleanup = done;
    const log = fileLogger(join(dir, "deep", "er"), "shell");
    expect(log.tail(5)).toEqual([]);
    writeFileSync(log.path, "");
    expect(log.tail(5)).toEqual([]);
  });
});

describe("memoryLogger", () => {
  it("keeps what it was told, with the level in front", () => {
    const log = memoryLogger();
    log.error("boom");
    log.raw("plain");
    expect(log.lines).toEqual(["error boom", "plain"]);
    expect(log.tail(1)).toEqual(["plain"]);
  });
});
