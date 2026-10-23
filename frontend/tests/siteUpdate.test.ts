import { describe, expect, it } from "vitest";
import type { AppConfig } from "../src/api/types";
import { HOSTED_DEFAULT } from "../src/logic/desktop";
import { siteUpdate } from "../src/logic/siteUpdate";

const site = (app_version: string): AppConfig => ({ ...HOSTED_DEFAULT, app_version });

describe("siteUpdate", () => {
  it("says nothing while the site runs the build this page loaded", () => {
    expect(siteUpdate("1.4.0", site("1.4.0"))).toBeNull();
  });

  it("names the new build once the site has moved", () => {
    expect(siteUpdate("1.4.0", site("1.5.0"))).toBe("1.5.0");
  });

  it("waits for a real answer before it has anything to compare", () => {
    expect(siteUpdate("", site("1.5.0"))).toBeNull();
    expect(siteUpdate("1.4.0", site(""))).toBeNull();
  });

  it("leaves the desktop to its own updater", () => {
    expect(
      siteUpdate("1.4.0", { ...site("1.5.0"), mode: "desktop", remote_origin: "x" }),
    ).toBeNull();
  });
});
