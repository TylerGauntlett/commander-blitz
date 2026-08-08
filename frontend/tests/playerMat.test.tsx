/**
 * The board's arrangement, asserted where a screenshot cannot fail a build.
 *
 * Two things here have no other coverage. The band order is a *rendered* fact
 * -- `LANES` declares it, but only the mat turns that into DOM order, and the
 * mirrored variant exists nowhere else. And the tucked aura is a whole feature
 * that no card in the shipped decks can currently produce: the engine sets
 * `attached_to` (see `engine/primitives.py`), but neither precon contains an
 * Aura or an Equipment, so nothing but this file exercises the path until the
 * card catalogue grows.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CardView } from "../src/api/types";
import { PlayerMat } from "../src/components/game/PlayerMat";
import { card, gameView, player } from "./fixtures";

afterEach(cleanup);

const NO_OIDS: ReadonlySet<number> = new Set();

function renderMat(
  battlefield: CardView[],
  props: { mirrored?: boolean; compact?: boolean } = {},
) {
  const state = gameView({ battlefield });
  return render(
    <PlayerMat
      state={state}
      player={player()}
      names={["You", "AI 1"]}
      cardScale={1}
      actionableOids={NO_OIDS}
      {...props}
    />,
  );
}

/** The lanes in the order they appear in the document. */
const laneOrder = (container: HTMLElement) =>
  [...container.querySelectorAll(".lane")].map((node) =>
    node.getAttribute("data-testid")?.replace("lane-0-", ""),
  );

describe("PlayerMat bands", () => {
  it("puts the viewer's lands last, nearest their own hand", () => {
    const { container } = renderMat([]);
    expect(laneOrder(container)).toEqual(["Creatures", "Artifacts-Enchantments", "Lands"]);
  });

  it("mirrors an opponent, so their lands sit against their own edge", () => {
    // This is what puts the two creature bands either side of the table's
    // midline. Without it combat is declared diagonally past a wall of mana.
    const { container } = renderMat(
      [card({ oid: 1, types: ["Creature"] }), card({ oid: 2, types: ["Land"] })],
      { mirrored: true, compact: true },
    );
    expect(laneOrder(container)).toEqual(["Lands", "Creatures", "Artifacts-Enchantments"]);
  });

  it("shares one band between the creatures and the global permanents", () => {
    const { container } = renderMat([]);
    const front = container.querySelector(".band--front");
    expect(front?.querySelectorAll(".lane")).toHaveLength(2);
    expect(container.querySelector(".band--back")?.querySelectorAll(".lane")).toHaveLength(1);
  });

  /*
   * Every lane is rendered on every mat whether or not it holds anything, and
   * an empty one keeps its full card height (board.css). Together those two are
   * the whole reason a mat is a fixed height -- and a fixed height is the whole
   * reason the board stops moving when a permanent enters or leaves.
   */
  it("keeps all three lanes for the viewer even when empty", () => {
    const { container } = renderMat([]);
    expect(container.querySelectorAll(".lane")).toHaveLength(3);
  });

  it("keeps all three for an opponent too, so their first creature moves nothing", () => {
    // Dropping their empty lanes grew the opponents row when they played
    // something, which pushed *your* board down the screen on somebody else's
    // turn.
    const { container } = renderMat([card({ oid: 1, types: ["Land"] })], {
      mirrored: true,
      compact: true,
    });
    expect(container.querySelectorAll(".lane")).toHaveLength(3);
    expect(container.querySelector(".band--front")).not.toBeNull();
  });

  it("renders the same lanes in the same order whether the board is empty or full", () => {
    const empty = laneOrder(renderMat([]).container);
    cleanup();
    const full = laneOrder(
      renderMat([
        card({ oid: 1, types: ["Creature"] }),
        card({ oid: 2, types: ["Land"] }),
        card({ oid: 3, types: ["Artifact"] }),
      ]).container,
    );
    expect(full).toEqual(empty);
  });
});

describe("PlayerMat attachments", () => {
  const bear = card({ oid: 1, name: "Grizzly Bears", types: ["Creature"] });
  const aura = card({
    oid: 9,
    name: "Rancor",
    card_id: "rancor",
    types: ["Enchantment"],
    subtypes: ["Aura"],
    attached_to: 1,
    power: null,
    toughness: null,
  });

  it("draws an aura inside its host's stack, not loose in the global lane", () => {
    const { container } = renderMat([bear, aura]);
    const creatures = container.querySelector('[data-testid="lane-0-Creatures"]');
    const globals = container.querySelector('[data-testid="lane-0-Artifacts-Enchantments"]');
    expect(creatures?.querySelector('[data-card-name="Rancor"]')).not.toBeNull();
    expect(globals?.querySelector('[data-card-name="Rancor"]')).toBeNull();
    expect(container.querySelector(".cardstack__attach")).not.toBeNull();
  });

  it("keeps the aura its own card, so it can still be read and clicked", () => {
    const { container } = renderMat([bear, aura]);
    expect(container.querySelector('[data-testid="card-9"]')).not.toBeNull();
  });

  it("never merges an enchanted permanent into a stack with a bare copy", () => {
    // The stack would hide the aura, and with it a whole permanent.
    const { container } = renderMat([bear, card({ oid: 2, name: "Grizzly Bears" }), aura]);
    const stacks = container.querySelectorAll('[data-testid="lane-0-Creatures"] .cardstack');
    expect(stacks).toHaveLength(2);
  });

  it("leaves an aura on somebody else's creature loose in its own lane", () => {
    const theirs = card({ oid: 1, controller: 1, types: ["Creature"] });
    const mine = { ...aura, attached_to: 1 };
    const { container } = renderMat([theirs, mine]);
    expect(container.querySelector(".cardstack__attach")).toBeNull();
    expect(
      container
        .querySelector('[data-testid="lane-0-Creatures"]')
        ?.querySelector('[data-card-name="Rancor"]'),
    ).not.toBeNull();
  });
});
