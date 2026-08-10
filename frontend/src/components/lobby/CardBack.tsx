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
      <div className="back__mark">{mark}</div>
    </div>
  );
}
