import { test } from "@playwright/test";
import {
  actionsOfKind,
  budget,
  enabledActionButtons,
  isOver,
  pickDeck,
  startGame,
  waitForOurTurn,
} from "./helpers";

/**
 * Not an assertion suite -- a camera.
 *
 * Plays a real game at cinematic speed and photographs each surface, so the
 * result can be looked at rather than guessed about. Run it with
 * `npx playwright test playtest --grep-invert nothing` and read
 * `e2e-shots/`. Skipped by default so it never gates a normal run.
 */
test.describe("playtest capture", () => {
  test.skip(!process.env.PLAYTEST, "set PLAYTEST=1 to capture screenshots");

  test("photograph a game", async ({ page }) => {
    test.setTimeout(budget(600_000));

    const shots: string[] = [];
    const shoot = async (name: string) => {
      if (shots.includes(name)) return;
      shots.push(name);
      await page.screenshot({ path: `e2e-shots/${shots.length}-${name}.png`, fullPage: false });
    };

    // "fast" rather than "instant": the captures should show the banners and
    // floating numerals, which instant deliberately skips. Set through the
    // stored preference, because the control itself sits behind any modal.
    await page.addInitScript(() => {
      window.localStorage.setItem("commanderblitz.speed", "fast");
    });

    // The front door first, with its entrance animation finished.
    await page.goto("/");
    await page.getByTestId("home").waitFor();
    await page.waitForTimeout(900);
    await shoot("door");

    // Then the lobby, which is the screen this flow is actually about.
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await page.getByTestId("opponents-1").click();
    await pickDeck(page, "aesi");
    await page.waitForTimeout(600);
    await shoot("lobby");

    await page.getByPlaceholder("random").fill("3");
    await page.getByTestId("lock-in").click();
    await page.getByTestId("start-game").click();
    await page.getByTestId("table").waitFor({ timeout: 30_000 });

    await waitForOurTurn(page);
    await page.waitForTimeout(400);
    await shoot("mulligan");

    // The shots that make the review worth doing. Stop as soon as we have
    // them rather than playing all the way out.
    const WANTED = ["board-midgame", "combat-attackers", "combat-arrows", "hover-preview"];

    for (let i = 0; i < 260; i += 1) {
      if (WANTED.every((name) => shots.includes(name))) break;
      if (await isOver(page)) break;
      await waitForOurTurn(page);
      if (await isOver(page)) break;

      const dialog = page.getByTestId("prompt-dialog");
      const modal = await dialog.isVisible().catch(() => false);
      if (modal) {
        const kind = await dialog.getAttribute("data-decision-kind");
        await shoot(`prompt-${kind}`);
      }

      const panel = page.getByTestId("combat-panel");
      if (await panel.isVisible().catch(() => false)) {
        const kind = await panel.getAttribute("data-combat-kind");
        await shoot(`combat-${kind}`);
        if (kind === "attackers" && (await actionsOfKind(page, "add_attacker").count())) {
          await actionsOfKind(page, "add_attacker").first().click();
          await shoot("combat-staged");
          const confirm = page.getByTestId("combat-confirm");
          if (await confirm.isEnabled().catch(() => false)) {
            await confirm.click();
            await shoot("combat-arrows");
            continue;
          }
        }
      }

      // A mid-game board with permanents down is the interesting picture.
      const permanents = await page.locator('[data-testid^="mat-0"] .card').count();
      if (permanents >= 5) await shoot("board-midgame");
      if (await page.locator(".cardstack__count").count()) await shoot("stacking");

      // Hover something to capture the preview panel. Not while a decision modal
      // is up: its backdrop covers the hand, so the hover retries until the test
      // times out and the capture stops at the mulligan -- which is exactly how
      // far the committed shots got.
      const hand = page.locator(".hand .card");
      if (!modal && (await hand.count())) {
        await hand.first().hover();
        await shoot("hover-preview");
      }

      const stack = page.locator(".sitem");
      if (await stack.count()) await shoot("stack-panel");

      for (const kind of ["keep", "play_land", "cast", "pass"]) {
        const candidate = actionsOfKind(page, kind).first();
        if (await candidate.count()) {
          await candidate.click();
          break;
        }
        if (kind === "pass") await enabledActionButtons(page).first().click();
      }
    }

    await shoot("game-over");

    console.log(`captured ${shots.length} shots: ${shots.join(", ")}`);
  });

  /**
   * The pod, separately.
   *
   * Three opponents is the layout every sizing decision in cycle 3 was made
   * against, and the one a two-player capture says nothing about.
   */
  test("photograph a four-player pod", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await page.addInitScript(() => {
      window.localStorage.setItem("commanderblitz.speed", "instant");
    });
    await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });

    for (let i = 0; i < 90; i += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) break;
      let clicked = false;
      for (const kind of ["keep", "play_land", "cast", "pass"]) {
        const candidate = actionsOfKind(page, kind).first();
        if (await candidate.count()) {
          await candidate.click();
          clicked = true;
          break;
        }
      }
      if (!clicked) await enabledActionButtons(page).first().click();
    }

    await page.waitForTimeout(400);
    await page.screenshot({ path: "e2e-shots/pod-1-board.png" });
  });
});
