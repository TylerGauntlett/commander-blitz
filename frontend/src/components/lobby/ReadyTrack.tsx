/**
 * Four segments, one per chair, filling as each card turns face-up and stamps.
 *
 * The count beside it is "of the seats that are filled", not "of four": a
 * three-player pod is not permanently 3/4 done, and a progress bar that can
 * never complete is worse than no progress bar.
 */

import type { PodView } from "../../api/types";
import { filledSeats, podSize, readyTrack, seatLabel } from "../../logic/lobby";

export function ReadyTrack({ pod }: { pod: PodView }) {
  const segments = readyTrack(pod);
  const done = filledSeats(pod).filter((seat) => seat.ready).length;

  return (
    <div className="turned" data-testid="ready-track">
      <div className="turned__l">
        Cards face up{" "}
        <span className="turned__n tabular" data-testid="ready-count">
          {done} of {podSize(pod)}
        </span>
      </div>
      <div className="turned__t">
        {segments.map((segment, index) => {
          const label = seatLabel(pod, index);
          return (
            <i
              key={pod.seats[index].index}
              className={`turned__s turned__s--${segment}`}
              data-state={segment}
              data-hint={
                segment === "none"
                  ? `Seat ${index + 1} · empty`
                  : `${label.title} · ${segment === "on" ? "ready" : label.sub}`
              }
            />
          );
        })}
      </div>
    </div>
  );
}
