/**
 * Jump straight to a region, instead of cycling to it.
 *
 * `L1`/`R1` step through the five regions, which is right at two or three and
 * wearing at five -- getting from the hand to the board is three presses and a
 * guess about which direction is shorter. Holding either shoulder opens this,
 * and a direction plus a release lands there in one gesture.
 *
 * ## `wheelwrap` is not a new name
 *
 * `input/stops.ts`'s focus trap has preferred `.wheelwrap` over every other
 * candidate since it was written, and nothing in the repo has ever rendered
 * one -- it was the prototype's name for exactly this control, carried into the
 * trap and then not built. So this needs no change to the trap at all: the
 * class is the contract, and the ring is inside the dial the moment it opens.
 *
 * ## Spokes are tools, not actions
 *
 * `data-stop="tool:group-<id>"` and no `data-action-id`. Choosing where to look
 * is not a move in the game, and `ActionPanel`'s invariant is that every legal
 * action is a control carrying an id exactly once in the document.
 */

import { motion } from "motion/react";
import { useEffect } from "react";
import { setCursor } from "../../input/cursor";
import { GROUPS, type GroupId, groupsPresent } from "../../input/groups";
import { stopId } from "../../input/stops";
import { ease } from "../../motion/springs";

interface Props {
  /** The region the ring is in, drawn as the resting spoke. */
  current: GroupId | null;
  /** Chosen a region. The dial closes and the caller moves the ring. */
  onPick: (id: GroupId) => void;
}

export function GroupDial({ current, onPick }: Props) {
  const present = groupsPresent();

  /*
   * The ring goes to the spoke you are already in, or the first one.
   *
   * Opening a picker with the ring nowhere is the same failure as opening a
   * dialog with it nowhere: every direction is a wall and the player concludes
   * the control is broken. `setCursor` rather than a `FocusRing` re-derive,
   * because this mounts and unmounts inside a hold and the resolve is one frame
   * too late to be felt as instant.
   *
   * ON MOUNT ONLY, and the empty dependency list is the whole point rather than
   * an oversight. `present` is a fresh array every render and `Table`
   * re-renders on every engine push, so a dependency on it re-ran this once a
   * second while an AI played -- putting the ring back on the landing spoke
   * under a player who had moved it. A picker that undoes your choice while you
   * are making it is worse than no picker.
   */
  // biome-ignore lint/correctness/useExhaustiveDependencies: opening is a moment, not a state; see above.
  useEffect(() => {
    const landing = current && present.includes(current) ? current : present[0];
    if (landing) setCursor(stopId.tool(`group-${landing}`));
  }, []);

  return (
    <motion.div
      className="wheelwrap"
      data-testid="group-dial"
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94 }}
      transition={ease}
      aria-label="Jump to a region of the board"
    >
      <div className="wheel">
        {GROUPS.filter((group) => present.includes(group.id)).map((group) => (
          <button
            key={group.id}
            type="button"
            className={
              group.id === current ? "wheel__spoke wheel__spoke--here" : "wheel__spoke"
            }
            data-stop={stopId.tool(`group-${group.id}`)}
            data-testid={`group-${group.id}`}
            onClick={() => onPick(group.id)}
          >
            {group.label}
          </button>
        ))}
      </div>
    </motion.div>
  );
}
