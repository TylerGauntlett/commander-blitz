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
import * as pool from "../../testing/cards";
import { card } from "../../testing/fixtures";
import { CardFace } from "./CardFace";

const meta = {
  title: "Game/CardFace",
  component: CardFace,
  parameters: { automtg: { frame: "bare" } },
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

function Grid({ cards }: { cards: CardView[] }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      {cards.map((c) => (
        <CardFace key={c.oid} card={c} />
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
  parameters: { automtg: { frame: "bare", art: "none" } },
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
