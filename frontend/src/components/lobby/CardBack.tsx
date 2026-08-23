/**
 * One picture for every "you do not get to know this yet".
 *
 * An empty chair, a player who has not chosen, and a player whose list is
 * sealed are all the same fact, and the mockup's central observation is that
 * they should therefore be the same object. Three different plates -- a dashed
 * box, a hatch, an italic caption -- said it three times and said it worse.
 *
 * The rectangle has to match `CardFace` exactly: the seat row only reads as a
 * hand if a face-down card and a face-up one are the same shape, and
 * `.podhand__felt` is positioned off `--card-w` on the assumption that they are.
 */

interface Props {
  /** The words on the back. Three or four, in small caps. */
  mark: string;
  /**
   * `open` -- a chair held for somebody who has not arrived.
   * `empty` -- nobody, and nobody invited.
   * Neither -- a sealed deck: a real card, face-down.
   */
  tone?: "open" | "empty";
  /**
   * Overridden by `CommanderCard`, which draws a back while a card is loading.
   * "There is nothing here yet" and "you are not allowed to see this" look the
   * same on purpose and must not *test* the same.
   */
  testId?: string;
}

export function CardBack({ mark, tone, testId = "card-back" }: Props) {
  const classes = tone ? `back back--${tone}` : "back";
  return (
    <div className={classes} data-testid={testId} data-tone={tone ?? "sealed"}>
      {/*
        The mark on the back of the card, and it is a *pattern* rather than a
        label: the same words repeated across every face-down seat, at the size
        a card back's printing is. Nobody reads it and nothing depends on it.

        `aria-hidden` says so out loud, which is worth doing for two reasons
        beyond the obvious one: a screen reader announcing "Commander Blitz"
        four times before reaching the first real seat is noise, and
        `e2e/handheldAssert.ts` exempts hidden text from the 16px floor -- so
        this is the honest way to be under it, rather than inflating decoration
        to the size of information.
      */}
      <div className="back__mark" aria-hidden="true">
        {mark}
      </div>
    </div>
  );
}
