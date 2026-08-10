/**
 * The front door.
 *
 * `?join=CODE` still prefills the field, unchanged: it is what an old invite
 * link carries, and it is also where a `/pods/CODE` link lands when it arrives
 * on a machine that holds no token for that pod. Read from the URL rather than
 * from a boot-time snapshot, but still only as the field's *initial* value --
 * see `HomeScreen`, which will not fight somebody who has started typing.
 */

import { useNavigate, useSearchParams } from "react-router";
import { ApiError, setPlayerToken } from "../api/client";
import { HomeScreen } from "../components/lobby/HomeScreen";
import { Screen } from "../components/screen/Screen";
import { gamePath, podPath } from "../logic/routes";
import { useDecks } from "../state/useGame";
import { adoptPod, storedToken, useCreatePod, useJoinPod } from "../state/usePod";
import { linkGame } from "../state/usePodSession";

export function HomeRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const decks = useDecks();
  const createPod = useCreatePod();
  const joinPod = useJoinPod();

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

  return (
    <Screen center>
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
        onBrowse={() => navigate("/decks")}
      />
    </Screen>
  );
}
