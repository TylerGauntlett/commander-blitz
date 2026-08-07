/**
 * Server state.
 *
 * The engine is authoritative, so there is no optimistic update anywhere: every
 * mutation returns the new state and we simply replace what we hold. Polling is
 * on mutation only -- a local single-user app has no other writer.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { GameEvent, GameView, LegalAction, SeatConfig } from "../api/types";
import { useUiStore } from "./uiStore";

export interface GameSession {
  gameId: string;
  seat: number;
}

export function useDecks() {
  return useQuery({
    queryKey: ["decks"],
    queryFn: api.decks,
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function useGame(session: GameSession | null) {
  const queryClient = useQueryClient();
  const setError = useUiStore((s) => s.setError);
  const clearStaging = useUiStore((s) => s.clearStaging);
  const [log, setLog] = useState<GameEvent[]>([]);

  const query = useQuery({
    queryKey: ["game", session?.gameId, session?.seat],
    queryFn: async () => {
      if (!session) throw new Error("no game");
      const response = await api.state(session.gameId, session.seat, 0);
      setLog(response.events);
      return response;
    },
    enabled: session !== null,
  });

  const absorb = useCallback(
    (response: { state: GameView; actions: LegalAction[]; events: GameEvent[] }) => {
      if (!session) return;
      queryClient.setQueryData(["game", session.gameId, session.seat], response);
      setLog((previous) => [...previous, ...response.events]);
      clearStaging();
      setError(null);
    },
    [session, queryClient, clearStaging, setError],
  );

  const act = useMutation({
    mutationFn: async (actionId: string) => {
      if (!session) throw new Error("no game");
      return api.applyAction(session.gameId, session.seat, actionId);
    },
    onSuccess: absorb,
    onError: (error: Error) => setError(error.message),
  });

  const declare = useMutation({
    mutationFn: async (input: {
      kind: "attackers" | "blockers";
      pairs: [number, number][];
    }) => {
      if (!session) throw new Error("no game");
      return api.declare(session.gameId, session.seat, input.kind, input.pairs);
    },
    onSuccess: absorb,
    onError: (error: Error) => setError(error.message),
  });

  const undo = useMutation({
    mutationFn: async () => {
      if (!session) throw new Error("no game");
      return api.undo(session.gameId, session.seat);
    },
    onSuccess: (response) => {
      if (!session) return;
      queryClient.setQueryData(["game", session.gameId, session.seat], response);
      setLog(response.events);
      clearStaging();
      setError(null);
    },
    onError: (error: Error) => setError(error.message),
  });

  return {
    state: query.data?.state ?? null,
    actions: query.data?.actions ?? [],
    events: log,
    isLoading: query.isLoading,
    error: query.error as Error | null,
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
