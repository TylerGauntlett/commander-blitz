/**
 * The foot of the table: the hand, the hint bar, the regions button, and the
 * host the compact tool strip portals into.
 *
 * Lifted out of `Table.tsx`'s render as it was. Everything here is drawn from
 * values `Table` owns and hands down -- the fit the zoom solver found, the
 * selection, the targeting state -- which is why the props list is long and
 * the component has no state of its own.
 */

import type { RefObject } from "react";
import type { CardView, GameView, LegalAction, PlayerView } from "../../api/types";
import { stopId } from "../../input/stops";
import { targetHint } from "../../logic/targetHint";
import { useUiStore } from "../../state/uiStore";
import type { useZoomFit } from "../../state/useZoomFit";
import { Glyph } from "../ui/Glyph";
import { HandFan } from "./HandFan";
import { HintBar } from "./HintBar";

interface Props {
  footRef: RefObject<HTMLDivElement | null>;
  handheld: boolean;
  state: GameView;
  actions: LegalAction[];
  viewer: PlayerView;
  targeting: LegalAction[];
  /** What the targeting can land on, for the hint about the hovered card. */
  targetableOids: ReadonlySet<number>;
  targetChosen: boolean;
  endTargeting: () => void;
  playableOids: ReadonlySet<number>;
  selectedOid: number | null;
  zoom: ReturnType<typeof useZoomFit>;
  locked: boolean;
  viewing: number | null;
  setDialOpen: (open: boolean) => void;
  playFromHand: (card: CardView) => void;
  onDropOnZone: (card: CardView, zone: string) => void;
}

export function TableFoot({
  footRef,
  handheld,
  state,
  actions,
  viewer,
  targeting,
  targetableOids,
  targetChosen,
  endTargeting,
  playableOids,
  selectedOid,
  zoom,
  locked,
  viewing,
  setDialOpen,
  playFromHand,
  onDropOnZone,
}: Props) {
  // The pointer and the ring both write `hoveredOid` (`input/cursor.ts`'s
  // `hoverFor`), so one subscription answers a mouse, a keyboard and a pad.
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const hint = targetChosen ? null : targetHint(state, targeting, targetableOids, hoveredOid);
  return (
    <div className="table__foot" ref={footRef}>
      {/*
      Where the tool strip goes on a handheld. A host, not the controls
      themselves.

      What goes in it depends on `ActionPanel`'s own decision state, so
      rebuilding it here would be a second implementation of controls the
      turn is waiting on. `ActionPanel` finds this by class and portals its
      real tool row into it, so there is exactly one in the document and
      every `data-action-id`, `data-testid` and ring stop travels with it.

      THE COMMIT SLAB USED TO HAVE A HOST HERE TOO. It does not need one any
      more: the rail runs the full height of the screen, so the 65px the
      slab costs is affordable there -- and under the list it commits is
      where it belongs, rather than in the corner beside the hand.

      Rendered only on a handheld. On a desktop the tools stay in the rail,
      where 304px of width and a 950px-tall screen make them the right
      shape; here the foot's row is 1017px and they are one line rather than
      the three a 200px column wrapped them to.
    */}
      {handheld && <div className="foot__tools" />}

      {/*
      THE DIAL NEEDED A BUTTON, because holding `L2` was the only way in.

      A Steam Deck in gaming mode hands the page a keyboard rather than a
      gamepad, so `L2` -- and `z`, its keyboard stand-in -- arrive as nothing
      at all. The region dial was therefore unreachable on the one device it
      was designed for. The ring can now walk out of a region at its edge
      (`input/stops.ts:escapeGroup`), so this is a shortcut rather than the
      only road, but a jump the hint bar advertises should have a surface.

      A `tool:` stop and no `data-action-id`: it flips a flag on a surface
      that already exists, which is what keeps the panel's "every legal
      action is a button, exactly once" invariant free.
    */}
      <button
        type="button"
        className="foot__regions"
        onClick={() => setDialOpen(true)}
        aria-label="Jump to a region"
        data-stop={stopId.tool("regions")}
        data-testid="regions"
        data-hint="Jump to a region of the board"
      >
        <Glyph btn="l2" />
        Regions
      </button>

      {/*
      What the buttons do, for whoever is holding one.

      `display: none` unless `html[data-input]` says a pad or a keyboard is
      driving, so a mouse player's foot is exactly the row it has always
      been -- no extra height, no reserved space, nothing to read. See
      `components/ui/Glyph.tsx`.
    */}
      <HintBar state={state} actions={actions} />

      {/*
      One hint, never a second copy of the actions.

      This used to be two blocks, and the first rendered every remaining
      action as a `data-action-id` button -- the same ids `ActionPanel`
      renders from `playRows`, which does *not* stand down for targeting.
      Two controls, one id: exactly what the panel's invariant forbids. It
      escaped CI only because no shipped card could reach it, and manual
      mana (Stage 2) reaches it immediately. The panel owns the choice; the
      foot only ever says what the click is for.
    */}
      {/*
        The label also answers "why won't this click". A card the targeting
        cannot land on is still focusable -- the ring has to be able to pass
        over it -- so pointing at one names the reason here rather than doing
        nothing. `aria-live` so a screen reader hears it on focus too. See
        `logic/targetHint.ts` for where each reason comes from.
      */}
      {targeting.length > 0 && (
        <div className="choices" data-testid={targetChosen ? "variant-hint" : "targeting-hint"}>
          <span
            className={
              hint?.refused ? "choices__label choices__label--refused" : "choices__label"
            }
            data-testid="targeting-reason"
            aria-live="polite"
          >
            {targetChosen ? "Pick how, in the panel" : (hint?.text ?? "Pick a target")}
          </span>
          <button type="button" className="btn btn--ghost" onClick={endTargeting}>
            Cancel (Esc)
          </button>
        </div>
      )}

      {/*
      The hand owns the foot outright.

      The commander used to sit to its left, on the theory that a zone you
      play from belongs beside the other zone you play from. In practice it
      put the format's defining card in the corner where nothing important
      goes, at a size where its own name did not fit. It is the hero of the
      player's info panel now -- see `CommandZone` and `PlayerOrb` -- and it
      still casts by the same click on the same `playFromHand` path.
    */}
      <HandFan
        cards={viewer.hand ?? []}
        playableOids={playableOids}
        reasons={viewer.hand_reasons ?? {}}
        mana={viewer.mana}
        selectedOid={selectedOid}
        cardScale={zoom.hand}
        fanWidth={zoom.fanW}
        onActivate={playFromHand}
        onDropOn={onDropOnZone}
        // Your lanes are not on screen while you are reading somebody
        // else's, so there is nowhere legal to drop.
        disabled={locked || viewing !== null}
      />
    </div>
  );
}
