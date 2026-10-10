/**
 * The region dial, held open on a shoulder.
 *
 * The dial reads the document to decide which spokes to draw -- a region with
 * nothing to land on is not a destination -- so the story stands three regions
 * up around it, each holding one stop. What the browser adds to the jsdom
 * tests is the geometry: on a Deck every spoke is a thumb target.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useState } from "react";
import { expect, fn, within } from "storybook/test";
import { expectHandheldFloors, expectHitFloor, settled } from "../../testing/asserts";
import { GroupDial } from "./GroupDial";

/** Three regions, each with a stop the dial can see -- laid out, so they are visible. */
function Regions() {
  const region = (className: string, stop: string, inner?: string) => (
    <div className={className} style={{ width: 140, height: 60 }}>
      <div className={inner}>
        <button type="button" data-stop={stop} style={{ width: 120, height: 44 }}>
          {stop}
        </button>
      </div>
    </div>
  );
  return (
    <div style={{ display: "flex", gap: 16, padding: 16 }}>
      {region("hand", "card:1")}
      {region("rail rail--right", "act:a1")}
      {region("play__mine", "card:2", "mat__lanes")}
    </div>
  );
}

const meta = {
  title: "Game/GroupDial",
  component: GroupDial,
  parameters: { commanderblitz: { mount: "bare" } },
  args: { current: "hand", onPick: fn() },
  decorators: [
    (Story) => {
      /*
       * The dial reads the document when it renders, so the regions have to be
       * IN the document first -- a sibling rendered in the same commit is not.
       * `Table` opens the dial on a hold, long after the board is up; this
       * reproduces that order.
       */
      const [ready, setReady] = useState(false);
      useEffect(() => setReady(true), []);
      return (
        <>
          <Regions />
          {ready && <Story />}
        </>
      );
    },
  ],
} satisfies Meta<typeof GroupDial>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const spokes = await canvas.findAllByRole("button", { name: /Hand|Actions|Board/ });
    expect(spokes.map((s) => s.textContent)).toEqual(["Hand", "Actions", "Board"]);
    expect(canvasElement.querySelector(".wheelwrap")).not.toBeNull();
    // The spoke for the region you are in is the resting one.
    expect(canvasElement.querySelector(".wheel__spoke--here")?.textContent).toBe("Hand");
    // The dial scales in from 0.94; a spoke measured mid-flight is under the floor.
    const wheel = canvasElement.querySelector(".wheel") as HTMLElement;
    await settled(wheel);
    expectHitFloor(wheel);
    spokes[2].click();
    expect(args.onPick).toHaveBeenCalledWith("board");
  },
};

export const OpenHandheld: Story = {
  globals: { handheld: "on" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByRole("button", { name: "Board" });
    const wheel = canvasElement.querySelector(".wheel") as HTMLElement;
    await settled(wheel);
    expectHandheldFloors(wheel);
  },
};
