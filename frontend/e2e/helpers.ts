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
    // Sound now defaults to *on*, so a run would otherwise synthesise a voice
    // for every click and every beat across sixteen specs. Explicit here rather
    // than relying on the default, which is exactly what changed underneath it.
    window.localStorage.setItem("automtg.muted", "on");
  });
}

/**
 * Pin the shuffle, which the lobby no longer has a control for.
 *
 * The seed field is gone from the pod rail: a reproducible game is a debugging
 * tool rather than a question a player arriving to play has, and it was one of
 * two text boxes the focus ring could walk into and not out of. Determinism is
 * a window flag now, injected before the app boots -- the same seam
 * `lockZoom` uses, and for the reason stated there: a persisted preference
 * would survive into a real player's browser with nothing on screen to point
 * at, and a window global cannot outlive the page it was injected into.
 */
export async function pinSeed(page: Page, seed: number): Promise<void> {
  await page.addInitScript((value) => {
    (window as { __AUTOMTG_SEED?: number }).__AUTOMTG_SEED = value;
  }, seed);
}

/**
 * Pin the card zoom to the sizes that shipped before it existed.
 *
 * Progressive zoom re-solves the card size against the space available, so a spec
 * asserting that the board *holds still* is asserting against a feature whose job
 * is to move it. Pinning lets those specs keep measuring exactly what they were
 * written to measure, rather than being loosened until they no longer catch the bug
 * they exist for.
 *
 * A window flag, not a persisted preference: `localStorage` would survive into a
 * real player's browser and silently disable the feature with nothing to point at.
 * `?zoom=lock` is honoured too, for eyeballing before-and-after by hand.
 */
export async function lockZoom(page: Page): Promise<void> {
  await page.addInitScript(() => {
    (window as { __AUTOMTG_ZOOM_LOCK?: boolean }).__AUTOMTG_ZOOM_LOCK = true;
  });
}

/**
 * Open a pod, fill it, deal it, and wait for the table.
 *
 * Every spec but two enters here and nowhere else, which is why the lobby was
 * built to keep the hooks the old setup screen had: `new-game` is the lobby,
 * `deck-${id}` is a catalogue tile, `opponents-${n}` adds the nth CPU, and
 * `start-game` deals. Rewriting this one function is what let the rest of the
 * suite stay untouched.
 *
 * `opponents` counts CPU seats, so `opponents: 3` is a four-player pod.
 */
export async function startGame(
  page: Page,
  options: { deck?: string; opponents?: number; seed?: number; zoomLock?: boolean } = {},
): Promise<void> {
  await setInstant(page);
  if (options.zoomLock) await lockZoom(page);
  if (options.seed !== undefined) await pinSeed(page, options.seed);
  await page.goto("/");

  await page.getByTestId("create-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });

  // The nth click seats the nth CPU, and the button it lands on is numbered by
  // the pod size it would produce -- so this is always the *first* empty chair.
  for (let i = 1; i <= (options.opponents ?? 1); i += 1) {
    await page.getByTestId(`opponents-${i}`).click();
  }

  await pickDeck(page, options.deck ?? "aesi");

  await page.getByTestId("lock-in").click();
  await page.getByTestId("start-game").click();
  await page.getByTestId("table").waitFor({ timeout: 30_000 });
}

/** Open the deck catalogue for your own seat and take one. */
export async function pickDeck(page: Page, deckId: string): Promise<void> {
  await page.getByTestId("change-deck").click();
  await page.getByTestId("deck-catalog").waitFor();
  await page.getByTestId(`deck-${deckId}-take`).click();
  await expect(page.getByTestId("deck-catalog")).toBeHidden();
}

/**
 * Open the catalogue on its own, without joining a pod.
 *
 * BY ADDRESS, because the front door no longer carries a Decks card. The
 * catalogue is still a screen of the app and `/decks` is still its address --
 * what went away is a menu item that started nothing, not the route.
 */
export async function browseDecks(page: Page): Promise<void> {
  await page.goto("/decks");
  await page.getByTestId("deck-catalog").waitFor();
}

/**
 * Open a pod and leave the catalogue open on your own seat.
 *
 * The path an import really takes: you are choosing a deck, and the deck you
 * want is not in the list yet. Browsing from the door reaches the same
 * catalogue but has no seat to select a deck *into*.
 */
export async function openCatalog(page: Page): Promise<void> {
  await setInstant(page);
  await page.goto("/");
  await page.getByTestId("create-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
  await page.getByTestId("change-deck").click();
  await page.getByTestId("deck-catalog").waitFor();
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

/**
 * Play until we hold a combat declaration with something to declare.
 *
 * Shaped after the combat loops in `smoke.spec.ts` rather than a poll on a
 * predicate: reaching combat means casting creatures and surviving to the step,
 * so the loop has to keep taking whatever action exists. Returns false if the
 * game ends first, which is a legitimate outcome and a reason to skip rather
 * than to fail.
 *
 * Blocking needs the extra nudge in `prefer`: a creature that attacked is tapped
 * and cannot block, so a loop that happily attacks never reaches a blocker
 * decision with a blocker in it.
 */
export async function reachDecision(
  page: Page,
  kind: "attackers" | "blockers",
  limit = 400,
): Promise<boolean> {
  const panel = page.getByTestId("combat-panel");
  const wanted = kind === "attackers" ? "add_attacker" : "add_blocker";
  const prefer =
    kind === "attackers"
      ? ["keep", "play_land", "cast", "pass"]
      : ["keep", "play_land", "cast", "finish_declaration", "pass"];

  for (let i = 0; i < limit; i += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) return false;
    if (await panel.isVisible().catch(() => false)) {
      const seen = await panel.getAttribute("data-combat-kind").catch(() => null);
      if (seen === kind && (await actionsOfKind(page, wanted).count())) return true;
    }
    await takeAction(page, prefer);
  }
  return false;
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
