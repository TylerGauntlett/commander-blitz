/**
 * The opening hand, in a real browser.
 *
 * Everything worth asserting about this screen is a box. The whole design is a
 * claim about geometry -- seven cards at the width their own rules text needs,
 * an arch that does not move when the selection does, and both of the handheld
 * floors met by being authored at them rather than repaired afterwards -- and
 * jsdom can see none of it. `tests/openingHand.test.ts` owns the arithmetic;
 * this owns what the arithmetic turns into.
 *
 * The handheld stories are also the only thing in CI that grades the floors:
 * `scripts/verify.py:290-302` runs `test:stories:handheld` and does not run
 * Playwright, so `e2e/handheldAssert.ts` has never actually stopped anything
 * landing.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";
import { noteInput, resetInputMode } from "../../input/inputMode";
import { MULL_TUNE } from "../../logic/openingHand";
import {
  expectHandheldFloors,
  expectNothingOverflows,
  expectUniqueActionIds,
  settled,
} from "../../testing/asserts";
import * as scenarios from "../../testing/scenarios";
import { OpeningHand } from "./OpeningHand";

const meta = {
  title: "Game/OpeningHand",
  component: OpeningHand,
  parameters: { automtg: { mount: "tableOverlay" } },
  args: { onAct: fn(), disabled: false },
} satisfies Meta<typeof OpeningHand>;

export default meta;
type Story = StoryObj<typeof meta>;

const keep = () => scenarios.mulligan();
const bottom = (taken = 1, selected: number[] = []) =>
  scenarios.mulliganBottom(taken, selected);

/** The first question, at whatever size the canvas happens to be. */
export const Keep: Story = {
  args: { state: keep().state, actions: keep().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    expect(stage.dataset.phase).toBe("keep");

    /* Every card in the hand is drawn, and each is a stop the ring can reach.
       The dialog this replaces drew none of them. */
    const cards = canvasElement.querySelectorAll("[data-card-oid]");
    expect(cards.length).toBe(7);

    // Two answers, one of each, and no third copy anywhere.
    expectUniqueActionIds(canvasElement);
    await userEvent.click(await canvas.findByText("Keep"));
    expect(args.onAct).toHaveBeenCalledWith("a0-keep");
  },
};

/**
 * THE ARCH DOES NOT MOVE WHEN THE SELECTION DOES.
 *
 * The mockup's second pass grew the selected card and closed the others up
 * around it, which meant re-centring the row on every press -- so the one thing
 * holding still was the card you were trying to read. A still cannot show that;
 * two stills compared can.
 */
export const ReadingMovesNothing: Story = {
  args: { state: keep().state, actions: keep().actions },
  parameters: { automtg: { mount: "tableOverlay", motion: "real" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    await settled(stage);

    /*
     * THE ROTATION, NOT THE WHOLE TRANSFORM.
     *
     * The slot carries its own lift as well as its place in the arch -- one
     * inline `translateY(...) rotate(...)`, because the ring is drawn around the
     * stop and a card that rose out of its own button left the ring behind it.
     * The `translateY` term IS a function of the selection and always was; it
     * simply used to live in a custom property this story never read. So the
     * pose is compared without it, and the lift is asserted separately below.
     */
    const arch = (el: HTMLElement) => ({
      left: el.style.left,
      top: el.style.top,
      rotate: /rotate\([^)]*\)/.exec(el.style.transform)?.[0] ?? "",
      // `offsetWidth`, because these are rotated -- see `HandheldKeep`.
      width: el.offsetWidth,
    });
    const liftOf = (el: HTMLElement) =>
      Number.parseFloat(/translateY\(([-\d.]+)px\)/.exec(el.style.transform)?.[1] ?? "0");

    const slots = [...canvasElement.querySelectorAll<HTMLElement>("[data-card-oid]")];
    const before = slots.map(arch);

    // Walk the whole row, both ways.
    for (const el of slots) await userEvent.hover(el);
    for (const el of [...slots].reverse()) await userEvent.hover(el);
    await settled(stage);

    expect(slots.map(arch)).toEqual(before);

    /* And the one thing that DID move is the card being read: exactly one slot
       is off its resting line, it is the one the pointer left on, and it is up
       rather than down. */
    const lifted = slots.filter((el) => liftOf(el) !== 0);
    expect(lifted.length).toBe(1);
    expect(lifted[0]).toBe(slots[0]);
    expect(liftOf(lifted[0])).toBeLessThan(0);
  },
};

/**
 * Only the card you are on prints its rules.
 *
 * Seven open rules boxes at this pitch is six columns of type sliced down the
 * middle by the card in front. The box closes on the others and the card's own
 * illustration takes the space back, so the card does not change size -- which
 * is what the story above is really protecting.
 */
export const OneRulesBoxAtATime: Story = {
  args: { state: keep().state, actions: keep().actions },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("opening-hand");

    /*
     * DISPLAYED, not present. The box is closed with `display: none`, so it is
     * still in the DOM on all six of the others -- and a `querySelector` that
     * only asks whether the node exists reports every card with rules text as
     * open. Three of these seven are basic lands, which `CardFace` gives no
     * rules box at all, so the wrong version of this check came back with the
     * plausible-looking answer 3.
     */
    const shown = () =>
      [...canvasElement.querySelectorAll<HTMLElement>(".mull__slot")].filter((slot) => {
        const rules = slot.querySelector<HTMLElement>(".face__rules");
        return rules !== null && getComputedStyle(rules).display !== "none";
      });

    // The middle card opens on mount, and it is the only one.
    const first = shown();
    expect(first.length).toBe(1);
    expect(first[0].dataset.on).toBe("true");

    /* Counterspell, at the far end, which has real rules text. */
    const slots = [...canvasElement.querySelectorAll<HTMLElement>(".mull__slot")];
    await userEvent.hover(slots[6]);
    const moved = shown();
    expect(moved.length).toBe(1);
    expect(moved[0]).toBe(slots[6]);

    /*
     * TWO CARDS IN THIS HAND HAVE NO BOX TO OPEN, and neither is this screen
     * hiding one. A basic land gets no rules box from `CardFace` at all
     * (`isPlainLand`), and Serra Angel's whole text is keywords, which
     * `variant="detail"` renders as neither a rules line nor the chip row a
     * board card would get. Both are the card component's calls and predate
     * this surface; pinning them here is what stops somebody "fixing" the
     * selection logic for a symptom that is not its.
     */
    await userEvent.hover(slots[0]);
    expect(shown().length).toBe(0);
    await userEvent.hover(slots[4]);
    expect(shown().length).toBe(0);
  },
};

/**
 * THE RING IS DRAWN AROUND THE STOP, SO THE STOP IS WHAT HAS TO RISE.
 *
 * Both halves of the ring measure the element carrying `data-stop`: the outline
 * in `handheld.css` is on `[data-cursor]` itself, and `#ring` is positioned from
 * `ringTargetFor`, which takes that element's box. The lift used to be on a span
 * inside the button, so an arrow key drew a gold rectangle 20px below the card
 * it was supposed to be around -- around the hole the card had just left.
 *
 * `.mull__slot::after` is what makes moving the button safe for a pointer; this
 * is what makes it necessary.
 */
export const TheRingRisesWithTheCard: Story = {
  args: { state: keep().state, actions: keep().actions },
  parameters: { automtg: { mount: "tableOverlay", motion: "real" } },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    await settled(stage);

    /* The far end of the row, which is also the most tilted -- so this is not
       quietly asserting about the one upright card in the middle. */
    const slots = [...canvasElement.querySelectorAll<HTMLElement>(".mull__slot")];
    const slot = slots[6];
    const rest = slot.getBoundingClientRect().top;

    await userEvent.hover(slot);
    await settled(slot);
    const raised = slot.getBoundingClientRect().top;
    expect(slot.dataset.on).toBe("true");
    expect(rest - raised, "the stop itself should rise with the card").toBeGreaterThan(4);

    /* And the two agree, which is the whole bug in one line: the box the ring is
       drawn around is the box the card is in. */
    const card = slot.querySelector<HTMLElement>(".card");
    expect(card).not.toBeNull();
    const drift = Math.abs((card?.getBoundingClientRect().top ?? 0) - raised);
    expect(drift, "the ring's box and the card's box are the same box").toBeLessThan(2);
  },
};

/** The second question, in the same room, with one card marked. */
export const Bottom: Story = {
  args: { state: bottom().state, actions: bottom().actions },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    expect(stage.dataset.phase).toBe("bottom");
    expect((await canvas.findByTestId("opening-hand-ask")).textContent).toContain(
      "1 more card",
    );

    /* The cards ARE the answers here, so each carries an id and there is no
       Keep button to duplicate. */
    expectUniqueActionIds(canvasElement);
    const slots = canvasElement.querySelectorAll<HTMLElement>(".mull__slot");
    await userEvent.click(slots[3]);
    expect(args.onAct).toHaveBeenCalledWith("a3-bottom");
  },
};

/** Two taken, two to bottom, and one of them already chosen. */
export const BottomPartlyChosen: Story = {
  args: { state: bottom(2, [5]).state, actions: bottom(2, [5]).actions },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("opening-hand");
    expect((await canvas.findByTestId("opening-hand-ask")).textContent).toContain(
      "1 more card",
    );
    const marked = canvasElement.querySelectorAll("[data-marked]");
    expect(marked.length).toBe(1);
  },
};

/* ==========================================================================
   The Deck
   ==========================================================================
   `tags: ["handheld"]` puts these in the `storybook-handheld` vitest project,
   which runs at a real 1280x800 -- the size every number in `MULL_TUNE` was
   measured at, and the only place in CI the floors are graded.
   ========================================================================== */

/** The composition of record: 1280x800, where `--mu` is exactly 1. */
export const HandheldKeep: Story = {
  args: { state: keep().state, actions: keep().actions },
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "tableOverlay", motion: "real", zoomLock: false } },
  beforeEach: () => {
    noteInput("pad");
    return resetInputMode;
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    await settled(stage);

    /*
     * THE MOCKUP'S PROPORTIONS, AT WHATEVER SCALE THE CANVAS GIVES.
     *
     * Not `--mu === 1`, and the reason is a property of the harness rather than
     * of the screen: the tester canvas is really about 1200px wide whatever
     * `vite.config.ts` declares for the project, which `.storybook/preview.tsx`
     * records at length as the reason the Layout toolbar has to be
     * authoritative. So `--mu` lands near 0.94 here and would land at exactly 1
     * on a real Deck.
     *
     * What the story can still hold is that the composition is the mockup's
     * SHAPE at whatever that scale is -- a 296-wide card at a 144 pitch, both
     * multiplied by the same number. The absolute pixels at `--mu` 1 are
     * `tests/openingHand.test.ts`'s to assert, and the browser MCP pass in the
     * plan is what checks them against the real thing.
     */
    const mu = Number(stage.dataset.mu);
    expect(mu).toBeGreaterThan(0.72);
    const slots = [...canvasElement.querySelectorAll<HTMLElement>(".mull__slot")];
    /*
     * `offsetWidth`, NOT `getBoundingClientRect().width`.
     *
     * These slots are rotated, and a rect is the AXIS-ALIGNED box of a rotated
     * element -- so the end card measured 295px against an expected 278 and
     * looked like a scale bug. `mockups/mulligan/measure.mjs` carries the same
     * note for the same reason: its first table reported every fanned direction
     * 15-28% too wide and only the one that does not rotate was right.
     */
    expect(slots[0].offsetWidth).toBeCloseTo(MULL_TUNE.CARD_W * mu, 0);
    expect(slots[1].offsetLeft - slots[0].offsetLeft).toBeCloseTo(MULL_TUNE.PITCH * mu, 0);

    // And nothing runs off the panel, at either end.
    expectNothingOverflows(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};

/** The second question at the same size, where the marks and the tag appear. */
export const HandheldBottom: Story = {
  args: { state: bottom(2).state, actions: bottom(2).actions },
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  parameters: { automtg: { mount: "tableOverlay", motion: "real", zoomLock: false } },
  beforeEach: () => {
    noteInput("pad");
    return resetInputMode;
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const stage = await canvas.findByTestId("opening-hand");
    await settled(stage);
    expectNothingOverflows(canvasElement);
    expectHandheldFloors(canvasElement);
  },
};
