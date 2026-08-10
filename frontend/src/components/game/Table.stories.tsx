/**
 * The whole board.
 *
 * This is the story that proves the harness. Every other component can look
 * plausible in a box; `Table` is the one whose correctness *is* its geometry --
 * the zoom solver measures three grid tracks, the hand fans against
 * `--card-w-base`, and the lanes band by distance from the player they belong
 * to. If this renders at sane card sizes, the cascade reached the canvas.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { fakeGame } from "../../testing/fakeGame";
import { action, card, gameView, player } from "../../testing/fixtures";
import { Table } from "./Table";

/** Seven cards, one land drop, nothing on the board yet. */
function openingHand() {
  const hand = [
    card({
      oid: 101,
      zone: "hand",
      card_id: "forest",
      name: "Forest",
      type_line: "Basic Land — Forest",
      mana_cost: "",
      mana_value: 0,
      types: ["Land"],
      supertypes: ["Basic"],
      subtypes: ["Forest"],
      produces: ["G"],
      colors: [],
      power: null,
      toughness: null,
    }),
    card({
      oid: 102,
      zone: "hand",
      card_id: "island",
      name: "Island",
      type_line: "Basic Land — Island",
      mana_cost: "",
      mana_value: 0,
      types: ["Land"],
      supertypes: ["Basic"],
      subtypes: ["Island"],
      produces: ["U"],
      colors: [],
      power: null,
      toughness: null,
    }),
    card({
      oid: 103,
      zone: "hand",
      card_id: "llanowar_elves",
      name: "Llanowar Elves",
      type_line: "Creature — Elf Druid",
      mana_cost: "{G}",
      mana_value: 1,
      power: 1,
      toughness: 1,
      subtypes: ["Elf", "Druid"],
    }),
    card({
      oid: 104,
      zone: "hand",
      card_id: "cultivate",
      name: "Cultivate",
      type_line: "Sorcery",
      mana_cost: "{2}{G}",
      mana_value: 3,
      types: ["Sorcery"],
      subtypes: [],
      power: null,
      toughness: null,
      oracle_text: "Search your library for up to two basic land cards.",
    }),
    card({
      oid: 105,
      zone: "hand",
      card_id: "counterspell",
      name: "Counterspell",
      type_line: "Instant",
      mana_cost: "{U}{U}",
      mana_value: 2,
      types: ["Instant"],
      subtypes: [],
      colors: ["U"],
      power: null,
      toughness: null,
      oracle_text: "Counter target spell.",
    }),
    card({
      oid: 106,
      zone: "hand",
      card_id: "sol_ring",
      name: "Sol Ring",
      type_line: "Artifact",
      mana_cost: "{1}",
      mana_value: 1,
      types: ["Artifact"],
      subtypes: [],
      colors: [],
      power: null,
      toughness: null,
      produces: ["C"],
    }),
    card({
      oid: 107,
      zone: "hand",
      card_id: "thragtusk",
      name: "Thragtusk",
      type_line: "Creature — Beast",
      mana_cost: "{4}{G}",
      mana_value: 5,
      power: 5,
      toughness: 3,
      subtypes: ["Beast"],
    }),
  ];

  const commander = card({
    oid: 1,
    zone: "command",
    card_id: "aesi_tyrant_of_gyre_strait",
    name: "Aesi, Tyrant of Gyre Strait",
    type_line: "Legendary Creature — Serpent",
    mana_cost: "{4}{G}{U}",
    mana_value: 6,
    colors: ["G", "U"],
    power: 5,
    toughness: 5,
    subtypes: ["Serpent"],
    supertypes: ["Legendary"],
    is_commander: true,
  });

  const state = gameView({
    players: [
      player({ hand, hand_count: hand.length, library_count: 92, command: [commander] }),
      player({
        pid: 1,
        name: "AI 1",
        deck_id: "edgar",
        hand: null,
        hand_count: 7,
        library_count: 92,
        hand_reasons: null,
      }),
    ],
  });

  // The client never builds an action; it echoes an id back. So a story's action
  // list has to be one the engine could plausibly have sent for this position.
  const actions = [
    action({ id: "a0-pass", kind: "pass", label: "Pass", base_label: "Pass" }),
    action({
      id: "a1-play_land",
      kind: "play_land",
      label: "Play Forest",
      base_label: "Play Forest",
      source_oid: 101,
    }),
    action({
      id: "a2-play_land",
      kind: "play_land",
      label: "Play Island",
      base_label: "Play Island",
      source_oid: 102,
    }),
  ];

  return { state, actions };
}

const meta = {
  title: "Game/Table",
  component: Table,
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

export const OpeningHand: Story = {
  args: (() => {
    const { state, actions } = openingHand();
    return {
      session: { gameId: "story", seat: 0 },
      state,
      game: fakeGame({ state, actions }),
      onQuit: () => undefined,
      onRematch: () => undefined,
    };
  })(),

  /*
   * The harness's own test.
   *
   * Nothing here is about the board's behaviour -- it is about whether the
   * cascade reached the canvas at all. If `#storybook-root` has no height, or
   * `theme.css` did not load, or `@property --card-w-base` failed to register,
   * the symptom is identical in every case: `useZoomFit` measures nothing and
   * every card collapses to the solver's 52px floor. That is a board of postage
   * stamps that still passes every content assertion ever written about it, so
   * it gets an assertion of its own.
   */
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const base = Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--card-w-base"),
    );
    expect(
      base,
      "--card-w-base must resolve to real pixels, not the clamp() text",
    ).toBeGreaterThan(60);

    const hand = canvasElement.querySelectorAll(".hand .card");
    expect(hand).toHaveLength(7);
    const width = hand[0].getBoundingClientRect().width;
    expect(
      width,
      "a card at the solver's 52px floor means the zoom measured nothing",
    ).toBeGreaterThan(60);
  },
};
