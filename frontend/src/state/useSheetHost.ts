/**
 * The phone sheet's voice, found rather than passed.
 *
 * On a phone the targeting hint and a hand card's "why not" are said in the
 * sheet (ADR 0025): `Table` renders an empty `.sheet__say` at the top of the
 * rail, and the components that own those lines portal their one copy into it.
 * A portal moves the node, so nothing is drawn twice and no `data-testid`
 * appears in two places.
 *
 * Found by class from an anchor, scoped with `closest(".table")`, for the
 * reason `ActionPanel` finds `.foot__tools` the same way: a story renders the
 * component without the table around it, and two boards on one docs page must
 * not portal into each other. `null` means "say it where you are".
 */

import { type RefObject, useEffect, useState } from "react";

export function useSheetHost(
  anchorRef: RefObject<HTMLElement | null>,
  enabled: boolean,
): HTMLElement | null {
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => {
    if (!enabled) {
      setHost(null);
      return;
    }
    // The rail is rendered by the same commit as the foot, so by the time an
    // effect runs the host exists.
    const scope = anchorRef.current?.closest(".table") ?? null;
    setHost(scope?.querySelector<HTMLElement>(".sheet__say") ?? null);
  }, [anchorRef, enabled]);
  return host;
}
