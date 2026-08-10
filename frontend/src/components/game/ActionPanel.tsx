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
 * Staging stays client-side, for the reason `Table.onBarAct` documents: posting
 * `add_blocker` one at a time has no inverse, and a single blocker committed onto
 * a menace attacker can strand the declaration with no legal `finish_declaration`
 * at all. Nothing here reaches the server until the commit slab is pressed.
 */

import { AnimatePresence, motion } from "motion/react";
import type { CardView, GameView, LegalAction } from "../../api/types";
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
import { type Speed, useUiStore } from "../../state/uiStore";
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

const SPEEDS: Speed[] = ["cinematic", "fast", "instant"];

const SPEED_LABELS: Record<Speed, string> = {
  cinematic: "0.5x",
  fast: "1x",
  instant: "≫",
};

const SPEED_TITLES: Record<Speed, string> = {
  cinematic: "Half speed — watch every beat",
  fast: "Normal speed",
  instant: "Skip narration entirely",
};

type Mode = "attack" | "block" | "play";

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
  narrating,
  onSkipNarration,
  busy,
  aiThinking,
  standDown,
}: Props) {
  const speed = useUiStore((s) => s.speed);
  const setSpeed = useUiStore((s) => s.setSpeed);
  const muted = useUiStore((s) => s.muted);
  const toggleMuted = useUiStore((s) => s.toggleMuted);
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
        : "play";
  const isCombat = mode !== "play";

  const card = (oid: number): CardView | null => findCard(state, oid);
  const nameOf = (oid: number) => card(oid)?.name ?? `#${oid}`;

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
   */
  const previewing = (oid: number | null | undefined) =>
    oid === null || oid === undefined
      ? {}
      : {
          onMouseEnter: () => hover(oid),
          onMouseLeave: () => hover(null),
          onFocus: () => hover(oid),
          onBlur: () => hover(null),
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

  /** Which target this copy of a grouped action aims at, for its chip. */
  const targetLabel = (action: LegalAction): string => {
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

  return (
    <>
      <section
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
            <span className="acts__stakes tabular" title="Total power attacking you">
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
                    data-action-id={action.id}
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
                          data-action-id={pairAction.id}
                          data-action-kind={pairAction.kind}
                          data-attacker={attacker}
                          data-defender={pid}
                          aria-pressed={aimed}
                          disabled={disabled}
                          onClick={() => onStage(pairAction.id)}
                          title={
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
                          data-action-id={action.id}
                          data-action-kind={action.kind}
                          data-blocker={blocker}
                          data-attacker={attacker}
                          data-tier={tier}
                          data-staged={on ? "true" : undefined}
                          aria-pressed={on}
                          disabled={disabled}
                          onClick={() => onStage(action.id)}
                          title={
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
                    data-action-id={head.id}
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
                        data-action-id={aim.id}
                        data-action-kind={aim.kind}
                        data-source={aim.source_oid ?? undefined}
                        disabled={disabled}
                        onClick={() => onAct(aim.id)}
                        title={aim.label}
                        // Not `previewing`: this is a hovering child of a
                        // hovering container, the case that comment warns
                        // about. Falling back to the row's own card rather
                        // than to null is what keeps the preview from going
                        // blank on the way from a chip back onto the row.
                        onMouseEnter={() => hover(targetOid(aim) ?? head.source_oid)}
                        onMouseLeave={() => hover(head.source_oid)}
                        onFocus={() => hover(targetOid(aim) ?? head.source_oid)}
                        onBlur={() => hover(head.source_oid)}
                      >
                        {targetLabel(aim)}
                      </button>
                    ))}
                  </span>
                </div>
              );
            })}

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
        */}
        <div className="tools">
          <fieldset className="speed">
            <legend className="visually-hidden">Animation speed</legend>
            {SPEEDS.map((option) => (
              <button
                type="button"
                key={option}
                className={option === speed ? "speed__btn speed__btn--on" : "speed__btn"}
                data-speed={option}
                onClick={() => setSpeed(option)}
                title={SPEED_TITLES[option]}
              >
                {SPEED_LABELS[option]}
              </button>
            ))}
          </fieldset>
          {narrating && (
            <button type="button" className="tool" onClick={onSkipNarration} title="Skip ahead">
              ⏩
            </button>
          )}
          <button
            type="button"
            className={muted ? "tool" : "tool tool--on"}
            onClick={toggleMuted}
            aria-pressed={!muted}
            data-testid="mute"
            title={muted ? "Sound off" : "Sound on"}
          >
            {muted ? "🔇" : "🔊"}
          </button>
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
            data-testid="full-control"
            title={
              state.full_control
                ? "Full control: stopping at every priority window"
                : "Stopping only where you have something to respond to. Turn on for every window."
            }
          >
            {state.full_control ? "Full control" : "Auto-pass"}
          </button>
          <button
            type="button"
            className="tool"
            onClick={onUndo}
            disabled={busy}
            title="Undo your last action (U)"
          >
            ↺
          </button>
          <button type="button" className="tool" onClick={onQuit} title="Quit this game">
            ✕
          </button>
        </div>
      </section>

      {/*
        The commit dock sits outside the pane on purpose: the list scrolls and
        this must not scroll with it. One large control for the thing the turn is
        waiting on, and the alternatives demoted to a row beneath it -- rather
        than three same-sized buttons where the most-pressed and the least-pressed
        look identical.
      */}
      <div className="commit-dock">
        {isCombat ? (
          <>
            {/*
              With nothing declarable there is nothing to confirm, so declining
              *is* the decision and it takes the slab. Leaving the dead
              "Confirm 0 blocks" here filled the dock with the one control that
              could not be pressed while the only live one was a pill below it.
            */}
            {nothingToDeclare && finish ? (
              <motion.button
                type="button"
                className="btn btn--primary commit"
                data-action-id={finish.id}
                data-action-kind={finish.kind}
                disabled={disabled}
                onClick={() => onAct(finish.id)}
                whileHover={disabled ? undefined : { y: -2, scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                transition={bouncy}
                data-testid="combat-skip"
              >
                <span className="commit__main">
                  {mode === "attack" ? "No attacks" : "No blocks"}
                </span>
                <span className="commit__key">↵</span>
              </motion.button>
            ) : (
              <motion.button
                type="button"
                className="btn btn--primary commit"
                disabled={disabled || staged.length === 0}
                onClick={() => onDeclare(mode === "attack" ? "attackers" : "blockers", staged)}
                whileHover={{ y: -2, scale: 1.02 }}
                whileTap={{ scale: 0.97 }}
                transition={bouncy}
                data-testid="combat-confirm"
              >
                <span className="commit__main">
                  {mode === "attack"
                    ? `Attack with ${attackPairs.length}`
                    : `Confirm ${blockPairs.length} block${blockPairs.length === 1 ? "" : "s"}`}
                </span>
                {/* Enter already does this; nothing used to say so. */}
                <span className="commit__key">↵</span>
              </motion.button>
            )}
            <div className="commit-alt">
              {nothingToDeclare ? null : mode === "attack" ? (
                <button
                  type="button"
                  data-testid="combat-all"
                  disabled={disabled || unstagedAttackers.length === 0}
                  onClick={attackWithAll}
                  title="Send every creature that can attack"
                >
                  All attack{unstagedAttackers.length > 0 && ` (${unstagedAttackers.length})`}
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="combat-all"
                  disabled={disabled || newBlocks.length === 0}
                  onClick={blockWithAll}
                  title={
                    newBlocks.length === 0
                      ? "No block here is worth making on its own"
                      : "Block where it is worth it: survive and kill first, then walls, then trades"
                  }
                >
                  All defend{newBlocks.length > 0 && ` (${newBlocks.length})`}
                </button>
              )}
              {finish && !nothingToDeclare && (
                <button
                  type="button"
                  data-action-id={finish.id}
                  data-action-kind={finish.kind}
                  disabled={disabled}
                  onClick={() => onAct(finish.id)}
                  data-testid="combat-skip"
                >
                  {mode === "attack" ? "No attacks" : "No blocks"}
                </button>
              )}
            </div>
          </>
        ) : (
          commit && (
            <motion.button
              type="button"
              className="btn btn--primary commit"
              data-action-id={commit.id}
              data-action-kind={commit.kind}
              disabled={disabled}
              onClick={() => onAct(commit.id)}
              whileHover={disabled ? undefined : { y: -2, scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
              data-testid="commit"
            >
              <span className="commit__main">{commit.label}</span>
              <span className="commit__key">{commit.kind === "pass" ? "␣" : "↵"}</span>
            </motion.button>
          )
        )}
      </div>
    </>
  );
}
