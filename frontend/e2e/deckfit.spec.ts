/**
 * The board fits a Steam Deck, with no scrollbar anywhere.
 *
 * This is a stronger claim than `handheld.spec.ts` makes and it is the one the
 * posture actually depends on: a Deck is held at arm's length in one position,
 * so a board you have to scroll is a board whose bottom half does not exist.
 * Every other gate in this suite measures whether a thing is big enough to
 * read. This one measures whether all of it is on screen at once.
 *
 * It runs at 1200x800 as well as 1280x800, and the second size is not a
 * duplicate of the first: 1200 is the same height with a narrower right rail,
 * so the action panel and the opponent strip both have less room to lay out in
 * while the vertical budget is unchanged. Every regression found while writing
 * this appeared at one width and not the other.
 *
 * The failure this exists to catch is specific and was live: the 16px floor
 * pushed a band label onto a second line, `logic/zoomFit.ts` went on modelling
 * it as one (`LANE_CHROME.labelAboveH`), and the solver left the board's cards
 * 7px wider than would fit -- so the viewer's own mat overflowed and
 * `.play__mine`'s `overflow-y: auto` turned that into a silent scroll with the
 * graveyard count below the fold. Nothing was too small; nothing had collapsed.
 */

import { type Page, expect, test } from "@playwright/test";
import { handheldAssert } from "./handheldAssert";
import { startGame, takeAction, waitForOurTurn } from "./helpers";

const SIZES = [
  { w: 1200, h: 800 },
  { w: 1280, h: 800 },
] as const;

/** Play far enough in that the lanes are holding something. */
async function develop(page: Page, steps = 14): Promise<void> {
  await waitForOurTurn(page);
  for (let i = 0; i < steps; i += 1) {
    if (
      await page
        .getByTestId("game-over")
        .isVisible()
        .catch(() => false)
    )
      return;
    await takeAction(page, ["keep", "play_land", "cast", "pass"]);
  }
  for (let i = 0; i < 12; i += 1) {
    /*
     * `[data-modal-root]`, not the dialog by name.
     *
     * That is the app's own word for "something is on top and owns the ring"
     * (`input/stops.ts:89-114`), and there are two such surfaces now -- the
     * generic dialog and `OpeningHand`. Naming one of them meant this loop
     * silently stopped clearing the opening hand, and the symptom would have
     * been every later `hover()` timing out against a full-screen surface it
     * could never reach -- which is the exact failure the comment above
     * describes, arrived at a second time.
     */
    const modal = page.locator("[data-modal-root]").last();
    if (!(await modal.isVisible().catch(() => false))) return;
    const choice = modal.locator("[data-action-id]:not([disabled])").first();
    if (!(await choice.count())) return;
    await choice.click();
  }
}

/**
 * Anything the player would have to scroll to see.
 *
 * Asked of the containers rather than of their children, because the child that
 * went missing is different every time -- a band label, a pile, a row of the
 * action list -- and the container is the thing that either fits or does not.
 */
async function scrollers(page: Page): Promise<{ selector: string; by: number }[]> {
  return page.evaluate(() => {
    const out: { selector: string; by: number }[] = [];
    for (const selector of [
      ".table",
      ".table__body",
      ".play",
      ".play__mine",
      ".play__mine .mat",
      ".play__opponents",
      /*
       * The seat, but NOT `.orb` inside it.
       *
       * `.orb` clips a deliberately oversized decorative wash, so its
       * `scrollHeight` always exceeds its box by design and asking this
       * question of it only ever returns yes. The mat is the box that either
       * holds a seat or does not.
       */
      ".mat--compact",
      ".table__foot",
      ".hand",
    ]) {
      for (const el of document.querySelectorAll<HTMLElement>(selector)) {
        const by = el.scrollHeight - el.clientHeight;
        // 2px of sub-pixel slack, for the reason handheldAssert's SLACK exists.
        if (by <= 2) continue;
        /*
         * WHICH CHILD, because the container is never the answer.
         *
         * "`.play__mine .mat` is 39px over" is true and unactionable: a mat is
         * a panel and a lane column, and the fix is different depending on
         * which one grew. The child that reaches furthest past the box is the
         * one to look at, and naming it here saved a second full run every time
         * this fired.
         */
        const box = el.getBoundingClientRect();
        let worst = "";
        let reach = 0;
        // Every descendant, not just the children: a lane whose own box fits
        // while its CARDS spill is the ordinary shape of this, and a
        // child-only walk reports nothing at all for it.
        for (const kid of el.querySelectorAll<HTMLElement>("*")) {
          const past = Math.round(kid.getBoundingClientRect().bottom - box.bottom);
          if (past <= reach) continue;
          reach = past;
          const cls = (kid.className || "")
            .toString()
            .trim()
            .split(/\s+/)
            .slice(0, 2)
            .join(".");
          worst = `${cls || kid.tagName.toLowerCase()} by ${past}`;
        }
        out.push({ selector: worst ? `${selector} (${worst})` : selector, by });
      }
    }
    return out;
  });
}

for (const { w, h } of SIZES) {
  test.describe(`the whole board is on screen at ${w}x${h}`, () => {
    test.use({ viewport: { width: w, height: h } });

    test("a two-player board, played in", async ({ page }) => {
      await startGame(page, { opponents: 1, seed: 7 });
      await develop(page);
      expect(await scrollers(page)).toEqual([]);
      // The page itself must not scroll either -- `body { overflow: hidden }`
      // would hide it, so this asks the documentElement directly.
      expect(
        await page.evaluate(
          () => document.documentElement.scrollHeight - document.documentElement.clientHeight,
        ),
      ).toBeLessThanOrEqual(2);
    });

    /*
     * Two opponents, which is the case that fell between the other two.
     *
     * One opponent and three were the obvious ends and the only ones covered,
     * and the seat layout switches arrangement somewhere between them -- so two
     * used the one-line strip at ~470px per mat, where it does not fit, and
     * every three-player game sat 16px over its cap with the overflow hidden.
     * Neither test could see it. A Storybook sweep found it, and this is where
     * it belongs.
     */
    test("three players, which is the density that fell between the tests", async ({
      page,
    }) => {
      await startGame(page, { opponents: 2, seed: 3 });
      await develop(page);
      expect(await scrollers(page)).toEqual([]);
    });

    test("a four-seat pod, which is the density that decides it", async ({ page }) => {
      await startGame(page, { opponents: 3, seed: 5 });
      await develop(page);
      expect(await scrollers(page)).toEqual([]);
    });

    test("the floors and the budgets still hold", async ({ page }) => {
      await startGame(page, { opponents: 1, seed: 7 });
      await develop(page);
      const report = await page.evaluate(handheldAssert);
      expect(report.pass, report.failures.join("\n  ")).toBe(true);
    });
  });
}
