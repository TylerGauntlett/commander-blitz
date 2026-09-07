import { type Locator, type Page, expect } from "@playwright/test";

/**
 * A per-test budget, scaled by the same factor as `playwright.config.ts`.
 *
 * Specs write the number they mean (`test.setTimeout(budget(600_000))`) and the
 * environment says how much slower this machine is right now. See the config for
 * why the factor exists and who sets it.
 */
export function budget(ms: number): number {
  return ms * Number(process.env.E2E_SLOW ?? 1);
}

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
 * Answer the opening hand and leave the board playable.
 *
 * ONE PLACE, because a dozen specs need to get past this and every one of them
 * used to reach into the surface that draws it -- finding `prompt-dialog`,
 * checking `data-decision-kind`, clicking a label. When `OpeningHand` replaced
 * that dialog, all dozen would have had to change, which is the cost this
 * function exists to pay once.
 *
 * What it will NOT do is name a surface. It presses `data-action-kind`, which is
 * the server's own vocabulary and the same invariant the rest of this file is
 * built on: *every legal action is a button carrying `data-action-id`*. A spec
 * that goes through here keeps working whatever draws the screen next.
 *
 * IT ANSWERS BOTH HALVES. A London mulligan asks twice -- keep or mulligan, then
 * put N on the bottom -- and the second only appears once you have taken at
 * least one. `mulligans` is how many to take first, so a spec that wants to see
 * the bottoming step can ask for it instead of engineering a seed that produces
 * one.
 */
export async function keepOpeningHand(page: Page, mulligans = 0): Promise<void> {
  for (let i = 0; i < mulligans; i += 1) {
    const mull = actionsOfKind(page, "mulligan");
    await mull.first().waitFor({ timeout: 30_000 });
    await mull.first().click();
    // The new seven arrives as a fresh decision, so wait for the question to be
    // askable again rather than for a fixed time.
    await expect(actionsOfKind(page, "keep").first()).toBeVisible({ timeout: 30_000 });
  }

  const keep = actionsOfKind(page, "keep");
  if (await keep.count()) await keep.first().click();

  /*
   * And the bottoming half, if there is one.
   *
   * KEYED ON `data-phase`, not on the screen still being up. Answering the
   * first question leaves the surface mounted for the round trip with every
   * control disabled, so a loop that only asked "is it still there" grabbed the
   * disabled Mulligan button and waited out the whole test timeout against it.
   * A phase of `bottom` is the only thing that means there is a second question.
   *
   * Each card is its own button, so pressing the first ENABLED one answers one
   * pick; `min_count` of them finishes the decision and the screen goes.
   */
  const stage = page.getByTestId("opening-hand");
  /*
   * ONE READ OF THE DOM, NOT THREE. This used to `count()` the stage, then
   * `getAttribute` its phase, then count its buttons -- three round trips, and
   * a stage that left between the first and the second left `getAttribute`
   * waiting for an element that was never coming back. With no action timeout
   * configured that wait is unbounded, so the poll timed out at 30s reporting
   * the value of its *previous* iteration, "waiting", against a board that had
   * been playable for 29 of them. The window is the gap between two calls,
   * which a stage that now leaves on a 260ms clock (`OpeningHand.tsx`) hits
   * about once in fifteen keeps. A leaving stage counts as gone: it has
   * answered, and `waitForOurTurn` below is what waits for the board.
   */
  const settledPhase = (): Promise<"gone" | "bottom" | "waiting"> =>
    page.evaluate(() => {
      const root = document.querySelector<HTMLElement>('[data-testid="opening-hand"]');
      if (!root || root.dataset.closing !== undefined) return "gone";
      if (root.dataset.phase !== "bottom") return "waiting";
      return root.querySelector("[data-action-id]:not([disabled])") ? "bottom" : "waiting";
    });
  for (let guard = 0; guard < 8; guard += 1) {
    /*
     * Polled, not slept. This used to be up to eight fixed 200ms waits -- ~1.6s
     * of patience on a machine that may need more, and a stack of sleeps on one
     * that needs none -- which is the shape every load-sensitive timeout in the
     * suite had (TECH_DEBT FT-06). The condition is unchanged: the screen has
     * gone, or it is asking the second question and has an enabled card to
     * press. Anything else is the round trip, and we keep watching it.
     */
    await expect
      .poll(settledPhase, { timeout: budget(15_000), intervals: [100] })
      .not.toBe("waiting");
    if ((await settledPhase()) === "gone") break;
    await stage.locator("[data-action-id]:not([disabled])").first().click();
  }

  await waitForOurTurn(page);

  /*
   * PARK THE POINTER. The click on Keep left it where the Keep plate was, which
   * is the bottom of the screen -- and once the stage has gone, that is over
   * the hand. Chromium re-evaluates what is under a resting pointer after a
   * layout change, so a hand card gets hovered and the preview rail reads it,
   * with nobody having moved the mouse. Two specs then assert the rail is
   * still asking to be pointed at ("Hover a card"), and on a CI runner that
   * re-evaluation lands before the assertion does; on a developer machine it
   * lands after, which is the only reason they passed. The top-left corner is
   * the turn strip, which reads nothing.
   */
  await page.mouse.move(1, 1);
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
 * Answer whatever is on top until nothing is, so the board underneath is
 * reachable -- not merely built.
 *
 * A modal decision -- discarding to hand size is the one that bites -- takes
 * more presses to answer than a spec's step budget has left, so a builder used
 * to return with a prompt still up. `.prompt-backdrop` is `position: fixed;
 * inset: 0`, so every later `hover()` on a board card waited out the whole test
 * timeout against a surface it could never reach, and the failure named the
 * hover rather than the dialog behind it.
 *
 * `[data-modal-root]:not([data-closing])`, not the dialog by name and not the
 * bare attribute either. The selector is the app's own word for "something is
 * on top and owns the ring" (`input/stops.ts`), and there are two such surfaces
 * -- the generic dialog and `OpeningHand`. Naming one of them meant this loop
 * silently stopped clearing the opening hand. Dropping the `:not` was the
 * subtler miss: every surface animates out through `AnimatePresence`, so for
 * its exit duration a dialog whose last option has just been answered is still
 * in the DOM with its buttons. This loop found one of those a few milliseconds
 * after its own click, asked Playwright to click it, and Playwright -- having
 * watched the element detach -- waited for it to come back for the rest of a
 * six-minute budget, while the pump carried the game on to a board with no
 * dialog on it at all.
 *
 * The click is bounded for the same reason. It should never need to be: an
 * exiting dialog is excluded above, and an open one is either clickable or its
 * buttons are `disabled` while the answer is in flight. But a click that fails
 * here means the surface moved, and the right answer is to look again, not to
 * spend the test's whole budget waiting for one element.
 */
export async function clearPrompts(page: Page, presses = 12): Promise<void> {
  for (let i = 0; i < presses; i += 1) {
    const modal = page.locator("[data-modal-root]:not([data-closing])").last();
    if (!(await modal.isVisible().catch(() => false))) return;
    const choice = modal.locator("[data-action-id]:not([disabled])").first();
    if (!(await choice.count())) return;
    await choice.click({ timeout: budget(10_000) }).catch(() => undefined);
  }
}

/**
 * The deck and seed on which the policy below reaches every combat
 * declaration, and quickly.
 *
 * FOUND BY SEARCH, NOT BY HOPE. The previous gates started `aesi` on seeds 3
 * and 5 and skipped when combat never came -- and on those seeds it never
 * does: the game is over before the first declaration, on every run, so
 * fourteen tests reported "skipped" for eleven days and nobody could tell
 * (TECH_DEBT CG-01). Driving the real lobby and engine offline with this
 * exact policy over seeds 1-12 of both decks: `aesi` reaches attackers on two
 * seeds of twelve; `edgar` reaches attackers, a block with an untapped blocker,
 * and a two-defender attack in a three-player pod on seed 7 within ten of the
 * human's decisions each. If a rules change moves that, the helper below
 * throws rather than skips, which is the whole point of it.
 */
export const COMBAT_SEED = { deck: "edgar", seed: 7 } as const;

/**
 * Play until the engine offers a combat declaration, or fail.
 *
 * Shaped after the combat loops in `smoke.spec.ts` rather than a poll on a
 * predicate: reaching combat means casting creatures and surviving to the step,
 * so the loop has to keep taking whatever action exists. It asks the engine's
 * own question -- is `add_attacker` (or `add_blocker`) legal for us -- rather
 * than three at once: the old helper also wanted the panel visible AND carrying
 * the right `data-combat-kind`, and a race between the decision arriving and
 * the panel drawing it was one more way to come back false.
 *
 * THROWS, NEVER SKIPS. A test that skips is a test that is not run, and a skip
 * on a fixed seed is deterministic, so it is not run on every run. The game
 * ending first is a real outcome, and here it is a failure: it means the seed
 * above no longer does what it was chosen for, and somebody should look.
 *
 * Blocking needs the extra nudge in `prefer`: a creature that attacked is tapped
 * and cannot block, so a loop that happily attacks never reaches a blocker
 * decision with a blocker in it.
 */
export async function reachDeclaration(
  page: Page,
  kind: "attackers" | "blockers",
  limit = 120,
): Promise<void> {
  const wanted = kind === "attackers" ? "add_attacker" : "add_blocker";
  const prefer =
    kind === "attackers"
      ? ["keep", "play_land", "cast", "pass"]
      : ["keep", "play_land", "cast", "finish_declaration", "pass"];

  for (let i = 0; i < limit; i += 1) {
    await waitForOurTurn(page);
    expect(await isOver(page), `the game ended before a ${kind} declaration`).toBe(false);
    if (await actionsOfKind(page, wanted).count()) return;
    await takeAction(page, prefer);
  }
  throw new Error(`never reached a ${kind} declaration in ${limit} decisions`);
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
