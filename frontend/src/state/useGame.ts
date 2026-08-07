/**
 * Server state.
 *
 * The engine is authoritative, so there is no optimistic update anywhere: every
 * mutation returns the new state and we simply replace what we hold.
 *
 * The one piece of real machinery is the AI pump. Every mutation is sent with
 * `ai_steps=1`, so the server hands control back after a single opponent
 * decision instead of playing all their turns and returning the finished
 * position. When a response comes back with no legal actions and the game is
 * not over, the opponents still owe decisions: we wait for the narration queue
 * to drain, then pump once more. That loop is what turns "the board suddenly
 * looks different" into "I watched them do it".
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
  seat: number;
}

/** Give up pumping after this many consecutive no-progress advances. */
const STALL_LIMIT = 24;

/** Breathing room between AI decisions, on top of the narration hold. */
const PUMP_DELAY_MS = 60;

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
      narration.push(beatsFor(response.events, playerNames(response.state), lookup));
      clearStaging();
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
      return api.applyAction(session.gameId, session.seat, actionId, 1);
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
      return api.declare(session.gameId, session.seat, input.kind, input.pairs, 1);
    },
    onSuccess: humanAbsorb,
    onError: (error: Error) => setError(error.message),
  });

  const undo = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("no game");
      return api.undo(session.gameId, session.seat);
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

  const pump = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("no game");
      return api.advance(session.gameId, session.seat, 1);
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

  /**
   * True when the opponents still owe decisions: no actions for us, the game is
   * live, and somebody is on the clock.
   */
  const aiThinking =
    state !== null &&
    !state.game_over &&
    state.pending !== null &&
    state.pending.player !== state.seat &&
    actions.length === 0;

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

  return {
    state,
    actions,
    events: log,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    /** Somebody else is deciding and we are watching it play out. */
    aiThinking,
    /** The pump gave up: the game is not progressing. */
    stalled,
    /** Any request in flight. */
    busy,
    narration,
    cardName: lookup,
    act,
    declare,
    undo,
  };
}

export function useNewGame() {
  return useMutation({
    mutationFn: (input: { seats: SeatConfig[]; seed?: number }) =>
      api.newGame(input.seats, input.seed),
  });
}
