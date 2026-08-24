/**
 * A decision with more options than anybody can read, as a combobox.
 *
 * Herald's Horn asks for a creature type, and the engine answers that question
 * with every subtype in the loaded pool -- around four hundred options. Drawn
 * the way every other decision is drawn, that is four hundred buttons in a
 * flex-wrap scroller: unreadable with a mouse, and genuinely unusable with a
 * controller, because the ring focuses with `preventScroll` and `candidatesIn`
 * drops any stop an ancestor has clipped. Everything past the fold was not
 * merely awkward to reach; it was unreachable.
 *
 * So: a filter field over a single vertical A-Z list, and a Choose button
 * beside it.
 *
 * THREE MECHANISMS CARRY THIS, and each replaces something that would otherwise
 * have been a second input path to keep in step with `useCursorNav`:
 *
 *   1. `onFocus` on a row sets the highlight. `cursor.stamp` focuses the stop
 *      the ring lands on, so walking the ring down the list moves the highlight
 *      and relabels the Choose button, with nothing here listening to the pad.
 *   2. The Choose button sits to the RIGHT of the list, so a right press
 *      reaches it from any row. Under the list it would be four hundred rows
 *      away.
 *   3. The list scrolls under the ring: the active row is scrolled into view on
 *      every move, and `styles/ui.css` leaves a whole neighbour row showing past
 *      the fold, so the row below the one you are on is still on screen and
 *      therefore still a candidate. That is what makes a held down-press walk
 *      the whole list instead of hitting a wall at the eighth row.
 *
 * ONE ACTION ID, NOT FOUR HUNDRED. Rows carry `combo:` stops and no
 * `data-action-id`; the Choose button carries the highlighted row's. The
 * panel's invariant -- every legal action is a button, exactly once in the
 * document -- is about buttons that ACT, and here exactly one of them does.
 */

import { type KeyboardEvent, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { getInputMode } from "../../input/inputMode";
import { actionAttrs, stopId } from "../../input/stops";
import { narrow } from "../../logic/promptFilter";

/** One option, flattened out of the decision by `PromptDialog`. */
export interface Choice {
  /** The action id this option submits. */
  id: string;
  kind: string;
  label: string;
  /** What the filter matches against. See `logic/promptFilter.ts`. */
  text: string;
}

interface Props {
  choices: Choice[];
  /**
   * Actions that are not one of the enumerated options -- `Done`, in practice.
   *
   * They sit under the Choose button rather than in the list, because a
   * decision that takes several picks sends `Done` alongside the options and an
   * alphabetical list is the wrong place to look for "I have finished".
   */
  extras?: Choice[];
  onAct: (actionId: string) => void;
  disabled: boolean;
}

export function ChoiceCombo({ choices, extras = [], onAct, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const shown = useMemo(() => narrow(choices, query), [choices, query]);
  /*
   * The highlight is CLAMPED rather than corrected.
   *
   * Typing shortens the list under the index, and an effect that pulled the
   * index back would run a render late -- one frame with the Choose button
   * bound to a row that is no longer on screen, which is one frame in which
   * Enter submits the wrong type. Deriving it costs nothing and cannot lag.
   */
  const at = Math.min(active, Math.max(shown.length - 1, 0));
  const current = shown[at] ?? null;

  /*
   * Keep the highlight on screen.
   *
   * `block: "nearest"` so a highlight that is already visible does not scroll
   * at all -- the alternative recentres the list under a player who is only
   * stepping through it. Optional-called because jsdom does not implement
   * `scrollIntoView` and every component test in this repo runs there.
   */
  useLayoutEffect(() => {
    const row = listRef.current?.children[at] as HTMLElement | undefined;
    row?.scrollIntoView?.({ block: "nearest" });
  }, [at]);

  const type = (next: string) => {
    setQuery(next);
    setActive(0);
    // A shorter list under an unchanged index leaves the scroller where the old
    // list left it, which is a blank box until something moves the highlight.
    listRef.current?.scrollTo?.({ top: 0 });
  };

  const step = (delta: number) => {
    if (shown.length === 0) return;
    setActive(Math.min(Math.max(at + delta, 0), shown.length - 1));
  };

  /*
   * The keys, and why focus stays in the field.
   *
   * A combobox that moved DOM focus onto the row would end the typing that is
   * the whole point of the field -- and `pad.ts:isTyping` would flip from
   * "somebody is typing" to "somebody is playing" mid-word. So the arrows move
   * `aria-activedescendant` and nothing else, which is the pattern's own answer
   * to exactly this.
   *
   * Escape clears a query before it does anything else. While a field holds
   * focus both `pad.ts` and `Table.tsx` already swallow the key, so nothing
   * downstream unwinds either way; this makes the first press useful instead of
   * inert, and the second press -- on an empty field, which blurs -- hands the
   * key back to the board.
   */
  const keys = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      step(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (current && !disabled) onAct(current.id);
      return;
    }
    if (event.key === "Escape") {
      if (query) {
        event.preventDefault();
        event.stopPropagation();
        type("");
        return;
      }
      event.currentTarget.blur();
    }
  };

  return (
    <div className="combo" data-testid="choice-combo">
      <div className="combo__pick">
        <label className="search search--combo">
          <span className="search__g" aria-hidden="true">
            &#8981;
          </span>
          <input
            className="search__i"
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={current ? `${listId}-${at}` : undefined}
            aria-label={`Filter ${choices.length} choices`}
            value={query}
            onChange={(event) => type(event.target.value)}
            onKeyDown={keys}
            placeholder="Type to narrow"
            spellCheck={false}
            data-testid="combo-filter"
            data-stop={stopId.combo("filter")}
            /*
             * NOT ON A PAD, where nobody asked for a keyboard and where a
             * focused field deadens the arrow keys that stand in for the d-pad
             * (`pad.ts:isTyping`). The ring still resolves onto the field,
             * because it is the dialog's first stop -- which is the right first
             * thing for a four-hundred-option prompt to offer.
             *
             * The rule this suppresses is about stealing focus from somebody
             * who did not ask. Here the dialog IS the whole screen, it opened
             * because the game demanded an answer, and the field is the only
             * way through two hundred options -- landing anywhere else would be
             * the surprise.
             */
            // biome-ignore lint/a11y/noAutofocus: a modal that exists to be answered; see above.
            autoFocus={getInputMode() !== "pad"}
          />
        </label>

        <div
          className="combo__list"
          id={listId}
          role="listbox"
          /*
           * Out of the tab order but able to take focus, which is what the
           * interactive role asks for. It is not a stop: the ring walks the
           * ROWS, and a container that could hold the cursor would be a stop
           * with nothing to press.
           */
          tabIndex={-1}
          aria-label="Choices"
          ref={listRef}
          data-testid="combo-list"
        >
          {shown.map((choice, index) => (
            <button
              type="button"
              key={choice.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === at}
              className={index === at ? "combo__opt combo__opt--on" : "combo__opt"}
              data-on={index === at ? "" : undefined}
              data-stop={stopId.combo(`opt:${choice.id}`)}
              disabled={disabled}
              onFocus={() => setActive(index)}
              onClick={() => setActive(index)}
            >
              {choice.label}
            </button>
          ))}

          {shown.length === 0 && (
            <p className="empty" data-testid="combo-empty">
              Nothing matches that.{" "}
              <button
                type="button"
                className="link"
                data-testid="combo-clear"
                data-stop={stopId.combo("clear")}
                onClick={() => type("")}
              >
                Clear it
              </button>
            </p>
          )}
        </div>
      </div>

      <aside className="combo__rail">
        <span className="combo__n tabular" data-testid="combo-count">
          {shown.length} of {choices.length}
        </span>
        <button
          type="button"
          className="btn btn--primary combo__go"
          data-testid="combo-go"
          /*
           * The action id only exists when a row is highlighted, and one always
           * is -- but an empty query that matched nothing has no row to bind to,
           * and an `data-action-id=""` would put a nameless action in the
           * document for every count and every selector to trip over.
           */
          {...(current ? actionAttrs(current.id) : {})}
          data-action-kind={current?.kind}
          disabled={disabled || current === null}
          onClick={() => current && onAct(current.id)}
        >
          {current ? `Choose ${current.label}` : "Choose"}
        </button>

        {extras.map((extra) => (
          <button
            type="button"
            key={extra.id}
            className="btn btn--ghost"
            {...actionAttrs(extra.id)}
            data-action-kind={extra.kind}
            disabled={disabled}
            onClick={() => onAct(extra.id)}
          >
            {extra.label}
          </button>
        ))}
      </aside>
    </div>
  );
}
