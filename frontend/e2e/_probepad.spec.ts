/** TEMPORARY probe: a pad that arrives silently, pressed repeatedly, with the loop's diagnostics. Not for commit. */

import { test } from "@playwright/test";
import { startGame, waitForOurTurn } from "./helpers";

test.describe("probe: a controller plugged in later", () => {
  test.use({ viewport: { width: 1600, height: 950 } });

  test("presses after a silent arrival", async ({ page }) => {
    test.setTimeout(120_000);
    await startGame(page, { opponents: 1, seed: 7 });
    await waitForOurTurn(page);
    const lines: string[] = [];
    const fps = await page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          let n = 0;
          const started = performance.now();
          const tick = () => {
            n += 1;
            if (performance.now() - started < 1000) requestAnimationFrame(tick);
            else resolve(n);
          };
          requestAnimationFrame(tick);
        }),
    );
    lines.push(`rAF/s=${fps}`);

    await page.evaluate(() => {
      const pad = {
        id: "Late Arrival (STANDARD GAMEPAD)",
        index: 0,
        connected: true,
        mapping: "standard",
        timestamp: 0,
        axes: [0, 0, 0, 0],
        buttons: Array.from({ length: 17 }, () => ({
          pressed: false,
          touched: false,
          value: 0,
        })),
      };
      (window as unknown as Record<string, unknown>).__PAD = pad;
      navigator.getGamepads = () => [pad as unknown as Gamepad, null, null, null];
    });
    const t0 = Date.now();
    while (Date.now() - t0 < 4000) {
      if (await page.evaluate(() => document.documentElement.hasAttribute("data-pad"))) break;
      await page.waitForTimeout(50);
    }
    lines.push(`data-pad after ${Date.now() - t0}ms`);
    const diag = () =>
      page.evaluate(() => {
        const w = window as unknown as Record<string, unknown>;
        const keys = Object.keys(w).filter((k) => k.startsWith("__AUTOMTG"));
        const out: Record<string, unknown> = {};
        for (const k of keys) {
          const v = w[k] as Record<string, unknown>;
          if (v && typeof v === "object") {
            for (const [name, fn] of Object.entries(v)) {
              if (typeof fn === "function" && fn.length === 0) {
                try {
                  out[`${k}.${name}`] = (fn as () => unknown)();
                } catch (e) {
                  out[`${k}.${name}`] = String(e);
                }
              }
            }
          }
        }
        return JSON.stringify(out).slice(0, 600);
      });
    lines.push(`diag before: ${await diag()}`);

    for (let attempt = 0; attempt < 6; attempt += 1) {
      await page.mouse.move(400, 400);
      await page.mouse.down();
      await page.mouse.up();
      await page.waitForTimeout(300);
      const seen = await page.evaluate(async (ms) => {
        const pad = (
          window as unknown as { __PAD: { buttons: { pressed: boolean; value: number }[] } }
        ).__PAD;
        pad.buttons[15].pressed = true;
        pad.buttons[15].value = 1;
        await new Promise((r) => setTimeout(r, ms));
        pad.buttons[15].pressed = false;
        pad.buttons[15].value = 0;
        const t = performance.now();
        while (performance.now() - t < 1500) {
          if (document.documentElement.getAttribute("data-input") === "pad") {
            return Math.round(performance.now() - t);
          }
          await new Promise((r) => setTimeout(r, 10));
        }
        return -1;
      }, 90);
      lines.push(`attempt ${attempt}: seen=${seen} diag=${await diag()}`);
    }
    console.log(lines.join("\n"));
  });
});
