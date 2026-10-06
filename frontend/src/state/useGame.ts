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
 * **Another human: the listener.** There is nothing to pump -- the server is
 * not going to move that seat, a person is. So we ask for the state with the
 * version we last saw and the request blocks until it changes. It is the same
 * self-rescheduling long poll as `usePod`: a timed-out poll is a 200 with the
 * same version, and the answer to it is simply another poll. Pumping here would
 * be a busy-wait against a human's thinking time.
 *
 * The listener carries **two cursors** from the last response it absorbed. The
 * version says *when* to wake; the event cursor says *what* is new, so the
 * answer carries only the events this client has not rendered. A response is
 * self-describing -- its events end at `event_cursor` -- which is what lets
 * `absorb` trim one that overlaps something already seen, and why a pump
 * response and a poll response landing out of order cannot narrate anything
 * twice. See `docs/adr/0007-versioned-long-polling.md`.
 *
 * `human_seats` in the response is what tells the two apart. The engine does not
 * model it (a seat is a seat to it); the session does. With several people at
 * one table and an AI on the clock, exactly one of them pumps -- the lowest
 * human seat -- and the rest listen, so the AI's turn is narrated once at one
 * pace on every screen. A listener whose poll times out while the AI is still
 * on the clock takes the pump over: the elected pumper's tab has gone.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
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
 * listener simply issues another -- so this is the *latency* of noticing a
 * server that restarted, not of noticing a move.
 */
const POLL_SECONDS = 25;

/**
 * How long to wait before re-polling after a *failed* poll.
 *
 * A successful poll re-issues immediately; a failure means the server is down
 * or restarting, and hammering it would turn a blip into a stampede.
 */
const RETRY_MS = 2000;

/**
 * How often a listener holding a fresh response checks whether the last batch
 * has finished animating. The request is never re-issued to wait: a poll that
 * is torn down and re-created leaves a parked server thread behind each time.
 */
const NARRATION_TICK_MS = 100;

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

/**
 * Whoever is on the clock, when it is not us and there is nothing to do.
 *
 * A pure function of one response so the listener can decide from the answer
 * it just absorbed whether to keep listening, rather than issuing the next
 * request and waiting for React to tear it down again.
 */
export function waitingOnFrom(response: StateResponse, seat: number | null): number | null {
  const state = response.state;
  return !state.game_over &&
    state.pending !== null &&
    seat !== null &&
    state.pending.player !== seat &&
    response.actions.length === 0
    ? state.pending.player
    : null;
}

/**
 * The events in a response this client has not seen.
 *
 * A response's events end at its `event_cursor`, so they start at
 * `event_cursor - events.length`; anything before `cursor` has already been
 * logged and narrated. A response that carries nothing new -- somebody toggled
 * an option, or the pump and the poll answered the same move -- trims to
 * nothing rather than narrating the move again.
 */
export function freshEvents(response: StateResponse, cursor: number): GameEvent[] {
  const start = response.event_cursor - response.events.length;
  return response.events.slice(Math.max(0, cursor - start));
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

  /*
   * The two cursors, in refs: they change on every response and the listener
   * reads them from inside a loop that must not restart when they move.
   */
  const versionRef = useRef(0);
  const cursorRef = useRef(0);
  const remember = useCallback((response: StateResponse) => {
    versionRef.current = response.version;
    cursorRef.current = response.event_cursor;
  }, []);

  /** A listener that has stopped hearing the pumper takes the pump over. */
  const [takeover, setTakeover] = useState(false);

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
      remember(response);
      setLog(response.events);
      return response;
    },
    enabled: session !== null,
    /*
     * THE SEAT MOVING IS NOT A NEW GAME, so the board does not blank for it.
     *
     * `GameRoute` asks with a null seat first and then with the seat the first
     * response named, and each is its own key. Without this the second key
     * started with no data at all: the table, already drawn from the first
     * response, went back to "Dealing…" for a round trip. The previous
     * response stands in until the new one lands.
     *
     * ONLY FOR THE SAME GAME. A rematch navigates `/games/a` to `/games/b`
     * inside one mounted route, and the finished game's board must not be
     * drawn as if it were the new one's -- nor its seat taken for this one's.
     */
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === session?.gameId ? previous : undefined,
  });

  const lookup = useCallback((cardId: string) => names.current.get(cardId), []);

  const absorb = useCallback(
    (response: StateResponse) => {
      if (!session) return;
      // A slow POST landing after a newer poll would put an older board and an
      // older action list back in the cache. Nothing it carries is news.
      if (response.version < versionRef.current) return;
      const fresh = freshEvents(response, cursorRef.current);
      remember(response);
      harvestNames(response.state, names.current);
      queryClient.setQueryData(key, response);
      if (fresh.length > 0) setLog((previous) => [...previous, ...fresh]);
      narration.push(beatsFor(fresh, playerNames(response.state), lookup, response.your_seat));
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
    [session, key, queryClient, clearStaging, setError, narration.push, lookup, remember],
  );
  const absorbRef = useRef(absorb);
  useEffect(() => {
    absorbRef.current = absorb;
  }, [absorb]);

  /** A player-driven action always resets the stall guard. */
  const humanAbsorb = useCallback(
    (response: StateResponse) => {
      stalls.current = 0;
      setStalled(false);
      absorb(response);
    },
    [absorb],
  );

  /**
   * Fetch the current position without ceremony, and absorb it like any other.
   *
   * The answer to a stale click. From the cursor we already hold, so anything
   * that landed in the meantime is logged and narrated once, exactly as a poll
   * would have done it -- not the full reload invalidating the query would be,
   * which re-seeds the log from the whole game.
   */
  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      absorb(await api.state(session.gameId, session.seat, cursorRef.current));
    } catch (caught) {
      setError((caught as Error).message);
    }
  }, [session, absorb, setError]);

  const act = useMutation({
    mutationFn: async (actionId: string) => {
      if (!session) throw new Error("no game");
      // The version of the list the id was read from, which is the cached
      // response the board is drawing -- not `versionRef`, which a poll can
      // move ahead of what has been rendered.
      const shown = queryClient.getQueryData<StateResponse>(key)?.version;
      return api.applyAction(session.gameId, seatOf(session), actionId, 1, shown);
    },
    onSuccess: humanAbsorb,
    onError: (error: Error) => {
      /*
       * The click was read off a list the game has already replaced -- most
       * often the second half of a double click, whose first half has just
       * played the card. Nothing the player did wrong and nothing to tell
       * them: fetch the list that is current and let them choose again. An
       * error toast here read "unknown action id 'a1-play_land'".
       */
      if (error instanceof ApiError && error.status === 409 && error.code === "stale_action") {
        void refresh();
        return;
      }
      setError(error.message);
    },
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

  const choose = useMutation({
    mutationFn: async (choices: number[]) => {
      if (!session) throw new Error("no game");
      return api.choose(session.gameId, seatOf(session), choices, 1);
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
      remember(response);
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
      remember(response);
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
      remember(response);
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
  const waitingOn = data ? waitingOnFrom(data, yourSeat) : null;

  /** An AI seat is deciding. */
  const aiThinking = waitingOn !== null && !humanSeats.includes(waitingOn);

  /** Another person is deciding. Nothing to pump; nothing to do but listen. */
  const waitingForPlayer = waitingOn !== null && humanSeats.includes(waitingOn);

  /**
   * Who pumps the AI: the lowest human seat, or a listener that has taken over.
   *
   * With two people at a table both pumping, each got half of the AI's events
   * and the other half arrived as a surprise; and the wait-for-narration gate
   * on one screen was defeated by the other screen's pump.
   */
  const pumper = humanSeats.length > 0 ? humanSeats[0] : null;
  const pumping = aiThinking && (yourSeat === pumper || takeover);

  /**
   * Whether to hold a long poll open. Gated on the session knowing its own
   * seat: `yourSeat` is known from the first, seat-less fetch, and a poll
   * started under that query key is torn down the moment the key changes.
   */
  const listening = waitingOn !== null && !pumping && session !== null && session.seat !== null;

  // A takeover lasts for one AI decision run. Once a person is on the clock
  // again the election starts over from the lowest seat.
  useEffect(() => {
    if (!aiThinking) setTakeover(false);
  }, [aiThinking]);

  const busy =
    act.isPending || declare.isPending || choose.isPending || undo.isPending || pump.isPending;

  // The pump. Deliberately waits for the narration queue so the animation of
  // the last decision finishes before the next one is requested.
  const pumpMutate = pump.mutate;
  useEffect(() => {
    if (!session || !pumping || stalled) return;
    if (busy || narration.busy) return;
    const timer = setTimeout(() => pumpMutate(), PUMP_DELAY_MS);
    return () => clearTimeout(timer);
  }, [session, pumping, stalled, busy, narration.busy, pumpMutate]);

  /*
   * The listener reads these from inside its loop. Refs, because the loop must
   * outlive any single render: a dependency that changed on every response
   * would tear the poll down and re-issue it, and every abandoned poll is a
   * server thread parked for up to 25 s.
   */
  const narrationBusyRef = useRef(false);
  useEffect(() => {
    narrationBusyRef.current = narration.busy;
  }, [narration.busy]);
  const aiOnClockRef = useRef(false);
  useEffect(() => {
    aiOnClockRef.current = aiThinking;
  }, [aiThinking]);

  // The listener: one request in flight at a time, re-issued the moment it
  // lands, for as long as somebody else is on the clock.
  const gameId = session?.gameId ?? null;
  useEffect(() => {
    if (!gameId || yourSeat === null || !listening) return;
    const seat = yourSeat;
    let live = true;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, ms);
      });

    const listen = async () => {
      while (live) {
        controller = new AbortController();
        try {
          const response = await api.state(
            gameId,
            seat,
            cursorRef.current,
            versionRef.current,
            POLL_SECONDS,
            controller.signal,
          );
          if (!live) return;
          if (response.version <= versionRef.current) {
            // Timed out. If an AI is on the clock and nobody has moved it in
            // all that time, the pumper's tab is gone: take the pump over.
            if (aiOnClockRef.current) {
              setTakeover(true);
              return;
            }
            continue;
          }
          // Let the last batch finish animating before this one lands on the
          // board -- by waiting, not by dropping the response and asking again.
          while (live && narrationBusyRef.current) await sleep(NARRATION_TICK_MS);
          if (!live) return;
          absorbRef.current(response);
          // Decide from the response whether there is anything left to hear.
          // The re-render that flips `listening` has not happened yet, and a
          // request issued now would park a server thread for nothing.
          const next = waitingOnFrom(response, seat);
          if (next === null) return;
          const nextIsAi = !response.human_seats.includes(next);
          if (nextIsAi && seat === response.human_seats[0]) return;
        } catch (caught) {
          if (!live) return;
          const error = caught as Error;
          setError(error.message);
          // The game is gone or the seat is not ours any more. Neither is
          // going to change by asking again every two seconds.
          if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
            return;
          }
          await sleep(RETRY_MS);
        }
      }
    };

    void listen();
    return () => {
      live = false;
      controller?.abort();
      if (timer) clearTimeout(timer);
    };
  }, [gameId, yourSeat, listening, setError]);

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
    choose,
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
