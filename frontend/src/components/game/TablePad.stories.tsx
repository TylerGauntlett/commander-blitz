/**
 * The whole board on a controller: every advertised button bound, the regions,
 * the card hold, the jump to the decision, the dial and the settings menu.
 *
 * Split out of `Table.stories.tsx`. Every story here is tagged `handheld`.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";
import type { PadButton } from "../../input/buttons";
import { getCursor, moveCursor, setCursor } from "../../input/cursor";
import { groupOf, groupRoot, landableStopsIn, setGroup } from "../../input/groups";
import { boundButtons, startPad } from "../../input/pad";
import { activeRoot } from "../../input/stops";
import { NAVIGATION_HINTS } from "../../logic/verbs";
import { board } from "../../testing/board";
import * as scenarios from "../../testing/scenarios";
import { Table } from "./Table";

const meta = {
  title: "Game/Table Pad",
  component: Table,
  parameters: { automtg: { mount: "screen" } },
} satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * EVERY BUTTON THE HINT BAR ADVERTISES ACTUALLY DOES SOMETHING.
 *
 * The bar has advertised `L1 Zone` and `L2 Menu` since it was written, and
 * `verbsFor` returns `Y Read` on every card stop -- and for several rounds
 * **nothing in the app listened for any of the three**. An advertised button
 * that does nothing is worse than an unadvertised one: it teaches the player
 * that the bar is not to be trusted.
 *
 * Nothing in the suite could see it, either, because the bar renders spans and
 * a span cannot fail to work. So this mounts the real board and compares what
 * the bar can SAY against what `pad.ts` has a listener for.
 */
export const EveryAdvertisedButtonIsBound: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");

    const bound = new Set(boundButtons());

    // The navigation half, which the bar draws unconditionally.
    for (const hint of NAVIGATION_HINTS) {
      if (hint.btn === "dpad") continue; // four bindings, and `useCursorNav` owns them.
      expect(bound.has(hint.btn as PadButton), `${hint.btn} is advertised`).toBe(true);
    }

    /*
     * ...and the verbs, which change with the stop.
     *
     * `A` and the four directions are deliberately not here: `useCursorNav`
     * binds those, and it is mounted by `Screen` rather than by the board, so a
     * story that renders `Table` alone would be asserting the absence of a
     * component it never mounted. `e2e/pad.spec.ts` owns them -- "the d-pad
     * walks the ring and A presses what it is on" -- against the real app.
     *
     * What is left is exactly the set this board is responsible for, which is
     * also the set that was advertised and unbound.
     */
    for (const btn of ["b", "x", "y", "r1"] as PadButton[]) {
      expect(bound.has(btn), `${btn} is a verb the bar can print`).toBe(true);
    }
  },
};

/**
 * Stepping between the board's regions, and the trap that follows.
 *
 * Directional navigation crosses a 96px seat strip, three lanes, a fanned hand
 * and a 243px rail one card at a time. `docs/handheld-playtest.md` Loop 1
 * records walking the board as "a bad way to ask can you reach everything":
 * reachable and reachable-in-under-a-second are different properties, and only
 * the second is playable.
 *
 * `[` and `]` are what `input/buttons.ts` maps to `L1` and `R1` on a keyboard,
 * which is the only route a test has into the pad -- neither Playwright nor
 * Vitest can synthesise a real Gamepad.
 *
 * `startPad()` because the key latch lives in `input/pad.ts` and `useCursorNav`
 * is what starts it in the app -- and that is mounted by `Screen`, not by the
 * board. A story that rendered `Table` alone would be asserting the absence of
 * a component it never mounted.
 */
export const HandheldRegionStepping: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const region = () => document.documentElement.getAttribute("data-group");

    /*
     * It is already in the hand, and that is the OTHER half of this feature.
     *
     * `earlyBoard` is your main phase with something castable, and
     * `groupForDecision` says a main phase is spent deciding what to play -- so
     * the ring has been put where the decision is before a button was touched.
     */
    await waitFor(() => expect(region()).toBe("hand"));
    const first = region();

    await userEvent.keyboard("]");
    await waitFor(() => expect(region()).not.toBe(first));

    // ...and back again, which is what makes it a step rather than a cycle you
    // have to go the long way round.
    //
    // `[[` and not `[`: a bare bracket opens a key descriptor in `userEvent`'s
    // grammar, so the literal has to be doubled.
    await userEvent.keyboard("[[");
    await waitFor(() => expect(region()).toBe(first));

    /*
     * The ring is inside the region it names.
     *
     * This is the trap, and it is the reason a region is a container rather
     * than a stop-id prefix: `card:<oid>` is a hand card AND a board card AND a
     * stack item, so only the DOM can say which one the ring is on.
     */
    const cursor = document.querySelector("[data-cursor]");
    expect(cursor, "the ring landed somewhere").not.toBeNull();
    expect(groupOf(cursor as Element)).toBe(first);
  },
};

/**
 * `Y` reads the card the ring is on, full screen.
 *
 * The rail's reader carries name, cost, type, P/T and rules at 16px, which is
 * what a player needs most of the time and is why it is worth 236px of the
 * rail. This is the deeper read -- a card with six lines of rules, or one whose
 * art is how you will recognise it next turn.
 *
 * `i` is `Y` on a keyboard (`input/buttons.ts`).
 */
export const HandheldCardHold: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    // Onto a card, wherever the decision rule left the ring.
    await waitFor(() => {
      expect(document.querySelector("[data-cursor]")).not.toBeNull();
    });

    await userEvent.keyboard("i");
    const hold = await canvas.findByTestId("card-hold");

    // The same `variant="big"` the desktop rail draws. The roadmap's rule for
    // this round is that the card sizes are fine as they are; what changes is
    // which one is used where.
    expect(hold.querySelector(".card--big")).not.toBeNull();
    // It traps the ring, so it cannot wander the board underneath a full-screen
    // overlay while the player cannot see where it has gone.
    expect(hold.hasAttribute("data-modal-root")).toBe(true);

    // `B` puts it down.
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="card-hold"]')).toBeNull();
    });
  },
};

/**
 * Holding `L2` jumps straight to a region instead of cycling to it.
 *
 * `L1`/`R1` step, which is right at two or three regions and wearing at five --
 * getting from the hand to the board is three presses and a guess about which
 * direction is shorter.
 *
 * ON THE TRIGGER AND NOT ON A SHOULDER, and that is not a preference. `pad.ts`
 * reports PRESSES and has no release event for a shoulder, so a hold there is a
 * timer with nothing to cancel it: a tap would open the dial 260ms later,
 * having already stepped. A trigger is analog and `onFrame` reports its
 * position every frame, which is the same channel the `R2` opponent reader is
 * held on. `z` is `L2` on a keyboard (`input/buttons.ts`).
 */
/**
 * `L2` TAPPED SENDS THE RING TO THE THING THAT ENDS THE DECISION.
 *
 * The commit slab -- Attack, Block, Done, Pass -- lives in the right rail, and
 * on a 1280x800 panel the ring is almost never near it: you are in your hand,
 * or out on an opponent's board choosing what to swing at, and the rail is the
 * far corner. Walking there is a dozen presses across a seat strip, three lanes
 * and a fanned hand; `R1` is two steps if you happen to know the region order.
 * Neither is a thing to ask for once a phase, thirteen phases a turn.
 *
 * The button was already advertised. It said `Jump`, and it jumped to the tool
 * strip -- which `Menu` also did, so the one shoulder the bar promises was
 * spent on the second way to reach the settings menu.
 *
 * A TAP, not a hold: holding `L2` still opens the region dial, and the two do
 * not collide because a tap crosses and releases the analog threshold inside a
 * frame or two. `HandheldRegionDial` above is the other half of the same
 * button.
 */
/**
 * THE COMMAND ZONE IS SOMEWHERE THE RING CAN GO.
 *
 * It was not, and it was the only control on the board that was not. The board
 * declares its stops explicitly -- `stopsIn` takes a surface at its word and
 * gives it no native-focusable fallback -- and the commander plinth is a
 * `<button>` carrying no `data-stop`, so the ring could not reach it by any
 * route. A controller could not cast its own commander at all, and the plinth's
 * documented promise that "the full card is one hover away in the preview rail"
 * held for a mouse and for nothing else: `hoverFor` drives `hoveredOid` from
 * the cursor, and the cursor could not get here.
 *
 * The plinth carries `card:<oid>` while the commander is in the command zone,
 * which is the same id the board would use for it and the reason everything
 * else follows for nothing: `A` casts, `Y` reads, and the rail fills.
 */
export const HandheldTheCommanderIsReachable: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const plinth = canvasElement.querySelector<HTMLElement>('[data-testid^="commander-"]');
    expect(plinth, "the scenario needs a commander in the command zone").not.toBeNull();
    const stop = plinth?.dataset.stop;
    expect(stop, "the plinth has to declare a stop or the ring cannot see it").toBeTruthy();

    /*
     * It is a LANDABLE stop of the region it sits in, which is the property
     * that was false. `groupsPresent` and `enterGroup` both walk this list, so
     * a plinth missing from it is a plinth `R1` steps past and no direction can
     * reach -- and `landableStopsIn` filters by visibility, so this also says
     * the ring would not be sent somewhere clipped away.
     *
     * Asked of the region rather than by pressing `R1` five times: which
     * region a given press lands in depends on what else is on the board, and
     * `HandheldRegionStepping` already owns the question of whether stepping
     * works at all. This one is about whether there is anything here to step to.
     */
    const orb = groupRoot("orb");
    expect(orb, "the viewer's side panel is where the plinth lives").not.toBeNull();
    const landable = landableStopsIn(orb as HTMLElement).map((el) => el.dataset.stop);
    expect(landable, `the orb region holds ${landable.join(", ")}`).toContain(stop);

    // ...and the ring can be put there, which the modal and region traps both
    // have to allow before the cursor will take it.
    setGroup("orb");
    expect(setCursor(stop as string), "the trap refused the plinth").toBe(true);
    expect(getCursor()).toBe(stop);

    // ...and the rail read it, which is the whole point of being able to.
    await waitFor(() => {
      const rail = canvasElement.querySelector('[data-testid="card-preview"]');
      expect(rail?.textContent).toContain("Aesi");
    });
  },
};

/** The element the ring is on, which is `[data-cursor]` and nothing else. */
function ringed(root: HTMLElement): HTMLElement {
  const el = root.querySelector<HTMLElement>("[data-cursor]");
  if (!el) throw new Error("the ring is not on anything");
  return el;
}

export const HandheldJumpToTheDecision: Story = {
  args: board(scenarios.combatDeclareAttackers()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const dock = canvasElement.querySelector(".commit-dock");
    expect(dock, "the scenario has to have a slab for this to be about").not.toBeNull();

    /*
     * Standing somewhere else first, which is the case this exists for -- and
     * PLACED rather than stepped to with `R1`. Which region a press lands in
     * depends on what else is on the board, and a step that has not finished
     * when the jump goes out is a race rather than a test.
     * `HandheldRegionStepping` owns whether stepping works.
     */
    const hand = groupRoot("hand");
    const away = hand ? landableStopsIn(hand)[0]?.dataset.stop : undefined;
    expect(away, "the scenario needs a hand to start away from").toBeTruthy();
    setGroup("hand");
    expect(setCursor(away as string)).toBe(true);
    expect(groupOf(ringed(canvasElement))).not.toBe("acts");

    // `z` is `L2`; native events for the reason `HandheldRegionDial` explains.
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "z", bubbles: true }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "z", bubbles: true }));

    await waitFor(() => {
      const on = ringed(canvasElement);
      expect(dock?.contains(on), `ring landed on ${on?.getAttribute("data-testid")}`).toBe(
        true,
      );
    });
    // ...and the region trap came with it, or the next direction press would
    // walk straight back out of the rail.
    expect(groupOf(ringed(canvasElement))).toBe("acts");
  },
};

export const HandheldRegionDial: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    /*
     * Native events rather than `userEvent`, and it is worth saying why.
     *
     * `pad.ts` listens on `window`, and `userEvent`'s press-and-hold grammar
     * (`{z>}` / `{/z}`) keeps its held-key state per SESSION -- two separate
     * `userEvent.keyboard()` calls are two sessions, so the release refers to a
     * key the second one never pressed and no `keyup` is dispatched at all. The
     * hold then never ends and the story fails on a detail of the test library
     * rather than on the app.
     */
    const key = (type: "keydown" | "keyup") =>
      window.dispatchEvent(new KeyboardEvent(type, { key: "z", bubbles: true }));

    key("keydown");
    const dial = await canvas.findByTestId("group-dial");

    /*
     * `.wheelwrap` is the contract, not decoration. `input/stops.ts`'s trap has
     * preferred that class over every other candidate since it was written and
     * nothing in the repo has ever rendered one -- it was the prototype's name
     * for exactly this control, carried into the trap and then not built. So
     * the ring is inside the dial the moment it opens, with no change to the
     * trap at all.
     */
    expect(dial.classList.contains("wheelwrap")).toBe(true);
    expect(activeRoot()).toBe(dial);

    // A spoke per region that is actually there, and none of them is an action.
    expect(dial.querySelectorAll(".wheel__spoke").length).toBeGreaterThan(1);
    expect(dial.querySelector("[data-action-id]")).toBeNull();

    // Letting go puts it away -- which is the whole argument for a hold over a
    // toggle: you cannot forget to release.
    key("keyup");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="group-dial"]')).toBeNull();
    });
  },
};

/**
 * The settings menu is a modal to the ring, and `B` is its way out.
 *
 * TECH_DEBT FB-12. On a handheld the tool strip is portaled into the foot,
 * which belongs to none of the regions, and the open menu used to be no modal
 * either -- so every direction pressed inside it was free to leave across the
 * board, `B` went down the unwind ladder and cancelled something else, and the
 * control-scheme picker (the setting that exists to rescue a controller) had
 * no stops at all.
 *
 * Directions through `moveCursor` rather than the arrow keys, for the reason
 * the stories above give: `useCursorNav` binds those and is mounted by
 * `Screen`. `B` IS the board's, and is pressed for real.
 */
export const HandheldSettingsMenu: Story = {
  args: board(scenarios.earlyBoard()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    setGroup(null);
    expect(setCursor("tool:settings"), "the gear is reachable").toBe(true);
    await userEvent.click(canvas.getByTestId("settings"));
    const menu = await canvas.findByTestId("settings-menu");
    expect(menu.hasAttribute("data-modal-root")).toBe(true);

    // Opening it put the ring on its first item.
    await waitFor(() => expect(getCursor()).toBe("tool:mute"));

    // Every direction stays inside, however many times it is pressed, and the
    // walk passes through the scheme picker on the way.
    const visited = new Set<string>();
    for (const dir of [
      "down",
      "down",
      "down",
      "down",
      "right",
      "up",
      "up",
      "up",
      "up",
    ] as const) {
      moveCursor(dir);
      const at = getCursor();
      expect(at, "the ring went out").not.toBeNull();
      expect(
        menu.querySelector(`[data-stop="${at}"]`),
        `${at} is outside the open menu`,
      ).not.toBeNull();
      visited.add(at as string);
    }
    expect(
      [...visited].some((id) => id.startsWith("tool:scheme-")),
      [...visited].join(" > "),
    ).toBe(true);

    // `B` (Escape on a keyboard) closes it, and the ring is back on the gear.
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="settings-menu"]')).toBeNull();
    });
    await waitFor(() => expect(getCursor()).toBe("tool:settings"));
  },
};

/**
 * `A` ON A PERMANENT WITH TWO ABILITIES ASKS WHICH.
 *
 * The press used to select the card and leave the answer to the panel, where
 * on this layout both rows read "Mind Stone: {T}…" and one of them sacrifices
 * it. `AbilityMenu` is a modal like every other decision: the ring lands on
 * its first item, every direction stays inside, `B` puts it away and the ring
 * comes back to the card the question was about.
 */
export const HandheldAbilityMenu: Story = {
  args: board(scenarios.twoAbilityPermanent()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    setGroup(null);
    expect(setCursor("card:401"), "the artifact is reachable").toBe(true);
    // `A` is a click on the ring's element (`useCursorNav`).
    await userEvent.click(canvas.getByTestId("card-401"));
    const menu = await canvas.findByTestId("ability-menu");
    expect(menu.hasAttribute("data-modal-root")).toBe(true);
    await waitFor(() => expect(getCursor()).toBe("menu:ability:0"));

    moveCursor("down");
    expect(getCursor()).toBe("menu:ability:1");
    moveCursor("down");
    expect(getCursor(), "the ring stays inside the menu").toBe("menu:ability:1");
    moveCursor("up");
    expect(getCursor()).toBe("menu:ability:0");

    // The reader stays on the card, so `Y` can read it over the menu.
    expect(menu.querySelector("[data-cursor]")?.getAttribute("data-preview-oid")).toBe("401");

    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(canvasElement.querySelector('[data-testid="ability-menu"]')).toBeNull();
    });
    await waitFor(() => expect(getCursor()).toBe("card:401"));
  },
};

/**
 * A HELD DOWN-PRESS WALKS EVERY TARGET CHIP, IN ORDER.
 *
 * On a desktop the chips wrap as pills sized to their names, and from a pill on
 * a wrapped line "down" preferred the next full-width row over the pill
 * diagonally below it (`nav.ts:pickStop`'s row rule), so the ring skipped
 * targets or zigzagged between columns. On a handheld they are one per line.
 */
export const HandheldTargetChipsWalk: Story = {
  args: board(scenarios.targetVariants()),
  globals: { handheld: "on", input: "pad" },
  tags: ["handheld"],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("table");
    startPad();

    const chips = [...canvasElement.querySelectorAll<HTMLElement>(".act__aims .aim")];
    expect(chips).toHaveLength(3);
    // One per line: each chip starts where the one above it ends.
    for (let i = 1; i < chips.length; i += 1) {
      const above = chips[i - 1].getBoundingClientRect();
      const here = chips[i].getBoundingClientRect();
      expect(here.top, `chip ${i} is on its own line`).toBeGreaterThanOrEqual(above.bottom - 1);
      expect(Math.abs(here.left - above.left), `chip ${i} is in the same column`).toBeLessThan(
        2,
      );
    }

    setGroup(null);
    expect(setCursor("act:a-charm-991")).toBe(true);
    moveCursor("down");
    expect(getCursor()).toBe("act:a-charm-992");
    moveCursor("down");
    expect(getCursor()).toBe("act:a-charm-993");
    moveCursor("up");
    moveCursor("up");
    expect(getCursor()).toBe("act:a-charm-991");
  },
};
