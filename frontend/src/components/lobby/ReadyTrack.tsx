/**
 * One segment per chair, filling as each card turns face-up and stamps.
 *
 * The count beside it is "of the seats that are filled", not "of four": a
 * three-player pod is not permanently 3/4 done, and a progress bar that can
 * never complete is worse than no progress bar.
 *
 * IT USED TO SAY "CARDS FACE UP" IN FRONT OF THE NUMBER, and that was three
 * words explaining a row of pips that sits directly under four cards, half of
 * which are visibly face up. The pips are the sentence; `aria-label` carries
 * the same fact for anybody who cannot see them, which is the only reader the
 * words were ever for.
 */

import type { PodView } from "../../api/types";
import { filledSeats, podSize, readyTrack, seatLabel } from "../../logic/lobby";

export function ReadyTrack({ pod }: { pod: PodView }) {
  const segments = readyTrack(pod);
  const done = filledSeats(pod).filter((seat) => seat.ready).length;
  const total = podSize(pod);

  return (
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: a labelled readout on a generic element, written before Biome 2 had this rule. The fix is a role, which changes what a screen reader announces -- a behaviour change, so it waits for an a11y pass rather than riding a dependency upgrade.
    <div
      className="pips"
      data-testid="ready-track"
      aria-label={`${done} of ${total} cards face up`}
    >
      <span className="pips__row" aria-hidden="true">
        {segments.map((segment, index) => {
          const label = seatLabel(pod, index);
          return (
            <i
              key={pod.seats[index].index}
              className={`pips__s pips__s--${segment}`}
              data-state={segment}
              data-hint={
                segment === "none"
                  ? `Seat ${index + 1} · empty`
                  : `${label.title} · ${segment === "on" ? "ready" : label.sub}`
              }
            />
          );
        })}
      </span>
      <b className="pips__n tabular" data-testid="ready-count">
        {done}/{total}
      </b>
    </div>
  );
}
