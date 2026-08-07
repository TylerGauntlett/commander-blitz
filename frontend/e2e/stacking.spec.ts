import { expect, test } from "@playwright/test";
import { actionsOfKind, isOver, startGame, takeAction, waitForOurTurn } from "./helpers";

/**
 * Identical permanents collapse into one stack with a count badge.
 *
 * Basics are the natural case: play several Islands and the land lane should
 * hold one stack of N rather than N separate cards.
 */
test("duplicate lands collapse into a counted stack", async ({ page }) => {
  test.slow();
  test.setTimeout(300_000);

  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

  // Play lands whenever offered until several are down.
  for (let i = 0; i < 400; i += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) break;

    const lands = await page.locator('[data-testid^="lane-0-Lands"] .card').count();
    if (lands >= 4) break;

    if (await actionsOfKind(page, "play_land").count()) {
      await actionsOfKind(page, "play_land").first().click();
      continue;
    }
    await takeAction(page, ["keep", "pass"]);
  }

  const lane = page.locator('[data-testid^="lane-0-Lands"]').first();
  await expect(lane).toBeVisible();

  const stacks = lane.locator("[data-stack-key]");
  const stackCount = await stacks.count();
  const cardCount = await lane.locator(".card").count();
  expect(cardCount, "no lands were ever played").toBeGreaterThan(0);

  // Every card belongs to some stack, and stacks are never more numerous than
  // the cards in them: that is the whole point of the collapse.
  expect(stackCount).toBeGreaterThan(0);
  expect(stackCount).toBeLessThanOrEqual(cardCount);

  // The counts on the stacks must add up to the cards on the board.
  let total = 0;
  for (let i = 0; i < stackCount; i += 1) {
    total += Number(await stacks.nth(i).getAttribute("data-stack-count"));
  }
  expect(total).toBe(cardCount);

  // If any duplicates were played, at least one stack shows a x2+ badge.
  if (cardCount > stackCount) {
    await expect(lane.locator(".cardstack__count").first()).toBeVisible();
  }
});

test("a stack fans out on hover so each copy stays reachable", async ({ page }) => {
  test.slow();
  test.setTimeout(300_000);

  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

  for (let i = 0; i < 400; i += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) break;

    // Find a stack holding more than one card, then pin it by its stable key.
    // Selecting it by the count badge would break the moment we hover: opening
    // the fan hides the badge, and the locator would stop matching.
    const multi = page.locator('[data-testid^="lane-0-Lands"] [data-stack-count]');
    const total = await multi.count();
    let key: string | null = null;
    for (let n = 0; n < total; n += 1) {
      const candidate = multi.nth(n);
      if (Number(await candidate.getAttribute("data-stack-count")) > 1) {
        key = await candidate.getAttribute("data-stack-key");
        break;
      }
    }

    if (key) {
      // Stack keys are built from card ids and flags, so they never contain a
      // quote; a quoted attribute selector is enough.
      const stack = page.locator(`[data-stack-key="${key}"]`).first();
      await expect(stack.locator(".cardstack__count")).toBeVisible();

      /** How far apart the member cards sit, horizontally. */
      const spread = async (): Promise<number> => {
        const cards = stack.locator(".card");
        const boxes = await cards.evaluateAll((nodes) =>
          nodes.map((node) => node.getBoundingClientRect().x),
        );
        return Math.max(...boxes) - Math.min(...boxes);
      };

      const boxBefore = await stack.boundingBox();
      const spreadBefore = await spread();
      await stack.hover();
      await page.waitForTimeout(500);
      const boxAfter = await stack.boundingBox();
      const spreadAfter = await spread();

      // The members fan apart so every copy is individually reachable...
      expect(spreadAfter).toBeGreaterThan(spreadBefore);
      // ...while the container keeps its footprint. Animating the width here
      // wrapped the lane onto new rows and slid the whole board under the
      // cursor, which made picking a card out of a stack impossible.
      expect(boxAfter?.width ?? 0).toBeCloseTo(boxBefore?.width ?? 0, 0);
      expect(boxAfter?.x ?? 0).toBeCloseTo(boxBefore?.x ?? 0, 0);
      return;
    }

    if (await actionsOfKind(page, "play_land").count()) {
      await actionsOfKind(page, "play_land").first().click();
      continue;
    }
    await takeAction(page, ["keep", "pass"]);
  }
  test.skip(true, "no duplicate land was drawn in this game");
});
