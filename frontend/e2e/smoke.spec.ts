import { expect, test } from "@playwright/test";
import {
  actionsOfKind,
  isOver,
  keepOpeningHand,
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
    await expect(page.locator(".acts")).toBeVisible();

    // Commander: 40 life each.
    expect(await lifeOf(page, 0)).toBe(40);
    expect(await lifeOf(page, 1)).toBe(40);
  });

  test("marks the current step, and the mark is actually painted", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    const marker = page.locator(".track__marker");
    await expect(marker).toHaveCount(1);
    await expect(marker).toBeVisible();

    // Every step keeps its label: the current one used to render as a blank gap,
    // because its near-black text was designed to sit on a marker that was not
    // being drawn.
    const labels = await page.locator(".track__step-label").allTextContents();
    expect(labels.length).toBe(13);
    expect(labels.every((text) => text.trim().length > 0)).toBe(true);

    // The real regression: `z-index: -1` on the marker, with no stacking context
    // between it and the root, put the gold pill in the *root's* negative layer
    // -- behind the track's own background, and so invisible. Assert the layering
    // rather than the pixels: a negative z-index child needs an ancestor that
    // contains it.
    const layering = await marker.evaluate((node) => {
      const step = node.parentElement as HTMLElement;
      return {
        markerZ: getComputedStyle(node).zIndex,
        isolation: getComputedStyle(step).isolation,
        stepZ: getComputedStyle(step).zIndex,
      };
    });
    expect(Number(layering.markerZ) >= 0 || layering.markerZ === "auto").toBe(true);
    expect(layering.isolation === "isolate" || layering.stepZ !== "auto").toBe(true);
  });

  test("opens on the opening hand and can keep", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    /*
     * The first frame of every game is `OpeningHand`, not the generic dialog.
     * It draws the seven cards themselves -- which is the whole point of it, and
     * the thing the dialog it replaced could not do: `PromptDialog` renders a
     * face only when an option refers to an object, and a mulligan's two options
     * refer to nothing.
     */
    const stage = page.getByTestId("opening-hand");
    await expect(stage).toBeVisible();
    expect(await stage.getAttribute("data-decision-kind")).toBe("mulligan");
    await expect(page.getByTestId("prompt-dialog")).toBeHidden();
    expect(await stage.locator(".mull__slot").count()).toBe(7);

    await keepOpeningHand(page);
    await expect(stage).toBeHidden();
    await expect(page.locator(".acts")).toBeVisible();
  });

  /*
   * The second question, which only exists once a mulligan has cost a card --
   * the first one is free, so it takes two.
   *
   * `engine/game.py` bottoms `mulligans_taken - FREE_MULLIGANS` cards, and it is a
   * different decision KIND from the first half -- so this is the one path that
   * proves `mulliganPhase` tells a mulligan's `choose_objects` apart from every
   * other one by the engine's `purpose` tag rather than by its prompt.
   */
  test("takes a mulligan and answers the bottoming half in the same room", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    const stage = page.getByTestId("opening-hand");
    const mullButton = page.locator('[data-action-kind="mulligan"]').first();
    await expect(mullButton).toContainText("Free");
    await mullButton.click();
    await expect(stage).toBeVisible();

    // One lamp is spent, which is the count the engine had never sent before --
    // and it is the free lamp, so the button no longer offers a free one.
    await expect(stage.locator(".mull__lamp[data-spent]")).toHaveCount(1);
    await expect(stage.locator(".mull__lamp[data-spent][data-free]")).toHaveCount(1);
    await expect(mullButton).not.toContainText("Free");

    // The first was free; the second is the one that costs a card.
    await page.locator('[data-action-kind="mulligan"]').first().click();
    await expect(stage.locator(".mull__lamp[data-spent]")).toHaveCount(2);

    await page.locator('[data-action-kind="keep"]').first().click();
    await expect(stage).toHaveAttribute("data-phase", "bottom");
    expect(await stage.getAttribute("data-decision-kind")).toBe("choose_objects");
    // Same room: the seven cards are still the seven cards.
    expect(await stage.locator(".mull__slot").count()).toBe(7);
    await expect(page.getByTestId("prompt-dialog")).toBeHidden();

    await stage.locator("[data-action-id]").first().click();
    await waitForOurTurn(page);
    await expect(stage).toBeHidden();
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

    // Park the pointer first. It is still where Keep was, and the hand deals in
    // underneath that spot -- so a card arriving under a still pointer gets a
    // real hover and fills the rail before this test has hovered anything. On
    // CI's slow runner that is what happened, twice, with the preview cycling
    // Forest -> Vivid Creek as the fan settled.
    await page.getByTestId("table").hover({ position: { x: 2, y: 2 } });
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
