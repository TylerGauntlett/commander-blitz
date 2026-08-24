/**
 * Specks of light drifting up through a screen.
 *
 * `fx/presets.ts:225` is the app's own `motes()` -- gold and white flecks
 * rising, the one preset in the vocabulary that is ambience rather than an
 * event. This is that preset re-expressed as sixteen spans on infinite CSS
 * animations, and it exists as a component for the reason `Room.tsx` exists:
 * the lobby had it and the board did not, so the two rooms of this app did not
 * look like they were in the same building.
 *
 * ## It takes the colour of wherever it is hung
 *
 * Nothing here names a colour. `.mote` reads `--lit`, which the lobby writes
 * per selected card (`Room.tsx`) and the board writes once on `.table__air`.
 * A caller changes the light and the flecks follow, through inheritance rather
 * than through React -- the same trick the floor sigil and the light pool use.
 *
 * ## The positions are fixed, not random
 *
 * `Math.random()` here would mean no two screenshots of a screen ever compare,
 * which is what `e2e/` spends its time doing. The arithmetic below is the
 * cheapest thing that looks unpatterned: three coprime strides over the index,
 * so `left`, duration and delay never come back into phase inside sixteen.
 */

import type { CSSProperties } from "react";

const MOTES = Array.from({ length: 16 }, (_, i) => ({
  left: 6 + ((i * 79) % 88),
  dur: 11 + ((i * 7) % 9),
  delay: (i * 13) % 11,
  drift: ((i % 5) - 2) * 22,
}));

interface Props {
  /**
   * How many to hang, from the head of the fixed list.
   *
   * Sixteen is the lobby's, on an empty screen. The board is not empty -- there
   * are up to four seats, a hand and a stack on it -- so it runs a thinner
   * field: ambience there has to be noticed only when you are not looking at
   * anything, which is the whole difficulty of putting any on a board at all.
   */
  count?: number;
}

export function Motes({ count = MOTES.length }: Props) {
  return (
    <div className="motes" aria-hidden="true">
      {MOTES.slice(0, count).map((m) => (
        <span
          key={`${m.left}-${m.dur}-${m.delay}`}
          className="mote"
          style={
            {
              left: `${m.left}%`,
              animationDuration: `${m.dur}s`,
              animationDelay: `-${m.delay}s`,
              "--drift": `${m.drift}px`,
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}
