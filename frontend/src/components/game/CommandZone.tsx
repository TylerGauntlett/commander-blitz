/**
 * The commander, on screen, always -- as a plinth in the player's info panel.
 *
 * In Commander the command zone is not a side pocket: it is the card the deck is
 * built around, the one that comes back every time it dies, and the one whose
 * cost climbs every time you cast it. It used to be a `CMD 1` chip on the orb
 * that opened a read-only modal (docs/playtest-feedback-02.md item 7); then a
 * shrunken card face parked in the bottom-left corner beside the hand, where
 * `--card-w` resolved to ~74px and the name clipped to "Aesi, Tyra…" --
 * docs/design-record.md (Open fidelity findings) defect #5, the least legible card on the board being
 * the one you cast most often.
 *
 * So this is not a card any more. It is a **plinth**: a cropped portrait in a
 * frame, a name, and a state strip, sized for the 190px column it lives in
 * rather than shrunk to fit it. Nothing legible is lost by not drawing a tiny
 * card face -- hovering puts the full card in the right-hand preview rail, which
 * is the surface rebuilt to hold it. That sentence was aspirational for a while:
 * the plinth was a `disabled` button in every state but "ready", and a disabled
 * control dispatches no mouse events, so the rail stayed empty for an opponent's
 * commander and for your own whenever you could not cast it. See `aria-disabled`
 * below.
 *
 * Only ever the viewer's, now that an opponent is an `OpponentSeat` -- so the
 * `compact` variant this used to draw at two-thirds the size for a seat nobody
 * could cast from is gone with it.
 *
 * The portrait also carries the **life seal**: `PlayerOrb` hands the dial down
 * as `seal` and the plinth stamps it over the art's lower right. Life is not a
 * fact about the command zone, but the art's bottom edge is the only anchor that
 * does not have to guess at the column's width, and it lives here.
 *
 * **State is said three ways.** A word, the art's brightness, and a glyph shape.
 * The green "you can play this" rim is a hairline that is easy to miss, which is
 * docs/design-record.md (Open fidelity findings)'s top-ranked open defect; this element is not allowed
 * to add to that pile, so it reads "READY" and lights the portrait as well.
 *
 * This is a *gesture* surface, exactly like `HandFan`: it carries no
 * `data-action-id`, and clicking routes through the same `playFromHand` path a
 * hand card takes, which resolves targeting and posts the real action. The
 * action panel keeps sole ownership of the id, so the "one button per action"
 * invariant at the top of `Table.tsx` still holds. `e2e/cycle3.spec.ts` and
 * `e2e/action-panel.spec.ts` both assert it.
 */

import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useEffect, useState } from "react";
import type { CardView, GameView } from "../../api/types";
import { stopId } from "../../input/stops";
import { artUrl } from "../../logic/cardArt";
import { manaPips } from "../../logic/cardStyle";
import { commandersOf } from "../../logic/zoneGrouping";
import { bouncy } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { ManaSymbol } from "./ManaSymbol";

/**
 * What the plinth says about where the commander is and whether you can do
 * anything about it.
 *
 * `word` and `glyph` are the two channels that read at 112px; the class carries
 * the third (how brightly the portrait is lit). Every state sets all three,
 * which is the whole point -- see the note at the top of the file.
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
  disabled: boolean;
  onActivate?: (card: CardView) => void;
  onHover?: (oid: number | null) => void;
  /**
   * The life seal, stamped over the portrait's lower right. Owned by
   * `PlayerOrb` -- the plinth knows where the art ends, and nothing else does.
   */
  seal?: ReactNode;
}

function Plinth({ card, castable, tax, disabled, onActivate, onHover, seal }: PlinthProps) {
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
  const showCost = card.zone === "command";
  const pips = showCost ? manaPips(card.mana_cost) : [];

  // Castable *and* not gated. `disabled` is the narration/in-flight lock.
  const clickable = castable && !disabled;

  /*
   * THE PLINTH IS A STOP, AND UNTIL NOW IT WAS THE ONLY CONTROL ON THE BOARD
   * THAT WAS NOT.
   *
   * The board declares its stops explicitly -- `stopsIn` takes a surface at its
   * word and gives it no native-focusable fallback, precisely so the rail's tool
   * buttons are not picked up twice. This element is a `<button>` and was
   * therefore invisible to the ring anyway: `setCursor("ui:commander-900")`
   * returned false, no direction could reach it, and **a controller could not
   * cast its own commander at all**. The hover-fills-the-preview-rail promise at
   * the top of this file went with it, because `hoverFor` drives `hoveredOid`
   * from the cursor and the cursor could not get here.
   *
   * `card:<oid>` and not a namespace of its own, because that is what this
   * element IS -- and then `A` casts it, `Y` reads it and the preview rail fills
   * with no second code path anywhere. See `stops.ts`, whose whole argument for
   * a string namespace is that a permanent keeps its id across zones.
   *
   * ONLY WHILE THE COMMANDER IS IN THE COMMAND ZONE, and that clause is what
   * keeps the id unique. A stop id names one element; the moment the commander
   * is cast, the stack panel draws `card:<oid>`, and once it resolves the
   * battlefield does -- so the plinth would be a second element answering to a
   * stop that already has one, and `stopElement` would hand the ring whichever
   * came first in the document. In the command zone nothing else is drawing this
   * card, which is also exactly when you need to reach it.
   */
  const reachable = card.zone === "command";

  /*
   * The pointer left because the plinth stopped existing.
   *
   * `hoveredOid` is only ever cleared by an element's own leave handler, so a
   * commander that is hovered and then leaves every visible zone -- shuffled
   * back into the library, say -- pins the preview rail to a card nobody is
   * pointing at. docs/design-record.md (Open fidelity findings) open defect #4.
   *
   * Guarded on the store rather than fired blind: by the time a plinth unmounts
   * the pointer may already have arrived somewhere else, and clearing then would
   * blank a preview that is correct.
   */
  useEffect(() => {
    return () => {
      if (useUiStore.getState().hoveredOid === card.oid) onHover?.(null);
    };
  }, [card.oid, onHover]);

  return (
    <motion.button
      type="button"
      className={`cmdslot cmdslot--${state.key}`}
      data-testid={`commander-${card.oid}`}
      data-stop={reachable ? stopId.card(card.oid) : undefined}
      data-castable={castable ? "true" : "false"}
      data-zone={card.zone}
      data-cmd-state={state.key}
      /*
        `aria-disabled`, not `disabled`, and the difference is the whole reason
        hovering an opponent's commander does nothing today: browsers do not
        dispatch mouse events over a disabled control, and every plinth but a
        castable one was disabled. So the surface whose documented job is "the
        full card is one hover away in the preview rail" was unhoverable in every
        state except the one where you were about to cast it anyway.

        Announced as disabled, click gated below, still focusable -- which also
        hands the preview to the keyboard, the way ActionPanel's `previewing()`
        already does.
      */
      aria-disabled={!clickable}
      data-hint={
        castable
          ? `Cast ${card.name}${tax > 0 ? ` — +${tax} commander tax` : ""}`
          : `${card.name} — ${state.word}`
      }
      onClick={() => {
        if (clickable) onActivate?.(card);
      }}
      onMouseEnter={() => onHover?.(card.oid)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(card.oid)}
      onBlur={() => onHover?.(null)}
      // The ring's copy of the two lines above: `input/cursor.ts`'s `hoverFor`
      // runs after focus and would otherwise clear what `onFocus` just set.
      // `ActionPanel`'s `previewing()` writes the same attribute.
      data-preview-oid={card.oid}
      whileHover={clickable ? { y: -3, scale: 1.03 } : undefined}
      whileTap={clickable ? { scale: 0.98 } : undefined}
      transition={bouncy}
    >
      {/*
        The portrait's own box, and the thing the life seal hangs off.

        It reserves the 2:1 banner whether or not there is an image in it yet.
        The art element itself is still conditional -- drawing the hatched "no
        art" plate before the image map arrives would flash it on every first
        paint -- but the *box* cannot be, because the seal is positioned against
        this element's bottom edge and a box that appears when `/images`
        resolves would drop the life dial into place a beat after the panel.
      */}
      <span className="cmdplinth__frame">
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
        <span className="cmdplinth__tag" data-hint="Commander">
          CMD
        </span>

        {/*
          Life, stamped half on the art and half off it. It costs the overlap
          instead of a row, which is what pays for the portrait being this size
          in a column this narrow. `pointer-events: none` in the CSS, because the
          portrait underneath is the cast control and a decorative disc must not
          eat the click that casts your commander.
        */}
        {seal}
      </span>

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
              <ManaSymbol code={pip.symbol} className={`pip--${pip.tone}`} key={pip.key} />
            ))}
            {tax > 0 && (
              <span
                className="cmdslot__tax"
                data-hint={`+${tax} generic to cast from the command zone`}
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
  onActivate?: (card: CardView) => void;
  onHover?: (oid: number | null) => void;
  disabled?: boolean;
  /**
   * The player's life dial, to be stamped over the first commander's portrait.
   *
   * It belongs to `PlayerOrb` -- life is not a fact about the command zone --
   * but only the plinth knows where the art ends, and the seal is anchored to
   * that edge. `PlayerOrb` draws it in a row of its own when there is no
   * commander anywhere visible and this component renders nothing at all.
   */
  seal?: ReactNode;
}

export function CommandZone({
  state,
  pid,
  playableOids,
  onActivate,
  onHover,
  disabled = false,
  seal,
}: Props) {
  const player = state.players[pid];
  const commanders = commandersOf(state, pid);
  if (commanders.length === 0) return null;

  return (
    <div className="cmdzone" data-testid={`command-zone-${pid}`}>
      <div className="cmdzone__cards">
        <AnimatePresence initial={false}>
          {commanders.map((card, index) => (
            <Plinth
              key={card.oid}
              card={card}
              // Only a commander sitting in the command zone can be cast from
              // it, and only when the server says so -- `playableOids` is built
              // from the legal-action list, never from a guess about mana.
              castable={card.zone === "command" && playableOids.has(card.oid)}
              tax={player.commander_cost?.[String(card.oid)] ?? 0}
              disabled={disabled}
              onActivate={onActivate}
              onHover={onHover}
              // One seal per player, not per commander: partners share a life
              // total, and two dials for one number would be a lie.
              seal={index === 0 ? seal : undefined}
            />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
