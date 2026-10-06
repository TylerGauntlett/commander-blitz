/** The positions at the edges of the layout: a full pod, crowded and full lanes, the end. */

import type { CardView } from "../../api/types";
import * as pool from "../cards";
import { gameView } from "../fixtures";
import type { Scenario } from "./build";
import { opponent, pass, you } from "./build";

/** Four seats. `opponentCardScale(3)` is the legibility floor in cardSize.ts. */
export function fourPlayerPod(): Scenario {
  const battlefield = [
    pool.forest({ oid: 601 }),
    pool.island({ oid: 602 }),
    pool.thragtusk({ oid: 603, summoning_sick: false }),
    pool.swamp({ oid: 610, controller: 1, owner: 1 }),
    pool.grizzlyBears({ oid: 611, controller: 1, owner: 1 }),
    pool.mountain({ oid: 620, controller: 2, owner: 2 }),
    pool.krakenToken({ oid: 621, controller: 2, owner: 2 }),
    pool.plains({ oid: 630, controller: 3, owner: 3 }),
    pool.serraAngel({ oid: 631, controller: 3, owner: 3 }),
  ];

  const state = gameView({
    turn: 13,
    round: 4,
    players: [
      you({ hand: [pool.cultivate({ oid: 640, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
      opponent(2, "AI 2", { life: 28 }),
      opponent(3, "AI 3", { life: 12 }),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/**
 * Twenty permanents, twelve of them basics.
 *
 * Duplicates collapse into counted piles, so this is the position that exercises
 * `stackCards` grouping and the crowded branch of the zoom solver at once.
 */
export function crowdedBoard(): Scenario {
  const battlefield: CardView[] = [];
  let oid = 700;
  for (let i = 0; i < 7; i += 1) battlefield.push(pool.forest({ oid: oid++ }));
  for (let i = 0; i < 5; i += 1) battlefield.push(pool.island({ oid: oid++ }));
  for (let i = 0; i < 4; i += 1)
    battlefield.push(pool.krakenToken({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.thragtusk({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.serraAngel({ oid: oid++, summoning_sick: false }));
  battlefield.push(pool.solRing({ oid: oid++ }));
  battlefield.push(pool.rhysticStudy({ oid: oid++ }));

  const state = gameView({
    turn: 21,
    round: 11,
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/**
 * Four distinct artifacts and enchantments in a four-player pod.
 *
 * The Steam Deck playtest board: the global lane is a third of the front band,
 * two cards wide at handheld size, so the third card used to start a second
 * row and push the lands and the viewer's own seat off the screen. Distinct
 * cards on purpose -- duplicates collapse into one counted pile and would not
 * crowd the lane at all.
 */
export function fullGlobalLane(): Scenario {
  const battlefield = [
    pool.thragtusk({ oid: 1101, summoning_sick: false }),
    pool.serraAngel({ oid: 1102, summoning_sick: false }),
    pool.grizzlyBears({ oid: 1103, summoning_sick: false }),
    pool.solRing({ oid: 1104 }),
    pool.mindStone({ oid: 1105 }),
    pool.mindStone({ oid: 1106, card_id: "arcane_signet", name: "Arcane Signet" }),
    pool.rhysticStudy({ oid: 1107 }),
    pool.plains({ oid: 1108 }),
    pool.swamp({ oid: 1110, controller: 1, owner: 1 }),
    pool.mountain({ oid: 1120, controller: 2, owner: 2 }),
    pool.island({ oid: 1130, controller: 3, owner: 3 }),
  ];

  const state = gameView({
    turn: 5,
    round: 5,
    players: [
      you({ hand: [pool.cultivate({ oid: 1140, zone: "hand" })] }, battlefield),
      opponent(1, "AI 1"),
      opponent(2, "AI 2"),
      opponent(3, "AI 3"),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** A creature wearing an Aura and an Equipment: the tucked-attachment path. */
export function withAttachments(): Scenario {
  const host = pool.serraAngel({ oid: 801, summoning_sick: false });
  const battlefield = [
    host,
    pool.rancor({ oid: 802, attached_to: 801 }),
    pool.swordOfFireAndIce({ oid: 803, attached_to: 801 }),
    pool.plains({ oid: 804 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** Graveyard, exile and command all populated, so the zone viewer has content. */
export function fullZones(): Scenario {
  const battlefield = [pool.forest({ oid: 851 }), pool.island({ oid: 852 })];
  const state = gameView({
    turn: 15,
    round: 8,
    players: [
      you(
        {
          hand: [pool.counterspell({ oid: 860, zone: "hand" })],
          graveyard: [
            pool.grizzlyBears({ oid: 870, zone: "graveyard" }),
            pool.forest({ oid: 871, zone: "graveyard" }),
            pool.forest({ oid: 872, zone: "graveyard" }),
            pool.cultivate({ oid: 873, zone: "graveyard" }),
          ],
          exile: [pool.thragtusk({ oid: 880, zone: "exile" })],
        },
        battlefield,
      ),
      opponent(1, "AI 1"),
    ],
    battlefield,
  });

  return { state, actions: [pass], events: [] };
}

/** Somebody won. `winners: [0]` is the viewer, so this is the victory face. */
export function gameOver(winner = 0): Scenario {
  const state = gameView({
    turn: 30,
    round: 15,
    game_over: true,
    winners: [winner],
    result: winner === 0 ? "You win" : "AI 1 wins",
    pending: null,
    players: [
      you({ hand: [], life: winner === 0 ? 22 : 0, has_lost: winner !== 0 }),
      opponent(1, "AI 1", {
        life: winner === 1 ? 18 : 0,
        has_lost: winner !== 1,
        loss_reason: winner !== 1 ? "life" : null,
      }),
    ],
  });

  return { state, actions: [], events: [] };
}
