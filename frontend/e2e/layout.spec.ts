/**
 * Two layout failures that every other check passes straight through.
 *
 * `body { overflow: hidden }` means the page reports
 * `scrollHeight === clientHeight` even while the board visibly runs under the
 * foot, so a naive overflow assertion is worthless here. Both of the bugs
 * below were present in the mockups and both passed exactly such a check --
 * see mockups/README.md, "Notes on fidelity".
 *
 * The lesson these encode is the one docs/playtest-feedback-03.md draws from
 * the mana-pip bug: an assertion about *content* passes happily through a
 * layout failure, so where a visual property reduces to a number, assert the
 * number.
 */

import { expect, test } from "@playwright/test";
import { startGame, takeAction, waitForOurTurn } from "./helpers";

/** The two shapes the board is actually played at. */
const VIEWPORTS = [
  { name: "laptop 1600x950", width: 1600, height: 950 },
  { name: "desktop 2560x1278", width: 2560, height: 1278 },
];

/** A card is ~1.4x its width tall; less than this and the lane is collapsed. */
const MIN_LANE_HEIGHT = 24;

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("the last lane never runs under the hand", async ({ page }) => {
      await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
      await waitForOurTurn(page);

      // Play a few lands so the viewer's mat has real content to overflow with.
      for (let i = 0; i < 6; i += 1) {
        await takeAction(page, ["play_land", "cast", "pass"]);
        if (
          await page
            .getByTestId("game-over")
            .isVisible()
            .catch(() => false)
        )
          break;
      }

      const spill = await page.evaluate(() => {
        const foot = document.querySelector(".table__foot");
        // Measure the *lane*, never the mat. The mat is stretched to its grid
        // row, so its box always ends exactly at the row edge no matter how
        // far the cards inside overflow -- it reports success unconditionally.
        const lanes = [...document.querySelectorAll(".play__mine .lane")];
        if (!foot || lanes.length === 0) return null;
        const last = lanes[lanes.length - 1].getBoundingClientRect();
        return { laneBottom: last.bottom, footTop: foot.getBoundingClientRect().top };
      });

      expect(spill, "expected a viewer mat with at least one lane").not.toBeNull();
      if (!spill) return;
      expect(
        spill.laneBottom,
        "the last battlefield lane is hidden underneath the hand row",
      ).toBeLessThanOrEqual(spill.footTop + 1);
    });

    test("no panel silently collapses to nothing", async ({ page }) => {
      await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
      await waitForOurTurn(page);

      // At 950px these flattened to 0 in three of the five mockups before a
      // min-height floor was added. Nothing about the *content* changed, so
      // only a measurement notices.
      const heights = await page.evaluate(() =>
        [".bar__actions", ".stackpanel", ".preview", ".table__foot"].map((selector) => {
          const node = document.querySelector(selector);
          return { selector, height: node ? node.getBoundingClientRect().height : -1 };
        }),
      );

      for (const { selector, height } of heights) {
        if (height === -1) continue; // not rendered in this position; fine
        expect(height, `${selector} collapsed to ${height}px`).toBeGreaterThan(MIN_LANE_HEIGHT);
      }
    });

    test("cards scale with the viewport instead of staying 104px", async ({ page }) => {
      await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
      await waitForOurTurn(page);

      const base = await page.evaluate(() =>
        Number.parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue("--card-w-base"),
        ),
      );

      // The bug this replaced: `--card-w: 104px` was hard-coded, so this number
      // was 104 on every display from a 1366px laptop to a 4K monitor.
      expect(base).toBeGreaterThan(40);
      expect(base).toBeLessThan(140);
    });
  });
}

test("a taller viewport gets bigger cards than a shorter one", async ({ page }) => {
  // The actual regression guard for the clamp: if someone re-pins the base to a
  // constant, every other test here still passes and only this one fails.
  const read = async (width: number, height: number) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    return page.evaluate(() =>
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--card-w-base"),
      ),
    );
  };

  const short = await read(1600, 800);
  const tall = await read(2560, 1278);
  expect(tall).toBeGreaterThan(short);
});
