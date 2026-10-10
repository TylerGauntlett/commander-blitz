/**
 * Which ability? A permanent with two or more, asked as a dialog.
 *
 * Pressing a Mind Stone used to select it and leave the choice to the panel,
 * which on a desktop reads fine and on a Steam Deck reads as two rows both
 * saying "Mind Stone: {T}…" -- one of which sacrifices the card. The press that
 * a handheld player makes is the one on the board, so the board has to ask.
 *
 * A MODAL, NOT A POPOVER. `SettingsMenu` is the only anchored popover here and
 * it took four fixes to become pad-usable (its header lists them); a popover
 * pinned to a card inside a zoom-fitted, scrolling lane would need all four
 * again and buy nothing, because the ring does not care where a button is
 * drawn. So this is the same `.prompt-backdrop` / `.prompt` shell every
 * decision dialog uses, trapped the same way (`data-modal-root`), closed the
 * same way (`B`, a backdrop click), and the ring lands on its first item.
 *
 * NO `data-action-id` HERE. The panel's rows carry every activate action
 * exactly once (`ActionPanel`'s header), and this only decides which ability
 * to go and do: `logic/abilities.ts:routeFor` says whether that is a post or a
 * targeting step, and both go through the same `act` / `beginTargeting` the
 * row would. `menu:` stops, for the reason `combo:` stops exist.
 *
 * `data-preview-oid` on every item keeps the reader on the card the question
 * is about, so `Y` reads it in full over the menu.
 *
 * TWO STEPS, AT MOST. A Treasure's one ability is five yields, and the menu
 * asks which colour straight away. A card with that ability *and* another
 * (Commander's Sphere) asks which ability first, then which colour, in the
 * same dialog: the chosen item's route is itself a `menu`, and `step` holds
 * which item that was so the yields are recomputed from the live actions.
 */

import { useEffect, useState } from "react";
import type { GameView, LegalAction } from "../../api/types";
import { setCursor } from "../../input/cursor";
import { stopId } from "../../input/stops";
import { type AbilityChoice, abilityRoute, routeFor } from "../../logic/abilities";
import type { Gesture } from "../../logic/followUp";
import { findCard } from "../../logic/zoneGrouping";
import { useUiStore } from "../../state/uiStore";
import { SymbolText } from "./SymbolText";

interface Props {
  state: GameView;
  actions: LegalAction[];
  act: (actionId: string) => void;
  followUp: (gesture: Gesture) => void;
  disabled: boolean;
}

export function AbilityMenu({ state, actions, act, followUp, disabled }: Props) {
  const oid = useUiStore((s) => s.abilityMenuOid);
  const setAbilityMenu = useUiStore((s) => s.setAbilityMenu);
  const beginTargeting = useUiStore((s) => s.beginTargeting);

  const card = oid === null ? null : findCard(state, oid);
  const route = oid === null ? null : abilityRoute(actions, oid, card?.name ?? null);
  const abilities: AbilityChoice[] | null = route?.kind === "menu" ? route.abilities : null;

  const [step, setStep] = useState<string | null>(null);
  // Every way the menu closes -- a pick, the backdrop, `B` -- clears the oid,
  // so the next question starts at its first step.
  useEffect(() => {
    if (oid === null) setStep(null);
  }, [oid]);
  const chosen = step === null ? undefined : abilities?.find((a) => keyOf(a) === step);
  const nested = chosen ? routeFor(chosen) : null;
  const items = nested?.kind === "menu" ? nested.abilities : abilities;
  const firstKey = items?.[0] ? keyOf(items[0]) : null;

  /*
   * The question can stop being one while it is open: an opponent's response
   * resolves and the card is gone, or the engine moves on and the actions
   * change. A menu over a card that no longer offers two abilities is a menu
   * with nothing true in it, so it goes.
   */
  useEffect(() => {
    if (oid !== null && abilities === null) setAbilityMenu(null);
  }, [oid, abilities, setAbilityMenu]);

  /*
   * The ring lands on the first item. `resolveCursor` would get there on its
   * own when it sees a new modal root, but saying so here makes it true in a
   * component test with no `FocusRing` mounted -- `SettingsMenu` does the
   * same. The return address puts it back on the card afterwards.
   */
  useEffect(() => {
    if (firstKey !== null) setCursor(stopId.menu(`ability:${firstKey}`));
  }, [firstKey]);

  if (oid === null || items === null || card === null) return null;

  const pick = (ability: AbilityChoice) => {
    if (disabled) return;
    const next = routeFor(ability);
    if (next.kind === "menu") {
      setStep(keyOf(ability));
      return;
    }
    setAbilityMenu(null);
    if (next.kind === "act") {
      act(next.id);
      return;
    }
    if (next.kind === "target") {
      beginTargeting(oid, next.ids);
      followUp({ kind: "targeting", actionIds: next.ids });
    }
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: the backdrop is a click-outside; the dialog inside it is the control.
    <div
      className="prompt-backdrop"
      data-modal-root
      data-testid="ability-menu"
      onClick={(event) => {
        if (!(event.target as Element).closest(".prompt")) setAbilityMenu(null);
      }}
    >
      <div
        className="prompt prompt--menu"
        role="dialog"
        aria-modal="true"
        aria-label={card.name}
      >
        <header className="prompt__head">
          <h2 className="prompt__title">{card.name}</h2>
          <p className="prompt__hint">{hintFor(items)}</p>
        </header>
        <div className="menu__items">
          {items.map((ability) => (
            <button
              type="button"
              key={ability.key ?? (ability.index === -1 ? ability.text : ability.index)}
              className="menu__item act act--ability"
              data-stop={stopId.menu(`ability:${keyOf(ability)}`)}
              data-preview-oid={oid}
              data-testid={`ability-${keyOf(ability)}`}
              disabled={disabled}
              onClick={() => pick(ability)}
            >
              <span className="act__name">
                <SymbolText text={ability.text} />
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** What names an item's stop and test id: its key, or else its place on the card. */
function keyOf(ability: AbilityChoice): string {
  return ability.key ?? String(ability.index);
}

/** The question the items answer, from what kind of items they are. */
function hintFor(items: AbilityChoice[]): string {
  if (items.every((a) => a.key?.startsWith("land-"))) return "How does it enter?";
  // Only mana abilities name their yields today (`legality._mana_option_label`).
  if (items.every((a) => a.key?.includes("-yield-"))) return "Which mana?";
  return "Which ability?";
}
