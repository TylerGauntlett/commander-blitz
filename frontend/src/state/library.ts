/**
 * Which library this browser is.
 *
 * There are no accounts in this app, and adding them to answer "whose deck is
 * this?" would be a login screen in front of a thing you play on your own sofa.
 * So a browser mints one random id, keeps it, and sends it as `X-Library-Id` on
 * every request. The server stamps it onto anything imported, shows a deck only
 * to the library that imported it, and refuses a delete from anybody else.
 *
 * `localStorage`, not `sessionStorage` -- and that is the opposite of the pod
 * token in `usePod`, for a reason. A token is deliberately per-tab so that two
 * tabs are two players at one table. A library is the other thing entirely: it
 * has to survive a reload, or your decks vanish every time you close the page.
 *
 * The honest cost, since it is worth saying out loud: clear site data and the
 * library is gone, and the decks it owned are invisible. They are recoverable by
 * re-importing the same Moxfield URL -- the deck id comes from the Moxfield
 * public id, so a re-import lands on the same deck and re-claims it.
 */

const KEY = "commanderblitz.library";

/**
 * Read once, then remember. `request` calls this on every fetch, and going to
 * `localStorage` each time would be a synchronous disk-backed read per request
 * for a value that cannot change while the page is open.
 */
let cached: string | null | undefined;

export function libraryId(): string | null {
  if (cached !== undefined) return cached;
  cached = mint();
  return cached;
}

function mint(): string | null {
  try {
    const existing = window.localStorage.getItem(KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    window.localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    // Private browsing with storage disabled, or a context with no `crypto`.
    // Null is a supported state rather than a failure: the server treats a
    // request with no library as the shared view, so the app keeps working and
    // only the privacy of an import is lost.
    return null;
  }
}

/** Test seam. Nothing in the app calls this -- a library is minted once. */
export function resetLibraryForTests(): void {
  cached = undefined;
}
