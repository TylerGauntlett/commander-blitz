/**
 * Spatial navigation, as pure arithmetic over rectangles.
 *
 * One walk, every screen. Candidates are scored by distance along the pressed
 * axis plus a *punished* perpendicular drift, and the punishment is the whole
 * design: it is what keeps a column a column when the rows below it are ragged,
 * which on a board of thirty permanents is the difference between a cursor that
 * feels deliberate and one that feels magnetic.
 *
 * This module takes rects rather than elements on purpose. Everything about the
 * scoring is arguable -- `PERP` especially -- and an argument you can only have
 * by opening a browser is an argument nobody has. `tests/spatialNav.test.ts`
 * pins the behaviour against synthetic layouts, and
 * `src/components/game/SpatialNav.stories.tsx` is where it gets looked at.
 *
 * The DOM half lives in `stops.ts`, which supplies the rects and applies the
 * focus trap. Nothing here touches `document`.
 */

/**
 * How much a sideways drift costs relative to distance along the axis.
 *
 * At 2.4 a candidate one card to the side has to be roughly two and a half
 * cards nearer to win, which is what stops "down" from sliding into the next
 * column when the card directly below is slightly further away.
 */
export const PERP = 2.4;

/**
 * Candidates nearer than this along the axis are not in that direction at all.
 *
 * Rects overlap constantly -- an attached aura sits partly under its host, a
 * badge sits on the card it belongs to -- and without a floor those score ~0
 * and win every press, so the ring would never leave. Six pixels is past
 * rounding and well under any real gap.
 */
export const ALONG_MIN = 6;

/**
 * How far sideways a candidate may sit when it does not line up at all.
 *
 * `PERP` ranks candidates; it cannot reject one. With a single candidate in a
 * direction it wins however absurd its score, and that produced a real defect:
 * from the leftmost creature, "up" jumped 260px across the board to a *tapped*
 * permanent whose centre happened to be 20px higher, because a tapped card is
 * landscape and therefore shorter. That reads as the ring teleporting.
 *
 * So a candidate qualifies if its perpendicular extent OVERLAPS the current
 * one -- it is genuinely above, below, or beside it -- or, failing that, if its
 * sideways offset is within this multiple of the distance it travels along the
 * axis. A real diagonal step to the next row still qualifies comfortably; a
 * lunge across the whole board does not, and the player gets a wall they can
 * see instead of a jump they cannot explain.
 *
 * ## The one caller that turns it off
 *
 * `relaxed` drops this test and keeps everything else, and exactly one caller
 * passes it: `stops.ts:escapeGroup`, on a second pass, after the strict one has
 * come back empty for the WHOLE BOARD. Inside a region the rule is what makes a
 * column feel like a column and it is never relaxed. At a region's edge the
 * player has already established there is nothing on their line -- the strict
 * pass said so -- and the alternative is a wall with somewhere obvious to go on
 * the other side of it, which is the "you cannot move up for no reason" a
 * playtester reports. `ring.ts:longHop` is what stops the resulting jump
 * strobing across the screen.
 */
export const DRIFT_LIMIT = 3;

export type Dir = "up" | "down" | "left" | "right";

/** Just enough of a DOMRect to score it. */
export interface NavRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface Candidate {
  id: string;
  rect: NavRect;
}

const centre = (r: NavRect): { x: number; y: number } => ({
  x: r.left + r.width / 2,
  y: r.top + r.height / 2,
});

/**
 * Score one candidate, or `null` if it does not lie in `dir` at all.
 *
 * Exported because the story renders it: seeing *why* a stop lost is worth more
 * than seeing which one won.
 */
/**
 * Whether two boxes line up on the axis `dir` does NOT travel along.
 *
 * Overlapping extents mean the candidate really is above, below or beside this
 * one rather than merely somewhere in that half-plane. Pulled out of
 * `scoreStop` because `pickStop` needs the same answer for a different reason
 * -- see the row rule there.
 */
export function alignedWith(from: NavRect, to: NavRect, dir: Dir): boolean {
  return dir === "left" || dir === "right"
    ? from.top < to.top + to.height && to.top < from.top + from.height
    : from.left < to.left + to.width && to.left < from.left + from.width;
}

export function scoreStop(
  from: NavRect,
  to: NavRect,
  dir: Dir,
  relaxed = false,
): number | null {
  const a = centre(from);
  const b = centre(to);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const along = dir === "left" ? -dx : dir === "right" ? dx : dir === "up" ? -dy : dy;
  const horizontal = dir === "left" || dir === "right";
  const perp = horizontal ? Math.abs(dy) : Math.abs(dx);
  if (along <= ALONG_MIN) return null;
  if (!relaxed && !alignedWith(from, to, dir) && perp > along * DRIFT_LIMIT) return null;
  return along + perp * PERP;
}

/**
 * The stop `dir` should move to, or `null` for a wall.
 *
 * `null` is a real answer and callers must draw it: `move()` plays the deny
 * voice, rumbles, and nudges the ring into the wall so the edge of the board is
 * something you can see rather than something you infer from nothing happening.
 *
 * Ties resolve to the earlier candidate, so a caller passing stops in document
 * order gets a deterministic result -- which is what makes the unit tests worth
 * having.
 */
export function pickStop(
  from: NavRect,
  candidates: readonly Candidate[],
  dir: Dir,
  exclude?: string,
  relaxed = false,
): string | null {
  let best: string | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  let inRow: string | null = null;
  let inRowScore = Number.POSITIVE_INFINITY;
  for (const candidate of candidates) {
    if (candidate.id === exclude) continue;
    const score = scoreStop(from, candidate.rect, dir, relaxed);
    if (score === null) continue;
    if (score < bestScore) {
      bestScore = score;
      best = candidate.id;
    }
    if (alignedWith(from, candidate.rect, dir) && score < inRowScore) {
      inRowScore = score;
      inRow = candidate.id;
    }
  }
  /*
   * THE ROW WINS OUTRIGHT, however far along it the nearest one is.
   *
   * `PERP` ranks a sideways drift against distance travelled; it cannot rank a
   * drift against *being on the same line*, and those are different questions.
   * The pod's rail is the case that named it: Lock in on the left, Deal on the
   * right, a thousand pixels of status between them -- and pressing Right from
   * Lock in went UP, to the nearest chair's button, because 195px sideways plus
   * a 166px drift scores better than 1082px straight along the row. Every rail,
   * toolbar and button strip in a menu has that shape, and every one of them
   * would have had that bug.
   *
   * It is also the rule a player already believes: a row is a thing you walk
   * along, and you leave it by pressing the direction that leaves it. So an
   * aligned candidate -- one whose box genuinely overlaps this one on the other
   * axis -- always beats a diagonal, and the diagonal is what you get when
   * there is nothing on your line at all.
   */
  return inRow ?? best;
}

/**
 * The stop nearest a point, for the pointer path.
 *
 * The Deck's trackpads and touchscreen arrive as ordinary mouse events (Steam
 * Input's pad-as-mouse), so the cursor has to be reachable by pointing as well
 * as by walking -- and a pointer that snaps to a stop is the difference between
 * a trackpad being usable and being a novelty. `null` when nothing is within
 * `within`, so a click on empty felt does not drag the ring across the board.
 *
 * Ties break toward the SMALLER rect, and that is the interesting half. Stops
 * nest constantly -- a zone pile inside an orb, a defender chip inside an
 * attacker row, a badge on a card -- so a pointer inside both is the normal
 * case rather than the edge one, and both score a distance of zero. The
 * smallest box containing the point is the most specific thing the player can
 * be pointing at, and it is the one they meant.
 */
export function nearestStop(
  x: number,
  y: number,
  candidates: readonly Candidate[],
  within = Number.POSITIVE_INFINITY,
): string | null {
  let best: string | null = null;
  let bestDistance = within;
  let bestArea = Number.POSITIVE_INFINITY;
  for (const candidate of candidates) {
    const { rect } = candidate;
    // Distance to the rect, not to its centre: a wide lane's centre can be
    // further from the pointer than a small badge sitting inside it.
    const dx = Math.max(rect.left - x, 0, x - (rect.left + rect.width));
    const dy = Math.max(rect.top - y, 0, y - (rect.top + rect.height));
    const distance = Math.hypot(dx, dy);
    const area = rect.width * rect.height;
    if (distance < bestDistance || (distance === bestDistance && area < bestArea)) {
      bestDistance = distance;
      bestArea = area;
      best = candidate.id;
    }
  }
  return best;
}

/**
 * Stops no direction from any other stop can reach.
 *
 * "Can a controller get to everything?" is a graph question, and walking the
 * board with synthetic key presses is a bad way to ask it: a fixed sweep
 * explores whatever its own order happens to explore, so it reports absences it
 * has not established. Twice while building this it claimed controls were
 * unreachable that were one press away, which is worse than not asking -- it
 * sends you looking for a bug that is not there.
 *
 * So this asks it properly: build the directed graph of every press from every
 * stop, and return the stops with no inbound edge. Those are the ones a player
 * genuinely cannot arrive at, whatever route they take.
 *
 * The starting stop is excluded, because a surface's first stop is where the
 * ring is placed rather than navigated to -- it needs no inbound edge to be
 * reachable, and reporting it would make every screen look broken.
 */
export function unreachableStops(candidates: readonly Candidate[]): string[] {
  if (candidates.length < 2) return [];
  const reached = new Set<string>([candidates[0].id]);
  const dirs: Dir[] = ["up", "down", "left", "right"];
  for (const from of candidates) {
    for (const dir of dirs) {
      const to = pickStop(from.rect, candidates, dir, from.id);
      if (to) reached.add(to);
    }
  }
  return candidates.map((c) => c.id).filter((id) => !reached.has(id));
}
