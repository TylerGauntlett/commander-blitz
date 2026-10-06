/**
 * Sound, undo, the control scheme and quit, folded into one menu.
 *
 * A MODAL WHILE IT IS OPEN, AND THAT IS FOUR THINGS (TECH_DEBT FB-12).
 *
 * The menu used to be a popover only a mouse could use properly. It carried no
 * `data-modal-root`, so `stops.ts:stopRoot` still answered `.table` and
 * `escapeGroup` let the ring walk straight out of it across the board; the
 * pad's `B` went down `Table`'s unwind ladder, which did not know the menu was
 * open, and cancelled whatever was underneath it instead; opening it left the
 * ring on the gear; and the control-scheme picker inside it had no stops at
 * all, so the one setting that exists to rescue a controller was the one a
 * controller could not reach. Now:
 *
 * - **It traps the ring.** `.settings__menu` is a `data-modal-root` while it is
 *   up, so the menu is the whole world to `nav`, the pointer snap and the
 *   resolver -- the same trap every dialog in this client uses.
 * - **Opening it puts the ring on its first item**, explicitly below rather
 *   than by trusting the resolver to notice, so a component test with no
 *   `FocusRing` sees the same thing a player does.
 * - **`B` closes it.** The open flag lives in `uiStore` so `Table.back` can
 *   take it as one level of the unwind. Escape is `B` (`input/buttons.ts`), so
 *   that is also the keyboard's way out -- the old `onKeyDown` here, which only
 *   worked with DOM focus inside, is gone with the double-unwind it raced.
 * - **Closing puts the ring back on the gear**, unless the menu was put away
 *   by a press somewhere else, which is a mouse player going somewhere.
 *
 * Lifted out of `ActionPanel.tsx` as it was: the open flag, the ref, the
 * close-and-restore-the-ring rule and the press-anywhere-else listener all
 * moved together, and every `data-stop`, `data-testid` and handler rides with
 * the buttons so the ring reaches them exactly as it did.
 */

import { useEffect, useRef } from "react";
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
  const settingsOpen = useUiStore((s) => s.settingsOpen);
  const setSettingsOpen = useUiStore((s) => s.setSettingsOpen);
  const settingsRef = useRef<HTMLDivElement>(null);

  /*
   * Leaving the game with the menu up must not open it on the next one: the
   * flag is in a store that outlives this component, and the board is
   * remounted per game.
   */
  useEffect(() => () => setSettingsOpen(false), [setSettingsOpen]);

  /*
   * Where the ring goes as the menu opens and closes.
   *
   * OPENING puts it on the first item. `cursor.ts:resolveCursor` would get
   * there too, a microtask later, when its observer sees a new modal root --
   * but saying so here makes it true without a `FocusRing` mounted, and does
   * not depend on which of the two runs first.
   *
   * CLOSING puts it back on the button that opened it. Without this the ring
   * is standing on a node that is about to stop existing, and `resolveCursor`'s
   * fallback is "the first stop of the surface on top" -- which is the far side
   * of the board. Closing a menu must not move the player somewhere they did
   * not ask to go. The one close that does NOT come back is a press somewhere
   * else (`returnRing` below): that is a mouse player who has already gone
   * where they meant to, and dragging the ring back to the gear would undo it.
   *
   * In an effect rather than in the handlers, because the close that matters
   * most happens in `Table` (`B`), which has no way to name this button.
   */
  const returnRing = useRef(true);
  const wasOpen = useRef(false);
  useEffect(() => {
    if (settingsOpen) {
      wasOpen.current = true;
      returnRing.current = true;
      setCursor(stopId.tool("mute"));
      return;
    }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    if (returnRing.current) setCursor(stopId.tool("settings"));
  }, [settingsOpen]);

  const closeSettings = () => setSettingsOpen(false);

  /*
   * A press anywhere else closes it. `pointerdown` rather than `click`, so the
   * menu is gone before whatever was pressed underneath it acts -- and capture,
   * so a control that stops propagation cannot leave the menu open behind it.
   */
  useEffect(() => {
    if (!settingsOpen) return;
    const onDown = (event: PointerEvent) => {
      if (settingsRef.current?.contains(event.target as Node)) return;
      returnRing.current = false;
      setSettingsOpen(false);
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [settingsOpen, setSettingsOpen]);

  /*
    Sound, undo and quit, folded into one control. See `settingsOpen`
    above for why: three buttons pressed once a game each, at the same
    weight as the two modes beside them that change how every priority
    window behaves.

    No `onKeyDown` for Escape any more. Escape is the pad's `B`, and `B` is
    `Table`'s unwind, which closes this menu as one level of it. A second
    listener here closed the menu AND let the same press go on down the
    ladder a frame later, cancelling whatever the player was in the middle
    of -- the very thing its old `stopPropagation` was trying to prevent,
    and could not, because the pad listens in the capture phase.
   */
  return (
    <div className="settings" ref={settingsRef}>
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
        <div className="settings__menu" role="menu" data-testid="settings-menu" data-modal-root>
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
            surfaces cannot drift -- with `stops`, because this surface
            declares its stops and a native button with no `data-stop` is
            invisible to the ring here (`stops.ts:stopsIn`). It used to be
            exactly that: the comment above was true of the door and false
            of the menu, and the four buttons were reachable by mouse only.
          */}
          <div className="settings__scheme" data-testid="settings-scheme">
            <span className="settings__label">Controls</span>
            <SchemePicker stops />
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
