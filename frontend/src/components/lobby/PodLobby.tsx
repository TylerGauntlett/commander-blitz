/**
 * The pod: a hand of four cards on a table, and a rail underneath.
 *
 * The rail carries three things and their order is the design. Locking in is on
 * the left and is the loudest control you own; the ready track and the "why not"
 * line are in the middle, saying what the pod is waiting for; dealing is on the
 * right and belongs to the host. **Unlocking is deliberately quieter than
 * locking** -- committing should feel heavier than reconsidering, because three
 * other people are waiting on it.
 *
 * The seed field has no counterpart in the mockup and is here anyway: a
 * reproducible game is the fastest way to re-examine something that went wrong,
 * and several e2e specs are built on it. Host-only, because a seed is a property
 * of the game and not of a seat.
 */

import { useState } from "react";
import { api } from "../../api/client";
import type { DeckImportResponse, DeckSummary, PodView } from "../../api/types";
import { canStart, whyNot, yourSeat } from "../../logic/lobby";
import { DeckCatalog } from "./DeckCatalog";
import { DeckDossier } from "./DeckDossier";
import { InviteDialog } from "./InviteDialog";
import { Mark } from "./Mark";
import { PodSeat } from "./PodSeat";
import { ReadyTrack } from "./ReadyTrack";

interface Props {
  pod: PodView;
  decks: DeckSummary[];
  busy: boolean;
  starting: boolean;
  error: Error | null;
  seed: string;
  onSeedChange: (seed: string) => void;
  onUpdateSeat: (body: { deck_id?: string; locked?: boolean; name?: string }) => void;
  onAdminSeat: (index: number, action: "add_cpu" | "open_chair" | "clear" | "set_deck") => void;
  onSetSeatDeck: (index: number, deckId: string) => void;
  onStart: () => void;
  onLeave: () => void;
  onDecksChanged: () => void;
}

export function PodLobby({
  pod,
  decks,
  busy,
  starting,
  error,
  seed,
  onSeedChange,
  onUpdateSeat,
  onAdminSeat,
  onSetSeatDeck,
  onStart,
  onLeave,
  onDecksChanged,
}: Props) {
  /** Which seat the catalogue is choosing for, or null when it is closed. */
  const [catalogFor, setCatalogFor] = useState<number | null>(null);
  const [dossier, setDossier] = useState<{ deckId: string; forSeat: number | null } | null>(
    null,
  );
  const [invite, setInvite] = useState(false);
  const [copied, setCopied] = useState(false);

  const you = yourSeat(pod);
  const locked = you?.locked ?? false;
  const canDeal = canStart(pod) && !starting;
  const host = pod.you_are_host;

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
    <div className="pod" data-testid="new-game" data-pod-code={pod.code}>
      <header className="head">
        <span className="brand">
          <Mark className="brand__badge" />
          <span className="brand__mark">Commander Blitz</span>
          <span className="brand__sub">Pod lobby</span>
        </span>
        <span className="head__spacer" />
        <span className="codechip">
          <span className="codechip__l">Pod</span>
          <b className="codechip__v tabular" data-testid="pod-code-chip">
            {pod.code}
          </b>
          <button type="button" className="btn" onClick={copyCode}>
            {copied ? "Copied" : "Copy"}
          </button>
        </span>
        <button
          type="button"
          className="btn"
          data-testid="invite"
          onClick={() => setInvite(true)}
        >
          Invite a player
        </button>
        <button type="button" className="ghost" data-testid="leave-pod" onClick={onLeave}>
          Leave the pod
        </button>
      </header>

      <div className="tablewrap">
        <div className="tablewrap__l">
          The pod
          <span className="tablewrap__h">
            A card turns face up when its seat picks a deck, and stamps when the seat locks in.
          </span>
        </div>
        <div className="podhand">
          <div className="podhand__felt" />
          {pod.seats.map((seat) => (
            <PodSeat
              key={seat.index}
              pod={pod}
              seat={seat}
              youAreHost={host}
              disabled={busy || starting}
              onChooseDeck={setCatalogFor}
              onAddCpu={(index) => onAdminSeat(index, "add_cpu")}
              onOpenChair={(index) => {
                onAdminSeat(index, "open_chair");
                setInvite(true);
              }}
              onClear={(index) => onAdminSeat(index, "clear")}
              onInvite={() => setInvite(true)}
              onDossier={(deckId, forSeat) => setDossier({ deckId, forSeat })}
              onRename={(name) => onUpdateSeat({ name })}
            />
          ))}
        </div>
      </div>

      <div className="podrail">
        <button
          type="button"
          className={locked ? "lock lock--on" : "lock"}
          data-testid="lock-in"
          disabled={busy || starting || !you?.deck}
          title={you?.deck ? undefined : "Choose a deck first"}
          onClick={() => onUpdateSeat({ locked: !locked })}
        >
          {locked ? "Unlock my card" : "Lock in my seat"}
        </button>

        {host && (
          <label className="field field--seed">
            <span className="field__label">Seed</span>
            <input
              className="field__input"
              value={seed}
              onChange={(event) => onSeedChange(event.target.value)}
              placeholder="random"
              inputMode="numeric"
              aria-label="Seed"
            />
          </label>
        )}

        <span className="podrail__spacer" />
        <ReadyTrack pod={pod} />
        <p className="podrail__why" data-testid="why-not">
          {error ? error.message.replace(/^\d+:\s*/, "") : whyNot(pod)}
        </p>

        {host ? (
          <button
            type="button"
            className="deal"
            data-testid="start-game"
            disabled={!canDeal}
            onClick={onStart}
          >
            {starting ? "Shuffling…" : "Deal the pod"}
          </button>
        ) : (
          <span className="podrail__guest" data-testid="waiting-on-host">
            The host deals
          </span>
        )}
      </div>

      {catalogFor !== null && (
        <>
          <div className="veil" onClick={() => setCatalogFor(null)} aria-hidden="true" />
          <DeckCatalog
            decks={decks}
            forSeat={catalogFor}
            forWhom={
              catalogFor === you?.index
                ? "Choosing your deck"
                : `Choosing for ${pod.seats[catalogFor]?.name ?? `seat ${catalogFor + 1}`}`
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
            inUse={pod.seats.flatMap((seat) => (seat.deck ? [seat.deck.id] : []))}
          />
        </>
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
    </div>
  );
}
