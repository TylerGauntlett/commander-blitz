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
import { settled } from "../../testing/asserts";
import { cardResponse } from "../../testing/fixtures";
import * as pods from "../../testing/pods";
import { CardBack } from "./CardBack";
import { CommanderCard } from "./CommanderCard";
import { InviteDialog } from "./InviteDialog";
import { ReadyTrack } from "./ReadyTrack";

const AESI = "aesi_tyrant_of_gyre_strait";

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
  parameters: { automtg: { mount: "podRail" } },
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.filling()} />,
};

export const ReadyTrackComplete: Story = {
  parameters: { automtg: { mount: "podRail" } },
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.ready()} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const track = await canvas.findByTestId("ready-track");
    // The words that stood in front of the number -- "Cards face up" -- are off
    // the screen and on the `aria-label`, which is the only reader they were
    // ever for: the pips sit directly under four cards, half of which are
    // visibly face up.
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("4/4");
    expect(track.getAttribute("aria-label")).toBe("4 of 4 cards face up");
  },
};

/** Three seats, so the denominator is three. */
export const ReadyTrackThreeHanded: Story = {
  parameters: { automtg: { mount: "podRail" } },
  args: { mark: "" },
  render: () => <ReadyTrack pod={pods.threeHanded()} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const track = await canvas.findByTestId("ready-track");
    expect(track.textContent?.replace(/\s+/g, " ")).toContain("/3");
    expect(track.getAttribute("aria-label")).toContain("of 3");
  },
};

/* ------------------------------------------------------------------ */
/* InviteDialog                                                        */
/* ------------------------------------------------------------------ */

export const Invite: Story = {
  parameters: { automtg: { mount: "screen" } },
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
  parameters: { automtg: { mount: "screen" } },
  args: { mark: "" },
  render: () => <InviteDialog pod={pods.ready()} onClose={fn()} onOpenChair={fn()} />,
};

export const InviteOpensAChair: Story = {
  parameters: { automtg: { mount: "screen" } },
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
 * The same component, in its three homes, at three different sizes.
 *
 * `CommanderCard` has no width of its own: it inherits `--card-w` from whichever
 * container it lands in, and the three differ by more than a factor of two --
 * a chair is `208px * --du`, a catalogue tile `clamp(122px, 150px * --du,
 * 172px)`, the dossier `clamp(150px, 22vh, 214px)`. One story at the 104px
 * `@property` fallback showed a size the app never draws.
 */
export const CommanderInASeat: Story = {
  args: { mark: "" },
  parameters: {
    automtg: { mount: "podSlot", query: [[["card", AESI], cardResponse()]] },
  },
  render: () => <CommanderCard cardId={AESI} variant="big" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    // Relational, for the reason the catalogue story explains.
    const seat = canvasElement.querySelector(".podcard") as HTMLElement;
    await settled(seat);
    const handed = Number.parseFloat(getComputedStyle(seat).getPropertyValue("--card-w"));
    expect(seat.getBoundingClientRect().width).toBeCloseTo(handed, 0);
  },
};

export const CommanderInTheCatalogue: Story = {
  args: { mark: "" },
  parameters: {
    automtg: { mount: "catalogPick", query: [[["card", AESI], cardResponse()]] },
  },
  render: () => <CommanderCard cardId={AESI} variant="board" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    const card = canvasElement.querySelector(".card") as HTMLElement;
    // Waited for: the card animates in, and measured on the way it reads 127px
    // of an eventual 135. Only in a full run, where the machine is busy enough
    // for the first frame to be the one sampled -- the worst kind of flake.
    await settled(card);

    /*
     * Asserted as a relationship, not an absolute. `--card-w` here is
     * `clamp(122px, 15vh, 168px)` and `vh` is the preview iframe's height, which
     * the runner is still settling while the first frame paints -- so a literal
     * is right in the browser and briefly wrong in the runner. "The card is the
     * width its container handed it" holds in both.
     */
    const handed = Number.parseFloat(getComputedStyle(card).getPropertyValue("--card-w"));
    expect(card.getBoundingClientRect().width).toBeCloseTo(handed, 0);

    /*
     * The corner radius is a ratio of the card's width, and `.rack` was the one
     * container that set `--card-w` without re-deriving `--card-r` from it --
     * `.podhand` and `.dos__top` both do, and both say why. So a catalogue card
     * rounded at the *board's* radius while every other card in the lobby rounded
     * proportionally. Nothing says so except the corners.
     */
    const radius = Number.parseFloat(
      getComputedStyle(card.querySelector(".face") as HTMLElement).borderTopLeftRadius,
    );
    expect(
      radius,
      "the catalogue card rounds at the board's radius, not its own width",
    ).toBeCloseTo(handed * 0.055, 0);
  },
};

export const CommanderInTheDossier: Story = {
  args: { mark: "" },
  parameters: {
    automtg: { mount: "dossierCard", query: [[["card", AESI], cardResponse()]] },
  },
  render: () => <CommanderCard cardId={AESI} variant="big" />,
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
  parameters: { automtg: { mount: "podSlot" } },
  render: () => <CommanderCard cardId="not_seeded_yet" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("card-loading");
  },
};

/** No card at all, which is a seat with no deck. */
export const CommanderAbsent: Story = {
  args: { mark: "" },
  parameters: { automtg: { mount: "podSlot" } },
  render: () => <CommanderCard cardId={null} placeholder="No deck" />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("No deck");
  },
};
