/** One player's board: their zones, life, and hidden-zone chips. */

import type { CardView, GameView } from "../api/types";
import { LANES, groupBattlefield } from "../logic/zoneGrouping";
import { useUiStore } from "../state/uiStore";
import { ZoneLane } from "./ZoneLane";

interface Props {
  state: GameView;
  pid: number;
  isViewer: boolean;
  activeLanes: Set<string>;
  targetableOids: Set<number>;
  stagedOids: Set<number>;
  onCardClick?: (card: CardView) => void;
}

export function PlayerMat({
  state,
  pid,
  isViewer,
  activeLanes,
  targetableOids,
  stagedOids,
  onCardClick,
}: Props) {
  const lanes = groupBattlefield(state, pid);
  const player = state.players[pid];
  const peek = useUiStore((s) => s.peek);

  const commanderDamage = Object.entries(player.commander_damage_taken)
    .filter(([, amount]) => amount > 0)
    .map(([from, amount]) => `${state.players[Number(from)].name}: ${amount}`);

  return (
    <section
      className={[
        "player-mat",
        isViewer ? "player-mat--viewer" : "player-mat--opponent",
        player.has_lost ? "player-mat--out" : "",
        state.active_player === pid ? "player-mat--active" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="player-mat__header">
        <span className="player-mat__name">{player.name}</span>
        <span className="player-mat__life" title="Life total">
          {player.has_lost ? "OUT" : player.life}
        </span>
        <span className="player-mat__deck">{player.deck_id}</span>
        <div className="player-mat__zones">
          <button type="button" className="zone-chip" onClick={() => peek(pid, "hand")}>
            Hand {player.hand_count}
          </button>
          <span className="zone-chip zone-chip--static">Library {player.library_count}</span>
          <button type="button" className="zone-chip" onClick={() => peek(pid, "graveyard")}>
            GY {player.graveyard.length}
          </button>
          <button type="button" className="zone-chip" onClick={() => peek(pid, "exile")}>
            Exile {player.exile.length}
          </button>
          <button type="button" className="zone-chip" onClick={() => peek(pid, "command")}>
            CMD {player.command.length}
          </button>
        </div>
        {commanderDamage.length > 0 && (
          <span className="player-mat__cmd-damage" title="Commander damage taken">
            {commanderDamage.join(" | ")}
          </span>
        )}
      </header>

      <div className="player-mat__lanes">
        {LANES.map((lane) => (
          <ZoneLane
            key={lane}
            lane={lane}
            pid={pid}
            cards={lanes[lane]}
            active={activeLanes.has(`${pid}:${lane}`)}
            compact={!isViewer}
            targetableOids={targetableOids}
            stagedOids={stagedOids}
            onCardClick={onCardClick}
          />
        ))}
      </div>
    </section>
  );
}
