/** TEMPORARY probe: why does Enter on a catalogue tile sometimes take nothing on the runner? Not for commit. */

import { expect, test } from "@playwright/test";
import { setInstant } from "./helpers";

test("probe: Enter on a deck tile", async ({ page }) => {
  const lines: string[] = [];
  const snap = (label: string) =>
    page.evaluate((l) => {
      const w = window as unknown as {
        __AUTOMTG_RING?: { cursor(): string | null; stops(): string[]; pad(): unknown };
      };
      const active = document.activeElement as HTMLElement | null;
      const pad = w.__AUTOMTG_RING?.pad
        ? JSON.stringify(w.__AUTOMTG_RING.pad()).slice(0, 220)
        : "?";
      return `${l}: t=${Math.round(performance.now())} input=${document.documentElement.dataset.input} cursor=${w.__AUTOMTG_RING?.cursor()} active=${active?.tagName}#${active?.dataset.testid ?? active?.className} catalog=${document.querySelector("[data-testid='deck-catalog']") !== null} stops=${w.__AUTOMTG_RING?.stops().length} pad=${pad}`;
    }, label);

  await setInstant(page);
  await page.goto("/");
  await page.getByTestId("create-pod").click();
  await page.getByTestId("new-game").waitFor({ timeout: 15_000 });
  await expect(page.getByTestId("change-deck")).toHaveAttribute("data-cursor", "");
  lines.push(await snap("before first Enter"));
  await page.keyboard.press("Enter");
  await page.getByTestId("deck-catalog").waitFor();
  lines.push(await snap("catalog open"));
  await expect(page.locator("[data-cursor]")).toHaveAttribute("data-testid", /^deck-.+-take$/);
  lines.push(await snap("cursor on tile"));
  await page.keyboard.press("Enter");
  for (const wait of [50, 200, 500, 1500]) {
    await page.waitForTimeout(wait);
    lines.push(await snap(`after second Enter +${wait}`));
  }
  const closed = await page.getByTestId("deck-catalog").count();
  lines.push(`catalog elements after: ${closed}`);
  console.log(lines.join("\n"));
});
