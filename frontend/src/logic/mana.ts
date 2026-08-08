/**
 * Turning the server's mana payload into something renderable.
 *
 * Two surfaces need this: the pip row on a player orb, and the "why can't I
 * cast this" hint on a dimmed hand card. Both want the same underlying fact —
 * how much mana is available and of what colours — so it lives here once, pure
 * and testable, rather than twice inside components.
 *
 * The one rule this module will not break: it never claims a spell is
 * castable. Affordability comes from the engine's action list, because only the
 * engine runs the payment solver. Everything here is descriptive.
 */

import type { CardView, LegalAction, ManaView, UnplayableReason } from "../api/types";

/** One renderable unit of mana. */
export interface ManaPipView {
  key: string;
  /** The class suffix that colours it: a WUBRG/C symbol, or "any". */
  tone: string;
  /** What it can make. Length > 1 means the player chooses when they tap. */
  symbols: string[];
  /** Already in the pool rather than still in the ground. */
  floating: boolean;
  /** The permanent this pip comes out of; null for mana already in the pool. */
  sourceOid: number | null;
  /** A hovered spell would tap this pip's source. Set by `markSpent`. */
  spent?: boolean;
}

const SYMBOL_ORDER = ["W", "U", "B", "R", "G", "C"];

/**
 * Every mana the player could produce, one pip each.
 *
 * Floating mana comes first — it is already made, and it disappears at end of
 * step, so it is the part worth spending. A source that offers a choice
 * contributes one ambiguous pip per mana rather than one solid pip per colour;
 * the alternative overstates a dual-heavy board by a mana per dual.
 */
export function manaRow(mana: ManaView | undefined): ManaPipView[] {
  if (!mana) return [];
  const pips: ManaPipView[] = [];

  for (const symbol of SYMBOL_ORDER) {
    const count = mana.pool[symbol] ?? 0;
    for (let i = 0; i < count; i += 1) {
      pips.push({
        key: `pool-${symbol}-${i}`,
        tone: symbol,
        symbols: [symbol],
        floating: true,
        sourceOid: null,
      });
    }
  }

  for (const source of mana.sources) {
    // Every option produces the same *amount* (the solver's max_output), so the
    // first one is enough to know how many pips this source is worth. Which
    // colours those pips could be is the union across options.
    const definite = source.options.length === 1 ? source.options[0] : null;
    for (let i = 0; i < source.amount; i += 1) {
      const symbols = definite ? [definite[i] ?? definite[0]] : source.symbols;
      pips.push({
        key: `src-${source.oid}-${i}`,
        tone: symbols.length === 1 ? symbols[0] : "any",
        symbols,
        floating: false,
        sourceOid: source.oid,
      });
    }
  }

  return pips;
}

/**
 * The permanents casting `card` would tap, or an empty set if it cannot be cast.
 *
 * The engine solves payment exactly and now ships the answer on every cast
 * action (`LegalAction.pays`), so this is a lookup, not a calculation. Guessing
 * client-side is precisely the mistake the `options` payload exists to avoid:
 * two "Add {G} or {U}" duals can pay {G}{U} or {G}{G} but not both, and only the
 * solver knows which lands it picked.
 *
 * Several cast actions can name one card when it has a choice of targets; they
 * all cost the same, so the first is enough.
 */
export function sourcesSpentBy(actions: LegalAction[], oid: number): Set<number> {
  const match = actions.find(
    (action) => action.source_oid === oid && action.kind === "cast" && action.pays.length > 0,
  );
  return new Set(match?.pays ?? []);
}

/**
 * Mark the pips a pending cast would consume.
 *
 * Every pip of a tapped source is marked, not one per mana owed: tapping is what
 * costs, and a land that makes two mana is unavailable for the rest of the step
 * whether the spell needed one of them or both. Marking half of it would claim a
 * mana the player cannot actually reach.
 *
 * Sources only. `Payment` does not itemise which floating mana it spent, so a
 * pool pip is never marked — see engine/legality.py.
 */
export function markSpent(pips: ManaPipView[], spent: ReadonlySet<number>): ManaPipView[] {
  if (spent.size === 0) return pips;
  return pips.map((pip) =>
    pip.sourceOid !== null && spent.has(pip.sourceOid) ? { ...pip, spent: true } : pip,
  );
}

/** "{G}{G}{U}", with an ambiguous pip written as "{?}". */
export function formatManaRow(pips: ManaPipView[]): string {
  if (pips.length === 0) return "{0}";
  return pips.map((pip) => (pip.symbols.length === 1 ? `{${pip.symbols[0]}}` : "{?}")).join("");
}

/**
 * A one-line answer to "why is this card dim?".
 *
 * The engine names the gate; this turns it into something a player learning the
 * format can act on. The mana case is the one worth spelling out in full,
 * because "you are two short" and "you have none of that colour" are different
 * problems with different fixes.
 */
export function unplayableHint(
  card: CardView,
  reason: UnplayableReason | undefined,
  mana: ManaView | undefined,
): string | null {
  switch (reason) {
    case undefined:
      return null;
    case "priority":
      return "Not your turn to act";
    case "timing":
      return card.types.includes("Land")
        ? "Lands only in your main phase"
        : "Sorcery speed — your main phase only";
    case "land_drop":
      return "Land drop already used this turn";
    case "mana": {
      const row = manaRow(mana);
      const cost = card.mana_cost || "{0}";
      return `Needs ${cost} — you have ${formatManaRow(row)}`;
    }
    case "targets":
      return "No legal target";
    default:
      return null;
  }
}
