import { describe, expect, it } from "vitest";
import { counterBadges, manaPips, statLine } from "../src/logic/cardStyle";
import {
  LANES,
  attachmentsFor,
  commandersOf,
  findCard,
  findCardByDefId,
  groupBattlefield,
  laneFor,
  seatOrder,
} from "../src/logic/zoneGrouping";
import { card, gameView, player, stackItem } from "./fixtures";

/**
 * The lanes are declared front to back -- toward the opponent first, the
 * player's own lands last -- because `PlayerMat` renders them in that order and
 * a player's mana belongs in the row nearest them. Reordering this array moves
 * the board, so it is asserted rather than assumed.
 */
describe("LANES", () => {
  it("runs from the opponent's side back to the player's own", () => {
    expect(LANES).toEqual(["Creatures", "Artifacts & Enchantments", "Lands"]);
  });
});

describe("laneFor", () => {
  it("puts creatures in the creature lane", () => {
    expect(laneFor(card({ types: ["Creature"] }))).toBe("Creatures");
  });

  it("puts lands in the land lane", () => {
    expect(laneFor(card({ types: ["Land"] }))).toBe("Lands");
  });

  it("groups artifacts and enchantments together", () => {
    expect(laneFor(card({ types: ["Artifact"] }))).toBe("Artifacts & Enchantments");
    expect(laneFor(card({ types: ["Enchantment"] }))).toBe("Artifacts & Enchantments");
  });

  it("treats an artifact creature as a creature", () => {
    expect(laneFor(card({ types: ["Artifact", "Creature"] }))).toBe("Creatures");
  });

  it("puts planeswalkers on the creature line, where combat is declared", () => {
    expect(laneFor(card({ types: ["Planeswalker"] }))).toBe("Creatures");
  });

  it("sends an attached permanent to its host's lane", () => {
    const aura = card({ types: ["Enchantment"], subtypes: ["Aura"], attached_to: 9 });
    expect(laneFor(aura)).toBe("Creatures");
  });

  it("sends an unattached Aura or Equipment there too, so a drag from hand aims right", () => {
    // `canDropOnLane` asks this same function which lane to highlight, and from
    // hand nothing is attached yet.
    expect(laneFor(card({ types: ["Enchantment"], subtypes: ["Aura"] }))).toBe("Creatures");
    expect(laneFor(card({ types: ["Artifact"], subtypes: ["Equipment"] }))).toBe("Creatures");
  });
});

describe("groupBattlefield", () => {
  it("only includes the requested controller", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 1, controller: 0, types: ["Creature"] }),
        card({ oid: 2, controller: 1, types: ["Creature"] }),
        card({ oid: 3, controller: 0, types: ["Land"] }),
      ],
    });
    const mine = groupBattlefield(state, 0);
    expect(mine.Creatures.map((c) => c.oid)).toEqual([1]);
    expect(mine.Lands.map((c) => c.oid)).toEqual([3]);
    expect(groupBattlefield(state, 1).Creatures.map((c) => c.oid)).toEqual([2]);
  });

  it("preserves battlefield order within a lane", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 7, types: ["Creature"] }),
        card({ oid: 3, types: ["Creature"] }),
      ],
    });
    expect(groupBattlefield(state, 0).Creatures.map((c) => c.oid)).toEqual([7, 3]);
  });

  it("holds back a permanent that is drawn tucked behind its host", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 1, controller: 0, types: ["Creature"] }),
        card({
          oid: 2,
          controller: 0,
          types: ["Enchantment"],
          subtypes: ["Aura"],
          attached_to: 1,
        }),
      ],
    });
    const mine = groupBattlefield(state, 0);
    expect(mine.Creatures.map((c) => c.oid)).toEqual([1]);
    expect(mine["Artifacts & Enchantments"]).toEqual([]);
  });

  it("keeps an aura on somebody else's creature as a loose card", () => {
    // Its host is not on this mat, so tucking it would put it on a board it
    // does not belong to -- or, worse, drop it from every board at once.
    const state = gameView({
      battlefield: [
        card({ oid: 1, controller: 1, types: ["Creature"] }),
        card({
          oid: 2,
          controller: 0,
          types: ["Enchantment"],
          subtypes: ["Aura"],
          attached_to: 1,
        }),
      ],
    });
    expect(groupBattlefield(state, 0).Creatures.map((c) => c.oid)).toEqual([2]);
    expect(attachmentsFor(state, 0).size).toBe(0);
    expect(attachmentsFor(state, 1).size).toBe(0);
  });

  it("keeps an attachment whose host has already left", () => {
    const state = gameView({
      battlefield: [
        card({
          oid: 2,
          controller: 0,
          types: ["Enchantment"],
          subtypes: ["Aura"],
          attached_to: 99,
        }),
      ],
    });
    expect(groupBattlefield(state, 0).Creatures.map((c) => c.oid)).toEqual([2]);
  });
});

describe("attachmentsFor", () => {
  it("keys every tucked permanent by the host that carries it", () => {
    const state = gameView({
      battlefield: [
        card({ oid: 1, controller: 0, types: ["Creature"] }),
        card({
          oid: 2,
          controller: 0,
          types: ["Artifact"],
          subtypes: ["Equipment"],
          attached_to: 1,
        }),
        card({
          oid: 3,
          controller: 0,
          types: ["Enchantment"],
          subtypes: ["Aura"],
          attached_to: 1,
        }),
      ],
    });
    expect([...(attachmentsFor(state, 0).get(1) ?? [])].map((c) => c.oid)).toEqual([2, 3]);
  });

  it("is empty for a board with nothing attached", () => {
    const state = gameView({ battlefield: [card({ oid: 1, types: ["Creature"] })] });
    expect(attachmentsFor(state, 0).size).toBe(0);
  });
});

describe("seatOrder", () => {
  it("puts the viewer last so they render at the bottom", () => {
    const state = gameView({
      seat: 0,
      players: [player(), player({ pid: 1 }), player({ pid: 2 }), player({ pid: 3 })],
    });
    expect(seatOrder(state)).toEqual([1, 2, 3, 0]);
  });

  it("rotates for a different viewing seat", () => {
    const state = gameView({
      seat: 2,
      players: [player(), player({ pid: 1 }), player({ pid: 2 }), player({ pid: 3 })],
    });
    expect(seatOrder(state)).toEqual([3, 0, 1, 2]);
  });
});

describe("statLine", () => {
  it("shows remaining toughness on the battlefield", () => {
    expect(statLine(card({ power: 5, toughness: 5, damage: 2 }))).toBe("5/3");
  });

  it("shows printed toughness elsewhere", () => {
    expect(statLine(card({ zone: "hand", power: 5, toughness: 5, damage: 0 }))).toBe("5/5");
  });

  it("is empty for a non-creature", () => {
    expect(statLine(card({ power: null, toughness: null }))).toBe("");
  });
});

describe("counterBadges", () => {
  it("renders a multiplier only above one", () => {
    expect(counterBadges(card({ counters: { "+1/+1": 1 } }))).toEqual(["+1/+1"]);
    expect(counterBadges(card({ counters: { "+1/+1": 3 } }))).toEqual(["+1/+1 x3"]);
  });

  it("ignores empty counter maps", () => {
    expect(counterBadges(card({ counters: {} }))).toEqual([]);
  });
});

describe("manaPips", () => {
  it("splits a cost into symbols", () => {
    expect(manaPips("{4}{G}{U}").map((pip) => pip.symbol)).toEqual(["4", "G", "U"]);
  });

  it("gives repeated symbols distinct keys", () => {
    const keys = manaPips("{G}{G}").map((pip) => pip.key);
    expect(new Set(keys).size).toBe(2);
  });

  it("returns nothing for a free cost", () => {
    expect(manaPips("{0}")).toEqual([]);
    expect(manaPips("")).toEqual([]);
  });
});

/**
 * The commander dock's source of truth.
 *
 * In Commander the commander is the card the deck is built around, so the dock
 * shows it at all times rather than only while it happens to be in the command
 * zone -- having it vanish from the interface the moment it resolves is the
 * opposite of what a player wants to track. See docs/playtest-feedback-02.md.
 */
describe("commandersOf", () => {
  const boss = (overrides = {}) =>
    card({ oid: 50, name: "Aesi", is_commander: true, owner: 0, controller: 0, ...overrides });

  it("finds a commander sitting in the command zone", () => {
    const state = gameView({
      players: [player({ command: [boss({ zone: "command" })] }), player({ pid: 1 })],
    });
    expect(commandersOf(state, 0).map((c) => c.oid)).toEqual([50]);
  });

  it("still finds it once it has resolved onto the battlefield", () => {
    const state = gameView({ battlefield: [boss({ zone: "battlefield" })] });
    expect(commandersOf(state, 0).map((c) => c.name)).toEqual(["Aesi"]);
  });

  it("keeps showing it while it is on the stack", () => {
    // Not an edge case: casting the commander is what the dock is for, and
    // between the click and the spell resolving the card is in no other zone.
    // Without this the dock blinks empty at the moment the player is watching.
    const spell = boss({ zone: "stack" });
    const state = gameView({
      stack: [
        {
          sid: 1,
          kind: "spell",
          controller: 0,
          def_id: "aesi",
          name: "Aesi",
          type_line: "Legendary Creature",
          oid: 50,
          source_oid: null,
          targets: [],
          description: "",
          card: spell,
        },
      ],
    });
    expect(commandersOf(state, 0).map((c) => c.zone)).toEqual(["stack"]);
  });

  it("finds it in the graveyard, before it is put back", () => {
    const state = gameView({
      players: [player({ graveyard: [boss({ zone: "graveyard" })] }), player({ pid: 1 })],
    });
    expect(commandersOf(state, 0)).toHaveLength(1);
  });

  it("finds it in exile", () => {
    const state = gameView({
      players: [player({ exile: [boss({ zone: "exile" })] }), player({ pid: 1 })],
    });
    expect(commandersOf(state, 0)).toHaveLength(1);
  });

  it("never lists the same object twice", () => {
    // The command zone is searched first and the battlefield after it; a payload
    // that somehow carried both must not produce two docked cards.
    const inZone = boss({ zone: "command" });
    const state = gameView({
      battlefield: [inZone],
      players: [player({ command: [inZone] }), player({ pid: 1 })],
    });
    expect(commandersOf(state, 0)).toHaveLength(1);
  });

  it("does not claim another player's commander", () => {
    const theirs = card({
      oid: 60,
      is_commander: true,
      owner: 1,
      controller: 1,
      zone: "battlefield",
    });
    const state = gameView({ battlefield: [theirs] });
    expect(commandersOf(state, 0)).toEqual([]);
  });

  it("follows ownership, not control, when a commander is stolen", () => {
    // Control can change; the dock belongs to whoever will get the card back.
    const stolen = card({
      oid: 50,
      is_commander: true,
      owner: 0,
      controller: 1,
      zone: "battlefield",
    });
    const state = gameView({ battlefield: [stolen] });
    expect(commandersOf(state, 0)).toHaveLength(1);
    expect(commandersOf(state, 1)).toEqual([]);
  });

  it("is empty while the commander is somewhere the viewer cannot see", () => {
    // Returned to hand, or shuffled into the library: there is no view to draw.
    expect(commandersOf(gameView(), 0)).toEqual([]);
  });

  it("handles a deck with two commanders", () => {
    const state = gameView({
      players: [
        player({
          command: [
            boss({ zone: "command" }),
            boss({ oid: 51, name: "Partner", zone: "command" }),
          ],
        }),
        player({ pid: 1 }),
      ],
    });
    expect(commandersOf(state, 0).map((c) => c.oid)).toEqual([50, 51]);
  });
});

/**
 * Resolving a spotlight's card.
 *
 * Events name a card by its *definition* id, not by object id, so the spotlight
 * cannot resolve a face the way a target can.
 */
describe("findCardByDefId", () => {
  const bolt = (overrides = {}) => card({ card_id: "lightning_bolt", ...overrides });

  it("prefers the copy still on the stack", () => {
    const state = gameView({
      stack: [
        {
          sid: 1,
          kind: "spell",
          controller: 0,
          def_id: "lightning_bolt",
          name: "Lightning Bolt",
          type_line: "Instant",
          oid: 7,
          source_oid: null,
          targets: [],
          description: "",
          card: bolt({ oid: 7, zone: "stack" }),
        },
      ],
      battlefield: [bolt({ oid: 8 })],
    });
    expect(findCardByDefId(state, "lightning_bolt")?.oid).toBe(7);
  });

  it("falls back to wherever the card landed once it resolved", () => {
    const state = gameView({
      players: [
        player({ graveyard: [bolt({ oid: 9, zone: "graveyard" })] }),
        player({ pid: 1 }),
      ],
    });
    expect(findCardByDefId(state, "lightning_bolt")?.oid).toBe(9);
  });

  it("prefers the requested controller's copy", () => {
    // Singleton decks make same-card collisions between seats common enough to
    // matter and cheap enough to get right.
    const state = gameView({
      battlefield: [bolt({ oid: 8, controller: 1 }), bolt({ oid: 9, controller: 0 })],
    });
    expect(findCardByDefId(state, "lightning_bolt", 0)?.oid).toBe(9);
  });

  it("takes somebody else's copy rather than showing nothing", () => {
    // The right card belonging to the wrong player is still the right card.
    const state = gameView({ battlefield: [bolt({ oid: 8, controller: 1 })] });
    expect(findCardByDefId(state, "lightning_bolt", 0)?.oid).toBe(8);
  });

  it("returns null when the card is nowhere visible", () => {
    // A countered spell has already left every zone the viewer can see; the
    // spotlight falls back to a name plate rather than rendering a gap.
    expect(findCardByDefId(gameView(), "lightning_bolt")).toBeNull();
  });
});

/**
 * What the preview rail resolves a hovered oid against.
 *
 * The stack case is the one that was missing, and it was not an edge case:
 * `commandersOf` deliberately keeps a commander on the plinth while it is
 * mid-cast, so the panel was drawing a card the rail could not find for exactly
 * the beat the player was watching it.
 */
describe("findCard", () => {
  it("finds a card on the stack", () => {
    const state = gameView({ stack: [stackItem({ card: card({ oid: 7, zone: "stack" }) })] });
    expect(findCard(state, 7)?.oid).toBe(7);
  });

  it("searches the stack before the battlefield, as findCardByDefId does", () => {
    // Mid-cast the object is on its way to the battlefield; the stack copy is
    // the live one. Two functions answering the same question in two orders is
    // how they drift apart.
    const state = gameView({
      stack: [stackItem({ card: card({ oid: 7, zone: "stack", name: "In flight" }) })],
      battlefield: [card({ oid: 7, zone: "battlefield", name: "Landed" })],
    });
    expect(findCard(state, 7)?.name).toBe("In flight");
  });

  it("still finds the battlefield, hand, graveyard, exile and command zone", () => {
    const state = gameView({
      players: [
        player({
          pid: 0,
          hand: [card({ oid: 2, zone: "hand" })],
          graveyard: [card({ oid: 3, zone: "graveyard" })],
          exile: [card({ oid: 4, zone: "exile" })],
          command: [card({ oid: 5, zone: "command" })],
        }),
        player({ pid: 1, hand: null }),
      ],
      battlefield: [card({ oid: 1 })],
    });
    for (const oid of [1, 2, 3, 4, 5]) {
      expect(findCard(state, oid)?.oid).toBe(oid);
    }
  });

  it("returns null for an oid in a hidden zone", () => {
    // A card in the library has no view to return. An empty preview beats a
    // crash, and the rail falls back to its idle line.
    expect(findCard(gameView(), 4242)).toBeNull();
  });

  it("survives a stack item whose face has already left the game", () => {
    // `StackItemView.card` is nullable for exactly that case.
    const state = gameView({ stack: [stackItem({ card: null })] });
    expect(findCard(state, 1)).toBeNull();
  });
});
