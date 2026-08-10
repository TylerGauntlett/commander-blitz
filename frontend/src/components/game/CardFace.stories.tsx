/**
 * The card face, which is the design system's smallest complete statement.
 *
 * Every dimension is a ratio of `--card-w`, so these stories are the first place
 * a broken cascade shows up. `tests/components.test.tsx` already asserts what
 * the face *says* -- the name, the stat line, the crown, the counter badges --
 * and can assert nothing about how it sits, because jsdom never resolves the
 * custom property and the face falls back to a fixed 104px.
 *
 * So what lives here is the other half: the art band and its scrims, the type
 * that has to stay legible over somebody's bright crop, and the colour tones
 * that tell a land from an instant at a glance.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";
import type { CardView } from "../../api/types";
import { CARD_SCALE, cardWidthVar } from "../../logic/cardSize";
import * as pool from "../../testing/cards";
import { card } from "../../testing/fixtures";
import type { CardVariant } from "./CardFace";
import { CardFace } from "./CardFace";

/** How wide the face's box is, per variant. */
const SCALE: Record<CardVariant, number> = {
  board: CARD_SCALE.own,
  detail: CARD_SCALE.peek,
  big: CARD_SCALE.preview,
};

/**
 * Every story draws the face inside a card-shaped slot.
 *
 * `.face` is `width: 100%; height: 100%` and in the app always sits inside
 * `.card`, which is `var(--card-w)` by 1.4 of it. Rendered bare it stretches to
 * whatever holds it -- which still passes every assertion about what it says
 * while looking nothing like a card, so the slot belongs in the story rather
 * than being left out of it.
 */
const meta = {
  title: "Game/CardFace",
  component: CardFace,
  parameters: { automtg: { mount: "bare" } },
  render: (args) => (
    <div
      className="card card--static"
      style={{ ["--card-w" as string]: cardWidthVar(SCALE[args.variant ?? "board"]) }}
    >
      <CardFace {...args} />
    </div>
  ),
} satisfies Meta<typeof CardFace>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Board: Story = {
  args: { card: pool.grizzlyBears() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Grizzly Bears");
    // Art in the "ready" state means the map arrived *and* had a printing --
    // the distinction `logic/cardArt.ts` exists to keep.
    const face = canvasElement.querySelector("[data-art]");
    expect(face?.getAttribute("data-art")).toBe("ready");
  },
};

export const Detail: Story = {
  args: { card: pool.aesi({ zone: "battlefield" }), variant: "detail" },
};

export const Big: Story = {
  args: { card: pool.aesi({ zone: "battlefield" }), variant: "big" },
};

export const Commander: Story = {
  args: { card: pool.aesi({ zone: "battlefield" }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText(/Aesi/);
    expect(canvasElement.querySelector(".face__name .crown")).not.toBeNull();
  },
};

export const Token: Story = { args: { card: pool.krakenToken() } };

/* ------------------------------------------------------------------ */
/* The colour ladder                                                   */
/* ------------------------------------------------------------------ */

/**
 * A grid of faces at card proportions.
 *
 * `.face` is `width: 100%; height: 100%` -- it fills whatever holds it, and in
 * the app that is always `.card`, which is `var(--card-w)` by 1.4 of it. A face
 * dropped straight into a flex row instead stretches to the row and renders as a
 * wide bar: still legible, still passing every content assertion, and nothing
 * like a card. So the slot is part of the story.
 */
function Grid({ cards, variant }: { cards: CardView[]; variant?: CardVariant }) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 12,
        ["--card-w" as string]: cardWidthVar(CARD_SCALE.own),
      }}
    >
      {cards.map((c) => (
        <div key={c.oid} className="card card--static">
          <CardFace card={c} variant={variant} />
        </div>
      ))}
    </div>
  );
}

/** One basic per colour, plus a dual: the tones a land is read by. */
export const Lands: Story = {
  args: { card: pool.forest() },
  render: () => (
    <Grid
      cards={[
        pool.plains({ oid: 1 }),
        pool.island({ oid: 2 }),
        pool.swamp({ oid: 3 }),
        pool.mountain({ oid: 4 }),
        pool.forest({ oid: 5 }),
        pool.breedingPool({ oid: 6 }),
      ]}
    />
  ),
};

/** A card of each type, since type is what the tone and glyph encode. */
export const EveryCardType: Story = {
  args: { card: pool.grizzlyBears() },
  render: () => (
    <Grid
      cards={[
        pool.grizzlyBears({ oid: 1 }),
        pool.counterspell({ oid: 2 }),
        pool.cultivate({ oid: 3 }),
        pool.solRing({ oid: 4 }),
        pool.rhysticStudy({ oid: 5 }),
        pool.rancor({ oid: 6 }),
        pool.swordOfFireAndIce({ oid: 7 }),
        pool.forest({ oid: 8 }),
      ]}
    />
  ),
};

/* ------------------------------------------------------------------ */
/* Battlefield states                                                  */
/* ------------------------------------------------------------------ */

export const Tapped: Story = { args: { card: pool.grizzlyBears({ tapped: true }) } };

export const SummoningSick: Story = {
  args: { card: pool.thragtusk({ summoning_sick: true }) },
};

/** Damage is subtracted from toughness on the battlefield, and only there. */
export const Damaged: Story = {
  args: { card: pool.thragtusk({ damage: 2 }) },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("5/1");
  },
};

export const Counters: Story = {
  args: { card: pool.grizzlyBears({ counters: { "+1/+1": 3, charge: 1 } }) },
};

export const Keywords: Story = {
  args: { card: pool.serraAngel() },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    // Keywords stand in for rules text on the compact face, where prose has no
    // room. Two of them join with a separator rather than wrapping.
    await canvas.findByText("Flying · Vigilance");
  },
};

/**
 * A name with nowhere to go.
 *
 * The face has one line for it and the type must shrink rather than wrap or
 * clip -- which is a measurement, so it can only be checked here.
 */
export const LongName: Story = {
  args: {
    card: card({
      name: "Rasputin Dreamweaver, Keeper of the Seventh Sleep",
      type_line: "Legendary Creature — Human Wizard Advisor",
      mana_cost: "{2}{W}{U}{B}",
    }),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const name = await canvas.findByText(/Rasputin/);
    const face = canvasElement.querySelector(".face") as HTMLElement;
    expect(
      name.getBoundingClientRect().right,
      "the name overflows the card it is printed on",
    ).toBeLessThanOrEqual(face.getBoundingClientRect().right + 1);
  },
};

/* ------------------------------------------------------------------ */
/* Art, in each of its three states                                    */
/* ------------------------------------------------------------------ */

/** Loaded, and this card has no printing: the hatched plate, drawn on purpose. */
export const NoArt: Story = {
  args: { card: pool.krakenToken() },
  parameters: { automtg: { mount: "bare", art: "none" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByText("Kraken");
    expect(canvasElement.querySelector("[data-art]")?.getAttribute("data-art")).toBe("none");
  },
};

/**
 * White type over a bright illustration.
 *
 * The scrims are the only thing keeping this readable, and they are graded --
 * `tests/palette.test.ts` checks the gradient's opaque end clears a darkness
 * floor in the stylesheet, and `e2e/legibility.spec.ts` checks the rendered
 * board. This is the same question posed at the level of one card, where a
 * regression is visible rather than inferred.
 */
export const BrightArt: Story = {
  args: {
    card: pool.serraAngel({
      // A pale, high-key crop is the case the scrims exist for.
      card_id: "bright_test_card_zzz",
      name: "Serra Angel",
    }),
    variant: "detail",
  },
};
