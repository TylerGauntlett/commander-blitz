// biome-ignore-all lint/a11y/useAriaPropsSupportedByRole: a labelled readout on a generic element, written before Biome 2 had this rule. The fix is a role, which changes what a screen reader announces -- a behaviour change, so it waits for an a11y pass rather than riding a dependency upgrade.
/**
 * An opponent, as five numbers you can check against their board.
 *
 * ## What this replaces, and why
 *
 * An opponent used to be a `PlayerOrb` -- the same column the viewer gets, at
 * two-thirds the size. That column is built to be *operated*: a commander you
 * cast, piles you open, a mana row that forecasts your own spend. None of it is
 * yours on somebody else's seat, so a pod was three control panels for controls
 * nobody could press, and the one question actually being asked across the
 * table -- **how developed is that board** -- was answered by counting cards at
 * 51px.
 *
 * So a seat answers that question directly: lands, creatures and other
 * permanents as `untapped/total`, a pip per creature, total power, and a gauge
 * that is life eaten from the left and commander damage closing from the right.
 *
 * ## The gate is the point
 *
 * the seat round (`docs/design-record.md#seat`) records the failure mode this whole family of components has:
 * **a summary that cannot be checked against the thing it summarises**. Five of
 * its six directions could not be wrong about the board, because the numbers
 * were never in the payload. Every number here comes from `musterOf`, which is
 * the one walk `threatOf` is also derived from.
 *
 * ## Drawn at every size, and that is a decision
 *
 * Not scoped to the handheld layout. A desktop pod draws an opponent's cards at
 * ~51px, where counting untapped creatures is a chore the client can simply do
 * -- and a desktop that summarised opponents differently from a handheld would
 * be two designs for one fact. What differs by size is what sits *below* the
 * seat: their actual lanes on a desktop, nothing on a handheld, where 1280px
 * cannot hold three boards and a hand at a legible card size.
 *
 * ## The identity attributes are not ours to rename
 *
 * `data-player` anchors `FxLayer`'s damage numerals and `CombatArrows`' ends.
 * `data-stop="orb:<pid>"` is what `parseStop`, `verbsFor` and the R2 hold all
 * branch on -- a `seat:<pid>` namespace would break three things silently.
 * `player-<pid>` and `life-<pid>` are what the e2e helpers query. All of them
 * are carried through unchanged from `PlayerOrb`.
 *
 * ## No `data-action-id`, ever
 *
 * The seat is a target and a viewer, never a second copy of the action space.
 * Its press routes through `onSelect`, which is the same gesture an orb has
 * always had: point an attacker at them, finish a player-targeted spell, or --
 * when neither is legal -- read their board. `ActionPanel` owns every id alone,
 * which `e2e/cycle3.spec.ts` asserts.
 */

import { motion } from "motion/react";
import type { CSSProperties } from "react";
import type { GameView, PlayerView } from "../../api/types";
import { getInputMode } from "../../input/inputMode";
import { stopId } from "../../input/stops";
import { artUrlFor } from "../../logic/cardArt";
import { lossReason } from "../../logic/labels";
import { type Muster, musterOf } from "../../logic/threat";
import { commandersOf, commandZoneCommanderCount } from "../../logic/zoneGrouping";
import type { PileKind } from "../../logic/zones";
import { bouncy } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { SeatIcon, type SeatIconName } from "./SeatIcon";

/** Commander damage becomes lethal here. The gauge is a fraction of it. */
const COMMANDER_LETHAL = 21;

/** Warn well before it is lethal: at 15 the next hit can end you. */
const COMMANDER_WARN = 15;

/** Starting life, and so what the life half of the gauge is a fraction of. */
const STARTING_LIFE = 40;

/**
 * Eight pips, then a count.
 *
 * Past eight the extra pips say nothing a reader can use, and the cap costs
 * resolution and never information -- the exact number is on the creature cell
 * beside them.
 */
const MAX_PIPS = 8;

interface Props {
  state: GameView;
  player: PlayerView;
  /** It is this player's turn. */
  isActive: boolean;
  /** This player holds priority, which is a different fact from the above. */
  hasPriority: boolean;
  /** This player can be pointed at right now. */
  targetable: boolean;
  /** Their board is the one currently drawn in the viewer's lane area. */
  viewing?: boolean;
  onSelect?: (pid: number) => void;
  /** Fills the reader with a card. The seat offers its commander. */
  onHoverCard?: (oid: number | null) => void;
  /** Input is gated (narration playing, request in flight). */
  locked?: boolean;
}

/**
 * One kind of permanent, drawn as a count over a meter.
 *
 * `open` is `null` for the cell that has no tapped state to draw. The lane
 * mixes artifacts with enchantments and an enchantment does not tap, so an
 * `untapped/total` there would be measuring two things and calling them one --
 * see `Muster.other`.
 */
function PermCell({
  kind,
  total,
  open,
  label,
}: {
  kind: SeatIconName & ("land" | "creature" | "other");
  total: number;
  open: number | null;
  label: string;
}) {
  const fill = open === null || total === 0 ? 0 : (open / total) * 100;
  return (
    <span
      className={`perm perm--${kind}${total === 0 ? " perm--zero" : ""}`}
      style={{ "--fill": `${fill}%` } as CSSProperties}
      data-perm={kind}
      data-total={total}
      data-open={open ?? ""}
      aria-label={label}
      data-hint={label}
    >
      {/* The mark first, because it says WHICH number this is -- "5/7" beside
          "2/3" beside "1" is three numbers in a row and nothing else. */}
      <SeatIcon name={kind} />
      <span className="perm__n tabular">{open === null ? total : `${open}/${total}`}</span>
    </span>
  );
}

/**
 * A pip per creature, untapped first and fliers first.
 *
 * The ordering is what makes the cap safe: the pips a player cares about are
 * the ones that survive it. Sorting them the other way round would mean a board
 * of nine creatures could hide its only flier behind the `+1`.
 */
function DetailCell({ muster }: { muster: Muster }) {
  const shown = Math.min(muster.creatures, MAX_PIPS);
  const pips: { up: boolean; fly: boolean }[] = [];
  let up = muster.creaturesUntapped;
  let fly = muster.fliers;
  for (let i = 0; i < shown; i += 1) {
    pips.push({ up: up-- > 0, fly: fly-- > 0 });
  }
  const more = muster.creatures - shown;

  const label = `${muster.power} power on board${
    muster.fliers > 0 ? `, ${muster.fliers} ${muster.fliers === 1 ? "flier" : "fliers"}` : ""
  }`;

  return (
    <span className="perm perm--detail" aria-label={label} data-hint={label}>
      <span className="pips">
        {pips.map((pip, i) => (
          <span
            // The pips have no identity of their own -- this is a bar chart
            // with one bar per creature, not a list of creatures -- so the
            // index is the honest key.
            // biome-ignore lint/suspicious/noArrayIndexKey: see above
            key={i}
            className={`tpip${pip.up ? " tpip--up" : ""}${pip.fly ? " tpip--fly" : ""}`}
          />
        ))}
        {more > 0 && <span className="pips__more tabular">+{more}</span>}
        {muster.creatures === 0 && <span className="pips__more">none</span>}
      </span>
      <span className="perm__pow tabular" data-power={muster.power}>
        <SeatIcon name="power" />
        {muster.power}
      </span>
    </span>
  );
}

interface SeatZone {
  zone: string;
  kind: PileKind;
  label: string;
  count: number;
}

/** The zones a seat reports, in the order the orb has always listed them. */
function zonesOf(player: PlayerView): SeatZone[] {
  const zones: SeatZone[] = [
    { zone: "library", kind: "lib", label: "Library", count: player.library_count },
    { zone: "hand", kind: "hand", label: "Hand", count: player.hand_count },
    { zone: "graveyard", kind: "gy", label: "Graveyard", count: player.graveyard.length },
  ];
  // Exile appears the moment anything is exiled and is NOT a fixed slot, so a
  // seat shows four marks or five. The row has to survive that reflow, which is
  // why the marks share the width rather than being placed.
  // Face-down exiles are not in `exile` for a seat that may not see them, so
  // the pile is counted rather than measured -- otherwise a Necropotence hiding
  // the only card in exile makes the whole mark disappear.
  const exileCount = player.exile.length + player.exile_hidden_count;
  if (exileCount > 0) {
    zones.push({ zone: "exile", kind: "ex", label: "Exile", count: exileCount });
  }
  zones.push({
    zone: "command",
    kind: "cmd",
    label: "Command zone",
    count: commandZoneCommanderCount(player),
  });
  return zones;
}

export function OpponentSeat({
  state,
  player,
  isActive,
  hasPriority,
  targetable,
  viewing = false,
  onSelect,
  onHoverCard,
  locked = false,
}: Props) {
  const images = useUiStore((s) => s.images);
  const seatImages = useUiStore((s) => s.seatImages);
  const muster = musterOf(state, player.pid);

  /*
   * The seat's ground and its window are one image at two treatments.
   *
   * The same `commandersOf` and `artUrl` the orb and the plinth already call,
   * so this is a second reference to a URL the browser has cached rather than a
   * second request. `undefined` (map not fetched) and `null` (no printing) both
   * mean draw no art: the seat falls back to its flat well, which is a
   * perfectly good seat and is what it looked like before this direction.
   */
  const commanders = commandersOf(state, player.pid);
  const commander = commanders[0];
  const art = commander ? artUrlFor(images, seatImages, commander) : undefined;

  /*
   * Commander damage, as two arrows riding this seat's own life bar.
   *
   * A Commander player watches two clocks per opponent and they run in
   * opposite directions: how close *their* commander is to killing *you*, and
   * how close *yours* is to killing *them*. What this seat used to draw was
   * neither -- it was the worst damage this seat had taken from *anybody*,
   * which in a pod is most often a number about two other players.
   *
   * So one arrow per direction, each parked at its own fraction of 21 along
   * the track: yours pointing down off the top edge, theirs pointing up off
   * the bottom. Distance travelled is progress toward lethal, and a length
   * survives `e2e/greyscale.spec.ts` where a hue does not -- the edge and the
   * direction are a second and third channel on top of it.
   *
   * The numbers themselves are on the gauge's `data-hint`, for the same reason
   * everything else in this component puts them there: a 22px row cannot hold
   * two more numerals at the 16px floor, and the hint bar surfaces them from
   * the cursor as well as from the pointer.
   */
  const viewer = state.players.find((seat) => seat.pid === state.seat);
  /** What the viewer's commander has done to this seat. */
  const dealt = player.commander_damage_taken[String(state.seat)] ?? 0;
  /** What this seat's commander has done to the viewer. */
  const taken = viewer?.commander_damage_taken[String(player.pid)] ?? 0;

  const arrows = [
    {
      key: "dealt",
      amount: dealt,
      label: `you have dealt ${dealt} of ${COMMANDER_LETHAL} commander damage to ${player.name}`,
    },
    {
      key: "taken",
      amount: taken,
      label: `${player.name} has dealt ${taken} of ${COMMANDER_LETHAL} commander damage to you`,
    },
  ];

  const gaugeLabel = `${player.life} life of ${STARTING_LIFE} — ${
    dealt === 0 && taken === 0
      ? "no commander damage either way"
      : `${arrows[0].label}; ${arrows[1].label}`
  }`;

  /*
   * FOCUSING THE SEAT READS THEIR COMMANDER, the way hovering its window does.
   *
   * The window's `mouseenter` below was the only route into the reader from a
   * seat, and the ring never enters a child span: it stands on the seat's own
   * button, because that is what `data-stop="orb:<pid>"` names. So on a Deck
   * the most-asked question across the table -- what is that deck about --
   * could be answered at full screen with `Y` and not at all in the rail, and
   * the rail is the one that stays up while you decide.
   *
   * `data-preview-oid` is the half that matters, and it is the plinth's
   * argument verbatim (`CommandZone.tsx`): `input/cursor.ts`'s `hoverFor` runs
   * AFTER the ring has moved DOM focus, so whatever `onFocus` wrote is
   * overwritten by what the stop declares -- a seat that declared nothing went
   * blank the instant it was reached. The attribute makes the ring and the
   * pointer one fact.
   *
   * `onFocus` is for focus that does not come from the ring, and it stands down
   * in mouse mode. A click focuses the button too, and a pointer player who
   * clicked the seat to read their board is pointing at the board next, not at
   * this commander -- the rail pinned to a card nobody is on is open defect #4
   * in `docs/design-record.md` again. The pointer already has the window.
   *
   * `onBlur` clears only what this seat wrote. Blur fires on the mousedown of
   * the NEXT click, by which time the pointer has already put whatever it is
   * over into the rail, and clearing blind would blank a preview that is right.
   */
  const reading = commander?.oid ?? null;
  const focusReads =
    reading === null
      ? {}
      : {
          onFocus: () => {
            if (getInputMode() !== "mouse") onHoverCard?.(reading);
          },
          onBlur: () => {
            if (useUiStore.getState().hoveredOid === reading) onHoverCard?.(null);
          },
          "data-preview-oid": reading,
        };

  const classes = [
    "seat",
    isActive ? "seat--active" : "",
    targetable ? "seat--targetable" : "",
    viewing ? "seat--viewing" : "",
    player.has_lost ? "seat--out" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.button
      type="button"
      className={classes}
      data-player={player.pid}
      data-stop={stopId.orb(player.pid)}
      data-testid={`player-${player.pid}`}
      data-seat={player.pid}
      disabled={locked}
      onClick={onSelect ? () => onSelect(player.pid) : undefined}
      {...focusReads}
      layout
      transition={bouncy}
      whileHover={targetable ? { scale: 1.02 } : undefined}
    >
      {/*
        Two layers rather than one blended one, which is `PlayerOrb`'s argument
        arriving here: tinting the scrim itself lifts the whole seat toward the
        art's dominant colour and takes the name with it, so the veil is
        unconditionally dark and no type here depends on what the painting
        happens to look like.
      */}
      {typeof art === "string" && (
        <>
          {/* Quoted, because an unquoted `url()` gives parentheses and
              whitespace meaning, and the deck importer mints ids from names it
              did not choose. */}
          <span
            className="seat__ground"
            style={{ backgroundImage: `url("${art}")` }}
            aria-hidden="true"
          />
          <span className="seat__veil" aria-hidden="true" />
        </>
      )}

      {/* Whose turn it is and who holds priority are two different facts, and
          the shipped ribbon ran them together into one highlighted name. The
          ring is the turn; this tick is priority. */}
      {hasPriority && <span className="seat__pri" aria-hidden="true" />}

      {/*
        The crisp window. The ground is the same painting veiled to nothing;
        this is the half somebody can recognise.

        Hovering it fills the reader with their commander, which is most of why
        anybody looks at an opponent's panel -- "what is that deck about" is one
        card's text. `Y` does the same thing for a controller, at full size, and
        both are reads rather than actions: no `data-action-id`, and nothing
        here changes the game.

        `aria-hidden` on the picture and not on the handlers: the seat's own
        button carries the accessible name, and a decorative image inside it
        should not announce itself twice.
      */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: a pointer-only hover affordance. The pad and the keyboard reach the same preview through the focus ring, which is why `useKeyWithClickEvents` is off in biome.json for the same reason. */}
      <span
        className="seat__win"
        onMouseEnter={commander ? () => onHoverCard?.(commander.oid) : undefined}
        onMouseLeave={commander ? () => onHoverCard?.(null) : undefined}
      >
        {typeof art === "string" && <img src={art} alt="" aria-hidden="true" />}
      </span>

      <span className="seat__head">
        <span className="seat__name">{player.name}</span>
        <span className="seat__cmdr">{commander?.name ?? ""}</span>
      </span>

      <span
        className="gauge"
        style={
          { "--fill": `${Math.min(player.life / STARTING_LIFE, 1) * 100}%` } as CSSProperties
        }
        aria-label={gaugeLabel}
        data-hint={gaugeLabel}
      >
        <span className="seat__life tabular" data-testid={`life-${player.pid}`}>
          {player.has_lost ? "OUT" : player.life}
        </span>
        {/*
          The two arrows, in their own inset track.

          Inset by the arrow's half-width so a source at 21 parks its point on
          the end of the bar rather than half outside it -- `.gauge` clips, and
          a mark that says "lethal" is the last one that should be cut in half.

          Zero draws nothing. An absolutely positioned mark costs no layout, so
          the reflow argument that keeps the seat's other cells at zero does not
          apply, and two arrows stacked on the left edge at the start of every
          game would be two marks saying nothing.
        */}
        <span
          className="cmdarrows"
          data-testid={`cmddmg-${player.pid}`}
          data-dealt={dealt}
          data-taken={taken}
          aria-hidden="true"
        >
          {arrows.map((arrow) =>
            arrow.amount > 0 ? (
              <span
                key={arrow.key}
                className={`cmdarrow cmdarrow--${arrow.key}${
                  arrow.amount >= COMMANDER_WARN ? " cmdarrow--warn" : ""
                }`}
                style={
                  {
                    "--at": `${
                      (Math.min(arrow.amount, COMMANDER_LETHAL) / COMMANDER_LETHAL) * 100
                    }%`,
                  } as CSSProperties
                }
                data-cmddmg={arrow.key}
                data-amount={arrow.amount}
              />
            ) : null,
          )}
        </span>
      </span>

      <span className="seat__perms">
        <PermCell
          kind="land"
          total={muster.lands}
          open={muster.landsUntapped}
          label={`${muster.lands} ${muster.lands === 1 ? "land" : "lands"} — ${
            muster.landsUntapped
          } untapped, ${muster.lands - muster.landsUntapped} tapped`}
        />
        <PermCell
          kind="creature"
          total={muster.creatures}
          open={muster.creaturesUntapped}
          label={`${muster.creatures} ${muster.creatures === 1 ? "creature" : "creatures"} — ${
            muster.creaturesUntapped
          } untapped, ${muster.creatures - muster.creaturesUntapped} tapped`}
        />
        <PermCell
          kind="other"
          total={muster.other}
          open={null}
          label={
            muster.other === 0
              ? "No artifacts or enchantments"
              : muster.other === 1
                ? "1 artifact or enchantment"
                : `${muster.other} artifacts or enchantments`
          }
        />
        <DetailCell muster={muster} />
      </span>

      {/*
        The zones, as marks rather than as controls.

        `PlayerOrb` makes each pile a button, because on your own column they
        are the only route into `ZonePeek`. A seat is 96px tall and the row it
        can spare is 20 -- a 44px hit target does not fit, and faking one with a
        transparent overlay would steal presses from the gauge and the counts
        above it. So the marks report, and the way into an opponent's zones is
        to read their board: press the seat.

        They keep `pile-<pid>-<zone>` so the counts stay queryable, and they are
        text inside the seat's own button, which a reader announces with it.
      */}
      <span className="seat__zones">
        {zonesOf(player).map((zone) => (
          <span
            key={zone.zone}
            className={`zmark zmark--${zone.kind}${zone.count === 0 ? " zmark--empty" : ""}`}
            data-testid={`pile-${player.pid}-${zone.zone}`}
            aria-label={`${zone.label}: ${zone.count}`}
            data-hint={`${zone.label}: ${zone.count}`}
          >
            <SeatIcon name={zone.kind as SeatIconName} />
            <span className="zmark__n tabular">{zone.count}</span>
          </span>
        ))}
      </span>

      {player.has_lost && <span className="seat__out">{lossReason(player.loss_reason)}</span>}
    </motion.button>
  );
}
