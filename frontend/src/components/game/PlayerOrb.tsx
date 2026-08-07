/**
 * A player: life, commander damage, and the zones you can look into.
 *
 * The life total is the thing the eye goes to, so it is a real counter that
 * reacts -- it pops and flashes on every change, in the direction of the
 * change. `data-player` marks it as an anchor for floating damage numerals.
 */

import { motion, useAnimationControls } from "motion/react";
import { useEffect, useRef } from "react";
import type { PlayerView } from "../../api/types";
import { lossReason } from "../../logic/labels";
import { formatManaRow, manaRow } from "../../logic/mana";
import { bouncy } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";

/** Commander damage becomes lethal here; warn well before it does. */
const COMMANDER_LETHAL = 21;

interface Props {
  player: PlayerView;
  isViewer: boolean;
  isActive: boolean;
  hasPriority: boolean;
  /** Names by pid, for the commander-damage tooltips. */
  names: string[];
  compact?: boolean;
  /** A legal action could point at this player: attack target, spell target. */
  targetable?: boolean;
  onSelect?: (pid: number) => void;
}

export function PlayerOrb({
  player,
  isViewer,
  isActive,
  hasPriority,
  names,
  compact = false,
  targetable = false,
  onSelect,
}: Props) {
  const setPeek = useUiStore((s) => s.setPeek);
  const controls = useAnimationControls();
  const previous = useRef(player.life);

  useEffect(() => {
    const before = previous.current;
    previous.current = player.life;
    if (before === player.life) return;
    const grew = player.life > before;
    controls.start({
      scale: [1, grew ? 1.28 : 1.34, 1],
      color: ["var(--text)", grew ? "var(--gain)" : "var(--danger)", "var(--text)"],
      transition: { duration: 0.5, times: [0, 0.25, 1] },
    });
  }, [player.life, controls]);

  const commanderDamage = Object.entries(player.commander_damage_taken).filter(
    ([, amount]) => amount > 0,
  );

  const pips = manaRow(player.mana);
  // Only surface tax that is actually owed. A commander cast for the first time
  // costs nothing extra, and a zero chip is noise on every orb all game.
  const commanderTax = Object.entries(player.commander_cost ?? {}).filter(
    ([, extra]) => extra > 0,
  );

  const classes = [
    "orb",
    compact ? "orb--compact" : "",
    isViewer ? "orb--viewer" : "",
    isActive ? "orb--active" : "",
    player.has_lost ? "orb--out" : "",
    targetable ? "orb--targetable" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.div
      className={classes}
      data-player={player.pid}
      data-testid={`player-${player.pid}`}
      layout
      transition={bouncy}
      onClick={onSelect ? () => onSelect(player.pid) : undefined}
      whileHover={targetable ? { scale: 1.04 } : undefined}
    >
      <div className="orb__head">
        <span className="orb__name">{player.name}</span>
        {hasPriority && <span className="orb__priority" title="Has priority" />}
      </div>

      <div className="orb__life-row">
        <motion.span
          className="orb__life tabular"
          animate={controls}
          data-testid={`life-${player.pid}`}
        >
          {player.has_lost ? "OUT" : player.life}
        </motion.span>
        {player.has_lost && <span className="orb__loss">{lossReason(player.loss_reason)}</span>}
      </div>

      {commanderDamage.length > 0 && (
        <div className="orb__cmd" title="Commander damage taken">
          {commanderDamage.map(([source, amount]) => (
            <span
              key={source}
              className={amount >= COMMANDER_LETHAL - 6 ? "cmd-pip cmd-pip--warn" : "cmd-pip"}
              title={`${amount} from ${names[Number(source)] ?? `P${source}`}`}
            >
              {amount}
            </span>
          ))}
        </div>
      )}

      {/*
        Available mana. The server sends it, nothing rendered it, and lands
        tapped during auto-payment with no indication of what was spent -- so
        the player had no running sense of what they could afford.

        An ambiguous source ("Add {G} or {U}") is one split pip, not two solid
        ones: two solid pips would claim a mana that does not exist.
      */}
      {pips.length > 0 && (
        <div
          className="orb__mana"
          data-testid={`mana-${player.pid}`}
          data-mana={formatManaRow(pips)}
          title={`${pips.length} available: ${formatManaRow(pips)}`}
        >
          {pips.map((pip) => (
            <span
              key={pip.key}
              className={`mana-pip mana-pip--${pip.tone}${
                pip.floating ? " mana-pip--floating" : ""
              }`}
              title={
                pip.symbols.length > 1
                  ? `Either ${pip.symbols.join(" or ")}`
                  : pip.floating
                    ? `${pip.symbols[0]} in pool`
                    : pip.symbols[0]
              }
            />
          ))}
        </div>
      )}

      {commanderTax.length > 0 && (
        <div className="orb__tax" data-testid={`tax-${player.pid}`}>
          {commanderTax.map(([oid, extra]) => (
            <span
              key={oid}
              className="tax-chip"
              title={`Commander tax: +${extra} generic to cast from the command zone`}
            >
              CMD +{extra}
            </span>
          ))}
        </div>
      )}

      <div className="orb__zones">
        <span className="zone-chip zone-chip--static" title="Cards in library">
          Lib {player.library_count}
        </span>
        <button
          type="button"
          className="zone-chip"
          onClick={() => setPeek({ pid: player.pid, zone: "hand" })}
          title={isViewer ? "Your hand" : "Hidden"}
        >
          Hand {player.hand_count}
        </button>
        <button
          type="button"
          className="zone-chip"
          onClick={() => setPeek({ pid: player.pid, zone: "graveyard" })}
        >
          GY {player.graveyard.length}
        </button>
        {player.exile.length > 0 && (
          <button
            type="button"
            className="zone-chip"
            onClick={() => setPeek({ pid: player.pid, zone: "exile" })}
          >
            Exile {player.exile.length}
          </button>
        )}
        <button
          type="button"
          className="zone-chip zone-chip--cmd"
          onClick={() => setPeek({ pid: player.pid, zone: "command" })}
          title="Command zone"
        >
          CMD {player.command.length}
        </button>
      </div>
    </motion.div>
  );
}
