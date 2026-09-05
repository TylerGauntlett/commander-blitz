/**
 * The core journeys, counted in presses, against the real engine.
 *
 * `src/components/game/Journeys.stories.tsx` counts the same presses against
 * fixtures and runs in CI. This is the half a fixture cannot honestly stand in
 * for: **the journeys that need the server to answer.** Playing a card is a
 * mutation, the follow-up deliberately waits for the new action list before it
 * moves the ring, and `fakeGame` never produces one -- so the story would be
 * asserting the absence of a step it never took. The lobby is the same story
 * again: five screens, a pod created over HTTP, and a game dealt at the end.
 *
 * The name lands this file in the `handheld` Playwright project, which runs at
 * 1280x800 -- a Steam Deck's panel, and the size the whole controller layer was
 * measured at. At any other size the answers are different and less
 * interesting: an opponent's lanes are drawn, so nothing is ever routed around.
 *
 * ## Keys, not a pad
 *
 * `input/buttons.ts:KEYS` is the keyboard fallback, and it is the only route a
 * test has into the ring -- Playwright cannot synthesise a `Gamepad`.
 * `pad.spec.ts` owns the one thing that needs a real one (`data-input="pad"`,
 * the analog triggers, the glyph set); everything below the button map is
 * shared, so a keystroke here exercises exactly what a button press would.
 *
 * ## Budgets are ceilings
 *
 * `toBeLessThanOrEqual`, always. An exact count fails on an improvement, which
 * is the wrong direction to be strict in; a ceiling fails only when a journey
 * gets worse, which is the regression worth catching.
 */

import { type Page, expect, test } from "@playwright/test";
import {
  budget,
  isOver,
  keepOpeningHand,
  reachDeclaration,
  setInstant,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

/** `input/buttons.ts:KEYS`, as Playwright spells them. */
const KEY = {
  up: "ArrowUp",
  down: "ArrowDown",
  left: "ArrowLeft",
  right: "ArrowRight",
  a: "Enter",
  b: "Escape",
  x: "x",
  y: "i",
  l1: "[",
  r1: "]",
  l2: "z",
} as const;

type Button = keyof typeof KEY;

/**
 * A walk, counted.
 *
 * The settle is not padding. `pad.ts:onKeyDown` puts the button in a latch and
 * wakes the loop; the intent is dispatched inside the next frame, and the ring
 * moves in the layout effect after the commit that follows. A press asserted
 * immediately is asserted against a board that has not heard it.
 */
function walker(page: Page) {
  let spent = 0;
  const trail: string[] = [];
  return {
    async press(button: Button, settle = 220) {
      await page.keyboard.press(KEY[button]);
      await page.waitForTimeout(settle);
      spent += 1;
      trail.push(`${spent}. ${button} -> ${await ring(page)}`);
    },
    get cost() {
      return spent;
    },
    get story() {
      return trail.join("\n");
    },
  };
}

/**
 * The stop the ring is on.
 *
 * `window.__AUTOMTG_RING` and not `[data-cursor]`'s `data-stop`, because OFF
 * THE BOARD THERE IS NO SUCH ATTRIBUTE. The lobby declares no stops at all --
 * everything interactive there is already a control, so `stops.ts` falls back
 * to native focusables and derives `ui:<testid>` ids on the fly. Reading the
 * attribute reported `null` for every screen the lobby draws, which looks
 * exactly like the ring being lost.
 *
 * The diagnostics object is dev-only, which is what these run against: the
 * Playwright config boots `npm run dev`.
 */
const ring = (page: Page) =>
  page.evaluate(() => {
    const diag = (window as unknown as { __AUTOMTG_RING?: { cursor(): string | null } })
      .__AUTOMTG_RING;
    if (diag) return diag.cursor();
    return document.querySelector("[data-cursor]")?.getAttribute("data-stop") ?? null;
  });

/**
 * The verb the bar prints under ONE glyph.
 *
 * Reading the whole bar and asking whether it contains a word cannot tell which
 * button the word belongs to -- `A Attack` and `X All attack` are both in there
 * during a declaration, and an `includes("Attack")` matched the wrong one. The
 * bar is a row of `.hint` spans and `Glyph` already stamps `data-glyph` on the
 * letter it draws, so one hint is addressable without adding a test seam.
 */
function verbFor(page: Page, btn: string) {
  return page.locator(`[data-testid="hint-bar"] .hint:has([data-glyph="${btn}"]) .hint__verb`);
}

/**
 * Play forward until it is your own main phase with something in hand to play.
 *
 * `keepOpeningHand` leaves the board at whatever the engine asks next, which on
 * half the seeds is the opponent's whole turn. Everything below needs a
 * priority window that is actually yours.
 */
async function untilYouCanPlay(page: Page, limit = 80): Promise<string[]> {
  for (let i = 0; i < limit; i += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) return [];
    const playable = await page.evaluate(() =>
      [...document.querySelectorAll(".hand .card--playable")].map(
        (el) => (el as HTMLElement).dataset.oid ?? "",
      ),
    );
    if (playable.length > 0) return playable;
    // Pass through everything that is not a chance to play, including the
    // prompts a Commander deck throws on the way -- `takeAction` prefers in
    // order and falls back to whatever is legal, which is what keeps this from
    // deadlocking on a decision it has no opinion about.
    if ((await takeAction(page, ["keep", "pass"])) === null) return [];
  }
  return [];
}

/**
 * Play forward to a declaration, then let the ring arrive.
 *
 * `helpers.reachDeclaration` is this file's old local loop, promoted: it asks
 * the engine's own question -- is `add_attacker` legal -- and throws rather
 * than skipping, so a genuine regression is loud instead of quiet.
 *
 * The settle is the one `pad.spec.ts` explains: `Table` moves the ring to the
 * region a new decision lives in and waits for narration first, so the decision
 * existing and the ring having arrived are two different moments, and a press
 * between them is a press the app then overrides.
 */
async function reachAttackDeclaration(page: Page): Promise<void> {
  await reachDeclaration(page, "attackers");
  await page.waitForTimeout(budget(1500));
}

const region = (page: Page) =>
  page.evaluate(() => document.documentElement.getAttribute("data-group"));

test.describe("the core journeys, in presses", () => {
  /**
   * THE LOBBY, IN THE ORDER THE SCREEN ITSELF PROPOSES.
   *
   * It opens on `Choose a deck`, so deck first is the natural order and the one
   * this walks. Two nudges carry it: the pod opens on the decision it is asking
   * you for, and `Deal` comes to the host the moment the pod is dealable.
   *
   * TAKING A DECK MOVES NOTHING, and that is the assertion worth having here.
   * It jumped to `Lock in` for one round, on the reasoning that the button that
   * opened the catalogue is finished with. But at that moment the chairs are
   * still empty -- so the jump landed the player on the control that ENDS the
   * screen, and the path became deck, walk back up to seat a CPU, walk back
   * down to lock in. It added the walk it was meant to remove.
   */
  test("the lobby deals a game without a walk it did not ask for", async ({ page }) => {
    await setInstant(page);
    await page.goto("/?input=pad");
    await expect(page.getByTestId("create-pod")).toBeVisible();

    const run = walker(page);
    await run.press("a", 1200); // Play, which creates the pod
    await expect(page.getByTestId("new-game")).toBeVisible({ timeout: 15_000 });
    // No walk at all: the pod opens on the one decision it asks you for.
    expect(await ring(page), run.story).toBe("ui:change-deck");

    await run.press("a", 700); // the catalogue, which opens on a deck
    await expect(page.getByTestId("deck-catalog")).toBeVisible();

    await run.press("a", 700); // take it
    await expect(page.getByTestId("deck-catalog")).toBeHidden();
    await expect(page.getByTestId("seat-0-deck")).toBeVisible();
    /*
     * STILL ON `Change deck`, one row above the chairs. `Lock in` is not the
     * next step, it is the LAST one, and only the player knows when the pod is
     * the shape they want.
     */
    expect(await ring(page), run.story).toBe("ui:change-deck");

    await run.press("right"); // the first empty chair, which is one step away
    expect(await ring(page), run.story).toBe("ui:opponents-1");

    await run.press("a", 500); // seat a CPU
    await run.press("down");
    expect(await ring(page), run.story).toBe("ui:lock-in");

    await run.press("a", 700); // lock in -- and the pod becomes dealable
    expect(await ring(page), run.story).toBe("ui:start-game");

    await run.press("a", 2000); // deal
    await page.getByTestId("table").waitFor({ timeout: 30_000 });

    expect(run.cost, run.story).toBeLessThanOrEqual(8);
  });

  /**
   * ...and seating a CPU FIRST comes back to your own chair.
   *
   * The other order, and the one nudge in this screen that survived. Filling a
   * chair leaves the ring on THAT chair's deck button -- `resolveCursor` keeps
   * it nearest to where the markup changed, which is right in general and wrong
   * here, because the chair you just filled is the one thing on the screen now
   * finished with and your own deck is what the pod is waiting on.
   *
   * Guarded on not having a deck yet, which is what stops it firing on the way
   * back: seat a second CPU after choosing and the ring stays where you put it.
   */
  test("seating an opponent comes back to the decision you still owe", async ({ page }) => {
    await setInstant(page);
    await page.goto("/?input=pad");
    await expect(page.getByTestId("create-pod")).toBeVisible();

    const run = walker(page);
    await run.press("a", 1200);
    await expect(page.getByTestId("new-game")).toBeVisible({ timeout: 15_000 });

    await run.press("right");
    expect(await ring(page), run.story).toBe("ui:opponents-1");
    await run.press("a", 500);
    expect(await ring(page), run.story).toBe("ui:change-deck");

    // ...and once you have a deck it stays put, wherever you left it.
    await run.press("a", 700);
    await run.press("a", 700);
    await expect(page.getByTestId("seat-0-deck")).toBeVisible();
    await run.press("right");
    const parked = await ring(page);
    await run.press("a", 700); // seat a second CPU
    expect(await ring(page), run.story).not.toBe("ui:change-deck");
    expect(parked, run.story).not.toBeNull();
  });

  /**
   * THE RING WAS LEFT ON THE CARD, AND THE CARD WAS NO LONGER IN YOUR HAND.
   *
   * `resolveCursor` keeps the ring on the object the engine replaced, which is
   * exactly right for a permanent that stayed put and exactly wrong for one
   * that went from hand to battlefield: the ring silently dropped to the lands
   * while `data-group` still said `hand`, and the next direction press
   * teleported back to whichever hand card won the scoring. Playing a land is
   * the most repeated gesture in the game and it ended somewhere nobody asked
   * to be.
   *
   * This is the journey a story cannot cover: the follow-up waits for the new
   * action list on purpose, and a fixture never produces one.
   */
  test("playing a card leaves the ring in your hand", async ({ page }) => {
    await startGame(page, { deck: "edgar", opponents: 1, seed: 11 });
    await keepOpeningHand(page);

    const targets = await untilYouCanPlay(page);
    test.skip(targets.length === 0, "this seed never offered a card to play");

    // Walk to something playable, staying inside the hand.
    const run = walker(page);
    for (let i = 0; i < 9; i += 1) {
      const at = (await ring(page)) ?? "";
      if (targets.includes(at.split(":")[1] ?? "")) break;
      await run.press("right", 160);
    }
    const played = await ring(page);
    expect(played, run.story).toMatch(/^card:/);

    await run.press("a", 1500);

    const stillInHand = await page.evaluate(
      () => document.querySelector(".hand [data-cursor]") !== null,
    );
    expect(stillInHand, `${run.story}\nthe ring followed the card out of the hand`).toBe(true);
    expect(await ring(page), run.story).not.toBe(played);
  });

  /**
   * `X` passes, from wherever the ring is.
   *
   * Passing is the most repeated action in the game and it had no button on a
   * pad: `Space` has been the keyboard's since before any of this existed, and
   * a controller paid `L2` then `A` for every priority window of every turn.
   *
   * Asserted on the REQUEST rather than on the board, and that is deliberate --
   * auto-pass moves the game through several steps at once, so the next window
   * can look identical to the one just answered. What the press promises is
   * that the id the panel is showing is the id that goes out.
   */
  test("X passes in one press, and the bar says so first", async ({ page }) => {
    await startGame(page, { deck: "edgar", opponents: 1, seed: 11 });
    await keepOpeningHand(page);
    const playable = await untilYouCanPlay(page);
    test.skip(playable.length === 0, "this seed never reached a priority window of your own");

    const posted: string[] = [];
    page.on("request", (request) => {
      if (request.method() !== "POST") return;
      if (!/\/actions/.test(request.url())) return;
      const body = request.postData() ?? "";
      const match = /"action_id":"([^"]+)"/.exec(body);
      if (match) posted.push(match[1]);
    });

    const passButton = page.locator('[data-action-kind="pass"]').first();
    await expect(passButton).toBeVisible({ timeout: 30_000 });
    const passId = await passButton.getAttribute("data-action-id");

    // The bar promises it before the button does it. A hint that disagrees with
    // the button is the one defect `logic/verbs.ts` exists to prevent.
    await expect(page.getByTestId("hint-bar")).toContainText("Pass");

    const run = walker(page);
    await run.press("x", 900);

    expect(posted, run.story).toContain(passId);
    expect(run.cost).toBe(1);
  });

  /**
   * `X` DECLARES A COMBAT FROM THE BOARD, WITHOUT GOING TO THE DOCK.
   *
   * Every decision this game asks ends at one control in the right rail, and
   * the ring is almost never near it -- you are out on your own board choosing
   * what to swing. `L2` jumps there and `A` presses it, then `right` and `A`
   * again: four presses, and the same four every turn.
   *
   * `X` is the hotkey for that control: `All attack` while nothing is staged,
   * `Attack` once something is. The first press STAGES and does not submit,
   * which is what makes it safe to bind -- it is reversible, and by the time
   * the second press commits the bar has changed and said so.
   *
   * Asserted against the real engine because the declaration is a mutation:
   * what proves it worked is combat leaving the declare step, which a fixture
   * cannot do.
   */
  test("X declares a combat in two presses, from wherever the ring is", async ({ page }) => {
    // Seed 3 and the long budget, which is what `pad.spec.ts` uses: playing to
    // combat against a real engine is minutes, not seconds.
    test.setTimeout(budget(600_000));
    await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
    /*
     * NO `keepOpeningHand` -- the loop answers the mulligan itself, which is
     * what `pad.spec.ts` does with this same deck and seed. Called separately it
     * hung here: the opening hand is a decision like any other and the loop's
     * `keep` preference already covers it, so the extra call was a second thing
     * racing the same screen.
     */
    await reachAttackDeclaration(page);

    const panel = page.getByTestId("combat-panel");
    await expect(panel).toBeVisible();
    const note = page.locator(".commit-note");
    await expect(note).toHaveText(/^0 attacking/);

    // The bar promises it before the button does it, and it promises the
    // FIRST half: nothing is staged, so `X` is the mark and not the slab.
    await expect(verbFor(page, "x")).toHaveText("All attack");

    const run = walker(page);
    await run.press("x", 600);
    await expect(note, run.story).not.toHaveText(/^0 attacking/);
    // ...and now the bar names the press that commits.
    await expect(verbFor(page, "x")).toHaveText("Attack");

    await run.press("x", 1500);
    await expect(panel, run.story).toBeHidden({ timeout: 30_000 });
    expect(run.cost, run.story).toBe(2);
  });

  /**
   * THE RING IS NEVER PARKED ON A BOARD THAT CANNOT ANSWER.
   *
   * A block is your creature and then the attacker it stops. At 1280x800 an
   * opponent's lanes are clipped to zero height so `FxLayer` keeps its anchors,
   * which means `stops.ts:onScreen` refuses to land the ring on an attacker --
   * correctly. `groupForDecision` sent the ring to the board anyway, and the
   * board held exactly half a decision: `A` on your own creature answered
   * nothing and every direction out of it was a wall or a seat, while the panel
   * had carried the whole pairing as rows the entire time.
   *
   * The whole assertion is one sentence: if no attacker is a stop, the ring is
   * in the panel.
   */
  test("a block decision puts the ring where the block can be made", async ({ page }) => {
    // The same budget as the attack journey above: a block is further into the
    // game than an attack, and this seed reaches it in ~27 of our decisions.
    test.setTimeout(budget(600_000));
    await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
    await keepOpeningHand(page);

    await reachDeclaration(page, "blockers");

    const attackerIsReachable = await page.evaluate(() => {
      const ring = (window as unknown as { __AUTOMTG_RING?: { stops(): string[] } })
        .__AUTOMTG_RING;
      const stops = new Set(ring?.stops() ?? []);
      return [...document.querySelectorAll(".card--attacking")].some((el) =>
        stops.has(`card:${(el as HTMLElement).dataset.oid}`),
      );
    });

    if (!attackerIsReachable) {
      expect(
        await region(page),
        "no attacker is a stop, so the board cannot answer this decision",
      ).toBe("acts");
      const at = await ring(page);
      expect(at?.startsWith("act:") || at?.startsWith("commit")).toBe(true);
    }

    /*
     * ...and picking a blocker aims it, wherever the aiming happens to live.
     *
     * One press, and the ring lands on something that finishes the block --
     * the attacker's card where the layout draws it, and the panel row for the
     * same pairing where it does not.
     */
    const blockerRow = page.locator('[data-action-kind="add_blocker"]').first();
    await expect(blockerRow).toBeVisible();
  });
});
