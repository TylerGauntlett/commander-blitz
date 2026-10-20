/**
 * What the targeting hint says about the card under the pointer or the ring.
 *
 * While a spell or ability is choosing a target, only the cards its actions
 * name can be clicked -- and a card that cannot was focusable and silent, so a
 * player pointing at a hexproof creature or a land under "destroy target
 * creature" had to guess why nothing happened. This turns the hovered card into
 * one sentence for the foot's targeting hint.
 *
 * NOTHING HERE DECIDES LEGALITY. Which cards are targets is the action list's
 * `targets`, as it always was. The reasons come from two places, neither of them
 * a rule re-derived in the client:
 *
 * - **The engine**, for the refusals that belong to the *object*: hexproof,
 *   shroud, protection. `LegalAction.untargetable`, from the same
 *   `target_refusal` that `can_be_targeted` answers with.
 * - **The printed text**, for the ones that belong to the *target line*: a land
 *   is not a "target creature". The sentence quotes the card rather than
 *   guessing at a selector, so it can be vague but never wrong about the rules.
 */

import type { CardView, GameView, LegalAction } from "../api/types";
import { findCard } from "./zoneGrouping";

/*
 * Where a printed target phrase ends: punctuation, or the word that starts the
 * rest of the sentence. A phrase cut too late reads oddly; one cut too early
 * still names the noun, which is the part a player needs.
 */
const PHRASE_END =
  /\s+(?:to|and|unless|until|if|then|as|at|into|onto|on|for|where|this|that|it|its|gets?|gains?|has|have|loses?|becomes?|deals?|draws?|discards?|sacrifices?|mills?|reveals?|creates?|puts?|returns?|searches|shuffles?|taps?|untaps?|phases?|fights?|attacks?|blocks?|explores?|can't|cannot|doesn't|is|are)\b/i;

/**
 * The target lines in a card's printed text -- "target creature", "any target",
 * "target nonland permanent with mana value 3 or less" -- in order, without
 * repeats.
 *
 * Reminder text is dropped first: ward's "becomes the target of a spell" is a
 * sentence about being targeted, not a target line.
 */
export function targetPhrases(oracle: string): string[] {
  const text = oracle.replace(/\([^)]*\)/g, "");
  const out: string[] = [];
  for (const match of text.matchAll(/\b(?:any target|target\b[^.;:,]*)/gi)) {
    let phrase = match[0];
    const end = PHRASE_END.exec(phrase.slice("target".length));
    if (end) phrase = phrase.slice(0, "target".length + end.index);
    phrase = phrase.trim().replace(/^Target/, "target");
    if (phrase === "target" || /^target of\b/i.test(phrase)) continue;
    if (!out.includes(phrase)) out.push(phrase);
  }
  return out;
}

/** The card a targeting session is choosing for: the spell or the ability's permanent. */
function sourceOf(state: GameView, targeting: LegalAction[]): CardView | null {
  const oid = targeting[0]?.source_oid;
  return oid == null ? null : findCard(state, oid);
}

export interface TargetHint {
  text: string;
  /** The card cannot be chosen; the foot draws this as a refusal. */
  refused: boolean;
}

/**
 * One sentence about ``oid`` for the targeting hint, or null when nothing is
 * being targeted or nothing is hovered.
 */
export function targetHint(
  state: GameView,
  targeting: LegalAction[],
  targetableOids: ReadonlySet<number>,
  oid: number | null,
): TargetHint | null {
  if (targeting.length === 0 || oid === null) return null;
  const card = findCard(state, oid);
  if (!card) return null;
  if (targetableOids.has(oid)) return { text: `Target ${card.name}`, refused: false };
  const refuse = (why: string): TargetHint => ({
    text: `Can't target ${card.name} — ${why}`,
    refused: true,
  });

  for (const action of targeting) {
    const reason = action.untargetable?.[String(oid)];
    if (reason) return refuse(reason);
  }

  const source = sourceOf(state, targeting);
  const phrases = source ? targetPhrases(source.oracle_text) : [];
  if (source && phrases.length > 0) {
    return refuse(`${source.name} needs ${phrases.join(" or ")}`);
  }
  return refuse(`not a legal target for ${targeting[0].base_label}`);
}
