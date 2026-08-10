/**
 * Identity, derived from the URL.
 *
 * The assertion that matters is the timing one: the token has to be armed
 * *before* a child's effect fires, because that is when the first request of a
 * deep link goes out. A test that only checked the token was set eventually
 * would pass against the bug this is guarding.
 */

import { render } from "@testing-library/react";
import { useEffect } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { getPlayerToken, setPlayerToken } from "../src/api/client";
import { storeToken } from "../src/state/usePod";
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
    let seen: unknown = "unset";
    function Probe() {
      seen = usePodSession("GYRE-8412").session;
      return null;
    }
    render(<Probe />);
    expect(seen).toBeNull();
    expect(getPlayerToken()).toBeNull();
  });

  it("arms the token before a child's effect can fetch with it", () => {
    storeToken("GYRE-8412", "tok-1");
    const atEffect: (string | null)[] = [];
    function Parent() {
      const { session } = usePodSession("GYRE-8412");
      expect(session).toEqual({ code: "GYRE-8412", token: "tok-1" });
      return <Child onEffect={(token) => atEffect.push(token)} />;
    }
    render(<Parent />);
    expect(atEffect[0]).toBe("tok-1");
  });

  it("re-arms when the URL moves to another pod", () => {
    storeToken("GYRE-8412", "tok-1");
    storeToken("BRAMBLE-1234", "tok-2");
    let seen: string | null = null;
    function Probe({ code }: { code: string }) {
      seen = usePodSession(code).session?.token ?? null;
      return null;
    }
    const view = render(<Probe code="GYRE-8412" />);
    expect(seen).toBe("tok-1");
    view.rerender(<Probe code="BRAMBLE-1234" />);
    expect(seen).toBe("tok-2");
    expect(getPlayerToken()).toBe("tok-2");
  });
});

describe("useGameSession", () => {
  it("walks game id -> pod code -> token", () => {
    storeToken("GYRE-8412", "tok-1");
    linkGame("g1", "GYRE-8412");
    const atEffect: (string | null)[] = [];
    function Parent() {
      const session = useGameSession("g1");
      expect(session).toEqual({ code: "GYRE-8412", token: "tok-1" });
      return <Child onEffect={(token) => atEffect.push(token)} />;
    }
    render(<Parent />);
    expect(atEffect[0]).toBe("tok-1");
  });

  it("is null for a table this tab was never dealt into", () => {
    let seen: unknown = "unset";
    function Probe() {
      seen = useGameSession("g-stranger");
      return null;
    }
    render(<Probe />);
    expect(seen).toBeNull();
    expect(getPlayerToken()).toBeNull();
  });
});
