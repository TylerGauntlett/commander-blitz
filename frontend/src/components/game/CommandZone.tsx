/**
 * The commander, on screen, always -- as a plinth in the player's info panel.
 *
 * In Commander the command zone is not a side pocket: it is the card the deck is
 * built around, the one that comes back every time it dies, and the one whose
 * cost climbs every time you cast it. It used to be a `CMD 1` chip on the orb
 * that opened a read-only modal (docs/playtest-feedback-02.md item 7); then a
 * shrunken card face parked in the bottom-left corner beside the hand, where
 * `--card-w` resolved to ~74px and the name clipped to "Aesi, Tyra…" --
 * docs/mockup-fidelity.md defect #5, the least legible card on the board being
 * the one you cast most often.
 *
 * So this is not a card any more. It is a **plinth**: a cropped portrait in a
 * frame, a name, and a state strip, sized for the 190px column it lives in
 * rather than shrunk to fit it. Nothing legible is lost by not drawing a tiny
 * card face -- hovering already puts the full card in the right-hand preview
 * rail, which is the surface rebuilt to hold it.
 *
 * **State is said three ways, none of them hue.** A word, the art's luminance,
 * and a glyph shape. The green "you can play this" rim carries its whole meaning
 * in colour, which is docs/mockup-fidelity.md's top-ranked open defect; this
 * element is not allowed to add to that pile, so a player who cannot use colour
 * still reads "READY" and sees a lit portrait against a dim one.
 *
 * This is a *gesture* surface, exactly like `HandFan`: it carries no
 * `data-action-id`, and clicking routes through the same `playFromHand` path a
 * hand card takes, which resolves targeting and posts the real action. The
 * action panel keeps sole ownership of the id, so the "one button per action"
 * invariant at the top of `Table.tsx` still holds. `e2e/cycle3.spec.ts` and
 * `e2e/action-panel.spec.ts` both assert it.
 */

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { CardView, GameView } from "../../api/types";
import { artUrl } from "../../logic/cardArt";
import { manaPips } from "../../logic/cardStyle";
import { commandersOf } from "../../logic/zoneGrouping";
import { bouncy } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";

/**
 * What the plinth says about where the commander is and whether you can do
 * anything about it.
 *
 * `word` and `glyph` are the two channels that survive greyscale; the class
 * carries the third (how brightly the portrait is lit). Every state sets all
 * three, which is the whole point -- see the note at the top of the file.
 */
interface CommanderState {
  key: string;
  word: string;
  glyph: string;
}

function commanderState(card: CardView, castable: boolean): CommanderState {
  if (castable) return { key: "ready", word: "Ready", glyph: "▶" };
  switch (card.zone) {
    case "command":
      return { key: "waiting", word: "In command", glyph: "·" };
    // Mid-cast the card is on the stack and in no other zone. It is on its way
    // to the battlefield and saying so beats blinking to "In command" for the
    // one beat the player is actually watching.
    case "stack":
      return { key: "deployed", word: "On the stack", glyph: "✦" };
    case "battlefield":
      return { key: "deployed", word: "On the battlefield", glyph: "✦" };
    case "graveyard":
      return { key: "fallen", word: "In the graveyard", glyph: "✕" };
    case "exile":
      return { key: "fallen", word: "Exiled", glyph: "✕" };
    default:
      return { key: "waiting", word: card.zone, glyph: "·" };
  }
}

interface PlinthProps {
  card: CardView;
  castable: boolean;
  /** Extra generic owed to cast from the command zone; already doubled. */
  tax: number;
  compact: boolean;
  disabled: boolean;
  onActivate?: (card: CardView) => void;
  onHover?: (oid: number | null) => void;
}

function Plinth({ card, castable, tax, compact, disabled, onActivate, onHover }: PlinthProps) {
  const images = useUiStore((s) => s.images);
  const [broken, setBroken] = useState(false);
  // Three states, and the last two differ: `undefined` means the image map has
  // not arrived, and drawing the "no art" plate there would flash a hatched
  // placeholder on every first paint. See logic/cardArt.ts.
  const art = artUrl(images, card.card_id);
  const showArt = art !== undefined && art !== null && !broken;

  const state = commanderState(card, castable);
  // A cost means something only where you could pay it. The surcharge goes with
  // it rather than outliving it: a bare "+2" beside a commander already on the
  // stack is a number with nothing to modify.
  const showCost = card.zone === "command" && !compact;
  const pips = showCost ? manaPips(card.mana_cost) : [];

  return (
    <motion.button
      type="button"
      className={`cmdslot cmdslot--${state.key}`}
      data-testid={`commander-${card.oid}`}
      data-castable={castable ? "true" : "false"}
      data-zone={card.zone}
      data-cmd-state={state.key}
      disabled={disabled || !castable}
      title={
        castable
          ? `Cast ${card.name}${tax > 0 ? ` — +${tax} commander tax` : ""}`
          : `${card.name} — ${state.word}`
      }
      onClick={() => onActivate?.(card)}
      onMouseEnter={() => onHover?.(card.oid)}
      onMouseLeave={() => onHover?.(null)}
      whileHover={castable && !disabled ? { y: -3, scale: 1.03 } : undefined}
      whileTap={castable && !disabled ? { scale: 0.98 } : undefined}
      transition={bouncy}
    >
      {art !== undefined && (
        <span
          className={showArt ? "cmdplinth__art" : "cmdplinth__art cmdplinth__art--none"}
          data-art={showArt ? "ready" : "none"}
        >
          {showArt ? (
            // A 404 is a real case: art outside the shipped pool is fetched
            // lazily and a fetch can fail. Fall back to the plate rather than
            // to the browser's broken-image glyph.
            <img src={art} alt="" loading="lazy" onError={() => setBroken(true)} />
          ) : (
            <span>no art</span>
          )}
        </span>
      )}

      {/*
        What this portrait is, pinned over its own corner rather than given a
        row of its own. The eyebrow it replaces cost 22px of a column that has
        to fit an orb, a mana row and five piles into the height of one mat --
        and at 1600x950 that was 22px the piles did not have.
      */}
      {!compact && (
        <span className="cmdplinth__tag" title="Commander">
          CMD
        </span>
      )}

      <span className="cmdplinth__name">{card.name}</span>

      {/*
        State on the left, cost on the right, one row.

        They never compete for the width: the cost only exists in the command
        zone, where the word is "Ready" or "In command", and the long words
        ("On the battlefield") only happen once the cost has stopped being
        information. Two rows here cost 16px of a column that did not have it.

        The cost lands directly above the orb's mana row, which is the reason
        the commander moved into this panel at all -- what you owe and what you
        have are now one glance apart instead of at opposite corners.

        `commander_cost` is the extra generic already doubled by the engine, not
        `commander_tax` -- that one counts prior casts. Two fields, one of them
        a trap; see the contract note in api/types.ts.
      */}
      <span className="cmdplinth__strip">
        <span className="cmdplinth__glyph" aria-hidden="true">
          {state.glyph}
        </span>
        <span className="cmdplinth__word">{state.word}</span>
        {showCost && (pips.length > 0 || tax > 0) && (
          <span className="cmdplinth__cost">
            {pips.map((pip) => (
              <span className={`pip pip--${pip.tone}`} key={pip.key}>
                {pip.symbol}
              </span>
            ))}
            {tax > 0 && (
              <span
                className="cmdslot__tax"
                title={`+${tax} generic to cast from the command zone`}
              >
                +{tax}
              </span>
            )}
          </span>
        )}
      </span>
    </motion.button>
  );
}

interface Props {
  state: GameView;
  pid: number;
  /** Oids a legal `cast`/`play_land` action names right now. */
  playableOids: ReadonlySet<number>;
  /** An opponent's plinth: reference only, and sized to a 112px column. */
  compact?: boolean;
  onActivate?: (card: CardView) => void;
  onHover?: (oid: number | null) => void;
  disabled?: boolean;
}

export function CommandZone({
  state,
  pid,
  playableOids,
  compact = false,
  onActivate,
  onHover,
  disabled = false,
}: Props) {
  const player = state.players[pid];
  const commanders = commandersOf(state, pid);
  if (commanders.length === 0) return null;

  return (
    <div className="cmdzone" data-testid={`command-zone-${pid}`}>
      <div className="cmdzone__cards">
        <AnimatePresence initial={false}>
          {commanders.map((card) => (
            <Plinth
              key={card.oid}
              card={card}
              // Only a commander sitting in the command zone can be cast from
              // it, and only when the server says so -- `playableOids` is built
              // from the legal-action list, never from a guess about mana.
              castable={card.zone === "command" && playableOids.has(card.oid)}
              tax={player.commander_cost?.[String(card.oid)] ?? 0}
              compact={compact}
              disabled={disabled}
              onActivate={onActivate}
              onHover={onHover}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
