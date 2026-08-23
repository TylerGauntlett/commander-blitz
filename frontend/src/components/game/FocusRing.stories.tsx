/**
 * The ring, and the one property that silently breaks.
 *
 * `outline-width` and `outline-style` are separate properties, and a bare
 * `:focus { outline: none }` anywhere in the document leaves the first at 3px
 * while zeroing the second -- so the ring computes healthily, shows as applied
 * in devtools, and draws nothing. `tests/focusOutline.test.ts` greps for the
 * pattern; this measures the rendered result, which is the half a grep cannot
 * do.
 *
 * Use the **Input** toolbar to see the ring appear and disappear: a mouse
 * player has a pointer to say where they are and gets no ring at all.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import { FocusRing } from "./FocusRing";

const meta = {
  title: "game/FocusRing",
  component: FocusRing,
  args: { context: "story" },
  parameters: { automtg: { mount: "bare" } },
} satisfies Meta<typeof FocusRing>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Three stops in a row, so the ring has somewhere to be and somewhere to go. */
function Stops() {
  return (
    <div style={{ display: "flex", gap: 16, padding: 24 }}>
      {["one", "two", "three"].map((id) => (
        <button
          key={id}
          type="button"
          className="btn"
          data-stop={`tool:${id}`}
          data-testid={`stop-${id}`}
        >
          {id}
        </button>
      ))}
    </div>
  );
}

export const OnAControl: Story = {
  globals: { input: "pad" },
  parameters: { automtg: { mount: "bare", cursor: "tool:two" } },
  render: (args) => (
    <>
      <Stops />
      <FocusRing {...args} />
    </>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const marked = canvasElement.ownerDocument.querySelectorAll("[data-cursor]");
    await expect(marked.length).toBe(1);

    const cur = canvas.getByTestId("stop-two");
    const style = getComputedStyle(cur);
    // Both halves. The width alone passes against the exact bug this guards.
    await expect(Number.parseFloat(style.outlineWidth)).toBeGreaterThanOrEqual(3);
    await expect(style.outlineStyle).not.toBe("none");
  },
};

/**
 * FILL IS FOCUS: the control the ring is on fills, and the others do not.
 *
 * The argument is that a 3px outline on a 7-inch panel at arm's length is a
 * hairline the eye has to hunt for, and a filled control is not.
 */
export const FillIsFocus: Story = {
  globals: { input: "pad" },
  parameters: { automtg: { mount: "bare", cursor: "tool:two" } },
  render: (args) => (
    <>
      <Stops />
      <FocusRing {...args} />
    </>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const on = getComputedStyle(canvas.getByTestId("stop-two")).backgroundColor;
    const off = getComputedStyle(canvas.getByTestId("stop-one")).backgroundColor;
    await expect(on).not.toBe(off);
  },
};

/** A mouse player gets no ring: the outline is suppressed even on the cursor. */
export const MouseHasNoRing: Story = {
  globals: { input: "mouse" },
  parameters: { automtg: { mount: "bare", cursor: "tool:two" } },
  render: (args) => (
    <>
      <Stops />
      <FocusRing {...args} />
    </>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(getComputedStyle(canvas.getByTestId("stop-two")).outlineStyle).toBe("none");
  },
};
