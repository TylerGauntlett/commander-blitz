/**
 * One panel for every decision.
 *
 * This replaces two surfaces that used to sit in the rail together: `ActionBar`,
 * which rendered every legal action as a pill, and `CombatPanel`, which rendered
 * one chip per legal *pair* plus a separate staged-summary list and stood the bar
 * down while it was open. Between them a player had three different shapes to
 * learn for what is always the same question -- "what can I do, and which of it
 * am I doing" -- and combat had the worst of them: in a pod the chip cloud was
 * attackers x opponents, and declaring a block took two clicks in a fixed order
 * with nothing on screen saying what the block would achieve.
 *
 * THE INVARIANT THIS INHERITS. `ActionBar`'s contract was that every legal action
 * is a button carrying `data-action-id`, exactly once in the document -- dragging
 * and clicking cards are ergonomic shortcuts for picking an action out of this
 * list, and when a gesture and this panel disagree, this panel is right. That
 * contract moved here wholesale. `e2e/clarity.spec.ts` and
 * `e2e/action-panel.spec.ts` both fail the run if an id appears twice or goes
 * missing, and two rules below exist only to protect it:
 *
 *   - the action promoted to the commit slab is filtered out of the list, or it
 *     would render twice;
 *   - an attacker with several legal defenders puts the ids on its defender
 *     chips and carries none itself, so the N ids for N defenders land on N
 *     controls rather than sharing one.
 *
 * THE ONE EXCEPTION, and it is deliberate: `choose_x`. `ask_x` offers every
 * value from 0 up to whatever the board can pay for, so a Fireball on ten mana
 * is eleven legal actions that differ by a number. Drawing eleven buttons would
 * satisfy the letter of the invariant and destroy the point of it, so the panel
 * draws a stepper and only the *selected* value carries an id. "Exactly once"
 * still holds -- no id is duplicated, and there is always at least one button,
 * which is what `e2e/full-game.spec.ts` actually depends on.
 *
 * Staging stays client-side, for the reason `Table.onBarAct` documents: posting
 * `add_blocker` one at a time has no inverse, and a single blocker committed onto
 * a menace attacker can strand the declaration with no legal `finish_declaration`
 * at all. Nothing here reaches the server until the commit slab is pressed.
 */

import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { CardView, GameView, LegalAction } from "../../api/types";
import {
  availableAttackers,
  availableBlockers,
  defendersFor,
  groupPlayActions,
} from "../../logic/actionMatch";
import { sensibleAttacks } from "../../logic/autoAttack";
import { autoBlocks } from "../../logic/autoBlock";
import { statLine } from "../../logic/cardStyle";
import { decisionPrompt, thinkingLabel } from "../../logic/labels";
import { findCard } from "../../logic/zoneGrouping";
import { ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { useHandheldLayout } from "../../state/useHandheld";
import { AttackRows } from "./AttackRows";
import { BlockGroups } from "./BlockGroups";
import { CommitDock } from "./CommitDock";
import { PlayRows } from "./PlayRows";
import { ToolStrip } from "./ToolStrip";
import { XStepper } from "./XStepper";

/**
 * Actions big enough to be the slab rather than a row.
 *
 * Only one is ever promoted, and it is then *excluded* from the list -- see the
 * id invariant above. Mulligans and modal choices never reach here: those are
 * `isModalDecision`, and the panel stands its list down for them entirely.
 */
const COMMIT_KINDS = ["keep", "yes", "pass"];

type Mode = "attack" | "block" | "play" | "chooseX";

interface Props {
  state: GameView;
  actions: LegalAction[];
  /** Post an action id to the server. */
  onAct: (actionId: string) => void;
  /** Stage or unstage one combat pair, locally. */
  onStage: (actionId: string) => void;
  onDeclare: (kind: "attackers" | "blockers", pairs: [number, number][]) => void;
  onUndo: () => void;
  onQuit: () => void;
  onToggleFullControl: (value: boolean) => void;
  onToggleManualMana: (value: boolean) => void;
  /** Narration is playing: gate input rather than let a click land mid-flight. */
  narrating: boolean;
  onSkipNarration: () => void;
  busy: boolean;
  aiThinking: boolean;
  /** Another person is deciding; name them the way an AI on the clock is named. */
  waitingForPlayer?: boolean;
  /**
   * A modal owns the decision, so the list renders no action ids at all.
   *
   * The prompt and the tools stay in the document. Note they are not *reachable*
   * while a dialog is up: `.prompt-backdrop` is fixed at `inset: 0` above
   * everything and swallows the clicks. That predates this panel and is recorded
   * in docs/design-record.md (Open fidelity findings) rather than worked around here.
   */
  standDown: boolean;
}

export function ActionPanel({
  state,
  actions,
  onAct,
  onStage,
  onDeclare,
  onUndo,
  onQuit,
  onToggleFullControl,
  onToggleManualMana,
  narrating,
  onSkipNarration,
  busy,
  aiThinking,
  waitingForPlayer = false,
  standDown,
}: Props) {
  /*
   * Where the tool strip actually goes.
   *
   * On a handheld the five utility controls leave this panel: at the 44px hit
   * floor they wrap to three rows in a 200px column -- 101px, pinned, of a 252px
   * panel -- while the action list underneath sat at its 74px floor clipping
   * the choices the turn was waiting on. `Table` renders `.foot__tools` in the
   * foot and they are portalled there, where the row is 1017px wide and they
   * are one line.
   *
   * THE COMMIT SLAB CAME BACK. It left for the same reason and the reason no
   * longer holds: the rail runs the full height of the screen now, 748px rather
   * than 514, so the 65px the slab costs is affordable and the list still comes
   * out at 363-398. Putting it back is also the arrangement
   * the handheld-board round (`docs/design-record.md#handheld-board`) draws and the one that reads better -- the thing
   * you press to end a decision belongs under the list of that decision, not in
   * the corner of the hand.
   *
   * PORTALLED, NOT DUPLICATED. The node is the same node, so every
   * `data-action-id`, `data-testid` and ring stop travels with it and this
   * panel's one-control-per-action invariant holds. A second copy of the tree
   * would break it on the first render.
   *
   * FOUND, NOT PASSED IN, and that is a deliberate second version. It was two
   * props threaded from `Table` through a ref-into-state dance, which worked in
   * the app and made every `ActionPanel` story wrong: a story renders the panel
   * without a `Table`, so it got no hosts and drew the slab inline -- showing an
   * arrangement the handheld app does not have. Looking the hosts up means any
   * surface that renders a foot gets the real thing, and `mounts.tsx` can supply
   * one without inventing a way to pass refs through a class-name chain.
   *
   * Scoped with `closest(".table")` rather than the document, so two boards on
   * one page (the docs view renders several stories at once) cannot portal into
   * each other's foot.
   */
  const anchorRef = useRef<HTMLElement>(null);
  const handheld = useHandheldLayout();
  const [hosts, setHosts] = useState<{ slab: HTMLElement | null; tools: HTMLElement | null }>({
    slab: null,
    tools: null,
  });
  useEffect(() => {
    if (!handheld) {
      setHosts((c) => (c.slab || c.tools ? { slab: null, tools: null } : c));
      return;
    }
    // The foot is rendered by the same commit that renders this panel, so by the
    // time an effect runs the nodes exist. Scoped to this board.
    const scope = anchorRef.current?.closest(".table") ?? document;
    const tools = scope.querySelector<HTMLElement>(".foot__tools");
    // `slab` stays null at every size: the dock renders in place, in the rail,
    // under the list it commits. `dock()` below is the one that reads it, and a
    // null host means "leave it where it is".
    setHosts((c) => (c.slab === null && c.tools === tools ? c : { slab: null, tools }));
  }, [handheld]);

  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const stageAttack = useUiStore((s) => s.stageAttack);
  const stageBlock = useUiStore((s) => s.stageBlock);
  const hover = useUiStore((s) => s.hover);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);

  const disabled = busy || narrating;
  const pending = state.pending;
  const mine = pending !== null && pending.player === state.seat && !state.game_over;
  const mode: Mode =
    mine && pending.kind === "declare_attackers"
      ? "attack"
      : mine && pending.kind === "declare_blockers"
        ? "block"
        : mine && pending.kind === "choose_x"
          ? "chooseX"
          : "play";
  const isCombat = mode === "attack" || mode === "block";

  const card = (oid: number): CardView | null => findCard(state, oid);
  const nameOf = (oid: number) => card(oid)?.name ?? `#${oid}`;

  // ------------------------------------------------------------------ X
  //
  // A stepper rather than a row of buttons: `ask_x` offers every value from 0
  // to whatever the board can pay for, which is up to 21 options for one
  // question, and a wall of near-identical pills is not a choice anybody can
  // read. The trade is that only the *selected* value carries a
  // `data-action-id` -- see the note on the id invariant at the top of this
  // file, where this is the one deliberate exception.
  const maxX = mode === "chooseX" ? Number(pending?.context?.max_x ?? 0) : 0;
  const perPoint = mode === "chooseX" ? Number(pending?.context?.per_point ?? 1) : 1;
  // A fresh question starts at zero rather than at the last spell's answer.
  // Stored with the question it belongs to and reset during render rather than
  // in an effect -- React's own "adjusting state when a prop changes" pattern,
  // and it avoids a frame where the previous spell's X is on screen. Keyed on
  // the prompt and the ceiling because a decision has no id of its own.
  const xKey = `${pending?.kind}:${pending?.prompt}:${maxX}`;
  const [xAnswer, setXAnswer] = useState({ key: xKey, value: 0 });
  const chosenX = xAnswer.key === xKey ? xAnswer.value : 0;
  const setChosenX = (value: number) => setXAnswer({ key: xKey, value });
  const clampedX = Math.min(Math.max(chosenX, 0), maxX);
  const xAction =
    mode === "chooseX"
      ? (actions.find((a) => a.kind === "choose" && a.choice === clampedX) ?? null)
      : null;

  /**
   * Point the preview rail at the card a control is about.
   *
   * The same `hover` the hand and the board write, so a row and the card it
   * names are one gesture apart: every row here is a decision about a specific
   * card, and reading that card used to mean finding it on the board first.
   * Focus as well as pointer -- the rows are buttons, so this is also how the
   * preview follows keyboard navigation.
   *
   * Deliberately *not* put on a container that also holds hovering children:
   * React's mouseleave does not fire when the pointer moves onto a descendant,
   * but the descendant's own leave handler still clears the preview on the way
   * back out, which reads as flicker. Each control carries its own.
   *
   * `data-preview-oid` IS THE SAME FACT, WRITTEN WHERE THE RING CAN READ IT, and
   * without it the `onFocus` above was dead on arrival for a pad or a keyboard.
   * `input/cursor.ts`'s `hoverFor` writes `hoveredOid` on every cursor move and
   * it runs *after* `stamp()` has focused the element -- so a stop it could not
   * read a card out of cleared the preview a beat after the row's own `onFocus`
   * had filled it. The rail was blank on exactly the surface a controller player
   * navigates with, while a mouse over the same row worked.
   */
  const previewing = (oid: number | null | undefined) =>
    oid === null || oid === undefined
      ? {}
      : {
          onMouseEnter: () => hover(oid),
          onMouseLeave: () => hover(null),
          onFocus: () => hover(oid),
          onBlur: () => hover(null),
          "data-preview-oid": oid,
        };
  const ptOf = (oid: number) => {
    const found = card(oid);
    return found ? statLine(found) : null;
  };

  const attackPairs = Object.entries(stagedAttacks).map(
    ([attacker, defender]) => [Number(attacker), defender] as [number, number],
  );
  const blockPairs = Object.entries(stagedBlocks).map(
    ([blocker, attacker]) => [Number(blocker), attacker] as [number, number],
  );
  const staged = mode === "attack" ? attackPairs : blockPairs;

  // ------------------------------------------------------------------ attack

  const attackers = availableAttackers(actions);
  const unstagedAttackers = attackers.filter((oid) => stagedAttacks[oid] === undefined);

  /*
   * "ALL ATTACK" IS RANKED, AND A SECOND PRESS IS THE ALPHA STRIKE.
   *
   * It used to stage every legal attacker, and "All defend" has declined a
   * chump block since cycle 2 -- so the shortcut for the more consequential
   * decision of the turn was the one you had to undo card by card. A 0/1 Blood
   * Artist swung into an untapped 1/1 and the creature you needed at home was
   * tapped out, both from one press.
   *
   * `logic/autoAttack.ts` has the ranking and what it deliberately guesses at.
   * The escalation is the other half and it is not a nicety: racing is a real
   * decision, no arithmetic here should be allowed to make it two dozen
   * presses, and the ring is already resting on this mark when you arrive
   * (`Table.jumpToCommit`). So press one sends what is worth sending and press
   * two sends the rest -- which is also why the escalation lives on the SAME
   * control rather than beside it: a second mark in a three-button dock at the
   * 44px hit floor is a row that no longer fits, and `expectStableDock` says so.
   *
   * Keyed on the decision rather than reset by an effect: `escalated` has to be
   * false again the next time a declaration opens, and comparing the key on read
   * is one fewer thing that can be forgotten than an effect that clears it. The
   * pending kind plus the step is the same narrow key `Table` uses, for the same
   * reason it uses it.
   */
  const sensible = mode === "attack" ? sensibleAttacks(state, actions) : [];
  const newAttacks = sensible.filter(({ attacker }) => stagedAttacks[attacker] === undefined);
  const combatKey = `${state.pending?.kind ?? ""}|${state.step}`;
  const [escalated, setEscalated] = useState({ key: combatKey, on: false });
  const allOut = escalated.key === combatKey && escalated.on;
  /*
   * What the mark would stage if pressed right now.
   *
   * Everything once the ranking has been spent -- either because it was
   * escalated, or because it had nothing to offer in the first place. A mark
   * that greys out while four creatures could still attack is a mark that looks
   * broken; the second state has to be reachable from the first by pressing it.
   */
  const wouldAttack =
    allOut || newAttacks.length === 0 ? unstagedAttackers.length : newAttacks.length;

  /** The `add_attacker` action for one exact pair, which is what carries the id. */
  const attackActionFor = (attacker: number, defender: number) =>
    actions.find(
      (a) =>
        a.kind === "add_attacker" &&
        a.source_oid === attacker &&
        a.targets.some((ref) => ref.kind === "player" && ref.id === defender),
    ) ?? null;

  const attackWithAll = () => {
    if (allOut || newAttacks.length === 0) {
      for (const oid of unstagedAttackers) {
        const [first] = defendersFor(actions, oid);
        if (first !== undefined) stageAttack(oid, first);
      }
      setEscalated({ key: combatKey, on: true });
      return;
    }
    for (const { attacker, defender } of newAttacks) stageAttack(attacker, defender);
    setEscalated({ key: combatKey, on: true });
  };

  // ------------------------------------------------------------------- block

  const blockers = availableBlockers(actions);

  const blockActionFor = (blocker: number, attacker: number) =>
    actions.find(
      (a) =>
        a.kind === "add_blocker" &&
        a.source_oid === blocker &&
        a.targets.some((ref) => ref.kind === "object" && ref.id === attacker),
    ) ?? null;

  // Ranked rather than exhaustive: "block everything" is a way to lose a board.
  // See logic/autoBlock.ts for what the ranking deliberately ignores.
  const suggested = mode === "block" ? autoBlocks(state, actions) : [];
  const newBlocks = suggested.filter(({ blocker }) => stagedBlocks[blocker] === undefined);
  const blockWithAll = () => {
    for (const { blocker, attacker } of newBlocks) stageBlock(blocker, attacker);
  };

  /** Total power aimed at this seat, so the stakes are a number rather than a count. */
  const incomingPower = Object.entries(state.combat?.attackers ?? {})
    .filter(([, defender]) => defender === state.seat)
    .reduce((sum, [oid]) => sum + (card(Number(oid))?.power ?? 0), 0);

  // -------------------------------------------------------------------- play

  const finish = actions.find((a) => a.kind === "finish_declaration") ?? null;
  const commit = standDown
    ? null
    : (actions.find((a) => COMMIT_KINDS.includes(a.kind)) ?? null);
  /**
   * Ids `Table`'s `.choices` fallback bar is rendering in the foot right now.
   *
   * That bar carries `data-action-id` for the targeting actions, but only when
   * none of them names a board object or a player -- targets you cannot click
   * on the board, i.e. spells on the stack. Whenever it is up those ids are in
   * the document twice, which is the exactly-once invariant this file's header
   * describes. The panel yields for the duration: the foot bar is the surface
   * the player is looking at mid-selection.
   */
  const targetingRows = actions.filter((a) => targetingActionIds.includes(a.id));
  const footOwnsIds =
    targetingRows.length > 0 &&
    !targetingRows.some((a) =>
      a.targets.some((ref) => ref.kind === "object" || ref.kind === "player"),
    );
  const claimed = footOwnsIds ? new Set(targetingRows.map((a) => a.id)) : null;

  // Everything the slab did not take. Filtering by id, not by identity, so this
  // stays right if the action list is ever rebuilt between renders.
  const playRows = standDown
    ? []
    : actions.filter((a) => a.id !== commit?.id && !claimed?.has(a.id));
  /**
   * One row per card or ability, not per legal target tuple.
   *
   * The engine offers a targeted spell once per legal target, so a Simic Charm
   * with six creatures to point at is six `cast` actions -- and a row for a
   * card draws the card, so all six read as six copies of it. See
   * `logic/actionMatch.groupPlayActions` for why the collapse cannot happen in
   * the engine.
   */
  const playGroups = groupPlayActions(playRows);

  /** What this copy of a grouped action says on its chip. */
  const chipLabel = (action: LegalAction): string => {
    // A row can group over something other than targets: "Add one mana of any
    // colour" is five actions that all target nothing, and naming them all
    // "No target" would make the choice unreadable. The server says what
    // separates them when it is not a target.
    if (action.option_label) return action.option_label;
    const [ref] = action.targets;
    // Declining an optional target. It is a real, separately legal action, and
    // before the optional-target fix in `targeting.py` it was unreachable.
    if (ref === undefined) return "No target";
    if (ref.kind === "player") return state.players[ref.id]?.name ?? `p${ref.id}`;
    if (ref.kind === "stack") {
      return state.stack.find((item) => item.sid === ref.id)?.name ?? `#${ref.id}`;
    }
    return nameOf(ref.id);
  };

  /** The oid a chip previews, so hovering it shows the creature it would hit. */
  const targetOid = (action: LegalAction): number | null => {
    const [ref] = action.targets;
    return ref !== undefined && ref.kind === "object" ? ref.id : null;
  };

  const hand = state.players[state.seat]?.hand ?? [];
  /** The 1-9 key that already plays this card, from Table's keyboard handler. */
  const handKey = (oid: number | null): string | null => {
    if (oid === null) return null;
    const index = hand.findIndex((entry) => entry.oid === oid);
    return index >= 0 && index < 9 ? String(index + 1) : null;
  };

  // ------------------------------------------------------------------ render

  /**
   * Nothing is declarable at all: no creature untapped, or none that may block.
   *
   * The slab is meant to be the thing the turn is waiting on, and when there is
   * nothing to confirm that thing is *declining* -- so "No attacks" is promoted
   * into it rather than leaving a dead "Confirm 0 blocks" filling the dock while
   * the only live control is a small pill underneath.
   */
  const nothingToDeclare =
    isCombat && (mode === "attack" ? attackers.length === 0 : blockers.length === 0);

  const hint = nothingToDeclare
    ? null
    : mode === "attack"
      ? "Click a creature to send it. Click again to call it back."
      : mode === "block"
        ? "Click the attacker you want each creature to block."
        : null;

  /*
   * The dock, in whichever parent it belongs to this session.
   *
   * A function rather than a conditional around two copies of the tree: two
   * copies is how the same `data-action-id` ends up rendered twice, which is
   * the one thing this panel is not allowed to do.
   */
  const dock = (tree: ReactNode): ReactNode =>
    hosts.slab ? createPortal(tree, hosts.slab) : tree;

  const tool = (tree: ReactNode): ReactNode =>
    hosts.tools ? createPortal(tree, hosts.tools) : tree;

  return (
    <>
      <section
        ref={anchorRef as React.RefObject<HTMLElement>}
        className="acts pane"
        data-testid={isCombat ? "combat-panel" : "action-panel"}
        data-combat-kind={
          mode === "attack" ? "attackers" : mode === "block" ? "blockers" : undefined
        }
        data-mode={mode}
      >
        <div className="acts__head">
          <span className="acts__prompt" data-testid="prompt">
            {decisionPrompt(state)}
          </span>
          {mode === "block" && incomingPower > 0 && (
            <span className="acts__stakes tabular" data-hint="Total power attacking you">
              {incomingPower} power incoming
            </span>
          )}
          <AnimatePresence>
            {(narrating || aiThinking || waitingForPlayer) && (
              <motion.span
                className="acts__thinking"
                data-testid="waiting-on"
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={ease}
              >
                <span className="acts__dot" />
                {narrating ? "Playing it out" : thinkingLabel(state)}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {hint && <p className="acts__hint">{hint}</p>}

        <div className="acts__list" data-testid="action-list">
          {mode === "attack" && (
            <AttackRows
              attackers={attackers}
              actions={actions}
              state={state}
              stagedAttacks={stagedAttacks}
              disabled={disabled}
              onStage={onStage}
              attackActionFor={attackActionFor}
              nameOf={nameOf}
              ptOf={ptOf}
              previewing={previewing}
            />
          )}

          {mode === "block" && (
            <BlockGroups
              blockers={blockers}
              actions={actions}
              stagedBlocks={stagedBlocks}
              disabled={disabled}
              onStage={onStage}
              blockActionFor={blockActionFor}
              card={card}
              nameOf={nameOf}
              ptOf={ptOf}
              previewing={previewing}
            />
          )}

          {mode === "play" && (
            <PlayRows
              playGroups={playGroups}
              disabled={disabled}
              onAct={onAct}
              hover={hover}
              card={card}
              handKey={handKey}
              chipLabel={chipLabel}
              targetOid={targetOid}
              previewing={previewing}
            />
          )}

          {mode === "chooseX" && (
            <XStepper
              clampedX={clampedX}
              maxX={maxX}
              perPoint={perPoint}
              disabled={disabled}
              setChosenX={setChosenX}
            />
          )}

          {mode === "attack" && attackers.length === 0 && (
            <p className="acts__none">Nothing can attack.</p>
          )}
          {mode === "block" && blockers.length === 0 && (
            <p className="acts__none">Nothing can block.</p>
          )}
          {mode === "play" && playRows.length === 0 && !commit && !state.game_over && (
            <p className="acts__none">{standDown ? "Answer the dialog." : "Waiting…"}</p>
          )}
        </div>

        {/*
          The tools, as a footer of this panel rather than a panel of their own.
          They used to be `.bar__tools` inside a third bordered pane stacked under
          the combat panel, which made the rail read as three competing surfaces.
          A hairline rule is enough separation for controls that are always
          available and almost never the thing you came here to press.

          `toolHost` moves them out of the panel entirely on a handheld, for the
          reason the slab moved: measured mid-combat at 1200x800 they were 101px
          of a 252px panel, which left the action list pinned at its 74px floor
          holding 94px of "Declare attackers" choices. Five 44px targets do not
          fit across a 200px column, so the hit floor wraps them to three rows --
          and that is the floor working correctly in a column that is the wrong
          shape for it. The foot is 1180px wide and they fit on one line there.
        */}
        {tool(
          <ToolStrip
            state={state}
            busy={busy}
            narrating={narrating}
            onToggleFullControl={onToggleFullControl}
            onToggleManualMana={onToggleManualMana}
            onSkipNarration={onSkipNarration}
            onUndo={onUndo}
            onQuit={onQuit}
          />,
        )}
      </section>

      {/*
        The commit dock sits outside the pane on purpose: the list scrolls and
        this must not scroll with it. One large control for the thing the turn is
        waiting on, and the alternatives demoted to a row beneath it -- rather
        than three same-sized buttons where the most-pressed and the least-pressed
        look identical.

        `slabHost` moves the whole dock into the foot on a handheld -- see the
        prop. `renderDock` is the same tree either way; only its parent changes.
      */}
      {dock(
        <CommitDock
          mode={mode}
          state={state}
          disabled={disabled}
          isCombat={isCombat}
          nothingToDeclare={nothingToDeclare}
          attackPairs={attackPairs}
          blockPairs={blockPairs}
          staged={staged}
          unstagedAttackers={unstagedAttackers}
          wouldAttack={wouldAttack}
          attackWithAll={attackWithAll}
          blockWithAll={blockWithAll}
          newBlocks={newBlocks}
          finish={finish}
          commit={commit}
          xAction={xAction}
          clampedX={clampedX}
          onAct={onAct}
          onDeclare={onDeclare}
        />,
      )}
    </>
  );
}
