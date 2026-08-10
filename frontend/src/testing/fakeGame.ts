/**
 * A `useGame` session, without a server.
 *
 * `Table` takes the whole hook result as a prop, which is convenient in the app
 * and awkward here: the type includes four `UseMutationResult` objects, each
 * with about twenty fields, even though `Table` reads exactly one thing off each
 * of them (`.mutate` -- `isPending` is already folded into `game.busy` inside
 * the hook). `idleMutation` pays that type tax in one place so a story can say
 * what it means.
 *
 * Stories pass spies in: `fakeGame({ act: idleMutation(fn()) })`, and then a
 * play function can assert `expect(game.act.mutate).toHaveBeenCalledWith(id)`.
 *
 * The cleaner fix is to narrow `Table`'s prop to only what it reads, which would
 * delete this file. That is a production change and belongs in its own commit.
 */

import type { UseMutationResult } from "@tanstack/react-query";
import type { GameView, LegalAction } from "../api/types";
import type { useGame } from "../state/useGame";

export type FakeGame = ReturnType<typeof useGame>;

/**
 * A mutation that has never run.
 *
 * Cast at the boundary because react-query's result is a discriminated union
 * over `status`, and spelling out the idle branch's twenty fields to satisfy it
 * would be twenty ways to get a fixture wrong.
 */
export function idleMutation<TData = unknown, TVars = unknown>(
  mutate: (variables: TVars) => void = () => undefined,
): UseMutationResult<TData, Error, TVars, unknown> {
  return {
    data: undefined,
    error: null,
    variables: undefined,
    context: undefined,
    isError: false,
    isIdle: true,
    isPending: false,
    isSuccess: false,
    isPaused: false,
    failureCount: 0,
    failureReason: null,
    status: "idle",
    submittedAt: 0,
    mutate,
    mutateAsync: async () => undefined as TData,
    reset: () => undefined,
  } as unknown as UseMutationResult<TData, Error, TVars, unknown>;
}

/** A narration queue with nothing in it, which is the quiet board. */
function idleNarration(): FakeGame["narration"] {
  return {
    current: null,
    queued: 0,
    busy: false,
    push: () => undefined,
    skip: () => undefined,
    reset: () => undefined,
  };
}

export interface FakeGameInput extends Partial<FakeGame> {
  state?: GameView;
  actions?: LegalAction[];
}

/** A settled session: nothing in flight, nobody being waited on. */
export function fakeGame(overrides: FakeGameInput = {}): FakeGame {
  const state = overrides.state;
  return {
    state,
    actions: [],
    events: [],
    isLoading: false,
    error: null,
    yourSeat: state?.seat ?? 0,
    aiThinking: false,
    waitingForPlayer: false,
    stalled: false,
    busy: false,
    narration: idleNarration(),
    // Events carry the snake_case card id, not the printed name; the real hook
    // harvests the map from every zone it sees. A story's fixtures already have
    // real names on them, so returning nothing here is honest rather than lossy.
    cardName: () => undefined,
    act: idleMutation(),
    declare: idleMutation(),
    undo: idleMutation(),
    setFullControl: idleMutation(),
    setManualMana: idleMutation(),
    ...overrides,
  } as FakeGame;
}
