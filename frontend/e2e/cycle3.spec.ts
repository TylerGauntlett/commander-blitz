/**
 * The cycle-3 surfaces, driven in a real browser.
 *
 * Companion to `clarity.spec.ts` rather than a replacement: that file guards
 * what cycle 2 added, this one guards what cycle 3 added. Same principle --
 * assertions about *what is rendered*, never about pixels, because a screenshot
 * diff fails on every palette tweak and says nothing about whether the
 * information reached the player.
 *
 * See docs/playtest-feedback-02.md for what each of these is answering.
 */

import { type Page, expect, test } from "@playwright/test";
import {
  actionsOfKind,
  isOver,
  reachDecision,
  startGame,
  takeAction,
  waitForOurTurn,
} from "./helpers";

/** Play until `predicate` holds, or give up. Returns whether it held. */
async function playUntil(
  page: Page,
  predicate: () => Promise<boolean>,
  { limit = 200, prefer = ["keep", "play_land", "cast", "pass"] } = {},
): Promise<boolean> {
  for (let i = 0; i < limit; i += 1) {
    if (await predicate()) return true;
    await waitForOurTurn(page);
    if (await isOver(page)) return predicate();
    if (await predicate()) return true;
    await takeAction(page, prefer);
  }
  return predicate();
}

test.describe("a turn means a lap of the table", () => {
  test("the counter advances once for both seats, not once each", async ({ page }) => {
    // The complaint verbatim: "i take turn 1, opponent takes turn 2, my next
    // turn shows turn 3. This should be turn 2." The engine's own counter still
    // runs per player-turn -- summoning sickness needs it -- so this asserts the
    // two numbers exist side by side and that the *displayed* one is the round.
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();

    const counter = page.getByTestId("turn-counter");
    await expect(counter).toBeVisible();
    expect(await counter.getAttribute("data-round")).toBe("1");

    // Play on until the engine has taken at least four player-turns.
    await playUntil(page, async () => {
      const turn = Number(await counter.getAttribute("data-turn"));
      return turn >= 4;
    });

    const [turn, round] = await counter.evaluate((el) => [
      Number((el as HTMLElement).dataset.turn),
      Number((el as HTMLElement).dataset.round),
    ]);
    expect(turn).toBeGreaterThanOrEqual(4);
    // Two seats, so the round runs at half the player-turn count. Which seat
    // leads is randomised, so this pins the ratio rather than an exact formula:
    // before this cycle the two numbers were identical.
    expect(round, `turn=${turn} round=${round}`).toBeLessThan(turn);
    expect(Math.abs(round * 2 - turn), `turn=${turn} round=${round}`).toBeLessThanOrEqual(1);
    // And the number on screen is the round, not the engine's counter.
    await expect(counter.locator(".track__turn-n")).toHaveText(`T${round}`);
  });
});

test.describe("the commander is on screen", () => {
  test("the plinth shows the commander and can cast it", async ({ page }) => {
    // Cycle 2 left the command zone as a `CMD 1` chip opening a read-only modal,
    // and the only route to casting was a ghost button in the bar's overflow.
    // Then it was a ~74px card face in the bottom-left corner, whose own name
    // did not fit -- docs/mockup-fidelity.md defect #5.
    test.setTimeout(240_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    const dock = page.getByTestId("command-zone-0");
    await expect(dock).toBeVisible();
    // In the info panel, beside the life total -- not in a corner.
    await expect(page.getByTestId("player-0").locator(".cmdzone")).toBeVisible();
    // Named, not counted. And the name is whole: this is the assertion the old
    // card face could not have passed.
    const name = dock.locator(".cmdplinth__name").first();
    await expect(name).toBeVisible();
    await expect(name).not.toHaveText("");
    expect(
      await name.evaluate((n) => n.scrollWidth <= n.clientWidth + 1),
      "the commander's name is clipped again",
    ).toBe(true);

    const slot = dock.locator(".cmdslot").first();
    await expect(slot).toHaveAttribute("data-zone", "command");
    // State is said in words too, not only in the colour of the frame -- and the
    // word has to survive sharing its row with the cost pips. A narrower plinth
    // truncated this to "IN COMM…", which is not a channel.
    const word = slot.locator(".cmdplinth__word");
    await expect(word).toHaveText(/in command/i);
    expect(
      await word.evaluate((n) => n.scrollWidth <= n.clientWidth + 1),
      "the state word is clipped",
    ).toBe(true);

    // Ramp until the commander is affordable, then cast it from the plinth.
    const castable = await playUntil(
      page,
      async () => (await slot.getAttribute("data-castable")) === "true",
      { prefer: ["play_land", "cast", "pass"] },
    );
    test.skip(!castable, "never drew enough lands to cast the commander");

    await expect(slot).toHaveAttribute("data-cmd-state", "ready");
    await expect(slot.locator(".cmdplinth__word")).toHaveText(/ready/i);

    await slot.click();
    await waitForOurTurn(page);
    // It left the command zone: either on the battlefield, or on the stack and
    // about to be. Either way the plinth followed it rather than going blank.
    await expect(dock.locator(".cmdslot").first()).not.toHaveAttribute("data-zone", "command");
    await expect(dock.locator(".cmdslot").first()).toHaveAttribute(
      "data-cmd-state",
      "deployed",
    );
  });

  test("the plinth carries no action id, so the panel keeps sole ownership", async ({
    page,
  }) => {
    // It is a gesture surface like the hand. Giving it an id would put two
    // buttons on one action and break the invariant clarity.spec.ts guards.
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await expect(page.getByTestId("command-zone-0")).toBeVisible();
    expect(await page.locator("[data-testid^='command-zone-'] [data-action-id]").count()).toBe(
      0,
    );
  });
});

test.describe("lands say what they make", () => {
  test("a basic land carries its colour and drops its tap text", async ({ page }) => {
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    const lands = page.locator('.hand .face[data-type-tone="land"]');
    expect(await lands.count()).toBeGreaterThan(0);

    const classes = await lands.evaluateAll((nodes) =>
      nodes.map((n) => (n as HTMLElement).className),
    );
    // Every land is tinted by what it produces, not left on the shared tan.
    expect(classes.every((c) => /face--land-[WUBRGC]|face--land-multi/.test(c))).toBe(true);

    // And the watermark is there: the channel that reads at pod size. Read off
    // `data-symbol` rather than the text, because these are Scryfall's published
    // symbols drawn as images and an image has no letter to read.
    const pips = await lands
      .first()
      .locator(".watermark-pip")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).dataset.symbol ?? ""));
    expect(pips.length).toBeGreaterThan(0);
    expect(pips.every((p) => /^[WUBRGC]$/.test(p))).toBe(true);

    // No land shows a rules box whose entire content is its mana ability -- the
    // watermark says that better. A nonbasic that does something else keeps its
    // text, which is why this checks the content rather than counting boxes.
    const rules = await lands.locator(".face__rules").allTextContents();
    for (const text of rules) {
      expect(text.trim(), "a tap-for-mana line survived").not.toMatch(
        /^\{T\}:\s*Add\s*(\{[WUBRGC]\}\s*)+\.?$/,
      );
    }
  });

  test("two different basics do not look alike", async ({ page }) => {
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();

    // Play lands until the lane holds at least two, then check the tints differ
    // if the two lands do.
    const lane = page.locator('[data-testid^="lane-0-Lands"]');
    await playUntil(page, async () => (await lane.locator(".face").count()) >= 2, {
      prefer: ["play_land", "pass"],
    });

    const seen = await lane.locator(".face").evaluateAll((nodes) =>
      nodes.map((n) => ({
        name: (n as HTMLElement).dataset.cardName ?? "",
        tint:
          [...(n as HTMLElement).classList].find((c) => c.startsWith("face--land-")) ?? "none",
      })),
    );
    test.skip(seen.length < 2, "never got two lands onto the battlefield");
    for (const land of seen) {
      expect(land.tint, `${land.name} has no colour`).not.toBe("none");
    }
    // Same name implies same tint -- the encoding is a function of the card.
    const byName = new Map<string, string>();
    for (const { name, tint } of seen) {
      if (byName.has(name)) expect(byName.get(name)).toBe(tint);
      byName.set(name, tint);
    }
  });
});

test.describe("choosing a card shows the card", () => {
  test("prompt options render faces rather than bare names", async ({ page }) => {
    // The mulligan-bottom prompt names cards in a *hand*, and search/scry name
    // cards in a library -- which `player_view` sends as a count, so the client
    // had nothing to draw and fell back to a name-only button.
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });

    const dialog = page.getByTestId("prompt-dialog");
    const seen = await playUntil(
      page,
      async () => {
        if (!(await dialog.isVisible().catch(() => false))) return false;
        return (await dialog.locator(".opt--card").count()) > 0;
      },
      { prefer: ["mulligan", "play_land", "cast", "pass"], limit: 120 },
    );
    test.skip(!seen, "no card-choosing prompt came up in this game");

    // Every option that names an object is a face, and the face has a name on it.
    await expect(dialog.locator(".opt--card .face").first()).toBeVisible();
    const names = await dialog.locator(".opt--card .face__name").allTextContents();
    expect(names.length).toBeGreaterThan(0);
    expect(names.every((n) => n.trim().length > 0)).toBe(true);
  });
});

test.describe("combat has one surface", () => {
  test("the panel owns every combat action id", async ({ page }) => {
    // Cycle 2's item 1: "Done blocking" in the rail and "No blocks" in the panel,
    // the same underlying decision rendered twice because two surfaces both
    // claimed it. There is only one surface now -- `ActionPanel` is the action
    // bar as well as the combat panel -- so the question is no longer "did the
    // bar stand down" but "is every pair still reachable from the one place".
    //
    // Asserting it that way matters: the old version located a component that no
    // longer exists, which is a check that passes by finding nothing.
    test.setTimeout(600_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 3 });
    test.skip(
      !(await reachDecision(page, "attackers")),
      "never reached a declare-attackers decision",
    );

    const panel = page.getByTestId("combat-panel");
    expect(await panel.locator("[data-action-id]").count()).toBeGreaterThan(0);

    // Every declaration pair on the page is inside the panel, and nowhere else.
    const outside = await page.evaluate(() => {
      const panelEl = document.querySelector('[data-testid="combat-panel"]');
      return [...document.querySelectorAll("[data-action-kind]")]
        .filter((n) =>
          ["add_attacker", "add_blocker"].includes(n.getAttribute("data-action-kind") ?? ""),
        )
        .filter((n) => !panelEl?.contains(n))
        .map((n) => n.getAttribute("data-action-id"));
    });
    expect(outside, "a combat pair rendered outside the panel").toEqual([]);

    // The invariant clarity.spec.ts checks across a whole game, asserted here at
    // the exact moment it used to break.
    const ids = await page
      .locator("[data-action-id]")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).dataset.actionId ?? ""));
    expect(new Set(ids).size).toBe(ids.length);
    // And the decision is still reachable, which is why the exemption existed.
    expect(ids.length).toBeGreaterThan(0);
  });

  test("All attack stages every creature that can attack", async ({ page }) => {
    test.setTimeout(600_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 3 });
    test.skip(
      !(await reachDecision(page, "attackers")),
      "never reached a declare-attackers decision",
    );

    const panel = page.getByTestId("combat-panel");
    const all = page.getByTestId("combat-all");
    await expect(all).toBeEnabled();
    // One row per creature that can attack -- not one per legal *pair*, which is
    // what the chip cloud this replaced rendered. In a pod that was attackers
    // times opponents, and this count is the guard against it coming back.
    const candidates = await panel.locator(".acts__list .act[data-attacker]").count();
    expect(candidates).toBeGreaterThan(0);
    await all.click();

    // Staging is local, so this is immediate and nothing was posted. A staged
    // row says so on itself now -- there is no separate summary list to read.
    await expect(panel.locator('.act[data-staged="true"]')).toHaveCount(candidates);
    await expect(page.getByTestId("combat-confirm")).toBeEnabled();
    await expect(all).toBeDisabled();
  });

  test("All defend suggests blocks and never suggests a chump", async ({ page }) => {
    // The blocking half of the same idea, but ranked rather than exhaustive:
    // "block everything" is a way to lose a board.
    test.setTimeout(600_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 3 });

    const panel = page.getByTestId("combat-panel");
    let reached = false;
    for (let i = 0; i < 400 && !reached; i += 1) {
      await waitForOurTurn(page);
      if (await isOver(page)) break;
      if (await panel.isVisible().catch(() => false)) {
        const kind = await panel.getAttribute("data-combat-kind").catch(() => null);
        if (kind === "blockers" && (await actionsOfKind(page, "add_blocker").count())) {
          reached = true;
          break;
        }
      }
      // Decline to attack: a creature that attacked is tapped and cannot block,
      // and reaching a blocker decision is the whole point of this loop.
      await takeAction(page, ["keep", "play_land", "cast", "finish_declaration", "pass"]);
    }
    test.skip(!reached, "never reached a declare-blockers decision with a blocker");

    const all = page.getByTestId("combat-all");
    await expect(all).toHaveText(/All defend/);

    // The button is disabled precisely when every available block is a chump --
    // which is a real answer, not a broken button.
    if (!(await all.isEnabled())) return;

    await all.click();
    const stagedRows = panel.locator('.act[data-blocker][data-staged="true"]');
    const staged = await stagedRows.count();
    expect(staged).toBeGreaterThan(0);

    // One blocker to one attacker: no creature staged twice, no attacker ganged
    // up on by default.
    //
    // Read the oids off the row rather than splitting its label on " blocks ".
    // The old version did the latter and it was fragile in a way that failed
    // safe: any change to the wording made the uniqueness check pass for the
    // wrong reason, because both halves of a bad split are still distinct.
    const pairs = await stagedRows.evaluateAll((nodes) =>
      nodes.map((n) => ({
        blocker: n.getAttribute("data-blocker"),
        attacker: n.getAttribute("data-attacker"),
        tier: n.getAttribute("data-tier"),
      })),
    );
    expect(new Set(pairs.map((p) => p.blocker)).size).toBe(staged);
    expect(new Set(pairs.map((p) => p.attacker)).size).toBe(staged);
    // And never a chump: giving a creature away for nothing is a decision a
    // player makes when they are dying, not a default.
    expect(pairs.map((p) => p.tier)).not.toContain("4");
    await expect(page.getByTestId("combat-confirm")).toBeEnabled();
  });
});

test.describe("mana notation is drawn, not spelled", () => {
  test("rules text and action labels use the same pips as a cost row", async ({ page }) => {
    // A card's casting cost had been coloured pips since cycle 1, but rules text
    // and activation costs still read "{T}: Add {G}." -- two renderings of one
    // notation on one screen. See docs/playtest-feedback-02.md item 10.
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);

    // Rules text lives in the preview rail now, not on the hand card: at hand
    // size the box rendered at six pixels, so the cards went art-first and the
    // text moved to the one card big enough to read. So hover something first --
    // otherwise this looks for a surface that is deliberately not on screen.
    await page.locator(".hand .card").first().hover();
    await expect(page.getByTestId("card-preview").locator(".face__rules")).toBeVisible();

    // Nothing on screen may still be showing raw brace notation.
    const raw = await page.evaluate(() => {
      const hits: string[] = [];
      for (const node of document.querySelectorAll(".face__rules, .acts__list .act")) {
        const text = node.textContent ?? "";
        if (/\{[WUBRGCTQ0-9]+\}/.test(text)) hits.push(text.slice(0, 60));
      }
      return hits;
    });
    expect(raw, "mana notation is still being spelled out").toEqual([]);

    // And the pips are actually there, coloured by symbol.
    const tones = await page
      .locator(".face__rules .pip--inline, .acts__list .pip")
      .evaluateAll((nodes) =>
        nodes.flatMap((n) =>
          [...(n as HTMLElement).classList].filter(
            (c) => c.startsWith("pip--") && c !== "pip--inline",
          ),
        ),
      );
    expect(tones.length).toBeGreaterThan(0);

    // A pip is a pip, not a bar. `.pip` sizes itself off --card-w, and
    // `.face__rules` is a flex column -- get either wrong and every symbol
    // stretches to the width of the card. The tests above all still pass when
    // that happens, because the text is right and the classes are right.
    const shapes = await page.locator(".face__rules .pip--inline").evaluateAll((nodes) =>
      nodes.map((n) => {
        const box = (n as HTMLElement).getBoundingClientRect();
        return { w: box.width, h: box.height };
      }),
    );
    expect(shapes.length).toBeGreaterThan(0);
    for (const { w, h } of shapes) {
      expect(h).toBeGreaterThan(0);
      // Round-ish: a pip that has become a full-width lozenge fails this by a
      // factor of ten, so the bound is loose on purpose.
      expect(w / h, `a rules-text pip rendered ${w}x${h}`).toBeLessThan(2.5);
    }
  });

  test("every symbol is the real one, and it decoded", async ({ page }) => {
    // These were a letter on a CSS disc -- a `G` in a green circle, which is a
    // mark nobody who plays the game recognises. They are Scryfall's published
    // SVGs now, vendored into `public/symbols/`. A missing file is invisible in
    // the DOM and shows up only as a blank square, so check `naturalWidth`.
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();
    await waitForOurTurn(page);
    await page.locator(".hand .card").first().hover();
    await expect(page.getByTestId("card-preview").locator(".face__rules")).toBeVisible();

    const symbols = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLImageElement>("img.pip")].map((img) => ({
        src: new URL(img.src).pathname,
        code: img.dataset.symbol ?? "",
        decoded: img.naturalWidth > 0,
        // An image with no alt is a hole to a screen reader, and the notation is
        // the only thing it could sensibly say.
        alt: img.alt,
      })),
    );

    expect(symbols.length, "no real mana symbols on screen at all").toBeGreaterThan(0);
    for (const symbol of symbols) {
      // `{G/U}` lives in `G-U.svg`: a slash cannot be a filename on Windows, and
      // `symbolFile` makes the substitution on the way out. Asserting the code
      // verbatim passed only while no hybrid had ever rendered -- the orb's mana
      // panel draws one for every dual land, so it would have failed on the
      // first Simic source.
      expect(symbol.src).toBe(`/symbols/${symbol.code.replace("/", "-")}.svg`);
      expect(symbol.decoded, `${symbol.src} did not decode`).toBe(true);
      expect(symbol.alt).toBe(`{${symbol.code}}`);
    }

    // The fallback disc exists for symbols with no SVG. The engine rejects
    // hybrid and phyrexian at load time, so nothing in a real game should reach
    // it -- if this fires, `fetch_symbols.py`'s WANTED has fallen behind.
    const fallbacks = await page
      .locator(".pip--text")
      .evaluateAll((nodes) => nodes.map((n) => (n as HTMLElement).dataset.symbol ?? "?"));
    expect(fallbacks, "a symbol had no artwork to draw").toEqual([]);
  });
});

test.describe("the mana row answers what a spell costs", () => {
  test("hovering a castable card marks the mana it would tap", async ({ page }) => {
    test.setTimeout(180_000);
    await startGame(page, { deck: "aesi", opponents: 1, seed: 7 });
    const keep = actionsOfKind(page, "keep");
    if (await keep.count()) await keep.first().click();

    const row = page.getByTestId("mana-0");
    const ready = await playUntil(
      page,
      async () => {
        if (!(await row.isVisible().catch(() => false))) return false;
        return (await actionsOfKind(page, "cast").count()) > 0;
      },
      { prefer: ["play_land", "pass"], limit: 160 },
    );
    test.skip(!ready, "never reached a turn with mana and something to cast");

    expect(await row.getAttribute("data-spending")).toBe("0");

    // Hover each playable card until one forecasts a spend. A land is playable
    // and taps nothing, so "the first card that is not dimmed" would correctly
    // report zero and fail for the wrong reason.
    const playable = page.locator(".hand .card:not(.card--dimmed)");
    let spending = 0;
    for (let i = 0; i < (await playable.count()); i += 1) {
      await playable.nth(i).hover();
      spending = Number(await row.getAttribute("data-spending"));
      if (spending > 0) break;
    }
    expect(spending, "no playable card forecast a mana spend").toBeGreaterThan(0);

    // The forecast is the engine's solved payment, so it can never claim more
    // mana than the row is showing. Summed across the counted chips rather than
    // counted as elements: one chip stands for several mana and can be partly
    // spent, so `data-spent` is the number and the chip is not.
    const tally = await row.locator(".mana-grp").evaluateAll((nodes) =>
      nodes.reduce(
        (acc, n) => {
          const el = n as HTMLElement;
          acc.available += Number(el.dataset.count ?? "0");
          acc.spent += Number(el.dataset.spent ?? "0");
          return acc;
        },
        { available: 0, spent: 0 },
      ),
    );
    expect(spending).toBeLessThanOrEqual(tally.available);
    expect(tally.spent).toBe(spending);

    // And it goes away again, rather than sticking to the row.
    await page.getByTestId("phase-track").hover();
    await expect.poll(async () => await row.getAttribute("data-spending")).toBe("0");
  });
});

test.describe("a four-player pod fits", () => {
  test("opponent cards shrink with the pod, so three mats share the row", async ({ page }) => {
    test.setTimeout(180_000);

    // The pod is pinned to two decks, which is what this test measured when it
    // was written. `NewGameScreen` fills opponent seats by cycling whatever
    // `/api/decks` returns, so without this the *scenario* changes every time a
    // deck ships -- and a layout measurement that silently re-aims itself is
    // one that stops meaning anything.
    //
    // Pinning is not papering over a regression: the layout code is unchanged,
    // and a pod containing the token decks genuinely puts more permanents on an
    // opponent's mat than a 333px column holds. That is the content-sized-mat
    // limit already recorded in docs/roadmap.md, and the fix for it is the
    // fixed-lane-height work described there, not a looser number here.
    await page.route("**/api/decks", async (route) => {
      const response = await route.fetch();
      const decks = await response.json();
      return route.fulfill({
        json: decks.filter((deck: { id: string }) => ["aesi", "edgar"].includes(deck.id)),
      });
    });

    await startGame(page, { deck: "aesi", opponents: 3, seed: 5 });

    for (const pid of [1, 2, 3]) {
      await expect(page.getByTestId(`mat-${pid}`)).toBeVisible();
    }

    // Play a while so there is something in the lanes to measure.
    await playUntil(page, async () => false, {
      prefer: ["keep", "play_land", "cast", "pass"],
      limit: 60,
    });

    const measured = await page.evaluate(() => {
      const mats = [...document.querySelectorAll<HTMLElement>(".mat--compact")];
      // Read `--card-w` rather than measuring a card: a tapped permanent takes a
      // landscape footprint, so `getBoundingClientRect().width` is its *height*
      // and would report the wrong number depending on what happened to be
      // first in the lane.
      const lane = document.querySelector<HTMLElement>(".mat--compact .lane");
      const cardW = lane
        ? Number.parseFloat(getComputedStyle(lane).getPropertyValue("--card-w"))
        : 0;
      return {
        cardW,
        cardH: cardW * 1.4,
        overflow: mats
          .map((mat) => {
            const lanes = mat.querySelector<HTMLElement>(".mat__lanes");
            return lanes ? lanes.scrollHeight - lanes.clientHeight : 0;
          })
          .filter((slack) => slack > 4),
        // The row itself must never clip: a mat that outgrows it scrolls
        // internally rather than being cut off at the boundary.
        rowClipped: (() => {
          const row = document.querySelector<HTMLElement>(".play__opponents");
          return row ? row.scrollHeight - row.clientHeight > 4 : false;
        })(),
      };
    });

    // Cards are genuinely smaller than the 82px a duel uses -- the regression
    // guard on `opponentCardWidth`. At 82px three mats wrapped their lands onto
    // enough rows to hide most of a board.
    expect(measured.cardW).toBeGreaterThan(0);
    expect(measured.cardW).toBeLessThan(70);

    // A big enough board will still outgrow a 333px-wide mat -- there is no card
    // size that makes twelve permanents fit in a quarter of the screen. What is
    // asserted is that it never hides more than a partial row, and that the
    // scroll is inside the mat where the fade affordance shows it, rather than
    // the row clipping a card in half at its boundary.
    for (const slack of measured.overflow) {
      expect(slack, "an opponent mat is hiding more than one row").toBeLessThan(measured.cardH);
    }
    expect(measured.rowClipped, "the opponents row is clipping a mat").toBe(false);
  });
});
