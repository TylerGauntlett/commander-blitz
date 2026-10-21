/**
 * The table.
 *
 * Owns layout and gesture routing; every rules question is answered by the
 * server's legal-action list. Three input paths converge on one `act(id)`:
 *
 *   1. drag a card from hand onto a lane
 *   2. click a card, then click its target
 *   3. press the button in the action bar
 *
 * The third always exists. If a gesture cannot be mapped to a legal action, it
 * does nothing at all -- it never invents one.
 */

import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { GameView } from "../../api/types";
import { play, type SoundName } from "../../audio/sfx";
import { useAttackLean } from "../../fx/useAttackLean";
import { setCursorContext } from "../../input/cursor";
import { getGroup } from "../../input/groups";
import { useStickScroll } from "../../input/stickScroll";
import { useCardHold } from "../../input/useCardHold";
import { useFollowThrough, useFollowUp } from "../../input/useFollowUp";
import { useGroupDial } from "../../input/useGroupDial";
import { useOpponentReading } from "../../input/useOpponentReading";
import { useTableGestures } from "../../input/useTableGestures";
import { useKeyboardShortcuts, usePadBindings } from "../../input/useTableInput";
import { useTableRegions } from "../../input/useTableRegions";
import { useTableVerbs } from "../../input/useTableVerbs";
import { reset as forgetCardRects } from "../../logic/cardRects";
import { removalsByOid } from "../../logic/removals";
import { seatOrder } from "../../logic/zoneGrouping";
import { useUiStore } from "../../state/uiStore";
import type { GameSession, useGame } from "../../state/useGame";
import { useHandheldLayout, usePhone } from "../../state/useHandheld";
import { useNarrationSkip } from "../../state/useNarrationSkip";
import { useTableDerived } from "../../state/useTableDerived";
import { useViewingSeat } from "../../state/useViewingSeat";
import { useZoomFit } from "../../state/useZoomFit";
import { Motes } from "../ui/Motes";
import { ActionPanel } from "./ActionPanel";
import { CardPreview } from "./CardPreview";
import { CombatArrows } from "./CombatArrows";
import { useCursorResolve } from "./FocusRing";
import { FxLayer, useScreenShake } from "./FxLayer";
import { ParticleLayer } from "./ParticleLayer";
import { PhaseTrack } from "./PhaseTrack";
import { ownsDecision } from "./PromptDialog";
import { TableFoot } from "./TableFoot";
import { TableOverlays } from "./TableOverlays";
import { TablePlay } from "./TablePlay";

/** Decisions where clicking your own creatures means "commit it to combat". */
const COMBAT_DECISIONS = new Set(["declare_attackers", "declare_blockers"]);

type Game = ReturnType<typeof useGame>;

interface Props {
  session: GameSession;
  game: Game;
  state: GameView;
  onQuit: () => void;
  onRematch: () => void;
}

export function Table({ game, state, onQuit, onRematch }: Props) {
  const { actions, events, narration, busy, aiThinking, waitingForPlayer, stalled } = game;
  const boardRef = useRef<HTMLDivElement>(null);
  // The three the zoom measures. Each is a grid track whose size the cards inside
  // it cannot change, which is the only reason reading them is safe; see
  // `state/useZoomFit.ts`.
  const tableRef = useRef<HTMLDivElement>(null);
  const mineRef = useRef<HTMLDivElement>(null);
  const podRef = useRef<HTMLDivElement>(null);
  const footRef = useRef<HTMLDivElement>(null);

  /*
   * The two holds, declared here because `back` unwinds them.
   *
   * `dialOpen` is the region picker; `heldCard` is the card being read full
   * screen. Both are local rather than in `uiStore` for the reason the `R2`
   * reading hold is: a hold has no meaning across a re-render, and a hold kept
   * in a store is a hold that can get stuck.
   */
  const { dialOpen, setDialOpen, pick: pickGroup, picked, clearPicked } = useGroupDial();
  // The right stick scrolls the reader, or the list the ring is in.
  useStickScroll();

  const { heldCard, setHeldCard, closeHold, readHovered, longPress } = useCardHold(state);

  const speed = useUiStore((s) => s.speed);
  const selectedOid = useUiStore((s) => s.selectedOid);
  const targetingActionIds = useUiStore((s) => s.targetingActionIds);
  const stagedAttacks = useUiStore((s) => s.stagedAttacks);
  const stagedBlocks = useUiStore((s) => s.stagedBlocks);
  const endTargeting = useUiStore((s) => s.endTargeting);
  const setPeek = useUiStore((s) => s.setPeek);
  const logOverlay = useUiStore((s) => s.logOverlay);
  const setViewing = useUiStore((s) => s.setViewing);
  const toggleLogOverlay = useUiStore((s) => s.toggleLogOverlay);
  const peek = useUiStore((s) => s.peek);
  const hover = useUiStore((s) => s.hover);
  const hoveredOid = useUiStore((s) => s.hoveredOid);
  const error = useUiStore((s) => s.error);
  const setError = useUiStore((s) => s.setError);

  // Motion values, not state: the shake writes these every frame and going
  // through React would re-render the whole board sixty times a second.
  const { x: shakeX, y: shakeY } = useScreenShake(narration.current);
  const viewer = state.players[state.seat];

  // Memoised because `useZoomFit` keys its solve on it: a fresh array every render
  // would re-run the fit on every render rather than when the board changes.
  const opponents = useMemo(
    () => seatOrder(state).filter((pid) => pid !== state.seat),
    [state],
  );

  // How every card in a graveyard or exile pile got there, for the zone modal.
  // Folded from the accumulated log rather than the view, which carries no
  // history; recomputed wholesale so an undo simply un-tells the story.
  const removals = useMemo(() => removalsByOid(events, game.cardName), [events, game.cardName]);
  const decisionKind = state.pending?.player === state.seat ? state.pending.kind : null;
  const inCombatDecision = decisionKind !== null && COMBAT_DECISIONS.has(decisionKind);
  const locked = busy || narration.busy;

  /*
   * Which layout this viewport wants.
   *
   * Viewport-driven and nothing else: a desktop player who picks up a
   * controller keeps the wide board and gains the ring, and a Deck user with no
   * pad gets the compact board and no glyphs. The two signals are deliberately
   * independent -- see `input/inputMode.ts`.
   */
  const handheld = useHandheldLayout();
  /** A handheld whose floors are too big for it. See `logic/breakpoints.ts`. */
  const phone = usePhone();

  /** Which opponent is being read while `R2` is held. See `useOpponentReading`. */
  const reading = useOpponentReading(handheld, opponents, state.seat);

  // Card positions are remembered globally, by oid, and oids restart with each
  // game. Leaving them behind would let the first death of a new table fly out
  // of wherever the last table's card #12 happened to be sitting.
  useEffect(() => forgetCardRects, []);

  // A decision's buttons must exist exactly once in the document. Whichever
  // surface owns a decision renders its ids; everything else stands down.
  //
  // There used to be two surfaces to keep straight here -- an action bar and a
  // combat panel, each with its own stand-down rule and a comment explaining why
  // they disagreed. `ActionPanel` is both of them, so the only question left is
  // whether something full-screen owns the decision instead -- which is now two
  // somethings, the dialog and `OpeningHand`, and `ownsDecision` is the one
  // question that covers both.
  const modalOwnsDecision = ownsDecision(state);

  // Depend on the `mutate` functions, which react-query keeps stable, rather
  // than on the mutation objects, which are new every render -- otherwise every
  // callback below is rebuilt each render and the keyboard listener with it.
  const actMutate = game.act.mutate;
  const declareMutate = game.declare.mutate;
  const chooseMutate = game.choose.mutate;
  const undoMutate = game.undo.mutate;
  const fullControlMutate = game.setFullControl.mutate;
  const manualManaMutate = game.setManualMana.mutate;

  const { skipAll, gateInput } = useNarrationSkip(narration, busy);

  /** A sound the player's own hand caused, played without waiting for anybody. */
  const muted = useUiStore((s) => s.muted);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const cue = useCallback((sound: SoundName) => {
    if (!mutedRef.current) play(sound);
  }, []);

  const act = useCallback(
    (actionId: string) => {
      if (gateInput()) return;
      endTargeting();
      cue("drop");
      actMutate(actionId);
    },
    [gateInput, endTargeting, actMutate, cue],
  );

  /** A pick-several decision, committed as one set. See `logic/pickSeveral.ts`. */
  const choose = useCallback(
    (choices: number[]) => {
      if (gateInput()) return;
      cue("drop");
      chooseMutate(choices);
    },
    [gateInput, chooseMutate, cue],
  );

  // ---------------------------------------------------------------- derived

  const derived = useTableDerived({
    state,
    actions,
    targetingActionIds,
    decisionKind,
    inCombatDecision,
    selectedOid,
    stagedBlocks,
    hoveredOid,
  });
  const {
    playableOids,
    actionableOids,
    targeting,
    targetableOids,
    targetChosen,
    combatCandidates,
  } = derived;

  // ------------------------------------------------------------ interaction

  const { follow, setFollow, followAt, followUp } = useFollowUp();

  const {
    playFromHand,
    onStackItem,
    onDropOnZone,
    onBoardCard,
    onSelectPlayer,
    onDeclare,
    onBarAct,
  } = useTableGestures({
    holdCard: setHeldCard,
    state,
    actions,
    gateInput,
    act,
    cue,
    followUp,
    targeting,
    targetableOids,
    combatCandidates,
    decisionKind,
    inCombatDecision,
    declareMutate,
  });

  const viewing = useViewingSeat(state, reading);

  // ------------------------------------------------------------ controller

  const { back, secondary } = useTableVerbs({
    state,
    actions,
    decisionKind,
    dialOpen,
    setDialOpen,
    heldCard,
    setHeldCard,
    viewing,
    act,
    onBarAct,
    cue,
  });

  useAttackLean(stagedAttacks, boardRef);

  /*
   * The cursor re-derives after every commit *this* component makes.
   *
   * `Screen` mounts the ring itself, but React only runs layout effects for
   * components that re-render -- and the board re-renders on every engine push
   * without its wrapper doing so. Without this the ring would go out the first
   * time a card it was sitting on left play and never come back, because
   * navigation starts from `[data-cursor]`.
   */
  useCursorResolve();

  // Following a decision: see `input/useFollowUp.ts`, and why it is two hooks.
  useFollowThrough({ follow, setFollow, followAt, actions, state, stagedBlocks });

  /*
   * ...and the context, which decides whether the ring flies or teleports. A
   * dialog opening is a new context: springing 600px from a board card to a
   * modal button is a spring between two things that were never on screen
   * together, which reads as a glitch rather than as movement.
   */
  useEffect(() => {
    setCursorContext(`game|${peek?.zone ?? ""}|${state.pending?.kind ?? ""}`);
  }, [peek?.zone, state.pending?.kind]);

  const { enterGroup, jumpToCommit, stepGroup } = useTableRegions({
    state,
    actions,
    decisionKind,
    modalOwnsDecision,
    narration,
    cue,
  });

  /*
   * A region chosen on the dial, entered on the commit that took the dial
   * away -- `useGroupDial` says why it cannot be entered any sooner. The
   * region the ring is already in is no move at all: the dial closing hands
   * the ring back to where it stood, which is the better answer.
   */
  useEffect(() => {
    if (dialOpen || picked === null) return;
    clearPicked();
    if (picked !== getGroup()) enterGroup(picked);
  }, [dialOpen, picked, clearPicked, enterGroup]);

  usePadBindings({
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
  });

  // ------------------------------------------------------------- keyboard

  useKeyboardShortcuts({
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
  });

  // ---------------------------------------------------------------- render

  /*
   * How big the cards are, solved against the room they actually have.
   *
   * The three refs below are the only measurements taken, and `useZoomFit`
   * documents why each is safe to read -- the short version is that all three are
   * grid tracks whose size the cards inside cannot change. `opponentCardScale` and
   * `CARD_SCALE.own` / `.hand` are still here, but as the *ceilings* the solve may
   * not exceed rather than as the sizes; see `logic/cardSize.ts`.
   */
  const zoom = useZoomFit({
    state,
    actionableOids,
    opponents,
    handCount: viewer.hand?.length ?? 0,
    handheld,
    phone,
    tableRef,
    mineRef,
    footRef,
    podRef,
  });

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: the table root takes the context-menu and long-press gestures that open the card reader; it is the board, not a control, and the pad reaches the reader through the focus ring.
    <div
      className="table"
      data-testid="table"
      ref={tableRef}
      onContextMenu={readHovered}
      {...longPress}
      // Read by e2e rather than making it parse a resolved `calc()` off a lane, and
      // handy for eyeballing the solve in devtools. Same spirit as
      // `data-stack-count` on a stack.
      data-zoom-board={zoom.board.toFixed(3)}
      data-zoom-pod={zoom.pod.toFixed(3)}
      data-zoom-hand={zoom.hand.toFixed(3)}
      data-zoom-locked={zoom.locked || undefined}
      data-handheld={handheld || undefined}
      /*
        The box an opponent's lanes were solved inside, handed back to CSS.

        `theme.css` still declares `--pod-lanes-h` and it is still the floor;
        this only ever raises it, and only where the seat count says the room is
        going spare. Written here rather than on `.play` because the property is
        registered `inherits: true` and `.mat--compact` is several levels down.
        `null` on the pinned path leaves the stylesheet's clamp alone.
      */
      style={
        zoom.podLanesH === null
          ? undefined
          : ({ "--pod-lanes-h": `${Math.round(zoom.podLanesH)}px` } as React.CSSProperties)
      }
    >
      {/*
        THE AIR, and it is the first child for a reason.

        The board was one static radial gradient with no `@keyframes` anywhere
        on it, standing next to a lobby with a lit hall, drifting light and
        sixteen motes in it -- so pressing PLAY took the player out of a room
        and into a wallpaper. This is the least the board can do about that: a
        wash that drifts on a 64s cycle, a vignette, and a thin field of the
        lobby's own motes. `styles/ambience.css` owns all three.

        IT SITS OUTSIDE `.table__body`, which is the load-bearing placement.
        That div carries the screen-shake `x`/`y` and is the `data-fx-origin`
        every effect coordinate is measured from -- ambience inside it would
        shake with the board on every hit, and would move the origin's contents
        without moving the origin. Here it is a sibling under both of them,
        pinned to `.table` and pointer-transparent.
      */}
      <div className="table__air" aria-hidden="true">
        <div className="table__wash" />
        <div className="table__vig" />
        {/* Ten rather than the lobby's sixteen: there are up to four seats, a
            hand and a stack on this screen already. */}
        <Motes count={10} />
      </div>

      <PhaseTrack state={state} />

      {/*
        `data-fx-origin` marks the box every effect coordinate is relative to.
        `FxLayer` and `CombatArrows` already resolve it through `boardRef`, but a
        card actuator is reached from a module function with no props and no
        context, so it finds this by walking up from the card itself.
      */}
      <motion.div
        className="table__body"
        ref={boardRef}
        data-fx-origin
        style={{ x: shakeX, y: shakeY }}
      >
        {/*
          THE STACK FLOATS OVER THE BOARD, and the left rail is gone.

          It held two things. The log is reference you consult rather than
          watch, so it is an overlay on `View` -- which is what a handheld
          already did, and there was never an argument for a desktop keeping a
          232px column permanently open for it. The stack is the other, and it
          is urgent exactly when it is non-empty and absent the rest of the
          time, which is the shape of a thing that should not own a column at
          all.

          So it is a pile of real card faces over the top-left of the play area,
          growing down over the viewer's own panel as it deepens. `StackPanel`
          already drew exactly this -- plies at a 26px offset, each peeking out
          by its own name strip -- it simply drew it inside a rail.

          What the retired column buys is 232px of board at every size, which is
          most of what the foot costs by moving inside this column so the right
          rail can run to the bottom edge.
        */}
        <TablePlay
          state={state}
          viewer={viewer}
          opponents={opponents}
          podRef={podRef}
          mineRef={mineRef}
          zoom={zoom}
          derived={derived}
          selectedOid={selectedOid}
          stagedAttacks={stagedAttacks}
          stagedBlocks={stagedBlocks}
          viewing={viewing}
          setViewing={setViewing}
          locked={locked}
          hover={hover}
          onBoardCard={onBoardCard}
          onStackItem={onStackItem}
          onSelectPlayer={onSelectPlayer}
          playFromHand={playFromHand}
        />

        {/*
          The right rail is three things: the card you are reading, the panel of
          things you can do about it, and the commit slab. Nothing else.

          All of it used to live across the foot -- the action bar took a fixed
          420px out of the row the hand wanted, and combat was a full-width
          banner under the board, which put the decision as far as possible from
          the cards it was about. Here the creature you are reading and the list
          you are staging it into are one glance apart, and the foot belongs to
          the hand alone.
        */}
        <aside className="rail rail--right">
          <CardPreview state={state} />
          <ActionPanel
            state={state}
            actions={actions}
            onAct={act}
            onStage={onBarAct}
            onDeclare={onDeclare}
            onChoose={choose}
            onUndo={() => undoMutate()}
            onQuit={onQuit}
            onToggleFullControl={(value) => fullControlMutate(value)}
            onToggleManualMana={(value) => manualManaMutate(value)}
            narrating={narration.busy}
            onSkipNarration={skipAll}
            busy={busy}
            aiThinking={aiThinking}
            waitingForPlayer={waitingForPlayer}
            standDown={modalOwnsDecision}
          />
        </aside>

        {/*
          THE FOOT IS INSIDE THE BODY NOW, and that is the round's biggest
          single change.

          It used to be a sibling, spanning the full width under both rails, so
          the right rail stopped where the hand started -- 514px at 1280x800,
          of which the rows the turn is actually spent in got 172.
          the handheld-board round (`docs/adr/0013-handheld-floors-are-ci-gates.md`) measures the same rail at 748px when it runs
          to the foot instead, and the action list at 363-398.

          It also fixes something quietly: `data-fx-origin` is on this element,
          and with the foot outside it every card flying from the hand to the
          board crossed the origin's boundary. Every such flight is interior now.
        */}
        <TableFoot
          footRef={footRef}
          handheld={handheld}
          state={state}
          actions={actions}
          viewer={viewer}
          targeting={targeting}
          targetableOids={targetableOids}
          targetChosen={targetChosen}
          endTargeting={endTargeting}
          playableOids={playableOids}
          selectedOid={selectedOid}
          zoom={zoom}
          locked={locked}
          viewing={viewing}
          setDialOpen={setDialOpen}
          playFromHand={playFromHand}
          onDropOnZone={onDropOnZone}
        />

        <CombatArrows state={state} boardRef={boardRef} />
        <ParticleLayer boardRef={boardRef} />
        <FxLayer beat={narration.current} speed={speed} boardRef={boardRef} state={state} />
      </motion.div>

      <TableOverlays
        state={state}
        actions={actions}
        events={events}
        cardName={game.cardName}
        error={error}
        setError={setError}
        stalled={stalled}
        heldCard={heldCard}
        closeHold={closeHold}
        dialOpen={dialOpen}
        pickGroup={pickGroup}
        logOverlay={logOverlay}
        toggleLogOverlay={toggleLogOverlay}
        act={act}
        followUp={followUp}
        locked={locked}
        removals={removals}
        onRematch={onRematch}
        onQuit={onQuit}
      />
    </div>
  );
}
