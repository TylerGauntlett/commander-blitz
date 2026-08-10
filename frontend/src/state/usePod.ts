/**
 * Pod state: the lobby's half of the server.
 *
 * One idea, and it is the reason this file exists separately from `useGame`:
 * **the pod refetches because somebody else moved, not because we did.** In
 * single-player nothing could change that this client did not cause, so
 * `useGame` refetches in its own mutation handlers and nowhere else. A lobby
 * breaks that the moment a second person picks a deck.
 *
 * So `usePod` is a **self-rescheduling long poll**: it asks for the pod with the
 * version it last saw, the server blocks until that number moves or ~25 s
 * elapse, and the moment the answer lands it asks again. A timed-out poll is a
 * 200 with the same version, which is indistinguishable from a slow one and
 * costs one round trip -- see `docs/adr/0007-versioned-long-polling.md`.
 *
 * The token lives in `sessionStorage`, keyed by pod code. Session rather than
 * local, deliberately: two tabs on one machine are then two different players,
 * which is exactly how this gets tested by hand.
 *
 * That storage is also what makes `/pods/CODE` work as an address: the URL says
 * which pod, the token says whether this tab is in it. See `usePodSession`,
 * which derives one from the other.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, setPlayerToken } from "../api/client";
import type { PodView, SeatAdminAction } from "../api/types";

/** How long a single poll may block server-side. Matches the server's ceiling. */
const POLL_SECONDS = 25;

/**
 * How long to wait before re-polling after a *failed* poll.
 *
 * A successful poll re-issues immediately; a failure means the server is down
 * or restarting, and hammering it would turn a blip into a stampede.
 */
const RETRY_MS = 2000;

const TOKEN_PREFIX = "automtg.pod.";

function tokenKey(code: string): string {
  return `${TOKEN_PREFIX}${code.toUpperCase()}`;
}

export function storedToken(code: string): string | null {
  try {
    return window.sessionStorage.getItem(tokenKey(code));
  } catch {
    // Private browsing with storage disabled. The pod still works for the life
    // of the tab; only reconnecting after a reload is lost.
    return null;
  }
}

export function storeToken(code: string, token: string | null): void {
  try {
    if (token === null) window.sessionStorage.removeItem(tokenKey(code));
    else window.sessionStorage.setItem(tokenKey(code), token);
  } catch {
    /* see storedToken */
  }
}

export interface PodSession {
  code: string;
  token: string;
}

/**
 * Adopt a pod: remember its token and make every subsequent request carry it.
 *
 * Called on create, on join, and on boot when a stored token is found. The
 * client module holds one token at a time because a browser tab is one player.
 */
export function adoptPod(code: string, token: string): PodSession {
  storeToken(code, token);
  setPlayerToken(token);
  return { code, token };
}

export function forgetPod(code: string): void {
  storeToken(code, null);
  setPlayerToken(null);
}

/**
 * The pod, kept live by long-polling.
 *
 * `version` is held in a ref rather than in state: it changes on every poll and
 * putting it in state would re-render the whole lobby to store a number nothing
 * renders.
 */
export function usePod(session: PodSession | null) {
  const queryClient = useQueryClient();
  const code = session?.code ?? null;
  const version = useRef(0);
  const [pod, setPod] = useState<PodView | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // A different code is a different pod. Reset before polling rather than
    // showing the last one's seats for a frame while the first fetch is in
    // flight. In the same effect as the poll, because the two have to happen in
    // that order and a second effect existing only to run first is a rule
    // nothing enforces.
    version.current = 0;
    setPod(null);
    setError(null);
    if (!code) return;

    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      while (live) {
        try {
          const next = await api.pod(code, version.current, POLL_SECONDS);
          if (!live) return;
          version.current = next.version;
          setPod(next);
          setError(null);
          // A closed or dealt pod has nothing further to say. Stopping here is
          // what keeps a finished lobby from holding a server thread for the
          // rest of the session.
          if (next.status === "in_game" || next.status === "closed") return;
        } catch (caught) {
          if (!live) return;
          setError(caught as Error);
          await new Promise((resolve) => {
            timer = setTimeout(resolve, RETRY_MS);
          });
        }
      }
    };

    void poll();
    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [code]);

  /** Every mutation returns the fresh view, so there is no optimistic update. */
  const absorb = useCallback(
    (next: PodView) => {
      version.current = next.version;
      setPod(next);
      setError(null);
      queryClient.setQueryData(["pod", next.code], next);
    },
    [queryClient],
  );

  const updateSeat = useMutation({
    mutationFn: (body: { deck_id?: string; locked?: boolean; name?: string }) => {
      if (!code) throw new Error("no pod");
      return api.updateSeat(code, body);
    },
    onSuccess: absorb,
    onError: (caught: Error) => setError(caught),
  });

  const adminSeat = useMutation({
    mutationFn: (input: {
      index: number;
      action: SeatAdminAction;
      deck_id?: string;
      agent?: string;
    }) => {
      if (!code) throw new Error("no pod");
      const { index, ...body } = input;
      return api.adminSeat(code, index, body);
    },
    onSuccess: absorb,
    onError: (caught: Error) => setError(caught),
  });

  const start = useMutation({
    mutationFn: (seed?: number) => {
      if (!code) throw new Error("no pod");
      return api.startPod(code, seed);
    },
    onSuccess: absorb,
    onError: (caught: Error) => setError(caught),
  });

  const leave = useMutation({
    mutationFn: async () => {
      if (!code) throw new Error("no pod");
      await api.leavePod(code);
      forgetPod(code);
    },
    onError: (caught: Error) => setError(caught),
  });

  return {
    pod,
    error,
    /** Any pod mutation in flight. */
    busy: updateSeat.isPending || adminSeat.isPending || start.isPending || leave.isPending,
    updateSeat,
    adminSeat,
    start,
    leave,
    clearError: () => setError(null),
  };
}

export function useCreatePod() {
  return useMutation({
    mutationFn: (input: { name?: string; deckId?: string | null; seed?: number }) =>
      api.createPod(input.name, input.deckId, input.seed),
  });
}

/**
 * Join by code, reusing a stored token when there is one.
 *
 * `adoptPod` runs *before* the request so the token rides along in the header,
 * which is what makes a rejoin idempotent rather than taking a second chair.
 */
export function useJoinPod() {
  return useMutation({
    mutationFn: async (input: { code: string; name?: string }) => {
      const existing = storedToken(input.code);
      setPlayerToken(existing);
      try {
        return await api.joinPod(input.code, input.name);
      } catch (caught) {
        // A token that does not open the pod any more is worse than no token:
        // it would keep failing every retry. Drop it and let them join fresh.
        if (caught instanceof ApiError && caught.code === "bad_token") {
          forgetPod(input.code);
        }
        throw caught;
      }
    },
  });
}

/** One deck with the dossier's fields. Cached forever: it never changes. */
export function useDeckDetail(deckId: string | null) {
  return useQuery({
    queryKey: ["deck", deckId],
    queryFn: () => api.deck(deckId as string),
    enabled: deckId !== null,
    staleTime: Number.POSITIVE_INFINITY,
  });
}
