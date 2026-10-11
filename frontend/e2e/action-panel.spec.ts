/**
 * The action panel, driven in a real browser.
 *
 * `ActionPanel` merged an action bar and a combat panel into one surface with
 * three modes, and it took over the invariant the whole client rests on: every
 * legal action is a button carrying `data-action-id`, exactly once in the
 * document. That is a lot of behaviour concentrated in one component, and most
 * of it is the kind that fails silently -- a row that stages the wrong pair, an
 * id that renders twice, a control that moved into the footer and stopped
 * working there. None of it shows up as an exception.
 *
 * So these are assertions about structured data the panel emits on purpose --
 * `data-attacker`, `data-blocker`, `data-tier`, `data-staged` -- rather than
 * about label text. `cycle3.spec.ts` used to check "one blocker, one attacker"
 * by splitting a row's label on " blocks ", and that check would have passed for
 * the wrong reason the moment anybody reworded the row.
 */

import { expect, type Locator, type Page, test } from "@playwright/test";
import {
  actionsOfKind,
  budget,
  COMBAT_SEED,
  isOver,
  keepOpeningHand,
  reachDeclaration,
  startGame,
  waitForOurTurn,
} from "./helpers";

/** Every action id in the document, in DOM order, including disabled ones. */
async function renderedIds(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll("[data-action-id]")].map(
      (n) => n.getAttribute("data-action-id") ?? "",
    ),
  );
}

/** Action ids the server currently says are legal, read off the panel's own rows. */
function rowsOfKind(page: Page, kind: string): Locator {
  return page.locator(`.acts__list [data-action-kind="${kind}"]`);
}

/**
 * Reach a main-phase priority window with something playable in it.
 *
 * The opening hand has to be answered first and answered *there*: it owns the
 * screen, so the panel deliberately renders none of its actions, and a loop
 * that only looks for panel rows sits in front of it forever.
 */
async function reachPriority(page: Page, limit = 60): Promise<boolean> {
  await keepOpeningHand(page);

  for (let i = 0; i < limit; i += 1) {
    await waitForOurTurn(page);
    if (await isOver(page)) return false;
    if (
      (await rowsOfKind(page, "cast").count()) ||
      (await rowsOfKind(page, "play_land").count())
    ) {
      return true;
    }
    const pass = actionsOfKind(page, "pass");
    if (await pass.count()) {
      await pass.first().click();
      continue;
    }
    // Some other decision owns the turn; take whatever is offered and look again.
    const any = page.locator("[data-action-id]:not([disabled])").first();
    if (await any.count()) await any.click().catch(() => {});
  }
  return false;
}

// ---------------------------------------------------------------- attackers

test.describe("choosing attackers", () => {
  test("is one row per creature and one click per attack", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "attackers");

    const panel = page.getByTestId("combat-panel");
    const rows = panel.locator(".acts__list .act[data-attacker]");

    // 1. One row per *creature*, not per legal pair. The surface this replaced
    //    rendered a chip per pair, which in a pod is attackers x opponents.
    const distinctSources = await page.evaluate(
      () =>
        new Set(
          [...document.querySelectorAll('[data-action-kind="add_attacker"]')].map((n) =>
            n.getAttribute("data-attacker"),
          ),
        ).size,
    );
    await expect(rows).toHaveCount(distinctSources);

    // 2. One click stages, and nothing reaches the server. Watching `/declare`
    //    specifically: that is the endpoint staging must not touch, and a bare
    //    "no POSTs" check would be at the mercy of anything else in flight.
    const posts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /declare|action/.test(r.url())) posts.push(r.url());
    });
    const first = rows.first();
    await first.click();
    await expect(first).toHaveAttribute("data-staged", "true");
    await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
      "aria-label",
      "Attack with 1",
    );
    await expect(page.getByTestId("combat-confirm")).toBeEnabled();
    expect(posts, "staging posted to the server; it must stay local").toEqual([]);

    // 3. Clicking again releases it.
    await first.click();
    await expect(first).not.toHaveAttribute("data-staged", "true");
    await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
      "aria-label",
      "Attack with 0",
    );
    await expect(page.getByTestId("combat-confirm")).toBeDisabled();
  });

  test("keeps every pair reachable exactly once", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "attackers");

    // 5. The load-bearing invariant, asserted at the moment combat is open --
    //    which is when the surface that used to break it was on screen.
    const ids = await renderedIds(page);
    expect(new Set(ids).size, `duplicate action ids: ${ids.join(", ")}`).toBe(ids.length);
    expect(ids.length).toBeGreaterThan(0);
  });

  test("agrees with the board: staging on one surface shows on the other", async ({ page }) => {
    // The likeliest real bug in the merge, and neither surface tested it before:
    // the panel row and the card are two views of one `stagedAttacks` entry, and
    // nothing but this notices if they drift apart.
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "attackers");

    const row = page.getByTestId("combat-panel").locator(".act[data-attacker]").first();
    const oid = await row.getAttribute("data-attacker");
    expect(oid).not.toBeNull();
    const boardCard = page.locator(`.play__mine [data-oid="${oid}"]`);

    // 6a. Panel -> board.
    await row.click();
    await expect(row).toHaveAttribute("data-staged", "true");
    await expect(boardCard).toHaveClass(/card--staged/);

    // 6b. Board -> panel.
    await boardCard.click();
    await expect(row).not.toHaveAttribute("data-staged", "true");
    await expect(boardCard).not.toHaveClass(/card--staged/);
  });
});

// ---------------------------------------------------------------- defenders

test.describe("choosing a defender in a pod", () => {
  test("puts one id on each defender and re-points rather than adding", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 2 });
    await reachDeclaration(page, "attackers");

    const panel = page.getByTestId("combat-panel");

    // 7 + 8. Where the ids live depends on how many defenders a creature has,
    //        and getting that wrong is how the same id ends up on two controls.
    //        A row with chips carries none itself; a row without chips carries
    //        its own. Either way each pair is on exactly one control.
    const placement = await panel.evaluate((root) => {
      const out: { attacker: string | null; chips: number; onRow: boolean }[] = [];
      for (const row of root.querySelectorAll(".act[data-attacker]")) {
        out.push({
          attacker: row.getAttribute("data-attacker"),
          chips: row.querySelectorAll(".aim[data-action-id]").length,
          onRow: row.hasAttribute("data-action-id"),
        });
      }
      return out;
    });
    expect(placement.length).toBeGreaterThan(0);
    for (const row of placement) {
      if (row.chips > 0) {
        expect(row.onRow, `attacker ${row.attacker} carries an id and chips both`).toBe(false);
      } else {
        expect(row.onRow, `attacker ${row.attacker} carries no id anywhere`).toBe(true);
      }
    }

    const ids = await renderedIds(page);
    expect(new Set(ids).size).toBe(ids.length);

    // 9. Re-point, never add. `stagedAttacks` is keyed by attacker oid, so one
    //    creature cannot attack twice -- but a UI could easily imply it can.
    const multi = panel.locator(".act[data-attacker]:has(.aim)").first();
    test.skip(!(await multi.count()), "no creature had more than one legal defender");
    const chips = multi.locator(".aim");
    await chips.nth(0).click();
    await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
      "aria-label",
      "Attack with 1",
    );
    await chips.nth(1).click();
    await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
      "aria-label",
      "Attack with 1",
    );
    await expect(chips.nth(1)).toHaveAttribute("aria-pressed", "true");
    await expect(chips.nth(0)).toHaveAttribute("aria-pressed", "false");
  });
});

// ------------------------------------------------------------------ blockers

test.describe("choosing blocks", () => {
  test("groups by your creature and says what each block would do", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "blockers");

    const panel = page.getByTestId("combat-panel");

    // 10. One group per creature of yours that can block, and the rows under it
    //     are exactly the attackers it may legally block.
    const groups = await panel.evaluate((root) => {
      const out: { blocker: string | null; rows: string[] }[] = [];
      for (const group of root.querySelectorAll(".actgroup")) {
        out.push({
          blocker: group.getAttribute("data-blocker"),
          rows: [...group.querySelectorAll(".act[data-attacker]")].map(
            (n) => n.getAttribute("data-attacker") ?? "",
          ),
        });
      }
      return out;
    });
    expect(groups.length).toBeGreaterThan(0);
    // Every legal pair the server offered appears under its own blocker.
    const legal = await page.evaluate(() =>
      [...document.querySelectorAll('[data-action-kind="add_blocker"]')].map((n) => ({
        blocker: n.getAttribute("data-blocker"),
        attacker: n.getAttribute("data-attacker"),
      })),
    );
    for (const pair of legal) {
      const group = groups.find((g) => g.blocker === pair.blocker);
      expect(group, `no group for blocker ${pair.blocker}`).toBeTruthy();
      expect(group?.rows).toContain(pair.attacker);
    }

    // 11. The attacker's power and toughness, and the verdict, are both on the
    //     row *before* you click it. Deciding a block means comparing two
    //     numbers and only one of them used to be in the panel at all.
    const nested = panel.locator(".actgroup .act[data-attacker]").first();
    await expect(nested.locator(".act__pt")).toHaveText(/^\d+\/\d+$/);
    const tier = await nested.getAttribute("data-tier");
    expect(["1", "2", "3", "4"]).toContain(tier);
    await expect(nested.locator(".verdict")).not.toHaveText("");
  });

  test("assigns a block in one click and re-points on the second", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "blockers");

    const panel = page.getByTestId("combat-panel");
    // Prefer a creature with two or more legal blocks, so the re-point half of
    // the test is exercisable; fall back to any group that has one.
    const blocker = await panel.evaluate((root) => {
      const groups = [...root.querySelectorAll(".actgroup")];
      const rich = groups.find((g) => g.querySelectorAll(".act[data-attacker]").length >= 2);
      const any = groups.find((g) => g.querySelectorAll(".act[data-attacker]").length >= 1);
      return (rich ?? any)?.getAttribute("data-blocker") ?? null;
    });
    test.skip(blocker === null, "no creature had a legal block");
    const rows = panel.locator(`.actgroup[data-blocker="${blocker}"] .act[data-attacker]`);

    // 12. One click. No pick-blocker-then-pick-attacker step.
    await rows.first().click();
    await expect(rows.first()).toHaveAttribute("data-staged", "true");
    await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
      "aria-label",
      "Confirm 1 block",
    );
    await expect(page.getByTestId("combat-confirm")).toBeEnabled();

    // 13. One blocker, one attacker: choosing a second under the same creature
    //     moves it rather than adding a second assignment.
    if ((await rows.count()) > 1) {
      await rows.nth(1).click();
      await expect(rows.nth(1)).toHaveAttribute("data-staged", "true");
      await expect(rows.first()).not.toHaveAttribute("data-staged", "true");
      await expect(page.getByTestId("combat-confirm")).toHaveAttribute(
        "aria-label",
        "Confirm 1 block",
      );
    }

    // 15. And every pair is still reachable exactly once.
    const ids = await renderedIds(page);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

// ---------------------------------------------------------------------- play

test.describe("playing cards from the panel", () => {
  test("renders every legal action exactly once, and the slab is not a row", async ({
    page,
  }) => {
    test.setTimeout(budget(300_000));
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    test.skip(
      !(await reachPriority(page)),
      "never reached a priority window with a play in it",
    );

    // 16. The contract `ActionBar` used to hold: a decision always has a
    //     surface, and for a priority window it is this one.
    const ids = await renderedIds(page);
    expect(new Set(ids).size, `duplicate action ids: ${ids.join(", ")}`).toBe(ids.length);

    // Every *priority* action is in the panel or its dock. Scoped to those kinds
    // on purpose: two other surfaces legitimately carry ids and asserting "no id
    // anywhere else" would be asserting they are bugs. `PromptDialog` owns modal
    // decisions outright -- which is why the panel stands its list down for them
    // -- and `CommandZone` puts the play action on the commander itself.
    const outside = await page.evaluate(() => {
      const panel = document.querySelector('[data-testid="action-panel"]');
      const dock = document.querySelector(".commit-dock");
      const owned = ["cast", "play_land", "activate", "pass"];
      return [...document.querySelectorAll("[data-action-kind]")]
        .filter((n) => owned.includes(n.getAttribute("data-action-kind") ?? ""))
        .filter((n) => !panel?.contains(n) && !dock?.contains(n))
        .filter((n) => !n.closest('[data-testid^="command-zone-"]'))
        .map((n) => n.getAttribute("data-action-id"));
    });
    expect(outside, "a priority action rendered outside the panel").toEqual([]);

    // 17. The specific way this layout breaks the invariant: one action is
    //     promoted to the slab, and if it is not also removed from the list it
    //     renders twice.
    const slab = page.getByTestId("commit");
    if (await slab.count()) {
      const slabId = await slab.getAttribute("data-action-id");
      expect(
        await page.locator(`.acts__list [data-action-id="${slabId}"]`).count(),
        "the commit slab's action is also a list row",
      ).toBe(0);
    }
  });

  test("casts from a row, and the row wears the playable colour", async ({ page }) => {
    test.setTimeout(budget(300_000));
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    test.skip(
      !(await reachPriority(page)),
      "never reached a priority window with a play in it",
    );

    const playRow = page
      .locator(
        '.acts__list [data-action-kind="cast"], .acts__list [data-action-kind="play_land"]',
      )
      .first();

    // 19. The same signal the card's own rim uses. Asserted as a computed colour
    //     rather than a class name: a class assertion passes happily while the
    //     token behind it resolves to something else entirely.
    const [rowTone, rimTone] = await page.evaluate(() => {
      const row = document.querySelector(
        '.acts__list [data-action-kind="cast"], .acts__list [data-action-kind="play_land"]',
      );
      const root = document.documentElement;
      return [
        row ? getComputedStyle(row).borderLeftColor : "",
        getComputedStyle(root).getPropertyValue("--playable").trim(),
      ];
    });
    expect(rowTone).not.toBe("");
    // Both resolve through the browser, so compare them as the browser sees them.
    const asRgb = await page.evaluate((hex) => {
      const probe = document.createElement("span");
      probe.style.color = hex;
      document.body.append(probe);
      const value = getComputedStyle(probe).color;
      probe.remove();
      return value;
    }, rimTone);
    expect(rowTone).toBe(asRgb);

    // 18. And the row is a real route into the game, not just a label.
    //
    //     Asserted as "the server moved past this action" rather than as a card
    //     count: a land goes hand -> battlefield, a creature goes hand -> stack
    //     -> battlefield, and the intermediate frames of either are a race. The
    //     action id disappearing from the legal list is the unambiguous signal
    //     that the click reached the engine.
    //
    //     BY THE CARD, NOT BY THE ACTION ID. Ids are positional (`a1-play_land`
    //     is "the second legal action", whatever it is), and with nothing left
    //     to cast the engine auto-passes through the opponent's turn and back
    //     to ours in one response -- where the NEXT land drop is `a1-play_land`
    //     again. On CI's slow runner the poll never saw the gap between the two
    //     and timed out on an id that had been answered and re-issued. The
    //     row's card (`data-preview-oid`) is stable: the land that was played
    //     is on the battlefield, and no row for it comes back.
    const played = await playRow.getAttribute("data-action-id");
    expect(played).not.toBeNull();
    // A grouped row (a shock land's two drops) carries the card on the row
    // and the action kind on its chips, so the card is read off the nearest
    // element that names one, and both shapes are counted.
    const card = await playRow.evaluate(
      (el) => el.closest("[data-preview-oid]")?.getAttribute("data-preview-oid") ?? null,
    );
    const kind = await playRow.getAttribute("data-action-kind");
    expect(card, "a play row names the card it plays").not.toBeNull();
    await playRow.click();
    const rowFor = `.acts__list [data-preview-oid="${card}"]`;
    await expect
      .poll(
        async () =>
          page
            .locator(
              `${rowFor}[data-action-kind="${kind}"], ${rowFor} [data-action-kind="${kind}"]`,
            )
            .count(),
        { timeout: 15_000 },
      )
      .toBe(0);
  });
});

// ------------------------------------------------------------------- reading

/**
 * Park the pointer somewhere with nothing under it.
 *
 * Hover assertions need a real transition to assert on. The loops above finish
 * by *clicking* something, which leaves the mouse sitting inside the panel -- and
 * if the row we then want to hover happens to be under that same point, Playwright
 * moves the mouse nowhere, the browser fires no `mouseover`, and the preview keeps
 * whatever it was showing. That reads as a broken feature and is not one.
 */
async function parkPointer(page: Page): Promise<void> {
  await page.mouse.move(4, 4);
  await page.waitForTimeout(120);
}

/**
 * Hover a control until the preview rail agrees, and report what it settled on.
 *
 * Hover state in a live client is genuinely racy and a single `.hover()` is not
 * enough to assert on: the pointer may already be inside the target (in which
 * case the browser fires no `mouseover` at all and nothing happens), and the
 * panel re-renders on every poll, so a row can be replaced between the move and
 * React processing it. Re-parking and re-hovering drives to a stable state
 * rather than assuming the first attempt lands.
 *
 * This does not paper over a broken feature: if the handler is missing the
 * preview never changes and every attempt reports the same stale name.
 */
async function hoverToRead(page: Page, target: Locator, want: string): Promise<string | null> {
  let last: string | null = null;
  for (let i = 0; i < 8; i += 1) {
    await parkPointer(page);
    await target.hover();
    await page.waitForTimeout(250);
    last = await page
      .locator('[data-testid="card-preview"] .face--big')
      .getAttribute("data-card-name")
      .catch(() => null);
    // Retry until it *matches*, not merely until it is non-empty: the rail may
    // still be holding a card from before this test reached its decision, and
    // accepting that would make the assertion pass for the wrong reason.
    if (last === want) return last;
  }
  return last;
}

test.describe("reading a card from the panel", () => {
  test("hovering a row fills the preview, exactly as hovering the card does", async ({
    page,
  }) => {
    test.setTimeout(budget(300_000));
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    test.skip(
      !(await reachPriority(page)),
      "never reached a priority window with a play in it",
    );

    const preview = page.getByTestId("card-preview");
    await expect(preview).toContainText("Hover a card");

    // A play row names a card in hand. Pointing at the row must read that card,
    // otherwise the row is a decision you cannot inspect without going and
    // finding the card on the board first.
    //
    // The assertion compares the preview against the row's *own* label rather
    // than against a card looked up by oid beforehand. That is both the claim a
    // player would make -- the row and the rail name the same card -- and the
    // only version that cannot go stale: the panel re-renders on every poll, so
    // an oid read before the hover is not guaranteed to still be that row.
    const row = page
      .locator(
        '.acts__list [data-source][data-action-kind="cast"], .acts__list [data-source][data-action-kind="play_land"]',
      )
      .first();

    const rowName = (await row.locator(".act__name").textContent())?.trim();
    expect(rowName).toBeTruthy();
    const shown = await hoverToRead(page, row, rowName ?? "");
    expect(shown, "the rail should read the card the row names").toBe(rowName);

    // And it lets go again, rather than pinning the rail to the last row seen.
    await page.locator(".track").hover();
    await expect(preview).toContainText("Hover a card");
  });

  /*
   * The blocker list carries the same wiring, asserted structurally.
   *
   * The behavioural version of this -- hover the header, assert the rail reads
   * your creature -- is correct and was verified by hand, but it is not testable
   * here yet: the rail can arrive at a blocker decision already pinned to a card
   * from earlier in the turn, and in that state it does not swap to the newly
   * hovered one. That is a preview bug, not a panel bug, and it is left as a
   * known defect rather than papered over with a retry loop that
   * would pass for the wrong reason.
   *
   * So this checks what it can check deterministically: both surfaces carry the
   * handlers, and they point at different cards -- which is the mistake worth
   * catching, since the header and its rows are one `previewing()` call apart
   * and it is easy to pass the wrong oid to either.
   */
  test("the blocker list wires both your creature and each attacker", async ({ page }) => {
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "blockers");

    const group = page.getByTestId("combat-panel").locator(".actgroup").first();
    test.skip(!(await group.locator(".act[data-attacker]").count()), "no legal block");

    const wiring = await group.evaluate((root) => {
      const handlers = (el: Element | null) => {
        if (!el) return [];
        const key = Object.keys(el).find((k) => k.startsWith("__reactProps"));
        // biome-ignore lint/suspicious/noExplicitAny: reading React's own props bag
        return key ? Object.keys((el as any)[key]).filter((p) => p.startsWith("on")) : [];
      };
      const head = root.querySelector(".actgroup__head");
      const row = root.querySelector(".act[data-attacker]");
      return {
        headHandlers: handlers(head),
        rowHandlers: handlers(row),
        headName: head?.querySelector(".actgroup__name")?.textContent?.trim() ?? null,
        rowName: row?.querySelector(".act__name")?.textContent?.trim() ?? null,
      };
    });

    expect(wiring.headHandlers).toContain("onMouseEnter");
    expect(wiring.headHandlers).toContain("onMouseLeave");
    expect(wiring.rowHandlers).toContain("onMouseEnter");
    expect(wiring.rowHandlers).toContain("onMouseLeave");
    // The header reads your creature and the row reads the attacker: if both
    // named the same card, one of them has been given the wrong oid.
    expect(wiring.headName).toBeTruthy();
    expect(wiring.rowName).toBeTruthy();
    expect(wiring.rowName).not.toBe(wiring.headName);
  });
});

// --------------------------------------------------------------------- tools

test.describe("the tools footer", () => {
  test("lives inside the panel and still works from there", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    // Past the opening hand first. It is a full-screen surface above
    // everything, so while it is up the tools are on screen but not clickable --
    // the same shape as `.prompt-backdrop`'s. That
    // is pre-existing and out of scope here; this test is about the footer.
    await keepOpeningHand(page);

    // 21. A descendant of the panel, not a pane of its own. The controls used to
    //     sit in a third bordered box in the rail, which is the gap this closed.
    const inside = await page.evaluate(() => {
      const pane = document.querySelector(".acts");
      const tools = document.querySelector(".tools");
      return {
        nested: Boolean(pane && tools && pane.contains(tools)),
        panes: document.querySelectorAll(".rail--right > *").length,
      };
    });
    expect(inside.nested, "the tools row is not inside the action panel").toBe(true);
    // Preview, panel, commit dock. A fourth means a pane came back.
    expect(inside.panes).toBeLessThanOrEqual(3);

    // 22. Moving markup is exactly the change that silently unhooks a handler.
    //     Sound, undo and quit live behind the gear now -- three controls
    //     pressed at most once a game, at the same weight as the two modes
    //     beside them that change how every priority window behaves. The
    //     handler test is the same one; only the route to the button moved.
    await expect(page.getByTestId("settings-menu")).toHaveCount(0);
    await page.getByTestId("settings").click();
    await expect(page.getByTestId("settings-menu")).toBeVisible();

    const mute = page.getByTestId("mute");
    const before = await mute.getAttribute("aria-pressed");
    await mute.click();
    await expect(mute).not.toHaveAttribute("aria-pressed", before ?? "");

    // It opens UPWARDS: this strip is the last row of the panel on a desktop
    // and of the foot on a handheld, so a menu that opened downwards would land
    // on the commit slab or off the screen.
    const above = await page.evaluate(() => {
      const menu = document.querySelector(".settings__menu");
      const button = document.querySelector('[data-testid="settings"]');
      if (!menu || !button) return null;
      return menu.getBoundingClientRect().bottom <= button.getBoundingClientRect().top + 1;
    });
    expect(above, "the settings menu opened downwards").toBe(true);

    // A press outside puts it away again.
    await page
      .locator(".acts__list")
      .click({ position: { x: 5, y: 5 } })
      .catch(() => {});
    await expect(page.getByTestId("settings-menu")).toHaveCount(0);

    /*
     * 23. And the controller can use it (TECH_DEBT FB-12). The open menu is a
     *     modal to the ring: opening it puts the ring on its first item, no
     *     direction leaves it -- the scheme picker included, which used to have
     *     no stops at all -- and `B` (Escape is `B`) closes it and puts the
     *     ring back on the gear. Opened with the mouse here, because which
     *     direction reaches the gear from wherever the ring starts depends on
     *     the board; everything after the click is the keyboard's.
     */
    const ringAt = () =>
      page.evaluate(
        () => document.querySelector("[data-cursor]")?.getAttribute("data-stop") ?? null,
      );
    await page.getByTestId("settings").click();
    await expect(page.getByTestId("settings-menu")).toBeVisible();
    await expect.poll(ringAt).toBe("tool:mute");
    const walked = new Set<string>();
    for (const key of [
      "ArrowUp",
      "ArrowDown",
      "ArrowDown",
      "ArrowDown",
      "ArrowDown",
      "ArrowLeft",
    ]) {
      await page.keyboard.press(key);
      // The pad loop reads the key on its next frame; a wall changes nothing,
      // so there is no change to poll for -- wait the frames out instead.
      await page.evaluate(
        () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
      );
      const at = await ringAt();
      expect(at, `${key} took the ring out of the menu`).not.toBeNull();
      const inside = await page.evaluate(
        (stop) => document.querySelector(`.settings__menu [data-stop="${stop}"]`) !== null,
        at,
      );
      expect(inside, `${key} took the ring to ${at}, outside the menu`).toBe(true);
      walked.add(at as string);
    }
    expect([...walked].some((stop) => stop.startsWith("tool:scheme-"))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("settings-menu")).toHaveCount(0);
    await expect.poll(ringAt).toBe("tool:settings");

    // The speed selector used to be checked here too. It is gone: it took a
    // third of the strip's width, which is what pushed quit off the end, and a
    // per-player animation speed is a confusing thing to offer in a game other
    // people are waiting on. See `uiStore.ts`.
    await expect(page.locator("[data-speed]")).toHaveCount(0);
  });
});

// ------------------------------------------------------------------- styling

test.describe("panel styling", () => {
  test("keeps the selection colour off the panel itself", async ({ page }) => {
    // The regression this guards: `.combat` used to paint the whole panel amber,
    // which is the token meaning "staged". A signal spent on the container is a
    // signal the rows cannot use, and only a computed-colour check notices --
    // every assertion about content passes either way.
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    await waitForOurTurn(page);

    const tones = await page.evaluate(() => {
      const read = (selector: string) => {
        const node = document.querySelector(selector);
        if (!node) return null;
        const style = getComputedStyle(node);
        return { bg: style.backgroundColor, border: style.borderTopColor };
      };
      const probe = document.createElement("span");
      probe.style.color = getComputedStyle(document.documentElement)
        .getPropertyValue("--staged")
        .trim();
      document.body.append(probe);
      const staged = getComputedStyle(probe).color;
      probe.remove();
      return { acts: read(".acts"), stack: read(".stackpanel"), staged };
    });

    expect(tones.acts, "no action panel on screen").not.toBeNull();
    expect(tones.acts?.border).not.toBe(tones.staged);
    expect(tones.acts?.bg).not.toBe(tones.staged);
    // And it reads as the same furniture as the pane on the other rail.
    if (tones.stack) expect(tones.acts?.bg).toBe(tones.stack.bg);
  });

  test("gives the commit alternates a real outline", async ({ page }) => {
    // They were `.btn--ghost` -- transparent border, `--text-faint` -- so two of
    // the three answers to the question on screen rendered as bare text. They
    // are `.commit-mark` now, flanking the slab rather than sitting under it,
    // and the outline is still what says they are pressable.
    test.setTimeout(budget(600_000));
    await startGame(page, { ...COMBAT_SEED, opponents: 1 });
    await reachDeclaration(page, "attackers");

    const tone = await page.getByTestId("combat-all").evaluate((node) => {
      const style = getComputedStyle(node);
      return { border: style.borderTopColor, width: style.borderTopWidth };
    });
    expect(tone.border).not.toBe("rgba(0, 0, 0, 0)");
    expect(tone.border).not.toBe("transparent");
    expect(Number.parseFloat(tone.width)).toBeGreaterThan(0);
  });
});
