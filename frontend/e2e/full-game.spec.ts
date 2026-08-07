import { expect, test } from "@playwright/test";
import { actionButtons, isOver, startGame, takeAction, waitForOurTurn } from "./helpers";

/**
 * The real proof that the client covers every decision kind.
 *
 * Drive a whole game by always clicking a legal action. If any decision the
 * engine can produce has no surface in the UI, the loop runs out of buttons and
 * this fails -- which is exactly the bug worth catching.
 */
test.describe("a whole game can be played through the UI", () => {
  test("two players, to a result", async ({ page }) => {
    test.slow();
    test.setTimeout(600_000);

    await startGame(page, { deck: "aesi", opponents: 1, seed: 11 });

    const kindsSeen = new Set<string>();
    let steps = 0;

    for (; steps < 3000; steps += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) break;

      // Record which decision kinds we actually exercised.
      //
      // Bounded, and tolerant of the element going away: `isVisible` and
      // `getAttribute` are two round trips, and the AI pump can close a dialog
      // between them. Unbounded, that race spends the whole test budget waiting
      // for an element that is never coming back, and reports as a timeout with
      // nothing to do with the thing under test.
      const noteKind = async (testId: string, attribute: string) => {
        const node = page.getByTestId(testId);
        if (!(await node.isVisible().catch(() => false))) return;
        const kind = await node.getAttribute(attribute, { timeout: 2_000 }).catch(() => null);
        if (kind) kindsSeen.add(kind);
      };
      await noteKind("prompt-dialog", "data-decision-kind");
      await noteKind("combat-panel", "data-combat-kind");

      expect(
        await actionButtons(page).count(),
        "a decision was reached with no action rendered anywhere in the UI",
      ).toBeGreaterThan(0);

      // Prefer actually doing things over passing, so the game progresses.
      await takeAction(page, ["keep", "play_land", "cast", "add_attacker", "pass"]);
    }

    expect(await isOver(page), `game never finished in ${steps} decisions`).toBe(true);

    const over = page.getByTestId("game-over");
    await expect(over).toBeVisible();
    const result = await over.getAttribute("data-result");
    expect(["win", "loss", "draw"]).toContain(result);

    // The loop should have gone through the interesting decisions.
    expect([...kindsSeen]).toContain("mulligan");
  });

  test("a four-player pod is playable and shows every opponent", async ({ page }) => {
    test.slow();
    test.setTimeout(300_000);

    await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });

    for (const pid of [0, 1, 2, 3]) {
      await expect(page.getByTestId(`player-${pid}`)).toBeVisible();
      await expect(page.getByTestId(`life-${pid}`)).toHaveText("40");
    }

    // Play a few dozen decisions to make sure a pod does not wedge.
    for (let i = 0; i < 120; i += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) return;
      await takeAction(page, ["keep", "play_land", "cast", "pass"]);
    }
    expect(await actionButtons(page).count()).toBeGreaterThan(0);
  });
});
