import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PendingDecision } from "../src/api/types";
import { ActionBar } from "../src/components/game/ActionBar";
import { CardFace } from "../src/components/game/CardFace";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { action, card, gameView } from "./fixtures";

afterEach(cleanup);

const noop = () => undefined;

function pending(overrides: Partial<PendingDecision> = {}): PendingDecision {
  return {
    kind: "priority",
    player: 0,
    prompt: "",
    options: [],
    min_count: 1,
    max_count: 1,
    selected: [],
    allow_done: true,
    context: {},
    ...overrides,
  };
}

describe("CardFace", () => {
  it("renders the name, type line and mana pips", () => {
    render(<CardFace card={card({ name: "Grizzly Bears", mana_cost: "{1}{G}" })} />);
    expect(screen.getByText("Grizzly Bears")).toBeTruthy();
    expect(screen.getByText("Creature - Bear")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText("G")).toBeTruthy();
  });

  it("subtracts marked damage from toughness on the battlefield", () => {
    render(<CardFace card={card({ power: 4, toughness: 5, damage: 2 })} />);
    expect(screen.getByText("4/3")).toBeTruthy();
  });

  it("shows printed toughness outside the battlefield", () => {
    render(<CardFace card={card({ zone: "hand", power: 4, toughness: 5, damage: 0 })} />);
    expect(screen.getByText("4/5")).toBeTruthy();
  });

  it("shows oracle text only in detail mode", () => {
    const bear = card({ oracle_text: "Trample. Draw a card." });
    const { unmount } = render(<CardFace card={bear} />);
    expect(screen.queryByText("Trample. Draw a card.")).toBeNull();
    unmount();
    render(<CardFace card={bear} detail />);
    expect(screen.getByText("Trample. Draw a card.")).toBeTruthy();
  });

  it("shows keywords on the compact face, where rules text does not fit", () => {
    render(<CardFace card={card({ keywords: ["flying", "first_strike"] })} />);
    expect(screen.getByText("Flying · First strike")).toBeTruthy();
  });

  it("tags a commander", () => {
    render(<CardFace card={card({ is_commander: true })} />);
    expect(screen.getByText("CMD")).toBeTruthy();
  });

  it("renders counters as badges", () => {
    render(<CardFace card={card({ counters: { "+1/+1": 3 } })} />);
    expect(screen.getByText("+1/+1 x3")).toBeTruthy();
  });
});

describe("ActionBar", () => {
  const base = {
    onUndo: noop,
    onQuit: noop,
    onSkip: noop,
    narrating: false,
    busy: false,
    aiThinking: false,
  };

  it("renders one button per legal action", () => {
    const actions = [
      action({ id: "a0-pass", kind: "pass", label: "Pass" }),
      action({ id: "a1-cast", kind: "cast", label: "Cast Bear" }),
      action({ id: "a2-play_land", kind: "play_land", label: "Play Forest" }),
    ];
    render(<ActionBar state={gameView()} actions={actions} onAct={noop} {...base} />);
    for (const a of actions) {
      expect(document.querySelector(`[data-action-id="${a.id}"]`)).toBeTruthy();
    }
  });

  it("submits the action id it was given, not a reconstructed action", () => {
    const onAct = vi.fn();
    render(
      <ActionBar
        state={gameView()}
        actions={[action({ id: "a7-cast", kind: "cast", label: "Cast" })]}
        onAct={onAct}
        {...base}
      />,
    );
    fireEvent.click(screen.getByText("Cast"));
    expect(onAct).toHaveBeenCalledWith("a7-cast");
  });

  it("gates every action while narration is playing", () => {
    render(
      <ActionBar
        state={gameView()}
        actions={[action({ label: "Pass" })]}
        onAct={noop}
        {...base}
        narrating
      />,
    );
    expect(screen.getByText("Pass").hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Skip/)).toBeTruthy();
  });

  it("says who it is waiting for", () => {
    const state = gameView({ pending: pending({ player: 1 }) });
    render(<ActionBar state={state} actions={[]} onAct={noop} {...base} />);
    expect(screen.getByTestId("prompt").textContent).toContain("Waiting for AI 1");
  });
});

describe("PromptDialog", () => {
  const shown = (kind: string, extra: Partial<PendingDecision> = {}) =>
    gameView({ pending: pending({ kind, prompt: `Prompt for ${kind}`, ...extra }) });

  it("opens for a mulligan and submits the chosen action", () => {
    const onAct = vi.fn();
    render(
      <PromptDialog
        state={shown("mulligan")}
        actions={[
          action({ id: "a0-mulligan", kind: "mulligan", label: "Mulligan" }),
          action({ id: "a1-keep", kind: "keep", label: "Keep" }),
        ]}
        onAct={onAct}
        disabled={false}
      />,
    );
    expect(screen.getByTestId("prompt-dialog").dataset.decisionKind).toBe("mulligan");
    fireEvent.click(screen.getByText("Keep"));
    expect(onAct).toHaveBeenCalledWith("a1-keep");
  });

  it.each([
    "discard_to_hand_size",
    "choose_objects",
    "choose_mode",
    "may",
    "choose_player",
    "commander_zone_change",
  ])("handles the %s decision", (kind) => {
    render(
      <PromptDialog
        state={shown(kind)}
        actions={[action({ id: "a0-choose", kind: "choose", label: "Option A" })]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.getByTestId("prompt-dialog").dataset.decisionKind).toBe(kind);
    expect(screen.getByText("Option A")).toBeTruthy();
  });

  it("stays shut for priority and combat, which have their own surfaces", () => {
    for (const kind of ["priority", "declare_attackers", "declare_blockers"]) {
      const { unmount } = render(
        <PromptDialog state={shown(kind)} actions={[action()]} onAct={noop} disabled={false} />,
      );
      expect(screen.queryByTestId("prompt-dialog")).toBeNull();
      unmount();
    }
  });

  it("stays shut when the decision belongs to somebody else", () => {
    render(
      <PromptDialog
        state={shown("choose_objects", { player: 1 })}
        actions={[action()]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("prompt-dialog")).toBeNull();
  });

  it("draws an option that refers to a permanent as a real card", () => {
    const state = gameView({
      pending: pending({ kind: "choose_objects", prompt: "Sacrifice a creature" }),
      battlefield: [card({ oid: 55, name: "Doomed Traveler" })],
    });
    render(
      <PromptDialog
        state={state}
        actions={[
          action({
            id: "a0-choose",
            kind: "choose",
            label: "Doomed Traveler",
            targets: [{ kind: "object", id: 55 }],
          }),
        ]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(document.querySelector('[data-card-name="Doomed Traveler"]')).toBeTruthy();
  });

  it("shows the range when several things must be chosen", () => {
    render(
      <PromptDialog
        state={shown("choose_objects", { min_count: 1, max_count: 3 })}
        actions={[action({ kind: "choose", label: "A" })]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.getByText(/1–3/)).toBeTruthy();
  });
});
