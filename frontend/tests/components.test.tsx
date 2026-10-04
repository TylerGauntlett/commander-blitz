import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AnimatePresence } from "motion/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PendingDecision } from "../src/api/types";
import { ActionPanel } from "../src/components/game/ActionPanel";
import { StaticCard } from "../src/components/game/Card";
import { CardFace } from "../src/components/game/CardFace";
import { PromptDialog } from "../src/components/game/PromptDialog";
import { noteInput, resetInputMode } from "../src/input/inputMode";
import { chooseType } from "../src/testing/scenarios";
import { action, card, gameView, pending, player } from "./fixtures";

afterEach(cleanup);

const noop = () => undefined;

describe("StaticCard", () => {
  /*
   * The two halves of `onSurface`, side by side. A card of its own registers an
   * exit with the presence around it and stays for that animation; a card on a
   * surface has no exit to run, so the presence has nothing to wait on and the
   * card goes the moment it is dropped -- which is what keeps the surface's
   * own removal from depending on seven of them.
   */
  it("lingers for its exit by default, and leaves at once on a surface", () => {
    const view = (shown: boolean, onSurface: boolean) => (
      <AnimatePresence>
        {shown && (
          <StaticCard key="c" card={card({ name: "Grizzly Bears" })} onSurface={onSurface} />
        )}
      </AnimatePresence>
    );
    const own = render(view(true, false));
    own.rerender(view(false, false));
    expect(screen.queryByText("Grizzly Bears"), "an exit of its own runs first").not.toBeNull();
    cleanup();

    const onSurface = render(view(true, true));
    onSurface.rerender(view(false, true));
    expect(
      screen.queryByText("Grizzly Bears"),
      "nothing to run; nothing to wait on",
    ).toBeNull();
  });
});

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

  it("names every target of an any-number spell, so its subsets read apart", () => {
    const state = gameView({
      players: [
        player({ hand: [card({ oid: 12, zone: "hand", name: "Clever Concealment" })] }),
        player({ pid: 1, hand: null }),
      ],
      battlefield: [card({ oid: 1, name: "Giada" }), card({ oid: 2, name: "Thraben Watcher" })],
    });
    const shared = {
      kind: "cast",
      base_label: "Cast Clever Concealment",
      source_oid: 12,
    } as const;
    const giada = { kind: "object", id: 1 } as const;
    const watcher = { kind: "object", id: 2 } as const;
    render(
      <ActionPanel
        state={state}
        actions={[
          action({ id: "a1-cast", ...shared, targets: [giada] }),
          action({ id: "a2-cast", ...shared, targets: [giada, watcher] }),
          action({ id: "a3-cast", ...shared, targets: [watcher] }),
        ]}
        onAct={noop}
        {...base}
      />,
    );
    const chips = [...document.querySelectorAll(".act__aims .aim")];
    expect(chips.map((n) => n.textContent)).toEqual([
      "Giada",
      "Giada + Thraben Watcher",
      "Thraben Watcher",
    ]);
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

    /*
     * Brisela's "can't cast spells with mana value 3 or less" puts a floor under
     * an opponent's X: the engine offers X = 3..max, and each action's `choice` is
     * the option's index -- X less the floor -- not X itself.
     */
    describe("with a floor under X", () => {
      const floored = (minX: number, maxX: number) =>
        gameView({
          pending: pending({
            kind: "choose_x",
            prompt: "Choose X for Fireball",
            context: { purpose: "choose_x", min_x: minX, max_x: maxX, per_point: 1 },
            options: Array.from({ length: maxX - minX + 1 }, (_, i) => ({
              label: `X = ${minX + i}`,
              ref: null,
              value: minX + i,
            })),
          }),
        });
      const flooredActions = (minX: number, maxX: number) =>
        Array.from({ length: maxX - minX + 1 }, (_, i) =>
          action({
            id: `a${minX + i}-choose`,
            kind: "choose",
            label: `X = ${minX + i}`,
            choice: i,
          }),
        );

      it("starts at the floor and points at its action", () => {
        render(
          <ActionPanel
            state={floored(3, 6)}
            actions={flooredActions(3, 6)}
            onAct={noop}
            {...base}
          />,
        );
        expect(screen.getByTestId("choose-x").getAttribute("data-x")).toBe("3");
        expect(screen.getByTestId("commit").getAttribute("data-action-id")).toBe("a3-choose");
        expect(screen.getByTestId("choose-x").textContent).toContain("3 to 6");
      });

      it("cannot be stepped below the floor", () => {
        render(
          <ActionPanel
            state={floored(3, 6)}
            actions={flooredActions(3, 6)}
            onAct={noop}
            {...base}
          />,
        );
        expect(screen.getByTestId("choose-x-down").hasAttribute("disabled")).toBe(true);
      });

      it("submits the action for the X that is showing, not the index", () => {
        const onAct = vi.fn();
        render(
          <ActionPanel
            state={floored(3, 6)}
            actions={flooredActions(3, 6)}
            onAct={onAct}
            {...base}
          />,
        );
        fireEvent.click(screen.getByTestId("choose-x-up"));
        expect(screen.getByTestId("choose-x").getAttribute("data-x")).toBe("4");
        fireEvent.click(screen.getByTestId("commit"));
        expect(onAct).toHaveBeenCalledWith("a4-choose");
      });
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

  /*
   * THE MULLIGAN IS NOT ONE OF THESE ANY MORE, and the pair below is the whole
   * of that claim.
   *
   * `OpeningHand` draws it as a screen, so this dialog has to stay shut for it
   * or the two would render `keep` and `mulligan` twice between them. The
   * second case is the one that needed a new predicate rather than a new entry
   * in the denylist: the bottoming half of a mulligan is a `choose_objects`,
   * which is a kind this dialog still owns everywhere else.
   */
  it("stays shut for a mulligan, which has a screen of its own", () => {
    render(
      <PromptDialog
        state={shown("mulligan")}
        actions={[
          action({ id: "a0-mulligan", kind: "mulligan", label: "Mulligan" }),
          action({ id: "a1-keep", kind: "keep", label: "Keep" }),
        ]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("prompt-dialog")).toBeNull();
  });

  it("stays shut for the bottoming half, and opens for every other choose_objects", () => {
    const bottoming = shown("choose_objects", {
      context: { purpose: "mulligan_bottom", source_name: "Mulligan" },
    });
    render(
      <PromptDialog
        state={bottoming}
        actions={[action({ id: "a0-bottom", kind: "choose", label: "Forest", choice: 0 })]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("prompt-dialog")).toBeNull();
    cleanup();

    render(
      <PromptDialog
        state={shown("choose_objects", { context: { purpose: "sacrifice" } })}
        actions={[action({ id: "a0-sac", kind: "choose", label: "Forest", choice: 0 })]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.getByTestId("prompt-dialog").dataset.decisionKind).toBe("choose_objects");
  });

  /*
   * `AnimatePresence` keeps the dialog in the DOM for its exit animation, and
   * for that window it is still `[data-modal-root]` with its buttons. `stopRoot`
   * and the e2e prompt-clearing helper both read
   * `[data-modal-root]:not([data-closing])`, so the attribute is what stops the
   * ring -- or a test -- from choosing a surface that is already leaving.
   */
  it("marks itself closing while it animates out", () => {
    const answered = gameView({ pending: null });
    const { rerender } = render(
      <PromptDialog
        state={shown("choose_objects", { context: { purpose: "sacrifice" } })}
        actions={[action({ id: "a0-sac", kind: "choose", label: "Forest", choice: 0 })]}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.getByTestId("prompt-dialog").hasAttribute("data-closing")).toBe(false);

    rerender(<PromptDialog state={answered} actions={[]} onAct={noop} disabled={false} />);
    const leaving = screen.getByTestId("prompt-dialog");
    expect(leaving.hasAttribute("data-modal-root")).toBe(true);
    expect(leaving.hasAttribute("data-closing")).toBe(true);
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

/**
 * The wall, and the combobox that replaced it.
 *
 * `op_choose_type` asks with every creature type in the pool as an option, and
 * the surface has to change shape for that without changing shape for the
 * three-option charm beside it. Both halves are tested here, because a
 * threshold is only correct with respect to what falls on each side of it.
 */
describe("PromptDialog with a wall of options", () => {
  const mount = (disabled = false) => {
    const { state, actions } = chooseType();
    const onAct = vi.fn();
    const view = render(
      <PromptDialog state={state} actions={actions} onAct={onAct} disabled={disabled} />,
    );
    return { ...view, onAct, actions };
  };

  const field = () => screen.getByTestId("combo-filter") as HTMLInputElement;
  const rows = () => screen.getAllByRole("option");
  const go = () => screen.getByTestId("combo-go") as HTMLButtonElement;

  it("leaves a short decision exactly as it was", () => {
    render(
      <PromptDialog
        state={gameView({ pending: pending({ kind: "choose_mode", prompt: "Choose one" }) })}
        actions={[0, 1, 2].map((i) =>
          action({ id: `a${i}-choose`, kind: "choose", label: `Mode ${i}` }),
        )}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("choice-combo")).toBeNull();
    expect(document.querySelectorAll(".opt").length).toBe(3);
  });

  it("keeps drawing card options as cards however many there are", () => {
    // A card face is not a combobox row: choosing what to sacrifice should look
    // like looking at your board, and that stays true past the threshold.
    const battlefield = Array.from({ length: 20 }, (_, i) =>
      card({ oid: 500 + i, name: `Creature ${i}` }),
    );
    render(
      <PromptDialog
        state={gameView({
          pending: pending({ kind: "choose_objects", prompt: "Sacrifice one" }),
          battlefield,
        })}
        actions={battlefield.map((c, i) =>
          action({
            id: `a${i}-choose`,
            kind: "choose",
            label: c.name,
            targets: [{ kind: "object", id: c.oid }],
          }),
        )}
        onAct={noop}
        disabled={false}
      />,
    );
    expect(screen.queryByTestId("choice-combo")).toBeNull();
    expect(document.querySelectorAll(".opt--card").length).toBe(20);
  });

  it("offers the combobox instead of one button per type", () => {
    const { actions } = mount();
    expect(screen.getByTestId("choice-combo")).toBeTruthy();
    expect(rows().length).toBe(actions.length);
    expect(screen.getByTestId("combo-count").textContent).toBe(
      `${actions.length} of ${actions.length}`,
    );
    // The whole point: one action id in the document, not two hundred.
    expect(document.querySelectorAll("[data-action-id]").length).toBe(1);
  });

  it("highlights the first row, so the Choose button is never dead", () => {
    const { onAct, actions } = mount();
    expect(rows()[0].getAttribute("aria-selected")).toBe("true");
    expect(go().textContent).toBe(`Choose ${actions[0].label}`);
    expect(go().disabled).toBe(false);
    fireEvent.click(go());
    expect(onAct).toHaveBeenCalledWith(actions[0].id);
  });

  it("narrows to what was typed, and rebinds Choose to the best match", () => {
    const { onAct, actions } = mount();
    fireEvent.change(field(), { target: { value: "vam" } });
    expect(rows().map((row) => row.textContent)).toEqual(["Vampire"]);
    expect(go().textContent).toBe("Choose Vampire");
    fireEvent.click(go());
    expect(onAct).toHaveBeenCalledWith(actions.find((a) => a.label === "Vampire")?.id);
  });

  it("commits the highlighted row on Enter", () => {
    const { onAct, actions } = mount();
    fireEvent.change(field(), { target: { value: "vampire" } });
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(onAct).toHaveBeenCalledWith(actions.find((a) => a.label === "Vampire")?.id);
  });

  it("moves the highlight with the arrows without taking the caret", () => {
    const { onAct, actions } = mount();
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    fireEvent.keyDown(field(), { key: "ArrowDown" });
    expect(rows()[2].getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(field());
    fireEvent.keyDown(field(), { key: "ArrowUp" });
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(onAct).toHaveBeenCalledWith(actions[1].id);
  });

  it("follows the ring: focusing a row is what highlights it", () => {
    // The one wire between the global cursor and this component. `cursor.stamp`
    // focuses the stop it lands on, and this is what makes that a selection.
    const { actions } = mount();
    fireEvent.focus(rows()[4]);
    expect(rows()[4].getAttribute("aria-selected")).toBe("true");
    expect(go().getAttribute("data-action-id")).toBe(actions[4].id);
  });

  it("clears the query on Escape rather than answering the prompt", () => {
    const { onAct, actions } = mount();
    fireEvent.change(field(), { target: { value: "vam" } });
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field().value).toBe("");
    expect(rows().length).toBe(actions.length);
    expect(onAct).not.toHaveBeenCalled();
  });

  it("says so when nothing matches, and disables Choose", () => {
    mount();
    fireEvent.change(field(), { target: { value: "zzzz" } });
    expect(screen.queryAllByRole("option")).toEqual([]);
    expect(screen.getByTestId("combo-empty")).toBeTruthy();
    expect(go().disabled).toBe(true);
    expect(document.querySelectorAll("[data-action-id]").length).toBe(0);
    fireEvent.click(screen.getByTestId("combo-clear"));
    expect(screen.getAllByRole("option").length).toBeGreaterThan(0);
  });

  it("takes the caret for a mouse, and leaves it alone for a pad", () => {
    /*
     * A focused field deadens the arrow keys that stand in for the d-pad
     * (`pad.ts:isTyping`), so autofocusing one on a controller would break the
     * only navigation that player has.
     */
    const first = mount();
    expect(document.activeElement).toBe(field());
    first.unmount();

    noteInput("pad");
    mount();
    expect(document.activeElement).not.toBe(field());
    resetInputMode();
  });
});
