/**
 * The lobby's small parts: the card back, the ready track, the invite dialog and
 * the commander card that adapts a printed card into a face.
 *
 * They are grouped because each is a handful of states and none of them is worth
 * a file of its own -- but the card back in particular has to be checked, because
 * its whole job is to look the same in three situations that must never *test*
 * the same.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { CardBack } from "./CardBack";
import { CommanderCard } from "./CommanderCard";
import { InviteDialog } from "./InviteDialog";
import { ReadyTrack } from "./ReadyTrack";

const meta = {
  title: "Lobby/Parts",
  component: CardBack,
  parameters: { automtg: { mount: "bare" } },
} satisfies Meta<typeof CardBack>;

export default meta;
type Story = StoryObj<typeof meta>;

/* ------------------------------------------------------------------ */
/* CardBack                                                            */
/* ------------------------------------------------------------------ */

/**
 * The three backs, side by side.
 *
 * A sealed deck, a chair held open, and an empty chair. They are one picture for
 * three different facts, which is the point -- so `data-tone` is what tells them
 * apart, and it is the only thing that should.
 */
export const CardBacks: Story = {
  args: { mark: "Sealed" },
  render: () => (
    <div style={{ display: "flex", gap: 12 }}>
      <CardBack mark="Sealed" testId="back-sealed" />
      <CardBack mark="Open" tone="open" testId="back-open" />
      <CardBack mark="Empty" tone="empty" testId="back-empty" />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect((await canvas.findByTestId("back-sealed")).dataset.tone).toBe("sealed");
    expect((await canvas.findByTestId("back-open")).dataset.tone).toBe("open");
    expect((await canvas.findByTestId("back-empty")).dataset.tone).toBe("empty");
  },
};

/* ------------------------------------------------------------------ */
/* ReadyTrack                                                          */
/* ------------------------------------------------------------------ */

export const ReadyTrackPartial: Story = {
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.filling()} />,
};

export const ReadyTrackComplete: Story = {
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.ready()} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const track = await canvas.findByTestId("ready-track");
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("4 of 4");
  },
};

/** Three seats, so the denominator is three. */
export const ReadyTrackThreeHanded: Story = {
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.threeHanded()} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const track = await canvas.findByTestId("ready-track");
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("of 3");
  },
};

/* ------------------------------------------------------------------ */
/* InviteDialog                                                        */
/* ------------------------------------------------------------------ */

export const Invite: Story = {
  args: { mark: "" },
  render: () => <InviteDialog pod={pods.filling()} onClose={fn()} onOpenChair={fn()} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // The code is on screen in large type either way -- copying is a
    // convenience, because clipboard access is refused outside a secure
    // context and this runs over plain HTTP on a LAN.
    await canvas.findByText("GYRE-8412");
  },
};

/** No chairs open: inviting somebody needs one, so the dialog offers to make it. */
export const InviteWithNoOpenChairs: Story = {
  args: { mark: "" },
  render: () => <InviteDialog pod={pods.ready()} onClose={fn()} onOpenChair={fn()} />,
};

export const InviteOpensAChair: Story = {
  args: { mark: "" },
  render: function Render() {
    const onOpenChair = fn();
    return <InviteDialog pod={pods.ready()} onClose={fn()} onOpenChair={onOpenChair} />;
  },
};

/* ------------------------------------------------------------------ */
/* CommanderCard                                                       */
/* ------------------------------------------------------------------ */

/**
 * A printed card, adapted into a `CardView` so `CardFace` can draw it outside a
 * game. The seeded query is what makes it arrive on first paint.
 */
export const CommanderLoaded: Story = {
  args: { mark: "" },
  parameters: {
    automtg: {
      mount: "bare",
      query: [[["card", "aesi_tyrant_of_gyre_strait"], cardResponse()]],
    },
  },
  render: () => <CommanderCard cardId="aesi_tyrant_of_gyre_strait" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
  },
};

/**
 * Still loading.
 *
 * Drawn as a back with its own test id: "there is nothing here yet" and "you are
 * not allowed to see this" look the same on purpose, and must not test the same.
 */
export const CommanderLoading: Story = {
  args: { mark: "" },
  render: () => <CommanderCard cardId="not_seeded_yet" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("card-loading");
  },
};

/** No card at all, which is a seat with no deck. */
export const CommanderAbsent: Story = {
  args: { mark: "" },
  render: () => <CommanderCard cardId={null} placeholder="No deck" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("No deck");
  },
};
