/**
 * Combat declaration.
 *
 * Attackers and blockers are staged locally and submitted in one POST; the
 * server loops the engine's incremental declaration. That keeps the familiar
 * "select everything, then confirm" flow while the engine still validates each
 * step individually.
 */

import type { GameView, LegalAction } from "../api/types";
import { availableAttackers, blockActions, defendersFor } from "../logic/actionMatch";
import { useUiStore } from "../state/uiStore";

interface Props {
  state: GameView;
  actions: LegalAction[];
  busy: boolean;
  onConfirm: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
  onSkip: (action: LegalAction) => void;
}

export function CombatOverlay({ state, actions, busy, onConfirm, onSkip }: Props) {
  const pending = state.pending;
  const staged = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const unstageAttack = useUiStore((s) => s.unstageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const unstageBlock = useUiStore((s) => s.unstageBlock);

  if (!pending || pending.player !== state.seat) return null;
  const name = (oid: number) =>
    state.battlefield.find((card) => card.oid === oid)?.name ?? `#${oid}`;

  if (pending.kind === "declare_attackers") {
    const attackers = availableAttackers(actions);
    const pairs = Object.entries(staged).map(
      ([attacker, defender]) => [Number(attacker), defender] as [number, number],
    );
    return (
      <div className="combat-overlay">
        <div className="combat-overlay__title">Declare attackers</div>
        <div className="combat-overlay__rows">
          {attackers.map((oid) => {
            const defenders = defendersFor(actions, oid);
            const chosen = staged[oid];
            return (
              <div className="combat-row" key={oid}>
                <span className="combat-row__name">{name(oid)}</span>
                {defenders.map((pid) => (
                  <button
                    type="button"
                    key={pid}
                    className={chosen === pid ? "chip chip--selected" : "chip"}
                    onClick={() =>
                      chosen === pid ? unstageAttack(oid) : stageAttack(oid, pid)
                    }
                  >
                    {state.players[pid].name}
                  </button>
                ))}
              </div>
            );
          })}
          {attackers.length === 0 && (
            <span className="combat-overlay__none">No creature can attack.</span>
          )}
        </div>
        <div className="combat-overlay__buttons">
          <button
            type="button"
            className="action-button"
            disabled={busy || pairs.length === 0}
            onClick={() => onConfirm("attackers", pairs)}
          >
            Attack with {pairs.length}
          </button>
          <SkipButton actions={actions} busy={busy} onSkip={onSkip} label="No attacks" />
        </div>
      </div>
    );
  }

  if (pending.kind === "declare_blockers") {
    const blocks = blockActions(actions);
    const byBlocker = new Map<number, number[]>();
    for (const action of blocks) {
      if (action.source_oid === null) continue;
      const list = byBlocker.get(action.source_oid) ?? [];
      for (const ref of action.targets) {
        if (ref.kind === "object") list.push(ref.id);
      }
      byBlocker.set(action.source_oid, list);
    }
    const pairs = Object.entries(stagedBlocks).map(
      ([blocker, attacker]) => [Number(blocker), attacker] as [number, number],
    );
    return (
      <div className="combat-overlay">
        <div className="combat-overlay__title">Declare blockers</div>
        <div className="combat-overlay__rows">
          {[...byBlocker.entries()].map(([blocker, attackers]) => (
            <div className="combat-row" key={blocker}>
              <span className="combat-row__name">{name(blocker)}</span>
              {attackers.map((attacker) => (
                <button
                  type="button"
                  key={attacker}
                  className={
                    stagedBlocks[blocker] === attacker ? "chip chip--selected" : "chip"
                  }
                  onClick={() =>
                    stagedBlocks[blocker] === attacker
                      ? unstageBlock(blocker)
                      : stageBlock(blocker, attacker)
                  }
                >
                  blocks {name(attacker)}
                </button>
              ))}
            </div>
          ))}
          {byBlocker.size === 0 && (
            <span className="combat-overlay__none">Nothing can block.</span>
          )}
        </div>
        <div className="combat-overlay__buttons">
          <button
            type="button"
            className="action-button"
            disabled={busy}
            onClick={() => onConfirm("blockers", pairs)}
          >
            Confirm {pairs.length} block{pairs.length === 1 ? "" : "s"}
          </button>
          <SkipButton actions={actions} busy={busy} onSkip={onSkip} label="No blocks" />
        </div>
      </div>
    );
  }

  return null;
}

function SkipButton({
  actions,
  busy,
  onSkip,
  label,
}: {
  actions: LegalAction[];
  busy: boolean;
  onSkip: (action: LegalAction) => void;
  label: string;
}) {
  const done = actions.find((action) => action.kind === "finish_declaration");
  if (!done) return null;
  return (
    <button type="button" className="ghost-button" disabled={busy} onClick={() => onSkip(done)}>
      {label}
    </button>
  );
}
