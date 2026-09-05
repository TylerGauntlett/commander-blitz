/**
 * Two people, two browsers, one server.
 *
 * This is the only spec that runs more than one browser context, and it is the
 * one that proves multiplayer at all. Two contexts means two `sessionStorage`
 * jars, which means two different players against one uvicorn -- exactly the
 * "one normal window and one private window" gate that `docs/api.md` describes
 * doing by hand.
 *
 * The three properties it exists for:
 *
 *   1. The guest's deck is **face-down to the host** until they lock in.
 *   2. Both browsers reach the table **from their own poll of the pod**, not
 *      because the host navigated and the guest was told.
 *   3. Each seat sees **only its own hand** once they are there.
 */

import { type BrowserContext, type Page, expect, test } from "@playwright/test";
import {
  actionsOfKind,
  budget,
  enabledActionButtons,
  openCatalog,
  setInstant,
  takeAction,
} from "./helpers";

/** One player's browser. */
async function open(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();
  await setInstant(page);
  return page;
}

/**
 * NOBODY SAYS WHO THEY ARE ANY MORE, and the seat says it for them.
 *
 * There was a `rename` helper here and a text field on your own plate behind
 * it. Typing a name with a controller is a virtual keyboard, a d-pad and about
 * twenty presses to replace "Player 1" with something nobody at the table
 * needs -- and it was the last text box on the pod, which made it the last
 * place a ring could get stuck. The server names each chair after its seat, so
 * these specs assert against those names instead.
 */

async function host(page: Page): Promise<string> {
  await page.goto("/");
  await page.getByTestId("create-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
  const code = await page.getByTestId("pod-code-chip").textContent();
  expect(code).toMatch(/^[A-Z]+-\d{4}$/);
  // The pod is an address, not a screen the app happens to be showing.
  await expect(page).toHaveURL(new RegExp(`/pods/${code}$`));
  return code as string;
}

/**
 * The code field is behind the Join card now, so joining is two presses: the
 * card opens the hold, the hold takes the code. `join-pod` is the card and
 * `join-go` is the confirm inside it, which is the split the front door's own
 * markup makes -- a suite that drives `join-pod` is starting a join, and one
 * that drives `join-go` is finishing one.
 */
async function join(page: Page, code: string): Promise<void> {
  await page.goto("/");
  await page.getByTestId("join-pod").click();
  await page.getByTestId("pod-code").fill(code);
  await page.getByTestId("join-go").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
}

async function pick(page: Page, deckId: string): Promise<void> {
  await page.getByTestId("change-deck").click();
  await page.getByTestId("deck-catalog").waitFor();
  await page.getByTestId(`deck-${deckId}-take`).click();
  await expect(page.getByTestId("deck-catalog")).toBeHidden();
}

test.describe("the row of four is a hand", () => {
  /**
   * The test that was missing when this shipped.
   *
   * `cards.css`'s `.card--big` promises "every enlarged card is the same size,
   * whatever is on it" -- but the promise is kept by the *container*, and the
   * lobby had none, so each card came out as tall as its own rules text. A
   * face-up seat and a face-down `.back` have to be the same rectangle or the
   * row stops reading as a hand.
   *
   * Width alone passes even with the bug: `.chair` has a definite width. Height
   * and top are the assertions that bite.
   */
  test("every seat is the same rectangle, face up or face down", async ({ page }) => {
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    // Seat 1 becomes a CPU with a deck of its own, so two different card faces
    // are up; seats 2 and 3 stay empty and are the `.back` control.
    await page.getByTestId("opponents-1").click();
    await pick(page, "aesi");
    await expect(page.getByTestId("seat-1-deck")).toBeVisible();

    const boxes = await page.locator(".chair__card").evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return {
          w: Math.round(rect.width),
          h: Math.round(rect.height),
          top: Math.round(rect.top),
        };
      }),
    );

    expect(boxes).toHaveLength(4);
    for (const box of boxes) {
      expect(box.w).toBe(boxes[0].w);
      expect(box.h).toBe(boxes[0].h);
      expect(box.top).toBe(boxes[0].top);
      expect(box.h / box.w).toBeCloseTo(1.4, 1);
    }
  });

  test("the dossier's card leaves room for the prose beside it", async ({ page }) => {
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await pick(page, "zurgo");
    await page.getByTestId("seat-0-card").click();
    await page.getByTestId("deck-dossier").waitFor();
    await expect(page.getByText(/How it plays/i)).toBeVisible();

    const overflow = await page
      .locator(".dos__body")
      .evaluate((node) => node.scrollWidth - node.clientWidth);
    expect(overflow, "the dossier scrolls sideways").toBeLessThanOrEqual(1);

    // The overflow check alone would also pass if the panel merely clipped.
    // This is the fact the panel exists for: the prose column got the room.
    const column = await page
      .locator(".dos__col")
      .evaluate((node) => node.getBoundingClientRect().width);
    expect(column).toBeGreaterThan(300);
  });
});

test.describe("a pod with two people in it", () => {
  test("the guest's deck stays face-down until they lock in", async ({ browser }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);

    // The host sees the guest arrive, without doing anything.
    await expect(hostPage.getByTestId("seat-1")).toHaveAttribute("data-kind", "human", {
      timeout: 20_000,
    });
    // `server/lobby.py:103` names a chair after its seat -- "Player 2" for
    // seat index 1 -- and nobody types over it any more.
    await expect(hostPage.getByTestId("seat-1").getByText("Player 2")).toBeVisible({
      timeout: 20_000,
    });

    // The guest picks a deck. The host must not learn which.
    await pick(guestPage, "edgar");
    await expect(guestPage.getByTestId("seat-1-deck")).toHaveText("Edgar Markov");
    await expect(hostPage.getByTestId("seat-1").getByTestId("card-back")).toBeVisible();
    await expect(hostPage.getByTestId("seat-1-deck")).toHaveCount(0);

    // They lock in, and now everybody may read it.
    await guestPage.getByTestId("lock-in").click();
    await expect(hostPage.getByTestId("seat-1-deck")).toHaveText("Edgar Markov", {
      timeout: 20_000,
    });
    await expect(hostPage.getByTestId("stamp-1")).toBeVisible();

    await hostContext.close();
    await guestContext.close();
  });

  test("the host cannot deal until everybody is stamped", async ({ browser }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);
    await pick(hostPage, "aesi");
    await hostPage.getByTestId("lock-in").click();

    // The guest has not chosen anything: the button is off and the rail says
    // whose fault that is.
    await expect(hostPage.getByTestId("start-game")).toBeDisabled();
    await expect(hostPage.getByTestId("why-not")).toContainText("Player 2", {
      timeout: 20_000,
    });

    await pick(guestPage, "edgar");
    await guestPage.getByTestId("lock-in").click();
    await expect(hostPage.getByTestId("start-game")).toBeEnabled({ timeout: 20_000 });

    await hostContext.close();
    await guestContext.close();
  });

  test("a guest sees no deal button at all", async ({ browser }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);

    await expect(guestPage.getByTestId("waiting-on-host")).toBeVisible();
    await expect(guestPage.getByTestId("start-game")).toHaveCount(0);
    // Nor any way to change the host's chair.
    await expect(guestPage.getByTestId("opponents-2")).toHaveCount(0);

    await hostContext.close();
    await guestContext.close();
  });

  test("both browsers land on the table, and each sees only its own hand", async ({
    browser,
  }) => {
    test.setTimeout(budget(180_000));
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);

    await pick(hostPage, "aesi");
    await pick(guestPage, "edgar");
    await guestPage.getByTestId("lock-in").click();
    await hostPage.getByTestId("lock-in").click();

    await expect(hostPage.getByTestId("start-game")).toBeEnabled({ timeout: 20_000 });
    await hostPage.getByTestId("start-game").click();

    // The host navigates because it dealt; the guest navigates because its own
    // poll of the pod came back with a game id. Nobody told it.
    await hostPage.getByTestId("table").waitFor({ timeout: 60_000 });
    await guestPage.getByTestId("table").waitFor({ timeout: 60_000 });

    // Both are at the game's own address, and neither can walk back into the
    // lobby they came from. That is the promise the deal makes by *replacing*
    // its history entry rather than pushing one: the pod is `in_game` and its
    // lobby cannot be re-entered, so back goes to the front door instead of to
    // a room that no longer exists.
    await expect(hostPage).toHaveURL(/\/games\/[^/]+$/);
    await expect(guestPage).toHaveURL(/\/games\/[^/]+$/);
    await hostPage.goBack();
    await expect(hostPage.getByTestId("new-game")).toHaveCount(0);
    await hostPage.goForward();
    await hostPage.getByTestId("table").waitFor({ timeout: 60_000 });

    // Each holds a hand, and neither can read the other's.
    for (const page of [hostPage, guestPage]) {
      await expect(page.locator(".hand .card").first()).toBeVisible({ timeout: 30_000 });
    }

    const hands = await Promise.all(
      [hostPage, guestPage].map(async (page) => {
        const names = await page
          .locator(".hand [data-card-name]")
          .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-card-name")));
        return names.filter(Boolean).sort();
      }),
    );

    expect(hands[0].length).toBeGreaterThan(0);
    expect(hands[1].length).toBeGreaterThan(0);
    // Two different decks, so an overlap would mean somebody is reading a hand
    // that is not theirs.
    expect(hands[0]).not.toEqual(hands[1]);

    await hostContext.close();
    await guestContext.close();
  });

  test("a refreshed tab lands back in the same seat with the same deck", async ({
    browser,
  }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);
    await pick(guestPage, "edgar");

    // `sessionStorage` survives a reload of the same tab, which is the whole
    // reconnect story: the token comes back and the seat is still theirs.
    // Nothing to click any more -- the pod's own address is enough, which is
    // what the address existing is for.
    await guestPage.goto(`/pods/${code}`);
    await guestPage.getByTestId("new-game").waitFor({ timeout: 15_000 });

    await expect(guestPage.getByTestId("seat-1")).toHaveAttribute("data-kind", "human");
    await expect(guestPage.getByTestId("seat-1-deck")).toHaveText("Edgar Markov");
    // And the pod still holds two people, not three.
    await expect(hostPage.getByTestId("seat-2")).toHaveAttribute("data-kind", "empty");

    await hostContext.close();
    await guestContext.close();
  });

  test("an invite link prefills the code", async ({ browser }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    // The invite link now *is* the pod's address. On a browser holding no token
    // for it there is no seat to open, so it lands at the door with the code
    // already in the field -- one click from the pod rather than none, because
    // taking a chair has to be something somebody did on purpose.
    await guestPage.goto(`/pods/${code}`);
    await expect(guestPage.getByTestId("pod-code")).toHaveValue(code);
    await expect(guestPage).toHaveURL(`/?join=${code}`);

    await hostContext.close();
    await guestContext.close();
  });

  test("the old query-param invite link still works", async ({ browser }) => {
    // `/?join=CODE` is what every link shared before the pods got addresses.
    // Nothing reissues those, so they keep working.
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    // An invite link has already asked the question the hold exists to ask, so
    // the hold opens itself with the code in it rather than making somebody
    // press a card to see what they already typed into their address bar.
    await guestPage.goto(`/?join=${code}`);
    await expect(guestPage.getByTestId("pod-code")).toHaveValue(code);
    await guestPage.getByTestId("join-go").click();
    await guestPage.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await expect(guestPage).toHaveURL(new RegExp(`/pods/${code}$`));

    await hostContext.close();
    await guestContext.close();
  });

  test("the invite dialog offers the pod's own address", async ({ page }) => {
    await setInstant(page);
    const code = await host(page);
    await page.getByTestId("invite").click();
    await expect(page.getByTestId("invite-link")).toContainText(`/pods/${code}`);
  });

  test("every chair is named by its seat, on both browsers", async ({ browser }) => {
    /*
     * The pod's names come from the server, one per chair, and nobody types
     * them. That is what makes the row readable with no input at all -- which
     * is the whole trade the name field lost.
     */
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);

    // Your own chair says "You" and everybody else's says who they are.
    // `exact` because the tag above the plate also says "you" -- "Seat 1 · you"
    // is what KIND of chair it is, and the plate says who is in it.
    await expect(
      hostPage.getByTestId("seat-0").getByText("You", { exact: true }),
    ).toBeVisible();
    await expect(hostPage.getByTestId("seat-1").getByText("Player 2")).toBeVisible({
      timeout: 20_000,
    });
    await expect(
      guestPage.getByTestId("seat-1").getByText("You", { exact: true }),
    ).toBeVisible();

    // And there is nothing to type into on either.
    await expect(hostPage.locator('[data-testid="new-game"] input')).toHaveCount(0);
    await expect(guestPage.locator('[data-testid="new-game"] input')).toHaveCount(0);

    await hostContext.close();
    await guestContext.close();
  });

  test("the front door does not ask for a name", async ({ page }) => {
    // Pins the removal: the mockup's door is two actions and a code field, and
    // this is the assertion that stops one creeping back in.
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("home").waitFor();
    await expect(page.getByTestId("player-name")).toHaveCount(0);
  });

  test("typing in the search box leaves the caret in it", async ({ page }) => {
    /*
     * A `fill()` would never have caught this, which is why the rest of the
     * suite did not: the bug lives between keystrokes.
     *
     * The ring re-derives itself after every commit -- that is what keeps it on
     * a card the engine has just replaced -- and a controlled input commits on
     * every character. So the resolve was re-focusing the first control on the
     * screen, and a word typed one letter at a time arrived as one letter, with
     * some other button wearing the ring.
     *
     * It was written against the pod's seed box and then its name box; both are
     * gone, for the same reason and to the pod's benefit. The catalogue's
     * search is the field the property is about now -- and it is a field worth
     * keeping, because filtering two dozen decks by typing three letters is
     * faster than any amount of walking.
     */
    await setInstant(page);
    await openCatalog(page);

    const search = page.getByTestId("deck-search");
    await search.click();
    await search.pressSequentially("edgar", { delay: 40 });

    await expect(search).toHaveValue("edgar");
    await expect(search).toBeFocused();
  });

  test("there is no seed field, and no other way to pin a deal", async ({ page }) => {
    /*
     * The control is gone rather than hidden. A player arriving to play a game
     * has no question a seed box answers, it stood between them and the Deal
     * button, and it was one of two text fields the ring could walk into and --
     * before `pad.ts:fieldKeeps` -- never walk out of.
     */
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });

    await expect(page.getByLabel("Seed")).toHaveCount(0);
    await expect(page.getByPlaceholder("random")).toHaveCount(0);
    // Not one field on the whole screen. The seed went because a reproducible
    // shuffle is a debugging tool; the name went because typing one with a
    // controller costs a minute and buys a label the server already writes.
    // Between them the pod is the first screen in the app with nothing on it a
    // ring can get stuck in.
    await expect(page.locator('[data-testid="new-game"] input')).toHaveCount(0);
  });

  test("the ring can walk out of a text field with the arrows alone", async ({ page }) => {
    /*
     * THE BUG THAT ENDED A HANDHELD SESSION.
     *
     * Off the board every stop is a native control, so the ring walks onto a
     * search box in the ordinary course of moving around -- and the old guard
     * gave a field every key it saw. A desktop has Tab; a Deck does not, and
     * Tab is swallowed anyway, so reaching the box was the end of the screen.
     *
     * Driven with real key events rather than `focus()` calls, because the
     * whole question is which listener sees the keydown first. `Down` rather
     * than a sideways press: a single-line field has nowhere below it, so Down
     * is always the ring's however the caret is placed.
     */
    const ring = () =>
      expect.poll(() =>
        page.evaluate(() =>
          document.querySelector("[data-cursor]")?.getAttribute("data-testid"),
        ),
      );

    await setInstant(page);
    await openCatalog(page);

    /*
     * Up out of the grid, through the filter strip, to the search box.
     *
     * A bounded walk rather than a fixed number of presses: the strip's height
     * depends on how many decks are installed and how they wrapped, and a spec
     * that counted presses would be asserting the layout rather than the
     * navigation. What it does pin is that the box is REACHABLE by pressing one
     * direction, which is the only thing a player will try.
     */
    for (let i = 0; i < 6; i += 1) {
      const at = await page.evaluate(() =>
        document.querySelector("[data-cursor]")?.getAttribute("data-testid"),
      );
      if (at === "deck-search") break;
      await page.keyboard.press("ArrowUp");
    }
    await ring().toBe("deck-search");

    // Left, with text behind the caret, is the caret's: the ring stays put.
    await page.keyboard.type("edgar");
    await page.keyboard.press("ArrowLeft");
    await ring().toBe("deck-search");

    // Down has nowhere to go inside one line, so it is the ring's.
    await page.keyboard.press("ArrowDown");
    await expect
      .poll(() =>
        page.evaluate(() =>
          document.querySelector("[data-cursor]")?.getAttribute("data-testid"),
        ),
      )
      .not.toBe("deck-search");
  });

  test("pressing a deck puts the ring back on the control that opened it", async ({ page }) => {
    /*
     * The one a player describes as "the pad doesn't work". Taking a deck
     * closed the catalogue, the cursor named a tile that no longer existed, and
     * the fallback -- the first stop of whatever is on top -- was the copy
     * button in the pod's header. Every A press that dismissed anything threw
     * the ring to the top-left corner.
     *
     * `keyboard.press` throughout, because the second half of the same defect
     * was that Enter activated twice: once natively on the focused control and
     * once through the ring. A mouse click could not see it.
     */
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });

    // No walk at all: the pod opens on the one decision it asks for.
    await expect(page.getByTestId("change-deck")).toHaveAttribute("data-cursor", "");
    await page.keyboard.press("Enter");

    // The catalogue opens on a deck rather than on its own way out.
    await page.getByTestId("deck-catalog").waitFor();
    await expect(page.getByTestId("deck-catalog-close")).not.toHaveAttribute("data-cursor", "");
    await expect(page.locator("[data-cursor]")).toHaveAttribute(
      "data-testid",
      /^deck-.+-take$/,
    );

    await page.keyboard.press("Enter");
    await expect(page.getByTestId("deck-catalog")).toBeHidden();
    // One press took one deck -- it did not also press whatever the ring
    // landed on next -- and the ring came home.
    await expect(page.getByTestId("seat-0-deck")).toBeVisible();
    await expect(page.getByTestId("change-deck")).toHaveAttribute("data-cursor", "");
  });

  test("the ring opens on the decision the screen is asking for", async ({ page }) => {
    /*
     * `resolveCursor` falls back to the first stop of whatever surface is on
     * top, which here is the bar's copy button -- so a player arriving with a
     * pad started on a clipboard convenience and had to walk past their own
     * name to reach the only thing the screen wants from them. The front door
     * makes the same argument about opening on Play: a menu whose default
     * selection is not its default action has picked the wrong default.
     */
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });

    await expect(page.getByTestId("change-deck")).toHaveAttribute("data-cursor", "");
  });

  test("the ring moves to Deal the moment dealing becomes possible", async ({ page }) => {
    /*
     * The pod is mostly a wait, and the moment it stops being one the thing
     * left to do changes under a ring that is standing somewhere else. Moving
     * it is the screen answering the question it has just finished asking.
     *
     * A nudge, not a pin: the pod commits about once a second while anybody is
     * choosing, and re-asserting the cursor on each of those would make the
     * rest of the screen unreachable for as long as the host hesitated. So it
     * fires on the transition, and walking away from it works.
     */
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await page.getByTestId("opponents-1").click();
    await pick(page, "aesi");

    await expect(page.getByTestId("start-game")).toBeDisabled();
    await page.getByTestId("lock-in").click();
    await expect(page.getByTestId("start-game")).toBeEnabled();
    await expect(page.getByTestId("start-game")).toHaveAttribute("data-cursor", "");

    // And it lets go: one press up leaves the rail for the row of chairs.
    await page.keyboard.press("ArrowUp");
    await expect(page.getByTestId("start-game")).not.toHaveAttribute("data-cursor", "");
  });

  test("the rail is one row: Lock in and Deal are neighbours", async ({ page }) => {
    /*
     * There is a thousand pixels of status between them and nothing focusable
     * in it, so `PERP` used to send Right from Lock in UP to the nearest
     * chair's button instead -- 195px sideways beat 1082px straight along the
     * row. Every toolbar in the app has that shape.
     *
     * Every step is a `poll` on where the ring IS rather than an assertion on
     * one element's attribute, and the difference is not style: a press is
     * handled on the pad's next animation frame, so a step that has not landed
     * yet and a step that landed somewhere wrong look identical to
     * `toHaveAttribute` and completely different here. It also makes the
     * failure say where the ring went, which is the whole question.
     */
    const ring = () =>
      expect.poll(() =>
        page.evaluate(() =>
          document.querySelector("[data-cursor]")?.getAttribute("data-testid"),
        ),
      );

    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await page.getByTestId("opponents-1").click();
    await pick(page, "aesi");
    await page.getByTestId("lock-in").click();
    await expect(page.getByTestId("start-game")).toBeEnabled();
    await ring().toBe("start-game");

    await page.keyboard.press("ArrowLeft");
    await ring().toBe("lock-in");
    await page.keyboard.press("ArrowRight");
    await ring().toBe("start-game");

    // And Up out of the rail is the row of chairs, not a slide along it.
    await page.keyboard.press("ArrowLeft");
    await ring().toBe("lock-in");
    await page.keyboard.press("ArrowUp");
    await ring().toBe("change-deck");
  });

  test("the dossier opens ON TOP of the catalogue it was launched from", async ({ page }) => {
    /*
     * `toBeVisible` cannot see this one, which is why it needs its own test.
     *
     * The catalogue became a full-bleed room and `room.css` stacks a room over
     * a room at 600 so it covers the pod behind it. The dossier's z-index was
     * 460, set when the catalogue was a panel -- so pressing the `i` on a tile
     * mounted the slide-out UNDERNEATH the grid it was launched from: in the
     * DOM, holding the ring, sized correctly, and completely invisible. Every
     * assertion anybody would think to write passed.
     *
     * So this asks the only question that fails: what is actually painted at
     * the point the panel occupies.
     */
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("create-pod").click();
    await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
    await page.getByTestId("change-deck").click();
    await page.getByTestId("deck-catalog").waitFor();

    await page.getByTestId("deck-edgar-info").click();
    const dossier = page.getByTestId("deck-dossier");
    await expect(dossier).toBeVisible();

    const onTop = await dossier.evaluate((panel) => {
      const box = panel.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return panel.contains(hit);
    });
    expect(onTop, "the catalogue is painted over the dossier").toBe(true);
  });

  test("a bad code says so rather than opening an empty pod", async ({ page }) => {
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("join-pod").click();
    await page.getByTestId("pod-code").fill("GYRE-0000");
    await page.getByTestId("join-go").click();
    // In the hold, where the press was, and the hold stays up: a rejected code
    // is a code to correct, and closing the panel to report it would take the
    // field away from somebody who has one character wrong.
    await expect(page.getByTestId("home-error")).toBeVisible();
    await expect(page.getByTestId("join-hold")).toBeVisible();
    await expect(page.getByTestId("home")).toBeVisible();
  });
});

/**
 * The turn actually changes hands.
 *
 * The test above proves both browsers *arrive*. This one proves they can play:
 * a decision taken in one browser shows up as the other browser's decision
 * without anybody reloading, in both directions and across a real end of turn.
 * Which seat goes first is the engine's choice, so the spec asks rather than
 * assumes.
 *
 * And the reload case, which is where the old listener showed itself. It sent
 * `?since=0` on every poll, so the first poll to land after a reload replayed
 * the whole game and doubled the log. The check is exact: the log a tab has
 * accumulated live must be the same length as the log a fresh load of the same
 * tab shows, because both are the same event list rendered once.
 */
test.describe("a turn changes hands", () => {
  test("play passes between two browsers without a reload, and a reload replays nothing", async ({
    browser,
  }) => {
    test.setTimeout(budget(300_000));
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage);
    await join(guestPage, code);
    await pick(hostPage, "aesi");
    await pick(guestPage, "edgar");
    await guestPage.getByTestId("lock-in").click();
    await hostPage.getByTestId("lock-in").click();
    await expect(hostPage.getByTestId("start-game")).toBeEnabled({ timeout: 20_000 });
    await hostPage.getByTestId("start-game").click();
    await hostPage.getByTestId("table").waitFor({ timeout: 60_000 });
    await guestPage.getByTestId("table").waitFor({ timeout: 60_000 });

    // The log is an overlay: Tab opens it, Escape closes it. Count and close,
    // so the panel is never sitting over a button the next step wants.
    const lines = async (page: Page) => {
      await page.keyboard.press("Tab");
      await page.getByTestId("log-overlay").waitFor({ timeout: 10_000 });
      const count = await page.getByTestId("event-log").locator(".ticker__line").count();
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("log-overlay")).toBeHidden();
      return count;
    };
    const up = async (page: Page) => (await enabledActionButtons(page).count()) > 0;

    // Seat 0 holds the first mulligan, and the guest is told so.
    const hostKeep = actionsOfKind(hostPage, "keep").first();
    await hostKeep.waitFor({ timeout: 30_000 });
    await expect(guestPage.getByTestId("waiting-on")).toBeVisible({ timeout: 30_000 });

    // Host -> guest: the host keeps and the guest's own question appears.
    await hostKeep.click();
    const guestKeep = actionsOfKind(guestPage, "keep").first();
    await guestKeep.waitFor({ timeout: 30_000 });
    await guestKeep.click();

    // Whoever the engine chose to go first is on the clock; the other waits.
    await expect
      .poll(async () => (await up(hostPage)) || (await up(guestPage)), { timeout: 60_000 })
      .toBe(true);
    const [active, waiting] = (await up(hostPage))
      ? [hostPage, guestPage]
      : [guestPage, hostPage];
    await expect(waiting.getByTestId("waiting-on")).toBeVisible();

    // A reload while somebody else is on the clock comes back with the same
    // log, not the log twice.
    await expect.poll(() => lines(waiting), { timeout: 30_000 }).toBeGreaterThan(0);
    const before = await lines(waiting);
    await waiting.reload();
    await waiting.getByTestId("table").waitFor({ timeout: 60_000 });
    await expect.poll(() => lines(waiting), { timeout: 30_000 }).toBe(before);

    // The active seat plays turn 1 out until the other has something to do.
    // That crosses the end of the turn, which is the hand-over this spec is for.
    let handedOver = false;
    for (let i = 0; i < 80 && !handedOver; i += 1) {
      handedOver = await up(waiting);
      if (handedOver) break;
      if (await up(active)) {
        await takeAction(active, ["play_land", "pass"]);
      } else {
        await active.waitForTimeout(250);
      }
    }
    expect(handedOver, "the turn was never handed over").toBe(true);

    // Everything the active seat did reached the reloaded tab through its
    // listener, exactly once: the live log is the length a fresh load says.
    const live = await lines(waiting);
    expect(live).toBeGreaterThan(before);
    await waiting.reload();
    await waiting.getByTestId("table").waitFor({ timeout: 60_000 });
    await expect.poll(() => lines(waiting), { timeout: 30_000 }).toBe(live);
    await expect.poll(() => up(waiting), { timeout: 30_000 }).toBe(true);

    // And back the other way once more: the first seat hears the second's move.
    const heard = await lines(active);
    await takeAction(waiting, ["play_land", "pass"]);
    await expect.poll(() => lines(active), { timeout: 30_000 }).toBeGreaterThan(heard);

    await hostContext.close();
    await guestContext.close();
  });
});
