/** TEMPORARY probe: is the attacker clipped at a block decision on this machine? Not for commit. */

import { test } from "@playwright/test";
import { keepOpeningHand, reachDeclaration, startGame } from "./helpers";

test("probe: the attacker's clipping ancestors at a block decision", async ({ page }) => {
  test.setTimeout(600_000);
  await startGame(page, { deck: "edgar", opponents: 1, seed: 3 });
  await keepOpeningHand(page);
  await reachDeclaration(page, "blockers");

  const report = await page.evaluate(() => {
    const lines: string[] = [];
    const html = document.documentElement;
    lines.push(
      `group=${html.dataset.group} input=${html.dataset.input} handheld=${html.dataset.handheld} viewport=${innerWidth}x${innerHeight}`,
    );
    lines.push(`cursor=${document.querySelector("[data-cursor]")?.getAttribute("data-stop")}`);
    lines.push(
      `fonts: ${getComputedStyle(document.body).fontFamily} | ready=${document.fonts.status}`,
    );
    const r = (b: DOMRect) =>
      `${Math.round(b.left)},${Math.round(b.top)} ${Math.round(b.width)}x${Math.round(b.height)}`;
    for (const card of document.querySelectorAll<HTMLElement>(".card--attacking")) {
      lines.push(
        `attacker ${card.dataset.oid} ${card.dataset.cardName} rect=${r(card.getBoundingClientRect())}`,
      );
      for (let a = card.parentElement; a; a = a.parentElement) {
        const s = getComputedStyle(a);
        const clips = ["hidden", "clip", "auto", "scroll", "overlay"];
        const clipping =
          clips.includes(s.overflowX) ||
          clips.includes(s.overflowY) ||
          clips.includes(s.overflow);
        const cls = a.className.toString().split(" ").slice(0, 2).join(".");
        if (clipping || /mat|seat|lane|play__/.test(cls)) {
          lines.push(
            `  ${clipping ? "CLIP" : "    "} ${cls} overflow=${s.overflow}/${s.overflowY} rect=${r(a.getBoundingClientRect())} h=${s.height} display=${s.display}`,
          );
        }
      }
    }
    const lanes = document.querySelectorAll<HTMLElement>(".mat--compact .lane");
    lines.push(
      `compact lanes: ${[...lanes].map((l) => r(l.getBoundingClientRect())).join(" ; ")}`,
    );
    return lines.join("\n");
  });
  console.log(report);
});
