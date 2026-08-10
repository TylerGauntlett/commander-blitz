/**
 * One seat, rendered.
 *
 * Two properties carry this file. **A face-down card is one picture for three
 * different facts** -- empty, invited, sealed -- so the tests check that all
 * three draw a `.back` and that the three are distinguishable by the plate
 * rather than by three different card designs. And **the stamp is only ever on
 * a face-up card**, because a wax seal over a card back would be saying two
 * contradictory things at once.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PodSeat } from "../src/components/lobby/PodSeat";
import { deckSummary, podView } from "./fixtures";

afterEach(cleanup);

const noop = () => undefined;

/** `CommanderCard` fetches; nothing here asserts on the fetched card. */
function draw(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function seatAt(pod: ReturnType<typeof podView>, index: number, props = {}) {
  return draw(
    <PodSeat
      pod={pod}
      seat={pod.seats[index]}
      youAreHost={pod.you_are_host}
      onChooseDeck={noop}
      onAddCpu={noop}
      onOpenChair={noop}
      onClear={noop}
      onInvite={noop}
      onDossier={noop}
      {...props}
    />,
  );
}

const me = { kind: "human" as const, is_you: true, is_host: true, name: "You" };

describe("an empty seat", () => {
  it("draws a card back and offers to fill it", () => {
    const pod = podView([{ ...me, deck: deckSummary() }]);
    seatAt(pod, 1);
    expect(screen.getByTestId("card-back").getAttribute("data-tone")).toBe("empty");
    expect(screen.getByTestId("opponents-1")).toBeTruthy();
    expect(screen.getByTestId("invite-1")).toBeTruthy();
  });

  it("numbers the CPU button by the pod size it would produce", () => {
    // `e2e/helpers.ts:startGame` clicks these in order, so the number is a
    // contract rather than a label.
    const pod = podView([
      { ...me, deck: deckSummary() },
      { kind: "cpu", ready: true },
    ]);
    seatAt(pod, 2);
    expect(screen.getByTestId("opponents-2")).toBeTruthy();
  });

  it("offers a guest nothing to press", () => {
    const pod = podView([
      { kind: "human", name: "Host", is_host: true },
      { ...me, is_host: false, index: 1 },
    ]);
    seatAt(pod, 2, { youAreHost: false });
    expect(screen.queryByTestId("opponents-2")).toBeNull();
  });
});

describe("an open chair", () => {
  it("is a card back that says what it is waiting for", () => {
    const pod = podView([
      { ...me, deck: deckSummary() },
      { kind: "open", name: "Open" },
    ]);
    seatAt(pod, 1);
    expect(screen.getByTestId("card-back").getAttribute("data-tone")).toBe("open");
    expect(screen.getByText("Open chair")).toBeTruthy();
    expect(screen.getByText(/Pod GYRE-8412/)).toBeTruthy();
  });

  it("wears no stamp, because there is nothing face up to stamp", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, { kind: "open" }]);
    seatAt(pod, 1);
    expect(screen.queryByTestId("stamp-1")).toBeNull();
  });
});

describe("another player's seat", () => {
  const unlocked = { kind: "human" as const, name: "Priya", deck: null };

  it("is sealed until they lock in", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, unlocked]);
    seatAt(pod, 1);
    expect(screen.getByTestId("card-back").getAttribute("data-tone")).toBe("sealed");
    expect(screen.getByText("Deck sealed")).toBeTruthy();
    expect(screen.getByText(/Readable once they lock in/)).toBeTruthy();
  });

  it("turns face up and stamps once they do", () => {
    const pod = podView([
      { ...me, deck: deckSummary() },
      {
        kind: "human",
        name: "Priya",
        deck: deckSummary({ id: "edgar", name: "Edgar Markov" }),
        locked: true,
        ready: true,
      },
    ]);
    seatAt(pod, 1);
    expect(screen.queryByTestId("card-back")).toBeNull();
    expect(screen.getByTestId("seat-1-deck").textContent).toBe("Edgar Markov");
    expect(screen.getByTestId("stamp-1")).toBeTruthy();
  });

  it("wears a different stamp from your own", () => {
    // At a glance the row should say "mine is gold, theirs are green" without
    // anybody reading a name.
    const pod = podView([
      { ...me, deck: deckSummary(), locked: true, ready: true },
      { kind: "human", name: "Priya", deck: deckSummary(), locked: true, ready: true },
    ]);
    const { container } = seatAt(pod, 0);
    expect(container.querySelector(".stamp--them")).toBeNull();
    cleanup();
    const other = seatAt(pod, 1);
    expect(other.container.querySelector(".stamp--them")).toBeTruthy();
  });

  it("carries no controls at all -- there is nothing for you to change", () => {
    const pod = podView([
      { ...me, deck: deckSummary() },
      { kind: "human", name: "Priya", deck: deckSummary(), locked: true, ready: true },
    ]);
    const { container } = seatAt(pod, 1);
    expect(container.querySelector(".plate__acts")).toBeNull();
    // Not even for the host: that deck is theirs, and the server refuses it.
    expect(container.querySelector(".slot__x")).toBeNull();
  });
});

describe("a CPU seat", () => {
  const cpu = {
    kind: "cpu" as const,
    name: "CPU 1",
    deck: deckSummary({ id: "zurgo", name: "Zurgo Stormrender" }),
    locked: true,
    ready: true,
  };

  it("is always face up -- the host chose its deck", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, cpu]);
    seatAt(pod, 1);
    expect(screen.queryByTestId("card-back")).toBeNull();
    expect(screen.getByTestId("seat-1-deck").textContent).toBe("Zurgo Stormrender");
  });

  it("is stamped, because it is locked in by construction", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, cpu]);
    seatAt(pod, 1);
    expect(screen.getByTestId("stamp-1")).toBeTruthy();
  });

  it("lets the host change its deck and empty its chair", () => {
    const pod = podView([{ ...me, deck: deckSummary() }, cpu]);
    const chooseDeck = vi.fn();
    const clear = vi.fn();
    const { container } = seatAt(pod, 1, { onChooseDeck: chooseDeck, onClear: clear });
    fireEvent.click(screen.getByTestId("cpu-deck-1"));
    expect(chooseDeck).toHaveBeenCalledWith(1);
    fireEvent.click(container.querySelector(".slot__x") as Element);
    expect(clear).toHaveBeenCalledWith(1);
  });

  it("offers a guest neither", () => {
    const pod = podView([
      { kind: "human", name: "Host", is_host: true },
      cpu,
      { ...me, is_host: false },
    ]);
    const { container } = seatAt(pod, 1, { youAreHost: false });
    expect(screen.queryByTestId("cpu-deck-1")).toBeNull();
    expect(container.querySelector(".slot__x")).toBeNull();
  });
});

describe("your own seat", () => {
  it("says Choose a deck before you have one", () => {
    seatAt(podView([me]), 0);
    expect(screen.getByTestId("change-deck").textContent).toBe("Choose a deck");
  });

  it("says Change deck once you do", () => {
    seatAt(podView([{ ...me, deck: deckSummary() }]), 0);
    expect(screen.getByTestId("change-deck").textContent).toBe("Change deck");
  });

  it("refuses to change decks while you are locked in", () => {
    seatAt(podView([{ ...me, deck: deckSummary(), locked: true, ready: true }]), 0);
    expect(screen.getByTestId("change-deck").hasAttribute("disabled")).toBe(true);
  });

  it("has no ✕ -- a host who emptied it could not get back in", () => {
    const { container } = seatAt(podView([{ ...me, deck: deckSummary() }]), 0);
    expect(container.querySelector(".slot__x")).toBeNull();
  });

  it("opens the dossier from the card and from the glyph", () => {
    const pod = podView([{ ...me, deck: deckSummary() }]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 0, { onDossier: dossier });

    fireEvent.click(container.querySelector(".slot__card") as Element);
    expect(dossier).toHaveBeenCalledWith("aesi", 0);

    fireEvent.click(container.querySelector(".ibtn") as Element);
    expect(dossier).toHaveBeenCalledTimes(2);
  });

  it("opens the dossier from the keyboard too", () => {
    // `role=button` rather than a real `<button>`, because a `<button>` may not
    // contain the divs a card face is made of -- so the key handler is the
    // whole keyboard story and is worth a test.
    const pod = podView([{ ...me, deck: deckSummary() }]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 0, { onDossier: dossier });
    fireEvent.keyDown(container.querySelector(".slot__card") as Element, { key: "Enter" });
    expect(dossier).toHaveBeenCalledWith("aesi", 0);
  });

  it("does not offer a dossier for a card nobody may read", () => {
    const pod = podView([
      { ...me, deck: deckSummary() },
      { kind: "human", name: "Priya" },
    ]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 1, { onDossier: dossier });
    fireEvent.click(container.querySelector(".slot__card") as Element);
    expect(dossier).not.toHaveBeenCalled();
  });
});
