/**
 * Where the ring goes when the decision you just started needs a second press.
 *
 * `logic/focusGroup.ts` answers "which REGION does this decision live in", once
 * per decision. This answers the question underneath it: half the decisions in
 * this game are two presses, and nothing moved between them.
 *
 * Press an instant in your hand and the board lights up with legal targets --
 * and the ring is still on the card in your hand, four regions away from every
 * one of them. Press one of your creatures during a block declaration and the
 * attacker it has to be pointed at is on an opponent's board, which at 1280x800
 * is a lane clipped to zero height that `stops.ts:onScreen` correctly refuses to
 * land on. A pointer never pays either cost, because a pointer arrives at the
 * second half of a decision by moving there.
 *
 * ## An ORDERED LIST, and that is what makes it work at both sizes
 *
 * Every function here returns candidates best-first rather than one answer, and
 * the caller takes the first that lands. `setCursor` already returns `false`
 * for a stop that is not currently reachable, so a target on an opponent's
 * board wins on a desktop, and on a handheld -- where that same card is clipped
 * -- it is declined and the PANEL's row for the same action wins. One rule, no
 * layout branch, and nothing here has to know what a handheld is.
 *
 * ## Pure, like its neighbour
 *
 * Nothing here touches the DOM or the cursor, which is what makes it a table of
 * states in `tests/followUp.test.ts` rather than something you can only argue
 * about with a browser open. `Table` does the moving, and `Table` is also where
 * the group has to be released first -- see `cursor.ts:moveCursor`, which
 * records what happens when it is not.
 *
 * ## It must not fight the player
 *
 * Every rule here fires on a gesture the player just made, never on a state the
 * engine pushed. That is the line `focusGroup`'s header draws for the same
 * reason: a ring that returns to where the app thinks you should be is worse
 * than one that stays where you put it. A press is a request; a poll is not.
 */

import type { CardView, GameView, LegalAction } from "../api/types";
import { blockableBy } from "./actionMatch";
import { blockTier } from "./autoBlock";
import { findCard } from "./zoneGrouping";

/** `input/stops.ts`'s namespace, restated as the three shapes used here. */
const cardStop = (oid: number) => `card:${oid}`;
const orbStop = (pid: number) => `orb:${pid}`;
const actStop = (id: string) => `act:${id}`;

/**
 * What the player just did. One shape per gesture that leaves a decision half
 * finished, which is the whole set this module is about.
 */
export type Gesture =
  | { kind: "targeting"; actionIds: string[] }
  | { kind: "blocker-selected"; blocker: number }
  | { kind: "block-staged"; blocker: number }
  | { kind: "played-from-hand"; oid: number };

/**
 * How much this permanent wants to be shot at.
 *
 * Higher first. An opponent's board before your own, because a spell you aimed
 * by hand is nearly always removal and removal points across the table; then
 * the biggest thing, because that is what removal is for. Anything past that is
 * a guess about a card's text, and a guess that puts the ring on the wrong
 * creature costs the player exactly the press it was trying to save.
 */
function targetRank(state: GameView, target: CardView): number {
  const theirs = target.controller !== state.seat ? 1000 : 0;
  return theirs + (target.power ?? 0);
}

/**
 * Where to stand to finish a spell that is waiting for a target.
 *
 * Board targets first, then players, then the panel row that carries the same
 * action id. The panel is last and is never omitted: it is the one surface that
 * is reachable whatever the layout has done to the board, so it is what keeps
 * this from ever being a dead end.
 */
export function targetStops(
  state: GameView,
  actions: LegalAction[],
  actionIds: readonly string[],
): string[] {
  const live = actions.filter((action) => actionIds.includes(action.id));
  const objects: { oid: number; rank: number }[] = [];
  const players: number[] = [];
  for (const action of live) {
    for (const ref of action.targets) {
      if (ref.kind === "object") {
        const target = findCard(state, ref.id);
        if (target) objects.push({ oid: ref.id, rank: targetRank(state, target) });
      } else if (ref.kind === "player") {
        players.push(ref.id);
      }
    }
  }
  objects.sort((a, b) => b.rank - a.rank || a.oid - b.oid);
  players.sort((a, b) => Number(a === state.seat) - Number(b === state.seat) || a - b);

  const out: string[] = [];
  for (const entry of objects) push(out, cardStop(entry.oid));
  for (const pid of players) push(out, orbStop(pid));
  for (const action of live) push(out, actStop(action.id));
  return out;
}

/**
 * Where to stand once a blocker is picked: the attacker it should stop.
 *
 * Ranked by `blockTier`, so the first press after choosing a creature lands on
 * the block that creature actually wants to make. The `act:` row for the same
 * pairing follows each card, rather than being appended in a block of its own,
 * because the two are one answer -- if the card is unreachable the row for THAT
 * attacker is the fallback, not the row for the next one down the list.
 */
export function blockTargetStops(
  state: GameView,
  actions: LegalAction[],
  blocker: number,
): string[] {
  const mine = findCard(state, blocker);
  if (!mine) return [];
  const ranked = blockableBy(actions, blocker)
    .map((attacker) => {
      const theirs = findCard(state, attacker);
      return { attacker, tier: theirs ? blockTier(mine, theirs) : 4 };
    })
    .sort((a, b) => a.tier - b.tier || a.attacker - b.attacker);

  const out: string[] = [];
  for (const entry of ranked) {
    push(out, cardStop(entry.attacker));
    const row = actions.find(
      (action) =>
        action.kind === "add_blocker" &&
        action.source_oid === blocker &&
        action.targets.some((ref) => ref.kind === "object" && ref.id === entry.attacker),
    );
    if (row) push(out, actStop(row.id));
  }
  return out;
}

/**
 * Where to stand after a block is staged: your next creature with a job.
 *
 * Blocking a pod's worth of attackers is the same two presses repeated, and
 * without this the second one starts with a walk back across your own board.
 * Only creatures that can still block something, and never the one just used.
 */
export function nextBlockerStops(
  actions: LegalAction[],
  staged: Readonly<Record<number, number>>,
  just: number,
): string[] {
  const free = [
    ...new Set(
      actions
        .filter((action) => action.kind === "add_blocker")
        .map((action) => action.source_oid),
    ),
  ]
    .filter((oid): oid is number => oid !== null)
    .filter((oid) => oid !== just && staged[oid] === undefined)
    .sort((a, b) => a - b);
  return free.map(cardStop);
}

/**
 * Where to stand after a card leaves your hand.
 *
 * THE RING WAS LEFT ON THE CARD, AND THE CARD WAS NO LONGER IN YOUR HAND.
 * `resolveCursor` keeps the ring on the object the engine replaced, which is
 * exactly right for a permanent that stayed where it was and exactly wrong for
 * one that went from hand to battlefield: the ring silently moved down to the
 * lands while `data-group` still said `hand`, and the next direction press
 * teleported back to whichever hand card happened to win the scoring. Playing a
 * land is the most repeated gesture in the game and it ended somewhere the
 * player did not ask to be.
 *
 * So the ring stays IN THE HAND: on the next card you could actually play, and
 * failing that on whatever is still there. The second half is not a courtesy --
 * the commonest case in the game is the land drop, which spends itself, so
 * "nothing is playable now" is exactly the state the most repeated gesture
 * leaves behind. An empty list means the hand is empty, and then there is
 * genuinely nowhere in it to be.
 */
export function nextHandStops(
  state: GameView,
  actions: LegalAction[],
  played: number,
): string[] {
  const hand = (state.players[state.seat]?.hand ?? []).filter((entry) => entry.oid !== played);
  const playable = new Set(
    actions
      .filter((action) => action.kind === "cast" || action.kind === "play_land")
      .map((action) => action.source_oid),
  );
  const out: string[] = [];
  for (const entry of hand) if (playable.has(entry.oid)) push(out, cardStop(entry.oid));
  for (const entry of hand) push(out, cardStop(entry.oid));
  return out;
}

/** The candidates for one gesture, best first. Empty means "leave the ring alone". */
export function followUpStops(
  state: GameView,
  actions: LegalAction[],
  gesture: Gesture,
  staged: Readonly<Record<number, number>> = {},
): string[] {
  switch (gesture.kind) {
    case "targeting":
      return targetStops(state, actions, gesture.actionIds);
    case "blocker-selected":
      return blockTargetStops(state, actions, gesture.blocker);
    case "block-staged":
      return nextBlockerStops(actions, staged, gesture.blocker);
    case "played-from-hand":
      return nextHandStops(state, actions, gesture.oid);
  }
}

/** Append unless it is already there. Order is the answer, so duplicates are noise. */
function push(out: string[], id: string): void {
  if (!out.includes(id)) out.push(id);
}
