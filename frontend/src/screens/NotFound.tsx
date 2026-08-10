/**
 * An address that is not anything.
 *
 * A screen rather than a silent redirect home. `/pod/GYRE-8412` is one letter
 * away from a real pod link and somebody will type it -- landing them at the
 * front door with no explanation looks like the invite was rejected, and they
 * will ask for another one that works exactly as badly.
 */

import { Link } from "react-router";
import { Screen } from "../components/screen/Screen";

export function NotFound() {
  return (
    <Screen variant="fade" center testId="not-found">
      <p className="menu__note">There is nothing at this address.</p>
      <Link className="btn btn--ghost" to="/">
        Back to the front door
      </Link>
    </Screen>
  );
}
