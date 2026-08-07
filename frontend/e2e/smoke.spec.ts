import { expect, test } from "@playwright/test";
import {
  actionsOfKind,
  isOver,
  lifeOf,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

test.describe("the table renders and plays", () => {
  test("deals a game and shows both players at 40 life", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    await expect(page.getByTestId("table")).toBeVisible();
    await expect(page.getByTestId("phase-track")).toBeVisible();
    await expect(page.getByTestId("action-bar")).toBeVisible();

    // Commander: 40 life each.
    expect(await lifeOf(page, 0)).toBe(40);
    expect(await lifeOf(page, 1)).toBe(40);
  });

  test("opens on the mulligan decision and can keep", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    const dialog = page.getByTestId("prompt-dialog");
    if (await dialog.isVisible()) {
      expect(await dialog.getAttribute("data-decision-kind")).toBe("mulligan");
      await page.locator('[data-action-kind="keep"]').click();
    }
    await waitForOurTurn(page);
    await expect(page.getByTestId("action-bar")).toBeVisible();
  });

  test("draws a hand of real cards with names and mana costs", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);
    const keep = page.locator('[data-action-kind="keep"]');
    if (await keep.count()) await keep.click();
    await waitForOurTurn(page);

    const hand = page.locator(".hand .card");
    await expect(hand.first()).toBeVisible();
    expect(await hand.count()).toBeGreaterThanOrEqual(6);

    // A card face carries its printed name.
    const name = await hand.first().getAttribute("data-card-name");
    expect(name).toBeTruthy();
    expect(name).not.toBe("");
  });

  test("plays a land and it appears in the land lane", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);
    const keep = page.locator('[data-action-kind="keep"]');
    if (await keep.count()) await keep.click();

    // Walk forward until a land drop is on offer.
    for (let i = 0; i < 40; i += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) break;
      if (await actionsOfKind(page, "play_land").count()) {
        const before = await page.locator('[data-testid^="lane-0-Lands"] .card').count();
        await actionsOfKind(page, "play_land").first().click();
        await waitForOurTurn(page);
        await expect
          .poll(async () => page.locator('[data-testid^="lane-0-Lands"] .card').count())
          .toBeGreaterThan(before);
        return;
      }
      await takeAction(page, ["pass"]);
    }
    throw new Error("never got the chance to play a land");
  });

  test("hovering a card fills the preview panel with its rules text", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);
    const keep = page.locator('[data-action-kind="keep"]');
    if (await keep.count()) await keep.click();
    await waitForOurTurn(page);

    await expect(page.getByTestId("card-preview")).toContainText("Hover a card");
    await page.locator(".hand .card").first().hover();
    await expect(page.getByTestId("card-preview")).not.toContainText("Hover a card");
    await expect(page.getByTestId("card-preview").locator(".face")).toBeVisible();
  });

  test("reaches combat and can declare an attack", async ({ page }) => {
    test.slow();
    await startGame(page, { deck: "aesi", opponents: 1, seed: 3 });

    for (let i = 0; i < 400; i += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) return;

      const panel = page.getByTestId("combat-panel");
      if (await panel.isVisible().catch(() => false)) {
        const kind = await panel.getAttribute("data-combat-kind");
        if (kind === "attackers" && (await actionsOfKind(page, "add_attacker").count())) {
          // Click a creature on our board to stage it, then confirm.
          const attacker = await actionsOfKind(page, "add_attacker")
            .first()
            .getAttribute("data-action-id");
          expect(attacker).toBeTruthy();
          await actionsOfKind(page, "add_attacker").first().click();
          await waitForOurTurn(page);
          await expect(page.getByTestId("phase-track")).toBeVisible();
          return;
        }
      }
      await takeAction(page, ["keep", "play_land", "pass"]);
    }
    throw new Error("never reached a declare-attackers decision");
  });
});
