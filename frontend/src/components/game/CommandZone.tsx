/**
 * The commander, on screen, always.
 *
 * In Commander the command zone is not a side pocket -- it is the card the deck
 * is built around, the one that comes back every time it dies, and the one whose
 * cost climbs every time you cast it. It used to be a `CMD 1` chip on the orb
 * that opened a read-only modal, and the only way to actually cast a commander
 * was a small ghost button in the action bar's overflow. See
 * docs/playtest-feedback-02.md item 7 (Commander Zone).
 *
 * This is a *gesture* surface, exactly like `HandFan`: it carries no
 * `data-action-id`, and clicking routes through the same `playFromHand` path a
 * hand card takes, which resolves targeting and posts the real action. The
 * action bar keeps sole ownership of the id, so the "one button per action"
 * invariant at the top of `Table.tsx` still holds.
 */

import { AnimatePresence, motion } from "motion/react";
import type { CardView, GameView } from "../../api/types";
import { commandersOf } from "../../logic/zoneGrouping";
import { bouncy } from "../../motion/springs";
import { StaticCard } from "./Card";

/** Where a commander is, in the words a player would use. */
function whereabouts(card: CardView): string {
  switch (card.zone) {
    case "command":
      return "Command zone";
    case "battlefield":
      return "On the battlefield";
    case "graveyard":
      return "In the graveyard";
    case "exile":
      return "Exiled";
    default:
      return card.zone;
  }
}

interface Props {
  state: GameView;
  pid: number;
  /** Oids a legal `cast`/`play_land` action names right now. */
  playableOids: ReadonlySet<number>;
  onActivate?: (card: CardView) => void;
  onHover?: (oid: number | null) => void;
  disabled?: boolean;
}

export function CommandZone({
  state,
  pid,
  playableOids,
  onActivate,
  onHover,
  disabled = false,
}: Props) {
  const player = state.players[pid];
  const commanders = commandersOf(state, pid);
  if (commanders.length === 0) return null;

  return (
    <div className="cmdzone" data-testid={`command-zone-${pid}`}>
      <div className="cmdzone__head">
        <span className="cmdzone__label">Commander</span>
      </div>
      <div className="cmdzone__cards">
        <AnimatePresence initial={false}>
          {commanders.map((card) => {
            // Only a commander sitting in the command zone can be cast from it,
            // and only when the server says so -- `playableOids` is built from
            // the legal-action list, never from a guess about mana.
            const castable = card.zone === "command" && playableOids.has(card.oid);
            const tax = player.commander_cost?.[String(card.oid)] ?? 0;

            return (
              <motion.button
                type="button"
                key={card.oid}
                className={castable ? "cmdslot cmdslot--castable" : "cmdslot"}
                data-testid={`commander-${card.oid}`}
                data-castable={castable ? "true" : "false"}
                data-zone={card.zone}
                disabled={disabled || !castable}
                title={
                  castable
                    ? `Cast ${card.name}${tax > 0 ? ` — +${tax} commander tax` : ""}`
                    : `${card.name} — ${whereabouts(card)}`
                }
                onClick={() => onActivate?.(card)}
                onMouseEnter={() => onHover?.(card.oid)}
                onMouseLeave={() => onHover?.(null)}
                whileHover={castable && !disabled ? { y: -4, scale: 1.04 } : undefined}
                whileTap={castable && !disabled ? { scale: 0.97 } : undefined}
                transition={bouncy}
              >
                <StaticCard card={card} variant="board" />
                {/*
                  The tax rides on the card rather than on the orb. It is a
                  property of casting *this* card, and reading it next to the
                  mana cost it modifies is the only place it means anything.
                */}
                {tax > 0 && (
                  <span
                    className="cmdslot__tax"
                    title={`+${tax} generic to cast from the command zone`}
                  >
                    +{tax}
                  </span>
                )}
                {card.zone !== "command" && (
                  <span className="cmdslot__where">{whereabouts(card)}</span>
                )}
              </motion.button>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}
