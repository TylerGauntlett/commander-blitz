/**
 * An opponent's seat, in the mat it actually sits in.
 *
 * The states worth looking at are the ones where the seat has to say something
 * uncomfortable in 96px: a developed board with more creatures than it has
 * pips, a life total being eaten from both ends, and a seat with nothing at all
 * -- which is the one that decides whether the layout holds, because "nothing
 * in play" is the most useful thing the strip can say and the easiest to draw
 * as an empty box.
 *
 * `mount: "matSideCompact"` puts these in the app's own wrapper chain, so the
 * width comes from `.mat--compact` in the stylesheet rather than from anything
 * a story says. The seat states its own height (`--seat-h`); nothing here may.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, within } from "storybook/test";
import type { CardView, GameView, PlayerView } from "../../api/types";
import { musterOf } from "../../logic/threat";
import { card, gameView, player } from "../../testing/fixtures";
import { OpponentSeat } from "./OpponentSeat";

const creature = (overrides: Partial<CardView> = {}): CardView =>
  card({
    types: ["Creature"],
    type_line: "Creature — Vampire Soldier",
    zone: "battlefield",
    power: 2,
    toughness: 2,
    ...overrides,
  });

const land = (overrides: Partial<CardView> = {}): CardView =>
  card({
    name: "Forest",
    types: ["Land"],
    type_line: "Basic Land — Forest",
    zone: "battlefield",
    power: null,
    toughness: null,
    ...overrides,
  });

/**
 * The commander, which is the seat's ground and its window.
 *
 * Every story here gives its seat one. A seat whose commander is in a hidden
 * zone draws neither -- a real state, and `NoCommanderVisible` is where it is
 * looked at -- but it is not the state to review the component in, because the
 * art is what stops three opponents being three rectangles.
 */
function commander(name: string, pid: number): CardView {
  return card({
    name,
    card_id: name.toLowerCase().replace(/[^a-z]+/g, "_"),
    zone: "command",
    is_commander: true,
    types: ["Legendary", "Creature"],
    type_line: "Legendary Creature — Vampire Knight",
    owner: pid,
    controller: pid,
  });
}

/** A four-seat view with the opponent under test at pid 1. */
function view(battlefield: CardView[] = [], overrides: Partial<PlayerView> = {}): GameView {
  const players = [
    player({ pid: 0, name: "You" }),
    player({
      pid: 1,
      name: "Edgar Markov",
      command: [commander("Edgar Markov", 1)],
      ...overrides,
    }),
    player({ pid: 2, name: "Marco", command: [commander("Isperia", 2)] }),
    player({ pid: 3, name: "Duelist", command: [commander("Krenko", 3)] }),
  ];
  return gameView({
    players,
    battlefield: battlefield.map((c) => ({ ...c, controller: 1, owner: 1 })),
  });
}

function seat(state: GameView) {
  return {
    state,
    player: state.players[1],
    isActive: false,
    hasPriority: false,
    targetable: false,
    onSelect: fn(),
  };
}

const meta = {
  title: "Game/OpponentSeat",
  component: OpponentSeat,
  parameters: { automtg: { mount: "matSideCompact" } },
} satisfies Meta<typeof OpponentSeat>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A turn-eight board: lands down, creatures out, some of both tapped. */
export const Developed: Story = {
  args: seat(
    view(
      [
        ...Array.from({ length: 5 }, () => land()),
        ...Array.from({ length: 2 }, () => land({ tapped: true })),
        creature(),
        creature({ tapped: true }),
        creature({ keywords: ["flying"], power: 3, toughness: 3 }),
        card({ types: ["Artifact"], type_line: "Artifact", zone: "battlefield" }),
      ],
      { life: 25, commander_damage_taken: { "0": 5 } },
    ),
  ),
  play: async ({ args, canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");

    /*
     * The seat and the board it summarises, checked against each other.
     *
     * `mockups/seat/` names this the failure mode the whole family of
     * components has: a summary that cannot be checked against the thing it
     * summarises. Here it can, because both come off the same view.
     */
    const muster = musterOf(args.state, 1);
    expect(canvasElement.querySelector('[data-perm="land"] .perm__n')?.textContent).toBe(
      `${muster.landsUntapped}/${muster.lands}`,
    );
    expect(canvasElement.querySelector('[data-perm="creature"] .perm__n')?.textContent).toBe(
      `${muster.creaturesUntapped}/${muster.creatures}`,
    );
    expect(canvasElement.querySelectorAll(".tpip")).toHaveLength(muster.creatures);
  },
};

/**
 * The state the layout is actually decided by.
 *
 * A seat with nothing in play is the easiest thing to draw as an empty box, and
 * the row still has to say the four cells are at zero rather than absent --
 * dropping them would move the widths of the ones that remain every time
 * somebody's first land came down.
 */
export const Empty: Story = {
  args: seat(view([])),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    expect(canvasElement.querySelectorAll(".perm")).toHaveLength(4);
  },
};

/**
 * Eleven creatures against eight pips.
 *
 * The cap costs resolution and never information -- the exact number is on the
 * creature cell beside it -- and the ordering is what makes it safe: untapped
 * first and fliers first, so the facts a player acts on are the ones that
 * survive.
 */
export const MoreCreaturesThanPips: Story = {
  args: seat(
    view([
      ...Array.from({ length: 9 }, () => creature({ tapped: true })),
      creature(),
      creature({ keywords: ["flying"] }),
    ]),
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    expect(canvasElement.querySelectorAll(".tpip")).toHaveLength(8);
    expect(canvasElement.querySelector(".pips__more")?.textContent).toBe("+3");
  },
};

/**
 * Life from the left, commander damage as two arrows on the same track.
 *
 * Three clocks, and a Commander player watches all of them: their life, how
 * close your commander is to killing them (the arrow off the top edge), and
 * how close theirs is to killing you (the arrow off the bottom). The seat used
 * to draw the worst damage *this seat* had taken from anybody, which in a pod
 * is most often a number about two other players.
 */
export const UnderPressure: Story = {
  args: seat(
    view([creature()], {
      life: 12,
      commander_damage_taken: { "0": 16 },
    }),
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    const dealt = canvasElement.querySelector('[data-cmddmg="dealt"]') as HTMLElement;
    expect(dealt.dataset.amount).toBe("16");
    expect(dealt.className, "16 of 21 should be reading as a warning").toContain(
      "cmdarrow--warn",
    );
  },
};

/**
 * The race, which is the fact both arrows exist to carry.
 *
 * Nine dealt against fourteen taken: their commander is ahead of yours, and
 * the two arrows say so by where they sit rather than by a pair of numbers
 * somebody has to compare. Neither is at the warning line yet, so this is also
 * the state that shows the two directions apart by colour.
 */
export const CommanderRace: Story = {
  args: (() => {
    const state = view([creature()], { life: 26, commander_damage_taken: { "0": 9 } });
    state.players[0].commander_damage_taken = { "1": 14 };
    return seat(state);
  })(),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    expect(canvasElement.querySelectorAll(".cmdarrow")).toHaveLength(2);
  },
};

/** Their turn: the astral ring. */
export const Active: Story = {
  args: { ...seat(view([land(), creature()])), isActive: true },
};

/**
 * Their priority on somebody else's turn, which is a different fact.
 *
 * The shipped ribbon ran the two together into one highlighted name. This is
 * the case that proves they are separate, and it is the ordinary case in
 * Commander rather than an edge one.
 */
export const HasPriority: Story = {
  args: { ...seat(view([land(), creature()])), hasPriority: true },
};

/** You are aiming something at them. */
export const Targetable: Story = {
  args: { ...seat(view([land(), creature()])), targetable: true },
};

/** Their board is the one currently drawn in the viewer's lane area. */
export const Viewing: Story = {
  args: { ...seat(view([land(), creature()])), viewing: true },
};

/** Out of the game. Kept on screen: who is left is a fact you play around. */
export const Eliminated: Story = {
  args: seat(view([], { has_lost: true, loss_reason: "life", life: 0 })),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    expect((await canvas.findByTestId("life-1")).textContent).toBe("OUT");
  },
};

/**
 * A long name against a long commander, which is the row's real test.
 *
 * The player's name is the half that survives: it is what identifies the seat,
 * and the commander is on the window beside it in any case.
 */
export const NamesThatDoNotFit: Story = {
  args: seat(
    view([land()], {
      name: "Bartholomew Winterbottom III",
      command: [commander("Ghyrson Starn, Kelermorph", 1)],
    }),
  ),
};

/**
 * Their commander is nowhere visible -- shuffled back into the library, say.
 *
 * `commandersOf` finds nothing, so there is no art for the ground or the
 * window and no name for the head row. The seat falls back to its flat well,
 * which is what every seat looked like before this direction and is still a
 * perfectly good seat. What it must not do is leave a hole where the window is.
 */
export const NoCommanderVisible: Story = {
  args: seat(view([land(), creature()], { command: [] })),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await canvas.findByTestId("player-1");
    expect(canvasElement.querySelector(".seat__ground")).toBeNull();
    expect(canvasElement.querySelector(".seat__win img")).toBeNull();
  },
};
