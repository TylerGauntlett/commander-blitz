/** TEMPORARY probe: when does the ring settle after a block decision on this machine? Not for commit. */

import { test } from "@playwright/test";
import { keepOpeningHand, reachDeclaration, startGame } from "./helpers";

test("probe: the ring after a block decision, at 20ms", async ({ page }) => {
  test.setTimeout(600_000);
  const logs: string[] = [];
  page.on("console", (m) => {
    const text = m.text();
    if (text.startsWith("[placement]") || text.startsWith("[enterGroup]")) {
      logs.push(`${Date.now()} ${text}`);
    }
  });
  await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
  await keepOpeningHand(page);
  await reachDeclaration(page, "blockers");

  const lines: string[] = await page.evaluate(async () => {
    const out: string[] = [];
    const t0 = performance.now();
    let last = "";
    while (performance.now() - t0 < 2500) {
      const html = document.documentElement;
      const ring = (
        window as unknown as { __AUTOMTG_RING?: { stops(): string[]; cursor(): string } }
      ).__AUTOMTG_RING;
      const stops = ring?.stops() ?? [];
      const dialog = document.querySelector<HTMLElement>("[data-testid='prompt-dialog']");
      const actsStops = [
        ...document.querySelectorAll<HTMLElement>(".acts [data-stop], aside [data-stop]"),
      ]
        .map((el) => el.dataset.stop)
        .slice(0, 4);
      const snap = `group=${html.dataset.group} cursor=${document.querySelector("[data-cursor]")?.getAttribute("data-stop")} ring=${ring?.cursor()} dialog=${dialog ? (dialog.dataset.closing ? "closing" : "open") : "none"} stops=${stops.length}:${stops.slice(0, 3).join(",")} acts=${actsStops.join(",")}`;
      if (snap !== last) out.push(`${Math.round(performance.now() - t0)}ms ${snap}`);
      last = snap;
      await new Promise((r) => setTimeout(r, 20));
    }
    return out;
  });
  console.log(["probe-start", ...lines, "--- app logs ---", ...logs.slice(-12)].join("\n"));
});
