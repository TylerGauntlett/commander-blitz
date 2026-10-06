/**
 * The play rows: what can be cast, played or activated right now, grouped so a
 * spell with several legal targets is one row with a chip per target.
 *
 * Lifted out of `ActionPanel.tsx` as it was, including the one place that
 * deliberately does NOT use `previewing`: a chip is a hovering child of a
 * hovering row, and its own leave handler falls back to the row's card rather
 * than to nothing.
 */

import type { CardView, LegalAction } from "../../api/types";
import { actionAttrs } from "../../input/stops";
import type { groupPlayActions } from "../../logic/actionMatch";
import { manaPips, statLine } from "../../logic/cardStyle";
import { ManaSymbol } from "./ManaSymbol";
import type { Previewing } from "./previewing";
import { SymbolText } from "./SymbolText";

interface Props {
  playGroups: ReturnType<typeof groupPlayActions>;
  disabled: boolean;
  onAct: (actionId: string) => void;
  hover: (oid: number | null) => void;
  card: (oid: number) => CardView | null;
  handKey: (oid: number | null) => string | null;
  chipLabel: (action: LegalAction) => string;
  targetOid: (action: LegalAction) => number | null;
  previewing: Previewing;
}

export function PlayRows({
  playGroups,
  disabled,
  onAct,
  hover,
  card,
  handKey,
  chipLabel,
  targetOid,
  previewing,
}: Props) {
  return (
    <>
      {playGroups.map(({ key: groupKey, head, actions: aims }) => {
        const source = head.source_oid === null ? null : card(head.source_oid);
        const isCard = head.kind === "cast" || head.kind === "play_land";
        const tone = isCard
          ? " act--playable"
          : head.kind === "activate"
            ? " act--ability"
            : "";
        const key = handKey(head.source_oid);
        const single = aims.length === 1;
        const body = (
          <>
            {key && <span className="act__key">{key}</span>}
            {isCard && source ? (
              <>
                <span className="act__name">{source.name}</span>
                <span className="act__type">{source.type_line}</span>
                {manaPips(source.mana_cost).length > 0 && (
                  <span className="act__cost">
                    {manaPips(source.mana_cost).map((pip) => (
                      <ManaSymbol
                        code={pip.symbol}
                        className={`pip--${pip.tone}`}
                        key={pip.key}
                      />
                    ))}
                  </span>
                )}
                {statLine(source) && (
                  <span className="act__pt tabular">{statLine(source)}</span>
                )}
              </>
            ) : (
              // Activation costs live in these labels ("{2}, {T}, Sacrifice:
              // ..."), and they were the last place mana stayed raw text.
              // Grouped, the row names the ability and the chips name the
              // targets, so the `-> Bear` suffix would be one arbitrary
              // target repeated on every row of the same permanent.
              <span className="act__name">
                <SymbolText text={single ? head.label : head.base_label} />
              </span>
            )}
          </>
        );

        // One way to aim it: the row *is* the action, exactly as before.
        if (single) {
          return (
            <button
              type="button"
              key={groupKey}
              className={`act${tone}`}
              {...actionAttrs(head.id)}
              data-action-kind={head.kind}
              data-source={head.source_oid ?? undefined}
              disabled={disabled}
              onClick={() => onAct(head.id)}
              {...previewing(head.source_oid)}
            >
              {body}
            </button>
          );
        }

        // Several: the row is inert and each target carries its own id,
        // which is what keeps N actions on N controls rather than on one.
        // Same shape as an attacker with several legal defenders above.
        return (
          <div
            key={groupKey}
            className={`act${tone} act--group`}
            data-source={head.source_oid ?? undefined}
            {...previewing(head.source_oid)}
          >
            {body}
            <span className="act__aims">
              {aims.map((aim) => (
                <button
                  type="button"
                  key={aim.id}
                  className="aim"
                  {...actionAttrs(aim.id)}
                  data-action-kind={aim.kind}
                  data-source={aim.source_oid ?? undefined}
                  disabled={disabled}
                  onClick={() => onAct(aim.id)}
                  data-hint={aim.label}
                  // Not `previewing`: this is a hovering child of a
                  // hovering container, the case that comment warns
                  // about. Falling back to the row's own card rather
                  // than to null is what keeps the preview from going
                  // blank on the way from a chip back onto the row.
                  onMouseEnter={() => hover(targetOid(aim) ?? head.source_oid)}
                  onMouseLeave={() => hover(head.source_oid)}
                  onFocus={() => hover(targetOid(aim) ?? head.source_oid)}
                  onBlur={() => hover(head.source_oid)}
                  // The ring's copy of the line above -- see `previewing`.
                  data-preview-oid={targetOid(aim) ?? head.source_oid ?? undefined}
                >
                  <SymbolText text={chipLabel(aim)} />
                </button>
              ))}
            </span>
          </div>
        );
      })}
    </>
  );
}
