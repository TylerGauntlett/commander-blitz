/**
 * Server state.
 *
 * The engine is authoritative, so there is no optimistic update anywhere: every
 * mutation returns the new state and we simply replace what we hold.
 *
 * There are two pieces of real machinery, and which one runs depends on *who*
 * we are waiting for.
 *
 * **An AI seat: the pump.** Every mutation is sent with `ai_steps=1`, so the
 * server hands control back after a single opponent decision instead of playing
 * all their turns and returning the finished position. When a response comes
 * back with no legal actions and the game is not over, the opponents still owe
 * decisions: we wait for the narration queue to drain, then pump once more.
 * That loop is what turns "the board suddenly looks different" into "I watched
 * them do it".
 *
 * **Another human: the long poll.** There is nothing to pump -- the server is
 * not going to move that seat, a person is. So we ask for the state with the
 * version we last saw and the request blocks until it changes. Pumping here
 * would be a busy-wait against a human's thinking time.
 *
 * `human_seats` in the response is what tells the two apart. The engine does not
 * model it (a seat is a seat to it); the session does.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { GameEvent, GameView, SeatConfig, StateResponse } from "../api/types";
import { beatsFor } from "../logic/events";
import { playerNames } from "../logic/labels";
import { useNarration } from "./narration";
import { useUiStore } from "./uiStore";

export interface GameSession {
  gameId: string;
  /**
   * Null means "ask my token".
   *
   * A client arriving from a pod does not know its table seat: the lobby's four
   * chairs are compacted down to the players actually in the game, so lobby
   * seat 2 can be table seat 1. The first state response carries `your_seat`.
   */
  seat: number | null;
}

/** Give up pumping after this many consecutive no-progress advances. */
const STALL_LIMIT = 24;

/** Breathing room between AI decisions, on top of the narration hold. */
const PUMP_DELAY_MS = 60;

/**
 * How long one long poll may block, in seconds. Matches the server's ceiling.
 *
 * A poll that finds nothing comes back with a 200 and the same version, and the
 * effect below simply issues another -- so this is the *latency* of noticing a
 * server that restarted, not of noticing a move.
 */
const POLL_SECONDS = 25;

/**
 * `staleTime: Infinity` because the deck list was fixed for the life of the
 * server -- which stopped being true with deck import. It is still never
 * *stale*, though: it changes only when this client causes it to, so the import
 * invalidates the key by hand rather than every consumer polling for a change
 * that almost never happens.
 */
export function useDecks() {
  return useQuery({
    queryKey: ["decks"],
    queryFn: api.decks,
    staleTime: Number.POSITIVE_INFINITY,
  });
}

/**
 * Every card id we have seen, mapped to its printed name.
 *
 * Events carry the snake_case definition id, not the name, so without this the
 * play-by-play would read "sol_ring". Any card that has been in a visible zone
 * is enough to resolve it.
 */
function harvestNames(state: GameView, into: Map<string, string>): void {
  const add = (cardId: string, name: string) => {
    if (!into.has(cardId)) into.set(cardId, name);
  };
  for (const card of state.battlefield) add(card.card_id, card.name);
  for (const item of state.stack) add(item.def_id, item.name);
  for (const player of state.players) {
    for (const card of player.hand ?? []) add(card.card_id, card.name);
    for (const card of player.graveyard) add(card.card_id, card.name);
    for (const card of player.exile) add(card.card_id, card.name);
    for (const card of player.command) add(card.card_id, card.name);
  }
}

/**
 * The seat to act as.
 *
 * `POST` bodies carry an explicit seat, so a session that has not yet learned
 * its own falls back to 0 -- which is right for every single-player caller and
 * is corrected the moment the first state response lands.
 */
function seatOf(session: GameSession): number {
  return session.seat ?? 0;
}

export function useGame(session: GameSession | null) {
  const queryClient = useQueryClient();
  const setError = useUiStore((s) => s.setError);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const speed = useUiStore((s) => s.speed);

  const narration = useNarration(speed);
  const [log, setLog] = useState<GameEvent[]>([]);
  const names = useRef(new Map<string, string>());
  const stalls = useRef(0);
  const [stalled, setStalled] = useState(false);

  // Memoised so the callbacks below keep a stable identity: rebuilding them
  // every render would restart the pump effect on every render too.
  const key = useMemo(
    () => ["game", session?.gameId, session?.seat],
    [session?.gameId, session?.seat],
  );

  const query = useQuery({
    queryKey: key,
    queryFn: async () => {
      if (!session) throw new Error("no game");
      const response = await api.state(session.gameId, session.seat, 0);
      // The opening events (shuffle, opening hands) are history, not drama:
      // seed the log but do not narrate them.
      harvestNames(response.state, names.current);
      setLog(response.events);
      return response;
    },
    enabled: session !== null,
  });

  const lookup = useCallback((cardId: string) => names.current.get(cardId), []);

  const absorb = useCallback(
    (response: StateResponse) => {
      if (!session) return;
      harvestNames(response.state, names.current);
      queryClient.setQueryData(key, response);
      setLog((previous) => [...previous, ...response.events]);
      narration.push(
        beatsFor(response.events, playerNames(response.state), lookup, response.your_seat),
      );
      // Keep a half-built declaration alive across responses that are not the
      // declaration itself -- the AI pump lands here too, and wiping the staged
      // set mid-choice loses work the player has not committed yet.
      const pending = response.state.pending;
      const stillDeclaring =
        pending !== null &&
        pending.player === response.your_seat &&
        (pending.kind === "declare_attackers" || pending.kind === "declare_blockers");
      if (!stillDeclaring) clearStaging();
      setError(null);
    },
    [session, key, queryClient, clearStaging, setError, narration.push, lookup],
  );

  /** A player-driven action always resets the stall guard. */
  const humanAbsorb = useCallback(
    (response: StateResponse) => {
      stalls.current = 0;
      setStalled(false);
      absorb(response);
    },
    [absorb],
  );

  const act = useMutation({
    mutationFn: async (actionId: string) => {
      if (!session) throw new Error("no game");
      return api.applyAction(session.gameId, seatOf(session), actionId, 1);
    },
    onSuccess: humanAbsorb,
    onError: (error: Error) => setError(error.message),
  });

  const declare = useMutation({
    mutationFn: async (input: {
      kind: "attackers" | "blockers";
      pairs: [number, number][];
    }) => {
      if (!session) throw new Error("no game");
      return api.declare(session.gameId, seatOf(session), input.kind, input.pairs, 1);
    },
    onSuccess: humanAbsorb,
    onError: (error: Error) => setError(error.message),
  });

  const undo = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("no game");
      return api.undo(session.gameId, seatOf(session));
    },
    onSuccess: (response) => {
      if (!session) return;
      // Undo rewinds by replaying the tape, so the events it returns are the
      // whole game again. Replace the log; never narrate a rewind.
      narration.reset();
      harvestNames(response.state, names.current);
      queryClient.setQueryData(key, response);
      setLog(response.events);
      stalls.current = 0;
      setStalled(false);
      clearStaging();
      setError(null);
    },
    onError: (error: Error) => setError(error.message),
  });

  /**
   * Ask the engine to stop at every priority window, or only meaningful ones.
   *
   * Not narrated: it changes nothing about the game, only which windows the
   * engine offers, and turning it on can immediately reveal a window that was
   * about to be auto-passed.
   */
  const setFullControl = useMutation({
    mutationFn: async (value: boolean) => {
      if (!session) throw new Error("no game");
      return api.setFullControl(session.gameId, seatOf(session), value);
    },
    onSuccess: (response) => {
      if (!session) return;
      harvestNames(response.state, names.current);
      queryClient.setQueryData(key, response);
      setError(null);
    },
    onError: (error: Error) => setError(error.message),
  });

  /**
   * Tap your own lands, or hand it back to the solver.
   *
   * Not narrated, for the same reason as `setFullControl`: it changes nothing
   * about the game, only which actions the engine offers.
   */
  const setManualMana = useMutation({
    mutationFn: async (value: boolean) => {
      if (!session) throw new Error("no game");
      const current = queryClient.getQueryData<StateResponse>(key);
      return api.setManualMana(
        session.gameId,
        seatOf(session),
        current?.state.full_control ?? false,
        value,
      );
    },
    onSuccess: (response) => {
      if (!session) return;
      harvestNames(response.state, names.current);
      queryClient.setQueryData(key, response);
      setError(null);
    },
    onError: (error: Error) => setError(error.message),
  });

  const pump = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("no game");
      return api.advance(session.gameId, seatOf(session), 1);
    },
    onSuccess: (response) => {
      // No events and still nothing for the human to do means the engine did
      // not move. Count it; a handful in a row is a stuck game, not a slow one.
      if (response.events.length === 0) {
        stalls.current += 1;
        if (stalls.current >= STALL_LIMIT) setStalled(true);
      } else {
        stalls.current = 0;
      }
      absorb(response);
    },
    onError: (error: Error) => {
      setStalled(true);
      setError(error.message);
    },
  });

  const data = query.data ?? null;
  const state = data?.state ?? null;
  const actions = useMemo(() => data?.actions ?? [], [data]);
  /** Resolved by the server from our token when the session did not know it. */
  const yourSeat = data?.your_seat ?? session?.seat ?? null;
  const humanSeats = useMemo(() => data?.human_seats ?? [], [data]);

  /** Whoever is on the clock, when it is not us and there is nothing to do. */
  const waitingOn =
    state !== null &&
    !state.game_over &&
    state.pending !== null &&
    yourSeat !== null &&
    state.pending.player !== yourSeat &&
    actions.length === 0
      ? state.pending.player
      : null;

  /** An AI seat: pump it forward a decision at a time so its turn is watchable. */
  const aiThinking = waitingOn !== null && !humanSeats.includes(waitingOn);

  /** Another person: there is nothing to pump. Block until they move. */
  const waitingForPlayer = waitingOn !== null && humanSeats.includes(waitingOn);

  const busy = act.isPending || declare.isPending || undo.isPending || pump.isPending;

  // The pump. Deliberately waits for the narration queue so the animation of
  // the last decision finishes before the next one is requested.
  const pumpMutate = pump.mutate;
  useEffect(() => {
    if (!session || !aiThinking || stalled) return;
    if (busy || narration.busy) return;
    const timer = setTimeout(() => pumpMutate(), PUMP_DELAY_MS);
    return () => clearTimeout(timer);
  }, [session, aiThinking, stalled, busy, narration.busy, pumpMutate]);

  // The long poll. One request in flight at a time, re-issued the moment it
  // lands -- a timed-out poll is a 200 with the same version, which is
  // indistinguishable from a slow one.
  const version = data?.version ?? 0;
  useEffect(() => {
    if (!session || !waitingForPlayer || yourSeat === null) return;
    if (busy || narration.busy) return;
    let live = true;
    void (async () => {
      try {
        const response = await api.state(
          session.gameId,
          yourSeat,
          // The events we already hold; the server sends only what is new.
          undefined,
          version,
          POLL_SECONDS,
        );
        if (live && response.version > version) absorb(response);
      } catch (caught) {
        if (live) setError((caught as Error).message);
      }
    })();
    return () => {
      live = false;
    };
  }, [session, waitingForPlayer, yourSeat, version, busy, narration.busy, absorb, setError]);

  return {
    state,
    actions,
    events: log,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    /** The seat this client is playing, once the server has told us. */
    yourSeat,
    /**
     * Which seats are people rather than agents.
     *
     * The engine does not model it and `GameView` does not carry it -- it rides
     * on the state RESPONSE beside the view. Exposed because the rematch has to
     * rebuild the lineup, and "which of these four is a person" is the one fact
     * about a seat that the board itself cannot answer.
     */
    humanSeats,
    /** An AI is deciding and we are watching it play out. */
    aiThinking,
    /** Another person is deciding. Nothing to animate; we are simply waiting. */
    waitingForPlayer,
    /** The pump gave up: the game is not progressing. */
    stalled,
    /** Any request in flight. */
    busy,
    narration,
    cardName: lookup,
    act,
    declare,
    undo,
    setFullControl,
    setManualMana,
  };
}

export function useNewGame() {
  return useMutation({
    mutationFn: (input: { seats: SeatConfig[]; seed?: number }) =>
      api.newGame(input.seats, input.seed),
  });
}
