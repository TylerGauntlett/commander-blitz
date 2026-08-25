/**
 * Back, in the lobby, and how far it is allowed to go.
 *
 * Two defects, one shape, and both of them were reported as "the B button takes
 * me to the wrong place".
 *
 * **B did nothing at all.** Every overlay in the lobby -- the deck catalogue,
 * the dossier, the invite dialog -- bound a bare `window` keydown for `Escape`
 * and nothing for the pad's `b`. The catalogue's own footer draws a `B — Back`
 * hint, and `tests/hintsBound.test.ts` could not see the gap because it asks
 * only whether a button is bound SOMEWHERE in the app. So a player on a pad
 * pressed the advertised button, the game ignored it, and whatever their
 * controller layout does with an unclaimed B happened instead -- on a Steam
 * Deck a history step, and from `/pods/{code}` a history step is the front
 * door. Backing out of a modal dropped them out of the pod.
 *
 * **And Escape closed two things at once.** The catalogue can open a dossier
 * over itself; both listeners were on `window`, so one press ran both and the
 * catalogue underneath -- which nobody had asked to leave and nobody could see
 * past the dossier -- went with it. Back means back one.
 *
 * `input/useDismiss.ts` is the one path both now take, and `stopRoot()` is what
 * it asks -- the same question navigation already asks about which surface owns
 * the ring, rather than a second stack that could disagree with the first.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PodLobby } from "../src/components/lobby/PodLobby";
import { Screen } from "../src/components/screen/Screen";
import { resetInputMode } from "../src/input/inputMode";
import { resetPad } from "../src/input/pad";
import { deckSummary, podView } from "../src/testing/fixtures";

/** rAF on the fake clock: `b` arrives from the poll loop, a frame after the key. */
beforeEach(() => {
  vi.useFakeTimers();
  (navigator as unknown as { getGamepads: () => unknown[] }).getGamepads = () => [];
  (globalThis as unknown as Record<string, unknown>).requestAnimationFrame = (
    cb: FrameRequestCallback,
  ) => setTimeout(() => cb(performance.now()), 16) as unknown as number;
  (globalThis as unknown as Record<string, unknown>).cancelAnimationFrame = (h: number) =>
    clearTimeout(h as unknown as ReturnType<typeof setTimeout>);
});

afterEach(() => {
  cleanup();
  resetPad();
  resetInputMode();
  vi.useRealTimers();
});

const noop = () => undefined;
const DECKS = [deckSummary(), deckSummary({ id: "edgar", name: "Edgar Markov" })];

function lobby() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  const pod = podView([
    { kind: "human", is_you: true, is_host: true, name: "You", deck: deckSummary() },
  ]);
  return render(
    <QueryClientProvider client={client}>
      <Screen>
        <PodLobby
          pod={pod}
          decks={DECKS}
          busy={false}
          starting={false}
          error={null}
          onUpdateSeat={noop}
          onAdminSeat={noop}
          onSetSeatDeck={noop}
          onStart={noop}
          onLeave={noop}
          onDecksChanged={noop}
        />
      </Screen>
    </QueryClientProvider>,
  );
}

/**
 * One press of `B`, all the way through the pad layer.
 *
 * `k` rather than `Escape`: `buttons.ts` maps both onto `b`, and `k` is the one
 * that cannot also be answered by a raw `Escape` listener -- so what this
 * exercises is the pad intent itself.
 */
function back(): void {
  act(() => {
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "k" });
    vi.advanceTimersByTime(60);
    fireEvent.keyUp(document.activeElement ?? document.body, { key: "k" });
    vi.advanceTimersByTime(60);
  });
}

/** ...and the same press spelled as the key a keyboard sends. */
function pressEscape(): void {
  act(() => {
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    vi.advanceTimersByTime(60);
    fireEvent.keyUp(document.activeElement ?? document.body, { key: "Escape" });
    vi.advanceTimersByTime(60);
  });
}

/** Open the catalogue the way the screen does, from the chair's own control. */
function openCatalogue(): void {
  act(() => {
    screen.getByTestId("change-deck").click();
  });
}

function openDossier(): void {
  act(() => {
    screen.getByTestId("deck-aesi-info").click();
  });
}

describe("B, in the deck catalogue", () => {
  it("closes it, which is what its own footer has been promising", () => {
    lobby();
    openCatalogue();
    expect(screen.queryByTestId("deck-catalog")).toBeTruthy();

    back();
    expect(screen.queryByTestId("deck-catalog")).toBeNull();
    // ...and the pod is still there. The bug was that nothing in the app
    // claimed this press, so the browser's own Back did, and that leaves.
    expect(screen.queryByTestId("new-game")).toBeTruthy();
  });
});

describe("B, with a dossier open over the catalogue", () => {
  it("closes the dossier and leaves the catalogue standing", () => {
    lobby();
    openCatalogue();
    openDossier();
    expect(screen.queryByTestId("deck-dossier")).toBeTruthy();

    back();
    expect(screen.queryByTestId("deck-dossier")).toBeNull();
    expect(screen.queryByTestId("deck-catalog")).toBeTruthy();
  });

  it("takes two presses to leave both, one surface each", () => {
    lobby();
    openCatalogue();
    openDossier();

    back();
    back();
    expect(screen.queryByTestId("deck-dossier")).toBeNull();
    expect(screen.queryByTestId("deck-catalog")).toBeNull();
    expect(screen.queryByTestId("new-game")).toBeTruthy();
  });
});

describe("Escape, which is the same button", () => {
  it("also unwinds exactly one surface", () => {
    lobby();
    openCatalogue();
    openDossier();

    pressEscape();
    expect(screen.queryByTestId("deck-dossier")).toBeNull();
    expect(
      screen.queryByTestId("deck-catalog"),
      "one press closed the dossier AND the catalogue under it",
    ).toBeTruthy();
  });

  it("still closes the catalogue from inside the search box", () => {
    /*
     * The press the pad layer never delivers: `fieldKeeps` gives a text field
     * every non-direction key, so Escape typed here emits no `b` at all. That
     * is the one case `useDismiss` answers the raw key for -- and answering it
     * unconditionally instead is what closed two overlays at once.
     */
    lobby();
    openCatalogue();
    act(() => {
      screen.getByTestId("deck-search").focus();
    });
    pressEscape();
    expect(screen.queryByTestId("deck-catalog")).toBeNull();
  });
});
