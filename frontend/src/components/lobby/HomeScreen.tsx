/**
 * The front door: create a pod, or join one with a code.
 *
 * Two actions and nothing else. Every configuration decision this screen used to
 * carry -- which deck, how many opponents, which AI -- now lives in the pod,
 * because those are things you decide *with* the people you are playing against
 * and there is no reason to decide them before they arrive.
 *
 * The fan of four card backs is the pod before anybody has chosen anything,
 * which is what the whole flow is about.
 */

import { motion } from "motion/react";
import { useState } from "react";
import { looksLikeCode, normaliseCode } from "../../logic/lobby";
import { bouncy, ease } from "../../motion/springs";
import { CardBack } from "./CardBack";

/**
 * The longest code the server can issue: `BRAMBLE-123456` -- a seven-letter
 * word, a hyphen, and the six-digit collision fallback.
 *
 * A shorter cap silently truncates what somebody pasted, and the Join button
 * then sits disabled next to a code that looks perfectly right on screen. It
 * only bites on the long words, which is why it is a constant with a reason
 * rather than a number somebody eyeballed.
 */
const MAX_CODE_LENGTH = 14;

interface Props {
  /** Prefilled from `?join=CODE` when somebody followed an invite link. */
  initialCode?: string;
  deckCount: number;
  onCreate: (name: string) => void;
  onJoin: (code: string, name: string) => void;
  busy: boolean;
  error: Error | null;
  onBrowse: () => void;
}

export function HomeScreen({
  initialCode = "",
  deckCount,
  onCreate,
  onJoin,
  busy,
  error,
  onBrowse,
}: Props) {
  // Initialised, not synced: `initialCode` comes from `?join=` and is read once
  // at boot. A `useEffect` that pushed it into state later would arrive after
  // the field had already mounted empty -- and would fight anybody typing.
  const [code, setCode] = useState(() => normaliseCode(initialCode));
  // Kept in the door rather than asked for later: the first thing everybody
  // else in the pod sees is this name, and asking for it after they can already
  // see your chair is the wrong order.
  const [name, setName] = useState("");

  const join = () => {
    if (looksLikeCode(code)) onJoin(normaliseCode(code), name.trim() || "Player");
  };

  return (
    <div className="door" data-testid="home">
      <header className="door__top">
        <span className="brand">
          <span className="brand__mark">Auto MTG</span>
          <span className="brand__sub">Commander, against the engine or each other</span>
        </span>
      </header>

      <main className="door__mid">
        <div className="hero">
          <motion.div
            className="fan"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={ease}
          >
            {[0, 1, 2, 3].map((i) => (
              <CardBack key={i} mark="Auto MTG" />
            ))}
          </motion.div>

          <h1 className="hero__mark">Auto MTG</h1>
          <p className="hero__line">
            Four seats, four cards, all face-down. Turn yours over, fill the rest with the
            engine or with friends, and deal when every card is up.
          </p>

          <label className="who">
            <span className="who__l">You are</span>
            <input
              className="who__in"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Your name"
              maxLength={24}
              spellCheck={false}
              data-testid="player-name"
              aria-label="Your name"
            />
          </label>

          <div className="hero__acts">
            <motion.button
              type="button"
              className="big"
              data-testid="create-pod"
              disabled={busy}
              onClick={() => onCreate(name.trim() || "You")}
              whileHover={{ y: -3, scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              transition={bouncy}
            >
              {busy ? "Dealing the table…" : "Create a pod"}
            </motion.button>

            <span className="or">or</span>

            <span className="join">
              <input
                className="join__in"
                type="text"
                value={code}
                onChange={(event) => setCode(normaliseCode(event.target.value))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") join();
                }}
                placeholder="Pod code"
                spellCheck={false}
                maxLength={MAX_CODE_LENGTH}
                aria-label="Pod code"
                data-testid="pod-code"
              />
              <button
                type="button"
                className="join__go"
                data-testid="join-pod"
                disabled={busy || !looksLikeCode(code)}
                onClick={join}
              >
                Join
              </button>
            </span>
          </div>

          {error && (
            <p className="menu__error" data-testid="home-error">
              {error.message.replace(/^\d+:\s*/, "")}
            </p>
          )}
        </div>
      </main>

      <footer className="door__bot">
        <div className="door__cap">
          <b className="tabular">{deckCount}</b> deck{deckCount === 1 ? "" : "s"} in the
          catalogue
          <span>·</span>
          <button type="button" className="link" onClick={onBrowse}>
            Browse them
          </button>
          <span>·</span>
          <span>or import your own from Moxfield</span>
        </div>
      </footer>
    </div>
  );
}
