/**
 * Sound, undo, the control scheme and quit, folded into one menu.
 *
 * OPEN (TECH_DEBT FB-12): the open menu carries no `data-modal-root` and binds
 * no `B`. `stops.ts:stopRoot` therefore still answers `.table`, so
 * `escapeGroup` lets the ring walk out of the menu across the board, and the
 * pad's `B` goes to `Table`'s unwind ladder, which does not know the menu is
 * open. Escape works only through the `onKeyDown` below, which needs DOM focus
 * inside. Documented here rather than fixed on the refactor branch.
 *
 * Lifted out of `ActionPanel.tsx` as it was: the open flag, the ref, the
 * close-and-restore-the-ring rule and the press-anywhere-else listener all
 * moved together, and every `data-stop`, `data-testid` and handler rides with
 * the buttons so the ring reaches them exactly as it did.
 */

import { useEffect, useRef, useState } from "react";
import { setCursor } from "../../input/cursor";
import { stopId } from "../../input/stops";
import { useUiStore } from "../../state/uiStore";
import { SchemePicker } from "../ui/SchemePicker";

interface Props {
  busy: boolean;
  onUndo: () => void;
  onQuit: () => void;
}

export function SettingsMenu({ busy, onUndo, onQuit }: Props) {
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

  /*
    Sound, undo and quit, folded into one control. See `settingsOpen`
    above for why: three buttons pressed once a game each, at the same
    weight as the two modes beside them that change how every priority
    window behaves.

    `onKeyDown` rather than a document listener for Escape, and it stops
    propagating: `Table` binds `Escape` to a strict unwind of the whole
    board, so an un-stopped one here would close the menu AND cancel
    whatever the player was in the middle of.
   */
  return (
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
  );
}
