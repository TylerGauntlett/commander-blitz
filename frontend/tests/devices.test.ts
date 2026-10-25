/**
 * The phones in `testing/devices.ts`, held to the descriptors they name.
 *
 * Storybook cannot import Playwright, so the sizes are repeated in that file;
 * this is what makes repeating them safe. A Playwright upgrade that moves a
 * descriptor fails here rather than leaving a story and a spec on two sizes.
 */

import { devices } from "playwright";
import { describe, expect, it } from "vitest";
import { PHONE_VIEWPORTS, PHONES, VIEWPORTS } from "../src/testing/devices";

describe("PHONES", () => {
  for (const phone of PHONES.filter((p) => p.descriptor !== null)) {
    it(`${phone.name} matches Playwright's "${phone.descriptor}"`, () => {
      const upright = devices[phone.descriptor as string];
      const sideways = devices[`${phone.descriptor} landscape`];
      expect(phone.portrait).toEqual(upright.viewport);
      expect(phone.landscape).toEqual(sideways.viewport);
      expect(phone.screen).toEqual((upright as { screen?: unknown }).screen);
      expect(phone.deviceScaleFactor).toBe(upright.deviceScaleFactor);
      expect(phone.userAgent).toBe(upright.userAgent);
    });
  }

  it("holds the iPhone Duo at its published folded screen", () => {
    const duo = PHONES.find((p) => p.id === "iphoneduo");
    expect(duo?.screen).toEqual({ width: 466, height: 678 });
    expect(duo?.portrait).toEqual({ width: 466, height: 485 });
    expect(duo?.landscape).toEqual({ width: 560, height: 416 });
  });
});

describe("VIEWPORTS", () => {
  it("puts every phone, held either way, in the phone layout", () => {
    expect(PHONE_VIEWPORTS).toHaveLength(PHONES.length * 2);
  });

  it("has one id per viewport", () => {
    const ids = VIEWPORTS.map((v) => v.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
