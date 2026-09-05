/**
 * The player orb, rebuilt from `mockups/orb/03-plinth.html`.
 *
 * Two things here reduce to numbers, and `docs/testing.md` is explicit that where
 * they do they must be *measured* rather than looked at: `body { overflow:
 * hidden }` means the page reports `scrollHeight === clientHeight` while content
 * visibly runs off the bottom, so an assertion about content passes happily
 * through a layout failure. The numbers are the panel's height against its column
 * and every child's box against the panel's.
 *
 * The third thing is behavioural and was the actual bug: hovering a commander
 * fills the preview rail. It worked only for a commander you could cast this
 * instant, because every other plinth was a `disabled` button and a disabled
 * control dispatches no mouse events.
 */

import { type Locator, type Page, expect, test } from "@playwright/test";
import { budget, keepOpeningHand, startGame } from "./helpers";

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

async function boxOf(locator: Locator): Promise<Box> {
  const box = await locator.boundingBox();
  if (!box) throw new Error("element has no box");
  return box;
}

/** Start a pod and get past the opening hand. A pod is where seats differ. */
async function openPod(page: Page, opponents = 3): Promise<void> {
  await startGame(page, { deck: "aesi", opponents, seed: 7, zoomLock: true });
  await keepOpeningHand(page);
}

test.describe("the orb fills its column", () => {
  test("the panel is as tall as the side column it sits in", async ({ page }) => {
    // 03 Plinth measures 190x318 and the column gets 341px or more, which left a
    // strip of dead mat under the panel. 01 Astrolabe's proportion -- the orb
    // reaching the same height as the board beside it -- is the one to match.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const orb = await boxOf(page.getByTestId("player-0"));
    const side = await boxOf(page.locator('[data-testid="mat-0"] .mat__side'));
    expect(
      Math.abs(orb.height - side.height),
      `orb ${orb.height} vs column ${side.height}`,
    ).toBeLessThanOrEqual(1);
  });

  test("the piles sit on the panel's bottom edge, not under the plinth", async ({ page }) => {
    // `space-between` is where the slack goes. If the piles ever float back up
    // to the top the panel has stopped filling and started padding.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const orb = await boxOf(page.getByTestId("player-0"));
    const piles = await boxOf(page.locator('[data-testid="player-0"] .piles'));
    const gap = orb.y + orb.height - (piles.y + piles.height);
    expect(gap, `${gap}px of panel below the piles`).toBeLessThanOrEqual(12);
  });

  test("nothing paints outside the panel", async ({ page }) => {
    // The "escape" check mockups/README.md asks for, and the one `overflow:
    // hidden` on the orb would hide if it were asserted by eye. The seal hangs
    // off the *portrait*, deliberately; it must not hang off the panel.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const escaped = await page.evaluate(() => {
      const orb = document.querySelector('[data-testid="player-0"]');
      if (!orb) return ["no orb"];
      const bounds = orb.getBoundingClientRect();
      const out: string[] = [];
      for (const node of orb.querySelectorAll("*")) {
        const box = node.getBoundingClientRect();
        if (box.width === 0 && box.height === 0) continue;
        // The wash is inset -14% on purpose; the panel clips it.
        if ((node as HTMLElement).classList.contains("orb__wash")) continue;
        if (
          box.left < bounds.left - 1 ||
          box.right > bounds.right + 1 ||
          box.top < bounds.top - 1 ||
          box.bottom > bounds.bottom + 1
        ) {
          out.push(`${(node as HTMLElement).className || node.nodeName}`);
        }
      }
      return out;
    });
    expect(escaped, "these escaped the orb").toEqual([]);
  });

  test("the piles still share one baseline in the 190px column", async ({ page }) => {
    // The arithmetic written into board.css: 5 x 28 + 4 x 5 = 160px, and adding
    // the scrim plate's padding is exactly the kind of change that quietly
    // breaks it. Measured on the *bottom* edge, not the top: the piles are
    // deliberately bottom-aligned so their heights read against each other, so a
    // drawn-down library and a grown graveyard have different tops by design.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const bottoms = await page
      .locator('[data-testid="player-0"] .pile')
      .evaluateAll((nodes) => nodes.map((n) => Math.round(n.getBoundingClientRect().bottom)));
    expect(bottoms.length).toBeGreaterThanOrEqual(4);
    expect(new Set(bottoms).size, `pile bottoms: ${bottoms.join(", ")}`).toBe(1);
  });

  test("an opponent's zone marks share one row, exile included", async ({ page }) => {
    /*
     * This used to measure PILES on an opponent's orb. There is no opponent orb
     * any more -- a seat is a summary rather than a control panel, and its
     * zones are 20px marks rather than leaf stacks, because a seat can spare
     * one row of a 96px budget and a 44px pile target does not fit in it.
     *
     * What survives unchanged is the question: five marks or four, sharing one
     * row, none of them clipped. Exile is conditional and it is the fifth, so
     * it is inserted rather than waited for -- a spec that only ever sees four
     * is not testing the case that overflows.
     */
    test.setTimeout(budget(240_000));
    await openPod(page, 3);

    const rows = await page.evaluate(() => {
      const zones = document.querySelector('[data-testid="player-1"] .seat__zones');
      if (!zones) return null;
      const last = zones.children[zones.children.length - 1];
      zones.insertBefore(last.cloneNode(true), last);

      const kids = [...zones.children] as HTMLElement[];
      return {
        count: kids.length,
        rows: new Set(kids.map((k) => Math.round(k.getBoundingClientRect().bottom))).size,
        clipped: kids
          .filter((k) => k.scrollWidth > k.clientWidth + 1)
          .map((k) => k.textContent),
        overflow: Math.round(zones.scrollWidth - zones.clientWidth),
      };
    });

    expect(rows?.count).toBe(5);
    expect(rows?.rows, "the seat's zone marks wrapped to a second row").toBe(1);
    expect(rows?.clipped, "these zone marks are clipped").toEqual([]);
    expect(rows?.overflow, "the zone row overflows the seat").toBeLessThanOrEqual(0);
  });
});

test.describe("the life seal", () => {
  test("is stamped on the portrait, half on and half off", async ({ page }) => {
    // The idea the whole direction is built on: the dial costs the overlap
    // rather than a row of its own. If it stops overlapping it has silently
    // become a row again and the panel has grown by its diameter.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const dial = await boxOf(page.locator('[data-testid="player-0"] .dial'));
    const frame = await boxOf(page.locator('[data-testid="player-0"] .cmdplinth__frame'));

    // Overlapping the art's lower edge from inside it.
    expect(dial.y, "the seal starts above the portrait").toBeGreaterThan(frame.y);
    expect(dial.y, "the seal has left the portrait entirely").toBeLessThan(
      frame.y + frame.height,
    );
    expect(dial.y + dial.height, "the seal no longer hangs off the portrait").toBeGreaterThan(
      frame.y + frame.height,
    );
    // And on the right, where the crop is least informative.
    expect(dial.x).toBeGreaterThan(frame.x + frame.width / 2);
  });

  test("holds a bare life total that the helpers can still parse", async ({ page }) => {
    test.setTimeout(budget(180_000));
    await openPod(page, 1);
    const text = await page.getByTestId("life-0").textContent();
    expect(Number(text)).toBe(40);
  });

  test("does not eat the click that casts the commander", async ({ page }) => {
    // A decorative disc sitting on the cast control is the one way this
    // arrangement could break the thing it sits on.
    //
    // Asserted on the computed property rather than by hit-testing the point:
    // `elementFromPoint` answers about whatever is topmost in the *document*, so
    // a decision modal's backdrop over the board turns this into a test of which
    // prompt the seed happened to produce. The property is the actual contract,
    // and cycle3.spec.ts already clicks the plinth through it for real.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);
    const pointers = await page
      .locator('[data-testid="player-0"] .cmdplinth__frame .dial')
      .evaluate((node) => [
        getComputedStyle(node).pointerEvents,
        getComputedStyle(node.querySelector(".dial__n") as Element).pointerEvents,
      ]);
    expect(pointers, "the seal is intercepting pointer events over the plinth").toEqual([
      "none",
      "none",
    ]);
  });
});

test.describe("hovering a commander fills the preview rail", () => {
  test("works for your own commander while it is not castable", async ({ page }) => {
    // The bug, in its most common form: on turn one you cannot cast a six-drop,
    // so the plinth was disabled, so hovering it did nothing at all.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const slot = page.getByTestId("command-zone-0").locator(".cmdslot").first();
    await expect(slot).toHaveAttribute("data-castable", "false");
    const name = (await slot.locator(".cmdplinth__name").textContent())?.trim() ?? "";
    expect(name).not.toBe("");

    const preview = page.getByTestId("card-preview");
    await expect(preview).toContainText("Hover a card to read it");
    await slot.hover();
    await expect(preview).toContainText(name);
  });

  test("works for an opponent's commander, which you can never cast", async ({ page }) => {
    /*
     * Reading an opponent's commander is most of why you look at their panel --
     * "what is that deck about" is one card's text.
     *
     * It used to be a `.cmdslot` plinth, because an opponent rendered the same
     * column the viewer does. An opponent is an `OpponentSeat` now and its
     * commander is the 72x43 window, so the affordance moved rather than went:
     * hover the window and the reader fills, exactly as before. `Y` does the
     * same for a controller, at full size.
     */
    test.setTimeout(budget(180_000));
    await openPod(page, 3);

    const seat = page.getByTestId("player-1");
    const name = (await seat.locator(".seat__cmdr").textContent())?.trim() ?? "";
    expect(name, "the seat should name its commander").not.toBe("");

    await seat.locator(".seat__win").hover();
    await expect(page.getByTestId("card-preview")).toContainText(name);
  });

  test("clears again when the pointer leaves", async ({ page }) => {
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const slot = page.getByTestId("command-zone-0").locator(".cmdslot").first();
    await slot.hover();
    await expect(page.getByTestId("card-preview")).not.toContainText("Hover a card to read it");
    await page.getByTestId("table").hover({ position: { x: 2, y: 2 } });
    await expect(page.getByTestId("card-preview")).toContainText("Hover a card to read it");
  });
});

test.describe("the commander is the panel's ground", () => {
  test("every seat's orb is washed with its own commander's art", async ({ page }) => {
    // README defect #4: four seats were four grey rectangles told apart by a name
    // in 12px type. Distinct URLs is the machine-checkable form of "they look
    // different", and it is what a screenshot cannot fail a build on.
    test.setTimeout(budget(240_000));
    await openPod(page, 3);

    /*
     * Four seats, four paintings -- drawn by two components now.
     *
     * The viewer keeps `.orb__wash`; an opponent is an `OpponentSeat` and its
     * ground is `.seat__ground`. The claim is unchanged and is the one that
     * matters: every seat is told apart by its own commander's art rather than
     * by a name in 12px type, and DISTINCT URLS is the machine-checkable form
     * of "they look different".
     */
    const grounds = await page
      .locator(".orb__wash, .seat__ground")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).style.backgroundImage));
    expect(await page.locator(".orb__wash").count(), "one orb, and it is yours").toBe(1);
    expect(await page.locator(".seat__ground").count(), "one ground per opponent").toBe(3);
    expect(grounds.length).toBe(4);
    expect(grounds.every((w) => w.includes("/art/"))).toBe(true);
    expect(new Set(grounds).size, `grounds: ${grounds.join(" | ")}`).toBe(4);
  });

  test("the wash reuses the plinth's art rather than asking for a second crop", async ({
    page,
  }) => {
    test.setTimeout(budget(180_000));
    await openPod(page, 1);

    const same = await page.evaluate(() => {
      const orb = document.querySelector('[data-testid="player-0"]');
      const wash = orb?.querySelector<HTMLElement>(".orb__wash")?.style.backgroundImage ?? "";
      const img = orb?.querySelector<HTMLImageElement>(".cmdplinth__art img")?.src ?? "";
      return img !== "" && wash.includes(new URL(img).pathname);
    });
    expect(same, "the wash and the portrait disagree about the art URL").toBe(true);
  });

  test("carries no colour-identity tint", async ({ page }) => {
    // Dropped from the mockup on purpose: the tint is the channel that dies in
    // greyscale and the portrait under it is not. greyscale.spec.ts is what has
    // to agree first if it ever comes back.
    test.setTimeout(budget(180_000));
    await openPod(page, 1);
    expect(await page.locator(".orb__tint").count()).toBe(0);
  });
});
