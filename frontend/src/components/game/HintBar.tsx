/**
 * What each button would do, right now.
 *
 * A mouse tells you what a click will do before you click, by where the pointer
 * is and what changes under it. A ring tells you where you are and nothing
 * about what happens next -- so on a controller the verb has to be written
 * down, and this is where.
 *
 * ## It renders spans, never buttons
 *
 * THE INVARIANT THIS PROTECTS: every legal action is a control carrying
 * `data-action-id`, exactly once in the document (`ActionPanel`'s header). A
 * hint bar that rendered pressable rows would be a second copy of the action
 * space, would duplicate ids, and would fail `e2e/clarity.spec.ts` across a
 * whole game. So this is *text about the ring*, carries no id and no
 * `data-stop`, and is not reachable -- exactly the discipline the targeting
 * hint in `Table.tsx` already follows.
 *
 * ## It names buttons, and nothing else
 *
 * IT USED TO ALSO ECHO `data-hint` off whatever the ring was on -- the string
 * the 43 native `title` attributes became. That line was the widest thing in
 * the bar and the only one whose length was unbounded, so it wrapped the row
 * onto a second line and grew the foot underneath the hand, moving every tool
 * button mid-decision. The attributes stay where they are, because
 * `tests/noTooltips.test.ts` is what keeps `title` off this app, but the bar
 * shows verbs only and is therefore exactly one line tall, always.
 *
 * ## It subscribes to the cursor, and it is allowed to
 *
 * `input/cursor.ts` says no component subscribes to the cursor, because thirty
 * cards doing so is what costs the frame rate. This is one of the two
 * deliberate exceptions -- a single leaf component at the edge of the tree,
 * rendering a handful of spans. Re-rendering it per step is a rounding error
 * next to re-rendering the board, and it is the whole reason the ring is worth
 * having.
 */

import { useSyncExternalStore } from "react";
import type { GameView, LegalAction } from "../../api/types";
import { getCursor, subscribeCursor } from "../../input/cursor";
import { NAVIGATION_HINTS, type Verbs, verbsFor } from "../../logic/verbs";
import { useUiStore } from "../../state/uiStore";
import { Glyph } from "../ui/Glyph";

interface Props {
  state: GameView;
  actions: LegalAction[];
}

/** One `[btn] verb` pair. A span, never a control. */
function Hint({ btn, label }: { btn: Parameters<typeof Glyph>[0]["btn"]; label: string }) {
  return (
    <span className="hint">
      <Glyph btn={btn} />
      <span className="hint__verb">{label}</span>
    </span>
  );
}

export function HintBar({ state, actions }: Props) {
  // `useSyncExternalStore` rather than an effect: the cursor is module state,
  // and this is the supported way to read a value React does not own without
  // tearing during a concurrent render.
  const cursor = useSyncExternalStore(subscribeCursor, getCursor, () => null);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const selectedOid = useUiStore((s) => s.selectedOid);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);

  const verbs: Verbs = verbsFor(state, actions, cursor, {
    stagedAttacks,
    stagedBlocks,
    selectedOid,
    targeting: targetingActionIds.length > 0,
  });

  return (
    <div className="hints" data-testid="hint-bar">
      <Hint btn="dpad" label={NAVIGATION_HINTS[0].label} />
      <Hint btn="a" label={verbs.a} />
      {verbs.x && <Hint btn="x" label={verbs.x} />}
      {verbs.y && <Hint btn="y" label={verbs.y} />}
      {verbs.b && <Hint btn="b" label={verbs.b} />}
      {/*
        The navigation half is constant, and it is separated because it answers
        a different question. The verbs above change with every step and are
        about *this* stop; these are about the board, and a player learns them
        once. Grouping them keeps the changing half short enough to read at a
        glance mid-decision.
      */}
      {/*
        Rendered FROM `NAVIGATION_HINTS`, not restated.
        
        These were two hard-coded `Hint`s, and the list they were supposed to be
        showing sat unread in `logic/verbs.ts` -- so changing the list changed
        nothing and the bar went on advertising a button that had been renamed.
        One source, and `tests/verbs.test.ts` holds it.
      */}
      <span className="hints__nav">
        {NAVIGATION_HINTS.filter((nav) => nav.btn !== "dpad").map((nav) => (
          <Hint key={nav.btn} btn={nav.btn} label={nav.label} />
        ))}
      </span>
    </div>
  );
}
