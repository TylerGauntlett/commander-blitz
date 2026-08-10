/**
 * The pod code, and a link carrying it.
 *
 * Both get their own copy button and their own confirmation, because they are
 * for two different situations: the code is what you read out to somebody in
 * the room, the link is what you paste to somebody who is not.
 *
 * The link is built from `window.location` rather than sent by the server. The
 * server does not know what host the browser reached it on -- over a LAN that is
 * a machine address it has no way to guess -- so a server-built link would be
 * `localhost` and would work for exactly one person.
 */

import { useCallback, useEffect, useState } from "react";
import type { PodView } from "../../api/types";
import { openSeats } from "../../logic/lobby";

/** How long a "Copied" label stays up before reverting. */
const CONFIRM_MS = 1600;

export function inviteUrl(pod: PodView): string {
  if (typeof window === "undefined") return pod.invite_link;
  return new URL(pod.invite_link, window.location.href).toString();
}

interface Props {
  pod: PodView;
  onClose: () => void;
  onOpenChair: () => void;
}

export function InviteDialog({ pod, onClose, onOpenChair }: Props) {
  const [copied, setCopied] = useState<"code" | "link" | null>(null);
  const open = openSeats(pod);

  useEffect(() => {
    if (copied === null) return;
    const timer = setTimeout(() => setCopied(null), CONFIRM_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = useCallback(async (what: "code" | "link", value: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard access is refused outside a secure context, which over plain
      // HTTP on a LAN is exactly where this runs. The code is on screen in
      // 25px type either way, so this is a convenience, not the mechanism.
    }
    setCopied(what);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const link = inviteUrl(pod);

  return (
    <>
      <div className="veil veil--invite" onClick={onClose} aria-hidden="true" />
      <section
        className="inv"
        role="dialog"
        aria-modal="true"
        aria-label="Invite a player"
        data-testid="invite-dialog"
      >
        <div className="inv__head">
          <span className="inv__t">Invite a player</span>
          <button type="button" className="inv__x" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="inv__body">
          <div>
            <div className="inv__l">Pod code</div>
            <div className="inv__code">
              <b className="inv__codev tabular" data-testid="invite-code">
                {pod.code}
              </b>
              <button type="button" className="btn" onClick={() => copy("code", pod.code)}>
                {copied === "code" ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          <div>
            <div className="inv__l">Or send the link</div>
            <div className="inv__code">
              <span className="inv__linkv" data-testid="invite-link">
                {link}
              </span>
              <button type="button" className="btn" onClick={() => copy("link", link)}>
                {copied === "link" ? "Copied" : "Copy"}
              </button>
            </div>
          </div>

          <p className="inv__note">
            {open > 0
              ? `${open} chair${open > 1 ? "s are" : " is"} open and holding this code. Whoever arrives picks their own deck, and their card stays face-down until they lock in.`
              : "Anybody with the code can take a free chair. Open one to hold it for a particular person."}
          </p>
        </div>

        <div className="inv__foot">
          {open > 0 ? (
            <button type="button" className="btn btn--wide" onClick={onClose}>
              Back to the pod
            </button>
          ) : (
            <button type="button" className="btn btn--wide btn--live" onClick={onOpenChair}>
              Open a chair
            </button>
          )}
        </div>
      </section>
    </>
  );
}
