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
import { useEffect } from "react";
import { Route, Routes, useLocation, useMatch } from "react-router";
import { UpdateBanner } from "./components/ui/UpdateBanner";
import { startInputMode } from "./input/inputMode";
import { isCompact } from "./logic/breakpoints";
import { screenKey, titleFor } from "./logic/routes";
import { DeckDossierRoute } from "./screens/DeckDossierRoute";
import { DecksRoute } from "./screens/DecksRoute";
import { GameRoute } from "./screens/GameRoute";
import { HomeRoute } from "./screens/HomeRoute";
import { NotFound } from "./screens/NotFound";
import { PodRoute } from "./screens/PodRoute";
import { AppConfigProvider } from "./state/useAppConfig";
import { useLayoutByQuery } from "./state/useHandheld";
import { useImages } from "./state/useImages";

export function App() {
  const location = useLocation();

  // Commander art has to be on screen in the lobby, before there is a game to
  // scope the map to. Unscoped on the way in, scoped once there is a game -- an
  // unscoped map grows with every imported deck and a board only ever draws its
  // own ~90 cards. The URL is now what says whether there is one.
  useImages(useMatch("/games/:gameId")?.params.gameId);

  // The tab, and with it the back-button menu and anything somebody bookmarks.
  // A single-page app keeps whatever title `index.html` shipped with unless it
  // says otherwise, so four tabs on four pods would all read the same thing.
  // Effect rather than render: `document.title` is outside React's tree.
  useEffect(() => {
    document.title = titleFor(location.pathname);
  }, [location.pathname]);

  /*
   * Which controls the game draws, watched for the whole session.
   *
   * App-wide rather than per-screen, and app-wide from the first paint: the
   * home screen and the lobby have buttons too, and a player arriving with a
   * controller should see its glyphs on the front door rather than only once
   * they reach a table.
   *
   * It writes `data-input` and `data-pad` onto `<html>` and nothing else --
   * every glyph in the app is shown or hidden by CSS reading those, so moving
   * a mouse costs no React work at all. See `input/inputMode.ts`.
   */
  useEffect(() => {
    startInputMode();
  }, []);

  /*
   * ...and which layout the viewport wants, on the same element.
   *
   * It started on `.table`, which meant the front door, the pod lobby and the
   * deck catalogue never saw it -- so the 16px floor applied to the board and
   * nowhere else, and the lobby was still drawing 9px text. The layout is a
   * property of the environment, not of one component, and it belongs beside
   * `data-input` on the root where every stylesheet can see it.
   */
  const layout = useLayoutByQuery();
  useEffect(() => {
    const root = document.documentElement;
    // One mode of three (ADR 0025), and the compact family the handheld and the
    // phone share. `styles/handheld.css` keys structure on the second and
    // `styles/phone.css` keys the phone's own rules on the first.
    root.setAttribute("data-layout", layout);
    root.toggleAttribute("data-compact", isCompact(layout));
  }, [layout]);

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
  // `AppConfigProvider` outside the screens: which server this is -- the
  // desktop sidecar or the site -- is something the door, the catalogue and
  // the lobby all ask, and none of them should fetch it twice.
  return (
    <AppConfigProvider>
      {/* Above the screens, so the desktop's "update ready" outlives any one
          of them. It renders nothing on the site. */}
      <UpdateBanner />
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
    </AppConfigProvider>
  );
}
