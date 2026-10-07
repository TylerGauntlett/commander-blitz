/**
 * The block groups: one per creature of yours that can block, with a row for
 * each attacker it may legally block and the verdict of that block.
 *
 * Lifted out of `ActionPanel.tsx` as it was. The header of a group previews
 * your creature; each row previews the attacker it would block, so deciding a
 * block means reading both without finding either on the board.
 */

import type { CardView, LegalAction } from "../../api/types";
import { actionAttrs } from "../../input/stops";
import { blockableBy } from "../../logic/actionMatch";
import { type BlockTier, blockTier } from "../../logic/autoBlock";
import { keywordLabel, statLine } from "../../logic/cardStyle";
import type { Previewing } from "./previewing";

/**
 * What a block would actually achieve, in four words.
 *
 * Straight off `blockTier`, which is the ranking "All defend" already sorts by,
 * so the label and the suggestion can never disagree. Naming the outcome is the
 * whole point of the grouped blocker list: the numbers were always on the cards,
 * but working out "my 2/2 into their 2/2 is a trade" for six pairs is arithmetic
 * the player was being asked to do under time pressure.
 */
const TIER_LABEL: Record<BlockTier, string> = {
  1: "kills it, survives",
  2: "survives",
  3: "trades",
  4: "chumps",
};

interface Props {
  blockers: number[];
  actions: LegalAction[];
  stagedBlocks: Record<number, number>;
  disabled: boolean;
  onStage: (actionId: string) => void;
  blockActionFor: (blocker: number, attacker: number) => LegalAction | null;
  card: (oid: number) => CardView | null;
  nameOf: (oid: number) => string;
  ptOf: (oid: number) => string | null;
  previewing: Previewing;
}

export function BlockGroups({
  blockers,
  actions,
  stagedBlocks,
  disabled,
  onStage,
  blockActionFor,
  card,
  nameOf,
  ptOf,
  previewing,
}: Props) {
  /*
   * Who is already standing in front of each attacker.
   *
   * The groups are per BLOCKER, so with three creatures able to block the same
   * attacker you could not tell from any one group that another had already
   * taken it -- and "which of mine should block this" is exactly the question
   * a second blocker is asking. Each row names the others, so a double block is
   * a decision and a wasted one is visible.
   */
  const blockedBy = new Map<number, number[]>();
  for (const [blocker, attacker] of Object.entries(stagedBlocks)) {
    blockedBy.set(attacker, [...(blockedBy.get(attacker) ?? []), Number(blocker)]);
  }

  return (
    <>
      {blockers.map((blocker) => {
        const blockerCard = card(blocker);
        const chosen = stagedBlocks[blocker];
        const targets = blockableBy(actions, blocker);
        return (
          <div className="actgroup" key={blocker} data-blocker={blocker}>
            {/* The header previews *your* creature; each row below it
              previews the attacker that row would block. Deciding a
              block means reading both, and now neither needs finding on
              the board first. */}
            <div className="actgroup__head" {...previewing(blocker)}>
              <span className="actgroup__name">{nameOf(blocker)}</span>
              {blockerCard && blockerCard.keywords.length > 0 && (
                <span className="actgroup__kw">
                  {blockerCard.keywords.map(keywordLabel).join(" · ")}
                </span>
              )}
              {ptOf(blocker) && <span className="actgroup__pt tabular">{ptOf(blocker)}</span>}
            </div>
            {targets.length === 0 ? (
              <p className="actgroup__none">Nothing this can block.</p>
            ) : (
              targets.map((attacker) => {
                const action = blockActionFor(blocker, attacker);
                const attackerCard = card(attacker);
                if (!action || !blockerCard || !attackerCard) return null;
                const tier = blockTier(blockerCard, attackerCard);
                const on = chosen === attacker;
                const others = (blockedBy.get(attacker) ?? []).filter((b) => b !== blocker);
                return (
                  <button
                    type="button"
                    key={action.id}
                    className={`act act--nested act--staged${on ? " act--on" : ""}`}
                    {...actionAttrs(action.id)}
                    data-action-kind={action.kind}
                    data-blocker={blocker}
                    data-attacker={attacker}
                    data-tier={tier}
                    data-staged={on ? "true" : undefined}
                    aria-pressed={on}
                    disabled={disabled}
                    onClick={() => onStage(action.id)}
                    data-hint={
                      on
                        ? `Blocking ${nameOf(attacker)} — click to release`
                        : `Block ${nameOf(attacker)}`
                    }
                    {...previewing(attacker)}
                  >
                    <span className="act__name">{nameOf(attacker)}</span>
                    {/* The attacker's P/T, next to the verdict it produced.
                      Deciding a block means comparing two numbers, and
                      only one of them used to be in the panel. */}
                    <span className="act__pt tabular">{statLine(attackerCard)}</span>
                    <span className={`verdict verdict--${tier}`}>{TIER_LABEL[tier]}</span>
                    {others.length > 0 && (
                      <span className="act__also" data-testid="also-blocked-by">
                        Blocked by {others.map(nameOf).join(", ")}
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        );
      })}
    </>
  );
}
