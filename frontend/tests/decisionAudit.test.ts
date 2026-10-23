/**
 * The shape of the selection audit.
 *
 * `tests/unit/choices/test_decision_audit.py` holds the table to the engine:
 * every decision kind and every purpose tag has a row. This holds the half the
 * engine cannot see -- that the ceilings and the journeys agree with each
 * other and with the stories that measure them:
 *
 * - a row never names a journey that has no ceiling, and a ceiling is never
 *   left unspent by every row, because a number nothing is held to is a number
 *   that will quietly stop being true;
 * - every ceiling is the name of a story in `Journeys.stories.tsx`, so a
 *   reader can find the walk behind the number -- the e2e journey reuses a
 *   story's name and ceiling rather than minting its own;
 * - the derived rule keeps the panel under every table pick (ADR 0015), and a
 *   row the engine never raises claims no journey.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  BUDGET,
  ceiling,
  DECISION_AUDIT,
  type JourneyName,
  ruleOf,
} from "../src/components/game/decisionAudit";

const STORIES = readFileSync(
  join(__dirname, "..", "src", "components", "game", "Journeys.stories.tsx"),
  "utf-8",
);

const journeys = Object.keys(BUDGET) as JourneyName[];

describe("the ceilings", () => {
  it("are whole presses, at least one", () => {
    for (const journey of journeys) {
      expect(Number.isInteger(ceiling(journey)), journey).toBe(true);
      expect(ceiling(journey), journey).toBeGreaterThanOrEqual(1);
    }
  });

  it("are each spent by at least one row", () => {
    const spent = new Set(DECISION_AUDIT.flatMap((row) => row.journeys));
    const idle = journeys.filter((journey) => !spent.has(journey));
    expect(idle, "ceilings no row is held to").toEqual([]);
  });

  it("each name a story that measures them", () => {
    const unmeasured = journeys.filter(
      (journey) => !new RegExp(`^export const ${journey}: Story`, "m").test(STORIES),
    );
    expect(unmeasured, "ceilings with no story of that name").toEqual([]);
  });
});

describe("the rows", () => {
  it("are one per question", () => {
    const keys = DECISION_AUDIT.map((row) => `${row.kind}:${row.purpose}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("keep the panel under every pick of a thing on the table", () => {
    for (const row of DECISION_AUDIT) {
      const rule = ruleOf(row);
      if (row.of === "table" || row.of === "players" || row.of === "actions") {
        expect(rule, `${row.kind}/${row.purpose}`).toEqual(["board", "panel"]);
      }
      expect(
        rule.length,
        `${row.kind}/${row.purpose} has no surface under the rule`,
      ).toBeGreaterThan(0);
    }
  });

  it("hold a journey for everything that is answered, and none for what is not", () => {
    for (const row of DECISION_AUDIT) {
      const label = `${row.kind}/${row.purpose}`;
      if (row.today.length === 0) {
        expect(row.journeys, `${label} is raised by nothing and cannot be walked`).toEqual([]);
      } else {
        expect(
          row.journeys.length,
          `${label} is answered but held to no ceiling`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("say a kind is raised by nothing only in every one of its rows", () => {
    // A kind's rows agree about whether the engine asks it at all: one row
    // with surfaces and another with none would be two claims about one enum
    // value.
    const byKind = new Map<string, boolean[]>();
    for (const row of DECISION_AUDIT) {
      byKind.set(row.kind, [...(byKind.get(row.kind) ?? []), row.today.length > 0]);
    }
    for (const [kind, answered] of byKind) {
      expect(new Set(answered).size, `${kind} both is and is not raised`).toBe(1);
    }
  });
});
