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
      onClear={noop}
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
    // ONE button per chair. There were two, and the second said "Invite a
    // player" on all three empty chairs -- the same words the header carries,
    // three more times, on the screen with the least room for them.
    expect(screen.queryByTestId("invite-1")).toBeNull();
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
    // The chair says WAITING on its back and nothing else: "Pod GYRE-8412"
    // under it repeated the code chip in the bar, and "Anyone with the code"
    // repeated the word "open" in the tag above it.
    expect(screen.queryByText(/Pod GYRE-8412/)).toBeNull();
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
    // The back says SEALED. "Deck sealed" and "Readable once they lock in"
    // under it were two captions for a picture that had already said it.
    expect(screen.queryByText(/Readable once they lock in/)).toBeNull();
    expect(screen.queryByTestId("seat-1-deck")).toBeNull();
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
    expect(container.querySelector(".chair__act button")).toBeNull();
    // Not even for the host: that deck is theirs, and the server refuses it.
    expect(container.querySelector(".chair__x")).toBeNull();
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
    fireEvent.click(container.querySelector(".chair__x") as Element);
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
    expect(container.querySelector(".chair__x")).toBeNull();
  });
});

describe("nobody types a name", () => {
  /*
   * THE FIELD IS GONE, AND ITS ABSENCE IS THE ASSERTION.
   *
   * Typing a name with a controller is a virtual keyboard, a d-pad and about
   * twenty presses to replace "Player 1" with something nobody at the table
   * needs. The server names every chair after its seat, so the row still reads
   * as four distinct people -- and this was the last text box on the pod, which
   * makes it the last place a ring could get stuck.
   */
  it("labels your own chair exactly like everybody else's", () => {
    const pod = podView([
      { ...me, name: "Tyler", deck: deckSummary() },
      { kind: "human", name: "Priya", deck: deckSummary(), locked: true, ready: true },
    ]);
    const { container } = seatAt(pod, 0);
    expect(screen.queryByTestId("your-name")).toBeNull();
    expect(container.querySelectorAll("input").length).toBe(0);
    expect(screen.getByText("You")).toBeTruthy();
    cleanup();

    seatAt(pod, 1);
    expect(screen.getByText("Priya")).toBeTruthy();
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
    expect(container.querySelector(".chair__x")).toBeNull();
  });

  it("opens the dossier from the card, which is the only way in", () => {
    // There was a second door -- an `i` glyph in the plate's meta row -- and it
    // was a second stop for the ring to walk through on every chair to reach
    // the one button underneath. The card is already the size and shape of a
    // thing you pick up; a caption-sized duplicate of it is not a second
    // affordance, it is a second thing to get past.
    const pod = podView([{ ...me, deck: deckSummary() }]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 0, { onDossier: dossier });

    fireEvent.click(container.querySelector(".chair__card") as Element);
    expect(dossier).toHaveBeenCalledWith("aesi", 0);
    expect(container.querySelector(".ibtn")).toBeNull();
  });

  it("opens the dossier from the keyboard too", () => {
    // `role=button` rather than a real `<button>`, because a `<button>` may not
    // contain the divs a card face is made of -- so the key handler is the
    // whole keyboard story and is worth a test.
    const pod = podView([{ ...me, deck: deckSummary() }]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 0, { onDossier: dossier });
    fireEvent.keyDown(container.querySelector(".chair__card") as Element, { key: "Enter" });
    expect(dossier).toHaveBeenCalledWith("aesi", 0);
  });

  it("does not offer a dossier for a card nobody may read", () => {
    const pod = podView([
      { ...me, deck: deckSummary() },
      { kind: "human", name: "Priya" },
    ]);
    const dossier = vi.fn();
    const { container } = seatAt(pod, 1, { onDossier: dossier });
    fireEvent.click(container.querySelector(".chair__card") as Element);
    expect(dossier).not.toHaveBeenCalled();
  });
});
