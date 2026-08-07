/** Play-by-play, newest last. */

import { useEffect, useRef } from "react";
import type { GameEvent, GameView } from "../api/types";
import { describeEvent, playerNames } from "../logic/labels";
import { useUiStore } from "../state/uiStore";

export function EventLog({ state, events }: { state: GameView; events: GameEvent[] }) {
  const open = useUiStore((s) => s.logOpen);
  const toggle = useUiStore((s) => s.toggleLog);
  const bottom = useRef<HTMLDivElement>(null);
  const names = playerNames(state);
  const lines = events
    .map((event, index) => ({ text: describeEvent(event, names), key: index }))
    .filter((entry): entry is { text: string; key: number } => entry.text !== null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, []);

  return (
    <aside className={open ? "event-log" : "event-log event-log--closed"}>
      <header className="event-log__header">
        <span>Log</span>
        <button type="button" className="ghost-button" onClick={toggle}>
          {open ? "Hide" : "Show"}
        </button>
      </header>
      {open && (
        <div className="event-log__lines">
          {lines.slice(-200).map((line) => (
            <div className="event-log__line" key={line.key}>
              {line.text}
            </div>
          ))}
          <div ref={bottom} />
        </div>
      )}
    </aside>
  );
}
