/**
 * The front door.
 *
 * `?join=CODE` still prefills the field, unchanged: it is what an old invite
 * link carries, and it is also where a `/pods/CODE` link lands when it arrives
 * on a machine that holds no token for that pod. Read from the URL rather than
 * from a boot-time snapshot, but still only as the field's *initial* value --
 * see `HomeScreen`, which will not fight somebody who has started typing.
 *
 * Two more things the URL can say, both from the desktop build:
 *
 * `?from=desktop` means the Steam Deck app sent this visitor to the hosted
 * site to play with friends, and `?import=a,b` names the Moxfield decks they
 * imported at home. A pod only seats decks the server it runs on already has,
 * so the site imports those first and then shows the door -- with the code in
 * the field if there was one. That is the *handoff*, and it is the whole of
 * what makes a deck follow its owner online.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { ApiError, api, setPlayerToken } from "../api/client";
import { HomeScreen } from "../components/lobby/HomeScreen";
import { Screen } from "../components/screen/Screen";
import { bridge } from "../desktop/bridge";
import { handoffImports, isHandoff, moxfieldUrl, onlineUrl } from "../logic/desktop";
import { gamePath, joinPath, podPath } from "../logic/routes";
import { useAppConfig } from "../state/useAppConfig";
import { useDecks } from "../state/useGame";
import { adoptPod, storedToken, useCreatePod, useJoinPod } from "../state/usePod";
import { linkGame } from "../state/usePodSession";

export function HomeRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const decks = useDecks();
  const createPod = useCreatePod();
  const joinPod = useJoinPod();
  const config = useAppConfig();

  // `adoptPod` before navigating, not after: the token has to be in storage
  // before `PodRoute` renders, because that is where it reads it back from --
  // and it has to be armed before the lobby's first poll leaves the browser.
  //
  // No name: the door does not ask for one and the server names the chair after
  // its seat. You say who you are from the plate, once there is a table for it
  // to mean anything to.
  const create = () => {
    createPod.mutate(
      {},
      {
        onSuccess: (made) => {
          adoptPod(made.pod.code, made.player_token);
          navigate(podPath(made.pod.code));
        },
      },
    );
  };

  const join = (code: string) => {
    joinPod.mutate(
      { code },
      {
        onSuccess: (joined) => {
          adoptPod(joined.pod.code, joined.player_token);
          navigate(podPath(joined.pod.code));
        },
        onError: (caught) => {
          // A pod that already dealt is not a failure to show, it is somebody
          // who should be at the table. The server puts the game id in the
          // error detail for exactly this.
          if (caught instanceof ApiError && caught.code === "already_started") {
            const found = caught.detail?.game_id;
            const stored = storedToken(code);
            if (typeof found === "string" && stored) {
              setPlayerToken(stored);
              linkGame(found, code);
              navigate(gamePath(found), { replace: true });
            }
          }
        },
      },
    );
  };

  /*
   * The desktop's way to a pod with friends: hand the window to the site.
   *
   * The imported decks' Moxfield ids ride along so the site can import them
   * too. Through the shell when there is one, so it can bring the window back
   * afterwards; a plain navigation otherwise, which is what a browser tab
   * pointed at a desktop server would want anyway.
   */
  const playOnline = (code?: string) => {
    const importIds = (decks.data ?? [])
      .filter((deck) => deck.source === "moxfield" && deck.source_id)
      .map((deck) => deck.source_id as string);
    const url = onlineUrl(config.remote_origin, { join: code, importIds });
    const shell = bridge();
    if (shell) void shell.openOnline(url);
    else window.location.assign(url);
  };

  const handoff = useHandoff(
    params,
    decks.data?.map((deck) => deck.id),
  );

  // Not `center`: `.screen--center` adds 24px of padding, which would put the
  // door's `--du` at 0.94 on a Deck and every number the mockup round measured
  // out by six percent. The door fills the screen itself.
  if (handoff) {
    return (
      <Screen center>
        <p className="door__p" data-testid="handoff-import" role="status">
          Bringing your decks over…
        </p>
      </Screen>
    );
  }
  return (
    <Screen>
      <HomeScreen
        initialCode={params.get("join") ?? ""}
        deckCount={decks.data?.length ?? 0}
        onCreate={create}
        onJoin={join}
        busy={createPod.isPending || joinPod.isPending}
        error={
          (createPod.error as Error | null) ??
          (joinPod.error as Error | null) ??
          (decks.error as Error | null)
        }
        mode={config.mode}
        online={config.online}
        onPlayOnline={playOnline}
        onReturnLocal={
          config.mode === "hosted" && bridge() ? () => void bridge()?.returnLocal() : undefined
        }
      />
    </Screen>
  );
}

/**
 * The hosted end of the handoff: import what the desktop sent, then settle.
 *
 * Returns true while it is working. Imports run one at a time -- the server
 * reloads its registry after each, and two at once would race that -- and a
 * failure is logged and skipped rather than shown: the player came here to
 * play, and a deck that could not be brought is a deck they can import by hand
 * from the lobby like anybody else. Decks already on this server are skipped
 * without a request, which is what makes coming back a second time free.
 *
 * Ends by replacing the address: the handoff is a redirect, not a place.
 */
function useHandoff(params: URLSearchParams, present: readonly string[] | undefined): boolean {
  const navigate = useNavigate();
  const search = params.toString() ? `?${params.toString()}` : "";
  const wanted = isHandoff(search);
  const [working, setWorking] = useState(wanted);
  const started = useRef(false);

  useEffect(() => {
    if (!wanted || started.current || present === undefined) return;
    started.current = true;
    const join = params.get("join");
    const ids = handoffImports(search).filter(
      (id) => !present.includes(`mox_${id.toLowerCase()}`),
    );
    let cancelled = false;
    (async () => {
      for (const id of ids) {
        try {
          await api.importDeck(moxfieldUrl(id));
        } catch (caught) {
          console.warn(`handoff: could not import ${id}`, caught);
        }
        if (cancelled) return;
      }
      setWorking(false);
      navigate(join ? joinPath(join) : "/", { replace: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [wanted, present, params, search, navigate]);

  return working;
}
