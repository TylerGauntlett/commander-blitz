/**
 * One chair: a card, and a printed plate under it.
 *
 * Every chair has the same anatomy whatever is in it -- a tag, a card, a plate,
 * and AT MOST ONE BUTTON. That sameness is what makes the row read as a hand
 * rather than as four unrelated widgets, and the one-button rule is what makes
 * it navigable with a thumb.
 *
 * ---------------------------------------------------------------------------
 * ## What was cut, and why cutting was the design
 *
 * The shipped plate carried, per chair: a title, a subtitle, a deck line, a
 * meta row and up to two full-width buttons -- so an empty pod opened with
 * eight buttons and twelve lines of prose on it, none of which a player had
 * asked a question about. Four of those buttons said "Invite a player", which
 * the header also said, and the sentences said things the picture already said:
 * "No one yet" under a card back reading EMPTY, "A pod seats four" under four
 * chairs, "Readable once they lock in" under a card that is visibly face down.
 *
 * A caption that repeats its picture is not redundancy, it is noise with a
 * legibility cost -- and on a 7-inch panel it is the difference between the row
 * of cards filling the screen and the row of cards being a strip above a wall
 * of grey text. So the plate says the two things only it can say -- who is in
 * the chair and what they are playing -- and everything else went.
 *
 * ## The chair is a stop, and so is its button
 *
 * Both are native controls, so `input/stops.ts` picks them up with no
 * registration. The card is a stop only when there is something to read: an
 * unlocked stranger's chair arrives with `deck: null` from the server, so a
 * card nobody may read is a plain div and the ring walks past it rather than
 * onto a dead end.
 *
 * Every control here carries a `data-testid`, and that is a navigation
 * requirement rather than a testing one. `stopIdOf` falls back to
 * accessible-name-plus-INDEX for a control with no id -- so "Add a CPU" in seat
 * 3 was `ui:Add a CPU:9`, and the moment seat 2 became a CPU the whole list
 * re-indexed, every id changed, and the ring fell back to the first control on
 * the screen. Naming them is what makes a chair the same stop before and after
 * the pod changes under it.
 */

import type { PodSeatView, PodView } from "../../api/types";
import { cpuNumber, firstEmpty, seatLabel } from "../../logic/lobby";
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
  onClear: (index: number) => void;
  onDossier: (deckId: string, forSeat: number | null) => void;
}

export function PodSeat({
  pod,
  seat,
  youAreHost,
  disabled = false,
  onChooseDeck,
  onAddCpu,
  onClear,
  onDossier,
}: Props) {
  const index = seat.index;
  const you = seat.is_you;
  const label = seatLabel(pod, index);
  const deck = seat.deck;

  /*
    Whose deck you may read: your own, a CPU's, and another player's once they
    have locked in. The server has already made that decision -- an unlocked
    seat arrives with `deck: null` -- so this is not a second gate, it is the
    same fact driving the card's clickability and the plate's deck line.
  */
  const readable = deck !== null;

  /*
    The "Add a CPU" hook is numbered by the pod size it would produce:
    `opponents-1` adds the first opponent, `opponents-2` the second. That is
    what `e2e/helpers.ts:startGame` clicks.

    Only the *first* empty chair carries it. Every empty chair would compute the
    same number -- they are all "the next one" -- and three buttons with one id
    is a strict-mode violation in Playwright and a genuine ambiguity for
    anybody else reading the DOM.
  */
  const opponents = pod.seats.filter((s) => s.kind === "cpu" || s.kind === "human").length;
  const nextEmpty = firstEmpty(pod) === index;

  /*
    The word after the seat number, and it is the only place a chair says what
    KIND of thing it is. "Seat 2 · CPU" is the whole caption; the plate below it
    then only has to say who and what, which is the split the old plate did not
    make and paid for in five lines of prose.
  */
  const kindWord =
    seat.kind === "empty"
      ? null
      : seat.kind === "cpu"
        ? "CPU"
        : seat.kind === "open"
          ? "open"
          : you
            ? "you"
            : "player";

  /*
    Face-down covers three different facts with one picture, on purpose: a chair
    nobody has taken, a chair held for somebody who has not arrived, and a deck
    chosen but not committed to. The words on the back are one each, because a
    card back is a pattern rather than a caption -- see `CardBack`.
  */
  /*
    `board` rather than `big`, which is the art-forward face rather than the
    reading one.

    `big` is the preview rail's card: a full printed face with the oracle text
    set in it. That is the right object beside a rail whose job is READING a
    card, and the wrong one in a row of four chairs -- at 208px the rules ran
    off the bottom mid-sentence, so every seat in the pod showed a commander
    with its own ability truncated. A chair says WHICH deck, and the art says
    that in one glance; the reading is a press away in the dossier.
  */
  const face = readable ? (
    <CommanderCard cardId={deck.commanders[0] ?? null} variant="board" />
  ) : seat.kind === "empty" ? (
    <CardBack mark="Empty" tone="empty" />
  ) : seat.kind === "open" ? (
    <CardBack mark="Waiting" tone="open" />
  ) : you ? (
    /* Your own chair before you have chosen. "Sealed" is what everybody ELSE's
       unchosen chair says, and saying it on yours told you your own deck was
       being kept from you. */
    <CardBack mark="Choose" tone="open" />
  ) : (
    <CardBack mark="Sealed" />
  );

  /*
    Every resolved seat wears the stamp, CPUs included -- a CPU is locked in by
    construction, and it was the one seat whose card said nothing about that.
    Only a face-up card can carry one; a chair showing a back is not resolved.
  */
  const stamped = readable && seat.ready;

  /*
    ONE BUTTON, AND ONLY THE ONE YOU CAME TO THE CHAIR FOR.

    Your own chair chooses your deck; a CPU's chair (host only) chooses its
    deck; an empty chair seats a CPU; a chair held open swaps to a CPU when
    nobody turns up. Another player's chair has no button at all, which is
    right -- there is nothing about it for you to change. Inviting is one
    control in the header rather than four identical ones down here.
  */
  const act = (() => {
    if (you) {
      return {
        testId: "change-deck",
        label: deck ? "Change deck" : "Choose a deck",
        hint: seat.locked ? "Unlock your card to change decks" : undefined,
        off: disabled || seat.locked,
        run: () => onChooseDeck(index),
      };
    }
    if (!youAreHost) return null;
    if (seat.kind === "cpu") {
      return {
        testId: `cpu-deck-${cpuNumber(pod, index)}`,
        label: "Change deck",
        hint: undefined,
        off: disabled,
        run: () => onChooseDeck(index),
      };
    }
    if (seat.kind === "empty") {
      return {
        testId: nextEmpty ? `opponents-${opponents}` : `seat-${index}-cpu`,
        label: "Add a CPU",
        hint: undefined,
        off: disabled,
        run: () => onAddCpu(index),
      };
    }
    if (seat.kind === "open") {
      return {
        testId: `seat-${index}-cpu`,
        label: "CPU instead",
        hint: undefined,
        off: disabled,
        run: () => onAddCpu(index),
      };
    }
    return null;
  })();

  /* role/tabindex rather than a <button>: a <button> may not contain the divs a
     card face is made of. The key handler supplies Enter and Space in
     exchange, and only a readable card gets any of it. */
  const cardAct = readable
    ? {
        role: "button",
        tabIndex: 0,
        "data-testid": `seat-${index}-card`,
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
    : {};

  return (
    <div
      className="chair"
      data-testid={`seat-${index}`}
      data-kind={seat.kind}
      data-locked={seat.locked ? "yes" : "no"}
    >
      <div className="chair__tag">
        <span className={you ? "chair__no chair__no--you" : "chair__no"}>
          Seat {index + 1}
          {kindWord ? ` · ${kindWord}` : ""}
        </span>
        {/* Never on your own seat: a host who emptied their own chair would have
            no way back into their pod. Never on another human's either -- that
            is theirs, and the server refuses it. */}
        {youAreHost && !you && seat.kind !== "human" && seat.kind !== "empty" && (
          <button
            type="button"
            className="chair__x"
            data-testid={`seat-${index}-clear`}
            data-hint="Empty this chair"
            aria-label={`Empty seat ${index + 1}`}
            disabled={disabled}
            onClick={() => onClear(index)}
          >
            ✕
          </button>
        )}
      </div>

      <div className="chair__card" {...cardAct}>
        {face}
        {stamped && (
          <span className={you ? "stamp" : "stamp stamp--them"} data-testid={`stamp-${index}`}>
            Locked in
          </span>
        )}
      </div>

      <div className="plank chair__plate">
        <div className="chair__who">
          {/*
            A LABEL ON EVERY PLATE, INCLUDING YOUR OWN.

            Your chair used to carry a text field here. Typing a name with a
            controller is a virtual keyboard, a d-pad and about twenty presses
            to replace "Player 1" with something nobody at the table needs --
            and it was the last text box on the screen the focus ring could walk
            into, which made it the last place a pad could get stuck. The server
            names each chair after its seat, so the row still reads as four
            distinct people; what is gone is the invitation to spend a minute on
            it before a game.

            An empty chair has no name to be missing, and the row keeps its
            height from `--who-h` so the four plates still line up.
          */}
          <span className="chair__name">{seat.kind === "empty" ? "" : label.title}</span>
        </div>

        <div className="chair__deck">
          {/* An em dash where a deck name will go, but only for a chair that
              can hold one: a chair with nobody in it has no deck to be missing,
              and four dashes down an empty pod read as four broken lines. */}
          {deck ? (
            <>
              <span className="chair__deckname" data-testid={`seat-${index}-deck`}>
                {deck.name}
              </span>
              <span className="chair__pips">
                {deck.color_identity.map((colour) => (
                  <ManaSymbol key={colour} code={colour} />
                ))}
              </span>
            </>
          ) : seat.kind === "empty" ? null : (
            <span className="chair__deckname chair__deckname--none">—</span>
          )}
        </div>

        <div className="chair__act">
          {act && (
            <button
              type="button"
              className="key chair__key"
              data-testid={act.testId}
              data-hint={act.hint}
              disabled={act.off}
              onClick={act.run}
            >
              {act.label}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
