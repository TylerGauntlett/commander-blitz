/**
 * The opponent seat: the five numbers, and the hooks the rest of the app holds.
 *
 * Two kinds of assertion here, and they fail for different reasons.
 *
 * **The numbers** are the whole reason this component exists. the seat round
 * records the failure mode: five of its six directions could not be *wrong*
 * about the board, because the numbers were never in the payload -- so nothing
 * could contradict them. Every count here is checked against `musterOf`, which
 * is also what `threatOf` is derived from, so a seat that disagrees with the
 * board it summarises fails in this file rather than in a playtest.
 *
 * **The identity attributes** are the ones that break silently and far away.
 * `data-player` anchors `FxLayer` and `CombatArrows`; `data-stop="orb:<pid>"`
 * is what `parseStop`, `verbsFor` and the R2 hold branch on; `player-<pid>` and
 * `life-<pid>` are what `e2e/helpers.ts` queries. Renaming any of them compiles
 * cleanly and takes out damage numerals, the hint bar and the e2e suite.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CardView, GameView, PlayerView } from "../src/api/types";
import { OpponentSeat } from "../src/components/game/OpponentSeat";
import { RAIL_SETTLE, resetCursor, setCursor } from "../src/input/cursor";
import { noteInput, resetInputMode } from "../src/input/inputMode";
import { musterOf } from "../src/logic/threat";
import { useUiStore } from "../src/state/uiStore";
import { card, gameView, player } from "./fixtures";

afterEach(() => {
  cleanup();
  useUiStore.setState({ peek: null, images: null, hoveredOid: null });
});

const creature = (overrides: Partial<CardView> = {}): CardView =>
  card({
    types: ["Creature"],
    type_line: "Creature — Bear",
    zone: "battlefield",
    power: 2,
    toughness: 2,
    ...overrides,
  });

const land = (overrides: Partial<CardView> = {}): CardView =>
  card({
    name: "Forest",
    types: ["Land"],
    type_line: "Basic Land — Forest",
    zone: "battlefield",
    power: null,
    toughness: null,
    ...overrides,
  });

/**
 * A two-seat view with the opponent at pid 1.
 *
 * `commandersOf` reads `state.players[pid]`, so the seat under test has to sit
 * at its own index -- a seat rendered for pid 1 against a one-player view would
 * look up undefined.
 */
function view(
  battlefield: CardView[] = [],
  overrides: Partial<PlayerView> = {},
  extraSeats = 0,
): GameView {
  const players = [
    player({ pid: 0, name: "You" }),
    player({ pid: 1, name: "Edgar", ...overrides }),
    ...Array.from({ length: extraSeats }, (_, i) => player({ pid: 2 + i })),
  ];
  return gameView({
    players,
    battlefield: battlefield.map((c) => ({ ...c, controller: 1, owner: 1 })),
  });
}

function renderSeat(state: GameView, props: Record<string, unknown> = {}) {
  return render(
    <OpponentSeat
      state={state}
      player={state.players[1]}
      isActive={false}
      hasPriority={false}
      targetable={false}
      {...props}
    />,
  );
}

describe("the counts", () => {
  it("says untapped over total for lands and creatures", () => {
    const state = view([
      land(),
      land({ tapped: true }),
      creature(),
      creature({ tapped: true }),
      creature({ tapped: true }),
    ]);
    const { container } = renderSeat(state);

    expect(container.querySelector('[data-perm="land"] .perm__n')?.textContent).toBe("1/2");
    expect(container.querySelector('[data-perm="creature"] .perm__n')?.textContent).toBe("1/3");
  });

  it("gives the artifact cell a count and no meter", () => {
    /*
     * The lane mixes artifacts with enchantments, and an enchantment does not
     * tap -- so `untapped/total` there would be measuring two different things
     * and calling them one. A meter the component cannot vouch for is worse
     * than no meter, so the cell is a bare number and `--bar: 0` in the sheet.
     */
    const state = view([
      card({ types: ["Artifact"], type_line: "Artifact", zone: "battlefield", tapped: true }),
      card({ types: ["Enchantment"], type_line: "Enchantment", zone: "battlefield" }),
    ]);
    const { container } = renderSeat(state);
    const cell = container.querySelector('[data-perm="other"]');

    expect(cell?.querySelector(".perm__n")?.textContent).toBe("2");
    expect(cell?.getAttribute("data-open")).toBe("");
  });

  it("agrees with `musterOf` on every cell", () => {
    // The property the whole component rests on. `e2e/handheldAssert.ts` asks
    // the same question of the rendered board against its own walk.
    const state = view([
      land(),
      land(),
      land({ tapped: true }),
      creature({ power: 5 }),
      creature({ tapped: true, keywords: ["flying"], power: 3 }),
      card({ types: ["Artifact"], type_line: "Artifact", zone: "battlefield" }),
    ]);
    const muster = musterOf(state, 1);
    const { container } = renderSeat(state);

    const cell = (kind: string) => container.querySelector(`[data-perm="${kind}"]`);
    expect(cell("land")?.getAttribute("data-total")).toBe(String(muster.lands));
    expect(cell("land")?.getAttribute("data-open")).toBe(String(muster.landsUntapped));
    expect(cell("creature")?.getAttribute("data-total")).toBe(String(muster.creatures));
    expect(cell("creature")?.getAttribute("data-open")).toBe(String(muster.creaturesUntapped));
    expect(cell("other")?.getAttribute("data-total")).toBe(String(muster.other));
    expect(container.querySelector(".perm__pow")?.getAttribute("data-power")).toBe(
      String(muster.power),
    );
  });

  it("counts each duplicate permanent, not each visible stack", () => {
    // The board collapses seven Forests into one card with a x7 on it. A seat
    // that reported "1 land" would be wrong about the number it exists to say.
    const { container } = renderSeat(view(Array.from({ length: 7 }, () => land())));
    expect(container.querySelector('[data-perm="land"] .perm__n')?.textContent).toBe("7/7");
  });

  it("reports an empty board rather than rendering nothing", () => {
    // "Nothing in play" is the most useful thing a seat can say, so the cells
    // are drawn at zero rather than dropped -- and dropping them would move the
    // widths of the ones that remain every time a board changed.
    const { container } = renderSeat(view([]));
    expect(container.querySelectorAll(".perm")).toHaveLength(4);
    expect(container.querySelector(".pips__more")?.textContent).toBe("0/0");
  });
});

describe("the creature pips", () => {
  it("fills a pip per untapped creature and shoulders the fliers", () => {
    const { container } = renderSeat(
      view([creature(), creature({ tapped: true }), creature({ keywords: ["flying"] })]),
    );
    const pips = container.querySelectorAll(".tpip");

    expect(pips).toHaveLength(3);
    expect(container.querySelectorAll(".tpip--up")).toHaveLength(2);
    expect(container.querySelectorAll(".tpip--fly")).toHaveLength(1);
  });

  it("caps at eight and says how many more", () => {
    const { container } = renderSeat(view(Array.from({ length: 11 }, () => creature())));

    expect(container.querySelectorAll(".tpip")).toHaveLength(8);
    expect(container.querySelector(".pips__more")?.textContent).toBe("+3");
  });

  it("keeps the untapped and the fliers when it caps", () => {
    /*
     * The ordering is what makes the cap safe. Ten creatures with one flier and
     * one untapped, drawn in the order the lane happens to hold them, would put
     * both facts behind the `+2` -- and both are exactly what the pips are for.
     */
    const cards = [
      ...Array.from({ length: 9 }, () => creature({ tapped: true })),
      creature({ keywords: ["flying"] }),
    ];
    const { container } = renderSeat(view(cards));

    expect(container.querySelectorAll(".tpip--up")).toHaveLength(1);
    expect(container.querySelectorAll(".tpip--fly")).toHaveLength(1);
  });
});

describe("the lethal gauge", () => {
  it("fills life as a fraction of forty", () => {
    const { container } = renderSeat(view([], { life: 30 }));
    const gauge = container.querySelector(".gauge") as HTMLElement;
    expect(gauge.style.getPropertyValue("--fill")).toBe("75%");
  });

  it("never fills past full when life goes above forty", () => {
    const { container } = renderSeat(view([], { life: 55 }));
    const gauge = container.querySelector(".gauge") as HTMLElement;
    expect(gauge.style.getPropertyValue("--fill")).toBe("100%");
  });

  it("draws one arrow per direction, each at its own fraction of 21", () => {
    /*
     * The two facts a Commander player actually watches, and they are about
     * different pairs of people: what YOUR commander has done to this seat, and
     * what THIS SEAT's commander has done to you. The bar used to carry neither
     * -- it drew the worst damage this seat had taken from anybody.
     */
    const state = view([], { commander_damage_taken: { "0": 7 } });
    state.players[0].commander_damage_taken = { "1": 14 };
    const { getByTestId } = renderSeat(state);
    const track = getByTestId("cmddmg-1");

    const dealt = track.querySelector<HTMLElement>('[data-cmddmg="dealt"]');
    const taken = track.querySelector<HTMLElement>('[data-cmddmg="taken"]');
    expect(dealt?.style.getPropertyValue("--at")).toBe(`${(7 / 21) * 100}%`);
    expect(taken?.style.getPropertyValue("--at")).toBe(`${(14 / 21) * 100}%`);
    expect(track.getAttribute("data-dealt")).toBe("7");
    expect(track.getAttribute("data-taken")).toBe("14");
  });

  it("never parks an arrow past the end of the track", () => {
    const state = view([], { commander_damage_taken: { "0": 26 } });
    const { getByTestId } = renderSeat(state);
    expect(
      getByTestId("cmddmg-1")
        .querySelector<HTMLElement>('[data-cmddmg="dealt"]')
        ?.style.getPropertyValue("--at"),
    ).toBe("100%");
  });

  it("draws no arrow in a direction nothing has happened in", () => {
    // Zero costs no layout here -- the arrows are absolutely positioned -- so
    // the reflow argument that keeps the other cells at zero does not apply,
    // and two marks parked on the left edge would be two marks saying nothing.
    const state = view([], { commander_damage_taken: { "0": 0 } });
    const { getByTestId } = renderSeat(state);
    expect(getByTestId("cmddmg-1").querySelectorAll(".cmdarrow")).toHaveLength(0);
  });

  it("warns from fifteen, which is one hit short of lethal", () => {
    const state = view([], { commander_damage_taken: { "0": 15 } });
    const { getByTestId } = renderSeat(state);
    expect(getByTestId("cmddmg-1").querySelector('[data-cmddmg="dealt"]')?.className).toContain(
      "cmdarrow--warn",
    );
  });

  it("puts both numbers on the gauge's hint, since the row cannot hold them", () => {
    const state = view([], { commander_damage_taken: { "0": 4 } });
    state.players[0].commander_damage_taken = { "1": 12 };
    const { container } = renderSeat(state);
    const hint = container.querySelector(".gauge")?.getAttribute("data-hint") ?? "";
    expect(hint).toContain("you have dealt 4 of 21 commander damage to Edgar");
    expect(hint).toContain("Edgar has dealt 12 of 21 commander damage to you");
  });
});

describe("the hooks the rest of the app holds", () => {
  it("keeps every attribute another module resolves it by", () => {
    const { container, getByTestId } = renderSeat(view([]));
    const seat = container.querySelector(".seat") as HTMLElement;

    // FxLayer's damage numerals and CombatArrows' ends.
    expect(seat.getAttribute("data-player")).toBe("1");
    // `parseStop` case "orb" -- NOT a new `seat:<pid>` namespace, which would
    // break `verbsFor` and the R2 hold silently and in three places.
    expect(seat.getAttribute("data-stop")).toBe("orb:1");
    // `full-game.spec.ts`, and `e2e/helpers.ts`'s `lifeOf`.
    expect(getByTestId("player-1")).toBe(seat);
    expect(getByTestId("life-1").textContent).toBe("40");
  });

  it("keeps the zone counts queryable", () => {
    const state = view([], {
      library_count: 72,
      hand_count: 4,
      graveyard: [card({ zone: "graveyard" })],
    });
    const { getByTestId } = renderSeat(state);

    expect(getByTestId("pile-1-library").textContent).toBe("72");
    expect(getByTestId("pile-1-hand").textContent).toBe("4");
    expect(getByTestId("pile-1-graveyard").textContent).toBe("1");
  });

  it("counts commanders in the command zone, not emblems", () => {
    const state = view([], {
      // The emblem first, so a seat that took the first command card as its
      // commander would name the emblem.
      command: [
        card({
          oid: 900,
          name: "Ob Nixilis Reignited Emblem",
          type_line: "Emblem",
          zone: "command",
        }),
        card({ oid: 11, name: "Edgar Markov", is_commander: true, zone: "command" }),
      ],
    });
    const { container, getByTestId } = renderSeat(state);
    expect(getByTestId("pile-1-command").textContent).toBe("1");
    expect(container.querySelector(".seat__cmdr")?.textContent).toBe("Edgar Markov");
  });

  it("shows exile only once something is in it", () => {
    // Four marks or five, and the row has to survive the reflow -- which is why
    // the marks share the width rather than being placed.
    expect(renderSeat(view([])).queryByTestId("pile-1-exile")).toBeNull();
    cleanup();
    const state = view([], { exile: [card({ zone: "exile" })] });
    expect(renderSeat(state).queryByTestId("pile-1-exile")).not.toBeNull();
  });

  it("renders OUT rather than a number for a dead seat", () => {
    const state = view([], { has_lost: true, loss_reason: "life" });
    expect(renderSeat(state).getByTestId("life-1").textContent).toBe("OUT");
  });

  it("carries no action id, because the panel owns every one of them", () => {
    // The seat is a target and a viewer, never a second copy of the action
    // space. `e2e/cycle3.spec.ts` asserts the same thing of the whole board.
    const { container } = renderSeat(view([]));
    expect(container.querySelectorAll("[data-action-id]")).toHaveLength(0);
  });

  it("opens no native tooltip", () => {
    // A `title` opens on hover and on nothing else, so on a controller it is
    // information that cannot be reached at all. `tests/noTooltips.test.ts`
    // holds the same line across the source tree.
    const state = view([creature()], { commander_damage_taken: { "0": 3 } });
    const { container } = renderSeat(state);
    expect(container.querySelectorAll("[title]")).toHaveLength(0);
    // ...and everything that would have carried one names itself instead.
    expect(container.querySelector(".gauge")?.getAttribute("aria-label")).toContain("life");
  });
});

describe("pressing it", () => {
  it("reports the seat it belongs to", () => {
    const onSelect = vi.fn();
    const { getByTestId } = renderSeat(view([]), { onSelect });
    fireEvent.click(getByTestId("player-1"));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("does nothing while input is gated", () => {
    // Narration playing, or a request in flight. `disabled` rather than a
    // swallowed handler, so the ring can see it is not a destination.
    const onSelect = vi.fn();
    const { getByTestId } = renderSeat(view([]), { onSelect, locked: true });
    fireEvent.click(getByTestId("player-1"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("marks the turn and priority as two different facts", () => {
    /*
     * The shipped ribbon ran them together into one highlighted name, which is
     * wrong in the case that matters most: on somebody else's turn, holding
     * your own priority is the whole of a Commander player's job.
     */
    const { container } = renderSeat(view([]), { isActive: true, hasPriority: false });
    expect(container.querySelector(".seat--active")).not.toBeNull();
    expect(container.querySelector(".seat__pri")).toBeNull();

    cleanup();

    const other = renderSeat(view([]), { isActive: false, hasPriority: true }).container;
    expect(other.querySelector(".seat--active")).toBeNull();
    expect(other.querySelector(".seat__pri")).not.toBeNull();
  });
});

/**
 * Focusing the seat reads their commander, the way hovering its window does.
 *
 * The window's `mouseenter` was the only route into the rail from a seat, and
 * the ring stands on the seat's button rather than inside it -- so on a Deck an
 * opposing commander could be read full screen with `Y` and never in the rail.
 * `data-preview-oid` is what `cursor.ts:hoverFor` reads after it moves focus;
 * the focus handlers are for focus that does not come from the ring.
 */
describe("reading their commander from the seat", () => {
  const withCommander = () =>
    view([], {
      command: [card({ oid: 11, name: "Edgar Markov", is_commander: true, zone: "command" })],
    });

  afterEach(() => {
    resetCursor();
    resetInputMode();
  });

  it("declares the commander for the ring to read", () => {
    const { getByTestId } = renderSeat(withCommander());
    expect(getByTestId("player-1").getAttribute("data-preview-oid")).toBe("11");
  });

  it("declares nothing when there is no commander to read", () => {
    // A missing attribute and not `"undefined"`, which `previewOidFor` would
    // turn into NaN and a stray `0` would turn into a hover on object zero.
    const { getByTestId } = renderSeat(view([]));
    expect(getByTestId("player-1").hasAttribute("data-preview-oid")).toBe(false);
  });

  it("fills the rail when the ring lands on it", async () => {
    noteInput("pad");
    const state = withCommander();
    render(
      <div className="table">
        <OpponentSeat
          state={state}
          player={state.players[1]}
          isActive={false}
          hasPriority={false}
          targetable={false}
        />
      </div>,
    );
    expect(setCursor("orb:1")).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, RAIL_SETTLE + 20));
    expect(useUiStore.getState().hoveredOid).toBe(11);
  });

  it("fills the rail on keyboard focus, and clears it on the way out", () => {
    noteInput("keyboard");
    const onHoverCard = vi.fn();
    const { getByTestId } = renderSeat(withCommander(), { onHoverCard });
    fireEvent.focus(getByTestId("player-1"));
    expect(onHoverCard).toHaveBeenLastCalledWith(11);

    useUiStore.setState({ hoveredOid: 11 });
    fireEvent.blur(getByTestId("player-1"));
    expect(onHoverCard).toHaveBeenLastCalledWith(null);
  });

  it("does not pin the rail when a click is what focused it", () => {
    // A pointer player clicks a seat to read their BOARD; the pointer is on
    // its way to that board, and the window already has its own hover.
    noteInput("mouse");
    const onHoverCard = vi.fn();
    const { getByTestId } = renderSeat(withCommander(), { onHoverCard });
    fireEvent.focus(getByTestId("player-1"));
    expect(onHoverCard).not.toHaveBeenCalled();
  });

  it("leaves a card the pointer has since put in the rail alone on blur", () => {
    // Blur fires on the mousedown of the next click, after that card's own
    // `mouseenter` has written it -- clearing blind would blank it.
    const onHoverCard = vi.fn();
    const { getByTestId } = renderSeat(withCommander(), { onHoverCard });
    useUiStore.setState({ hoveredOid: 42 });
    fireEvent.blur(getByTestId("player-1"));
    expect(onHoverCard).not.toHaveBeenCalled();
  });

  it("still fills the rail from the window on hover", () => {
    const onHoverCard = vi.fn();
    const { container } = renderSeat(withCommander(), { onHoverCard });
    const win = container.querySelector(".seat__win") as HTMLElement;
    fireEvent.mouseEnter(win);
    expect(onHoverCard).toHaveBeenLastCalledWith(11);
    fireEvent.mouseLeave(win);
    expect(onHoverCard).toHaveBeenLastCalledWith(null);
  });
});

describe("energy", () => {
  it("draws nothing for a seat with no energy", () => {
    const { queryByTestId } = renderSeat(view());
    expect(queryByTestId("energy-1")).toBeNull();
  });

  it("shows an opponent's energy beside their name", () => {
    const { getByTestId } = renderSeat(view([], { energy: 6 }));
    const chip = getByTestId("energy-1");
    expect(chip.textContent).toContain("6");
    expect(chip.getAttribute("data-hint")).toBe("6 energy");
  });
});
