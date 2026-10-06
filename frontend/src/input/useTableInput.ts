/**
 * `Table`'s input bindings: every pad button, and the keyboard shortcuts.
 *
 * Two effects lifted out of `Table.tsx` as they were. They read a dozen of the
 * component's callbacks and values between them, which is why they are the
 * last thing that left; both take those as one options object so the bodies
 * -- and their dependency lists -- could move verbatim.
 *
 * THIS FILE IS SCANNED. `tests/hintsBound.test.ts` reads the source of every
 * file that binds a pad intent and checks each button the hint bar advertises
 * is bound somewhere, so a binding may not hide in a file that list does not
 * name. Keep every `onPad(...)` here.
 */

import { useEffect } from "react";
import type { CardView, GameView, LegalAction } from "../api/types";
import type { SoundName } from "../audio/sfx";
import { parseStop } from "../logic/verbs";
import { commandersOf, findCard } from "../logic/zoneGrouping";
import type { PeekTarget } from "../state/uiStore";
import type { useGame } from "../state/useGame";
import { getCursor, readingOid, setCursor } from "./cursor";
import { onAny as onAnyPad, on as onPad } from "./pad";
import { stopId } from "./stops";

/** Keyboard routes into the zone viewer, which previously had none. */
const PEEK_KEYS: Record<string, PeekTarget["zone"]> = {
  g: "graveyard",
  e: "exile",
  c: "command",
};

export interface PadBindingsInput {
  back: () => void;
  secondary: () => void;
  stepGroup: (step: 1 | -1) => void;
  jumpToCommit: () => void;
  toggleLogOverlay: () => void;
  narration: ReturnType<typeof useGame>["narration"];
  skipAll: () => void;
  heldCard: number | null;
  setHeldCard: (oid: number | null) => void;
  cue: (sound: SoundName) => void;
  state: GameView;
}

/** Every pad button `Table` answers, bound for the life of the board. */
export function usePadBindings({
  back,
  secondary,
  stepGroup,
  jumpToCommit,
  toggleLogOverlay,
  narration,
  skipAll,
  heldCard,
  setHeldCard,
  cue,
  state,
}: PadBindingsInput): void {
  useEffect(() => {
    const unbind = [
      onPad("b", back),
      onPad("x", secondary),
      /*
       * A tap steps, a hold opens the dial.
       *
       * `pad.ts` reports a press and this app has no release event, so the hold
       * is a timer started on the press and cancelled by the next press of
       * anything -- which `onAnyPad` below does. A tap therefore steps
       * immediately AND arms a timer that the tap itself cancels; a hold leaves
       * the timer to fire.
       */
      onPad("l1", () => stepGroup(-1)),
      onPad("r1", () => stepGroup(1)),
      /*
       * `Y` reads the card in the rail, full screen.
       *
       * THE RAIL FIRST, AND THEN THE RING. `cursor.ts:readingOid` is the card
       * the reader is showing, which on a pad is the ring's card -- including a
       * panel row's or a seat's `data-preview-oid`, the case this binding used
       * to `deny` (TECH_DEBT FB-08) -- and with a mouse is the card under the
       * pointer. That second half is the desktop's way in: `i` is this button,
       * and a desktop player has no visible ring, so before this a mouse user
       * pressing `i` over a card got whatever the invisible cursor last rested
       * on. The two branches below stay as the fallback for a rail that is
       * empty while the ring stands on something readable.
       *
       * `logic/verbs.ts` has returned `Y Read` on every card stop since it was
       * written and nothing was ever bound to it. An advertised button that
       * does nothing is worse than an unadvertised one: it teaches the player
       * that the hint bar is not to be trusted.
       */
      onPad("y", () => {
        const shown = readingOid();
        if (shown !== null && findCard(state, shown) !== null) {
          setHeldCard(shown);
          return;
        }
        const ref = parseStop(getCursor());
        if (ref.kind === "card" && ref.id !== null) {
          setHeldCard(ref.id);
          return;
        }
        /*
         * On a SEAT, `Read` means their commander.
         *
         * `verbsFor` returns `Y Read` for an orb stop as well as for a card,
         * and a bar that promises a verb the button does not have is the exact
         * defect this whole binding exists to close -- so the seat answers the
         * only question it could be asking. In Commander the deck IS the
         * commander, and a seat you are deciding whether to attack is one whose
         * commander's text you want.
         */
        if (ref.kind === "orb" && ref.id !== null) {
          const commander = commandersOf(state, ref.id)[0];
          if (commander) {
            setHeldCard(commander.oid);
            return;
          }
        }
        cue("deny");
      }),
      // `View` is the log and `Menu` jumps the ring to the tool strip. Neither
      // renders a control of its own: they flip a flag an existing surface
      // already reads, or move the ring to a button that already exists. That
      // is what keeps `data-action-id` and `data-testid` unique for free.
      onPad("view", toggleLogOverlay),
      // The strip's first stop, which is the settings menu now that sound, undo
      // and quit live inside it. It was `tool:mute`, and a stop that only
      // exists while a menu is open is a jump that does nothing four times out
      // of five.
      onPad("menu", () => {
        setCursor(stopId.tool("settings"));
      }),
      /*
       * A PRESS jumps to the commit slab, and HOLDING it opens the region dial
       * (the `onPadFrame` above). The two do not collide: a tap crosses and
       * releases the analog threshold inside a frame or two, which is over long
       * before the dial is worth looking at. See `jumpToCommit`.
       */
      onPad("l2", jumpToCommit),
      /*
       * Any press ends a hold and puts a held card down.
       *
       * `pad.ts` reports presses and has no release event, so "held" here means
       * "until you do something else" -- which is how it behaves in practice
       * anyway, because the thing you do next is the thing you were reading the
       * card in order to decide.
       */
      onAnyPad((button) => {
        if (narration.busy) skipAll();
        if (button !== "y" && heldCard !== null) setHeldCard(null);
      }),
    ];
    return () => {
      for (const off of unbind) off();
    };
  }, [
    back,
    secondary,
    toggleLogOverlay,
    narration.busy,
    skipAll,
    stepGroup,
    jumpToCommit,
    heldCard,
    setHeldCard,
    cue,
    state,
  ]);
}

export interface KeyboardShortcutsInput {
  actions: LegalAction[];
  act: (actionId: string) => void;
  gateInput: () => boolean;
  narration: ReturnType<typeof useGame>["narration"];
  skipAll: () => void;
  setPeek: (target: PeekTarget | null) => void;
  peek: PeekTarget | null;
  playFromHand: (card: CardView) => void;
  viewer: { hand: CardView[] | null };
  undoMutate: () => void;
  state: GameView;
}

/** The desktop shortcuts: zone peeks, Space to pass, U to undo, 1-9 to play. */
export function useKeyboardShortcuts({
  actions,
  act,
  gateInput,
  narration,
  skipAll,
  setPeek,
  peek,
  playFromHand,
  viewer,
  undoMutate,
  state,
}: KeyboardShortcutsInput): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

      /*
       * `Escape` is handled as the pad's `B` rather than here.
       *
       * It used to cancel targeting and close the zone viewer in one go. `B` is
       * a strict unwind instead -- peek, then targeting, then selection -- which
       * is the behaviour a back button needs in order to be predictable, and
       * which is now the same code whether the player pressed Escape,
       * Backspace, or B on a controller. One button, one implementation.
       */
      if (narration.busy && event.key !== "Escape") {
        skipAll();
        return;
      }
      /*
       * Zone peeking. `Esc` closed it and nothing opened it, so the only route
       * in was a chip on the orb. Placed before `gateInput` on purpose: looking
       * at your own graveyard asks the server nothing, so there is no reason to
       * refuse it while a request is in flight.
       */
      const peekZone = PEEK_KEYS[event.key.toLowerCase()];
      if (peekZone) {
        setPeek(peek?.zone === peekZone ? null : { pid: state.seat, zone: peekZone });
        return;
      }

      if (gateInput()) return;

      if (event.key === " ") {
        const pass = actions.find((a) => a.kind === "pass");
        if (pass) {
          event.preventDefault();
          act(pass.id);
        }
        return;
      }
      /*
       * `Enter` is deliberately not handled here any more.
       *
       * It is bound to the pad's `A`, which presses whatever the ring is on --
       * and the ring rests on the commit slab whenever a decision is pending,
       * so the same keystroke still confirms. Keeping this branch as well made
       * one press post two actions: this one took the first `keep`/`yes`/
       * `finish_declaration` in the list while `confirm()` posted the button
       * under the ring.
       *
       * It is also strictly better than what it replaced. The old branch could
       * only ever confirm those three kinds; `A` presses the control the player
       * is actually looking at, which is every kind.
       */
      if (event.key.toLowerCase() === "u") {
        undoMutate();
        return;
      }
      if (/^[1-9]$/.test(event.key)) {
        const card = viewer.hand?.[Number(event.key) - 1];
        if (card) playFromHand(card);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    actions,
    act,
    gateInput,
    narration,
    skipAll,
    setPeek,
    playFromHand,
    viewer.hand,
    undoMutate,
    peek,
    state.seat,
  ]);
}
