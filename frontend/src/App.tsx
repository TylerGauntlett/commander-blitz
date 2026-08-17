/**
 * The screens, and the addresses they live at.
 *
 * This file used to hold a `useState<Route>` discriminated union and an argument
 * for why a router was the wrong tool:
 *
 * > A router would buy back-button navigation between a lobby and a game that
 * > are both *server* state -- going "back" to a pod that has already dealt is
 * > not a thing that can work, and a URL that pretends otherwise is worse than
 * > no URL.
 *
 * The observation was right and the conclusion was wrong. A dead lobby is not
 * something URLs make possible, it is something *pushing a history entry* makes
 * possible -- so the deal replaces its entry rather than pushing one, and the
 * room that no longer exists stops being somewhere you can go back to. What the
 * argument gave up in exchange was everything else: sharing a pod meant
 * smuggling a code through `?join=`, and a refresh at the table dropped you at
 * the front door mid-game.
 *
 * Paths are shaped like the API resources behind them -- `/pods/:code` beside
 * `/api/pods/{code}` -- so there is one naming rule here rather than two that
 * disagree by an `s`. The route components live in `screens/`; `logic/routes.ts`
 * holds the only decision in this file that is not "match a path".
 */

import { AnimatePresence, MotionConfig } from "motion/react";
import { Route, Routes, useLocation, useMatch } from "react-router";
import { screenKey } from "./logic/routes";
import { DeckDossierRoute } from "./screens/DeckDossierRoute";
import { DecksRoute } from "./screens/DecksRoute";
import { GameRoute } from "./screens/GameRoute";
import { HomeRoute } from "./screens/HomeRoute";
import { NotFound } from "./screens/NotFound";
import { PodRoute } from "./screens/PodRoute";
import { useImages } from "./state/useImages";

export function App() {
  const location = useLocation();

  // Commander art has to be on screen in the lobby, before there is a game to
  // scope the map to. Unscoped on the way in, scoped once there is a game -- an
  // unscoped map grows with every imported deck and a board only ever draws its
  // own ~90 cards. The URL is now what says whether there is one.
  useImages(useMatch("/games/:gameId")?.params.gameId);

  // `location` is passed explicitly so the *exiting* screen keeps matching
  // against the address it was rendered for. Without it the outgoing route
  // re-matches the new URL mid-fade, loses its params, and blanks out on its
  // way off screen.
  /*
   * `reducedMotion="user"` rather than Motion's default of `"never"`.
   *
   * The board now throws sparks, knocks cards backwards and kicks the screen,
   * and a player who has asked their system for reduced motion should get none
   * of it. `fx/reducedMotion.ts` is the same decision for the effects that are
   * not Framer animations -- particles and actuators run on a raw frame loop
   * and cannot see this context.
   *
   * What survives either way is everything that carries meaning: numerals,
   * captions, the log, the ring flashes. "How it felt" goes; "what happened"
   * stays.
   */
  return (
    <MotionConfig reducedMotion="user">
      <AnimatePresence mode="wait">
        <Routes location={location} key={screenKey(location.pathname)}>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/pods/:code" element={<PodRoute />} />
          <Route path="/games/:gameId" element={<GameRoute />} />
          <Route path="/decks" element={<DecksRoute />}>
            <Route path=":deckId" element={<DeckDossierRoute />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AnimatePresence>
    </MotionConfig>
  );
}
