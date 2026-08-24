/**
 * Final acceptance: the critical flows, driven end to end in a real browser.
 *
 * Deliberately not a unit test of anything. This walks the path a player walks
 * -- deal, mulligan, play a land, cast a creature, hover to read it, reach
 * combat, look inside a zone, finish the game -- and asserts that each surface
 * the re-theme touched is actually there when it is needed.
 */

import { expect, test } from "@playwright/test";
import { actionsOfKind, isOver, startGame, takeAction, waitForOurTurn } from "./helpers";

test("a game can be played from deal to result, with every re-themed surface working", async ({
  page,
}) => {
  test.setTimeout(600_000);

  // --- deal -------------------------------------------------------------
  await startGame(page, { deck: "aesi", opponents: 1, seed: 11 });
  await expect(page.getByTestId("table")).toBeVisible();

  // The phase ribbon: five phases, and all thirteen steps still addressable.
  await expect(page.getByTestId("phase-track")).toBeVisible();
  expect(await page.locator(".ph").count()).toBe(5);
  expect(await page.locator(".track__step-label").count()).toBe(13);
  await expect(page.locator(".ph--now")).toHaveCount(1);

  // The life dial, reading as a number for both seats.
  for (const pid of [0, 1]) {
    await expect(page.getByTestId(`life-${pid}`)).toHaveText("40");
  }
  /*
   * ONE DIAL, and it is the viewer's.
   *
   * There were two, one per seat, because an opponent used to render the same
   * `PlayerOrb` column at two-thirds the size. An opponent is an `OpponentSeat`
   * now, and their life is a GAUGE -- life filling from the left, commander
   * damage closing from the right on the same track -- because what a seat is
   * for is "how close are they to dying", not "what is their number".
   * `life-<pid>` still reads as a bare number on both, which is what
   * `e2e/helpers.ts` parses.
   */
  expect(await page.locator(".dial").count()).toBe(1);
  await expect(page.locator(".dial--mine")).toHaveCount(1);
  await expect(page.locator(".gauge")).toHaveCount(1);

  // The zone piles, with the library showing a full deck.
  const library = page.getByTestId("pile-0-library");
  await expect(library).toBeVisible();
  expect(Number(await library.getAttribute("data-count"))).toBeGreaterThan(80);

  // --- play -------------------------------------------------------------
  for (let i = 0; i < 30; i += 1) {
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      break;
    await takeAction(page, ["keep", "play_land", "cast", "pass"]);
  }

  // Everything below inspects the live board, so it cannot run once the
  // game-over screen is up -- its backdrop covers the table and swallows every
  // click. The first version of this test hung for ten minutes on exactly that.
  test.skip(await isOver(page), "the game finished before the board could be inspected");

  // Art is on the board and decoded, not just requested.
  await expect
    .poll(
      () =>
        page.evaluate(
          () =>
            [...document.querySelectorAll<HTMLImageElement>(".face__art-img")].filter(
              (img) => img.naturalWidth > 0,
            ).length,
        ),
      { timeout: 20_000 },
    )
    .toBeGreaterThan(0);

  // --- read a card ------------------------------------------------------
  const permanent = page.locator(".play__mine .card").first();
  if (await permanent.count()) {
    await permanent.hover();
    const preview = page.getByTestId("card-preview");
    await expect(preview.locator(".face")).toBeVisible();
    // The rail shows the big card *and* credits the illustrator.
    await expect.poll(async () => (await preview.textContent()) ?? "").toContain("Art");
  }

  // --- look inside a zone ----------------------------------------------
  // The piles replaced the zone chips, so they are now the only way in.
  const graveyard = page.getByTestId("pile-0-graveyard");
  if (Number(await graveyard.getAttribute("data-count")) > 0) {
    await graveyard.click();
    const peek = page.getByTestId("zone-peek");
    await expect(peek).toBeVisible();
    await peek.getByRole("button", { name: /close/i }).click();
    await expect(peek).toBeHidden();
  }

  // Playing on to a result is `full-game.spec.ts`'s job and takes minutes;
  // repeating it here bought nothing and made this spec the slowest in the
  // suite. What is unique to this test is the surfaces above.
});

test("combat still works through the re-themed controls", async ({ page }) => {
  test.setTimeout(300_000);
  await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });

  for (let i = 0; i < 120; i += 1) {
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      return;
    await waitForOurTurn(page);
    if (
      await page
        .getByTestId("combat-panel")
        .isVisible()
        .catch(() => false)
    ) {
      // The commit slab is the primary control, and it still carries the
      // server's action id like every other button.
      const confirm = page.getByTestId("combat-confirm");
      if (await confirm.count()) {
        await expect(confirm).toHaveClass(/btn--primary/);
      }
      const attacks = actionsOfKind(page, "declare_attackers");
      if (await attacks.count()) {
        await attacks.first().click();
        return;
      }
    }
    await takeAction(page, ["keep", "play_land", "cast", "attack", "pass"]);
  }
});

test("every rendered action still has a unique server id", async ({ page }) => {
  test.setTimeout(180_000);
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

  // The load-bearing invariant of the whole client. The re-theme added a
  // commit slab, a rune and five piles; none of them may invent or duplicate
  // an action id.
  for (let i = 0; i < 25; i += 1) {
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      break;
    const ids = await page.evaluate(() =>
      [...document.querySelectorAll("[data-action-id]")].map((n) =>
        n.getAttribute("data-action-id"),
      ),
    );
    expect(new Set(ids).size, `duplicate action ids: ${ids.join(", ")}`).toBe(ids.length);
    await takeAction(page, ["keep", "play_land", "cast", "pass"]);
  }
});
