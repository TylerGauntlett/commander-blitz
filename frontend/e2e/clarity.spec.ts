/**
 * The cycle-2 clarity surfaces, driven in a real browser.
 *
 * Everything here answers a question the player could not previously answer by
 * looking: how much mana do I have, why is that card dim, what type is that
 * permanent, what is the opponent doing. See docs/playtest-feedback-01.md.
 *
 * These are deliberately assertions about *what is rendered*, not about
 * pixels -- a screenshot diff would fail on every palette tweak and tell us
 * nothing about whether the information reached the player.
 */

import { expect, test } from "@playwright/test";
import { actionButtons, actionsOfKind, budget, startGame, waitForOurTurn } from "./helpers";

test.describe("mana is visible", () => {
  test("the player orb counts every available mana in its panel", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();

    const row = page.getByTestId("mana-0");
    // The panel is permanent -- it says "no mana" rather than vanishing, because
    // a plate that comes and goes re-spaces the whole orb several times a turn.
    // Turn one, no lands down: there is nothing in it yet.
    await expect(row).toBeVisible();
    await expect(row.locator(".mana-grp")).toHaveCount(0);

    // Play lands until some appear, then the counted chips must add up to the
    // row's own formatted summary -- the two are derived separately.
    for (let i = 0; i < 60; i += 1) {
      if (await row.locator(".mana-grp").count()) break;
      const land = actionsOfKind(page, "play_land");
      const pass = actionsOfKind(page, "pass");
      if (await land.count()) await land.first().click();
      else if (await pass.count()) await pass.first().click();
      await page.waitForTimeout(80);
    }

    // One chip per *kind* of mana carrying a count, not one mark per mana: at
    // the real symbol's width a mark each wrapped to three rows in this column.
    const counts = await row
      .locator(".mana-grp")
      .evaluateAll((nodes) =>
        nodes.map((n) => Number((n as HTMLElement).dataset.count ?? "0")),
      );
    const available = counts.reduce((sum, n) => sum + n, 0);
    const summary = (await row.getAttribute("data-mana")) ?? "";
    expect(available).toBeGreaterThan(0);
    expect(summary.match(/\{/g) ?? []).toHaveLength(available);
  });
});

test.describe("unplayable cards say why", () => {
  test("hovering a dimmed hand card explains the gate", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    const dimmed = page.locator(".hand .card--dimmed").first();
    await expect(dimmed).toBeVisible();
    await dimmed.hover();

    const hint = page.getByTestId("unplayable-hint");
    await expect(hint).toBeVisible();
    // Whatever the reason, it must be a sentence rather than a code.
    await expect(hint).not.toHaveText("");
    await expect(hint).not.toHaveText(/^(mana|timing|targets|priority|land_drop)$/);
  });
});

test.describe("card type is encoded on the card", () => {
  test("lands and creatures carry different body tones and glyphs", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();

    const tones = await page
      .locator(".hand .face")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).dataset.typeTone));
    expect(tones.length).toBeGreaterThan(0);
    expect(tones.every(Boolean)).toBe(true);

    // An opening hand of this deck has both. If a future deck change breaks
    // that, the assertion below is the honest thing to fail on.
    expect(new Set(tones).size).toBeGreaterThan(1);

    // Every face carries a glyph, which is what still reads at 82px.
    const glyphs = await page.locator(".hand .face__glyph").allTextContents();
    expect(glyphs).toHaveLength(tones.length);
    expect(glyphs.every((g) => g.trim().length === 1)).toBe(true);
  });
});

test.describe("a decision's buttons exist exactly once", () => {
  test("no two rendered actions share an action id", async ({ page }) => {
    test.setTimeout(budget(300_000));
    await startGame(page, { deck: "aesi", opponents: 1, seed: 3 });

    for (let i = 0; i < 260; i += 1) {
      if (
        await page
          .getByTestId("game-over")
          .isVisible()
          .catch(() => false)
      )
        break;

      const ids = await actionButtons(page).evaluateAll((nodes) =>
        nodes.map((n) => (n as HTMLElement).dataset.actionId ?? ""),
      );
      // The invariant the action bar's stand-down rules exist to protect: a
      // modal or the combat panel owns a decision, never both it and the bar.
      expect(new Set(ids).size, `duplicate action ids rendered: ${ids.join(", ")}`).toBe(
        ids.length,
      );

      const next = page.locator("[data-action-id]:not([disabled])");
      if (!(await next.count())) {
        await page.waitForTimeout(120);
        continue;
      }
      for (const kind of ["keep", "play_land", "cast", "add_attacker", "pass"]) {
        const btn = actionsOfKind(page, kind);
        if (await btn.count()) {
          await btn
            .first()
            .click()
            .catch(() => {});
          break;
        }
      }
      await page.waitForTimeout(60);
    }
  });
});

test.describe("the hand fits on screen", () => {
  test("no card hangs below the viewport", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await page.waitForTimeout(800);

    const overflow = await page.evaluate(() => {
      const height = window.innerHeight;
      return [...document.querySelectorAll(".hand .card")]
        .map((c) => c.getBoundingClientRect().bottom)
        .filter((bottom) => bottom > height);
    });
    expect(overflow, "hand cards clipped by the bottom edge").toEqual([]);
  });
});

test.describe("zone peeking has a keyboard route", () => {
  test("g opens the graveyard and Esc closes it", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    await expect(page.getByTestId("zone-peek")).toBeHidden();
    await page.keyboard.press("g");
    await expect(page.getByTestId("zone-peek")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("zone-peek")).toBeHidden();
  });
});
