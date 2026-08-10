/**
 * Tell the preview it is being tested rather than looked at.
 *
 * The two want opposite things from motion: a play function needs the board to
 * hold still, and a person opening Storybook needs to see the hand fan lift.
 * `preview.tsx` reads this flag and applies `reducedMotion` only here.
 *
 * This file must not register the preview's annotations -- the addon has done
 * that itself since Storybook 10.3, and doing it again makes the addon stand
 * down and hand every story a renderer that does not exist. It detects the
 * clash by *searching this file's text* for the name of the registering
 * function, so the name must not appear here even inside a comment. It did, in
 * an earlier draft of this very paragraph, and every story failed with
 * "No render function available".
 */

(window as Window & { __STORY_TEST__?: boolean }).__STORY_TEST__ = true;
