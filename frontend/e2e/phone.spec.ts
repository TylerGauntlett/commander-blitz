/**
 * The phone gate, against the real engine (ADR 0025).
 *
 * Runs in the `phone` Playwright project, once per phone `testing/devices.ts`
 * names, upright and sideways, as a touch device: `hasTouch`, `isMobile`, the
 * device's viewport and scale. Every gesture is a TAP (`locator.tap()`), so the
 * page is in `data-input="touch"` throughout, exactly as a phone puts it.
 *
 * What it holds, on every device:
 *
 * - the floors of `logic/floors.ts`'s phone row and the phone's region budgets,
 *   through the same `handheldAssert` the Deck's gate runs (`PHONE_GATE`), and
 *   the legibility spec's scrim and frame checks (`legibilityAssert.ts`);
 * - no horizontal scroll, on any screen;
 * - every stop reachable by tap: each one on screen, or scrolled to, is the
 *   element a finger at its centre lands on;
 * - every decision answerable from the sheet: whatever the engine asks, every
 *   enabled control for it is in the sheet or in the surface that owns it;
 * - the journeys the audit's touch column names, held to its ceilings
 *   (`decisionAudit.ts:TAP_BUDGET`), and one whole game played by tap.
 *
 * Chromium for every descriptor, iPhones included: it is the one browser CI
 * installs, and what this gates is the layout and the gestures, not WebKit.
 */

import { expect, type Page, test } from "@playwright/test";
import { tapCeiling } from "../src/components/game/decisionAudit";
import { type Device, type Orientation, PHONES } from "../src/testing/devices";
import { type HandheldReport, handheldAssert, PHONE_GATE } from "./handheldAssert";
import { budget, COMBAT_SEED, isOver, pinSeed, setInstant, waitForOurTurn } from "./helpers";
import { frameWidths, MIN_FRAME, MIN_SCRIM, scrimFailures } from "./legibilityAssert";

/** A phone held one way, as Playwright context options. */
function heldAs(device: Device, orientation: Orientation) {
  return {
    viewport: device[orientation],
    screen: device.screen,
    deviceScaleFactor: device.deviceScaleFactor,
    userAgent: device.userAgent,
    isMobile: true,
    hasTouch: true,
  };
}

/** Wait until nothing finite is still moving; `handheld.spec.ts` says why. */
async function settled(page: Page): Promise<void> {
  await page.waitForFunction(
    () =>
      document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getTiming().iterations ?? 1))
        .every((a) => a.playState !== "running"),
    undefined,
    { timeout: 5_000 },
  );
}

/** The phone gate, every check of it, on whatever screen is up. */
async function gate(page: Page, where: string): Promise<HandheldReport> {
  await settled(page).catch(() => undefined);
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-layout"))).toBe(
    "phone",
  );
  const report = (await page.evaluate(handheldAssert, PHONE_GATE)) as HandheldReport;
  expect(
    report.pass,
    `${where}\n  ${report.failures.join("\n  ")}\n  (min font ${report.minFontPx}px, ` +
      `min card ${report.minCardPx}px)`,
  ).toBe(true);
  const side = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    width: window.innerWidth,
  }));
  expect(side.scroll, `${where}: the page scrolls sideways`).toBeLessThanOrEqual(side.width);
  return report;
}

/**
 * Stops a finger cannot land on.
 *
 * For each visible `[data-stop]`, scrolled into view inside its own scroller,
 * some point of it must be the element a finger there lands on. A stop wholly
 * covered by another surface, or clipped where no scroll reaches it, is
 * reported.
 * Self-contained, because `page.evaluate` sends this function alone.
 */
function untappable(): string[] {
  const out: string[] = [];
  const modal = document.querySelector("[data-modal-root]:not([data-closing])");
  const scope = modal ?? document;
  for (const el of scope.querySelectorAll<HTMLElement>("[data-stop]")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (el.closest("[aria-hidden='true'], [inert]")) continue;
    // A clipped opponent's lane (`[data-compact] .mat--compact .mat__lanes`) is
    // not a place a stop is meant to be reached; its board opens on a tap.
    if (el.closest(".mat--compact .mat__lanes")) continue;
    let box = el.getBoundingClientRect();
    if (box.width <= 0 || box.height <= 0) continue;
    el.scrollIntoView({ block: "nearest", inline: "nearest" });
    box = el.getBoundingClientRect();
    /*
     * ANY point of it, not its centre. A fan overlaps its cards on purpose --
     * each shows a strip of itself beside the next -- so a hand card's centre
     * is under its neighbour and its strip is where a finger lands on it. A grid
     * of points across the box asks whether any of it takes a tap.
     */
    let reached = false;
    for (let i = 1; i <= 7 && !reached; i += 1) {
      for (let j = 1; j <= 5 && !reached; j += 1) {
        const x = box.left + (box.width * i) / 8;
        const y = box.top + (box.height * j) / 6;
        if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) continue;
        const hit = document.elementFromPoint(x, y);
        reached =
          !!hit && (el === hit || el.contains(hit) || hit.closest("[data-stop]") === el);
      }
    }
    if (!reached) out.push(el.getAttribute("data-stop") ?? "?");
  }
  return out;
}

/** Every enabled decision control is in the sheet or in the surface that owns it. */
function offSheet(): string[] {
  const out: string[] = [];
  for (const el of document.querySelectorAll<HTMLElement>("[data-action-id]:not([disabled])")) {
    if (el.closest(".rail--right") || el.closest("[data-modal-root]")) continue;
    out.push(el.getAttribute("data-action-id") ?? "?");
  }
  return out;
}

/** The legibility spec's two questions, asked at this phone's size. */
async function legible(page: Page, where: string): Promise<void> {
  const scrims = await page.evaluate(scrimFailures, MIN_SCRIM);
  expect(scrims, `${where}: card text on too little scrim`).toEqual([]);
  for (const width of await page.evaluate(frameWidths, ".face")) {
    expect(width, `${where}: a card frame is thinner than a line`).toBeGreaterThanOrEqual(
      MIN_FRAME,
    );
  }
}

/** A count of taps, so a journey can be held to its ceiling. */
function tapper(page: Page) {
  let spent = 0;
  return {
    async tap(selector: string) {
      const target = page.locator(selector).first();
      await target.scrollIntoViewIfNeeded();
      await target.tap();
      spent += 1;
    },
    get cost() {
      return spent;
    },
  };
}

/** The lobby, by finger: Play, a deck, a CPU per opponent, lock in, deal. */
async function dealByTap(page: Page, opponents: number, deck: string, seed?: number) {
  await setInstant(page);
  if (seed !== undefined) await pinSeed(page, seed);
  await page.goto("/");
  const run = tapper(page);
  await run.tap('[data-testid="create-pod"]');
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
  await run.tap('[data-testid="change-deck"]');
  await page.getByTestId("deck-catalog").waitFor();
  await run.tap(`[data-testid="deck-${deck}-take"]`);
  await expect(page.getByTestId("deck-catalog")).toBeHidden();
  for (let i = 1; i <= opponents; i += 1) await run.tap(`[data-testid="opponents-${i}"]`);
  await run.tap('[data-testid="lock-in"]');
  await run.tap('[data-testid="start-game"]');
  await page.getByTestId("table").waitFor({ timeout: 30_000 });
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-input"))).toBe(
    "touch",
  );
  return run.cost;
}

/** Tap one legal action, preferring kinds in order; check the sheet holds them all first. */
async function tapAction(page: Page, prefer: string[]): Promise<string | null> {
  await waitForOurTurn(page);
  if (await isOver(page)) return null;
  const stray = await page.evaluate(offSheet);
  expect(stray, "a decision control outside the sheet and its surfaces").toEqual([]);
  const enabled = "[data-action-id]:not([disabled])";
  for (const kind of [...prefer, null]) {
    const selector = kind ? `[data-action-kind="${kind}"]:not([disabled])` : enabled;
    const candidate = page.locator(selector).first();
    if (!(await candidate.count())) continue;
    const id = await candidate.getAttribute("data-action-id").catch(() => null);
    await candidate.scrollIntoViewIfNeeded({ timeout: budget(5_000) }).catch(() => undefined);
    await candidate.tap({ timeout: budget(10_000) }).catch(() => undefined);
    return id;
  }
  return null;
}

for (const device of PHONES) {
  test.describe(`${device.name}, upright`, () => {
    test.use(heldAs(device, "portrait"));

    test("the front door, the lobby and the catalogue hold the phone's floors", async ({
      page,
    }) => {
      await setInstant(page);
      await page.goto("/");
      await page.getByTestId("home").waitFor();
      await gate(page, "the front door");
      await page.getByTestId("create-pod").tap();
      await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
      await gate(page, "the pod lobby");
      await page.getByTestId("change-deck").tap();
      await page.getByTestId("deck-catalog").waitFor();
      await gate(page, "the deck catalogue");
    });

    test("the lobby deals a game in six taps, and the opening hand keeps in one", async ({
      page,
    }) => {
      const taps = await dealByTap(page, 1, "edgar", 11);
      expect(taps).toBeLessThanOrEqual(6);

      const stage = page.getByTestId("opening-hand");
      await expect(stage).toHaveAttribute("data-phase", "keep");
      await gate(page, "the opening hand");
      const run = tapper(page);
      await run.tap('[data-action-kind="keep"]:not([disabled])');
      await expect
        .poll(
          () =>
            page.evaluate(() => {
              const root = document.querySelector<HTMLElement>('[data-testid="opening-hand"]');
              return (
                !root || root.dataset.closing !== undefined || root.dataset.phase !== "keep"
              );
            }),
          { timeout: budget(15_000) },
        )
        .toBe(true);
      expect(run.cost).toBeLessThanOrEqual(tapCeiling("KeepTheHand"));
    });

    test("a dealt pod: floors, stops by tap, and Pass in one tap", async ({ page }) => {
      test.setTimeout(budget(300_000));
      await dealByTap(page, 3, "aesi", 5);
      await tapAction(page, ["keep"]);
      await waitForOurTurn(page);
      await gate(page, "a four-seat pod, upright");
      await legible(page, "a four-seat pod, upright");
      expect(await page.evaluate(untappable), "stops a finger cannot land on").toEqual([]);

      // An orb opens that seat's board, and the strip brings you home.
      await page.getByTestId("player-1").tap();
      await expect(page.getByTestId("viewing-strip")).toBeVisible();
      await gate(page, "standing at an opponent's board");
      await page.locator('[data-stop="tool:stop-viewing"]').tap();
      await expect(page.getByTestId("viewing-strip")).toBeHidden();

      // A long press reads a card, full screen.
      const card = page.locator(".hand .card").first();
      await card.scrollIntoViewIfNeeded();
      const box = await card.boundingBox();
      if (box) {
        const cdp = await page.context().newCDPSession(page);
        const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
        await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [at] });
        await page.waitForTimeout(700);
        await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
        await expect(page.getByTestId("card-hold")).toBeVisible();
        await gate(page, "the full card view");
        await page.keyboard.press("Escape");
        await expect(page.getByTestId("card-hold")).toBeHidden();
      }

      // Pass, from the sheet, in one tap.
      await waitForOurTurn(page);
      const pass = page.locator('[data-action-kind="pass"]:not([disabled])').first();
      if (await pass.count()) {
        const posted: string[] = [];
        page.on("request", (request) => {
          if (request.method() !== "POST" || !/\/actions/.test(request.url())) return;
          const match = /"action_id":"([^"]+)"/.exec(request.postData() ?? "");
          if (match) posted.push(match[1]);
        });
        const id = await pass.getAttribute("data-action-id");
        const run = tapper(page);
        await run.tap('[data-action-kind="pass"]:not([disabled])');
        await expect.poll(() => posted, { timeout: budget(10_000) }).toContain(id);
        expect(run.cost).toBeLessThanOrEqual(tapCeiling("PassInOnePress"));
      }
    });

    test("a combat is declared from the sheet in two taps", async ({ page }) => {
      test.setTimeout(budget(600_000));
      await dealByTap(page, 1, COMBAT_SEED.deck, COMBAT_SEED.seed);
      for (let i = 0; i < 120; i += 1) {
        await waitForOurTurn(page);
        expect(await isOver(page), "the game ended before a declaration").toBe(false);
        if (await page.locator('[data-action-kind="add_attacker"]:not([disabled])').count()) {
          break;
        }
        await tapAction(page, ["keep", "play_land", "cast", "pass"]);
      }
      const panel = page.getByTestId("combat-panel");
      await expect(panel).toBeVisible();
      await gate(page, "the attack declaration");
      expect(await page.evaluate(offSheet)).toEqual([]);

      const note = page.locator(".commit-note");
      await expect(note).toHaveText(/^0 attacking/);
      const run = tapper(page);
      await run.tap('[data-testid="combat-all"]:not([disabled])');
      await expect(note).not.toHaveText(/^0 attacking/);
      await run.tap('[data-testid="combat-confirm"]:not([disabled])');
      await expect(panel).toBeHidden({ timeout: budget(30_000) });
      expect(run.cost).toBeLessThanOrEqual(tapCeiling("CommitFromAnywhere"));
    });

    test("one whole game, to a result, by tap", async ({ page }) => {
      test.slow();
      test.setTimeout(budget(900_000));
      await dealByTap(page, 1, "aesi", 11);
      let steps = 0;
      for (; steps < 3000; steps += 1) {
        await waitForOurTurn(page);
        if (await isOver(page)) break;
        await tapAction(page, ["keep", "play_land", "cast", "add_attacker", "pass"]);
      }
      expect(await isOver(page), `the game never finished in ${steps} decisions`).toBe(true);
      await expect(page.getByTestId("game-over")).toBeVisible();
      await gate(page, "the game over screen");
    });
  });

  test.describe(`${device.name}, sideways`, () => {
    test.use(heldAs(device, "landscape"));

    test("a dealt pod holds the phone's floors held sideways", async ({ page }) => {
      test.setTimeout(budget(300_000));
      await dealByTap(page, 3, "aesi", 5);
      await tapAction(page, ["keep"]);
      await waitForOurTurn(page);
      await gate(page, "a four-seat pod, sideways");
      await legible(page, "a four-seat pod, sideways");
      expect(await page.evaluate(untappable), "stops a finger cannot land on").toEqual([]);
      expect(await page.evaluate(offSheet)).toEqual([]);
    });
  });
}
