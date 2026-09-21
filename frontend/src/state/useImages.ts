/**
 * Fetch the card-art map, once per game.
 *
 * `/api/images` is static for the life of the server process, so this is a
 * fetch-and-forget: `staleTime: Infinity` and no refetching. It lands in
 * `uiStore` rather than being read out of react-query at each card, because
 * `CardFace` renders bare in unit tests with no `QueryClientProvider` around
 * it, and a card must never depend on one.
 *
 * Scoped to a game once there is one -- which is also what makes the per-seat
 * layer possible at all: only a game says which deck sits at which seat.
 *
 * Scoped to a game once there is one. Unscoped, the response carries every card
 * the server knows, and deck import means that is no longer a couple of hundred
 * -- a machine with twenty imported decks would send thousands of entries to
 * draw a board that holds about ninety. Before a game exists there is nothing to
 * scope by, so the menu asks for the whole map and the game replaces it.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { useUiStore } from "./uiStore";

export function useImages(gameId?: string): void {
  const setImages = useUiStore((s) => s.setImages);

  const { data } = useQuery({
    queryKey: ["images", gameId ?? null],
    queryFn: () => api.images(gameId),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    // A board with text frames is a working board -- it is what shipped before
    // art existed. Losing this request must never block the game.
    retry: 1,
  });

  useEffect(() => {
    if (data) setImages(data.images, data.seats ?? null);
  }, [data, setImages]);
}
