/** The per-event beats for what changes on the table. See `logic/events.ts`. */

import { arrival, type EventContext, num } from "./context";

/**
 * Beats for the events that change the table: turns, the stack, arrivals,
 * life and stats, counters, chapters, levels, the crown and emblems.
 *
 * True when the event was one of these -- whether or not it earned a beat --
 * so `beatsFor` knows not to ask `actionBeat`.
 */
export function changeBeat(ctx: EventContext): boolean {
  const { event, who, card, amount, viewerSeat, push, onSource } = ctx;
  switch (event.type) {
    case "turn_began": {
      const turn = event.data.extra ? "Extra Turn" : "Turn";
      push({
        hold: 620,
        banner: {
          text: event.player === viewerSeat ? `Your ${turn}` : `${who}'s ${turn}`,
          tone: "neutral",
        },
      });
      return true;
    }

    /*
     * A skipped extra turn (Trouble in Pairs). A banner for the reason the
     * monarch gets one: nothing on the board changes, and the only visible
     * consequence -- the turn going to somebody else -- looks like the
     * promised turn was never there. Toned per seat, because losing your own
     * turn is bad news and an opponent losing theirs is good.
     */
    case "turn_skipped": {
      const mine = event.player === viewerSeat;
      push({
        hold: 520,
        banner: {
          text: mine ? "You skip your extra turn" : `${who} skips their extra turn`,
          tone: mine ? "danger" : "good",
        },
      });
      return true;
    }

    case "spell_cast":
      push({
        hold: 520,
        sound: "chime",
        spotlight: {
          cardId: typeof event.data.card === "string" ? event.data.card : "",
          name: card ?? "a spell",
          controller: event.player ?? 0,
        },
      });
      return true;

    case "spell_resolved":
      push({ hold: 180 });
      return true;

    case "spell_countered":
      push({
        hold: 650,
        banner: { text: "Countered", tone: "danger" },
      });
      return true;

    case "spell_fizzled":
      push({
        hold: 650,
        banner: { text: "Fizzled", tone: "danger" },
      });
      return true;

    /*
     * Something arriving on the battlefield.
     *
     * All three used to be a ring flash and nothing else -- a permanent
     * landed by fading a circle over itself, which reads as a highlight
     * rather than as weight. They now land: a puff of dust under the card and
     * a small squash, on top of the flash the tests already assert.
     */
    case "land_played":
      push({
        hold: 260,
        sound: "thump",
        flash: onSource("neutral"),
        fx: arrival(event.source),
      });
      return true;

    case "enters_battlefield":
      push({
        hold: 220,
        sound: "thump",
        flash: onSource("good"),
        fx: arrival(event.source),
      });
      return true;

    case "token_created":
      push({
        hold: 200,
        flash: onSource("good"),
        fx: arrival(event.source),
      });
      return true;

    /*
     * Dice (rule 705.1). Anchored to the permanent that rolled and floating
     * the faces themselves, because the beats that follow are the payoff --
     * a Treasure per even result -- and a player who did not see what came up
     * cannot tell whether the number of them is right.
     *
     * Held longer than a token arrival: the tokens land immediately after, and
     * the two running together is exactly what hides the roll. No beat when
     * the source is gone, which is the same guard every anchored beat carries.
     */
    case "dice_rolled": {
      if (event.source === null) return true;
      const results = Array.isArray(event.data.results) ? event.data.results : [];
      const anchor = { kind: "object", oid: event.source } as const;
      push({
        hold: 420,
        sound: "chime",
        float: { anchor, value: results.join(" "), tone: "good" },
        fx: [{ at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 }],
      });
      return true;
    }

    // Both of these change what a card *is* without moving it, so the frame
    // redraws in place. Held longer than an ETB so the change reads as a play
    // rather than as a rendering glitch.
    case "transformed":
    case "control_changed":
      push({
        hold: 480,
        sound: "chime",
        flash:
          event.source === null
            ? undefined
            : { anchor: { kind: "object", oid: event.source }, tone: "good" },
      });
      return true;

    /*
     * Damage has no case here any more.
     *
     * Every `damage_dealt` -- combat or not -- is collected by `planCombat`
     * into a run and animated as one concurrent burst, so an event that
     * reaches this switch is one that produced no hit at all: zero damage, or
     * a form with no anchor to put a numeral on. Both are correctly silent.
     */

    /*
     * A fog landing. The counterpart of the note just above: `planCombat`
     * collects the hits, and a prevented swing produces no hit for it to
     * collect, so without a beat here the attack simply plays out and nothing
     * moves. That silence is fine for absorb -- the reduced damage still
     * animates -- and is not fine for a shield over a player, which is the
     * whole of the turn.
     *
     * Scoped to the player shape for the reason `describeEvent` scopes its
     * line: the permanent shape has no anchor this can put a numeral on
     * without first resolving an `oid` the payload does not promise.
     */
    case "damage_prevented":
      if (amount === null || amount <= 0 || event.data.to !== "player") return true;
      push({
        hold: 280,
        float: {
          anchor: { kind: "player", pid: event.player ?? 0 },
          value: `${amount} prevented`,
          tone: "good",
        },
      });
      return true;

    /*
     * Energy arriving. A numeral on the player, in the gain tone: it is a
     * resource banked, and the ticker line carries the running total.
     */
    case "energy_added":
      if (amount === null) return true;
      push({
        hold: 240,
        float: {
          anchor: { kind: "player", pid: event.player ?? 0 },
          value: `+${amount} energy`,
          tone: "gain",
        },
      });
      return true;

    case "life_gained":
      if (amount === null) return true;
      push({
        hold: 280,
        float: {
          anchor: { kind: "player", pid: event.player ?? 0 },
          value: `+${amount}`,
          tone: "gain",
        },
      });
      return true;

    case "life_lost":
      if (amount === null) return true;
      push({
        hold: 280,
        float: {
          anchor: { kind: "player", pid: event.player ?? 0 },
          value: `-${amount}`,
          tone: "loss",
        },
      });
      return true;

    /*
     * A combat trick landing.
     *
     * The engine used to change a creature's power in complete silence --
     * `pump` mutated `until_eot` and called `bump_chars()` and that was all --
     * so a creature would survive lethal damage for no reason the board ever
     * gave. It now says so: the numbers swell off the card, and the card
     * itself takes a pulse so the eye is pointed at the right creature before
     * the damage arrives.
     */
    case "stats_changed": {
      if (event.source === null) return true;
      const power = num(event.data.power);
      const toughness = num(event.data.toughness);
      const keyword = typeof event.data.keyword === "string" ? event.data.keyword : null;
      const anchor = { kind: "object", oid: event.source } as const;
      const value = keyword
        ? keyword
        : `${power !== null && power >= 0 ? "+" : ""}${power ?? 0}/${
            toughness !== null && toughness >= 0 ? "+" : ""
          }${toughness ?? 0}`;
      push({
        hold: 200,
        fx: [
          { at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 },
          { at: 0, kind: "emit", preset: "motes", at_point: anchor },
          { at: 0, kind: "float", at_point: anchor, value, tone: "good" },
        ],
      });
      return true;
    }

    case "counter_placed": {
      const kind = typeof event.data.counter === "string" ? event.data.counter : "counter";
      push({
        hold: 220,
        float:
          event.source === null
            ? undefined
            : {
                anchor: { kind: "object", oid: event.source },
                value: `+${amount ?? 1} ${kind}`,
                tone: "good",
              },
      });
      return true;
    }

    /*
     * A Saga reaching a chapter.
     *
     * A board moment rather than a table one -- there is a permanent, and it is
     * the permanent the player wants their eye drawn to -- so it floats off the
     * Saga rather than taking a banner. The `counter_placed` beat fires beside
     * it and floats "+1 lore", which is the bookkeeping; this is the chapter,
     * and the two read as one gesture on the same card.
     *
     * Worth a beat because a Saga's whole clock is invisible otherwise. Nothing
     * on the board changes when a chapter *triggers*: the ability goes on the
     * stack and its consequences arrive later, so without this the tokens simply
     * appear a moment afterwards with nothing having announced them. And the
     * chapter that ends the story is followed by the Saga going to the graveyard
     * for no reason a viewer can see.
     */
    case "chapter_reached": {
      if (event.source === null) return true;
      const n = num(event.data.chapter) ?? 0;
      const roman = ["I", "II", "III", "IV"][n - 1] ?? String(n);
      const anchor = { kind: "object", oid: event.source } as const;
      push({
        hold: 320,
        sound: "chime",
        float: { anchor, value: roman, tone: "good" },
        fx: [{ at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 }],
      });
      return true;
    }

    /*
     * A Class gaining a level.
     *
     * The Saga chapter's shape, and for its reason: a board moment on one
     * permanent, whose consequence -- the abilities printed under the new
     * level -- is otherwise invisible until something they do happens. The
     * level badge on the card changes too, and this is what draws the eye to
     * it.
     */
    case "became_level": {
      if (event.source === null) return true;
      const anchor = { kind: "object", oid: event.source } as const;
      push({
        hold: 320,
        sound: "chime",
        float: { anchor, value: `Level ${num(event.data.level) ?? 0}`, tone: "good" },
        fx: [{ at: 0, kind: "actuate", oid: event.source, move: "pulse", power: 1 }],
      });
      return true;
    }

    /*
     * The crown changing hands, which is a table-level moment and not a board
     * one: no permanent to flash, no number to float, nothing on screen that
     * changed. A banner is the only shape that fits, and it is the same shape
     * the other two table-level moments use -- the turn change and an
     * elimination.
     *
     * Worth a beat at all because the consequence is invisible: the monarch
     * draws at every one of their end steps, and the usual way it moves is a
     * creature connecting, so without this the player who just lost it sees
     * only their opponent quietly drawing more cards. Held about as long as a
     * transform, and toned "good" or "danger" from the viewer's side, since
     * gaining and losing the crown are the same event told two ways.
     */
    case "became_monarch": {
      const mine = event.player === viewerSeat;
      push({
        hold: 520,
        sound: "chime",
        banner: {
          text: mine ? "You are the monarch" : `${who} is the monarch`,
          tone: mine ? "good" : "danger",
        },
      });
      return true;
    }

    /*
     * An emblem (114): another table-level moment, and so the monarch's
     * shape. There is nothing on the board to flash -- the emblem lives in
     * the command zone, which is a pile rather than a drawn card -- and its
     * effect lasts the game while showing nothing until it next triggers.
     *
     * Toned neutral, unlike the crown: an emblem is as often a curse handed to
     * an opponent (Ob Nixilis) as a boon kept by the walker's controller, and
     * the event does not say which.
     */
    case "emblem_created": {
      const mine = event.player === viewerSeat;
      push({
        hold: 520,
        sound: "chime",
        banner: {
          text: mine ? "You get an emblem" : `${who} gets an emblem`,
          tone: "neutral",
        },
      });
      return true;
    }

    default:
      return false;
  }
}
