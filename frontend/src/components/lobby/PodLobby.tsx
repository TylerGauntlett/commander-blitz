/**
 * The pod: four chairs in a lit room, and a rail under them.
 *
 * THE SCREEN AFTER THE FRONT DOOR HAS TO BE THE SAME GAME AS THE FRONT DOOR.
 *
 * The door was rebuilt from the door round's 01 'The Hand' and came out
 * looking like a first-party menu -- a hall, a floor sigil, three printed cards
 * lifting under a moving light. Pressing PLAY then landed on this screen, which
 * was a grey bar, a grey strip and eight identical grey buttons. Nobody
 * experiences that as "one screen has had its visual pass and one has not";
 * they experience it as the game being over one second after it started, and
 * every judgement they make about the rest of it is made from there.
 *
 * So the pod stands in the same room -- `Room` owns the hall, the light and the
 * stage scale -- and its furniture is built from the same kit: `.plank` for
 * anything printed, `.key` for anything pressable, one gold control per screen.
 * See `styles/room.css`.
 *
 * ---------------------------------------------------------------------------
 * ## The rail's order is the design
 *
 * Locking in is on the left and is the loudest control you own; the ready pips
 * and the "why not" line are in the middle, saying what the pod is waiting for;
 * dealing is on the right and belongs to the host. **Unlocking is deliberately
 * quieter than locking** -- committing should feel heavier than reconsidering,
 * because three other people are waiting on it.
 *
 * ## Where the seed and the name field went
 *
 * There was a seed field here, host-only, and it is gone. A reproducible game
 * is a debugging tool, not a thing a player wants a text box for on the way
 * into a match -- and it was the second of the two fields on this screen that
 * the ring could walk into and never walk out of. Every deal is random now.
 * `e2e/helpers.ts` sets `window.__COMMANDERBLITZ_SEED` instead, which is the same seam
 * `__COMMANDERBLITZ_ZOOM_LOCK` already uses: a test can pin the shuffle without a
 * control existing in a real player's build to do it with.
 *
 * The seat-name field went the same way and for a sharper version of the same
 * reason. Typing a name with a controller is a virtual keyboard, a d-pad and
 * about twenty presses to replace "Player 1" -- the server already names every
 * chair after its seat, so the row reads as four distinct people either way,
 * and what the field bought was the chance to spend a minute on it on the way
 * into a match. It was also the last text box on this screen, which makes the
 * pod the first screen in the app with nothing on it a ring can get stuck in.
 * `PATCH /pods/{code}/seat` still takes a name; nothing in the client sends one.
 */

import { useLayoutEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { DeckImportResponse, DeckSummary, PodView } from "../../api/types";
import { setCursor } from "../../input/cursor";
import { canStart, whyNot, yourSeat } from "../../logic/lobby";
import { useAppConfig } from "../../state/useAppConfig";
import { Glyph } from "../ui/Glyph";
import { DeckCatalog } from "./DeckCatalog";
import { DeckDossier } from "./DeckDossier";
import { InviteDialog } from "./InviteDialog";
import { PodSeat } from "./PodSeat";
import { ReadyTrack } from "./ReadyTrack";
import { POD_HUE, Room } from "./Room";

interface Props {
  pod: PodView;
  decks: DeckSummary[];
  busy: boolean;
  starting: boolean;
  error: Error | null;
  onUpdateSeat: (body: { deck_id?: string; locked?: boolean; name?: string }) => void;
  onAdminSeat: (index: number, action: "add_cpu" | "open_chair" | "clear" | "set_deck") => void;
  onSetSeatDeck: (index: number, deckId: string) => void;
  onStart: () => void;
  onLeave: () => void;
  onDecksChanged: () => void;
  /** Star an import in the catalogue; see `DeckCatalog`'s `onStar`. */
  onStarDeck: (deckId: string, starred: boolean) => void;
}

export function PodLobby({
  pod,
  decks,
  busy,
  starting,
  error,
  onUpdateSeat,
  onAdminSeat,
  onSetSeatDeck,
  onStart,
  onLeave,
  onDecksChanged,
  onStarDeck,
}: Props) {
  /** Which seat the catalogue is choosing for, or null when it is closed. */
  const [catalogFor, setCatalogFor] = useState<number | null>(null);
  const [dossier, setDossier] = useState<{ deckId: string; forSeat: number | null } | null>(
    null,
  );
  const [invite, setInvite] = useState(false);
  const [copied, setCopied] = useState(false);
  const config = useAppConfig();

  const you = yourSeat(pod);
  const locked = you?.locked ?? false;
  const canDeal = canStart(pod) && !starting;
  const host = pod.you_are_host;
  /** Chairs with somebody in them, which is what "an opponent was added" means. */
  const seated = pod.seats.filter(
    (seat) => seat.kind === "cpu" || seat.kind === "human",
  ).length;

  /*
   * THE RING OPENS ON THE THING THIS SCREEN IS FOR.
   *
   * `resolveCursor` falls back to the first stop of whatever surface is on top,
   * which here is the copy button in the bar -- so a player arriving with a pad
   * started on a clipboard convenience and had to walk past their own name to
   * reach the only decision the screen asks them for. The door makes exactly
   * this argument about opening on Play rather than on Decks: a menu whose
   * default selection is not its default action has picked the wrong default.
   *
   * Once, on mount. A guest watching a pod has no chair and therefore no
   * button, and `setCursor` declines a stop that is not there rather than
   * blanking the ring, so no guard is needed for them.
   */
  useLayoutEffect(() => {
    setCursor("ui:change-deck");
  }, []);

  /*
   * ...AND MOVES TO DEAL THE MOMENT DEALING BECOMES POSSIBLE.
   *
   * The pod's whole job is a wait: you lock in, and then three other people do
   * something you cannot influence. The moment the last of them stamps, the one
   * thing left to do changes -- and a host still standing on `Unlock` has to
   * notice that and walk there. Moving the ring is the screen answering the
   * question it just started asking.
   *
   * ON THE TRANSITION, NOT ON THE STATE. This runs after every commit and the
   * pod commits about once a second while anybody is choosing; re-asserting the
   * cursor on each of those would pin the ring to Deal and make the rest of the
   * screen unreachable for as long as the host hesitated. `was` is what makes
   * it a one-time nudge somebody can immediately walk away from.
   */
  const wasDealable = useRef(false);
  useLayoutEffect(() => {
    if (canDeal && !wasDealable.current) setCursor("ui:start-game");
    wasDealable.current = canDeal;
  }, [canDeal]);

  /*
   * ...AND SEATING A CPU COMES BACK TO YOUR OWN CHAIR, IF YOU HAVE NO DECK YET.
   *
   * `resolveCursor` keeps the ring nearest to where the markup changed, so
   * filling a chair left it on THAT chair's deck button -- which is right in
   * general and wrong here, because the chair you just filled is the one thing
   * on the screen now finished with, and choosing your own deck is the decision
   * the pod is actually waiting on you for.
   *
   * ON THE TRANSITION, not on the state, for the reason above: the pod commits
   * about once a second while anybody is choosing, and re-asserting a cursor on
   * each of those would pin the ring and make the rest of the screen
   * unreachable. `wasSeated` is what makes it a one-time nudge somebody can walk
   * straight back out of.
   *
   * GUARDED ON NOT HAVING A DECK, which is what stops it firing on the way back
   * -- seat a second CPU after choosing and the ring stays where you put it.
   *
   * `setCursor` declines a stop that is not on screen rather than blanking the
   * ring, so a guest with no chair needs no guard of its own.
   */
  const wasSeated = useRef(seated);
  useLayoutEffect(() => {
    if (seated > wasSeated.current && !you?.deck) setCursor("ui:change-deck");
    wasSeated.current = seated;
  }, [seated, you?.deck]);

  /*
   * TAKING A DECK MOVES NOTHING, AND THAT IS DELIBERATE.
   *
   * It jumped to `Lock in` for one round, on the reasoning that the button that
   * opened the catalogue is finished with the moment a deck is on the chair.
   * That is true and it is not the whole board: the pod OPENS on `Choose a
   * deck`, so picking one first is the natural order, and at that point there
   * are no opponents seated. The jump landed the player on a button that ends
   * the screen while the chairs behind them were still empty -- so the path
   * became deck, walk back up to seat a CPU, walk back down to lock in. It
   * added the walk it was meant to remove.
   *
   * `Lock in` is not the next step; it is the LAST one, and only the player
   * knows when the pod is the shape they want. The ring stays on the return
   * address -- `Change deck`, one row above the chairs -- and `Deal` still
   * comes to them the moment the pod is dealable, which is the one nudge here
   * that cannot be premature.
   */

  const take = (deckId: string, forSeat: number | null) => {
    if (forSeat === null) return;
    if (forSeat === you?.index) onUpdateSeat({ deck_id: deckId });
    else onSetSeatDeck(forSeat, deckId);
  };

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(pod.code);
    } catch {
      // Refused outside a secure context, which over plain HTTP on a LAN is
      // exactly where this runs. The code is on screen either way.
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <Room hue={POD_HUE} className="pod" testId="new-game" floorY="34%" washY="62%">
      {/*
        `data-pod-code` rather than a heading: the code is on the chip below,
        and specs that need to know which pod this is should not have to read
        the same string out of a sentence.
      */}
      <div className="pod__id" data-pod-code={pod.code} aria-hidden="true" />

      <header className="pod__bar">
        {/*
          The code, and nothing else about the product.

          The brand lockup that stood here -- a bolt, COMMANDER BLITZ, and the
          words "Pod lobby" -- told a player who had already launched the game
          what the game was called, above the only string on the screen they
          actually need to read out loud to somebody else. `Mark.tsx`'s own rule
          is once per app at its largest brand moment, and that moment is the
          door.
        */}
        <span className="pod__code">
          <b className="pod__codev tabular" data-testid="pod-code-chip">
            {pod.code}
          </b>
          <button
            type="button"
            className="key key--mark pod__copy"
            data-testid="pod-copy"
            data-hint={copied ? "Copied" : "Copy the code"}
            aria-label={copied ? "Code copied" : "Copy the pod code"}
            onClick={copyCode}
          >
            {/* Drawn rather than typed. `⧉` renders as a tofu box in the
                fallback stack on a Deck, and "Copy" beside a code that is
                already the loudest thing in the bar is a word doing a mark's
                job. */}
            {copied ? (
              <span aria-hidden="true">✓</span>
            ) : (
              <svg
                viewBox="0 0 20 20"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                aria-hidden="true"
                focusable="false"
              >
                <rect x="7" y="3" width="10" height="12" rx="2" />
                <path d="M13 17H5a2 2 0 0 1-2-2V7" />
              </svg>
            )}
          </button>
        </span>

        <span className="pod__gap" />

        {/* Not on the desktop: the sidecar is bound to 127.0.0.1, so there is
            nobody an invite could reach. Pods with friends go through the
            door's Online card to the hosted site, which has this button. */}
        {config.mode !== "desktop" && (
          <button
            type="button"
            className="key"
            data-testid="invite"
            onClick={() => setInvite(true)}
          >
            Invite
          </button>
        )}
        <button
          type="button"
          className="key key--quiet"
          data-testid="leave-pod"
          onClick={onLeave}
        >
          Leave
        </button>
      </header>

      {/*
        THE ROW OF CHAIRS, AND NOTHING ABOVE IT.

        There was a caption here -- "The pod", and beside it "A card turns face
        up when its seat picks a deck, and stamps when the seat locks in". It
        described a rule the screen demonstrates the moment anybody touches it,
        it was the widest line of text in the app, and on a 7-inch panel it cost
        the row of cards 42 vertical pixels it needed more.
      */}
      <div className="pod__row">
        {pod.seats.map((seat) => (
          <PodSeat
            key={seat.index}
            pod={pod}
            seat={seat}
            youAreHost={host}
            disabled={busy || starting}
            onChooseDeck={setCatalogFor}
            onAddCpu={(index) => onAdminSeat(index, "add_cpu")}
            onClear={(index) => onAdminSeat(index, "clear")}
            onDossier={(deckId, forSeat) => setDossier({ deckId, forSeat })}
          />
        ))}
      </div>

      <div className="pod__rail">
        <button
          type="button"
          className={locked ? "key pod__lock pod__lock--on" : "key pod__lock"}
          data-testid="lock-in"
          disabled={busy || starting || !you?.deck}
          data-hint={you?.deck ? undefined : "Choose a deck first"}
          onClick={() => onUpdateSeat({ locked: !locked })}
        >
          {locked ? "Unlock" : "Lock in"}
        </button>

        <span className="pod__state">
          <ReadyTrack pod={pod} />
          <p className="pod__why" data-testid="why-not">
            {error ? error.message.replace(/^\d+:\s*/, "") : whyNot(pod)}
          </p>
        </span>

        {host ? (
          <button
            type="button"
            className="key key--commit pod__deal"
            data-testid="start-game"
            disabled={!canDeal}
            onClick={onStart}
          >
            {starting ? "Shuffling…" : "Deal"}
          </button>
        ) : (
          <span className="pod__guest" data-testid="waiting-on-host">
            The host deals
          </span>
        )}
      </div>

      <div className="room__hints" aria-hidden="true">
        <span className="hint">
          <Glyph btn="a" />
          <span className="hint__verb">Select</span>
        </span>
        <span className="hint">
          <Glyph btn="dpad" />
          <span className="hint__verb">Move</span>
        </span>
      </div>

      {catalogFor !== null && (
        <DeckCatalog
          decks={decks}
          forSeat={catalogFor}
          forWhom={
            catalogFor === you?.index
              ? "your chair"
              : (pod.seats[catalogFor]?.name ?? `seat ${catalogFor + 1}`)
          }
          chosen={pod.seats[catalogFor]?.deck?.id ?? null}
          onPick={(deckId) => {
            take(deckId, catalogFor);
            setCatalogFor(null);
          }}
          onDossier={(deckId) => setDossier({ deckId, forSeat: catalogFor })}
          onClose={() => setCatalogFor(null)}
          onImported={(result: DeckImportResponse) => {
            onDecksChanged();
            // Somebody who pasted a link wants to play that deck; making them
            // find it in the rack afterwards is a step with no decision in it.
            take(result.deck.id, catalogFor);
          }}
          onDelete={async (deckId) => {
            await api.deleteDeck(deckId);
            onDecksChanged();
          }}
          onStar={onStarDeck}
          inUse={pod.seats.flatMap((seat) => (seat.deck ? [seat.deck.id] : []))}
        />
      )}

      {dossier && (
        <DeckDossier
          deckId={dossier.deckId}
          canTake={
            dossier.forSeat !== null &&
            !(dossier.forSeat === you?.index && locked) &&
            (dossier.forSeat === you?.index || host)
          }
          onTake={(deckId) => {
            take(deckId, dossier.forSeat);
            setDossier(null);
            setCatalogFor(null);
          }}
          onClose={() => setDossier(null)}
        />
      )}

      {invite && (
        <InviteDialog
          pod={pod}
          onClose={() => setInvite(false)}
          onOpenChair={() => {
            const free = pod.seats.find((seat) => seat.index > 0 && seat.kind === "empty");
            if (free) onAdminSeat(free.index, "open_chair");
          }}
        />
      )}
    </Room>
  );
}
