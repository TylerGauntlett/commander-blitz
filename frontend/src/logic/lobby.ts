/**
 * The lobby's decisions, as pure functions.
 *
 * Lifted out of the components so they can be tested without a DOM, and because
 * "why is the Deal button off" is one question with one answer -- if the button
 * and the explanatory line derived it separately they would eventually disagree,
 * and the disagreement would be silent.
 *
 * The server re-checks every one of these under its pod lock. These exist to
 * make the screen *say* what will happen, not to decide it: a client that got
 * `canStart` wrong renders a live button and gets a 409, which is annoying but
 * not wrong.
 */

import type { DeckSummary, PodSeatView, PodView } from "../api/types";

/* ------------------------------------------------------------------ */
/* Seats                                                               */
/* ------------------------------------------------------------------ */

/** Would the game be waiting on this seat? Mirrors `PodSeat.ready`. */
export function seatReady(seat: PodSeatView): boolean {
  return seat.ready;
}

/** Seats that would become players. An open chair is not one -- yet. */
export function filledSeats(pod: PodView): PodSeatView[] {
  return pod.seats.filter((seat) => seat.kind === "cpu" || seat.kind === "human");
}

export function podSize(pod: PodView): number {
  return filledSeats(pod).length;
}

export function openSeats(pod: PodView): number {
  return pod.seats.filter((seat) => seat.kind === "open").length;
}

export function allReady(pod: PodView): boolean {
  const filled = filledSeats(pod);
  return filled.length > 0 && filled.every(seatReady);
}

/** The viewer's own chair, or null when they are only watching. */
export function yourSeat(pod: PodView): PodSeatView | null {
  return pod.seats.find((seat) => seat.is_you) ?? null;
}

/**
 * The first chair the host could put something in.
 *
 * Never seat 0: that is the host's own, and a host who cleared their own chair
 * would have no way back into their pod.
 */
export function firstEmpty(pod: PodView): number {
  const found = pod.seats.findIndex((seat, index) => index > 0 && seat.kind === "empty");
  return found;
}

/**
 * CPUs are numbered by their position among the CPU seats, not by seat index:
 * the second CPU in a pod whose seat 2 is a human is still "CPU 2".
 */
export function cpuNumber(pod: PodView, index: number): number {
  return pod.seats.slice(0, index + 1).filter((seat) => seat.kind === "cpu").length;
}

export interface SeatLabel {
  title: string;
  sub: string;
}

export function seatLabel(pod: PodView, index: number): SeatLabel {
  const seat = pod.seats[index];
  if (!seat) return { title: "Seat", sub: "" };
  if (seat.kind === "empty") return { title: "No one yet", sub: "A pod seats four" };
  if (seat.kind === "open") return { title: "Open chair", sub: "Waiting for a player" };
  if (seat.kind === "cpu") {
    // A CPU is ready by construction, which is the only thing true about it that
    // is not its deck.
    return { title: seat.name ?? `CPU ${cpuNumber(pod, index)}`, sub: "Ready" };
  }
  const who = seat.is_you ? "You" : (seat.name ?? "Player");
  if (seat.locked) return { title: who, sub: "Locked in" };
  return { title: who, sub: seat.deck ? "Choosing" : "Choosing a deck…" };
}

/* ------------------------------------------------------------------ */
/* Dealing                                                             */
/* ------------------------------------------------------------------ */

/**
 * Can the host deal?
 *
 * Deliberately *not* "is every chair full". Open chairs become CPUs on the
 * server when the pod deals, so waiting for somebody who never arrives is a
 * choice the host makes, not a state the lobby traps them in.
 */
export function canStart(pod: PodView): boolean {
  if (pod.status !== "open") return false;
  if (!pod.you_are_host) return false;
  const you = yourSeat(pod);
  if (!you || !you.locked) return false;
  // Open chairs fill with CPUs, so they count towards the two-player minimum.
  if (podSize(pod) + openSeats(pod) < 2) return false;
  return allReady(pod);
}

/**
 * One sentence saying what the pod is waiting for.
 *
 * The same order the server checks in, so the line and the 409 can never
 * contradict each other. Returned for everybody, not only the host -- a guest
 * staring at a screen with nothing happening deserves to know it is waiting on
 * Marco and not on them.
 */
export function whyNot(pod: PodView): string {
  if (pod.status === "closed") return "Everybody left. This pod is closed.";
  if (pod.status === "in_game") return "Dealt. Taking you to the table…";

  const you = yourSeat(pod);
  if (!you) return "You are watching this pod, not sitting in it.";
  if (!you.deck) return "Pick a deck to turn your card over.";
  if (podSize(pod) + openSeats(pod) < 2) {
    return "A pod needs at least one opponent. Add a CPU or invite somebody.";
  }
  if (!you.locked) return "Your card is face up but not stamped.";

  const waiting = pod.seats
    .filter((seat) => seat.kind === "human" && !seat.ready)
    .map((seat) => seat.name ?? "somebody");
  if (waiting.length === 1) return `Waiting on ${waiting[0]}.`;
  if (waiting.length > 1) {
    return `Waiting on ${waiting.slice(0, -1).join(", ")} and ${waiting[waiting.length - 1]}.`;
  }

  const open = openSeats(pod);
  if (open > 0) {
    return `${open} chair${open > 1 ? "s" : ""} still open — a CPU will fill ${
      open > 1 ? "them" : "it"
    }.`;
  }
  if (!pod.you_are_host) return "Everybody is ready. Waiting on the host to deal.";
  return `${podSize(pod)} cards up. Deal them.`;
}

/** Four segments, one per chair, for the ready track. */
export type TrackSegment = "on" | "wait" | "none";

export function readyTrack(pod: PodView): TrackSegment[] {
  return pod.seats.map((seat) => {
    if (seat.kind === "empty") return "none";
    if (seat.ready) return "on";
    return "wait";
  });
}

/* ------------------------------------------------------------------ */
/* The catalogue                                                       */
/* ------------------------------------------------------------------ */

export type DeckSort = "name" | "speed" | "complexity" | "pilot";
export type DeckSource = "all" | "precon" | "moxfield";

export interface CatalogFilters {
  q: string;
  /** Colour identity, as an AND: three colours means decks that play all three. */
  colours: string[];
  source: DeckSource;
  sort: DeckSort;
}

export const EMPTY_FILTERS: CatalogFilters = {
  q: "",
  colours: [],
  source: "all",
  sort: "name",
};

/**
 * Sorts that read a rating.
 *
 * `pilot` inverts: the axis is "demands on you", so "easiest to pilot" is the
 * *lowest* number, and a deck with no ratings at all sorts to the end rather
 * than pretending to be a 0.
 */
const RATING_SORTS: Record<string, { key: "speed" | "complexity" | "pilot"; invert: boolean }> =
  {
    speed: { key: "speed", invert: false },
    complexity: { key: "complexity", invert: false },
    pilot: { key: "pilot", invert: true },
  };

/** Ratings for one deck, or nothing if this screen has not fetched them. */
export type RatingLookup = (deckId: string) => Record<string, number> | null | undefined;

/**
 * The catalogue's rack: filter, then sort.
 *
 * `ratingOf` is optional because `GET /api/decks` deliberately does not carry
 * ratings -- the rack draws two dozen tiles and would otherwise pay for two
 * dozen strategy essays. Without it a rating sort falls back to name, which is
 * a real answer rather than an arbitrary order.
 */
export function visibleDecks(
  decks: DeckSummary[],
  filters: CatalogFilters,
  ratingOf?: RatingLookup,
): DeckSummary[] {
  const q = filters.q.trim().toLowerCase();
  const matched = decks.filter((deck) => {
    if (filters.source !== "all" && deck.source !== filters.source) return false;
    if (
      filters.colours.length > 0 &&
      !filters.colours.every((colour) => deck.color_identity.includes(colour))
    ) {
      return false;
    }
    if (!q) return true;
    const haystack = [deck.name, ...deck.commander_names, ...deck.tags, deck.notes]
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });

  const rating = RATING_SORTS[filters.sort];
  const byName = (a: DeckSummary, b: DeckSummary) => a.name.localeCompare(b.name);
  if (!rating || !ratingOf) return matched.sort(byName);

  return matched.sort((a, b) => {
    const left = ratingOf(a.id)?.[rating.key];
    const right = ratingOf(b.id)?.[rating.key];
    // A deck with no ratings sorts to the end rather than to the top: an
    // imported deck has none, and calling it the fastest deck in the catalogue
    // would be the one lie on the screen.
    if (left === undefined && right === undefined) return byName(a, b);
    if (left === undefined) return 1;
    if (right === undefined) return -1;
    const delta = rating.invert ? left - right : right - left;
    return delta || byName(a, b);
  });
}

/* ------------------------------------------------------------------ */
/* Codes                                                               */
/* ------------------------------------------------------------------ */

/**
 * The longest a player may call themselves. Mirrors `MAX_NAME_LENGTH` in
 * `server/schemas.py`, which is the one that actually refuses.
 */
export const MAX_NAME_LENGTH = 24;

/**
 * Make a code somebody typed match one the server issued.
 *
 * The server normalises too -- this is not the check, it is so the input shows
 * `GYRE-8412` while it is being typed rather than correcting itself on submit.
 */
export function normaliseCode(raw: string): string {
  const squashed = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const match = /^([A-Z]+)(\d{1,6})$/.exec(squashed);
  if (!match) return squashed;
  return `${match[1]}-${match[2]}`;
}

/** A code is worth submitting when it has a word and four digits. */
export function looksLikeCode(raw: string): boolean {
  return /^[A-Z]+-\d{4,6}$/.test(normaliseCode(raw));
}
