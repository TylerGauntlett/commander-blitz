/**
 * THE VIEWER: their commander, life, mana, and the zones they can look into.
 *
 * Only ever the viewer's. An opponent used to render this same column at
 * two-thirds the size, which meant a pod was three control panels for controls
 * nobody could press -- they are `OpponentSeat` now, and the `compact` variant
 * and the `!isViewer` summary line that existed for them are gone with them.
 * `isViewer` survives because the dial still names itself, and because a
 * spectator view would put this column on somebody else's seat.
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
 * column could not do and the reason the orb round (`docs/adr/0012-art-fetched-once-served-locally.md`) picked this direction. It is
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
import { stopId } from "../../input/stops";
import { artUrlFor } from "../../logic/cardArt";
import { lossReason } from "../../logic/labels";
import {
  formatManaRow,
  type ManaGroupView,
  manaGroups,
  manaRow,
  markSpent,
} from "../../logic/mana";
import { commandersOf, commandZoneCommanderCount } from "../../logic/zoneGrouping";
import { type PileKind, pileLeaves } from "../../logic/zones";
import { bouncy } from "../../motion/springs";
import { type PeekTarget, useUiStore } from "../../state/uiStore";
import { CommandZone } from "./CommandZone";
import { EnergyChip } from "./EnergyChip";
import { ManaSymbol } from "./ManaSymbol";
import { SeatIcon, type SeatIconName } from "./SeatIcon";

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

/** Starting life, and so what the handheld dial's ring is a fraction of. */
const STARTING_LIFE = 40;

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
  /**
   * The top card of the library, when something on the battlefield shows it.
   * The library alone can carry one.
   */
  topCard?: CardView | null;
  /**
   * Whether that card is *revealed* to the table or only *looked at* by its
   * controller. The server sends a private look to one seat and a reveal to
   * every seat, so by the time it is here the difference is no longer about
   * who has the data -- it is about what this pile is allowed to claim.
   * Wording a private look as "revealed" would tell the one player who can see
   * it that their opponents can too.
   */
  topCardPublic?: boolean;
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
 *
 * Unless it is not hidden. With `topCard` set the pile names the card and
 * hovering it fills the preview rail, which is the only way this mechanic pays
 * for itself: Vampire Nocturnus is unpilotable if you cannot tell whether your
 * team has flying before you declare attackers.
 */
function ZonePile({
  pid,
  zone,
  name,
  kind,
  label,
  count,
  title,
  topCard,
  topCardPublic,
}: PileProps) {
  const setPeek = useUiStore((s) => s.setPeek);
  const hover = useUiStore((s) => s.hover);
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
      {/*
        THE MARK IS WHAT THE WORD WAS FOR.
        
        Loop 3 dropped `.pile__label` at the 16px floor and took it back the
        same day: the column became the bare row "82 4 5 1" and there was no way
        to tell a library count from a graveyard count. The note it left is the
        right one -- **the order only helps somebody who already knows it** --
        and so is the conclusion, that a count is not its own name.
        
        A shape is, though, and does not have to be taught: a headstone is a
        graveyard, a fan of three is a hand, a face-down card is a library.
        the handheld-board round reaches for exactly this, and `SeatIcon` is
        the set. So the word can go where the room is tight without the row
        becoming anonymous again -- see `styles/handheld.css`.
      */}
      <SeatIcon name={kind as SeatIconName} />
      <span className="pile__label">{label}</span>
      {topCard && <span className="pile__revealed">{topCard.name}</span>}
    </>
  );

  const className = [
    "pile",
    count > 0 ? "" : "pile--empty",
    zone === null ? "pile--static" : "",
    topCard ? "pile--revealed" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const shared = {
    className,
    "data-testid": `pile-${pid}-${name}`,
    "data-count": count,
    "data-revealed": topCard?.name,
    "data-top-private": topCard && !topCardPublic ? "" : undefined,
    /*
     * `data-hint` rather than `title`.
     *
     * A native tooltip opens on hover and on nothing else, so on a controller
     * it is information that cannot be reached at all -- and this pile's hint
     * is the only place the revealed top card is named. The hint bar and the
     * read rail surface it from the focused element, which also means a mouse
     * player gets it immediately instead of after a 500ms delay.
     */
    "data-hint": topCard
      ? topCardPublic
        ? `Top of library, revealed: ${topCard.name}`
        : `Top of library, only you can see it: ${topCard.name}`
      : (title ?? `${label}: ${count}`),
    /*
     * ...and an accessible name, which `title` had been supplying as a last
     * resort. The handheld layout hides `.pile__label`, so without this the
     * button would have no name at all there -- the one place it is most needed.
     */
    "aria-label": `${label}: ${count}`,
  };

  if (zone === null) {
    if (!topCard) return <div {...shared}>{body}</div>;
    return (
      // biome-ignore lint/a11y/noStaticElementInteractions: a pointer-only hover affordance. The pad and the keyboard reach the same preview through the focus ring, which is why `useKeyWithClickEvents` is off in biome.json for the same reason.
      <div {...shared} onMouseEnter={() => hover(topCard.oid)} onMouseLeave={() => hover(null)}>
        {body}
      </div>
    );
  }
  return (
    <button
      type="button"
      {...shared}
      data-stop={stopId.pile(pid, zone)}
      onClick={() => setPeek({ pid, zone })}
    >
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
  const seatImages = useUiStore((s) => s.seatImages);

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
  const wash = commanders.length > 0 ? artUrlFor(images, seatImages, commanders[0]) : undefined;

  useEffect(() => {
    const before = previous.current;
    previous.current = player.life;
    if (before === player.life) return;
    const grew = player.life > before;
    controls.start({
      scale: [1, grew ? 1.28 : 1.34, 1],
      /*
       * Rests on `--dial-n`, which is WHATEVER THE STYLESHEET SAYS the numeral
       * is -- and that indirection is the fix rather than a tidy.
       *
       * It rested on `--dial-ink` directly, which was right for the old brass
       * seal. The dial is a gold ring around a hole punched out of `--void-1`
       * now, and the stylesheet colours the numeral `--text` for exactly that
       * reason -- but Framer writes the resting colour back as an inline
       * style, which beats a stylesheet. So one point of damage stamped
       * near-black ink onto a dark purple well and the life total became
       * unreadable, and only after the first hit -- which is precisely when
       * nobody is looking at the CSS.
       *
       * `--dial-n` is defined on `.dial__n` in `board.css`, so this says "put
       * it back" without knowing what the disc looks like.
       */
      color: ["var(--dial-n)", grew ? "var(--gain)" : "var(--danger)", "var(--dial-n)"],
      transition: { duration: 0.5, times: [0, 0.25, 1] },
    });
  }, [player.life, controls]);

  const pips = markSpent(manaRow(player.mana), spending ?? EMPTY);
  const spentCount = pips.filter((pip) => pip.spent).length;
  const groups = manaGroups(pips);

  const classes = [
    "orb",
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
      /*
        The fraction of a starting life total, for the dial's ring: "34" reads
        as "34 of the 40 you started with" without adding a character.
      */
      style={
        {
          "--fill": `${(Math.min(Math.max(player.life, 0), STARTING_LIFE) / STARTING_LIFE) * 100}%`,
        } as CSSProperties
      }
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
      data-stop={stopId.orb(player.pid)}
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
        {/*
          Your own name, and on a handheld it is the one thing here that says
          nothing.

          the handheld-board round calls this its single deviation from the
          plinth direction and argues it: the information strip six pixels above
          names you, and unlike the three seats beside it there is never any
          doubt whose panel this is. It is worth 21px of a 250px column and not
          of a 128px one. The row stays in the DOM so the priority tick has
          somewhere to live and `orb.spec.ts` keeps its anchor; `handheld.css`
          drops the NAME.
        */}
        <div className="orb__head">
          <span className="orb__name">{player.name}</span>
          <EnergyChip pid={player.pid} energy={player.energy} />
          {hasPriority && <span className="orb__priority" data-hint="Has priority" />}
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

          Commander damage is deliberately not here at all any more. It was a
          chip per opposing seat with a meter under it -- the loudest object in
          the column, answering "how close is each of them to killing me" and
          nothing about the other direction. It is two arrows on each
          opponent's own life bar now: see `OpponentSeat`.

          Commander tax is deliberately not here either -- it rides on the
          plinth above, beside the mana cost it modifies, which is the only
          arrangement in which a surcharge means anything.
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
            data-hint={
              spentCount > 0
                ? `${pips.length} available; this spell taps ${spentCount}`
                : `${pips.length} available: ${formatManaRow(pips)}`
            }
          >
            <span className="orb__lab">Mana</span>
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
                  data-hint={groupTitle(group)}
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
              data-hint="Cards in library"
              topCard={player.library_top}
              topCardPublic={player.library_top_public}
            />
            <ZonePile
              pid={player.pid}
              zone="hand"
              name="hand"
              kind="hand"
              label="Hand"
              count={player.hand_count}
              data-hint={isViewer ? "Your hand" : "Hidden"}
            />
            <ZonePile
              pid={player.pid}
              zone="graveyard"
              name="graveyard"
              kind="gy"
              label="GY"
              count={player.graveyard.length}
            />
            {player.exile.length + player.exile_hidden_count > 0 && (
              <ZonePile
                pid={player.pid}
                zone="exile"
                name="exile"
                kind="ex"
                label="Exile"
                count={player.exile.length + player.exile_hidden_count}
              />
            )}
            <ZonePile
              pid={player.pid}
              zone="command"
              name="command"
              kind="cmd"
              label="CMD"
              count={commandZoneCommanderCount(player)}
              data-hint="Command zone"
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
