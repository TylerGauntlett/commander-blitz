/** The props `Table` takes, for a story. Shared by the `Table*.stories.tsx` files. */

import { fn } from "storybook/test";
import { fakeGame } from "./fakeGame";
import type { Scenario } from "./scenarios";

/** A scenario, wired into the props `Table` takes. */
export function board(scenario: Scenario, game = {}) {
  return {
    session: { gameId: "story", seat: 0 },
    state: scenario.state,
    game: fakeGame({ state: scenario.state, actions: scenario.actions, ...game }),
    onQuit: fn(),
    onRematch: fn(),
  };
}
