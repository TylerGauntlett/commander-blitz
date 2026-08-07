import { type Locator, type Page, expect } from "@playwright/test";

/**
 * Driving the client the way a player does: through the DOM.
 *
 * Every legal action is a button carrying `data-action-id`, which is the
 * server's opaque id. That invariant is what makes these helpers possible --
 * a spec never has to know the rules, only that a button exists.
 */

/**
 * Put the narration on its fastest setting so specs are not paced by it.
 *
 * Set through the persisted preference rather than by clicking the control: a
 * decision modal covers the tool bar, so the button is genuinely unreachable
 * for most of a game.
 */
export async function setInstant(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem("automtg.speed", "instant");
  });
}

/** Start a game and wait for the table. */
export async function startGame(
  page: Page,
  options: { deck?: string; opponents?: number; seed?: number } = {},
): Promise<void> {
  await setInstant(page);
  await page.goto("/");
  await page.getByTestId("new-game").waitFor();

  if (options.deck) await page.getByTestId(`deck-${options.deck}`).click();
  if (options.opponents) await page.getByTestId(`opponents-${options.opponents}`).click();
  if (options.seed !== undefined) {
    await page.getByPlaceholder("random").fill(String(options.seed));
  }

  await page.getByTestId("start-game").click();
  await page.getByTestId("table").waitFor({ timeout: 30_000 });
}

/**
 * Every action the server says is legal, as rendered.
 *
 * Deliberately includes disabled buttons: the invariant worth testing is that a
 * decision always *has* a surface, not that it happens to be clickable at the
 * instant we looked. Input is gated while narration plays, so an enabled-only
 * selector races the animation rather than testing anything.
 */
export function actionButtons(page: Page): Locator {
  return page.locator("[data-action-id]");
}

/** The subset that can be clicked right now. */
export function enabledActionButtons(page: Page): Locator {
  return page.locator("[data-action-id]:not([disabled])");
}

export function actionsOfKind(page: Page, kind: string): Locator {
  return page.locator(`[data-action-kind="${kind}"]:not([disabled])`);
}

/**
 * Wait until it is the human's turn to decide, or the game is over.
 *
 * The client pumps the opponents one decision at a time, so "no buttons" is a
 * transient state rather than an error.
 */
export async function waitForOurTurn(page: Page, timeout = 60_000): Promise<void> {
  await expect
    .poll(
      async () => {
        if (
          await page
            .getByTestId("game-over")
            .isVisible()
            .catch(() => false)
        )
          return "over";
        const stalled = await page
          .getByTestId("stall-toast")
          .isVisible()
          .catch(() => false);
        if (stalled) return "stalled";
        return (await enabledActionButtons(page).count()) > 0 ? "ready" : "waiting";
      },
      { timeout, intervals: [120] },
    )
    .not.toBe("waiting");

  const stalled = await page
    .getByTestId("stall-toast")
    .isVisible()
    .catch(() => false);
  expect(stalled, "the client reported the game stopped progressing").toBe(false);
}

/** Click one legal action, chosen by a predicate over the visible buttons. */
export async function takeAction(page: Page, prefer: string[] = []): Promise<string | null> {
  await waitForOurTurn(page);
  if (
    await page
      .getByTestId("game-over")
      .isVisible()
      .catch(() => false)
  )
    return null;

  for (const kind of prefer) {
    const candidate = actionsOfKind(page, kind).first();
    if (await candidate.count()) {
      const id = await candidate.getAttribute("data-action-id");
      await candidate.click();
      return id;
    }
  }
  const first = enabledActionButtons(page).first();
  const id = await first.getAttribute("data-action-id");
  await first.click();
  return id;
}

/** The life total a player's orb is showing. */
export async function lifeOf(page: Page, pid: number): Promise<number> {
  const text = await page.getByTestId(`life-${pid}`).textContent();
  return Number(text);
}

export async function isOver(page: Page): Promise<boolean> {
  return page
    .getByTestId("game-over")
    .isVisible()
    .catch(() => false);
}
