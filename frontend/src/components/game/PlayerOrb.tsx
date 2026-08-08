/**
 * A player: their commander, life, mana, and the zones you can look into.
 *
 * Three things here are physical rather than textual, and they read better than
 * what they replace:
 *
 * **The commander is the panel's hero.** It used to be a shrunken card face in
 * the bottom-left corner, which is where you put a thing nobody needs to look
 * at -- in Commander it is the thing the whole deck is about. It sits directly
 * under the player's name now, and its cost lands one glance above the mana row
 * that has to pay it. See `CommandZone`.
 *
 * **Life is a dial.** It is the one number people actually hunt for, so it is
 * the largest object in the column rather than a slightly bigger numeral. It
 * still pops and flashes on every change, in the direction of the change, and
 * `data-player` still marks it as the anchor for floating damage numerals.
 *
 * **Zones are piles.** `Lib 72 / GY 3 / Exile 1` gave three numbers to compare
 * by reading; a pile shows the shape of the game as well as the count. The
 * piles are still buttons -- they are the only route into `ZonePeek`, and a
 * decorative pile would make the graveyard unreachable.
 */

import { motion, useAnimationControls } from "motion/react";
import { useEffect, useRef } from "react";
import type { CardView, GameView, PlayerView } from "../../api/types";
import { lossReason } from "../../logic/labels";
import { formatManaRow, manaRow, markSpent } from "../../logic/mana";
import { type PileKind, pileLeaves } from "../../logic/zones";
import { bouncy } from "../../motion/springs";
import { type PeekTarget, useUiStore } from "../../state/uiStore";
import { CommandZone } from "./CommandZone";

/** Commander damage becomes lethal here; warn well before it does. */
const COMMANDER_LETHAL = 21;

const EMPTY: ReadonlySet<number> = new Set();

interface PileProps {
  pid: number;
  /** Which zone this opens. `null` for the library, which cannot be looked at. */
  zone: PeekTarget["zone"] | null;
  name: string;
  kind: PileKind;
  label: string;
  count: number;
  title?: string;
}

/**
 * One zone, drawn as a stack of leaves whose height is the count.
 *
 * A button wherever the zone can be opened: these replaced the zone chips, and
 * the chips were how you reached `ZonePeek`. A decorative pile would make the
 * graveyard unreachable for anyone not using the keyboard shortcut.
 *
 * The library is the exception and stays a plain element -- it is hidden
 * information, and a control that does nothing when clicked is worse than no
 * control.
 */
function ZonePile({ pid, zone, name, kind, label, count, title }: PileProps) {
  const setPeek = useUiStore((s) => s.setPeek);
  const leaves = pileLeaves(count);

  const body = (
    <>
      <span className="pile__stack">
        {Array.from({ length: leaves }, (_, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: leaves are identical and positional
          <span className={`pile__leaf pile__leaf--${kind}`} key={i} />
        ))}
        {/* The top leaf carries the exact number, so capping the leaf count
            costs resolution but never information. */}
        <span className={`pile__leaf pile__leaf--top pile__leaf--${kind} tabular`}>
          {count}
        </span>
      </span>
      <span className="pile__label">{label}</span>
    </>
  );

  const className = [
    "pile",
    count > 0 ? "" : "pile--empty",
    zone === null ? "pile--static" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const shared = {
    className,
    "data-testid": `pile-${pid}-${name}`,
    "data-count": count,
    title: title ?? `${label}: ${count}`,
  };

  if (zone === null) return <div {...shared}>{body}</div>;
  return (
    <button type="button" {...shared} onClick={() => setPeek({ pid, zone })}>
      {body}
    </button>
  );
}

interface Props {
  /** The whole view, because the commander plinth searches every visible zone. */
  state: GameView;
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
  /**
   * Sources a currently-hovered spell would tap, from the engine's own solved
   * payment. Empty when nothing is hovered, or for any seat but the viewer.
   */
  spending?: ReadonlySet<number>;
  /** Oids a legal play action names, for the plinth's ready state. */
  playableOids?: ReadonlySet<number>;
  /** Casting a commander out of the command zone. */
  onCastCommander?: (card: CardView) => void;
  onHoverCard?: (oid: number | null) => void;
  /** Input is gated (narration playing, request in flight). */
  locked?: boolean;
}

export function PlayerOrb({
  state,
  player,
  isViewer,
  isActive,
  hasPriority,
  names,
  compact = false,
  targetable = false,
  onSelect,
  spending,
  playableOids,
  onCastCommander,
  onHoverCard,
  locked = false,
}: Props) {
  const controls = useAnimationControls();
  const previous = useRef(player.life);

  useEffect(() => {
    const before = previous.current;
    previous.current = player.life;
    if (before === player.life) return;
    const grew = player.life > before;
    controls.start({
      scale: [1, grew ? 1.28 : 1.34, 1],
      // Rests on the dial's ink, not `--text`. The numeral sits on brass now,
      // so returning it to the old off-white would leave it white-on-gold from
      // the first life change onwards -- a bug that only appears after the
      // first hit, which is exactly when nobody is looking at the CSS.
      color: ["var(--dial-ink)", grew ? "var(--gain)" : "var(--danger)", "var(--dial-ink)"],
      transition: { duration: 0.5, times: [0, 0.25, 1] },
    });
  }, [player.life, controls]);

  const commanderDamage = Object.entries(player.commander_damage_taken).filter(
    ([, amount]) => amount > 0,
  );

  const pips = markSpent(manaRow(player.mana), spending ?? EMPTY);
  const spentCount = pips.filter((pip) => pip.spent).length;

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

      {/*
        The commander, above the life total rather than below the fold.

        Clicking it is a gesture, not an action id -- `onCastCommander` routes
        through the same path a hand card takes. Nothing in this subtree may
        carry `data-action-id`; see the note at the top of `CommandZone`.
      */}
      <CommandZone
        state={state}
        pid={player.pid}
        playableOids={playableOids ?? EMPTY}
        compact={compact}
        onActivate={onCastCommander}
        onHover={onHoverCard}
        disabled={locked}
      />

      <div className="orb__life-row">
        <div
          className={[
            "dial",
            isViewer ? "dial--mine" : "dial--foe",
            isActive ? "dial--active" : "",
            player.has_lost ? "dial--out" : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {/*
            The testid sits on the numeral, not the disc: `lifeOf()` in
            e2e/helpers.ts does `Number(textContent)` on this node, so it has
            to hold the bare number and nothing else.
          */}
          <motion.span
            className="dial__n tabular"
            animate={controls}
            data-testid={`life-${player.pid}`}
          >
            {player.has_lost ? "OUT" : player.life}
          </motion.span>
        </div>
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

        Hovering a castable card hollows out the pips it would spend, so the row
        answers "and what will that leave me with" as well as "what do I have".
        Which lands those are comes from the engine's solved payment, never from
        arithmetic here -- see logic/mana.ts.

        The row itself is still conditional -- an empty mana row would be a
        control that says nothing -- but the *slot* around it is not. Mana
        appears and empties several times a turn, and letting the orb grow and
        shrink with it moved the mat, the opponents row, and with it the whole
        board underneath the player's cursor. The slot keeps its line whether or
        not there is anything to draw in it.
      */}
      <div className="orb__manaslot">
        {pips.length > 0 && (
          <div
            className="orb__mana"
            data-testid={`mana-${player.pid}`}
            data-mana={formatManaRow(pips)}
            data-spending={spentCount}
            title={
              spentCount > 0
                ? `${pips.length} available; this spell taps ${spentCount}`
                : `${pips.length} available: ${formatManaRow(pips)}`
            }
          >
            {pips.map((pip) => (
              <span
                key={pip.key}
                className={[
                  "mana-pip",
                  `mana-pip--${pip.tone}`,
                  pip.floating ? "mana-pip--floating" : "",
                  pip.spent ? "mana-pip--spent" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                title={
                  pip.spent
                    ? `${pip.symbols.join(" or ")} — this spell would tap it`
                    : pip.symbols.length > 1
                      ? `Either ${pip.symbols.join(" or ")}`
                      : pip.floating
                        ? `${pip.symbols[0]} in pool`
                        : pip.symbols[0]
                }
              />
            ))}
          </div>
        )}
      </div>

      {/*
        Commander tax used to live here as a `CMD +N` chip. It rides on the
        plinth above now, beside the mana cost it modifies and directly over the
        mana row -- which is the only arrangement in which a surcharge means
        anything.
      */}
      {/*
        Bottom-aligned, so the piles' heights read comparatively: a library
        that has been drawn down to nothing is visibly a short stack next to a
        graveyard that has grown, which is a thing you want to notice rather
        than work out.
      */}
      <div className="piles">
        <ZonePile
          pid={player.pid}
          zone={null}
          name="library"
          kind="lib"
          label="Lib"
          count={player.library_count}
          title="Cards in library"
        />
        <ZonePile
          pid={player.pid}
          zone="hand"
          name="hand"
          kind="lib"
          label="Hand"
          count={player.hand_count}
          title={isViewer ? "Your hand" : "Hidden"}
        />
        <ZonePile
          pid={player.pid}
          zone="graveyard"
          name="graveyard"
          kind="gy"
          label="GY"
          count={player.graveyard.length}
        />
        {player.exile.length > 0 && (
          <ZonePile
            pid={player.pid}
            zone="exile"
            name="exile"
            kind="ex"
            label="Exile"
            count={player.exile.length}
          />
        )}
        <ZonePile
          pid={player.pid}
          zone="command"
          name="command"
          kind="cmd"
          label="CMD"
          count={player.command.length}
          title="Command zone"
        />
      </div>
    </motion.div>
  );
}
