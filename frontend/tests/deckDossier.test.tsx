/**
 * The deck dossier, and the honest empty states in it.
 *
 * Half of what this screen shows is authored per deck and half is derived from
 * the card list. An imported deck has none of the first half, and the whole
 * design point is that it says so rather than inventing a strategy paragraph or
 * drawing a flat rating bar. So most of this file is the *absent* cases.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeckDetail } from "../src/api/types";
import { DeckDossier, ManaCurve, RatingBar } from "../src/components/lobby/DeckDossier";
import { useUiStore } from "../src/state/uiStore";
import { cardResponse, deckDetail as detail } from "./fixtures";

afterEach(() => {
  cleanup();
  // The image map is module state; a dossier that credited the previous test's
  // illustrator would be the sort of pass nobody trusts.
  useUiStore.setState({ images: null });
});

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

function draw(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Serve `/api/decks/{id}`, and a bare card for the commander face. */
function serve(deck: DeckDetail) {
  fetchMock.mockImplementation((url: string) => {
    // No art on the commander: this file is about the dossier's own content,
    // and a face that resolved a picture would credit an artist these
    // assertions did not ask for.
    const body = url.includes("/decks/") ? deck : cardResponse({ art_url: null, artist: null });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    } as Response);
  });
}

async function open(deck: DeckDetail) {
  serve(deck);
  const rendered = draw(
    <DeckDossier deckId={deck.id} canTake onTake={() => undefined} onClose={() => undefined} />,
  );
  await waitFor(() => expect(screen.getByText(deck.name)).toBeTruthy());
  return rendered;
}

describe("RatingBar", () => {
  it("fills as many of four segments as the rating", () => {
    const { container } = render(<RatingBar label="Speed" value={3} />);
    expect(container.querySelectorAll(".bar__seg")).toHaveLength(4);
    expect(container.querySelectorAll(".bar__seg--on")).toHaveLength(3);
  });

  it("says the number out loud for a screen reader", () => {
    // The bar is the whole signal visually, so without this the rating is
    // simply absent for anybody not looking at it.
    render(<RatingBar label="Speed" value={3} />);
    expect(screen.getByLabelText("Speed: 3 of 4")).toBeTruthy();
  });
});

describe("ManaCurve", () => {
  it("draws a column per bucket, tallest at 100%", () => {
    const { container } = render(<ManaCurve values={[9, 13, 18, 7, 7, 3, 5]} />);
    const bars = container.querySelectorAll(".curve__bar");
    expect(bars).toHaveLength(7);
    expect((bars[2] as HTMLElement).style.height).toBe("100%");
    expect((bars[5] as HTMLElement).style.height).toBe("17%");
  });

  it("labels the last bucket as open-ended", () => {
    render(<ManaCurve values={[1, 1, 1, 1, 1, 1, 1]} />);
    expect(screen.getByText("7+")).toBeTruthy();
  });

  it("says so rather than drawing a flat line when there is no curve", () => {
    render(<ManaCurve values={[]} />);
    expect(screen.getByTestId("curve-empty")).toBeTruthy();
  });

  it("treats an all-zero curve as no curve", () => {
    render(<ManaCurve values={[0, 0, 0, 0, 0, 0, 0]} />);
    expect(screen.getByTestId("curve-empty")).toBeTruthy();
  });
});

describe("a fully authored deck", () => {
  it("shows the ratings, the strategy and the signature cards", async () => {
    await open(detail());
    expect(screen.getByTestId("dossier-ratings")).toBeTruthy();
    expect(screen.getByText(/first four turns/)).toBeTruthy();
    expect(screen.getByText("Tatyova, Benthic Druid")).toBeTruthy();
    expect(screen.getByText("A second Aesi.")).toBeTruthy();
  });

  it("shows the derived numbers", async () => {
    await open(detail());
    expect(screen.getByTestId("curve")).toBeTruthy();
    expect(screen.getByText(/37 lands · 100 cards/)).toBeTruthy();
    expect(screen.getByTestId("dossier-swaps").textContent).toMatch(/Rhystic Study/);
  });

  it("says outright when nothing was swapped", async () => {
    await open(detail({ swaps: 0, swap_note: "" }));
    expect(screen.queryByTestId("dossier-swaps")).toBeNull();
    expect(screen.getByText(/implemented and tested/)).toBeTruthy();
  });
});

describe("an imported deck, which has none of the editorial half", () => {
  const imported = detail({
    id: "mine",
    name: "Zada Storm",
    source: "moxfield",
    tags: [],
    ratings: null,
    strategy: "",
    signature: [],
    notes: "",
    simplified: 12,
    swaps: 0,
    swap_note: "",
  });

  it("admits it has no ratings rather than drawing empty bars", async () => {
    await open(imported);
    expect(screen.queryByTestId("dossier-ratings")).toBeNull();
    expect(screen.getByTestId("dossier-no-ratings")).toBeTruthy();
  });

  it("admits it has no signature cards", async () => {
    await open(imported);
    expect(screen.getByTestId("dossier-no-signature")).toBeTruthy();
  });

  it("admits it has no write-up and no tags", async () => {
    await open(imported);
    expect(screen.getByText(/whatever you built/)).toBeTruthy();
    expect(screen.getByText(/Untagged/)).toBeTruthy();
  });

  it("still draws the curve, because that is derived and not authored", async () => {
    await open(imported);
    expect(screen.getByTestId("curve")).toBeTruthy();
  });

  it("names how many of its cards are inert", async () => {
    await open(imported);
    expect(screen.getByText(/12 of the imported cards/)).toBeTruthy();
  });
});

describe("crediting the illustrator", () => {
  it("names the artist once the image map has arrived", async () => {
    useUiStore.setState({
      images: {
        aesi_tyrant_of_gyre_strait: {
          card_id: "aesi_tyrant_of_gyre_strait",
          art: "/art/aesi_tyrant_of_gyre_strait.jpg",
          artist: "Viktor Titov",
        },
      },
    });
    await open(detail());
    expect(screen.getByText("Art: Viktor Titov")).toBeTruthy();
  });

  it("says nothing at all rather than 'Art: null' when it does not know", async () => {
    // Two ways of not knowing -- the map has not landed, or this server has no
    // art. Neither is worth a placeholder, and both must not print the word.
    await open(detail());
    expect(screen.queryByText(/^Art:/)).toBeNull();
  });

  it("says nothing when the map has landed but this card has no printing", async () => {
    useUiStore.setState({
      images: { aesi_tyrant_of_gyre_strait: null },
    });
    await open(detail());
    expect(screen.queryByText(/^Art:/)).toBeNull();
  });
});

describe("taking the deck", () => {
  it("offers the button when the dossier came from a seat you may change", async () => {
    await open(detail());
    expect(screen.getByTestId("dossier-take")).toBeTruthy();
  });

  it("offers nothing when it did not", async () => {
    serve(detail());
    draw(
      <DeckDossier
        deckId="aesi"
        canTake={false}
        onTake={() => undefined}
        onClose={() => undefined}
      />,
    );
    await waitFor(() => expect(screen.getByText("Aesi, Tyrant of Gyre Strait")).toBeTruthy());
    expect(screen.queryByTestId("dossier-take")).toBeNull();
  });
});
