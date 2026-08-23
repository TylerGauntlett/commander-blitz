/**
 * The handheld gates, at every state a player can reach.
 *
 * Runs in the `handheld` project, which is a 1280×800 viewport — a Steam Deck's
 * panel exactly. The desktop project deliberately ignores this file: running it
 * at 1600×950 would test the wide layout while claiming to test the compact one.
 *
 * What it asserts is `e2e/handheldAssert.ts`, and the numbers there are not
 * style preferences. The 16px floor comes from a 7-inch panel at 40–50cm, and
 * the round that produced it found 2.11px text that had looked fine in every
 * screenshot for months — because a reviewer already knows what the label says.
 * Hence the rule this file exists to keep:
 *
 * > Do not ship a controller mode without the 16px floor asserted in CI.
 */

import { expect, test } from "@playwright/test";
import { type HandheldReport, handheldAssert } from "./handheldAssert";
import { actionsOfKind, startGame, waitForOurTurn } from "./helpers";

/**
 * Wait until nothing is still moving.
 *
 * Every dialog here animates in from `scale: 0.96`, and
 * `getBoundingClientRect` reports the *scaled* box -- so a 44px button sampled
 * mid-entry measures 42.7px and the hit floor fails on a control that is the
 * right size. This cost one confusing loop: the button measured 44px in a live
 * browser and 43px in the spec, every time.
 *
 * `getAnimations` is exact where a fixed wait is a guess, and it covers Framer's
 * transforms because they run as Web Animations.
 */
async function settled(page: import("@playwright/test").Page): Promise<void> {
  await page.waitForFunction(
    () =>
      document
        .getAnimations()
        // Infinite ones never finish by definition -- the focus ring's sheen and
        // the commit slab's waiting pulse both loop forever, and waiting on them
        // waits for the heat death of the tab. Only entrances and exits move a
        // box, and those are the ones with a finite iteration count.
        .filter((a) => Number.isFinite(a.effect?.getTiming().iterations ?? 1))
        .every((a) => a.playState !== "running"),
    undefined,
    { timeout: 5_000 },
  );
}

/** Run the gate and fail with everything it found, not just the first thing. */
async function gate(
  page: import("@playwright/test").Page,
  where: string,
): Promise<HandheldReport> {
  await settled(page);
  const report = (await page.evaluate(handheldAssert)) as HandheldReport;
  expect(
    report.pass,
    `${where}\n  ${report.failures.join("\n  ")}\n  (min font ${report.minFontPx}px, ` +
      `min card ${report.minCardPx}px, ${report.stops} stops, ${report.cursors} cursor)`,
  ).toBe(true);
  return report;
}

test.describe("the handheld layout holds its floors", () => {
  test("the front door, the lobby and the catalogue", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("home").waitFor();
    await gate(page, "the front door");

    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await gate(page, "the pod lobby");

    await page.getByTestId("change-deck").click();
    await page.getByTestId("deck-catalog").waitFor();
    const catalogue = await gate(page, "the deck catalogue");

    /*
     * The trap, asserted where it matters most. With the catalogue open, every
     * stop on the lobby behind it is still in the document -- and a resolver
     * that took the first `[data-stop]` in document order would put the ring
     * there, because the lobby comes first in the markup.
     */
    expect(catalogue.stops, "the catalogue does not own the ring").toBeGreaterThan(0);
    const inside = await page.evaluate(() => {
      const dialog = document.querySelector('[data-testid="deck-catalog"]');
      const cursor = document.querySelector("[data-cursor]");
      return {
        hasDialog: !!dialog,
        cursorInside: !!(dialog && cursor && dialog.contains(cursor)),
      };
    });
    expect(inside.hasDialog).toBe(true);
    expect(inside.cursorInside, "the ring escaped the open catalogue").toBe(true);
  });

  test("the board, from the mulligan through combat", async ({ page }) => {
    await startGame(page, { deck: "edgar", opponents: 3, seed: 11 });

    // The mulligan owns the screen and the ring before anything else does.
    await gate(page, "the mulligan");

    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);
    await gate(page, "your turn, main phase");

    // A board with something on it: play whatever land is offered.
    const land = actionsOfKind(page, "play_land");
    if (await land.count()) {
      await land.first().click();
      await waitForOurTurn(page);
      await gate(page, "a land on the board");
    }

    // The zone viewer, which is a second full-screen surface.
    await page.keyboard.press("g");
    await page.getByTestId("zone-peek").waitFor();
    await gate(page, "the graveyard viewer");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("zone-peek")).toBeHidden();

    // The log overlay, which only exists on this layout.
    await page.keyboard.press("Tab");
    await page.getByTestId("log-overlay").waitFor();
    await gate(page, "the log overlay");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("log-overlay")).toBeHidden();
  });

  test("a four-seat pod is the density that decides it", async ({ page }) => {
    await startGame(page, { deck: "edgar", opponents: 3, seed: 4 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    const report = await gate(page, "a four-seat pod");

    /*
     * The two numbers the whole layout is built around, asserted directly
     * rather than only through `pass` -- so a regression names itself.
     */
    expect(report.minFontPx, "the 16px floor").toBeGreaterThanOrEqual(16);
    expect(report.minCardPx, "the 96px card floor").toBeGreaterThanOrEqual(96);
    expect(report.titleAttrs, "native tooltips are unreachable on a controller").toBe(0);
    expect(report.unreachable, "every stop must be reachable").toEqual([]);
  });
});

test.describe("the compact layout is the one being drawn", () => {
  test("the left rail leaves the grid and its contents survive", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    await expect(page.getByTestId("table")).toHaveAttribute("data-handheld", "true");

    /*
     * The stack moved rather than disappeared. Exactly one of it, because two
     * would put two `data-testid="stack-panel"` in the document -- which
     * Playwright's strict mode fails on, confusingly and far from the cause.
     */
    await expect(page.getByTestId("stack-panel")).toHaveCount(1);
    const inRightRail = await page.evaluate(
      () => !!document.querySelector('.rail--right [data-testid="stack-panel"]'),
    );
    expect(inRightRail, "the stack should ride in the right rail here").toBe(true);

    // The log is reachable, and closable, without a mouse.
    await expect(page.getByTestId("log-overlay")).toBeHidden();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("log-overlay")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("log-overlay")).toBeHidden();
  });

  test("the action list keeps its floor when the rail is full", async ({ page }) => {
    await startGame(page, { deck: "edgar", opponents: 3, seed: 11 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    /*
     * The regression this is for: moving the stack into the right rail left the
     * action list 41px tall holding 197px of content, with the decision's
     * prompt, its choices and the commit alternatives crushed together. The
     * list is where the turn happens, so it is the thing that may not be
     * squeezed.
     */
    const list = page.locator(".acts__list");
    const box = await list.boundingBox();
    expect(box?.height ?? 0, "the action list flattened").toBeGreaterThanOrEqual(74);

    const rail = await page.evaluate(() => {
      const el = document.querySelector(".rail--right");
      return el ? { client: el.clientHeight, scroll: el.scrollHeight } : null;
    });
    expect(rail).not.toBeNull();
    expect(
      (rail?.scroll ?? 0) - (rail?.client ?? 0),
      "the right rail overflows its own column",
    ).toBeLessThanOrEqual(2);
  });
});
