import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PendingDecision } from "../src/api/types";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { CardFace } from "../src/components/game/CardFace";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { action, card, gameView, pending, player } from "./fixtures";

afterEach(cleanup);

const noop = () => undefined;

describe("CardFace", () => {
  it("renders the name, type line and mana symbols", () => {
    const { container } = render(
      <CardFace card={card({ name: "Grizzly Bears", mana_cost: "{1}{G}" })} />,
    );
    expect(screen.getByText("Grizzly Bears")).toBeTruthy();
    expect(screen.getByText("Creature - Bear")).toBeTruthy();
    // The cost is Scryfall's real symbols now, not a letter on a disc, so it has
    // no text to query -- `data-symbol` is what carries the code. Order matters:
    // "{1}{G}" is not the same cost as "{G}{1}" to read, even though it is to pay.
    expect(
      [...container.querySelectorAll(".face__cost .pip")].map((n) =>
        n.getAttribute("data-symbol"),
      ),
    ).toEqual(["1", "G"]);
  });

  it("draws each mana symbol as its published artwork", () => {
    // The point of the swap: a `G` in a green circle is a mark nobody who plays
    // the game recognises.
    const { container } = render(<CardFace card={card({ mana_cost: "{2}{U}" })} />);
    const sources = [...container.querySelectorAll<HTMLImageElement>(".face__cost img")].map(
      (img) => img.getAttribute("src"),
    );
    expect(sources).toEqual(["/symbols/2.svg", "/symbols/U.svg"]);
  });

  it("subtracts marked damage from toughness on the battlefield", () => {
    render(<CardFace card={card({ power: 4, toughness: 5, damage: 2 })} />);
    expect(screen.getByText("4/3")).toBeTruthy();
  });

  it("shows printed toughness outside the battlefield", () => {
    render(<CardFace card={card({ zone: "hand", power: 4, toughness: 5, damage: 0 })} />);
    expect(screen.getByText("4/5")).toBeTruthy();
  });

  it("shows oracle text only where there is room for it", () => {
    const bear = card({ oracle_text: "Trample. Draw a card." });
    const { unmount } = render(<CardFace card={bear} />);
    expect(screen.queryByText("Trample. Draw a card.")).toBeNull();
    unmount();
    render(<CardFace card={bear} variant="detail" />);
    expect(screen.getByText("Trample. Draw a card.")).toBeTruthy();
  });

  it("shows keywords on the compact face, where rules text does not fit", () => {
    render(<CardFace card={card({ keywords: ["flying", "first_strike"] })} />);
    expect(screen.getByText("Flying · First strike")).toBeTruthy();
  });

  it("crowns a commander, inside the name", () => {
    // It was a `CMD` badge pinned to a corner, which at pod size rendered at
    // under 3px. The crown scales with the name because it is part of it.
    const { container } = render(<CardFace card={card({ is_commander: true })} />);
    expect(container.querySelector(".face__name .crown")).not.toBeNull();
    expect(container.querySelector(".crown")?.getAttribute("data-hint")).toBe("Commander");
  });

  it("crowns nothing else", () => {
    const { container } = render(<CardFace card={card({ is_commander: false })} />);
    expect(container.querySelector(".crown")).toBeNull();
  });

  it("renders counters as badges", () => {
    render(<CardFace card={card({ counters: { "+1/+1": 3 } })} />);
    expect(screen.getByText("+1/+1 x3")).toBeTruthy();
  });
});

describe("ActionPanel", () => {
  const base = {
    onStage: noop,
    onDeclare: noop,
    onUndo: noop,
    onQuit: noop,
    onSkipNarration: noop,
    narrating: false,
    busy: false,
    aiThinking: false,
    onToggleFullControl: noop,
    onToggleManualMana: noop,
    standDown: false,
  };

  /** Every action id the panel put in the document, in order. */
  const renderedIds = () =>
    [...document.querySelectorAll("[data-action-id]")].map((n) =>
      n.getAttribute("data-action-id"),
    );

  it("renders one button per legal action", () => {
    const actions = [
      action({ id: "a0-pass", kind: "pass", label: "Pass" }),
      action({ id: "a1-cast", kind: "cast", label: "Cast Bear" }),
      action({ id: "a2-play_land", kind: "play_land", label: "Play Forest" }),
    ];
    render(<ActionPanel state={gameView()} actions={actions} onAct={noop} {...base} />);
    for (const a of actions) {
      expect(document.querySelector(`[data-action-id="${a.id}"]`)).toBeTruthy();
    }
  });

  /*
   * The specific way this layout can break the id invariant: one action is
   * promoted to the commit slab, and if it is not also removed from the list it
   * renders twice. `clarity.spec.ts` would catch it a hundred actions later; this
   * catches it here.
   */
  it("promotes one action to the slab without also leaving it in the list", () => {
    const actions = [
      action({ id: "a0-pass", kind: "pass", label: "Pass" }),
      action({ id: "a1-cast", kind: "cast", label: "Cast Bear" }),
    ];
    render(<ActionPanel state={gameView()} actions={actions} onAct={noop} {...base} />);
    const ids = renderedIds();
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toHaveLength(2);
    expect(screen.getByTestId("commit").getAttribute("data-action-id")).toBe("a0-pass");
  });

  /*
   * The reported bug: six ways to aim one Simic Charm read as six copies of it,
   * because a row for a card draws the card and never the label. One row now,
   * with the ids on its target chips -- the shape an attacker with several legal
   * defenders already used, and the reason the invariant above still holds.
   */
  it("collapses one card's target variants into a row of target chips", () => {
    const charm = card({ oid: 12, zone: "hand", name: "Simic Charm", types: ["Instant"] });
    const state = gameView({
      players: [player({ hand: [charm] }), player({ pid: 1, hand: null })],
      battlefield: [
        card({ oid: 1, name: "Arixmethes" }),
        card({ oid: 2, name: "Kraken Token" }),
        card({ oid: 3, name: "Wall of Roots" }),
      ],
    });
    const aims = [1, 2, 3].map((id) =>
      action({
        id: `a${id}-cast`,
        kind: "cast",
        label: `Cast Simic Charm -> #${id}`,
        base_label: "Cast Simic Charm",
        source_oid: 12,
        targets: [{ kind: "object", id }],
      }),
    );
    render(
      <ActionPanel
        state={state}
        actions={[action({ id: "a0-pass", kind: "pass", label: "Pass" }), ...aims]}
        onAct={noop}
        {...base}
      />,
    );

    const rows = document.querySelectorAll(".acts__list .act");
    expect(rows).toHaveLength(1);
    expect(rows[0].getAttribute("data-action-id"), "the group row must carry no id").toBeNull();
    expect(screen.getByText("Simic Charm")).toBeTruthy();

    // Every action still reachable, exactly once, one control each.
    const chips = [...document.querySelectorAll(".act__aims .aim")];
    expect(chips.map((n) => n.textContent)).toEqual([
      "Arixmethes",
      "Kraken Token",
      "Wall of Roots",
    ]);
    const ids = renderedIds();
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(["a1-cast", "a2-cast", "a3-cast", "a0-pass"]);
  });

  it("names declining an optional target rather than showing a blank chip", () => {
    const state = gameView({
      players: [
        player({ hand: [card({ oid: 12, zone: "hand", name: "Simic Charm" })] }),
        player({ pid: 1, hand: null }),
      ],
      battlefield: [card({ oid: 1, name: "Arixmethes" })],
    });
    const shared = { kind: "cast", base_label: "Cast Simic Charm", source_oid: 12 } as const;
    render(
      <ActionPanel
        state={state}
        actions={[
          action({ id: "a1-cast", ...shared, targets: [{ kind: "object", id: 1 }] }),
          action({ id: "a2-cast", ...shared }),
        ]}
        onAct={noop}
        {...base}
      />,
    );
    const chips = [...document.querySelectorAll(".act__aims .aim")];
    expect(chips.map((n) => n.textContent)).toEqual(["Arixmethes", "No target"]);
  });

  it("clicking a chip submits that chip's action, not the row's first", () => {
    const onAct = vi.fn();
    const state = gameView({
      battlefield: [card({ oid: 1, name: "Arixmethes" }), card({ oid: 2, name: "Kraken" })],
    });
    const shared = {
      kind: "activate",
      base_label: "Herd Heirloom: {T}: gains trample",
      source_oid: 30,
      ability_index: 1,
    } as const;
    render(
      <ActionPanel
        state={state}
        actions={[
          action({ id: "a1-activate", ...shared, targets: [{ kind: "object", id: 1 }] }),
          action({ id: "a2-activate", ...shared, targets: [{ kind: "object", id: 2 }] }),
        ]}
        onAct={onAct}
        {...base}
      />,
    );
    fireEvent.click(screen.getByText("Kraken"));
    expect(onAct).toHaveBeenCalledWith("a2-activate");
  });

  it("renders no action at all while a modal owns the decision", () => {
    // Otherwise the mulligan buttons exist both here and behind the dialog.
    render(
      <ActionPanel
        state={gameView()}
        actions={[action({ id: "a0-keep", kind: "keep", label: "Keep" })]}
        onAct={noop}
        {...base}
        standDown
      />,
    );
    expect(renderedIds()).toEqual([]);
    // The tools stay reachable: quitting is most wanted exactly when a
    // dialog is up.
    expect(screen.getByTestId("full-control")).toBeTruthy();
  });

  it("submits the action id it was given, not a reconstructed action", () => {
    const onAct = vi.fn();
    render(
      <ActionPanel
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
      <ActionPanel
        state={gameView()}
        actions={[action({ id: "a3-cast", kind: "cast", label: "Cast Bear" })]}
        onAct={noop}
        {...base}
        narrating
      />,
    );
    expect(document.querySelector('[data-action-id="a3-cast"]')?.hasAttribute("disabled")).toBe(
      true,
    );
    expect(document.querySelector('[data-hint="Skip ahead"]')).toBeTruthy();
  });

  it("shows the stops setting the engine is actually holding", () => {
    const { unmount } = render(
      <ActionPanel state={gameView()} actions={[]} onAct={noop} {...base} />,
    );
    expect(screen.getByTestId("full-control").textContent).toBe("Auto-pass");
    unmount();

    render(
      <ActionPanel
        state={gameView({ full_control: true })}
        actions={[]}
        onAct={noop}
        {...base}
      />,
    );
    expect(screen.getByTestId("full-control").textContent).toBe("Full control");
  });

  it("asks for the opposite of the current stops setting", () => {
    const onToggleFullControl = vi.fn();
    render(
      <ActionPanel
        state={gameView()}
        actions={[]}
        onAct={noop}
        {...base}
        onToggleFullControl={onToggleFullControl}
      />,
    );
    fireEvent.click(screen.getByTestId("full-control"));
    expect(onToggleFullControl).toHaveBeenCalledWith(true);
  });

  it("says who it is waiting for", () => {
    const state = gameView({ pending: pending({ player: 1 }) });
    render(<ActionPanel state={state} actions={[]} onAct={noop} {...base} />);
    expect(screen.getByTestId("prompt").textContent).toContain("Waiting for AI 1");
  });

  /*
   * Choosing X is the one place the panel does *not* draw a button per legal
   * action -- `ask_x` offers 0..max, which is up to 21 of them. The stepper is
   * the deliberate exception recorded in the component's header doc, and what
   * these pin is that it is an exception and not a hole: no id is duplicated,
   * and there is always exactly one to press.
   */
  describe("choosing X", () => {
    const xState = (maxX: number) =>
      gameView({
        pending: pending({
          kind: "choose_x",
          prompt: "Choose X for Fireball",
          context: { purpose: "choose_x", max_x: maxX, per_point: 1 },
          options: Array.from({ length: maxX + 1 }, (_, i) => ({
            label: `X = ${i}`,
            ref: null,
            value: i,
          })),
        }),
      });

    const xActions = (maxX: number) =>
      Array.from({ length: maxX + 1 }, (_, i) =>
        action({ id: `a${i}-choose`, kind: "choose", label: `X = ${i}`, choice: i }),
      );

    it("draws a stepper instead of one button per value", () => {
      render(<ActionPanel state={xState(6)} actions={xActions(6)} onAct={noop} {...base} />);
      expect(screen.getByTestId("choose-x")).toBeTruthy();
      // Seven legal actions, one control. That is the exception.
      expect(renderedIds()).toHaveLength(1);
    });

    it("starts at zero", () => {
      render(<ActionPanel state={xState(6)} actions={xActions(6)} onAct={noop} {...base} />);
      expect(screen.getByTestId("choose-x").getAttribute("data-x")).toBe("0");
      expect(screen.getByTestId("commit").getAttribute("data-action-id")).toBe("a0-choose");
    });

    it("points the slab at whichever value is showing", () => {
      render(<ActionPanel state={xState(6)} actions={xActions(6)} onAct={noop} {...base} />);
      fireEvent.click(screen.getByTestId("choose-x-up"));
      fireEvent.click(screen.getByTestId("choose-x-up"));
      expect(screen.getByTestId("choose-x").getAttribute("data-x")).toBe("2");
      expect(screen.getByTestId("commit").getAttribute("data-action-id")).toBe("a2-choose");
    });

    it("submits the value that is showing", () => {
      const onAct = vi.fn();
      render(<ActionPanel state={xState(6)} actions={xActions(6)} onAct={onAct} {...base} />);
      fireEvent.click(screen.getByTestId("choose-x-up"));
      fireEvent.click(screen.getByTestId("commit"));
      expect(onAct).toHaveBeenCalledWith("a1-choose");
    });

    it("cannot be stepped past either end", () => {
      render(<ActionPanel state={xState(1)} actions={xActions(1)} onAct={noop} {...base} />);
      expect(screen.getByTestId("choose-x-down").hasAttribute("disabled")).toBe(true);
      fireEvent.click(screen.getByTestId("choose-x-up"));
      expect(screen.getByTestId("choose-x").getAttribute("data-x")).toBe("1");
      expect(screen.getByTestId("choose-x-up").hasAttribute("disabled")).toBe(true);
    });

    it("still offers X = 0 when that is the only value", () => {
      // The engine skips a forced question, but the panel must not render a
      // dead dock if one ever arrives -- `full-game.spec.ts` fails on zero
      // buttons, not on too few.
      render(<ActionPanel state={xState(0)} actions={xActions(0)} onAct={noop} {...base} />);
      expect(renderedIds()).toEqual(["a0-choose"]);
    });
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
