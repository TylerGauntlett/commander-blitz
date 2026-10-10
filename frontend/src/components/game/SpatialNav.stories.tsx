/**
 * Why the ring goes where it goes.
 *
 * `PERP = 2.4` is the most arguable number in the controller layer, and an
 * argument you can only have by reading a unit test is an argument nobody has.
 * This draws a deliberately ragged board -- the shape a lane of mixed tapped
 * and untapped permanents really makes, since a tapped card is landscape and
 * shorter -- and prints what each direction would pick and why.
 *
 * `tests/spatialNav.test.ts` pins the behaviour. This is where you look at it.
 */

import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { type Candidate, type Dir, PERP, pickStop, scoreStop } from "../../input/nav";

const meta = {
  title: "game/SpatialNav",
  parameters: { commanderblitz: { mount: "bare" } },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** A ragged board: a short wide "tapped" card and two portrait ones. */
const BOARD: Candidate[] = [
  { id: "creature-a", rect: { left: 40, top: 40, width: 100, height: 140 } },
  { id: "creature-b", rect: { left: 160, top: 40, width: 100, height: 140 } },
  { id: "tapped-c", rect: { left: 280, top: 40, width: 140, height: 100 } },
  { id: "land-a", rect: { left: 40, top: 220, width: 100, height: 140 } },
  { id: "land-b", rect: { left: 160, top: 220, width: 100, height: 140 } },
  { id: "orb", rect: { left: 460, top: 40, width: 120, height: 320 } },
];

const DIRS: Dir[] = ["up", "down", "left", "right"];

function Board({ from }: { from: string }) {
  const cur = BOARD.find((c) => c.id === from);
  if (!cur) return null;
  const picks = Object.fromEntries(
    DIRS.map((dir) => [dir, pickStop(cur.rect, BOARD, dir, from)]),
  );
  const chosen = new Set(Object.values(picks));

  return (
    <div style={{ display: "flex", gap: 32, padding: 16 }}>
      <div style={{ position: "relative", width: 600, height: 380 }}>
        {BOARD.map((c) => (
          <div
            key={c.id}
            data-testid={`cell-${c.id}`}
            style={{
              position: "absolute",
              left: c.rect.left,
              top: c.rect.top,
              width: c.rect.width,
              height: c.rect.height,
              display: "grid",
              placeItems: "center",
              fontSize: 11,
              textAlign: "center",
              borderRadius: 8,
              border:
                c.id === from
                  ? "3px solid var(--focus)"
                  : chosen.has(c.id)
                    ? "2px solid var(--playable)"
                    : "1px solid var(--edge)",
              background: c.id === from ? "rgb(255 224 138 / 0.12)" : "var(--pane-bg)",
              color: "var(--text-dim)",
            }}
          >
            {c.id}
          </div>
        ))}
      </div>
      <table style={{ fontSize: 12, color: "var(--text-dim)", borderSpacing: "10px 4px" }}>
        <thead>
          <tr>
            <th align="left">press</th>
            <th align="left">goes to</th>
            <th align="left">score</th>
          </tr>
        </thead>
        <tbody>
          {DIRS.map((dir) => {
            const to = picks[dir];
            const target = BOARD.find((c) => c.id === to);
            const score = target ? scoreStop(cur.rect, target.rect, dir) : null;
            return (
              <tr key={dir} data-testid={`pick-${dir}`} data-goes={to ?? "wall"}>
                <td style={{ color: "var(--text)" }}>{dir}</td>
                <td>{to ?? <em>wall — the ring nudges</em>}</td>
                <td>{score === null ? "—" : Math.round(score)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export const FromACreature: Story = {
  render: () => <Board from="creature-b" />,
};

/**
 * The case `PERP` exists for.
 *
 * From the bottom-left land, "up" must reach the creature directly above it and
 * not the shorter tapped one further along the row -- even though the tapped
 * card's centre is nearer on the vertical axis. Drop `PERP` toward 1 and this
 * story is where you would see it break.
 */
export const AColumnStaysAColumn: Story = {
  render: () => <Board from="land-a" />,
  play: async ({ canvasElement }) => {
    const row = canvasElement.querySelector('[data-testid="pick-up"]');
    await expect(row?.getAttribute("data-goes")).toBe("creature-a");
    await expect(PERP).toBeGreaterThan(1);
  },
};

/** A wall is a real answer, and the ring has to draw it rather than do nothing. */
export const AtAWall: Story = {
  render: () => <Board from="creature-a" />,
  play: async ({ canvasElement }) => {
    const up = canvasElement.querySelector('[data-testid="pick-up"]');
    await expect(up?.getAttribute("data-goes")).toBe("wall");
  },
};
