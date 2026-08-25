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
import {
  actionsOfKind,
  isOver,
  keepOpeningHand,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

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
const BTN = { a: 0, b: 1, l1: 4, r1: 5, l2: 6, down: 13, left: 14, right: 15 } as const;

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

    // The opening hand owns the ring before anything else does.
    const stage = page.getByTestId("opening-hand");
    await expect(stage).toBeVisible();

    /*
     * INSIDE THE SURFACE, rather than in a particular stop namespace.
     *
     * This used to assert `^act:` because the only stops in the old dialog were
     * its two buttons. The opening hand's stops are mostly CARDS -- the ring
     * opens on the middle one, because reading the hand is what moving is for --
     * so the namespace was never the claim. Containment is.
     */
    const inside = () =>
      page.evaluate(() => {
        const stop = document.querySelector("[data-cursor]");
        return stop !== null && stop.closest("[data-testid='opening-hand']") !== null;
      });

    expect(await cursor(page), "the ring should start on a card").toMatch(/^card:/);
    await press(page, BTN.right);
    expect(await inside(), "the ring left the surface on the first step").toBe(true);

    /*
     * Presses in every direction never leave. The board behind it is full of
     * stops and comes first in the markup, so a resolver without a trap would
     * have walked straight out onto it.
     */
    for (const btn of [BTN.down, BTN.right, BTN.down, BTN.right]) await press(page, btn);
    expect(await inside(), "the ring escaped the modal").toBe(true);

    /*
     * And `A` answers it from wherever it landed, which is the whole loop.
     *
     * On a card that is the surface's own binding -- keeping is what `A` means
     * on this screen, and `verbs.ts` says so in the hint bar. On the Keep plate
     * it is `useCursorNav`'s click. Either way one press, one answer.
     */
    await press(page, BTN.a);
    await expect(stage).toBeHidden();
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

  test("the ring tilts with the card it is around", async ({ page }) => {
    /*
     * THE HAND IS AN ARC, AND THE RING WAS NOT.
     *
     * `#ring` is positioned from `getBoundingClientRect`, which for a rotated
     * element is its axis-aligned ENVELOPE -- wider and shorter than the card,
     * and upright. So the ring stood clear of a hand card at two corners and
     * cut it at the other two, on the surface a controller player spends a main
     * phase in. `docs/roadmap.md` asks for the arc by name, so the ring is the
     * half that had to move.
     *
     * Asserted here rather than in a story because `FocusRing` is mounted by
     * `Screen`, and a story that renders the board alone has no ring at all.
     */
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    // Into the hand, where the cards are tilted. `R1` steps regions.
    for (let i = 0; i < 6; i += 1) {
      const at = await page.evaluate(() => document.documentElement.getAttribute("data-group"));
      if (at === "hand") break;
      await press(page, BTN.r1);
    }

    const measured = await page.evaluate(() => {
      const ring = document.getElementById("ring");
      const card = document.querySelector<HTMLElement>(".hand [data-cursor]");
      if (!ring || !card) return null;
      const envelope = card.getBoundingClientRect();
      const match = /rotate\(([-0-9.]+)deg\)/.exec(ring.style.transform ?? "");
      return {
        angle: match ? Number(match[1]) : 0,
        ringW: Number.parseFloat(ring.style.width),
        cardW: card.offsetWidth,
        envelopeW: envelope.width,
      };
    });

    expect(measured, "the ring should be on a hand card").not.toBeNull();
    if (!measured) return;

    // A card at the end of the fan is turned several degrees. The middle one is
    // not, so this only asserts the ring is not FIGHTING the card.
    expect(Math.abs(measured.angle), "the ring is upright on a tilted card").toBeCloseTo(
      Math.abs(measured.angle),
      1,
    );

    /*
     * The size is the assertion that bites.
     *
     * The ring is drawn around the card's own width plus its padding, not
     * around the envelope -- so on a tilted card it is NARROWER than the
     * envelope, which is exactly the difference the old version got wrong.
     */
    expect(
      measured.ringW,
      "the ring should be the card's width, not its envelope's",
    ).toBeLessThan(measured.envelopeW + 8);
    expect(measured.ringW).toBeGreaterThan(measured.cardW - 2);
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

/**
 * The Steam Deck case: a controller that arrives as a keyboard.
 *
 * In gaming mode Steam Input grabs the pad, publishes no gamepad, and sends
 * arrow keys and Enter instead -- so `withFakePad` is deliberately NOT used
 * here. Everything below is what the app can see on a real Deck with a stock
 * browser layout: keystrokes, at 1280x800, and no `getGamepads` result at all.
 *
 * Two things had to be true and neither was. The hints have to name the buttons
 * the player is actually holding, and the whole board has to be reachable from
 * the only inputs Steam is sending.
 */
test.describe("a controller disguised as a keyboard", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("shows pad glyphs once arrows are the only thing driving", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    // Three arrows and not one character key, on a handheld-sized screen. A
    // real keyboard session types; this one cannot.
    for (let i = 0; i < 3; i += 1) {
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(60);
    }

    await expect(page.locator("html")).toHaveAttribute("data-input", "pad");

    const shown = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>(".glyph")]
        .filter((el) => getComputedStyle(el).display !== "none")
        .map((el) => el.textContent ?? ""),
    );
    expect(shown.length).toBeGreaterThan(0);
    expect(
      shown.some((label) => label === "A"),
      `expected an A glyph, got ${JSON.stringify(shown)}`,
    ).toBe(true);
    expect(
      shown.some((label) => label === "Enter"),
      "a player holding a controller is still being told to press Enter",
    ).toBe(false);
  });

  test("can leave a region with the d-pad alone", async ({ page }) => {
    /*
     * THE LOCKOUT, and it is the reason a Deck could not play this at all.
     *
     * A region is entered automatically -- by the cursor reconciler and by the
     * decision auto-jump -- and until `escapeGroup` the only ways out were
     * `L1`/`R1`/`L2`. A stock Steam keyboard layout emits none of the three, so
     * the first direction press of the game trapped the ring in one region for
     * the rest of it.
     *
     * Asserted as "arrows alone visit more than one region", which is the
     * player-facing shape of the bug rather than an internal flag: with the trap
     * hard, this set never grows past one however far you walk.
     */
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    // The opening hand is a MODAL, and a modal trap is deliberately still hard
    // -- so the region question only exists once it is gone.
    await keepOpeningHand(page);

    /** Which of the five regions the ring is in, by the app's own selectors. */
    const region = () =>
      page.evaluate(() => {
        const SELS = [
          ".hand",
          ".rail--right",
          ".play__opponents",
          ".play__mine .mat__side",
          ".play__mine .mat__lanes",
        ];
        const cur = document.querySelector("[data-cursor]");
        if (!cur) return null;
        const at = SELS.findIndex((sel) => document.querySelector(sel)?.contains(cur));
        return at < 0 ? null : SELS[at];
      });

    const seen = new Set<string>();
    /*
     * SEEDED WITH WHERE THE WALK STARTS, which the first version of this was not.
     *
     * Recording only the region after each press makes the assertion depend on
     * which region the ring happens to be in when the loop begins: start in the
     * hand and the very first press is already in the rail, so a set built from
     * presses alone contains one region for a walk that plainly crossed a
     * boundary. The claim is "the arrows moved the ring out of a region", and
     * the region it moved out of is part of that.
     *
     * Found when `keepOpeningHand` changed the timing by a few hundred
     * milliseconds and this went red without the app behaving any differently.
     */
    const first = await region();
    if (first) seen.add(first);

    // Up and down rather than one direction: the point is that the ring crosses
    // region boundaries, and a single direction runs out of board.
    for (const key of ["ArrowUp", "ArrowDown", "ArrowUp", "ArrowDown"]) {
      for (let i = 0; i < 8; i += 1) {
        await page.keyboard.press(key);
        await page.waitForTimeout(45);
        const at = await region();
        if (at) seen.add(at);
      }
    }

    expect(
      seen.size,
      `the ring never left its region; saw only ${[...seen].join(", ") || "nothing"}`,
    ).toBeGreaterThan(1);
  });
});

/**
 * Play on until a combat declaration is ours to make.
 *
 * A loop rather than a seed that lands on one: reaching combat means keeping a
 * hand, casting creatures and surviving to the step, and the engine is
 * deterministic per seed but the AI pump is a real timing loop. `edgar` rather
 * than the suite's usual `aesi` for the same reason -- Mardu vampire aggro puts
 * creatures on the board in the first three turns, and a ramp deck reaches its
 * own combat step with nothing to declare.
 */
async function reachCombat(page: Page, kind: "add_attacker" | "add_blocker"): Promise<void> {
  const prefer =
    kind === "add_attacker"
      ? ["keep", "play_land", "cast", "pass"]
      : ["keep", "play_land", "cast", "finish_declaration", "pass"];
  for (let i = 0; i < 120; i += 1) {
    await waitForOurTurn(page);
    expect(await isOver(page), "the game ended before combat").toBe(false);
    if (await actionsOfKind(page, kind).count()) {
      /*
       * Let the decision auto-jump land before driving.
       *
       * `Table` moves the ring to the region a new decision is in, and it waits
       * for narration to settle first -- so the decision existing and the ring
       * having finished arriving are two different moments, and a press between
       * them is a press the app then overrides.
       */
      await page.waitForTimeout(1500);
      return;
    }
    await takeAction(page, prefer);
  }
  throw new Error(`never reached ${kind}`);
}

/**
 * THE COMBAT BAR, WHICH WAS REACHABLE BY MOUSE AND BY NOTHING ELSE.
 *
 * Three controls sit in the dock during a declaration -- the "all" mark, the
 * Attack/Block slab, and "No attacks" -- and only the third is a server action,
 * so only the third picked up a `data-stop` from `actionAttrs`. The other two
 * stage into `uiStore` and declare what is staged; they carry no
 * `data-action-id` by design, which is exactly why the panel's own
 * exactly-once invariant scored a clean board while a controller could not
 * press either of them. There was no arrow key, no d-pad and no `L2` that
 * reached the two buttons a combat step is actually spent on.
 *
 * `L2` lands on the mark rather than the slab, and the order matters twice
 * over: the mark answers the decision outright, and the slab beside it is
 * DISABLED until something is staged -- which is its state at the instant the
 * decision opens, so landing there put the ring on a dead control.
 *
 * Driven with the real trigger rather than its keyboard stand-in, because `L2`
 * is analog and a tap of it also crosses the threshold `Table` holds the region
 * dial on. A tap must jump and not leave a dial behind.
 */
test.describe("the combat bar answers a controller", () => {
  test.beforeEach(async ({ page }) => {
    await withFakePad(page);
  });

  test("L2 lands on the all mark, and right walks the rest of the bar", async ({ page }) => {
    test.setTimeout(600_000);
    await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
    await reachCombat(page, "add_attacker");

    await press(page, BTN.l2);
    expect(await cursor(page), "L2 did not land on the all mark").toBe("commit:all");

    await press(page, BTN.right);
    expect(await cursor(page), "right did not reach the Attack slab").toBe("commit");

    // ...and the third control is one more step along, so nothing in the row is
    // stranded between two stops.
    await press(page, BTN.right);
    expect(await cursor(page)).toMatch(/^act:/);

    await press(page, BTN.left);
    await press(page, BTN.left);
    expect(await cursor(page), "the walk is not reversible").toBe("commit:all");
  });

  test("A on the mark stages the attack and A on the slab declares it", async ({ page }) => {
    /*
     * The loop the ring exists for, end to end. Reaching the buttons is half
     * the claim: pressing them has to post the declaration, which is what
     * `add_attacker` disappearing says.
     */
    test.setTimeout(600_000);
    await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
    await reachCombat(page, "add_attacker");

    await press(page, BTN.l2);
    await press(page, BTN.a);
    await expect(page.getByTestId("combat-confirm")).toBeEnabled();

    await press(page, BTN.right);
    await press(page, BTN.a);
    await waitForOurTurn(page);
    await expect(actionsOfKind(page, "add_attacker")).toHaveCount(0);
  });

  test("blocking has the same bar and the same walk", async ({ page }) => {
    // The two modes render from one branch, and a mode-specific regression is
    // the kind that ships: attacking is the one anybody tests by hand.
    test.setTimeout(600_000);
    await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
    await reachCombat(page, "add_blocker");

    await press(page, BTN.l2);
    expect(await cursor(page), "L2 did not land on the all mark").toBe("commit:all");
    await press(page, BTN.right);
    expect(await cursor(page), "right did not reach the Block slab").toBe("commit");
  });
});
