/**
 * The mana symbols, as published artwork rather than letters on discs.
 *
 * `AllSymbols` is the story that earns its keep: 54 SVGs are vendored into
 * `public/symbols/`, every cost row on every card resolves against them, and a
 * missing file fails silently -- a broken `<img>` still occupies its box, so a
 * card with a gap in its cost renders at exactly the right size. Drawing the
 * whole set on one page makes that a thing you can see.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor, within } from "storybook/test";
import { ManaSymbol } from "./ManaSymbol";

/*
 * Every code with a vendored SVG.
 *
 * Written in the printed notation -- `{W/U}`, not `W-U`. The slash is what the
 * oracle text carries and what `hasSymbol` knows; `symbolFile` is what turns it
 * into `W-U.svg`, because a slash cannot be a filename on Windows. Spelling
 * these the file's way is a real mistake to make, and it degrades quietly: the
 * pip falls back to rendering its own code as text and still occupies its box.
 *
 * The hybrids are in Scryfall's *guild* order, and three of them run backwards
 * against WUBRG -- there is no `{W/R}`, `{W/G}` or `{U/G}` to fetch. That is
 * recorded at length in `logic/manaSymbols.ts`, which got it wrong once.
 */
const GENERIC = [...Array.from({ length: 17 }, (_, n) => String(n)), "X"];
const COLOURS = ["W", "U", "B", "R", "G", "C"];
const HYBRID = ["W/U", "W/B", "U/B", "U/R", "B/R", "B/G", "R/G", "R/W", "G/W", "G/U"];
const TWOBRID = ["2/W", "2/U", "2/B", "2/R", "2/G"];
const PHYREXIAN = ["W/P", "U/P", "B/P", "R/P", "G/P", "C/P"];
const COLOURLESS_HYBRID = ["C/W", "C/U", "C/B", "C/R", "C/G"];
const SPECIAL = ["T", "Q", "S", "E"];

const meta = {
  title: "Game/ManaSymbol",
  component: ManaSymbol,
  parameters: { automtg: { mount: "bare" } },
} satisfies Meta<typeof ManaSymbol>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Green: Story = { args: { code: "G" } };
export const Generic: Story = { args: { code: "4" } };
export const Tap: Story = { args: { code: "T" } };

/** A code the engine cannot emit today, drawn as text rather than a gap. */
export const Fallback: Story = { args: { code: "ZZ", fallback: "?" } };

function Row({ label, codes }: { label: string; codes: string[] }) {
  return (
    <div style={{ marginBottom: "0.9rem" }}>
      <div style={{ color: "#9aa", fontSize: 12, marginBottom: 4, letterSpacing: ".08em" }}>
        {label.toUpperCase()}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {codes.map((code) => (
          <ManaSymbol key={code} code={code} />
        ))}
      </div>
    </div>
  );
}

export const AllSymbols: Story = {
  args: { code: "G" },
  render: () => (
    <div>
      <Row label="Generic" codes={GENERIC} />
      <Row label="Colours" codes={COLOURS} />
      <Row label="Hybrid" codes={HYBRID} />
      <Row label="Twobrid" codes={TWOBRID} />
      <Row label="Phyrexian" codes={PHYREXIAN} />
      <Row label="Colourless hybrid" codes={COLOURLESS_HYBRID} />
      <Row label="Special" codes={SPECIAL} />
    </div>
  ),

  /*
   * Every symbol must be a real image that actually decoded.
   *
   * `naturalWidth === 0` is the tell: the element exists, it is laid out, and
   * nothing arrived. That is precisely the failure mode a missing `staticDirs`
   * entry produces, and the reason it would otherwise go unnoticed.
   */
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTitle("{G}");

    // Every code must have produced an <img>, not the text fallback. A code
    // spelled the file's way (`W-U` rather than `{W/U}`) fails exactly here.
    const images = () => [...canvasElement.querySelectorAll<HTMLImageElement>("img.pip")];
    expect(images().length).toBe(
      GENERIC.length +
        COLOURS.length +
        HYBRID.length +
        TWOBRID.length +
        PHYREXIAN.length +
        COLOURLESS_HYBRID.length +
        SPECIAL.length,
    );

    // And every one must have decoded. `naturalWidth === 0` is the tell for a
    // file that is not on disk: the element exists and is laid out, so nothing
    // else in the suite would notice. Waited for, because 54 requests do not
    // finish within the tick that rendered them.
    await waitFor(
      () => {
        const broken = images()
          .filter((img) => !img.complete || img.naturalWidth === 0)
          .map((img) => img.getAttribute("src"));
        expect(broken, "these symbol files did not load").toEqual([]);
      },
      { timeout: 5000 },
    );
  },
};
