/**
 * A finger drags a hand card onto the board and the card is played.
 *
 * Two things stopped it, and this walks the gesture both broke. The card's
 * art is an `<img>`, natively draggable, so a press on the picture started the
 * browser's own drag and cancelled the card's; and a drop counted only over
 * the lane the card would sit in, which the compact board draws no heading for,
 * so a land let go over the creature row or the seat panel sprang back. Now
 * anywhere on your own board plays it (`logic/actionMatch.ts:dropPlays`).
 *
 * Real touch events through CDP, at the unfolded-phone size the bug was found
 * at, on a mobile engine. Named `-handheld` so the handheld project runs it.
 */

import { expect, type Page, test } from "@playwright/test";
import { actionsOfKind, keepOpeningHand, startGame } from "./helpers";

test.use({ viewport: { width: 1000, height: 703 }, isMobile: true, hasTouch: true });

/** A point on the card that is the card's own, not a fanned neighbour's. */
async function grabPoint(page: Page, oid: string): Promise<{ x: number; y: number }> {
  const point = await page.evaluate((id) => {
    const el = document.querySelector(`.hand [data-oid="${id}"]`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    for (let fy = 0.3; fy < 0.9; fy += 0.1) {
      for (let fx = 0.1; fx < 0.95; fx += 0.05) {
        const x = r.x + r.width * fx;
        const y = r.y + r.height * fy;
        if (
          document.elementFromPoint(x, y)?.closest("[data-oid]")?.getAttribute("data-oid") ===
          id
        )
          return { x, y };
      }
    }
    return null;
  }, oid);
  if (!point) throw new Error(`no visible point on hand card ${oid}`);
  return point;
}

async function touchDrag(
  page: Page,
  from: { x: number; y: number },
  to: { x: number; y: number },
): Promise<void> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [from] });
  const steps = 20;
  for (let i = 1; i <= steps; i += 1) {
    const x = from.x + ((to.x - from.x) * i) / steps;
    const y = from.y + ((to.y - from.y) * i) / steps;
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y }] });
    await page.waitForTimeout(16);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

for (const target of ["creature row", "seat panel"] as const) {
  test(`a land dragged onto the ${target} is played`, async ({ page }) => {
    await startGame(page, { opponents: 1, seed: 7 });
    await keepOpeningHand(page);
    await actionsOfKind(page, "play_land").first().waitFor({ timeout: 60_000 });

    const land = page.locator(".hand [data-oid]:has(.face--type-land)").first();
    const oid = await land.getAttribute("data-oid");
    if (!oid) throw new Error("no land in the opening hand");
    const from = await grabPoint(page, oid);

    const zone = page.locator(
      target === "creature row" ? '[data-testid="lane-0-Creatures"]' : ".play__mine .orb",
    );
    const box = await zone.boundingBox();
    if (!box) throw new Error(`no ${target} on screen`);

    const lands = page.locator('[data-testid="lane-0-Lands"] [data-oid]');
    await expect(lands).toHaveCount(0);
    await touchDrag(page, from, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
    await expect(lands).toHaveCount(1);
  });
}
