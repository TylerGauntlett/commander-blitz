/**
 * Every button, in every input mode, on one page.
 *
 * The requirement this exists to review is a single sentence -- "a mouse player
 * never sees a controller hint" -- and it is the kind of thing that is either
 * obviously right or obviously wrong at a glance and almost impossible to
 * verify by reading the CSS. Switch the **Input** toolbar between Mouse,
 * Keyboard and Gamepad: the grid should go blank, then show key names, then
 * show A/B/X/Y.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { PAD_LABEL, type PadButton } from "../../input/buttons";
import { Glyph } from "./Glyph";

const ALL = Object.keys(PAD_LABEL) as PadButton[];

const meta = {
  title: "ui/Glyph",
  component: Glyph,
  parameters: { commanderblitz: { mount: "bare" } },
} satisfies Meta<typeof Glyph>;

export default meta;
type Story = StoryObj<typeof meta>;

function Row({ btn }: { btn: PadButton }) {
  return (
    <span
      style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 120 }}
      data-testid={`row-${btn}`}
    >
      <Glyph btn={btn} />
      <span style={{ color: "var(--text-dim)", fontSize: 12 }}>{btn}</span>
    </span>
  );
}

/** All sixteen buttons plus the d-pad, at whatever the toolbar is set to. */
export const EveryButton: Story = {
  args: { btn: "a" },
  render: () => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      <Row btn={"dpad" as PadButton} />
      {ALL.map((btn) => (
        <Row key={btn} btn={btn} />
      ))}
    </div>
  ),
};

/**
 * The one that matters: a mouse player sees nothing.
 *
 * Asserted by *height*, not by a class. `display: none` is the mechanism today,
 * but what the requirement actually says is "costs the player nothing", and a
 * glyph that was merely transparent would still push the foot's row taller.
 */
export const MouseSeesNothing: Story = {
  args: { btn: "a" },
  globals: { input: "mouse" },
  render: () => (
    <div data-testid="glyphs">
      <Glyph btn="a" />
      <Glyph btn="b" />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const box = canvas.getByTestId("glyphs").getBoundingClientRect();
    await expect(box.height).toBe(0);
  },
};

/** A controller player sees the pad's own lettering, and only that. */
export const PadShowsPadLabels: Story = {
  args: { btn: "a" },
  globals: { input: "pad" },
  render: () => (
    <div data-testid="glyphs">
      <Glyph btn="a" />
      <Glyph btn="l1" />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const shown = [...canvasElement.querySelectorAll<HTMLElement>(".glyph")].filter(
      (el) => getComputedStyle(el).display !== "none",
    );
    await expect(shown.map((el) => el.textContent)).toEqual(["A", "L1"]);
  },
};

/**
 * A keyboard player sees keys they actually have.
 *
 * "L2" is a real label on a pad and a meaningless one at a keyboard -- this is
 * the story that caught it reading `L2 Menu` to somebody with no controller.
 */
export const KeyboardShowsKeys: Story = {
  args: { btn: "a" },
  globals: { input: "keyboard" },
  render: () => (
    <div data-testid="glyphs">
      <Glyph btn="a" />
      <Glyph btn="b" />
      <Glyph btn="l2" />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const shown = [...canvasElement.querySelectorAll<HTMLElement>(".glyph")].filter(
      (el) => getComputedStyle(el).display !== "none",
    );
    await expect(shown.map((el) => el.textContent)).toEqual(["Enter", "Esc", "Z"]);
  },
};
