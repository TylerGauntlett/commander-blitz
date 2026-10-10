import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { appPaths, defaultHome } from "../src/paths.js";

describe("defaultHome", () => {
  it("is overridden by COMMANDERBLITZ_HOME on every platform", () => {
    for (const platform of ["linux", "win32", "darwin"] as const) {
      expect(defaultHome(platform, { COMMANDERBLITZ_HOME: "/scratch" })).toBe("/scratch");
    }
  });

  it("follows XDG on Linux, which is where a Steam Deck keeps things", () => {
    expect(defaultHome("linux", { XDG_DATA_HOME: "/xdg" })).toBe(
      join("/xdg", "commanderblitz"),
    );
    expect(defaultHome("linux", {})).toMatch(/[\\/]\.local[\\/]share[\\/]commanderblitz$/);
  });

  it("uses LOCALAPPDATA on Windows", () => {
    expect(defaultHome("win32", { LOCALAPPDATA: "C:\\Users\\x\\AppData\\Local" })).toBe(
      join("C:\\Users\\x\\AppData\\Local", "CommanderBlitz"),
    );
  });
});

describe("appPaths", () => {
  it("puts everything under the one home", () => {
    const home = join("/home/deck/.local/share/commanderblitz");
    const paths = appPaths(home);
    for (const value of Object.values(paths)) {
      expect(value.startsWith(home)).toBe(true);
    }
    expect(paths.state.endsWith("state.json")).toBe(true);
  });
});
