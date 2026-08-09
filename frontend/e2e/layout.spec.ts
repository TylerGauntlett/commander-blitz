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
        [".acts__list", ".stackpanel", ".preview", ".table__foot"].map((selector) => {
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

/**
 * The board is laid out the way it is played: a player's lands are the row
 * nearest *them*.
 *
 * This is the one assertion that catches the whole feature going backwards. Both
 * orders render perfectly well and every content-level check passes through
 * either, so the only thing that notices a flipped `LANES` array or a dropped
 * `mirrored` prop is a comparison of two numbers.
 */
test("lands sit nearest the player who controls them, on both sides of the table", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 950 });
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await waitForOurTurn(page);

  const bands = await page.evaluate(() => {
    const midOf = (root: Element, lane: string) => {
      const node = root.querySelector(`[data-testid$="-${lane}"]`);
      if (!node) return null;
      const box = node.getBoundingClientRect();
      return box.top + box.height / 2;
    };
    const mine = document.querySelector(".play__mine .mat");
    const theirs = document.querySelector(".play__opponents .mat");
    return {
      mine: mine && { lands: midOf(mine, "Lands"), creatures: midOf(mine, "Creatures") },
      theirs: theirs && {
        lands: midOf(theirs, "Lands"),
        creatures: midOf(theirs, "Creatures"),
      },
    };
  });

  expect(bands.mine, "expected a viewer mat").not.toBeNull();
  if (bands.mine?.lands != null && bands.mine.creatures != null) {
    expect(
      bands.mine.lands,
      "your lands must be the band closest to your hand, not the far one",
    ).toBeGreaterThan(bands.mine.creatures);
  }

  // An opponent's mat is mirrored, so their lands are against their own edge of
  // the screen and the two creature bands meet in the middle. Their lanes are
  // only rendered once they hold something, so this half is conditional.
  if (bands.theirs?.lands != null && bands.theirs.creatures != null) {
    expect(
      bands.theirs.lands,
      "an opponent's mat is not mirrored: their lands should sit above their creatures",
    ).toBeLessThan(bands.theirs.creatures);
  }
});

/**
 * The viewer's own board holds still as it is played on.
 *
 * It did not. An empty lane collapsed to a 30px strip, so playing your first
 * creature shoved your land row down by a whole card and killing it shoved the
 * row back up -- under the cursor, mid-decision, on the one mat that owns every
 * drop target. The orb's mana row did the same thing a second time, several
 * times a turn, as mana was tapped and spent.
 *
 * The viewer's three lanes are now always rendered at a full card's height and
 * the mana row has a reserved slot, so a permanent of the viewer's own entering
 * or leaving moves nothing.
 *
 * This measures *relative* positions inside the mat, not absolute screen
 * coordinates, and the distinction is the whole point. An opponent's mat is
 * still content-sized -- a compact mat has no width to spare for an empty lane
 * (see PlayerMat) -- so the row above can still translate the viewer's board
 * down the screen. What must never change again is the distance between the
 * viewer's own bands, because that is the gap a card jumps across.
 */
test("the viewer's bands do not move as permanents enter and leave play", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1600, height: 950 });
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await waitForOurTurn(page);

  /** Each band's offset from the top of the viewer's own mat. */
  const offsets = () =>
    page.evaluate(() => {
      const mat = document.querySelector(".play__mine .mat");
      const from = mat?.getBoundingClientRect().top ?? Number.NaN;
      const off = (selector: string) => {
        const node = document.querySelector(`.play__mine ${selector}`);
        return node ? node.getBoundingClientRect().top - from : Number.NaN;
      };
      return {
        creatures: off('[data-testid$="-Creatures"]'),
        globals: off('[data-testid$="-Artifacts-Enchantments"]'),
        lands: off('[data-testid$="-Lands"]'),
      };
    });

  const samples = [await offsets()];
  for (let i = 0; i < 20; i += 1) {
    await takeAction(page, ["play_land", "cast", "pass"]);
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      break;
    samples.push(await offsets());
  }

  for (const key of ["creatures", "globals", "lands"] as const) {
    const seen = samples.map((s) => s[key]).filter((n) => !Number.isNaN(n));
    const drift = Math.max(...seen) - Math.min(...seen);
    // The budget is for sub-pixel rounding, not for a row of anything: the
    // regression this guards against is worth a whole card height, so nothing
    // subtle can hide underneath it.
    expect(
      drift,
      `the ${key} band moved ${Math.round(drift)}px within the mat; the board is jumping again`,
    ).toBeLessThan(6);
  }
});

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
