/**
 * Fetch the card-art map, once.
 *
 * `/api/images` is static for the life of the server process, so this is a
 * fetch-and-forget: `staleTime: Infinity` and no refetching. It lands in
 * `uiStore` rather than being read out of react-query at each card, because
 * `CardFace` renders bare in unit tests with no `QueryClientProvider` around
 * it, and a card must never depend on one.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { useUiStore } from "./uiStore";

export function useImages(): void {
  const setImages = useUiStore((s) => s.setImages);

  const { data } = useQuery({
    queryKey: ["images"],
    queryFn: api.images,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    // A board with text frames is a working board -- it is what shipped before
    // art existed. Losing this request must never block the game.
    retry: 1,
  });

  useEffect(() => {
    if (data) setImages(data.images);
  }, [data, setImages]);
}
