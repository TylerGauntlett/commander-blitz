/**
 * The deck detail overlay.
 *
 * Half of what it shows is authored per deck and half is derived from the card
 * list. An imported deck has none of the first half, and the design point is
 * that it *says so* rather than inventing a strategy paragraph or drawing a flat
 * rating bar -- so most of the interesting stories are the absent cases.
 *
 * `tests/deckDossier.test.tsx` covers the same ground in jsdom. What is added
 * here is the rating bars and the mana curve as drawn things: both are pure
 * geometry, and a curve whose columns are all the same height reads as data.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";
import { deckDetail } from "../../testing/fixtures";
import { DeckDossier, ManaCurve, RatingBar } from "./DeckDossier";

const precon = deckDetail();
const imported = deckDetail({
  id: "mine",
  name: "Zada Storm",
  source: "moxfield",
  tags: [],
  ratings: null,
  strategy: "",
  signature: [],
  notes: "",
  simplified: 12,
  swaps: 0,
  swap_note: "",
});

const meta = {
  title: "Lobby/DeckDossier",
  component: DeckDossier,
  parameters: { automtg: { mount: "screen" } },
  args: { canTake: true, onTake: fn(), onClose: fn() },
} satisfies Meta<typeof DeckDossier>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A fully authored precon: ratings, a write-up, signature cards. */
export const Precon: Story = {
  args: { deckId: precon.id },
  parameters: { automtg: { query: [[["deck", precon.id], precon]] } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("dossier-ratings");
    await canvas.findByTestId("curve");
    await canvas.findByText(/first four turns/);
  },
};

/**
 * An imported deck, which has none of the editorial half.
 *
 * Every absence is stated rather than blank, and the curve still draws because
 * it is derived rather than authored.
 */
export const Imported: Story = {
  args: { deckId: imported.id },
  parameters: { automtg: { query: [[["deck", imported.id], imported]] } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("dossier-no-ratings");
    await canvas.findByTestId("dossier-no-signature");
    // Derived, not authored, so it survives the import.
    await canvas.findByTestId("curve");
    expect(canvas.queryByTestId("dossier-ratings")).toBeNull();
  },
};

/** Nothing swapped: said outright, rather than by omission. */
export const NothingSwapped: Story = {
  args: { deckId: "clean" },
  parameters: {
    automtg: {
      query: [[["deck", "clean"], deckDetail({ id: "clean", swaps: 0, swap_note: "" })]],
    },
  },
};

/** Opened while browsing rather than from a seat: no take button. */
export const CannotTake: Story = {
  args: { deckId: precon.id, canTake: false },
  parameters: { automtg: { query: [[["deck", precon.id], precon]] } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("curve");
    expect(canvas.queryByTestId("dossier-take")).toBeNull();
  },
};

/* ------------------------------------------------------------------ */
/* The two drawn parts, on their own                                   */
/* ------------------------------------------------------------------ */

/**
 * The rating bar.
 *
 * Four segments, N filled. The bar is the whole signal visually, so it also
 * says the number out loud -- without that the rating is simply absent for
 * anybody not looking at it.
 */
export const Ratings: Story = {
  args: { deckId: precon.id },
  parameters: { automtg: { mount: "bare" } },
  render: () => (
    <div style={{ display: "grid", gap: 8, maxWidth: 320 }}>
      <RatingBar label="Speed" value={1} />
      <RatingBar label="Complexity" value={2} />
      <RatingBar label="Interaction" value={3} />
      <RatingBar label="Resilience" value={4} />
    </div>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByLabelText("Speed: 1 of 4");
    expect(canvasElement.querySelectorAll(".bar__seg--on")).toHaveLength(1 + 2 + 3 + 4);
  },
};

/** The curve, tallest column at full height. */
export const Curve: Story = {
  args: { deckId: precon.id },
  parameters: { automtg: { mount: "bare" } },
  render: () => <ManaCurve values={[9, 13, 18, 7, 7, 3, 5]} />,
  play: async ({ canvasElement }) => {
    const bars = [...canvasElement.querySelectorAll<HTMLElement>(".curve__bar")];
    expect(bars).toHaveLength(7);
    // The tallest bucket defines the scale, so it is the one at 100%.
    expect(bars[2].style.height).toBe("100%");
    // And the columns must actually differ, or the chart is decoration.
    const heights = new Set(bars.map((b) => b.style.height));
    expect(heights.size).toBeGreaterThan(3);
  },
};

/** No curve at all: said, rather than drawn as a flat line. */
export const EmptyCurve: Story = {
  args: { deckId: precon.id },
  parameters: { automtg: { mount: "bare" } },
  render: () => <ManaCurve values={[]} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("curve-empty");
  },
};
