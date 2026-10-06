/**
 * Whole positions, not single cards.
 *
 * A macro component needs a `GameView` whose parts agree with each other.
 * `logic/actionMatch.ts` looks up an action's `source_oid` on the battlefield,
 * `logic/zoneGrouping.ts` bands permanents by controller, `logic/autoBlock.ts`
 * pairs attackers against blockers, and `PlayerOrb` reads a payment forecast
 * against the mana sources it drew. A state assembled field by field renders
 * happily and tests none of that -- the component takes every branch marked
 * "nothing here", and the story passes while showing an empty board.
 *
 * So the positions are built here, once, with their legal-action lists *derived
 * from the state* rather than written beside it. The client never constructs an
 * action -- it echoes back an opaque id -- so an action list a real engine could
 * not have sent is the one kind of fixture that quietly invalidates a story.
 */

export type { Scenario } from "./build";
export * from "./extremes";
export * from "./hands";
export * from "./log";
export * from "./positions";
export * from "./prompts";
