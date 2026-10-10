import { beforeEach, describe, expect, it } from "vitest";
import { migrateLegacyStorage } from "../src/state/storage";

describe("storage migration", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("moves a returning player's automtg.* keys to their new names, once", () => {
    window.localStorage.setItem("automtg.speed", "fast");
    window.localStorage.setItem("automtg.library", '["deck-a"]');
    window.localStorage.setItem("automtg.pod.GYRE-8412", "token");
    window.localStorage.setItem("unrelated", "kept");

    expect(migrateLegacyStorage()).toBe(3);

    expect(window.localStorage.getItem("commanderblitz.speed")).toBe("fast");
    expect(window.localStorage.getItem("commanderblitz.library")).toBe('["deck-a"]');
    expect(window.localStorage.getItem("commanderblitz.pod.GYRE-8412")).toBe("token");
    expect(window.localStorage.getItem("automtg.speed")).toBeNull();
    expect(window.localStorage.getItem("automtg.library")).toBeNull();
    expect(window.localStorage.getItem("automtg.pod.GYRE-8412")).toBeNull();
    expect(window.localStorage.getItem("unrelated")).toBe("kept");

    // The second boot has nothing to do.
    expect(migrateLegacyStorage()).toBe(0);
  });

  it("never overwrites a value the player has set since the rename", () => {
    window.localStorage.setItem("automtg.muted", "0");
    window.localStorage.setItem("commanderblitz.muted", "1");

    expect(migrateLegacyStorage()).toBe(0);

    expect(window.localStorage.getItem("commanderblitz.muted")).toBe("1");
    expect(window.localStorage.getItem("automtg.muted")).toBeNull();
  });
});
