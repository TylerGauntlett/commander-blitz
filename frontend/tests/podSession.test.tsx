/**
 * Identity, derived from the URL.
 *
 * The assertion that matters is the timing one: the token has to be armed
 * *before* a child's effect fires, because that is when the first request of a
 * deep link goes out. A test that only checked the token was set eventually
 * would pass against the bug this is guarding.
 */

import { render, renderHook } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { getPlayerToken, setPlayerToken } from "../src/api/client";
import { type PodSession, storeToken } from "../src/state/usePod";
import {
  gamePodCode,
  linkGame,
  useGameSession,
  usePodSession,
} from "../src/state/usePodSession";

beforeEach(() => {
  window.sessionStorage.clear();
  setPlayerToken(null);
});

/** A child, because a child's effect is what runs first and does the fetching. */
function Child({ onEffect }: { onEffect: (token: string | null) => void }) {
  useEffect(() => {
    onEffect(getPlayerToken());
  }, [onEffect]);
  return null;
}

type Session = PodSession | null;

/** Reads the pod's session on its first render, then mounts a fetching child. */
function PodParent({
  code,
  onRender,
  onEffect,
}: {
  code: string;
  onRender: (session: Session) => void;
  onEffect: (token: string | null) => void;
}) {
  onRender(usePodSession(code).session);
  return <Child onEffect={onEffect} />;
}

/** The same, resolving the pod through a game id. */
function GameParent({
  gameId,
  onRender,
  onEffect,
}: {
  gameId: string;
  onRender: (session: Session) => void;
  onEffect: (token: string | null) => void;
}) {
  onRender(useGameSession(gameId));
  return <Child onEffect={onEffect} />;
}

describe("the game -> pod link", () => {
  it("round trips, uppercasing the code the way the token key is", () => {
    linkGame("g1", "gyre-8412");
    expect(gamePodCode("g1")).toBe("GYRE-8412");
  });

  it("has nothing to say about a game this tab never saw", () => {
    expect(gamePodCode("g-nobody")).toBeNull();
  });
});

describe("usePodSession", () => {
  it("is null for a pod this tab holds no token for", () => {
    const { result } = renderHook(() => usePodSession("GYRE-8412"));
    expect(result.current.session).toBeNull();
    expect(getPlayerToken()).toBeNull();
  });

  it("arms the token before a child's effect can fetch with it", () => {
    storeToken("GYRE-8412", "tok-1");
    const atRender: Session[] = [];
    const atEffect: (string | null)[] = [];
    render(
      <PodParent
        code="GYRE-8412"
        onRender={(session) => atRender.push(session)}
        onEffect={(token) => atEffect.push(token)}
      />,
    );
    expect(atRender[0]).toEqual({ code: "GYRE-8412", token: "tok-1" });
    expect(atEffect[0]).toBe("tok-1");
  });

  it("re-arms when the URL moves to another pod", () => {
    storeToken("GYRE-8412", "tok-1");
    storeToken("BRAMBLE-1234", "tok-2");
    const { result, rerender } = renderHook(
      ({ code }: { code: string }) => usePodSession(code),
      { initialProps: { code: "GYRE-8412" } },
    );
    expect(result.current.session?.token).toBe("tok-1");
    rerender({ code: "BRAMBLE-1234" });
    expect(result.current.session?.token).toBe("tok-2");
    expect(getPlayerToken()).toBe("tok-2");
  });
});

describe("useGameSession", () => {
  it("walks game id -> pod code -> token", () => {
    storeToken("GYRE-8412", "tok-1");
    linkGame("g1", "GYRE-8412");
    const atRender: Session[] = [];
    const atEffect: (string | null)[] = [];
    render(
      <GameParent
        gameId="g1"
        onRender={(session) => atRender.push(session)}
        onEffect={(token) => atEffect.push(token)}
      />,
    );
    expect(atRender[0]).toEqual({ code: "GYRE-8412", token: "tok-1" });
    expect(atEffect[0]).toBe("tok-1");
  });

  it("is null for a table this tab was never dealt into", () => {
    const { result } = renderHook(() => useGameSession("g-stranger"));
    expect(result.current).toBeNull();
    expect(getPlayerToken()).toBeNull();
  });
});
