/**
 * The player column: the commander plinth, the life dial, and zones as piles.
 *
 * Most of this is guarding hooks rather than looks. Replacing the life numeral
 * with a dial and the zone chips with piles moves two things the rest of the
 * app reaches for -- the `life-{pid}` testid that `e2e/helpers.ts` parses as a
 * number, and the click that is the only route into `ZonePeek`.
 *
 * The plinth cases guard the thing that is easy to lose in a re-skin: its state
 * is meant to be legible on three channels, and two of them (the word and the
 * glyph) are asserted here because a screenshot cannot fail a build.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { GameView, PlayerView } from "../src/api/types";
import { PlayerOrb } from "../src/components/game/PlayerOrb";
import { pileLeaves } from "../src/logic/zones";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player } from "./fixtures";

afterEach(() => {
  cleanup();
  // `images` too, now that the orb reads it for the wash. A test that left a map
  // behind would hand the next one a background it never asked for.
  useUiStore.setState({ peek: null, images: null, hoveredOid: null });
});

function renderOrb(
  overrides: Partial<PlayerView> = {},
  props = {},
  view: Partial<GameView> = {},
) {
  const seat = player(overrides);
  // `commandersOf` reads `state.players[pid]`, so the seat under test has to sit
  // at its own index -- an orb rendered for pid 2 against a two-player view
  // would look up undefined.
  const players = Array.from({ length: seat.pid + 1 }, (_, pid) =>
    pid === seat.pid ? seat : player({ pid }),
  );
  return render(
    <PlayerOrb
      state={gameView({ players, seat: seat.pid, ...view })}
      player={seat}
      isViewer
      isActive
      hasPriority
      {...props}
    />,
  );
}

/** A commander sitting in the command zone, ready to be found by the plinth. */
function commander(overrides = {}) {
  return card({
    oid: 99,
    name: "Aesi, Tyrant of Gyre Strait",
    mana_cost: "{4}{G}{U}",
    is_commander: true,
    zone: "command",
    ...overrides,
  });
}

describe("the commander plinth", () => {
  it("puts the commander in the info panel rather than in a corner", () => {
    const { container, getByTestId } = renderOrb({ command: [commander()] });
    expect(container.querySelector(".orb .cmdzone")).not.toBeNull();
    expect(getByTestId("commander-99")).not.toBeNull();
  });

  it("shows the commander's name in full rather than a count", () => {
    // The whole reason it stopped being a shrunken card face: at ~74px the name
    // clipped to "Aesi, Tyra…" -- docs/mockup-fidelity.md defect #5.
    const { container } = renderOrb({ command: [commander()] });
    expect(container.querySelector(".cmdplinth__name")?.textContent).toBe(
      "Aesi, Tyrant of Gyre Strait",
    );
  });

  it("costs nothing at all when no commander is anywhere visible", () => {
    const { container } = renderOrb({ command: [] });
    expect(container.querySelector(".cmdzone")).toBeNull();
  });

  const STATES: [string, string, Partial<PlayerView>, Partial<GameView>, boolean][] = [
    ["waiting", "In command", { command: [commander()] }, {}, false],
    [
      "deployed",
      "On the battlefield",
      { command: [] },
      { battlefield: [commander({ zone: "battlefield" })] },
      false,
    ],
    [
      "fallen",
      "In the graveyard",
      { command: [], graveyard: [commander({ zone: "graveyard" })] },
      {},
      false,
    ],
    ["fallen", "Exiled", { command: [], exile: [commander({ zone: "exile" })] }, {}, false],
    ["ready", "Ready", { command: [commander()] }, {}, true],
  ];

  it.each(STATES)(
    "says %s in words as well as in colour",
    (key, word, seat, view, castable) => {
      // The word channel, and the glyph beside it. They exist so the state is
      // legible at orb size, which the green rim, on its own, never was.
      const { getByTestId } = renderOrb(
        seat,
        // A castable commander is one the *server* named in a legal action. The
        // client never works it out from mana.
        { playableOids: castable ? new Set([99]) : new Set() },
        view,
      );
      const slot = getByTestId("commander-99");
      expect(slot.getAttribute("data-cmd-state")).toBe(key);
      expect(slot.querySelector(".cmdplinth__word")?.textContent).toBe(word);
      expect(slot.querySelector(".cmdplinth__glyph")?.textContent ?? "").not.toBe("");
    },
  );

  it("only lets you click a commander the server says you can cast", () => {
    // Announced as disabled, not *made* disabled. The plinth has to keep
    // dispatching mouse events in every state or hovering it stops filling the
    // preview rail -- see the hover cases in commandZone.test.tsx. So the gate
    // is the click handler, and this asserts the gate rather than the attribute.
    const cast: number[] = [];
    const waiting = renderOrb(
      { command: [commander()] },
      { onCastCommander: (c: { oid: number }) => cast.push(c.oid) },
    );
    const slot = waiting.getByTestId("commander-99");
    expect(slot.getAttribute("aria-disabled")).toBe("true");
    expect((slot as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(slot);
    expect(cast).toEqual([]);

    cleanup();
    const ready = renderOrb(
      { command: [commander()] },
      {
        playableOids: new Set([99]),
        onCastCommander: (c: { oid: number }) => cast.push(c.oid),
      },
    );
    const live = ready.getByTestId("commander-99");
    expect(live.getAttribute("aria-disabled")).toBe("false");
    fireEvent.click(live);
    expect(cast).toEqual([99]);
  });

  it("stops casting while input is locked, without going unhoverable", () => {
    // `locked` is the narration/in-flight gate. It must not reach for the
    // `disabled` attribute either: a player watching narration can still want to
    // read their own commander.
    const cast: number[] = [];
    const { getByTestId } = renderOrb(
      { command: [commander()] },
      {
        playableOids: new Set([99]),
        locked: true,
        onCastCommander: (c: { oid: number }) => cast.push(c.oid),
      },
    );
    const slot = getByTestId("commander-99");
    expect((slot as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(slot);
    expect(cast).toEqual([]);
  });

  it("casts through the caller's play path rather than an action id", () => {
    // A gesture surface like the hand: giving it a `data-action-id` would put
    // two buttons on one action. e2e/cycle3.spec.ts guards the same invariant.
    const cast: number[] = [];
    const { getByTestId } = renderOrb(
      { command: [commander()] },
      {
        playableOids: new Set([99]),
        onCastCommander: (c: { oid: number }) => cast.push(c.oid),
      },
    );
    const slot = getByTestId("commander-99");
    expect(slot.querySelector("[data-action-id]")).toBeNull();
    expect(slot.getAttribute("data-action-id")).toBeNull();
    fireEvent.click(slot);
    expect(cast).toEqual([99]);
  });

  it("shows the tax beside the cost it modifies, not the cast count", () => {
    // `commander_cost` is the generic already doubled by the engine;
    // `commander_tax` counts prior casts. Showing the latter would say "+2"
    // when the player owes four.
    const { getByTestId } = renderOrb({
      command: [commander()],
      commander_tax: { "99": 2 },
      commander_cost: { "99": 4 },
    });
    expect(getByTestId("commander-99").querySelector(".cmdslot__tax")?.textContent).toBe("+4");
  });

  it("drops the cost row once the commander has left the command zone", () => {
    // A mana cost is only information where you could pay it.
    const { getByTestId } = renderOrb({
      command: [],
      graveyard: [commander({ zone: "graveyard" })],
    });
    expect(getByTestId("commander-99").querySelector(".cmdplinth__cost")).toBeNull();
  });
});

describe("the commander as the panel's ground", () => {
  it("washes the orb with the commander's art", () => {
    // The reason this direction was picked: four seats in a pod are four grey
    // rectangles told apart by a name in 12px type, and the one asset that
    // separates them instantly was already loaded.
    useUiStore.setState({
      images: { aesi: { card_id: "aesi", art: "/art/aesi.jpg", artist: "A" } },
    });
    const { container } = renderOrb({ command: [commander({ card_id: "aesi" })] });
    const wash = container.querySelector<HTMLElement>(".orb__wash");
    expect(wash).not.toBeNull();
    expect(wash?.style.backgroundImage).toContain("/art/aesi.jpg");
    // Unconditionally dark, so no type in the panel depends on the picture.
    expect(container.querySelector(".orb__veil")).not.toBeNull();
  });

  it("uses the art the plinth already asked for, not a second URL", () => {
    // Same `artUrl` call on the same card, so the wash is a cache hit rather
    // than a second request for a 626x457 crop.
    useUiStore.setState({
      images: { aesi: { card_id: "aesi", art: "/art/aesi.jpg", artist: "A" } },
    });
    const { container } = renderOrb({ command: [commander({ card_id: "aesi" })] });
    const wash = container.querySelector<HTMLElement>(".orb__wash");
    const img = container.querySelector<HTMLImageElement>(".cmdplinth__art img");
    expect(img?.getAttribute("src")).toBe("/art/aesi.jpg");
    expect(wash?.style.backgroundImage).toContain(img?.getAttribute("src") ?? "");
  });

  it("falls back to the flat panel when there is no art to wash with", () => {
    // `null` images is the map not yet fetched. Drawing a half-built wash there
    // would flash on every first paint; the plain well is a perfectly good panel.
    useUiStore.setState({ images: null });
    const { container } = renderOrb({ command: [commander()] });
    expect(container.querySelector(".orb__wash")).toBeNull();
    expect(container.querySelector(".orb__veil")).toBeNull();
  });

  it("carries no colour-identity tint", () => {
    // Dropped from mockup 03 on purpose: a tint is the first channel to die in
    // greyscale, and the portrait underneath it is not. If a tint layer ever
    // comes back, e2e/greyscale.spec.ts is the thing that has to agree first.
    useUiStore.setState({
      images: { aesi: { card_id: "aesi", art: "/art/aesi.jpg", artist: "A" } },
    });
    const { container } = renderOrb({ command: [commander({ card_id: "aesi" })] });
    expect(container.querySelector(".orb__tint")).toBeNull();
  });
});

describe("the life dial", () => {
  it("stamps the dial on the commander's portrait rather than in a row", () => {
    // The seal: it costs the overlap instead of a row, which is what pays for
    // the portrait being this size in a 190px column.
    const { container } = renderOrb({ command: [commander()] });
    const frame = container.querySelector(".cmdplinth__frame");
    expect(frame?.querySelector(".dial")).not.toBeNull();
    expect(container.querySelector(".orb__life-row")).toBeNull();
  });

  it("gives life a row of its own when no commander is visible", () => {
    // A commander in a hidden zone renders no plinth at all, and life is not
    // allowed to vanish with it.
    const { container, getByTestId } = renderOrb({ command: [] });
    expect(container.querySelector(".cmdzone")).toBeNull();
    expect(container.querySelector(".orb__life-row .dial")).not.toBeNull();
    expect(getByTestId("life-0").textContent).toBe("40");
  });

  it("draws one seal for a pair of partners, not two", () => {
    // Partners share a life total; two dials for one number would be a lie.
    const { container } = renderOrb({
      command: [commander(), commander({ oid: 98, name: "Second Commander" })],
    });
    expect(container.querySelectorAll(".cmdslot").length).toBe(2);
    expect(container.querySelectorAll(".dial").length).toBe(1);
  });

  it("keeps the life testid holding a bare number", () => {
    // `lifeOf()` in e2e/helpers.ts does `Number(textContent)` on this node.
    // Any extra character in it breaks every spec that reads a life total.
    const { getByTestId } = renderOrb({ pid: 0, life: 37 });
    const node = getByTestId("life-0");
    expect(node.textContent).toBe("37");
    expect(Number(node.textContent)).toBe(37);
  });

  it("puts the number inside the dial rather than replacing it", () => {
    const { container } = renderOrb({ life: 40 });
    expect(container.querySelector(".dial .dial__n")).not.toBeNull();
  });

  it("names the dial after whose it is", () => {
    /*
     * `--foe` is reachable only through the prop now. Nothing in the game
     * renders this column for anybody but the viewer -- an opponent is an
     * `OpponentSeat`, whose life lives in a gauge rather than a dial -- but the
     * distinction is kept because a spectator view would need it, and because a
     * dial that could not say whose it was would be the bug this test names.
     */
    const mine = renderOrb({}, { isViewer: true }).container;
    expect(mine.querySelector(".dial--mine")).not.toBeNull();
    expect(mine.querySelector(".dial--foe")).toBeNull();

    cleanup();

    const theirs = renderOrb({}, { isViewer: false }).container;
    expect(theirs.querySelector(".dial--foe")).not.toBeNull();
    expect(theirs.querySelector(".dial--mine")).toBeNull();
  });

  it("marks whose turn it is on the dial", () => {
    const { container } = renderOrb({}, { isActive: true });
    expect(container.querySelector(".dial--active")).not.toBeNull();
  });

  it("shows OUT rather than a number for a dead player", () => {
    const { getByTestId } = renderOrb({ pid: 1, has_lost: true, loss_reason: "life" });
    expect(getByTestId("life-1").textContent).toBe("OUT");
  });

  it("keeps the data-player anchor the arrows and effects use", () => {
    const { container } = renderOrb({ pid: 2 });
    expect(container.querySelector('[data-player="2"]')).not.toBeNull();
  });
});

describe("the zone piles", () => {
  it("draws one pile per zone that has somewhere to go", () => {
    const { container } = renderOrb({ exile: [card()] });
    const testids = [...container.querySelectorAll(".pile")].map((n) =>
      n.getAttribute("data-testid"),
    );
    expect(testids).toEqual([
      "pile-0-library",
      "pile-0-hand",
      "pile-0-graveyard",
      "pile-0-exile",
      "pile-0-command",
    ]);
  });

  it("hides the exile pile when nothing is exiled", () => {
    const { container } = renderOrb({ exile: [] });
    expect(container.querySelector('[data-testid="pile-0-exile"]')).toBeNull();
  });

  it("puts the exact count on the top leaf", () => {
    // The leaf count is capped; the number never is.
    const { container } = renderOrb({ library_count: 200 });
    const pile = container.querySelector('[data-testid="pile-0-library"]');
    expect(pile?.querySelector(".pile__leaf--top")?.textContent).toBe("200");
  });

  it("counts commanders in the command zone, not emblems", () => {
    const emblem = card({
      oid: 900,
      name: "Ob Nixilis Reignited Emblem",
      type_line: "Emblem",
      zone: "command",
    });
    const { container } = renderOrb({ command: [commander(), emblem] });
    const pile = container.querySelector('[data-testid="pile-0-command"]');
    expect(pile?.querySelector(".pile__leaf--top")?.textContent).toBe("1");
    expect(container.querySelector('[data-testid="commander-900"]')).toBeNull();
  });

  it("draws as many leaves as the arithmetic says", () => {
    const { container } = renderOrb({ library_count: 37 });
    const pile = container.querySelector('[data-testid="pile-0-library"]');
    // Body leaves only -- the top leaf carries the number and is not one.
    const leaves = pile?.querySelectorAll(".pile__leaf:not(.pile__leaf--top)").length;
    expect(leaves).toBe(pileLeaves(37));
  });

  it("opens the zone viewer when clicked", () => {
    // The load-bearing one. These replaced the chips, and the chips were how
    // the graveyard was reachable at all.
    const { getByTestId } = renderOrb({ graveyard: [card()] });
    fireEvent.click(getByTestId("pile-0-graveyard"));
    expect(useUiStore.getState().peek).toEqual({ pid: 0, zone: "graveyard" });
  });

  it("opens the command zone too", () => {
    const { getByTestId } = renderOrb({ command: [card()] });
    fireEvent.click(getByTestId("pile-0-command"));
    expect(useUiStore.getState().peek).toEqual({ pid: 0, zone: "command" });
  });

  it("does not pretend the library can be opened", () => {
    // Hidden information: a control that does nothing when clicked is worse
    // than no control.
    const { getByTestId } = renderOrb();
    const library = getByTestId("pile-0-library");
    expect(library.tagName).toBe("DIV");
    fireEvent.click(library);
    expect(useUiStore.getState().peek).toBeNull();
  });

  it("marks an empty zone so it reads as empty rather than tiny", () => {
    const { getByTestId } = renderOrb({ graveyard: [] });
    expect(getByTestId("pile-0-graveyard").className).toContain("pile--empty");
  });

  it("names a revealed top card as revealed", () => {
    // "Play with the top card of your library revealed" -- Vampire Nocturnus.
    // The server sends this one to every seat, so the whole table knows it.
    const { getByTestId } = renderOrb({
      library_top: card({ name: "Sol Ring" }),
      library_top_public: true,
    });
    const pile = getByTestId("pile-0-library");
    expect(pile.getAttribute("data-revealed")).toBe("Sol Ring");
    expect(pile.getAttribute("data-hint")).toBe("Top of library, revealed: Sol Ring");
    expect(pile.hasAttribute("data-top-private")).toBe(false);
  });

  it("does not call a private look revealed", () => {
    // "You may look at the top card of your library any time" -- Verge Rangers.
    // The server sent this card to one seat and no other; the two payloads are
    // otherwise identical, so a pile that read only `library_top` would tell the
    // one player who can see it that their opponents can see it too.
    const { getByTestId } = renderOrb({
      library_top: card({ name: "Sol Ring" }),
      library_top_public: false,
    });
    const pile = getByTestId("pile-0-library");
    expect(pile.getAttribute("data-hint")).toBe(
      "Top of library, only you can see it: Sol Ring",
    );
    expect(pile.hasAttribute("data-top-private")).toBe(true);
  });

  it("claims nothing about a top card it was not sent", () => {
    const pile = renderOrb().getByTestId("pile-0-library");
    expect(pile.getAttribute("data-revealed")).toBeNull();
    expect(pile.hasAttribute("data-top-private")).toBe(false);
    expect(pile.className).not.toContain("pile--revealed");
  });
});

describe("what the piles did not replace", () => {
  it("still renders the mana panel with its spent markings", () => {
    // Neither mockup has this, and it is driven by the engine's own solved
    // payment -- losing it in a re-skin would be silent.
    const { container } = renderOrb({
      mana: {
        pool: {},
        total: 2,
        sources: [
          { oid: 5, options: [["G"]], symbols: ["G"], amount: 1 },
          // An ambiguous source is one mana of a choice, not two solid ones --
          // two would claim a mana that does not exist. Grouped, that is one
          // chip carrying a count of one, drawn as the {G/U} hybrid.
          { oid: 6, options: [["G"], ["U"]], symbols: ["G", "U"], amount: 1 },
        ],
      },
    });
    const panel = container.querySelector('[data-testid="mana-0"]');
    expect(panel).not.toBeNull();

    const groups = [...(panel?.querySelectorAll(".mana-grp") ?? [])];
    expect(groups.map((g) => g.getAttribute("data-tone"))).toEqual(["G", "any"]);
    // Two kinds of mana, one of each -- the counts are what the pips used to be.
    expect(groups.map((g) => g.getAttribute("data-count"))).toEqual(["1", "1"]);
    expect(panel?.getAttribute("data-mana")).toBe("{G}{?}");
  });

  it("keeps the panel when there is no mana rather than collapsing the orb", () => {
    // It used to hide, inside a height-reserved slot that existed only to stop
    // the panel resizing. The plate is permanent now and says so instead: mana
    // empties several times a turn and the foot must not move when it does.
    const { container } = renderOrb({ mana: { sources: [], pool: {}, total: 0 } });
    const panel = container.querySelector('[data-testid="mana-0"]');
    expect(panel).not.toBeNull();
    expect(panel?.querySelectorAll(".mana-grp").length).toBe(0);
    expect(panel?.querySelector(".orb__none")?.textContent).toBe("—");
  });
});

describe("commander damage is not this panel's job any more", () => {
  /*
   * It used to be a chip per opposing seat with a meter under it -- the
   * loudest object in a 154px column, and it answered only half the question:
   * how close is each of them to killing me, and nothing about the other
   * direction. Both halves are two arrows on each opponent's own life bar now;
   * see `OpponentSeat`.
   */
  it("draws no commander-damage plate, however much has been taken", () => {
    const seat = player({ pid: 0, commander_damage_taken: { "1": 15 } });
    const { container } = render(
      <PlayerOrb
        state={gameView({
          players: [seat, player({ pid: 1 }), player({ pid: 2 }), player({ pid: 3 })],
          seat: 0,
        })}
        player={seat}
        isViewer
        isActive
        hasPriority
      />,
    );

    expect(container.querySelector('[data-testid="cmddmg-0"]')).toBeNull();
    expect(container.querySelector(".cmd-pip")).toBeNull();
  });
});
