import { expect, test } from "@playwright/test";
import {
  actionButtons,
  budget,
  isOver,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

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
    test.setTimeout(budget(600_000));

    await startGame(page, { deck: "aesi", opponents: 1, seed: 11 });

    const kindsSeen = new Set<string>();
    let steps = 0;
    let vanished = 0;

    for (; steps < 3000; steps += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) break;

      /*
       * A decision can come and go between two reads.
       *
       * With a stack resolving, the client is handed priority, draws its rows,
       * and moves on as the next item resolves -- and on CI's slow runner the
       * whole life of that decision fit between `waitForOurTurn` seeing two
       * enabled rows and the count below seeing none (traced: 2, then 0, 250ms
       * apart, with the rows back on screen in the failure screenshot). That is
       * not a decision with no surface; it is one that was already answered.
       * So an empty read goes back to waiting. A decision that genuinely
       * renders nothing still fails: `waitForOurTurn` times out waiting for an
       * enabled row, and a run of empty reads trips the assertion below.
       */
      if ((await actionButtons(page).count()) === 0 && vanished < 20) {
        vanished += 1;
        continue;
      }
      vanished = 0;

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
      // The mulligan and its bottoming half have their own screen, and they
      // carry the same attribute -- so this is a second surface, not a second
      // vocabulary. Without it `kindsSeen` would stop containing "mulligan" and
      // the assertion at the end of this test would be checking nothing.
      await noteKind("opening-hand", "data-decision-kind");
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
    test.setTimeout(budget(300_000));

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
