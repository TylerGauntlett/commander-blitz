/**
 * One seat: a card, and a plate under it.
 *
 * Every slot has the same anatomy whatever is in it -- a header, a card, a
 * plate. That sameness is what makes the row read as a hand rather than as four
 * unrelated widgets, and it is why an empty chair's buttons live *under a card
 * back* rather than in a dashed box of their own.
 *
 * Two placements here were got wrong twice in the mockup round and are worth
 * keeping right. The remove control is a mark beside the seat number, not a
 * corner tag (which widened the slot and painted over its neighbour) and not a
 * plate button (which gave emptying a seat the same voice as the action you came
 * to the plate for). And reading a deck is the card itself plus a glyph in the
 * meta row, not a full-width "Details" button competing with the deck's name.
 */

import { useState } from "react";
import type { PodSeatView, PodView } from "../../api/types";
import { MAX_NAME_LENGTH, cpuNumber, firstEmpty, seatLabel } from "../../logic/lobby";
import { ManaSymbol } from "../game/ManaSymbol";
import { CardBack } from "./CardBack";
import { CommanderCard } from "./CommanderCard";

interface Props {
  pod: PodView;
  seat: PodSeatView;
  /** Host-only controls are hidden rather than disabled for a guest. */
  youAreHost: boolean;
  disabled?: boolean;
  onChooseDeck: (forSeat: number) => void;
  onAddCpu: (index: number) => void;
  onOpenChair: (index: number) => void;
  onClear: (index: number) => void;
  onInvite: () => void;
  onDossier: (deckId: string, forSeat: number | null) => void;
  /** Your own seat only. Renaming any other chair is refused by the server. */
  onRename: (name: string) => void;
}

/**
 * Your name, on your own plate.
 *
 * A local draft rather than a controlled read of `seat.name`: the pod
 * re-renders on every long-poll return, and a field that reset itself mid-word
 * would be unusable. Nobody else can change your name, so there is nothing for
 * the draft to drift from.
 *
 * Committed on blur and on Enter. A PATCH per keystroke would bump the pod's
 * version for every letter and wake three other browsers out of their long
 * polls to be told you are still typing.
 */
function SeatName({
  name,
  disabled,
  onRename,
}: {
  name: string | null;
  disabled: boolean;
  onRename: (name: string) => void;
}) {
  const [draft, setDraft] = useState(name ?? "");

  const commit = () => {
    const trimmed = draft.trim();
    // An emptied field is a slip, not an instruction: the server refuses a
    // blank name, and there would be nothing useful to show in its place.
    if (!trimmed) {
      setDraft(name ?? "");
      return;
    }
    setDraft(trimmed);
    if (trimmed !== name) onRename(trimmed);
  };

  return (
    <input
      className="plate__name"
      data-testid="your-name"
      aria-label="Your name at this table"
      value={draft}
      maxLength={MAX_NAME_LENGTH}
      spellCheck={false}
      placeholder="Your name"
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          event.currentTarget.blur();
        }
      }}
    />
  );
}

export function PodSeat({
  pod,
  seat,
  youAreHost,
  disabled = false,
  onChooseDeck,
  onAddCpu,
  onOpenChair,
  onClear,
  onInvite,
  onDossier,
  onRename,
}: Props) {
  const index = seat.index;
  const you = seat.is_you;
  const label = seatLabel(pod, index);
  const deck = seat.deck;

  /*
    Whose deck you may read: your own, a CPU's, and another player's once they
    have locked in. The server has already made that decision -- an unlocked
    seat arrives with `deck: null` -- so this is not a second gate, it is the
    same fact driving the card's clickability and the `i` glyph.
  */
  const readable = deck !== null;

  if (seat.kind === "empty") {
    /*
      The "Add a CPU" hook is numbered by the pod size it would produce:
      `opponents-1` adds the first opponent, `opponents-2` the second. That is
      what `e2e/helpers.ts:startGame` clicks.

      Only the *first* empty chair carries it. Every empty chair would compute
      the same number -- they are all "the next one" -- and three buttons with
      one id is a strict-mode violation in Playwright and a genuine ambiguity
      for anybody else reading the DOM.
    */
    const opponents = pod.seats.filter((s) => s.kind === "cpu" || s.kind === "human").length;
    const next = firstEmpty(pod) === index;
    return (
      <div className="slot" data-testid={`seat-${index}`} data-kind="empty">
        <div className="slot__head">
          <span className="slot__no">Seat {index + 1}</span>
        </div>
        <div className="slot__card">
          <CardBack mark="Empty seat" tone="empty" />
        </div>
        <div className="plate">
          <div className="plate__who">
            <span className="plate__n">No one yet</span>
          </div>
          <div className="plate__deck">A pod seats four</div>
          {youAreHost && (
            <span className="plate__fill">
              <button
                type="button"
                className="btn btn--wide"
                data-testid={next ? `opponents-${opponents}` : undefined}
                disabled={disabled}
                onClick={() => onAddCpu(index)}
              >
                Add a CPU
              </button>
              <button
                type="button"
                className="btn btn--wide"
                data-testid={next ? `invite-${opponents}` : undefined}
                disabled={disabled}
                onClick={() => onOpenChair(index)}
              >
                Invite a player
              </button>
            </span>
          )}
        </div>
      </div>
    );
  }

  /*
    Face-down covers three different facts with one picture, on purpose: a chair
    nobody has taken, and a deck somebody has chosen but not committed to.
  */
  const face = readable ? (
    <CommanderCard cardId={deck.commanders[0] ?? null} variant="big" />
  ) : seat.kind === "open" ? (
    <CardBack mark="Waiting for a player" tone="open" />
  ) : (
    <CardBack mark="Sealed until they lock in" />
  );

  /*
    Every resolved seat wears the stamp, CPUs included -- a CPU is locked in by
    construction, and it was the one seat whose card said nothing about that.
    Only a face-up card can carry one; an open chair is a card back.
  */
  const stamped = readable && seat.ready;

  const kindWord =
    seat.kind === "cpu" ? "CPU" : seat.kind === "open" ? "open" : you ? "you" : "player";

  return (
    <div
      className="slot"
      data-testid={`seat-${index}`}
      data-kind={seat.kind}
      data-locked={seat.locked ? "yes" : "no"}
    >
      <div className="slot__head">
        <span className={you ? "slot__no slot__no--you" : "slot__no"}>
          Seat {index + 1} · {kindWord}
        </span>
        {/* Never on your own seat: a host who emptied their own chair would have
            no way back into their pod. Never on another human's either -- that
            is theirs, and the server refuses it. */}
        {youAreHost && !you && seat.kind !== "human" && (
          <button
            type="button"
            className="slot__x"
            title="Empty this seat"
            aria-label={`Empty seat ${index + 1}`}
            disabled={disabled}
            onClick={() => onClear(index)}
          >
            ✕
          </button>
        )}
      </div>

      {/* role/tabindex rather than a <button>: a <button> may not contain the
          divs a card face is made of. */}
      <div
        className="slot__card"
        {...(readable
          ? {
              role: "button",
              tabIndex: 0,
              "data-act": "dossier",
              "aria-label": `Read ${deck.name}`,
              onClick: () => onDossier(deck.id, you || seat.kind === "cpu" ? index : null),
              onKeyDown: (event: React.KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onDossier(deck.id, you || seat.kind === "cpu" ? index : null);
                }
              },
            }
          : {})}
      >
        {face}
        {stamped && (
          <span className={you ? "stamp" : "stamp stamp--them"} data-testid={`stamp-${index}`}>
            Locked in
          </span>
        )}
      </div>

      <div className="plate">
        <div className="plate__who">
          {/* The one editable thing on any plate. `seatLabel` still says "You"
              for your own chair, which is right for the ready track's tooltip
              -- but here the question is what the *other* three people see. */}
          {you ? (
            <SeatName name={seat.name} disabled={disabled} onRename={onRename} />
          ) : (
            <span className="plate__n">{label.title}</span>
          )}
          <span className="plate__tag">{label.sub}</span>
        </div>

        {deck ? (
          <>
            <div className="plate__deck" data-testid={`seat-${index}-deck`}>
              {deck.name}
            </div>
            <div className="plate__meta">
              {deck.color_identity.map((colour) => (
                <ManaSymbol key={colour} code={colour} />
              ))}
              {deck.simplified > 0 && (
                <span className="badge badge--partial">{deck.simplified} simplified</span>
              )}
              <button
                type="button"
                className="ibtn"
                title="Deck details"
                aria-label={`Deck details for ${label.title}`}
                onClick={() => onDossier(deck.id, you || seat.kind === "cpu" ? index : null)}
              >
                i
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="plate__deck plate__deck--sealed">
              {seat.kind === "open" ? `Pod ${pod.code}` : "Deck sealed"}
            </div>
            <div className="plate__meta">
              <span className="count">
                {seat.kind === "open" ? "Anyone with the code" : "Readable once they lock in"}
              </span>
            </div>
          </>
        )}

        {/* What is left in the acts row is only ever what you came to the plate
            to do. A seat belonging to another player has no acts row at all,
            which is right -- there is nothing about it for you to change. */}
        {you && (
          <div className="plate__acts">
            <button
              type="button"
              className="btn btn--wide"
              data-testid="change-deck"
              disabled={disabled || seat.locked}
              title={seat.locked ? "Unlock your card to change decks" : undefined}
              onClick={() => onChooseDeck(index)}
            >
              {deck ? "Change deck" : "Choose a deck"}
            </button>
          </div>
        )}
        {!you && seat.kind === "cpu" && youAreHost && (
          <div className="plate__acts">
            <button
              type="button"
              className="btn btn--wide"
              data-testid={`cpu-deck-${cpuNumber(pod, index)}`}
              disabled={disabled}
              onClick={() => onChooseDeck(index)}
            >
              Change deck
            </button>
          </div>
        )}
        {!you && seat.kind === "open" && youAreHost && (
          <div className="plate__acts">
            <button type="button" className="btn" onClick={onInvite} disabled={disabled}>
              Share the code
            </button>
            <button
              type="button"
              className="btn"
              disabled={disabled}
              onClick={() => onAddCpu(index)}
            >
              CPU instead
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
