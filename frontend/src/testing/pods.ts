/**
 * Pods, at each stage of filling up.
 *
 * The lobby's whole subject is partial information -- who has arrived, who has
 * locked in, and what you are allowed to see about them -- so the states worth
 * posing are the incomplete ones. A pod with four locked seats is the least
 * interesting screen in the app.
 */

import type { PodView } from "../api/types";
import { deckSummary, podView } from "./fixtures";

const aesi = deckSummary();
const edgar = deckSummary({
  id: "edgar",
  name: "Edgar Markov",
  commanders: ["edgar_markov"],
  commander_names: ["Edgar Markov"],
  color_identity: ["B", "R", "W"],
  notes: "Vampire aristocrats.",
  tags: ["Aggro", "Tokens"],
});

export const DECKS = [
  aesi,
  edgar,
  deckSummary({
    id: "atraxa",
    name: "Atraxa, Praetors' Voice",
    commanders: ["atraxa_praetors_voice"],
    commander_names: ["Atraxa, Praetors' Voice"],
    color_identity: ["W", "U", "B", "G"],
    notes: "Counters, everywhere.",
    tags: ["Counters", "Midrange"],
  }),
  deckSummary({
    id: "mine",
    name: "Zada Storm",
    source: "moxfield",
    commanders: ["zada_hedron_grinder"],
    commander_names: ["Zada, Hedron Grinder"],
    color_identity: ["R"],
    notes: "",
    tags: [],
    playable: 88,
    simplified: 12,
  }),
];

/** You have just made a pod: your chair, and three empty ones. */
export function empty(): PodView {
  return podView([{ kind: "human", name: "You", is_you: true, is_host: true, deck: aesi }]);
}

/**
 * The very first frame of a pod: your chair with nothing in it yet.
 *
 * Distinct from `empty()`, which hands you a deck already -- convenient for
 * every story about the OTHER three chairs, and useless for the one question
 * only this state can ask: what your own chair says before you have chosen. It
 * says CHOOSE. It used to say SEALED, which is what everybody else's unchosen
 * chair says, so your own deck looked like it was being kept from you.
 */
export function fresh(): PodView {
  return podView([{ kind: "human", name: "You", is_you: true, is_host: true, deck: null }]);
}

/**
 * Filling up: you, a guest who has locked in, a CPU, and one chair still open.
 *
 * The guest's deck is `null` on purpose -- the lobby's hidden-information rule
 * is that another player's deck stays invisible until they lock in, and a
 * face-down card is one picture for three different facts.
 */
export function filling(): PodView {
  return podView([
    { kind: "human", name: "You", is_you: true, is_host: true, deck: aesi, locked: true },
    { kind: "human", name: "Sam", deck: null },
    { kind: "cpu", name: "CPU", deck: edgar, agent: "heuristic", locked: true, ready: true },
    { kind: "open" },
  ]);
}

/** Everybody locked in: the deal button is live. */
export function ready(): PodView {
  return podView([
    {
      kind: "human",
      name: "You",
      is_you: true,
      is_host: true,
      deck: aesi,
      locked: true,
      ready: true,
    },
    { kind: "human", name: "Sam", deck: edgar, locked: true, ready: true },
    {
      kind: "cpu",
      name: "CPU 1",
      deck: DECKS[2],
      agent: "heuristic",
      locked: true,
      ready: true,
    },
    { kind: "cpu", name: "CPU 2", deck: DECKS[3], agent: "random", locked: true, ready: true },
  ]);
}

/**
 * The same pod seen by a guest.
 *
 * Host-only controls are hidden rather than disabled, so this is a genuinely
 * different screen and not a greyed-out one.
 */
export function guestView(): PodView {
  return podView(
    [
      { kind: "human", name: "Ana", is_host: true, deck: aesi, locked: true },
      { kind: "human", name: "You", is_you: true, deck: edgar },
      {
        kind: "cpu",
        name: "CPU",
        deck: DECKS[2],
        agent: "heuristic",
        locked: true,
        ready: true,
      },
      { kind: "open" },
    ],
    { you_are_host: false },
  );
}

/** The host has dealt: everyone is about to be sent to the table. */
export function starting(): PodView {
  return podView(
    [
      { kind: "human", name: "You", is_you: true, is_host: true, deck: aesi, locked: true },
      { kind: "human", name: "Sam", deck: edgar, locked: true, ready: true },
    ],
    { status: "starting" },
  );
}

/** A three-player pod, which is why the ready track counts filled seats. */
export function threeHanded(): PodView {
  return podView([
    { kind: "human", name: "You", is_you: true, is_host: true, deck: aesi, locked: true },
    { kind: "human", name: "Sam", deck: null },
    { kind: "cpu", name: "CPU", deck: edgar, agent: "heuristic", locked: true, ready: true },
  ]);
}
