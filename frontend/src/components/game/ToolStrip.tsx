/**
 * The tool strip: the settings menu, the two modes that change how the game
 * plays, and the skip button while a beat is playing.
 *
 * Lifted out of `ActionPanel.tsx` as it was. `ActionPanel` still decides
 * WHERE it goes -- in the rail on a desktop, portaled into the foot on a
 * handheld -- so this is only the row itself.
 */

import type { GameView } from "../../api/types";
import { stopId } from "../../input/stops";
import { SettingsMenu } from "./SettingsMenu";

interface Props {
  state: GameView;
  busy: boolean;
  narrating: boolean;
  onToggleFullControl: (value: boolean) => void;
  onToggleManualMana: (value: boolean) => void;
  onSkipNarration: () => void;
  onUndo: () => void;
  onQuit: () => void;
}

export function ToolStrip({
  state,
  busy,
  narrating,
  onToggleFullControl,
  onToggleManualMana,
  onSkipNarration,
  onUndo,
  onQuit,
}: Props) {
  return (
    <div className="tools">
      <SettingsMenu busy={busy} onUndo={onUndo} onQuit={onQuit} />
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
    </div>
  );
}
