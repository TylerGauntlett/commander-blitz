/**
 * The logo: a bolt on a card back.
 *
 * Twin of `public/favicon.svg`, which is what every icon in `public/` is
 * rendered from. The two hold the same geometry and have to be edited together
 * -- inlining it here rather than pointing an `<img>` at the file is what lets
 * the bolt take `currentColor`, so a header that tints its brand gold tints the
 * mark with it and the two can never disagree.
 *
 * `aria-hidden`: the wordmark beside it already says the name, and a screen
 * reader announcing "Commander Blitz logo, Commander Blitz" is the same fact
 * twice.
 *
 * Where it appears is a rule rather than a preference: **once per screen, at
 * that screen's largest brand moment.** The front door has a hero, so it goes
 * there and the header above it stays type-only; the pod lobby has no hero, so
 * it goes in the header. Two bolts on one screen is a logo sheet, not a page.
 */

interface Props {
  /**
   * Sized in `em` by the caller's own font-size, so a 15px header brand and a
   * 66px hero ask for the mark the same way.
   */
  className?: string;
}

export function Mark({ className }: Props) {
  return (
    <svg
      className={className ? `mark ${className}` : "mark"}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="10" fill="var(--void-0)" />
      <rect
        x="5.8"
        y="5.8"
        width="52.4"
        height="52.4"
        rx="5"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.22"
        strokeWidth="1.4"
      />
      <path d="M37.2 11.2 L20.4 34 H29.2 L26.8 52.8 L43.6 29.6 H34.8 Z" fill="currentColor" />
    </svg>
  );
}
