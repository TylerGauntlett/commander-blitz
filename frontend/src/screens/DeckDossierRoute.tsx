/**
 * One deck, over the catalogue.
 *
 * `canTake` is false here for the same reason `forSeat` is null next door:
 * browsing is not choosing, and there is no chair for this deck to go into.
 */

import { useParams } from "react-router";
import { DeckDossier } from "../components/lobby/DeckDossier";
import { useCloseDossier } from "./DecksRoute";

export function DeckDossierRoute() {
  const deckId = useParams().deckId ?? "";
  const close = useCloseDossier();

  return (
    <DeckDossier deckId={deckId} canTake={false} onTake={() => undefined} onClose={close} />
  );
}
