/** TEMPORARY probe: frame cadence and press-hold sensitivity on the CI runner. Not for commit. */

import { type Page, test } from "@playwright/test";
import { startGame, waitForOurTurn } from "./helpers";

async function withFakePad(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const pad = {
      id: "Fake Deck Controller (STANDARD GAMEPAD)",
      index: 0,
      connected: true,
      mapping: "standard",
      timestamp: 0,
      axes: [0, 0, 0, 0],
      buttons: Array.from({ length: 17 }, () => ({ pressed: false, touched: false, value: 0 })),
    };
    (window as unknown as Record<string, unknown>).__PAD = pad;
    navigator.getGamepads = () => [pad as unknown as Gamepad, null, null, null];
    window.dispatchEvent(new Event("gamepadconnected"));
  });
}

test("probe: frames per second and how long a press must be held", async ({ page }) => {
  test.setTimeout(120_000);
  await withFakePad(page);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await waitForOurTurn(page);

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
  const lines = [
    `rAF callbacks in 1s: ${fps}, hidden=${await page.evaluate(() => document.hidden)}`,
  ];

  for (const hold of [30, 60, 90, 150, 300]) {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      // Back to mouse so the next press has to be noticed on its own.
      await page.mouse.move(400, 400);
      await page.mouse.down();
      await page.mouse.up();
      await page.waitForTimeout(250);
      const mode0 = await page.evaluate(() =>
        document.documentElement.getAttribute("data-input"),
      );
      const seen = await page.evaluate(async (ms) => {
        const pad = (
          window as unknown as { __PAD: { buttons: { pressed: boolean; value: number }[] } }
        ).__PAD;
        pad.buttons[13].pressed = true;
        pad.buttons[13].value = 1;
        await new Promise((r) => setTimeout(r, ms));
        pad.buttons[13].pressed = false;
        pad.buttons[13].value = 0;
        const t0 = performance.now();
        while (performance.now() - t0 < 1500) {
          if (document.documentElement.getAttribute("data-input") === "pad")
            return Math.round(performance.now() - t0);
          await new Promise((r) => setTimeout(r, 10));
        }
        return -1;
      }, hold);
      lines.push(`hold ${hold}ms attempt ${attempt}: from=${mode0} seen=${seen}`);
    }
  }
  console.log(lines.join("\n"));
});
