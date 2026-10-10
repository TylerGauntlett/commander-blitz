/**
 * Importing a deck from Moxfield.
 *
 * Almost all of this component is error states and an honesty report, because
 * the interesting thing about an import is what the engine *could not* do with
 * it: a deck can look like 37 lands and behave like 34.
 *
 * It calls `api` directly rather than through a hook, so these stories stub
 * `fetch` per story instead of seeding a query cache.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import type { DeckImportResponse } from "../../api/types";
import { deckSummary } from "../../testing/fixtures";
import { DeckImport } from "./DeckImport";

const MOXFIELD = "https://moxfield.com/decks/abc123";

function importResult(overrides: Partial<DeckImportResponse> = {}): DeckImportResponse {
  return {
    deck: deckSummary({ id: "mine", name: "Zada Storm", source: "moxfield", tags: [] }),
    source: "moxfield",
    source_id: "abc123",
    total: 100,
    playable: 100,
    simplified: 0,
    lands: 37,
    lands_producing_mana: 37,
    lands_inert: 0,
    cards: [],
    problems: [],
    ...overrides,
  };
}

/** Answer the import endpoint with `body`, or fail with `status`. */
function stubFetch(body: unknown, status = 200) {
  return async () => {
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      })) as typeof fetch;
    return () => {
      globalThis.fetch = original;
    };
  };
}

const meta = {
  title: "Menu/DeckImport",
  component: DeckImport,
  args: { onImported: fn() },
  parameters: { commanderblitz: { mount: "bare" } },
} satisfies Meta<typeof DeckImport>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Panel: Story = {};

/** The catalogue's footer strip, which is the same thing in one line. */
/** The catalogue's footer strip: `flex: 1; min-width: 300px` needs that row. */
export const Row: Story = {
  args: { variant: "row" },
  parameters: { commanderblitz: { mount: "catalogFoot" } },
};

/**
 * The desktop with no connection: Moxfield is the one thing the game cannot
 * reach from a server on the device, so the strip is disabled and says so.
 */
export const Offline: Story = {
  args: { variant: "row", enabled: false },
  parameters: { commanderblitz: { mount: "catalogFoot" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect(await canvas.findByRole("textbox")).toBeDisabled();
    expect(await canvas.findByTestId("import-go")).toBeDisabled();
    await canvas.findByTestId("import-offline");
  },
};

/**
 * A URL that is not a Moxfield deck.
 *
 * Rejected before any request goes out, so this story needs no stub at all.
 */
export const BadUrl: Story = {
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const field = await canvas.findByRole("textbox");
    await userEvent.type(field, "https://example.com/not-a-deck");
    await userEvent.click(await canvas.findByText(/Import/i));
    expect(args.onImported).not.toHaveBeenCalled();
    expect(canvasElement.textContent).toMatch(/moxfield/i);
  },
};

/** Everything came through intact. */
export const Success: Story = {
  beforeEach: stubFetch(importResult()),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByRole("textbox"), MOXFIELD);
    await userEvent.click(await canvas.findByText(/Import/i));
    await canvas.findByText(/Zada Storm/);
    expect(args.onImported).toHaveBeenCalled();
  },
};

/**
 * Imported, but twelve cards came through with their rules text inert.
 *
 * The whole point of the report: the deck is playable and the client says
 * exactly how much of it the engine actually represents.
 */
export const PartialWithSimplifiedCards: Story = {
  beforeEach: stubFetch(
    importResult({
      playable: 88,
      simplified: 12,
      lands: 37,
      lands_producing_mana: 34,
      lands_inert: 3,
      problems: ["Rhystic Study: replaced with a simplified equivalent."],
    }),
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByRole("textbox"), MOXFIELD);
    await userEvent.click(await canvas.findByText(/Import/i));
    await canvas.findByText(/Zada Storm/);
    // A deck that looks like 37 lands and behaves like 34 has to say so.
    expect(canvasElement.textContent).toContain("12");
  },
};

/** The server refused it. */
export const ServerError: Story = {
  beforeEach: stubFetch({ detail: "That deck is private.", code: "deck_private" }, 400),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByRole("textbox"), MOXFIELD);
    await userEvent.click(await canvas.findByText(/Import/i));
    await canvas.findByText(/private/i);
    expect(args.onImported).not.toHaveBeenCalled();
  },
};
