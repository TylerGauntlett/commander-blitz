/**
 * Two layout failures that every other check passes straight through.
 *
 * `body { overflow: hidden }` means the page reports
 * `scrollHeight === clientHeight` even while the board visibly runs under the
 * foot, so a naive overflow assertion is worthless here. Both of the bugs
 * below were present in the mockups and both passed exactly such a check --
 * see the design record (`docs/design-record.md#board-themes`), "Notes on fidelity".
 *
 * The lesson these encode is the one docs/playtest-feedback-03.md draws from
 * the mana-pip bug: an assertion about *content* passes happily through a
 * layout failure, so where a visual property reduces to a number, assert the
 * number.
 */

import { expect, test } from "@playwright/test";
import {
  budget,
  isOver,
  keepOpeningHand,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

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
 * coordinates, and the distinction is the whole point. What must never change
 * again is the distance between the viewer's own bands, because that is the gap a
 * card jumps across.
 *
 * **The zoom is pinned here, deliberately.** Progressive zoom re-solves the card
 * size as the board fills, which moves the bands on purpose -- so with it live this
 * assertion would have to be loosened past the point of catching a collapsing lane,
 * which is the bug it exists for. Pinned, it still guards that bug exactly as
 * written. The zoom's own obligations are asserted separately below: it must never
 * push a lane under the hand, and it must never leave the legibility band.
 */
test("the viewer's bands do not move as permanents enter and leave play", async ({ page }) => {
  /*
   * NO LONGER PINNED AS A KNOWN FAILURE (TECH_DEBT FT-04).
   *
   * This carried a conditional `test.fail()` for a creatures band measured
   * drifting 9-41px across repeats. Re-measured, the drift does not reproduce:
   * zero, in five repeats under `E2E_SLOW=2 CI=1` and in instrumented runs that
   * sampled every band every 25ms after each action -- including with the CPU
   * throttled six times. The suspected mechanism was Motion's `layout` on
   * `Lane`, whose JS-driven transform `document.getAnimations()` cannot see;
   * no lane ever reported a computed transform other than `none` in any of
   * those samples, but `settled()` below now waits for one anyway, so a
   * measurement can no longer land mid-flight whatever the cause.
   *
   * AND THE SPEC HAD STOPPED EXERCISING ANYTHING, which is half of why it looked
   * stable. `takeAction` presses the first enabled button when none of the
   * preferred kinds is offered, and on the opening hand that is "Mulligan" --
   * so the twenty actions were six mulligans, a bottoming down to one card, and
   * a game in which one land entered play. A board that never changes cannot
   * drift. The hand is kept now, and the twenty actions play lands and spells.
   *
   * If it drifts again it fails, as a relationship assertion should: the
   * budget is not re-baselined, and a moving band is the bug.
   */
  test.setTimeout(budget(180_000));
  await page.setViewportSize({ width: 1600, height: 950 });
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7, zoomLock: true });
  await keepOpeningHand(page);
  await waitForOurTurn(page);

  /*
   * Sample only once nothing is moving.
   *
   * `.mat` and every band animate their layout through Framer, and
   * `getBoundingClientRect` reports the *in-flight* box -- so a sample taken
   * the instant `takeAction` returns catches the mat and the band mid-flight
   * and reads an offset neither of them ever settles at. That is the whole of
   * the 9px "drift" this test used to report: measured with a settle in front
   * of it, across the same twenty actions, the drift is exactly zero.
   *
   * Infinite animations are excluded because they never finish by definition --
   * the focus ring's sheen and the commit slab's waiting pulse both loop, and
   * waiting on those waits forever.
   *
   * AND THE TRANSFORMS, because `getAnimations()` only sees CSS and Web
   * Animations. Motion's `layout` correction is driven from JavaScript, frame
   * by frame, through the element's inline `transform` -- invisible to that
   * list, and exactly what moves a `getBoundingClientRect` while it runs. The
   * mat and its bands are the boxes measured, so they are the ones that have
   * to be at rest.
   */
  const settled = async () => {
    await page.waitForFunction(
      () =>
        document
          .getAnimations()
          .filter((a) => Number.isFinite(a.effect?.getTiming().iterations ?? 1))
          .every((a) => a.playState !== "running") &&
        [...document.querySelectorAll(".play__mine .mat, .play__mine .lane")].every(
          (el) => getComputedStyle(el).transform === "none",
        ),
      undefined,
      { timeout: 5_000 },
    );
  };

  /** Each band's offset from the top of the viewer's own mat. */
  const offsets = async () => {
    await settled();
    return page.evaluate(() => {
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
  };

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

  // The budget is for sub-pixel rounding, not for a row of anything: the
  // regression this guards against is worth a whole card height, so nothing
  // subtle can hide underneath it.
  const BUDGET = 6;
  const drifts = (["creatures", "globals", "lands"] as const).map((key) => {
    const seen = samples.map((s) => s[key]).filter((n) => !Number.isNaN(n));
    return { key, drift: Math.max(...seen) - Math.min(...seen) };
  });

  for (const { key, drift } of drifts) {
    expect(
      drift,
      `the ${key} band moved ${Math.round(drift)}px within the mat; the board is jumping again`,
    ).toBeLessThan(BUDGET);
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

/* Progressive zoom ------------------------------------------------------
 *
 * The card size is solved against the space the board actually has, rather than
 * fixed at one ratio for the whole game (`logic/zoomFit.ts`,
 * `state/useZoomFit.ts`). Three properties matter, and only measurement notices any
 * of them: it has to *respond*, it has to stay inside the size band the card face
 * is legible in, and it must never buy space it does not have.
 */

/** The bounds from `logic/cardSize.ts`. Below the floor a card stops being readable. */
const MIN_CARD_W = 52;
const MAX_CARD_W = 150;

/** `--card-w` as resolved on a lane, which is the size cards actually render at. */
function laneCardWidths(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const of = (selector: string) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const raw = getComputedStyle(node).getPropertyValue("--card-w");
      const parsed = Number.parseFloat(raw);
      return Number.isFinite(parsed) ? parsed : null;
    };
    return { mine: of(".play__mine .lane"), pod: of(".play__opponents .lane") };
  });
}

test("the zoom uses the room a big display has, instead of one size for every screen", async ({
  page,
}) => {
  // The regression this catches is the feature being quietly pinned: every other
  // test here passes with `useZoomFit` returning its constants.
  await page.setViewportSize({ width: 2560, height: 1278 });
  await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
  await waitForOurTurn(page);

  // A 2560x1278 display has ~580px of lane budget against ~475px of content, and
  // spending it is the entire point of the feature. It should reach the ceiling.
  const zoom = Number(await page.getByTestId("table").getAttribute("data-zoom-board"));
  expect(zoom, "the board is not growing on a display with room to spare").toBeGreaterThan(1.2);

  // Polled, because `--card-w` is transitioned (`--t-zoom`) while the attribute
  // above changes instantly -- reading the variable once races the tween and lands
  // on whatever intermediate value the frame happened to hold.
  await expect
    .poll(async () => (await laneCardWidths(page)).mine, { timeout: 5_000 })
    .toBeGreaterThan(MAX_CARD_W - 1);
});

test("no card ever leaves the size band its face is legible in", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await page.setViewportSize({ width: 1600, height: 950 });
  await startGame(page, { deck: "aesi", opponents: 3, seed: 7 });
  await waitForOurTurn(page);

  // A pod is the case that pushes the floor: three mats share the row, and their
  // cards are the smallest anything renders at. `e2e/legibility.spec.ts` is
  // what established that a card still reads down there; this is what stops the
  // solver going below the size that was checked.
  for (let i = 0; i < 16; i += 1) {
    const { mine, pod } = await laneCardWidths(page);
    for (const [name, width] of [
      ["the viewer's", mine],
      ["an opponent's", pod],
    ] as const) {
      if (width === null) continue;
      expect(
        width,
        `${name} card shrank to ${width}px, past the legibility floor`,
      ).toBeGreaterThanOrEqual(MIN_CARD_W - 1);
      expect(
        width,
        `${name} card grew to ${width}px, wider than the preview rail's own card`,
      ).toBeLessThanOrEqual(MAX_CARD_W + 1);
    }
    if (await isOver(page)) break;
    await takeAction(page, ["play_land", "cast", "pass"]);
  }
});

/**
 * The obligation the zoom takes on by being allowed to grow at all.
 *
 * This is the same measurement as "the last lane never runs under the hand" at the
 * top of this file, but sampled at *every* action with the zoom live -- which makes
 * it strictly the stronger test. Growing the cards to fill the space is only safe if
 * it never overshoots, and a solver reading a stale or wrong budget overshoots
 * silently: the board still renders, it just hides its own last row.
 */
test("the zoom never grows the board under the hand", async ({ page }) => {
  test.setTimeout(budget(180_000));
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    for (let i = 0; i < 12; i += 1) {
      const spill = await page.evaluate(() => {
        const foot = document.querySelector(".table__foot");
        const mine = document.querySelector(".play__mine");
        const lanes = [...document.querySelectorAll(".play__mine .lane")];
        if (!foot || !mine || lanes.length === 0) return null;
        return {
          // Clamp to the scroll container: a lane below `.play__mine`'s own bottom
          // edge is scrolled out of view, not sitting under the hand.
          laneBottom: Math.min(
            lanes[lanes.length - 1].getBoundingClientRect().bottom,
            mine.getBoundingClientRect().bottom,
          ),
          footTop: foot.getBoundingClientRect().top,
        };
      });
      if (spill) {
        expect(
          spill.laneBottom,
          `${viewport.name}: the zoom grew the board under the hand at action ${i}`,
        ).toBeLessThanOrEqual(spill.footTop + 1);
      }
      if (await isOver(page)) break;
      await takeAction(page, ["play_land", "cast", "pass"]);
    }
  }
});

/**
 * The limit `docs/roadmap.md` used to record, as an assertion.
 *
 * An opponent's mat was content-sized, so a pod board growing translated the
 * viewer's whole board down the screen -- every drop target with it. Their lanes now
 * live in a fixed box (`--pod-lanes-h`) and scroll inside it, so their board filling
 * moves nothing. This is also what makes the viewer's own solve well-posed: the
 * opponent row's height has to be a function of the viewport alone.
 */
test("an opponent's board filling up does not move the viewer's board", async ({ page }) => {
  test.setTimeout(budget(180_000));
  await page.setViewportSize({ width: 1600, height: 950 });
  await startGame(page, { deck: "aesi", opponents: 3, seed: 7 });
  await waitForOurTurn(page);

  const topOfMine = () =>
    page.evaluate(() => {
      const mine = document.querySelector(".play__mine");
      return mine ? mine.getBoundingClientRect().top : Number.NaN;
    });

  // Sampling stops the moment somebody is eliminated. An orb gains a
  // `.orb__loss` line when its player dies, which grows the whole row by ~19px
  // -- and that is a different claim from the one this test makes. "Their board
  // filled up" must not move anything; "a player was knocked out" plainly may,
  // and pretending otherwise would either weaken this assertion or demand the
  // loss line be drawn somewhere it does not belong. Recorded as an open defect
  // in docs/design-record.md (Open fidelity findings) so the question is not lost.
  const eliminated = () => page.locator(".play__opponents .orb__loss").count();

  const samples = [await topOfMine()];
  for (let i = 0; i < 20; i += 1) {
    await takeAction(page, ["play_land", "cast", "pass"]);
    if (await isOver(page)) break;
    if ((await eliminated()) > 0) break;
    samples.push(await topOfMine());
  }
  expect(samples.length, "nobody got to play before somebody died").toBeGreaterThan(3);

  const seen = samples.filter((n) => !Number.isNaN(n));
  const drift = Math.max(...seen) - Math.min(...seen);
  expect(
    drift,
    `the viewer's board moved ${Math.round(drift)}px as the opponents played; the pod row is content-sized again`,
  ).toBeLessThan(6);
});
