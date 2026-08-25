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
import { setCursor } from "../../input/cursor";
import { actionAttrs, stopId } from "../../input/stops";
import {
  availableAttackers,
  availableBlockers,
  blockableBy,
  defendersFor,
  groupPlayActions,
} from "../../logic/actionMatch";
import { type BlockTier, autoBlocks, blockTier } from "../../logic/autoBlock";
import { keywordLabel, manaPips, statLine } from "../../logic/cardStyle";
import { decisionPrompt, thinkingLabel } from "../../logic/labels";
import { findCard } from "../../logic/zoneGrouping";
import { bouncy, ease } from "../../motion/springs";
import { useUiStore } from "../../state/uiStore";
import { useHandheldLayout } from "../../state/useHandheld";
import { ActionIcon } from "../ui/ActionIcon";
import { SchemePicker } from "../ui/SchemePicker";
import { ManaSymbol } from "./ManaSymbol";
import { SymbolText } from "./SymbolText";

/**
 * What a block would actually achieve, in four words.
 *
 * Straight off `blockTier`, which is the ranking "All defend" already sorts by,
 * so the label and the suggestion can never disagree. Naming the outcome is the
 * whole point of the grouped blocker list: the numbers were always on the cards,
 * but working out "my 2/2 into their 2/2 is a trade" for six pairs is arithmetic
 * the player was being asked to do under time pressure.
 */
const TIER_LABEL: Record<BlockTier, string> = {
  1: "kills it, survives",
  2: "survives",
  3: "trades",
  4: "chumps",
};

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
  /**
   * A modal owns the decision, so the list renders no action ids at all.
   *
   * The prompt and the tools stay in the document. Note they are not *reachable*
   * while a dialog is up: `.prompt-backdrop` is fixed at `inset: 0` above
   * everything and swallows the clicks. That predates this panel and is recorded
   * in docs/mockup-fidelity.md rather than worked around here.
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
   * `mockups/handheld-board/` draws and the one that reads better -- the thing
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

  const muted = useUiStore((s) => s.muted);
  const toggleMuted = useUiStore((s) => s.toggleMuted);

  /*
   * The settings menu, and why three controls went into it.
   *
   * Sound, undo and quit were three permanently visible buttons in a strip
   * whose whole job is to be ignorable. Two of them are pressed at most once a
   * game and the third is pressed when a game ends -- and they sat at the same
   * weight as `Auto-pass` and `Auto mana`, which are modes you flip mid-turn
   * and which change how every subsequent priority window behaves. Equal
   * prominence for "how does this game play" and "I would like to leave" reads
   * as a row of five equally likely things, which is what makes the strip cost
   * a glance it should never cost.
   *
   * So they are one control now, and they keep their ids: the same
   * `data-stop`, `data-testid` and handlers ride into the menu, so the ring
   * reaches them exactly as it did once the menu is open and no gate had to be
   * loosened to allow a second copy.
   *
   * IT OPENS UPWARDS. The strip is the last row of the foot on a handheld and
   * the last row of the panel on a desktop; there is nothing below either but
   * the screen edge.
   */
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  /*
   * Closing it puts the ring back on the button that opened it.
   *
   * Without this the ring is standing on a node that is about to stop existing,
   * and `resolveCursor`'s fallback is "the first stop of the surface on top" --
   * which is the far side of the board. Closing a menu must not move the player
   * somewhere they did not ask to go. Guarded on focus actually being inside,
   * so a mouse player clicking elsewhere is not dragged back here.
   */
  const closeSettings = () => {
    setSettingsOpen(false);
    const inside = settingsRef.current?.contains(document.activeElement);
    if (inside) setCursor(stopId.tool("settings"));
  };

  /*
   * A press anywhere else closes it. `pointerdown` rather than `click`, so the
   * menu is gone before whatever was pressed underneath it acts -- and capture,
   * so a control that stops propagation cannot leave the menu open behind it.
   */
  useEffect(() => {
    if (!settingsOpen) return;
    const onDown = (event: PointerEvent) => {
      if (settingsRef.current?.contains(event.target as Node)) return;
      setSettingsOpen(false);
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [settingsOpen]);
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

  /** The `add_attacker` action for one exact pair, which is what carries the id. */
  const attackActionFor = (attacker: number, defender: number) =>
    actions.find(
      (a) =>
        a.kind === "add_attacker" &&
        a.source_oid === attacker &&
        a.targets.some((ref) => ref.kind === "player" && ref.id === defender),
    ) ?? null;

  const attackWithAll = () => {
    for (const oid of unstagedAttackers) {
      const [first] = defendersFor(actions, oid);
      if (first !== undefined) stageAttack(oid, first);
    }
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

  /*
   * THE DOCK IS THE SAME SHAPE IN EVERY STATE, and this is the half that makes
   * it true when there is nothing to press.
   *
   * The well was always mounted and its contents were not, so between decisions
   * it collapsed to its own padding -- 18px -- and sprang back to 66 or 90 the
   * moment an action arrived. The whole rail below it moved with it, every time
   * a turn passed. `.preview` above already holds a constant height for exactly
   * this reason; `board.css` spends four paragraphs on why.
   *
   * So the bar is never absent, only idle: the same slab in the same quiet
   * treatment a disabled one wears, carrying the panel's own waiting mark
   * (`.acts__dot`, which is what `.acts__thinking` uses in the head). Gold
   * means "this is what the turn is waiting on", and while the engine is
   * playing out somebody else's turn it is not.
   *
   * IT IS NOT AN ACTION AND IS NOT A BUTTON. A `div`, not a disabled
   * `<button>`: there is nothing here to press even in principle, and a
   * disabled control is a promise that it will become pressable. It carries no
   * `data-action-id` -- the exactly-once invariant at the top of this file --
   * and no `data-stop`, so the controller cursor cannot land on it either.
   * `aria-hidden` because `.acts__none` in the list above already says
   * "Waiting..." to a screen reader, and saying it twice is worse than once.
   */
  const idleBar = (
    <div className="bar">
      <div className="commit commit--idle" aria-hidden="true">
        <span className="commit__dots" data-testid="commit-idle">
          <span className="acts__dot" />
          <span className="acts__dot" />
          <span className="acts__dot" />
        </span>
      </div>
    </div>
  );
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
            {(narrating || aiThinking) && (
              <motion.span
                className="acts__thinking"
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
          {mode === "attack" &&
            attackers.map((attacker, index) => {
              const defenders = defendersFor(actions, attacker);
              const chosen = stagedAttacks[attacker];
              const on = chosen !== undefined;
              const single = defenders.length === 1;
              const action = single ? attackActionFor(attacker, defenders[0]) : null;
              const rowClass = ["act", "act--staged", on ? "act--on" : ""]
                .filter(Boolean)
                .join(" ");
              const body = (
                <>
                  <span className="act__key">{index + 1}</span>
                  <span className="act__name">{nameOf(attacker)}</span>
                  {on && (
                    <span className="act__aim">→ {state.players[chosen]?.name ?? chosen}</span>
                  )}
                  {ptOf(attacker) && <span className="act__pt tabular">{ptOf(attacker)}</span>}
                </>
              );

              // One legal defender: the row *is* the action, so attacking is a
              // single click on the obvious thing.
              if (single && action) {
                return (
                  <button
                    type="button"
                    key={attacker}
                    className={rowClass}
                    {...actionAttrs(action.id)}
                    data-action-kind={action.kind}
                    data-attacker={attacker}
                    data-defender={defenders[0]}
                    data-staged={on ? "true" : undefined}
                    aria-pressed={on}
                    disabled={disabled}
                    onClick={() => onStage(action.id)}
                    {...previewing(attacker)}
                  >
                    {body}
                  </button>
                );
              }

              // Several: the row is inert and each defender carries its own id,
              // which is what keeps N pairs on N controls. Only in a pod.
              return (
                <div
                  key={attacker}
                  className={`${rowClass} act--group`}
                  data-attacker={attacker}
                  data-staged={on ? "true" : undefined}
                  {...previewing(attacker)}
                >
                  {body}
                  <span className="act__aims">
                    {defenders.map((pid) => {
                      const pairAction = attackActionFor(attacker, pid);
                      if (!pairAction) return null;
                      const aimed = chosen === pid;
                      return (
                        <button
                          type="button"
                          key={pid}
                          className={aimed ? "aim aim--on" : "aim"}
                          {...actionAttrs(pairAction.id)}
                          data-action-kind={pairAction.kind}
                          data-attacker={attacker}
                          data-defender={pid}
                          // The pointer gets this from the group row it is
                          // inside; the ring lands on the chip itself and needs
                          // it said here. See `previewing`.
                          data-preview-oid={attacker}
                          aria-pressed={aimed}
                          disabled={disabled}
                          onClick={() => onStage(pairAction.id)}
                          data-hint={
                            aimed
                              ? `Attacking ${state.players[pid]?.name} — click to call it back`
                              : `Send at ${state.players[pid]?.name}`
                          }
                        >
                          {state.players[pid]?.name ?? pid}
                        </button>
                      );
                    })}
                  </span>
                </div>
              );
            })}

          {mode === "block" &&
            blockers.map((blocker) => {
              const blockerCard = card(blocker);
              const chosen = stagedBlocks[blocker];
              const targets = blockableBy(actions, blocker);
              return (
                <div className="actgroup" key={blocker} data-blocker={blocker}>
                  {/* The header previews *your* creature; each row below it
                      previews the attacker that row would block. Deciding a
                      block means reading both, and now neither needs finding on
                      the board first. */}
                  <div className="actgroup__head" {...previewing(blocker)}>
                    <span className="actgroup__name">{nameOf(blocker)}</span>
                    {blockerCard && blockerCard.keywords.length > 0 && (
                      <span className="actgroup__kw">
                        {blockerCard.keywords.map(keywordLabel).join(" · ")}
                      </span>
                    )}
                    {ptOf(blocker) && (
                      <span className="actgroup__pt tabular">{ptOf(blocker)}</span>
                    )}
                  </div>
                  {targets.length === 0 ? (
                    <p className="actgroup__none">Nothing this can block.</p>
                  ) : (
                    targets.map((attacker) => {
                      const action = blockActionFor(blocker, attacker);
                      const attackerCard = card(attacker);
                      if (!action || !blockerCard || !attackerCard) return null;
                      const tier = blockTier(blockerCard, attackerCard);
                      const on = chosen === attacker;
                      return (
                        <button
                          type="button"
                          key={action.id}
                          className={`act act--nested act--staged${on ? " act--on" : ""}`}
                          {...actionAttrs(action.id)}
                          data-action-kind={action.kind}
                          data-blocker={blocker}
                          data-attacker={attacker}
                          data-tier={tier}
                          data-staged={on ? "true" : undefined}
                          aria-pressed={on}
                          disabled={disabled}
                          onClick={() => onStage(action.id)}
                          data-hint={
                            on
                              ? `Blocking ${nameOf(attacker)} — click to release`
                              : `Block ${nameOf(attacker)}`
                          }
                          {...previewing(attacker)}
                        >
                          <span className="act__name">{nameOf(attacker)}</span>
                          {/* The attacker's P/T, next to the verdict it produced.
                              Deciding a block means comparing two numbers, and
                              only one of them used to be in the panel. */}
                          <span className="act__pt tabular">{statLine(attackerCard)}</span>
                          <span className={`verdict verdict--${tier}`}>{TIER_LABEL[tier]}</span>
                        </button>
                      );
                    })
                  )}
                </div>
              );
            })}

          {mode === "play" &&
            playGroups.map(({ key: groupKey, head, actions: aims }) => {
              const source = head.source_oid === null ? null : card(head.source_oid);
              const isCard = head.kind === "cast" || head.kind === "play_land";
              const tone = isCard
                ? " act--playable"
                : head.kind === "activate"
                  ? " act--ability"
                  : "";
              const key = handKey(head.source_oid);
              const single = aims.length === 1;
              const body = (
                <>
                  {key && <span className="act__key">{key}</span>}
                  {isCard && source ? (
                    <>
                      <span className="act__name">{source.name}</span>
                      <span className="act__type">{source.type_line}</span>
                      {manaPips(source.mana_cost).length > 0 && (
                        <span className="act__cost">
                          {manaPips(source.mana_cost).map((pip) => (
                            <ManaSymbol
                              code={pip.symbol}
                              className={`pip--${pip.tone}`}
                              key={pip.key}
                            />
                          ))}
                        </span>
                      )}
                      {statLine(source) && (
                        <span className="act__pt tabular">{statLine(source)}</span>
                      )}
                    </>
                  ) : (
                    // Activation costs live in these labels ("{2}, {T}, Sacrifice:
                    // ..."), and they were the last place mana stayed raw text.
                    // Grouped, the row names the ability and the chips name the
                    // targets, so the `-> Bear` suffix would be one arbitrary
                    // target repeated on every row of the same permanent.
                    <span className="act__name">
                      <SymbolText text={single ? head.label : head.base_label} />
                    </span>
                  )}
                </>
              );

              // One way to aim it: the row *is* the action, exactly as before.
              if (single) {
                return (
                  <button
                    type="button"
                    key={groupKey}
                    className={`act${tone}`}
                    {...actionAttrs(head.id)}
                    data-action-kind={head.kind}
                    data-source={head.source_oid ?? undefined}
                    disabled={disabled}
                    onClick={() => onAct(head.id)}
                    {...previewing(head.source_oid)}
                  >
                    {body}
                  </button>
                );
              }

              // Several: the row is inert and each target carries its own id,
              // which is what keeps N actions on N controls rather than on one.
              // Same shape as an attacker with several legal defenders above.
              return (
                <div
                  key={groupKey}
                  className={`act${tone} act--group`}
                  data-source={head.source_oid ?? undefined}
                  {...previewing(head.source_oid)}
                >
                  {body}
                  <span className="act__aims">
                    {aims.map((aim) => (
                      <button
                        type="button"
                        key={aim.id}
                        className="aim"
                        {...actionAttrs(aim.id)}
                        data-action-kind={aim.kind}
                        data-source={aim.source_oid ?? undefined}
                        disabled={disabled}
                        onClick={() => onAct(aim.id)}
                        data-hint={aim.label}
                        // Not `previewing`: this is a hovering child of a
                        // hovering container, the case that comment warns
                        // about. Falling back to the row's own card rather
                        // than to null is what keeps the preview from going
                        // blank on the way from a chip back onto the row.
                        onMouseEnter={() => hover(targetOid(aim) ?? head.source_oid)}
                        onMouseLeave={() => hover(head.source_oid)}
                        onFocus={() => hover(targetOid(aim) ?? head.source_oid)}
                        onBlur={() => hover(head.source_oid)}
                        // The ring's copy of the line above -- see `previewing`.
                        data-preview-oid={targetOid(aim) ?? head.source_oid ?? undefined}
                      >
                        <SymbolText text={chipLabel(aim)} />
                      </button>
                    ))}
                  </span>
                </div>
              );
            })}

          {mode === "chooseX" && (
            <div className="xstep" data-testid="choose-x" data-x={clampedX}>
              <button
                type="button"
                className="xstep__btn"
                data-testid="choose-x-down"
                disabled={disabled || clampedX <= 0}
                onClick={() => setChosenX(clampedX - 1)}
                aria-label="One less"
              >
                −
              </button>
              <span className="xstep__value tabular">X = {clampedX}</span>
              <button
                type="button"
                className="xstep__btn"
                data-testid="choose-x-up"
                disabled={disabled || clampedX >= maxX}
                onClick={() => setChosenX(clampedX + 1)}
                aria-label="One more"
              >
                +
              </button>
              <span className="xstep__hint">
                up to {maxX}
                {perPoint > 1 && ` · ${perPoint} mana per point`}
              </span>
            </div>
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
          <div className="tools">
            {/*
            Sound, undo and quit, folded into one control. See `settingsOpen`
            above for why: three buttons pressed once a game each, at the same
            weight as the two modes beside them that change how every priority
            window behaves.

            `onKeyDown` rather than a document listener for Escape, and it stops
            propagating: `Table` binds `Escape` to a strict unwind of the whole
            board, so an un-stopped one here would close the menu AND cancel
            whatever the player was in the middle of.
          */}
            <div
              className="settings"
              ref={settingsRef}
              onKeyDown={(event) => {
                if (event.key !== "Escape" || !settingsOpen) return;
                event.stopPropagation();
                closeSettings();
              }}
            >
              <button
                type="button"
                className={settingsOpen ? "tool tool--on" : "tool"}
                onClick={() => (settingsOpen ? closeSettings() : setSettingsOpen(true))}
                aria-expanded={settingsOpen}
                aria-haspopup="menu"
                aria-label="Settings"
                data-stop={stopId.tool("settings")}
                data-testid="settings"
                data-hint="Sound, undo and quit"
              >
                ⚙
              </button>
              {settingsOpen && (
                <div className="settings__menu" role="menu" data-testid="settings-menu">
                  {/*
                  The only one that leaves the menu open: it is a toggle, and
                  the thing you most often want after flipping it is to flip it
                  back. The other two end what you were doing.
                */}
                  <button
                    type="button"
                    role="menuitem"
                    className="settings__item"
                    onClick={toggleMuted}
                    aria-pressed={!muted}
                    data-stop={stopId.tool("mute")}
                    data-testid="mute"
                    data-hint={muted ? "Sound off" : "Sound on"}
                  >
                    <span className="settings__glyph" aria-hidden="true">
                      {muted ? "🔇" : "🔊"}
                    </span>
                    {muted ? "Sound off" : "Sound on"}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="settings__item"
                    onClick={() => {
                      closeSettings();
                      onUndo();
                    }}
                    disabled={busy}
                    data-stop={stopId.tool("undo")}
                    data-testid="undo"
                    data-hint="Undo your last action (U)"
                  >
                    <span className="settings__glyph" aria-hidden="true">
                      ↺
                    </span>
                    Undo
                  </button>
                  {/*
                    THE ONE SETTING THAT CAN MAKE THE MENU UNREACHABLE, so it is
                    reachable from inside it.

                    The full diagnosis -- which pads the browser can see, and
                    which of the three environment causes is stopping it -- lives
                    on the front door's Settings card, where there is room for
                    prose. What has to be here is the half a player needs
                    MID-GAME: a Deck whose controller arrives as a keyboard shows
                    "Enter" and "Esc" on every hint, and quitting to the lobby to
                    fix that is a bad answer during somebody's turn.

                    The picker is the same component the door renders, so the two
                    surfaces cannot drift.
                  */}
                  <div className="settings__scheme" data-testid="settings-scheme">
                    <span className="settings__label">Controls</span>
                    <SchemePicker />
                  </div>
                  <button
                    type="button"
                    role="menuitem"
                    className="settings__item settings__item--danger"
                    onClick={() => {
                      closeSettings();
                      onQuit();
                    }}
                    data-stop={stopId.tool("quit")}
                    data-testid="quit"
                    data-hint="Quit this game"
                  >
                    <span className="settings__glyph" aria-hidden="true">
                      ✕
                    </span>
                    Quit game
                  </button>
                </div>
              )}
            </div>
            {/*
            The one control here that keeps a word rather than a glyph. It is a
            mode with real consequences for how the game plays -- whether it
            stops at every priority window -- and an unlabelled icon for that
            would be a regression in clarity, not a saving in space.
          */}
            <button
              type="button"
              className={state.full_control ? "tool tool--on tool--wide" : "tool tool--wide"}
              onClick={() => onToggleFullControl(!state.full_control)}
              disabled={busy}
              aria-pressed={state.full_control}
              data-stop={stopId.tool("full-control")}
              data-testid="full-control"
              data-hint={
                state.full_control
                  ? "Full control: stopping at every priority window"
                  : "Stopping only where you have something to respond to. Turn on for every window."
              }
            >
              {state.full_control ? "Full control" : "Auto-pass"}
            </button>
            {/*
            The second mode with real consequences, and it keeps its words for
            the same reason. Off, the solver taps for you and mana abilities are
            not actions at all; on, every untapped source becomes a row and a
            dual becomes one chip per colour.
          */}
            <button
              type="button"
              className={state.manual_mana ? "tool tool--on tool--wide" : "tool tool--wide"}
              onClick={() => onToggleManualMana(!state.manual_mana)}
              disabled={busy}
              aria-pressed={state.manual_mana}
              data-stop={stopId.tool("manual-mana")}
              data-testid="manual-mana"
              data-hint={
                state.manual_mana
                  ? "Manual mana: you choose which permanent to tap, and which colour it makes"
                  : "The solver taps for you. Turn on to tap lands yourself."
              }
            >
              {state.manual_mana ? "Manual mana" : "Auto mana"}
            </button>
            {/*
            Last, and only while it is worth anything.
            
            It used to be first. Skipping is urgent -- the whole point is that
            you have stopped wanting to watch -- but it is also transient, and a
            control that appears at the head of the row pushes the two modes
            beside it sideways every time a beat plays. At the end it costs
            nothing to the things that are always there.
          */}
            {narrating && (
              <button
                type="button"
                className="tool"
                data-stop={stopId.tool("skip")}
                onClick={onSkipNarration}
                data-hint="Skip ahead"
              >
                ⏩
              </button>
            )}
          </div>,
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
        <div className="commit-dock">
          {/*
            What the count used to be doing on the button, moved off it -- and
            now rendered in EVERY mode rather than only in combat.

            `Attack with 0` -> `Attack with 10` is a label that changes width,
            so the button re-centres itself under the thumb every time a
            creature is staged, which is exactly while you are aiming at it.
            `mockups/handheld-board/` names this and puts the number on a line
            of its own above the bar. It is also the line the block forecast
            wants, so the two states share one row rather than each inventing a
            place to sit.

            OUTSIDE THE MODE TERNARY, because a line that exists only in combat
            is a line that appears when combat starts -- 25px of dock arriving
            on top of the bar changing, which moved the rail a second time. Out
            of combat it renders empty and `.commit-note`'s `min-height: 1lh`
            keeps its row; `ActionPanel.stories`' `expectStableDock` fails if
            that ever stops being true.
          */}
          <p className="commit-note tabular">
            {mode === "attack"
              ? `${attackPairs.length} attacking`
              : mode === "block"
                ? `${blockPairs.length} blocked of ${Object.keys(state.combat?.attackers ?? {}).length}`
                : // Empty, and the row is held open by `.commit-note`'s
                  // `min-height: 1lh` rather than by a non-breaking space. A
                  // NBSP works and formats down to an invisible character in
                  // this file, which is a thing the next person deletes by
                  // accident; one mechanism in the stylesheet is better than
                  // two, one of which cannot be seen.
                  ""}
          </p>
          {mode === "chooseX" ? (
            // The only control in the document carrying an id for this decision.
            // The other twenty values are reachable through the stepper, which
            // changes which id this slab points at rather than adding more.
            xAction ? (
              <div className="bar">
                <motion.button
                  type="button"
                  className="commit"
                  {...actionAttrs(xAction.id)}
                  data-action-kind={xAction.kind}
                  disabled={disabled}
                  onClick={() => onAct(xAction.id)}
                  whileHover={disabled ? undefined : { y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  transition={bouncy}
                  data-testid="commit"
                >
                  <span className="commit__main">Pay X = {clampedX}</span>
                </motion.button>
              </div>
            ) : (
              idleBar
            )
          ) : isCombat ? (
            nothingToDeclare && finish ? (
              /*
                  With nothing declarable there is nothing to confirm, so
                  declining *is* the decision and it takes the whole bar. The
                  two marks go with it: "all" and "none" of an empty set are
                  the same button pressed twice.
                */
              <div className="bar">
                <motion.button
                  type="button"
                  className="commit"
                  {...actionAttrs(finish.id)}
                  data-action-kind={finish.kind}
                  disabled={disabled}
                  onClick={() => onAct(finish.id)}
                  whileHover={disabled ? undefined : { y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  transition={bouncy}
                  data-testid="combat-skip"
                >
                  <span className="commit__main">
                    {mode === "attack" ? "No attacks" : "No blocks"}
                  </span>
                </motion.button>
              </div>
            ) : (
              /*
                  EVERY CHOICE, THE DECISION, NO CHOICE -- in that order, on one
                  row.

                  These were a full-width slab with two 12px outlined pills
                  under it, which spends a whole row on the two answers nobody
                  presses and reads as one button with a caption. One shape
                  either side of the slab is the relationship they actually
                  have, and it puts all three at the 44px floor in the height
                  the slab alone was taking.

                  The marks themselves are DRAWN, not typed. They were `▣` and
                  `▢`, filled and empty of one square, which is the true
                  relationship and an unreadable picture of it -- playtest
                  found two squares nobody could tell apart. `ui/ActionIcon`
                  has the argument.

                  The names live in `aria-label` and `data-hint` and nowhere
                  else. A `title` would reach the mouse only, and this bar is
                  driven by a controller as often as by a thumb.
                */
              <div className="bar">
                {mode === "attack" ? (
                  <button
                    type="button"
                    className="commit-mark"
                    data-testid="combat-all"
                    disabled={disabled || unstagedAttackers.length === 0}
                    onClick={attackWithAll}
                    aria-label={`All attack${
                      unstagedAttackers.length > 0 ? ` (${unstagedAttackers.length})` : ""
                    }`}
                    data-hint="Send every creature that can attack"
                  >
                    <ActionIcon name="all" />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="commit-mark"
                    data-testid="combat-all"
                    disabled={disabled || newBlocks.length === 0}
                    onClick={blockWithAll}
                    aria-label={`All defend${
                      newBlocks.length > 0 ? ` (${newBlocks.length})` : ""
                    }`}
                    data-hint={
                      newBlocks.length === 0
                        ? "No block here is worth making on its own"
                        : "Block where it is worth it: survive and kill first, then walls, then trades"
                    }
                  >
                    <ActionIcon name="all" />
                  </button>
                )}

                <motion.button
                  type="button"
                  className="commit"
                  disabled={disabled || staged.length === 0}
                  data-empty={staged.length === 0 ? "true" : "false"}
                  aria-label={
                    mode === "attack"
                      ? `Attack with ${attackPairs.length}`
                      : `Confirm ${blockPairs.length} block${
                          blockPairs.length === 1 ? "" : "s"
                        }`
                  }
                  onClick={() =>
                    onDeclare(mode === "attack" ? "attackers" : "blockers", staged)
                  }
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.97 }}
                  transition={bouncy}
                  data-testid="combat-confirm"
                >
                  <span className="commit__main">{mode === "attack" ? "Attack" : "Block"}</span>
                </motion.button>

                {finish && (
                  <button
                    type="button"
                    className="commit-mark"
                    {...actionAttrs(finish.id)}
                    data-action-kind={finish.kind}
                    disabled={disabled}
                    onClick={() => onAct(finish.id)}
                    data-testid="combat-skip"
                    aria-label={mode === "attack" ? "No attacks" : "No blocks"}
                    data-hint={mode === "attack" ? "No attacks" : "No blocks"}
                  >
                    <ActionIcon name="skip" />
                  </button>
                )}
              </div>
            )
          ) : commit ? (
            <div className="bar">
              <motion.button
                type="button"
                className="commit"
                {...actionAttrs(commit.id)}
                data-action-kind={commit.kind}
                disabled={disabled}
                onClick={() => onAct(commit.id)}
                whileHover={disabled ? undefined : { y: -2 }}
                whileTap={{ scale: 0.97 }}
                transition={bouncy}
                data-testid="commit"
              >
                <span className="commit__main">{commit.label}</span>
              </motion.button>
            </div>
          ) : (
            /*
              Not your turn, or a dialog owns the decision. This is the branch
              the whole rail used to collapse on -- `commit` is null while the
              engine plays out every other seat's turn, which is most of the
              wall-clock of a four-player game.
            */
            idleBar
          )}
        </div>,
      )}
    </>
  );
}
