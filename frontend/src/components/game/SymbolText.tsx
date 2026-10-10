/**
 * Rules text with its mana symbols drawn as symbols.
 *
 * A card's *casting* cost has been coloured pips since cycle 1, but everything
 * else that names mana was raw text: "{T}: Add {G}." on a land, and
 * "Wayfarer's Bauble: {2}, {T}, Sacrifice: ..." in the action bar. Two
 * renderings of the same notation on the same screen, one of which needs
 * decoding -- a cycle-2 playtest finding (item 10).
 *
 * Splits on `{...}` and hands the pieces to `ManaSymbol`, the same component the
 * cost row uses, so a {G} is one thing everywhere. Anything it does not
 * recognise is left as text rather than guessed at.
 */

import { symbolTokens } from "../../logic/cardStyle";
import { ManaSymbol } from "./ManaSymbol";

interface Props {
  text: string;
  /**
   * Optional class on the wrapper.
   *
   * Callers that lay their box out with flex should keep their own element and
   * nest this inside it instead: a pip is an inline element, and as a flex item
   * it stretches to the whole line.
   */
  className?: string;
}

export function SymbolText({ text, className }: Props) {
  const tokens = symbolTokens(text);

  return (
    <span className={className}>
      {tokens.map((token) =>
        token.kind === "text" ? (
          token.value
        ) : (
          <ManaSymbol
            code={token.value}
            className={`pip--inline pip--${token.tone}`}
            // The glyph the disc used to draw -- `↷` for tap, `❄` for snow. Only
            // reached for a symbol with no SVG, which the engine cannot emit
            // today; kept so the fallback stays as readable as it was.
            fallback={token.label}
            key={token.key}
          />
        ),
      )}
    </span>
  );
}
