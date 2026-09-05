/**
 * What each button would do, across every decision the game can be in.
 *
 * The bar's whole risk is disagreeing with the board: a hint that says "Attack"
 * where `A` actually withdraws teaches the player a rule the game does not
 * follow, and they find out by pressing something they did not mean. So these
 * stories drive the same fixtures the action panel's do -- if the two ever
 * disagree, they disagree here in one screen rather than in a live game.
 *
 * The second thing to look at is the **Input** toolbar. On Mouse the bar takes
 * no layout at all, which is what keeps the desktop foot the row it has always
 * been; `MouseSeesNothing` asserts that by height rather than by class.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { expectHandheldFloors, settled } from "../../testing/asserts";
import { action, card, gameView, pending, player } from "../../testing/fixtures";
import { HintBar } from "./HintBar";

const bear = (oid: number, name = `Bear ${oid}`) =>
  card({
    oid,
    name,
    types: ["Creature"],
    type_line: "Creature — Bear",
    zone: "battlefield",
    power: 2,
    toughness: 2,
  });

const meta = {
  title: "game/HintBar",
  component: HintBar,
  globals: { input: "pad" },
  parameters: { automtg: { mount: "tableFoot" } },
} satisfies Meta<typeof HintBar>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Priority, with the ring on a castable hand card. */
export const Playing: Story = {
  args: {
    state: gameView({ battlefield: [bear(1, "Skymarcher Aspirant")] }),
    actions: [
      action({ id: "c1", kind: "cast", source_oid: 1, base_label: "Cast Skymarcher" }),
      action({ id: "p", kind: "pass", label: "Pass" }),
    ],
  },
  parameters: { automtg: { mount: "tableFoot", cursor: "card:1" } },
};

/** Declaring attackers: `A` toggles, and `X` appears only with a seat to re-aim at. */
export const DeclaringAttackers: Story = {
  args: {
    state: gameView({
      battlefield: [bear(1)],
      pending: pending({ kind: "declare_attackers", player: 0 }),
      players: [
        player({ pid: 0 }),
        player({ pid: 1, name: "Edgar" }),
        player({ pid: 2, name: "Duelist" }),
      ],
    }),
    actions: [
      action({
        id: "a1",
        kind: "add_attacker",
        source_oid: 1,
        targets: [{ kind: "player", id: 1 }],
      }),
      action({
        id: "a2",
        kind: "add_attacker",
        source_oid: 1,
        targets: [{ kind: "player", id: 2 }],
      }),
    ],
  },
  parameters: { automtg: { mount: "tableFoot", cursor: "card:1" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("hint-bar").textContent).toContain("Attack");
  },
};

/** Blocking: the bar names the creature the block would stop. */
export const DeclaringBlockers: Story = {
  args: {
    state: gameView({
      battlefield: [bear(1), { ...bear(2, "Attacker"), controller: 1, attacking: true }],
      pending: pending({ kind: "declare_blockers", player: 0 }),
    }),
    actions: [
      action({
        id: "b1",
        kind: "add_blocker",
        source_oid: 1,
        targets: [{ kind: "object", id: 2 }],
      }),
    ],
  },
  parameters: { automtg: { mount: "tableFoot", cursor: "card:1" } },
};

/** The ring on the commit slab, where it rests whenever a decision is pending. */
export const OnTheCommitSlab: Story = {
  args: {
    state: gameView(),
    actions: [action({ id: "p", kind: "pass", label: "Pass" })],
  },
  parameters: { automtg: { mount: "tableFoot", cursor: "commit" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("hint-bar").textContent).toContain("Confirm");
  },
};

/**
 * A stop with nothing to do still says so.
 *
 * A bar that goes blank reads as a bar that has broken, and "nothing happens
 * here" is a legitimate thing to tell somebody.
 */
export const NothingToDoHere: Story = {
  args: { state: gameView({ battlefield: [bear(1)] }), actions: [] },
  parameters: { automtg: { mount: "tableFoot", cursor: "card:1" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("hint-bar").textContent).toContain("Read");
  },
};

/** Keyboard mode: every button named with a key the player actually has. */
export const OnAKeyboard: Story = {
  args: {
    state: gameView(),
    actions: [action({ id: "p", kind: "pass", label: "Pass" })],
  },
  globals: { input: "keyboard" },
  parameters: { automtg: { mount: "tableFoot", cursor: "commit" } },
  play: async ({ canvasElement }) => {
    const shown = [...canvasElement.querySelectorAll<HTMLElement>(".glyph")].filter(
      (el) => getComputedStyle(el).display !== "none",
    );
    // No pad-only lettering may survive into keyboard mode: "L2" is a real
    // label on a controller and meaningless to somebody at a keyboard.
    await expect(shown.every((el) => el.classList.contains("glyph--key"))).toBe(true);
  },
};

/** ...and a mouse player gets no bar and, crucially, no row of height for it. */
export const MouseSeesNothing: Story = {
  args: {
    state: gameView(),
    actions: [action({ id: "p", kind: "pass", label: "Pass" })],
  },
  globals: { input: "mouse" },
  parameters: { automtg: { mount: "tableFoot", cursor: "commit" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId("hint-bar").getBoundingClientRect().height).toBe(0);
  },
};

/** The hint bar at 1280 wide: the verbs stay legible. */
export const PlayingHandheld: Story = {
  args: Playing.args,
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    await settled(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};
