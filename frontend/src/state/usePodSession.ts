/**
 * Who this tab is, for the place the URL is pointing at.
 *
 * The URL carries the *place*; `sessionStorage` carries the *identity*. Keeping
 * them apart is not tidiness -- a token in the address bar is a token in
 * somebody's chat history, and the whole point of an invite link is that it gets
 * pasted. So `/pods/GYRE-8412` says which pod and nothing about who you are,
 * and a link that arrives on a machine holding no token cannot open the lobby.
 * It goes to the front door with the code filled in, which is the join flow that
 * already existed.
 *
 * The awkward part is the table. Identity is stored per *pod code*
 * (`commanderblitz.pod.<CODE>`, see `usePod`) but `/games/:id` is keyed by game id, and
 * a reload there has no way to get from one to the other. So a second key
 * records which pod dealt which game -- written the moment a client learns the
 * game id, read on a cold boot at a table. The token itself still lives in
 * exactly one place, so `forgetPod` remains the single way to drop it.
 */

import { useCallback, useState } from "react";
import { setPlayerToken } from "../api/client";
import { forgetPod, type PodSession, storedToken } from "./usePod";

const GAME_PREFIX = "commanderblitz.game.";

function gameKey(gameId: string): string {
  return `${GAME_PREFIX}${gameId}`;
}

/** Remember which pod dealt a game, so a reload of `/games/:id` can find its token. */
export function linkGame(gameId: string, code: string): void {
  try {
    window.sessionStorage.setItem(gameKey(gameId), code.toUpperCase());
  } catch {
    // Private browsing with storage disabled. The table works for the life of
    // the tab; only surviving a reload is lost -- same trade as the token.
  }
}

/** The pod a game was dealt from, if this tab was there when it happened. */
export function gamePodCode(gameId: string): string | null {
  try {
    return window.sessionStorage.getItem(gameKey(gameId));
  } catch {
    return null;
  }
}

/**
 * Arm the module's token slot and describe the session, in one step.
 *
 * Called during *render*, deliberately, and this is the constraint the whole
 * file is shaped around: `usePod` and `useGame` fire their first request from an
 * effect in a child, and a child's effect runs before its parent's. A token
 * armed in an effect here would arrive one round trip late, so the opening
 * request of every deep link would go out unauthenticated and come back 403.
 *
 * It is safe to do in render because it is idempotent and derived purely from
 * the arguments -- StrictMode's double invocation computes the same answer
 * twice, and a re-render for any other reason re-asserts what is already true.
 */
function arm(code: string | null): PodSession | null {
  const token = code ? storedToken(code) : null;
  setPlayerToken(token);
  return code && token ? { code, token } : null;
}

/**
 * The session for a `/pods/:code`, or null when this tab has never joined it.
 *
 * Null is the cold case, and the caller's job is to send it to the front door
 * rather than to render a lobby with nobody in it.
 */
export function usePodSession(code: string | undefined): {
  session: PodSession | null;
  /** After leaving: drop the token, so the redirect does not race the render. */
  forget: () => void;
} {
  const at = code ?? null;
  const [held, setHeld] = useState<{ code: string | null; session: PodSession | null }>(() => ({
    code: at,
    session: arm(at),
  }));

  // Adjusting state during render rather than in an effect, for the reason in
  // `arm`: an effect would re-arm the token after the new pod's first request
  // had already gone out under the old one's.
  if (held.code !== at) setHeld({ code: at, session: arm(at) });

  const forget = useCallback(() => {
    if (at) forgetPod(at);
    else setPlayerToken(null);
    setHeld({ code: at, session: null });
  }, [at]);

  return { session: held.session, forget };
}

/**
 * The session for a `/games/:id`: game id -> pod code -> token.
 *
 * Returns null when this tab has no record of the game, which the server will
 * turn into a 403 rather than this client guessing at a seat.
 */
export function useGameSession(gameId: string | undefined): PodSession | null {
  const at = gameId ?? null;
  const [held, setHeld] = useState<{ gameId: string | null; session: PodSession | null }>(
    () => ({ gameId: at, session: arm(at ? gamePodCode(at) : null) }),
  );

  if (held.gameId !== at) {
    setHeld({ gameId: at, session: arm(at ? gamePodCode(at) : null) });
  }

  return held.session;
}
