import { describe, expect, it } from "vitest";
import type { GameEvent } from "../src/api/types";
import {
  decisionPrompt,
  describeEvent,
  exitPhrase,
  stepLabel,
  turnLabel,
} from "../src/logic/labels";
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
    // Loss reasons arrive as engine enum values; the log spells them out.
    expect(
      describeEvent(event({ type: "player_lost", player: 1, data: { reason: "life" } }), names),
    ).toBe("AI 1 is eliminated (life total hit zero)");
    expect(
      describeEvent(
        event({ type: "player_lost", player: 1, data: { reason: "commander_damage" } }),
        names,
      ),
    ).toBe("AI 1 is eliminated (21 commander damage)");
  });

  it("narrates the crown changing hands", () => {
    // A new engine event is silently dropped by the `default` fallthrough, and
    // nothing else in the log would say the monarch moved: no permanent changes
    // zones and no stat changes. The consequence is invisible too -- the monarch
    // draws at every one of their end steps -- so a player who did not notice
    // losing it just sees their opponent quietly drawing more cards.
    expect(describeEvent(event({ type: "became_monarch", player: 0 }), names, 0)).toBe(
      "You become the monarch",
    );
    expect(describeEvent(event({ type: "became_monarch", player: 1 }), names, 0)).toBe(
      "AI 1 becomes the monarch",
    );
  });

  it("prettifies a card id rather than printing the raw slug", () => {
    expect(
      describeEvent(event({ type: "land_played", data: { card: "sol_ring" } }), names),
    ).toBe("You plays Sol Ring");
  });

  it("uses second-person verbs for the viewer's own seat", () => {
    expect(describeEvent(event({ type: "draw", player: 0 }), names, 0)).toBe("You draw a card");
    expect(describeEvent(event({ type: "draw", player: 1 }), names, 0)).toBe(
      "AI 1 draws a card",
    );
    expect(
      describeEvent(event({ type: "life_lost", player: 0, data: { amount: 3 } }), names, 0),
    ).toBe("You lose 3 life");
  });

  it("returns null for noise", () => {
    expect(describeEvent(event({ type: "step_ended" }), names)).toBeNull();
    expect(describeEvent(event({ type: "mana_added" }), names)).toBeNull();
  });
});

describe("exitPhrase", () => {
  it("supplies each cause its own preposition", () => {
    // Not one blanket " by ": a creature is destroyed *by* a spell but
    // sacrificed *to* an outlet, and the wrong one reverses who wanted it.
    expect(exitPhrase("destroyed", "Vandalblast")).toBe("Destroyed by Vandalblast");
    expect(exitPhrase("sacrificed", "Ashnod's Altar")).toBe("Sacrificed to Ashnod's Altar");
    expect(exitPhrase("lethal_damage", "Ulamog")).toBe("Killed by Ulamog");
    expect(exitPhrase("cost", "Krark-Clan Ironworks")).toBe(
      "Paid as a cost for Krark-Clan Ironworks",
    );
  });

  it("falls back to a plain form when the engine named nobody", () => {
    // A gang block, where naming one of three blockers would be a lie.
    expect(exitPhrase("lethal_damage", null)).toBe("Lethal damage");
    expect(exitPhrase("destroyed", null)).toBe("Destroyed");
  });

  it("has a plain-only form for the causes with no possible culprit", () => {
    expect(exitPhrase("legend_rule", null)).toBe("Legend rule");
    expect(exitPhrase("zero_toughness", null)).toBe("Toughness reduced to 0");
    expect(exitPhrase("aura_unattached", null)).toBe("Nothing left to enchant");
  });

  it("adds the commander redirect as a rider, not as a replacement", () => {
    // Rule 903.9a changes the destination and leaves the cause alone, so the
    // line has to carry both halves or it loses the reason it left.
    expect(exitPhrase("destroyed", "Swords to Plowshares", "command")).toBe(
      "Destroyed by Swords to Plowshares — to the command zone",
    );
  });

  it("humanises a cause it has never heard of", () => {
    expect(exitPhrase("some_new_cause", null)).toBe("Some new cause");
  });
});

describe("describeEvent on zone changes", () => {
  const names = ["You", "AI 1"];
  const exit = (data: Record<string, unknown>, lookup?: (id: string) => string | undefined) =>
    describeEvent(event({ type: "zone_change", player: 1, data }), names, 0, lookup);

  const KILL = {
    card: "grizzly_bears",
    from: "battlefield",
    to: "graveyard",
    cause: "destroyed",
    by_card: "swords_to_plowshares",
  };

  it("names the card and why it left", () => {
    expect(exit(KILL)).toBe("Grizzly Bears — Destroyed by Swords To Plowshares");
  });

  it("uses the printed name for the culprit when one is known", () => {
    // The culprit goes through the same `card_id -> name` lookup the victim
    // does, which is what the fallback above cannot get right: prettifying
    // capitalises every word, and no card is called "Swords To Plowshares".
    const printed = { swords_to_plowshares: "Swords to Plowshares" } as Record<string, string>;
    expect(exit(KILL, (id) => printed[id])).toBe(
      "Grizzly Bears — Destroyed by Swords to Plowshares",
    );
  });

  it("stays silent about every zone change that did not start on the battlefield", () => {
    // The load-bearing negative. Without it the log gains a second line for
    // every draw, mill, discard and resolution -- and a library-origin zone
    // change carries a card id to every seat, so narrating one would put an
    // opponent's tutor target in the log.
    expect(exit({ card: "forest", from: "library", to: "hand", cause: "search" })).toBeNull();
    expect(
      exit({ card: "brainstorm", from: "stack", to: "graveyard", cause: "resolved" }),
    ).toBe(null);
    expect(exit({ card: "island", from: "library", to: "hand", cause: "draw" })).toBeNull();
  });

  it("no longer has a `dies` line, which would double every death", () => {
    // `move_object` emits the zone change and fires `dies` together, and only
    // the zone change knows the destination and the cause.
    expect(describeEvent(event({ type: "dies", data: { card: "grizzly_bears" } }), names)).toBe(
      null,
    );
  });
});
