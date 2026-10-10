import { describe, expect, it } from "vitest";
import { compareVersions, parseVersion, satisfiesMin } from "../src/version.js";

describe("compareVersions", () => {
  it("orders numerically, not lexically", () => {
    expect(compareVersions("1.10.0", "1.9.0")).toBeGreaterThan(0);
    expect(compareVersions("1.2.3", "1.2.3")).toBe(0);
    expect(compareVersions("0.9.9", "1.0.0")).toBeLessThan(0);
  });

  it("treats a missing patch as zero and ignores a leading v", () => {
    expect(compareVersions("v1.2", "1.2.0")).toBe(0);
    expect(compareVersions("1", "1.0.1")).toBeLessThan(0);
  });

  it("puts a pre-release below its release", () => {
    expect(compareVersions("1.3.0-beta.1", "1.3.0")).toBeLessThan(0);
    expect(compareVersions("1.3.0-beta.2", "1.3.0-beta.1")).toBeGreaterThan(0);
    expect(compareVersions("1.3.0-rc.1", "1.2.9")).toBeGreaterThan(0);
  });

  it("refuses what is not a version", () => {
    expect(() => parseVersion("latest")).toThrow(/not a version/);
  });
});

describe("satisfiesMin", () => {
  it("is true with no minimum, and at or above it", () => {
    expect(satisfiesMin("1.0.0", undefined)).toBe(true);
    expect(satisfiesMin("1.0.0", "")).toBe(true);
    expect(satisfiesMin("1.0.0", "1.0.0")).toBe(true);
    expect(satisfiesMin("1.1.0", "1.0.0")).toBe(true);
  });

  it("is false below it", () => {
    expect(satisfiesMin("1.0.0", "1.1.0")).toBe(false);
  });
});
