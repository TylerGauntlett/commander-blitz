/** The per-event beats for what players do. See `logic/events.ts`. */

import type { EventContext } from "./context";

/**
 * Beats for the events that are somebody doing something: declarations, cards
 * moving between hand, library and graveyard, triggers and activations,
 * targeting, blocks, mana, mulligans and the end of a player or the game.
 *
 * True when the event was one of these, as for `changeBeat`.
 */
export function actionBeat(ctx: EventContext): boolean {
  const { event, who, card, push } = ctx;
  switch (event.type) {
    case "attackers_declared":
      push({
        hold: 520,
        sound: "hit",
        banner: { text: "Attack!", tone: "damage" },
      });
      return true;

    case "blockers_declared":
      push({ hold: 420 });
      return true;

    case "draw":
      push({ hold: 90, sound: "shuffle" });
      return true;

    case "discard":
      push({ hold: 200 });
      return true;

    /*
     * Cycling reads as one action even though it is a discard, a draw and
     * often a trigger. A slightly longer hold than a plain discard, because
     * what usually follows it is a trigger going on the stack and the two
     * running together is what makes "(Do this before you draw)" invisible.
     */
    case "cycled":
      push({ hold: 260 });
      return true;

    case "mill":
      push({ hold: 200 });
      return true;

    /*
     * A connive finishing. Its draw and discard have already had their beats,
     * so this one is short; it is here so a "whenever a creature you control
     * connives" trigger that follows has a line before it.
     */
    case "connived":
      push({ hold: 200 });
      return true;

    /*
     * A library search. Its own beat rather than log-only, because it is the
     * one moment of a tutor or a cracked fetchland that shows nothing on the
     * board -- the card it finds arrives as a separate `zone_change` and a
     * search that finds nothing moves no card at all -- and Archivist of
     * Oghma's trigger goes on the stack right after it. The sound is the
     * shuffle a search nearly always ends in (701.19c), which emits nothing.
     */
    case "library_searched":
      push({ hold: 260, sound: "shuffle" });
      return true;

    /*
     * Triggers get the same spotlight a cast gets.
     *
     * In Commander triggers are most of what happens, and a trigger going on
     * the stack is the moment the player most needs to notice -- it used to
     * be a 300ms pause with nothing on screen at all, since the text this
     * beat carried was never rendered and the ticker had no case for it.
     */
    case "ability_triggered":
      push({
        hold: 460,
        sound: "chime",
        spotlight: {
          cardId: typeof event.data.card === "string" ? event.data.card : "",
          name: card ?? "An ability",
          controller: event.player ?? 0,
          kind: "trigger",
        },
        flash:
          event.source === null
            ? undefined
            : { anchor: { kind: "object", oid: event.source }, tone: "good" },
      });
      return true;

    /*
     * A copy going on the stack. Short, because storm puts several up at
     * once and a full cast-length beat each would stall the turn -- but not
     * silent, since a copy is the difference between one bolt and nine.
     */
    case "spell_copied":
      push({ hold: 120, sound: "chime" });
      return true;

    case "ability_activated":
      push({
        hold: 320,
        flash:
          event.source === null
            ? undefined
            : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
      });
      return true;

    /*
     * Targeting, which is where ward happens.
     *
     * The flash is on the permanent being *targeted*, not on the spell doing
     * it, and the tone is "danger" because from the board's point of view
     * this is a thing being aimed at. It matters more than a normal beat: ward
     * raises a payment prompt off this event, so without a flash the dialog
     * arrives with nothing on screen saying which creature it is about.
     */
    case "became_target": {
      const oid = typeof event.data.oid === "number" ? event.data.oid : null;
      if (oid === null) return true; // the player-target form; the cast beat covers it
      push({
        hold: 300,
        flash: { anchor: { kind: "object", oid }, tone: "danger" },
      });
      return true;
    }

    /*
     * The outcome of the block declaration, per attacker. Short holds: these
     * fire in a batch, one per attacker, immediately after the per-blocker
     * `blocks` beats, and a full-length hold each would stall the step on a
     * wide board. The tones are from the attacking player's point of view --
     * getting through is good, being blocked is not.
     */
    case "became_blocked":
    case "attacked_unblocked": {
      const oid = typeof event.data.oid === "number" ? event.data.oid : null;
      push({
        hold: 160,
        flash:
          oid === null
            ? undefined
            : {
                anchor: { kind: "object", oid },
                tone: event.type === "became_blocked" ? "danger" : "good",
              },
      });
      return true;
    }

    /*
     * Mana payment, which used to be entirely invisible: lands tapped during
     * auto-payment with no indication of what was spent. `tapped` flashes the
     * specific permanent that paid; `mana_spent` names the total.
     */
    case "tapped":
      push({
        hold: 70,
        sound: "tap",
        flash:
          event.source === null
            ? undefined
            : { anchor: { kind: "object", oid: event.source }, tone: "neutral" },
      });
      return true;

    case "mana_spent":
      push({ hold: 120 });
      return true;

    case "mulligan_taken":
      push({ hold: 200 });
      return true;

    case "hand_kept":
      push({ hold: 200 });
      return true;

    case "player_lost":
      push({
        hold: 1100,
        sound: "toll",
        banner: { text: `${who} is eliminated`, tone: "danger" },
        shake: 0.6,
      });
      return true;

    case "game_over":
      push({ hold: 400 });
      return true;

    default:
      return false;
  }
}
