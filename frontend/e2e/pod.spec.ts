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
import { setInstant } from "./helpers";

/** One player's browser. */
async function open(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();
  await setInstant(page);
  return page;
}

async function host(page: Page, name: string): Promise<string> {
  await page.goto("/");
  await page.getByTestId("player-name").fill(name);
  await page.getByTestId("create-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
  const code = await page.getByTestId("pod-code-chip").textContent();
  expect(code).toMatch(/^[A-Z]+-\d{4}$/);
  return code as string;
}

async function join(page: Page, code: string, name: string): Promise<void> {
  await page.goto("/");
  await page.getByTestId("player-name").fill(name);
  await page.getByTestId("pod-code").fill(code);
  await page.getByTestId("join-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
}

async function pick(page: Page, deckId: string): Promise<void> {
  await page.getByTestId("change-deck").click();
  await page.getByTestId("deck-catalog").waitFor();
  await page.getByTestId(`deck-${deckId}`).locator(".pick__card").click();
  await expect(page.getByTestId("deck-catalog")).toBeHidden();
}

test.describe("a pod with two people in it", () => {
  test("the guest's deck stays face-down until they lock in", async ({ browser }) => {
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage, "Tyler");
    await join(guestPage, code, "Priya");

    // The host sees the guest arrive, without doing anything.
    await expect(hostPage.getByTestId("seat-1")).toHaveAttribute("data-kind", "human", {
      timeout: 20_000,
    });
    await expect(hostPage.getByTestId("seat-1").getByText("Priya")).toBeVisible();

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

    const code = await host(hostPage, "Tyler");
    await join(guestPage, code, "Priya");
    await pick(hostPage, "aesi");
    await hostPage.getByTestId("lock-in").click();

    // The guest has not chosen anything: the button is off and the rail says
    // whose fault that is.
    await expect(hostPage.getByTestId("start-game")).toBeDisabled();
    await expect(hostPage.getByTestId("why-not")).toContainText("Priya", {
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

    const code = await host(hostPage, "Tyler");
    await join(guestPage, code, "Priya");

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
    test.setTimeout(180_000);
    const hostContext = await browser.newContext();
    const guestContext = await browser.newContext();
    const hostPage = await open(hostContext);
    const guestPage = await open(guestContext);

    const code = await host(hostPage, "Tyler");
    await join(guestPage, code, "Priya");

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

    const code = await host(hostPage, "Tyler");
    await join(guestPage, code, "Priya");
    await pick(guestPage, "edgar");

    // `sessionStorage` survives a reload of the same tab, which is the whole
    // reconnect story: the token comes back and the seat is still theirs.
    await guestPage.goto(`/?join=${code}`);
    await guestPage.getByTestId("join-pod").click();
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

    const code = await host(hostPage, "Tyler");
    await guestPage.goto(`/?join=${code}`);
    await expect(guestPage.getByTestId("pod-code")).toHaveValue(code);

    await hostContext.close();
    await guestContext.close();
  });

  test("a bad code says so rather than opening an empty pod", async ({ page }) => {
    await setInstant(page);
    await page.goto("/");
    await page.getByTestId("pod-code").fill("GYRE-0000");
    await page.getByTestId("join-pod").click();
    await expect(page.getByTestId("home-error")).toBeVisible();
    await expect(page.getByTestId("home")).toBeVisible();
  });
});
