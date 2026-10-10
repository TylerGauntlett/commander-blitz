/** Modal decisions about everything else: targets, modes, types, players, searches. */

import * as pool from "../cards";
import { action, decisionOption, gameView, pending } from "../fixtures";
import type { Scenario } from "./build";
import { opponent, pass, you } from "./build";

/** Choosing a permanent: options that name real objects draw as real cards. */
export function chooseTarget(): Scenario {
  const battlefield = [
    pool.grizzlyBears({ oid: 901 }),
    pool.serraAngel({ oid: 902 }),
    pool.wallOfRoots({ oid: 903 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
    pending: pending({ kind: "choose_objects", prompt: "Sacrifice a creature" }),
  });

  return {
    state,
    actions: battlefield.map((c, i) =>
      action({
        id: `a${i}-choose`,
        kind: "choose",
        label: c.name,
        base_label: c.name,
        targets: [{ kind: "object", id: c.oid }],
      }),
    ),
    events: [],
  };
}

/**
 * "Exile up to two target artifacts and/or enchantments" -- Angel of the Ruins.
 *
 * Both sides of the table, in the engine's order (an opponent's first), so the
 * dialog has to put yours back in front. `Done` is legal because "up to"
 * allows none.
 */
export function chooseSeveralTargets(): Scenario {
  const battlefield = [
    pool.rhysticStudy({ oid: 811, controller: 1, owner: 1 }),
    pool.solRing({ oid: 801 }),
    pool.solRing({ oid: 812, controller: 1, owner: 1 }),
    pool.rhysticStudy({ oid: 802 }),
  ];
  const options = battlefield.map((c, i) =>
    decisionOption({ label: c.name, ref: { kind: "object", id: c.oid }, value: i }),
  );

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
    pending: pending({
      kind: "choose_objects",
      prompt:
        "Choose targets for Angel of the Ruins: When this creature enters, exile up to two target artifacts and/or enchantments.",
      options,
      min_count: 0,
      max_count: 2,
      context: { purpose: "target", source_name: "Angel of the Ruins" },
    }),
  });

  return {
    state,
    actions: [
      ...battlefield.map((c, i) =>
        action({
          id: `a${i}-choose`,
          kind: "choose",
          label: c.name,
          base_label: c.name,
          choice: i,
          targets: [{ kind: "object", id: c.oid }],
        }),
      ),
      action({
        id: "a4-finish_declaration",
        kind: "finish_declaration",
        label: "Done",
        base_label: "Done",
      }),
    ],
    events: [],
  };
}

/** A modal spell: three modes, no targets yet. */
export function chooseMode(): Scenario {
  const state = gameView({
    players: [you({ hand: [pool.simicCharm({ oid: 950, zone: "hand" })] })],
    pending: pending({ kind: "choose_mode", prompt: "Choose one —" }),
  });

  return {
    state,
    actions: [
      action({
        id: "a0-choose",
        kind: "choose",
        label: "Target creature gets +3/+3 until end of turn",
        base_label: "Target creature gets +3/+3 until end of turn",
        choice: 0,
      }),
      action({
        id: "a1-choose",
        kind: "choose",
        label: "Return target creature to its owner's hand",
        base_label: "Return target creature to its owner's hand",
        choice: 1,
      }),
      action({
        id: "a2-choose",
        kind: "choose",
        label: "Target creature you control gains hexproof until end of turn",
        base_label: "Target creature you control gains hexproof until end of turn",
        choice: 2,
      }),
    ],
    events: [],
  };
}

/**
 * Herald's Horn: choose a creature type, from every type in the pool.
 *
 * The real list, lifted out of `data/cards/` rather than invented -- 199 of
 * them here and up to `MAX_TYPE_CHOICES` (400) in a full pool. The engine sends
 * this as an ordinary `choose_mode` with one option per type, which is exactly
 * why the client decides on the *shape* of a decision rather than its kind: no
 * discriminator distinguishes this from a three-mode charm.
 */
export const CREATURE_TYPES = `
  Advisor Aetherborn Alien Ally Andorian Angel Antelope Ape Archer Artificer Assassin
  Astartes Avatar Badger Barbarian Basilisk Bat Bear Beast Berserker Bird Boar Caitian
  Camel Cat Centaur Chimera Citizen Cleric Cockatrice Construct Crab Crocodile Cyclops
  Dauthi Demon Devil Dinosaur Djinn Doctor Dog Dragon Drake Drone Druid Dryad Dwarf Efreet
  Elder Eldrazi Elemental Elephant Elf Elk Faerie Fish Forest Fox Frog Fungus Gamma
  Gargoyle Giant Gnome Goat Goblin God Golem Gorgon Gorn Gremlin Griffin Hag Harpy Hero
  Hippo Hippogriff Homunculus Horror Horse Human Hydra Hyena Illusion Imp Insect Jackal
  Jellyfish Kavu Kirin Kithkin Klingon Knight Kobold Kor Kraken Kree Lammasu Leech Lemur
  Leviathan Lizard Mercenary Merfolk Minion Minotaur Mole Mongoose Monk Monkey Moonfolk
  Mutant Myr Mystic Nightmare Nightstalker Ninja Noble Nomad Nymph Octopus Officer Ogre
  Ooze Orc Orgg Otter Ox Pangolin Peasant Pegasus Performer Phyrexian Pilot Pirate Plant
  Praetor Rabbit Ranger Rat Rebel Rhino Robot Rogue Sable Salamander Saproling Satyr
  Scarecrow Scientist Scorpion Scout Seal Serpent Shaman Shapeshifter Shark Sheep Siren
  Skeleton Sliver Sloth Slug Snake Soldier Soltari Sorcerer Sphinx Spider Spirit Spy
  Squirrel Surrakar Symbiote Thalakos Thopter Thrull Treefolk Troll Turtle Tyranid Unicorn
  Vampire Vedalken Villain Vulcan Wall Walrus Warlock Warrior Weasel Werewolf Whale Wizard
  Wolf Wraith Wurm Yeti Zombie
`
  .trim()
  .split(/\s+/);

export function chooseType(): Scenario {
  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({
      kind: "choose_mode",
      prompt: "Choose a creature type",
      options: CREATURE_TYPES.map((label, i) => decisionOption({ label, value: i })),
      context: { source: 960, source_name: "Herald's Horn" },
    }),
  });

  return {
    state,
    actions: CREATURE_TYPES.map((label, i) =>
      action({ id: `a${i}-choose`, kind: "choose", label, base_label: label, choice: i }),
    ),
    events: [],
  };
}

/** Pointing at a player rather than a permanent. */
export function choosePlayer(): Scenario {
  const state = gameView({
    players: [you({ hand: [] }), opponent(1, "AI 1"), opponent(2, "AI 2")],
    pending: pending({ kind: "choose_player", prompt: "Choose an opponent" }),
  });

  return {
    state,
    actions: [1, 2].map((pid) =>
      action({
        id: `a${pid}-choose`,
        kind: "choose",
        label: `AI ${pid}`,
        base_label: `AI ${pid}`,
        targets: [{ kind: "player", id: pid }],
      }),
    ),
    events: [],
  };
}

/** An optional trigger: yes or no. */
export function mayAbility(): Scenario {
  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({ kind: "may", prompt: "Draw a card unless that player pays {1}?" }),
  });

  return {
    state,
    actions: [
      action({ id: "a0-choose", kind: "choose", label: "Yes", base_label: "Yes" }),
      action({ id: "a1-choose", kind: "choose", label: "No", base_label: "No" }),
    ],
    events: [],
  };
}

/**
 * Searching a library.
 *
 * The options carry faces the player view cannot supply -- a library is a count
 * -- which is exactly what `DecisionOption.card` exists for.
 */
export function searchLibrary(): Scenario {
  const found = [
    pool.forest({ oid: 981, zone: "library" }),
    pool.island({ oid: 982, zone: "library" }),
    pool.breedingPool({ oid: 983, zone: "library" }),
  ];

  const state = gameView({
    players: [you({ hand: [] })],
    pending: pending({
      kind: "choose_objects",
      prompt: "Search your library for a basic land card",
      options: found.map((c) => ({
        label: c.name,
        ref: { kind: "object", id: c.oid },
        value: c.oid,
        card: c,
      })),
    }),
  });

  return {
    state,
    actions: found
      .map((c, i) =>
        action({
          id: `a${i}-choose`,
          kind: "choose",
          label: c.name,
          base_label: c.name,
          // `choice` is the index into `pending.options`, and it is what makes the
          // attached face reachable: the dialog looks the option up by it, then
          // falls back to `findCard`, which cannot resolve a library card because
          // the player view sends libraries as a count. Without this the prompt
          // renders exactly the row of bare names `option.card` was added to fix.
          choice: i,
          targets: [{ kind: "object", id: c.oid }],
        }),
      )
      .concat(
        // "Search for up to one": finding nothing is a legal answer, and it is
        // the button that used to be drawn as a card-height grid cell.
        action({ id: "a3-finish_declaration", kind: "finish_declaration", label: "Done" }),
      ),
    events: [],
  };
}

/**
 * One card, several ways to aim it.
 *
 * The engine emits one action per legal target tuple, so six ways to point a
 * Simic Charm arrive as six actions with one `base_label`. Grouping them into a
 * single row with a chip per target is what stops the panel reading as six
 * copies of the same card.
 */
export function targetVariants(): Scenario {
  const battlefield = [
    pool.grizzlyBears({ oid: 991 }),
    pool.krakenToken({ oid: 992 }),
    pool.wallOfRoots({ oid: 993 }),
  ];
  const charm = pool.simicCharm({ oid: 990, zone: "hand" });

  const state = gameView({
    players: [you({ hand: [charm] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return {
    state,
    actions: [
      pass,
      ...battlefield.map((c) =>
        action({
          id: `a-charm-${c.oid}`,
          kind: "cast",
          label: `Cast Simic Charm -> ${c.name}`,
          base_label: "Cast Simic Charm",
          source_oid: 990,
          targets: [{ kind: "object", id: c.oid }],
        }),
      ),
    ],
    events: [],
  };
}

/**
 * A Treasure: one ability whose five actions differ only by the colour made.
 *
 * Pressing it asks which colour on the board (`AbilityMenu`), the way a
 * planeswalker asks which loyalty ability, rather than lighting five chips in
 * the panel.
 */
export function treasureColours(): Scenario {
  const battlefield = [pool.treasure({ oid: 451 }), pool.forest({ oid: 452 })];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  const base = "Treasure: {T}, Sacrifice this artifact: Add one mana of any color.";
  return {
    state,
    actions: [
      pass,
      ...["W", "U", "B", "R", "G"].map((colour, i) =>
        action({
          id: `a${i}-activate`,
          kind: "activate",
          label: `${base} ({${colour}})`,
          base_label: base,
          option_label: `{${colour}}`,
          source_oid: 451,
          ability_index: 0,
        }),
      ),
    ],
    events: [],
  };
}

/**
 * A permanent offering two abilities, neither of them targeted.
 *
 * The counterpart to `targetVariants`: there the ambiguity is *which target*,
 * here it is *which ability*, and the board has nothing to point at either way.
 * Clicking the artifact must therefore reach the panel rather than resolving to
 * an action -- one of these two sacrifices it.
 */
export function twoAbilityPermanent(): Scenario {
  const battlefield = [
    pool.mindStone({ oid: 401 }),
    pool.forest({ oid: 402 }),
    pool.island({ oid: 403 }),
  ];

  const state = gameView({
    players: [you({ hand: [] }, battlefield), opponent(1, "AI 1")],
    battlefield,
  });

  return {
    state,
    actions: [
      pass,
      action({
        id: "a1-activate",
        kind: "activate",
        label: "Mind Stone: {T}: Add {C}",
        base_label: "Mind Stone: {T}: Add {C}",
        source_oid: 401,
        ability_index: 0,
      }),
      action({
        id: "a2-activate",
        kind: "activate",
        label: "Mind Stone: {1}, {T}, Sacrifice this artifact: Draw a card.",
        base_label: "Mind Stone: {1}, {T}, Sacrifice this artifact: Draw a card.",
        source_oid: 401,
        ability_index: 1,
      }),
    ],
    events: [],
  };
}
