import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import { decisionPrompt, describeEvent, stepLabel, turnLabel } from "../src/logic/labels";
import { gameView, player } from "./fixtures";

function event(overrides: Partial<GameEvent> = {}): GameEvent {
  return { type: "draw", turn: 1, step: 3, player: 0, source: null, data: {}, ...overrides };
}

describe("stepLabel", () => {
  it("renders friendly names", () => {
    expect(stepLabel("PRECOMBAT_MAIN")).toBe("Main 1");
    expect(stepLabel("DECLARE_BLOCKERS")).toBe("Declare blockers");
  });

  it("falls back to the raw name", () => {
    expect(stepLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });
});

describe("turnLabel", () => {
  it("names the active player and step", () => {
    expect(turnLabel(gameView())).toBe("Turn 1 - You - Main 1");
  });
});

describe("decisionPrompt", () => {
  it("reports the result once the game is over", () => {
    expect(decisionPrompt(gameView({ game_over: true, winners: [0] }))).toBe("You win!");
    expect(decisionPrompt(gameView({ game_over: true, winners: [1] }))).toBe("You lose.");
    expect(decisionPrompt(gameView({ game_over: true, winners: [] }))).toBe(
      "The game is a draw.",
    );
  });

  it("says who we are waiting on", () => {
    const state = gameView({
      players: [player(), player({ pid: 1, name: "AI 1" })],
      pending: {
        kind: "priority",
        player: 1,
        prompt: "",
        options: [],
        min_count: 1,
        max_count: 1,
        selected: [],
        allow_done: true,
        context: {},
      },
    });
    expect(decisionPrompt(state)).toBe("Waiting for AI 1...");
  });

  it("prefers the server's prompt", () => {
    const state = gameView({
      pending: {
        kind: "choose_objects",
        player: 0,
        prompt: "Sacrifice a creature",
        options: [],
        min_count: 1,
        max_count: 1,
        selected: [],
        allow_done: false,
        context: {},
      },
    });
    expect(decisionPrompt(state)).toBe("Sacrifice a creature");
  });
});

describe("describeEvent", () => {
  const names = ["You", "AI 1"];

  it("describes the events worth showing", () => {
    expect(describeEvent(event({ type: "draw" }), names)).toBe("You draws a card");
    expect(
      describeEvent(event({ type: "spell_cast", data: { card: "Counterspell" } }), names),
    ).toBe("You casts Counterspell");
    expect(
      describeEvent(event({ type: "player_lost", player: 1, data: { reason: "life" } }), names),
    ).toBe("AI 1 is eliminated (life)");
  });

  it("returns null for noise", () => {
    expect(describeEvent(event({ type: "step_ended" }), names)).toBeNull();
    expect(describeEvent(event({ type: "mana_added" }), names)).toBeNull();
  });
});
