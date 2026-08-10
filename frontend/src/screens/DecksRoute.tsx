/**
 * The catalogue, browsing for nobody.
 *
 * The same `DeckCatalog` the lobby opens, with `forSeat` null -- the component
 * was already parameterised for this, so there is nothing to fork. What changes
 * is only where the answers go: in the lobby a pick takes a deck for a seat, and
 * here it opens the dossier, because there is no seat to take it for.
 *
 * The dossier is a nested route rendering into the `<Outlet/>` below rather than
 * a screen of its own. That is what keeps the catalogue mounted underneath it,
 * so opening a deck does not throw away the filters somebody just set -- the
 * same reason `screenKey` gives both paths one key.
 */

import { Outlet, useLocation, useNavigate } from "react-router";
import { DeckCatalog } from "../components/lobby/DeckCatalog";
import { Screen } from "../components/screen/Screen";
import { deckPath } from "../logic/routes";
import { useDecks } from "../state/useGame";

export function DecksRoute() {
  const navigate = useNavigate();
  const decks = useDecks();

  return (
    <Screen variant="fade">
      <DeckCatalog
        decks={decks.data ?? []}
        forSeat={null}
        forWhom="Browsing the catalogue"
        chosen={null}
        onPick={(deckId) => navigate(deckPath(deckId))}
        onDossier={(deckId) => navigate(deckPath(deckId))}
        onClose={() => navigate("/")}
        onImported={() => decks.refetch()}
      />
      <Outlet />
    </Screen>
  );
}

/**
 * Closing a dossier undoes the push that opened it, so the browser's back button
 * and the ✕ do the same thing. A dossier somebody deep-linked to has no such
 * push to undo -- `location.key` is `"default"` only on the first entry of a
 * session -- so it falls back to the catalogue it is sitting on top of.
 */
export function useCloseDossier(): () => void {
  const navigate = useNavigate();
  const location = useLocation();
  return () => {
    if (location.key !== "default") navigate(-1);
    else navigate("/decks", { replace: true });
  };
}
