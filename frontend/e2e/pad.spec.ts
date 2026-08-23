/**
 * A controller, synthesised.
 *
 * Playwright cannot produce a real gamepad, and the Gamepad API has no test
 * seam — so `navigator.getGamepads` is overridden before any script runs and a
 * `gamepadconnected` event is dispatched. That is enough to exercise everything
 * that matters, because `input/pad.ts` polls: it re-reads `getGamepads()` every
 * frame by design, which is exactly what makes it drivable from a fake.
 *
 * This is the only suite that covers the pad path at all. The keyboard fallback
 * shares the code below the button map, so `handheld.spec.ts` reaches the ring,
 * the trap and the repeat ramp — but not `data-input="pad"`, not the analog
 * triggers, and not the glyph set a controller player actually sees.
 *
 * ## The gap this suite had, and why it mattered
 *
 * `withFakePad` installs the pad in `addInitScript`, so `getGamepads()` returns
 * a live controller on the very first frame the app ever polls. A real one does
 * not: Chrome reports four nulls until the pad's first gesture, which can be
 * long after the app has booted. Every test below passed against a loop that
 * ran exactly one frame, saw nothing, and stopped forever — which is what a
 * real Xbox controller met. "the pad appears after the app has booted" covers
 * that path now, and it is deliberately the only test here that does not use
 * `withFakePad`.
 */

import { type Page, expect, test } from "@playwright/test";
import { actionsOfKind, startGame, waitForOurTurn } from "./helpers";

/**
 * Install a fake pad before the app boots.
 *
 * The button array is mutable and reachable as `window.__PAD`, so a test presses
 * a button by writing to it and the polling loop notices on its next frame —
 * the same way a real one works.
 */
async function withFakePad(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const pad = {
      id: "Fake Deck Controller (STANDARD GAMEPAD)",
      index: 0,
      connected: true,
      mapping: "standard",
      timestamp: 0,
      axes: [0, 0, 0, 0],
      buttons: Array.from({ length: 17 }, () => ({
        pressed: false,
        touched: false,
        value: 0,
      })),
    };
    (window as unknown as Record<string, unknown>).__PAD = pad;
    navigator.getGamepads = () => [pad as unknown as Gamepad, null, null, null];
    window.dispatchEvent(new Event("gamepadconnected"));
  });
}

/** Press and release one button by index, giving the loop frames to see both. */
async function press(page: Page, index: number): Promise<void> {
  await page.evaluate((i) => {
    const pad = (
      window as unknown as { __PAD: { buttons: { pressed: boolean; value: number }[] } }
    ).__PAD;
    pad.buttons[i].pressed = true;
    pad.buttons[i].value = 1;
  }, index);
  await page.waitForTimeout(90);
  await page.evaluate((i) => {
    const pad = (
      window as unknown as { __PAD: { buttons: { pressed: boolean; value: number }[] } }
    ).__PAD;
    pad.buttons[i].pressed = false;
    pad.buttons[i].value = 0;
  }, index);
  await page.waitForTimeout(90);
}

/** W3C Standard Gamepad indices, the ones this suite uses. */
const BTN = { a: 0, b: 1, l1: 4, r1: 5, down: 13, right: 15 } as const;

const cursor = (page: Page) =>
  page.evaluate(
    () => document.querySelector("[data-cursor]")?.getAttribute("data-stop") ?? null,
  );

test.describe("a gamepad drives the board", () => {
  test.beforeEach(async ({ page }) => {
    await withFakePad(page);
  });

  test("a pad press switches the input mode, and a mouse move switches it back", async ({
    page,
  }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    /*
     * Connection is not usage. `startGame` drives by clicking, so the mode is
     * `mouse` even though a pad has been present since before the first paint --
     * which is the whole point of last-input-wins: a Deck in desktop mode has
     * both attached at once.
     */
    await expect(page.locator("html")).toHaveAttribute("data-pad", "");
    await expect(page.locator("html")).toHaveAttribute("data-input", "mouse");

    await press(page, BTN.down);
    await expect(page.locator("html")).toHaveAttribute("data-input", "pad");

    await page.mouse.move(400, 400);
    await page.mouse.down();
    await page.mouse.up();
    await expect(page.locator("html")).toHaveAttribute("data-input", "mouse");
  });

  test("glyphs appear for a pad and never for a mouse", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    const barHeight = async () =>
      (await page.getByTestId("hint-bar").boundingBox())?.height ?? 0;

    // Asserted by height, not by class: the requirement is that the hints cost a
    // mouse player nothing, and a transparent glyph would still take a row.
    expect(await barHeight(), "the hint bar takes space for a mouse player").toBe(0);

    await press(page, BTN.down);
    expect(await barHeight(), "the hint bar is missing for a pad player").toBeGreaterThan(0);

    const shown = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>(".glyph")]
        .filter((el) => getComputedStyle(el).display !== "none")
        .map((el) => el.className),
    );
    expect(shown.length).toBeGreaterThan(0);
    expect(
      shown.every((c) => c.includes("glyph--pad")),
      "a pad player is being shown keyboard labels",
    ).toBe(true);
  });

  test("the d-pad walks the ring and A presses what it is on", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    // The mulligan owns the ring before anything else does.
    await expect(page.getByTestId("prompt-dialog")).toBeVisible();
    await press(page, BTN.down);
    const start = await cursor(page);
    expect(start, "the ring should start inside the open dialog").toMatch(/^act:/);

    await press(page, BTN.right);
    const moved = await cursor(page);
    expect(moved).toMatch(/^act:/);

    /*
     * Six presses in every direction never leave. The board behind the dialog
     * is full of stops and comes first in the markup, so a resolver without a
     * trap would have walked straight out onto it.
     */
    for (const btn of [BTN.down, BTN.right, BTN.down, BTN.right]) await press(page, btn);
    expect(await cursor(page), "the ring escaped the modal").toMatch(/^act:/);

    // And `A` answers it, which is the whole loop: navigate, press, continue.
    await press(page, BTN.a);
    await expect(page.getByTestId("prompt-dialog")).toBeHidden();
    await waitForOurTurn(page);

    // The ring re-derives onto the board rather than going out with the dialog.
    expect(await cursor(page), "the ring did not survive the dialog closing").not.toBeNull();
  });

  test("holding a direction sweeps rather than stepping once", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    /*
     * INTO THE HAND FIRST, and this is the half the test used to leave to luck.
     *
     * `L1`/`R1` step between the board's regions and trap the ring inside the
     * one it is in (`input/groups.ts`), so a direction held in a one-wide
     * column legitimately walks one stop and stops -- which is the trap working
     * and looks exactly like autorepeat being broken. The hand is a row of
     * cards laid left to right, so it is where holding RIGHT has somewhere to
     * go, and naming it is what makes this test about the ramp again.
     */
    for (let i = 0; i < 6; i += 1) {
      const at = await page.evaluate(() => document.documentElement.getAttribute("data-group"));
      if (at === "hand") break;
      await press(page, BTN.r1);
    }
    expect(
      await page.evaluate(() => document.documentElement.getAttribute("data-group")),
      "could not reach the hand to sweep it",
    ).toBe("hand");

    await press(page, BTN.right);

    /*
     * Hold, rather than tap. The first repeat is due after ~360ms at a digital
     * press and then every ~110ms, so a second of holding should visit several
     * stops -- which is the analog ramp doing its job. A fixed-rate d-pad would
     * also pass this; what it is really guarding is that autorepeat happens at
     * all, since without it crossing a board is one press per card.
     */
    const seen = await page.evaluate(async () => {
      const pad = (
        window as unknown as {
          __PAD: { buttons: { pressed: boolean; value: number }[] };
        }
      ).__PAD;
      const visited = new Set<string>();
      pad.buttons[15].pressed = true;
      pad.buttons[15].value = 1;
      const started = performance.now();
      while (performance.now() - started < 1200) {
        const at = document.querySelector("[data-cursor]")?.getAttribute("data-stop");
        if (at) visited.add(at);
        await new Promise((r) => setTimeout(r, 30));
      }
      pad.buttons[15].pressed = false;
      pad.buttons[15].value = 0;
      return [...visited];
    });

    expect(seen.length, "holding a direction did not autorepeat").toBeGreaterThan(2);
  });

  test("exactly one cursor exists, whatever is pressed", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    const count = () => page.locator("[data-cursor]").count();
    for (const btn of [BTN.down, BTN.right, BTN.down, BTN.b, BTN.right, BTN.b]) {
      await press(page, btn);
      expect(await count(), "more than one element wore the ring").toBeLessThanOrEqual(1);
    }
  });
});

/**
 * The pad shows up late, which is what a real one always does.
 *
 * Chrome hides gamepads until the player presses something, so `getGamepads()`
 * is four nulls while the app boots and the loop's first frame sees nothing.
 * The loop used to stop itself at that point and rely on `gamepadconnected` to
 * restart it -- one event, dispatched once, and if it landed before `Screen`
 * mounted its listener (a reload, an HMR pass, a slow first paint) the
 * controller was never seen again for the life of the page.
 *
 * No fake pad is installed up front here and NO EVENT IS DISPATCHED, on purpose.
 * The only thing that can make this pass is a loop that is still polling.
 *
 * ## Why this one runs at 1600x950
 *
 * It has to, or it proves nothing -- and the first version of it did not, which
 * is worth recording because it passed against the exact bug it was written
 * for. The old loop kept running while `frameHandlers` was non-empty, and
 * `Table.tsx` registers one for the R2 board-peek **only when the layout is
 * handheld**. At 1280x800 that subscriber exists from the moment the board
 * mounts, so the loop never idled and a late pad was seen either way.
 *
 * A desktop viewport is the honest reproduction: no frame subscriber, nothing
 * holding the loop open, and a pad arriving after boot with no event. It is
 * also the first case a real player meets, because the lobby has no board on it
 * at any size.
 */
test.describe("a controller plugged in later", () => {
  test.use({ viewport: { width: 1600, height: 950 } });

  test("is still noticed once the app has been running", async ({ page }) => {
    await startGame(page, { opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    // Nothing is plugged in, and the app has been running for a while.
    expect(await page.evaluate(() => navigator.getGamepads().filter(Boolean).length)).toBe(0);

    // Now one arrives -- silently, the way Chrome actually reveals it.
    await page.evaluate(() => {
      const pad = {
        id: "Late Arrival (STANDARD GAMEPAD)",
        index: 0,
        connected: true,
        mapping: "standard",
        timestamp: 0,
        axes: [0, 0, 0, 0],
        buttons: Array.from({ length: 17 }, () => ({
          pressed: false,
          touched: false,
          value: 0,
        })),
      };
      (window as unknown as Record<string, unknown>).__PAD = pad;
      navigator.getGamepads = () => [pad as unknown as Gamepad, null, null, null];
    });

    // The idle tick is ~100ms; give it several before believing it is dead.
    await expect
      .poll(() => page.evaluate(() => document.documentElement.hasAttribute("data-pad")), {
        timeout: 4_000,
      })
      .toBe(true);

    /*
     * And it DRIVES, which is a stronger claim than being detected.
     *
     * `data-input` only becomes "pad" from inside `fire()`, which only runs when
     * the poll sees a button go from up to down. So this asserts the whole chain
     * -- loop alive, pad readable, edge detected, intent dispatched -- rather
     * than merely that something noticed a device.
     *
     * A direction and not `A`, because `A` is literally a click on whatever the
     * ring is on and this test has no business pressing it.
     */
    await press(page, 15);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-input")), {
        timeout: 4_000,
      })
      .toBe("pad");
  });
});

/**
 * A second gamepad, sitting in front of the real one.
 *
 * THIS IS THE CONFIGURATION AN ORDINARY WINDOWS DESKTOP IS IN. Steam publishes
 * a virtual pad beside the physical one, a wheel or a flight stick holds a slot,
 * and a controller that reconnects comes back at a higher index -- so slot zero
 * is very often a device nobody is touching. `getGamepads()` is indexed by SLOT
 * and is sparse, which is what makes "the first non-null entry" such a
 * convincing wrong answer.
 *
 * Read that way, every button on the pad in the player's hands comes back
 * neutral, the mode never leaves `mouse`, the ring never appears and NOTHING AT
 * ALL happens -- which is indistinguishable from the polling loop being dead,
 * and sends the next person to debug the loop. Every other test in this file
 * puts a lone pad in slot zero, so the whole suite passed against it.
 */
test.describe("a second gamepad in front of the real one", () => {
  test.use({ viewport: { width: 1600, height: 950 } });

  test("does not stop the pad being held from driving", async ({ page }) => {
    await page.addInitScript(() => {
      const mk = (id: string, index: number) => ({
        id,
        index,
        connected: true,
        mapping: "standard",
        timestamp: 0,
        axes: [0, 0, 0, 0],
        buttons: Array.from({ length: 17 }, () => ({
          pressed: false,
          touched: false,
          value: 0,
        })),
      });
      // An idle decoy in slot 0, the real pad two slots back.
      const decoy = mk("Virtual Gamepad (STANDARD GAMEPAD)", 0);
      const real = mk("Real Controller (STANDARD GAMEPAD)", 2);
      (window as unknown as Record<string, unknown>).__PAD = real;
      navigator.getGamepads = () => [decoy, null, real, null] as unknown as (Gamepad | null)[];
    });

    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    expect(
      await page.evaluate(() => navigator.getGamepads().filter(Boolean).length),
      "the decoy is not actually present",
    ).toBe(2);

    // `press` writes to `__PAD`, which is the pad NOT in slot zero.
    await press(page, BTN.down);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-input")), {
        timeout: 4_000,
      })
      .toBe("pad");

    // ...and it moves the ring, not merely the mode.
    const before = await cursor(page);
    await press(page, BTN.right);
    await expect.poll(() => cursor(page), { timeout: 4_000 }).not.toBe(before);
  });
});
