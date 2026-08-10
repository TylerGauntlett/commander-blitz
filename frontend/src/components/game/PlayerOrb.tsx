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
 * **The commander is also the panel's ground.** Its art, blurred and scrimmed,
 * is the orb's background -- so four seats in a pod stop being four grey
 * rectangles told apart by a name in 12px type, which is the one thing the old
 * column could not do and the reason `mockups/orb/` picked this direction. It is
 * the same `/art/{card_id}.jpg` the plinth already draws, so it costs no second
 * request. There is deliberately **no colour-identity tint** over it: a tint
 * dies in greyscale and the portrait does not, and every scrap of type here is
 * legible against the unconditional dark veil rather than against the hue.
 *
 * **Life is a seal, not a row.** It is the one number people actually hunt for,
 * so it is the largest object in the column -- but it is stamped over the
 * portrait's lower right rather than given a row of its own, which is what buys
 * the portrait its size in a 190px column. It still pops and flashes on every
 * change, in the direction of the change, and `data-player` still marks it as
 * the anchor for floating damage numerals. When there is no commander anywhere
 * visible, it falls back to a row -- see `orb__life-row` below.
 *
 * **Zones are piles.** `Lib 72 / GY 3 / Exile 1` gave three numbers to compare
 * by reading; a pile shows the shape of the game as well as the count. The
 * piles are still buttons -- they are the only route into `ZonePeek`, and a
 * decorative pile would make the graveyard unreachable.
 */

import { motion, useAnimationControls } from "motion/react";
import { type CSSProperties, useEffect, useRef } from "react";
import type { CardView, GameView, PlayerView } from "../../api/types";
import { artUrl } from "../../logic/cardArt";
import { lossReason } from "../../logic/labels";
import {
  type ManaGroupView,
  formatManaRow,
  manaGroups,
  manaRow,
  markSpent,
} from "../../logic/mana";
import { commandersOf } from "../../logic/zoneGrouping";
import { type PileKind, pileLeaves } from "../../logic/zones";
import { bouncy } from "../../motion/springs";
import { type PeekTarget, useUiStore } from "../../state/uiStore";
import { CommandZone } from "./CommandZone";
import { ManaSymbol } from "./ManaSymbol";

/** Commander damage becomes lethal here; warn well before it does. */
const COMMANDER_LETHAL = 21;

/**
 * What a mana group says on hover, in the one form that fits every case.
 *
 * Spelled out rather than left to the numbers, because `2 -2` is compact enough
 * to be worth a sentence somewhere: the chip is a forecast, and a forecast that
 * cannot be read back in words is a puzzle.
 */
function groupTitle(group: ManaGroupView): string {
  const what =
    group.symbols.length > 1 ? `either ${group.symbols.join(" or ")}` : group.symbols[0];
  const where = group.floating ? " in pool" : "";
  if (group.spent > 0) {
    return `${group.count} ${what}${where}; this spell taps ${group.spent}, leaving ${
      group.count - group.spent
    }`;
  }
  return `${group.count} ${what}${where}`;
}

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
  const images = useUiStore((s) => s.images);

  /*
   * The seat's own commander, and with it the seat's own ground.
   *
   * The same `commandersOf` call `CommandZone` makes on the same state, so the
   * two cannot disagree about which commander is the hero of this panel -- and
   * the same `artUrl`, so the wash is a second reference to the URL the plinth's
   * `<img>` has already put in the cache rather than a second request.
   *
   * `undefined` (map not fetched) and `null` (no printing) both mean "draw no
   * wash": the panel falls back to its flat well, which is what it looked like
   * before this direction and is a perfectly good panel. See logic/cardArt.ts.
   */
  const commanders = commandersOf(state, player.pid);
  const wash = commanders.length > 0 ? artUrl(images, commanders[0].card_id) : undefined;

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

  /*
   * Every other seat, in seating order -- not the seats that have already dealt
   * commander damage.
   *
   * `commander_damage_taken` only carries seats that have connected, so building
   * the row from its keys made the plate appear on the first hit. Reading it as a
   * lookup against the seating instead means the chips are all there from turn
   * one, at zero, and the panel never changes size.
   */
  const opponents = state.players
    .filter((seat) => seat.pid !== player.pid)
    .map((seat) => seat.pid);

  const pips = markSpent(manaRow(player.mana), spending ?? EMPTY);
  const spentCount = pips.filter((pip) => pip.spent).length;
  const groups = manaGroups(pips);

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

  /*
   * The dial, built once and placed in one of two ways.
   *
   * Normally it is the seal: `CommandZone` stamps it over the first commander's
   * portrait, where it costs the overlap rather than a row. But `CommandZone`
   * renders nothing at all when the commander is in a hidden zone -- shuffled
   * back into the library, say -- and life is not allowed to vanish with it, so
   * `orb__life-row` is the fallback and not dead code.
   */
  // A span, not a div: the seal is stamped *inside* the plinth's `<button>`, and
  // a button may only contain phrasing content. `.dial` is `display: grid`
  // already, so nothing about it changes but its validity.
  const dial = (
    <span
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
    </span>
  );

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
      {/*
        The ground, and the reason a pod stops being four identical rectangles.

        Two layers rather than one blended one. Tinting the scrim itself lifts
        the whole panel toward the art's dominant colour and takes the header
        type with it; the veil is unconditionally dark so that no piece of type
        in this panel depends on what the portrait happens to look like.
      */}
      {typeof wash === "string" && (
        <>
          {/* Quoted, because an unquoted `url()` gives a bare path meaning to
              parentheses and whitespace. Card ids are slugs today, but the deck
              importer mints them from names it did not choose. */}
          <div
            className="orb__wash"
            style={{ backgroundImage: `url("${wash}")` }}
            aria-hidden="true"
          />
          <div className="orb__veil" aria-hidden="true" />
        </>
      )}

      <div className="orb__body">
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
          seal={dial}
        />

        {commanders.length === 0 && <div className="orb__life-row">{dial}</div>}

        {player.has_lost && <div className="orb__loss">{lossReason(player.loss_reason)}</div>}

        {/*
          The panel's foot: three plates that are always there.

          Mana and commander damage used to be conditional rows sitting loose
          between the plinth and the piles, and `orb__body` is `space-between` --
          so they floated in the slack, and each time one appeared or emptied the
          whole interior re-spaced itself. Grouping them with the piles puts all
          the slack in one gap under the plinth and gives the column a foot that
          holds still. It is also why neither plate is conditional any more: a
          panel that says "no mana" costs one line and never moves anything,
          which the reserved-height slot this replaces was an awkward way of
          buying.

          Commander tax is deliberately not here -- it rides on the plinth above,
          beside the mana cost it modifies, which is the only arrangement in
          which a surcharge means anything.
        */}
        <div className="orb__foot">
          {/*
            Available mana. The server sends it, nothing rendered it, and lands
            tapped during auto-payment with no indication of what was spent -- so
            the player had no running sense of what they could afford.

            One mark per *kind* of mana with a count, not one per mana. As a 9px
            dot a pip per mana was honest and cheap; as the real symbol it is
            twice as wide, and ten untapped lands wrapped the row to three lines
            in a 190px column. Grouping is also how players say it out loud.

            Hovering a castable card marks what it would take: the group shows
            what you would have left and a faint `-n` for what goes. That is the
            same question the hollowed-out pips answered -- "and what will that
            leave me with" -- in the form a counted chip can answer it. Which
            lands those are comes from the engine's solved payment, never from
            arithmetic here; see logic/mana.ts.
          */}
          <div
            className="orb__panel orb__mana"
            data-testid={`mana-${player.pid}`}
            data-mana={formatManaRow(pips)}
            data-spending={spentCount}
            title={
              spentCount > 0
                ? `${pips.length} available; this spell taps ${spentCount}`
                : `${pips.length} available: ${formatManaRow(pips)}`
            }
          >
            {!compact && <span className="orb__lab">Mana</span>}
            {groups.length === 0 ? (
              <span className="orb__none">—</span>
            ) : (
              groups.map((group) => (
                <span
                  key={group.key}
                  className={[
                    "mana-grp",
                    `mana-grp--${group.tone}`,
                    group.floating ? "mana-grp--floating" : "",
                    group.spent > 0 ? "mana-grp--spent" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-tone={group.tone}
                  data-count={group.count}
                  data-spent={group.spent}
                  title={groupTitle(group)}
                >
                  {/* No `pip--text` fallback here: a three-colour source has no
                      published mark, and cycle3.spec.ts asserts that fallback
                      never renders because reaching it means a symbol is
                      missing. The split disc is the answer for "some colour",
                      and it says the right thing besides -- the player picks
                      when they tap it, and we must not pretend otherwise. */}
                  {group.code === null ? (
                    <span className="mana-grp__any" aria-hidden="true" />
                  ) : (
                    <ManaSymbol code={group.code} title={group.symbols.join(" or ")} />
                  )}
                  <span className="mana-grp__n tabular">{group.count - group.spent}</span>
                  {group.spent > 0 && (
                    <span className="mana-grp__spend tabular">−{group.spent}</span>
                  )}
                </span>
              ))
            )}
          </div>

          {/*
            Commander damage, for every other seat rather than only the ones that
            have connected. Built from the seating rather than from the keys of
            `commander_damage_taken`, so the plate reads `0` from turn one
            instead of appearing the moment someone hits you -- which is both a
            reflow and the worst possible moment to move the panel.

            The chip carries who and how far. It was a bare number whose source
            lived only in a `title`, which in a four-player pod is three
            identical numbers and a hunt; and 21 is the number that matters, so
            the meter under it is the fraction of 21 rather than decoration.
          */}
          <div className="orb__panel orb__cmd" data-testid={`cmddmg-${player.pid}`}>
            {!compact && <span className="orb__lab">Cmd dmg</span>}
            {opponents.map((pid) => {
              const amount = player.commander_damage_taken[String(pid)] ?? 0;
              return (
                <span
                  key={pid}
                  className={[
                    "cmd-pip",
                    amount >= COMMANDER_LETHAL - 6 ? "cmd-pip--warn" : "",
                    amount === 0 ? "cmd-pip--zero" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-from={pid}
                  data-amount={amount}
                  title={`${amount} of ${COMMANDER_LETHAL} commander damage from ${
                    names[pid] ?? `Player ${pid}`
                  }`}
                >
                  <span className="cmd-pip__head">
                    {/* Seat number, not an initial: seats default to
                        `Player {i}` (server/sessions.py), so every initial is
                        "P". The name itself stays one hover away. */}
                    <span className="cmd-pip__who">P{pid}</span>
                    <span className="cmd-pip__n tabular">{amount}</span>
                  </span>
                  <span
                    className="cmd-pip__meter"
                    style={
                      {
                        "--fill": `${Math.min(amount / COMMANDER_LETHAL, 1) * 100}%`,
                      } as CSSProperties
                    }
                  />
                </span>
              );
            })}
          </div>

          {/*
            Bottom-aligned, so the piles' heights read comparatively: a library
            that has been drawn down to nothing is visibly a short stack next to
            a graveyard that has grown, which is a thing you want to notice
            rather than work out.
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
        </div>
      </div>
    </motion.div>
  );
}
