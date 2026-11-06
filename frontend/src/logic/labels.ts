/** Human-readable strings for steps, decisions, cards and events. */

import type { GameEvent, GameView } from "../api/types";

/**
 * The engine's 13 steps, in order.
 *
 * Careful: the server sends `step` UPPERCASE ("DECLARE_ATTACKERS") and `phase`
 * lowercase ("precombat_main") in the same payload. This module is the only
 * place that should have to know that.
 */
export const STEP_ORDER = [
  "UNTAP",
  "UPKEEP",
  "DRAW",
  "PRECOMBAT_MAIN",
  "BEGIN_COMBAT",
  "DECLARE_ATTACKERS",
  "DECLARE_BLOCKERS",
  "FIRST_STRIKE_DAMAGE",
  "COMBAT_DAMAGE",
  "END_OF_COMBAT",
  "POSTCOMBAT_MAIN",
  "END_STEP",
  "CLEANUP",
] as const;

/**
 * The thirteen steps, grouped into the five phases players actually name.
 *
 * Thirteen equal ticks is thirteen things to read, and twelve of them are
 * never the answer to "where are we". Grouping lets the live phase expand into
 * its steps while the rest collapse to a word -- so the track says "Combat,
 * declaring blockers" instead of making you count pills.
 *
 * Every step keeps a label in the DOM regardless of which phase is open;
 * `e2e/smoke.spec.ts` asserts all thirteen are still there, because a step that
 * renders as a blank gap is the bug this display replaced.
 */
export const PHASES = [
  { name: "Beginning", steps: ["UNTAP", "UPKEEP", "DRAW"] },
  { name: "Main 1", steps: ["PRECOMBAT_MAIN"] },
  {
    name: "Combat",
    steps: [
      "BEGIN_COMBAT",
      "DECLARE_ATTACKERS",
      "DECLARE_BLOCKERS",
      "FIRST_STRIKE_DAMAGE",
      "COMBAT_DAMAGE",
      "END_OF_COMBAT",
    ],
  },
  { name: "Main 2", steps: ["POSTCOMBAT_MAIN"] },
  { name: "End", steps: ["END_STEP", "CLEANUP"] },
] as const;

const STEP_NAMES: Record<string, string> = {
  UNTAP: "Untap",
  UPKEEP: "Upkeep",
  DRAW: "Draw",
  PRECOMBAT_MAIN: "Main 1",
  BEGIN_COMBAT: "Begin combat",
  DECLARE_ATTACKERS: "Declare attackers",
  DECLARE_BLOCKERS: "Declare blockers",
  FIRST_STRIKE_DAMAGE: "First strike",
  COMBAT_DAMAGE: "Combat damage",
  END_OF_COMBAT: "End of combat",
  POSTCOMBAT_MAIN: "Main 2",
  END_STEP: "End step",
  CLEANUP: "Cleanup",
};

/** Compact labels for the phase track, where horizontal space is scarce. */
const STEP_SHORT: Record<string, string> = {
  UNTAP: "Untap",
  UPKEEP: "Upkeep",
  DRAW: "Draw",
  PRECOMBAT_MAIN: "Main 1",
  BEGIN_COMBAT: "Combat",
  DECLARE_ATTACKERS: "Attack",
  DECLARE_BLOCKERS: "Block",
  FIRST_STRIKE_DAMAGE: "1st Strike",
  COMBAT_DAMAGE: "Damage",
  END_OF_COMBAT: "End Cbt",
  POSTCOMBAT_MAIN: "Main 2",
  END_STEP: "End",
  CLEANUP: "Cleanup",
};

const PHASE_NAMES: Record<string, string> = {
  beginning: "Beginning",
  precombat_main: "Main Phase",
  combat: "Combat",
  postcombat_main: "Second Main",
  ending: "End Phase",
};

const DECISION_PROMPTS: Record<string, string> = {
  priority: "You have priority",
  declare_attackers: "Declare attackers",
  declare_blockers: "Declare blockers",
  mulligan: "Keep this hand?",
  discard_to_hand_size: "Discard down to seven",
  choose_objects: "Choose",
  choose_mode: "Choose a mode",
  choose_x: "Choose X",
  may: "Optional effect",
  choose_player: "Choose a player",
  commander_zone_change: "Commander zone change",
};

const LOSS_REASONS: Record<string, string> = {
  life: "life total hit zero",
  empty_library: "drew from an empty library",
  commander_damage: "21 commander damage",
  poison: "ten poison counters",
  concede: "conceded",
  lost_by_effect: "a card made them lose the game",
};

export function stepLabel(step: string): string {
  return STEP_NAMES[step] ?? step;
}

export function stepShort(step: string): string {
  return STEP_SHORT[step] ?? step;
}

export function phaseLabel(phase: string): string {
  return PHASE_NAMES[phase] ?? phase;
}

export function lossReason(reason: string | null): string {
  if (!reason) return "";
  return LOSS_REASONS[reason] ?? reason.replace(/_/g, " ");
}

/**
 * A display name for a card id.
 *
 * Events carry the snake_case definition id, not the printed name, so
 * "sol_ring" would otherwise reach the play-by-play verbatim. Callers that have
 * seen the card in a zone should pass a real lookup; this is the fallback.
 */
export function prettyCardName(cardId: string): string {
  return cardId
    .split("_")
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function decisionPrompt(state: GameView): string {
  const pending = state.pending;
  if (state.game_over) {
    if (state.winners.includes(state.seat)) return "You win!";
    if (state.winners.length === 0) return "The game is a draw.";
    return "You lose.";
  }
  if (!pending) return "Waiting...";
  if (pending.player !== state.seat) {
    return `Waiting for ${state.players[pending.player].name}...`;
  }
  return pending.prompt || DECISION_PROMPTS[pending.kind] || pending.kind;
}

export function turnLabel(state: GameView): string {
  const active = state.players[state.active_player];
  // The round, matching PhaseTrack: "turn" to a player means a lap of the table.
  return `Turn ${state.round} - ${active.name} - ${stepLabel(state.step)}`;
}

/**
 * What the opponent is currently being asked, for the thinking indicator.
 *
 * A bare pulsing "Opponent thinking" told the player nothing, and a decision
 * that produces no events -- passing priority is the common one -- looked
 * identical to the game having hung. Naming the seat and the step at least
 * says *where* in the turn the wait is happening.
 */
export function thinkingLabel(state: GameView): string {
  const pending = state.pending;
  if (!pending || pending.player === state.seat) return "Thinking";
  const who = state.players[pending.player]?.name ?? `P${pending.player}`;
  const what =
    pending.kind === "declare_attackers"
      ? "declare attackers"
      : pending.kind === "declare_blockers"
        ? "declare blockers"
        : pending.kind === "mulligan"
          ? "mulligan"
          : stepLabel(state.step).toLowerCase();
  return `${who} — ${what}`;
}

/** Resolves a card id such as "sol_ring" to its printed name. */
export type NameLookup = (cardId: string) => string | undefined;

/**
 * How a permanent left the battlefield, in a few words.
 *
 * The engine's `cause` vocabulary is a small controlled set written at every
 * `move_object` call site (`engine/zones.py`); this is the whole of it, and an
 * unknown one falls through to the humanised string rather than to a blank.
 *
 * Each entry supplies its own *preposition*, which is the reason this is a
 * table of two forms rather than one string plus a blanket " by ": a creature
 * is destroyed **by** a spell but sacrificed **to** an outlet, and "Sacrificed
 * by Ashnod's Altar" reads as though the altar did it against your will.
 *
 * `attributed` is used when the engine named a culprit and `plain` when it
 * could not -- a gang block, a legend rule, a toughness reduced to zero. See
 * `sba._creature_deaths` for why declining to name one is deliberate.
 */
const EXIT_PHRASES: Record<string, { plain: string; attributed?: (by: string) => string }> = {
  destroyed: { plain: "Destroyed", attributed: (by) => `Destroyed by ${by}` },
  sacrificed: { plain: "Sacrificed", attributed: (by) => `Sacrificed to ${by}` },
  lethal_damage: { plain: "Lethal damage", attributed: (by) => `Killed by ${by}` },
  zero_toughness: { plain: "Toughness reduced to 0" },
  legend_rule: { plain: "Legend rule" },
  aura_unattached: { plain: "Nothing left to enchant" },
  player_left: { plain: "Its controller left the game" },
  exiled: { plain: "Exiled", attributed: (by) => `Exiled by ${by}` },
  returned: { plain: "Returned to hand", attributed: (by) => `Returned by ${by}` },
  tuck: { plain: "Put into a library", attributed: (by) => `Put into a library by ${by}` },
  cost: { plain: "Paid as a cost", attributed: (by) => `Paid as a cost for ${by}` },
  recursion: { plain: "Moved", attributed: (by) => `Moved by ${by}` },
};

/**
 * The caption under a departing card, and the tail of its log line.
 *
 * `to` is the destination the engine actually used, which is not always the one
 * the cause implies: rule 903.9a redirects a commander to the command zone
 * while leaving `cause` as "destroyed", so a destroyed commander is
 * `to=command, cause=destroyed` and deserves to say so.
 */
export function exitPhrase(cause: string, byName: string | null, to?: string): string {
  const entry = EXIT_PHRASES[cause];
  const base = entry
    ? byName && entry.attributed
      ? entry.attributed(byName)
      : entry.plain
    : humanise(cause) || `Put into the ${to ?? "graveyard"}`;
  // The commander replacement is a *second* thing that happened to the card and
  // reads as a rider, not as a replacement for why it left in the first place.
  return to === "command" && cause !== "commander_replacement"
    ? `${base} — to the command zone`
    : base;
}

/**
 * A power/toughness modifier the way a card prints it.
 *
 * Always signed, including the zero: "+3/+0" is how a pump reads on a card, and
 * "+3/0" is how nothing reads. Negatives already carry their own sign.
 */
function signed(n: number): string {
  return n < 0 ? String(n) : `+${n}`;
}

function humanise(cause: string): string {
  if (!cause) return "";
  const words = cause.replace(/_/g, " ");
  return words[0].toUpperCase() + words.slice(1);
}

/**
 * One line of play-by-play, or null for events not worth showing.
 *
 * THE ONLY PLACE THAT TURNS AN EVENT INTO PROSE. `beatsFor` used to carry its
 * own parallel switch over the same event types for `Beat.text`, which is how
 * triggers came to be missing from both of them at once, and why mana payment
 * narrated "You pays {2}{G}" while the log next to it said "You pay". Both
 * consumers now come through here; `logic/events.ts` owns timing, sound and
 * effects, and nothing else owns words.
 *
 * `viewerSeat` exists only for grammar: the viewer's own seat is "you", and
 * "you" takes a different verb form. Without it the log reads "You draws a
 * card" on every single draw, which is most of the log.
 *
 * `lookup` turns a card id into its printed name; without it the id is
 * prettified, which is close but not the same ("Kodamas Reach").
 */
export function describeEvent(
  event: GameEvent,
  names: string[],
  viewerSeat?: number,
  lookup?: NameLookup,
): string | null {
  const who = event.player === null ? "" : (names[event.player] ?? `P${event.player}`);
  const isViewer = event.player !== null && event.player === viewerSeat;
  /** Pick the verb form that agrees with `who`. */
  const v = (second: string, third: string) => (isViewer ? second : third);
  const raw = typeof event.data.card === "string" ? event.data.card : null;
  const card = raw ? (lookup?.(raw) ?? prettyCardName(raw)) : null;
  const amount = typeof event.data.amount === "number" ? event.data.amount : null;
  /** Possessive that agrees with `who`: "your", not "You's". */
  const whose = isViewer ? "Your" : `${who}'s`;
  switch (event.type) {
    case "turn_began":
      // The round, matching the phase track. `data.turn` is still on the event
      // for anything that needs the rules counter. An extra turn (500.7) does
      // not complete a round, so without the word it reads as the same turn
      // printed twice; `data.extra` is only ever present, and true, on one.
      return `-- ${whose} ${event.data.extra ? "extra turn" : "turn"} ${event.data.round ?? event.data.turn} --`;
    /*
     * An extra turn that did not happen, because its player skipped it (Trouble
     * in Pairs, 614.10). A skipped turn fires no `turn_began`, so this line is
     * the only trace of it: without it the log shows a spell that promised a
     * turn and a table that silently moved on.
     */
    case "turn_skipped":
      return `${who} ${v("skip", "skips")} an extra turn`;
    case "spell_cast":
      return `${who} ${v("cast", "casts")} ${card ?? "a spell"}`;
    case "spell_countered":
      return `${card ?? "A spell"} is countered`;
    // A copy is never *cast*, so no `spell_cast` line covers it -- a storm
    // count of nine would otherwise show as one spell in the log and eight
    // unexplained resolutions.
    case "spell_copied":
      return `${card ?? "A spell"} is copied`;
    case "spell_fizzled":
      return `${card ?? "A spell"} fizzles (no legal targets)`;
    case "land_played":
      return `${who} ${v("play", "plays")} ${card ?? "a land"}`;
    case "enters_battlefield":
      return `${card ?? "A permanent"} enters the battlefield`;
    /*
     * A permanent leaving the battlefield, and why.
     *
     * This replaced `dies`, which it strictly dominates: `move_object` emits
     * the two together, and only this one knows the destination *and* the
     * cause. Keeping both put two lines in the log for one departure, and the
     * `dies` line was the less informative of them -- it could not tell a
     * removal spell from a legend rule, and it said nothing at all about exile.
     *
     * Guarded to the battlefield, which is doing two jobs. Without it every
     * draw, mill, discard, mulligan and resolution earns a second line ("You
     * draw a card" / "Forest moves from library to hand"). And a zone change
     * out of a *library* carries a card id to every seat, so narrating one
     * would put an opponent's tutor target in the log.
     */
    case "zone_change": {
      if (event.data.from !== "battlefield") return null;
      const cause = typeof event.data.cause === "string" ? event.data.cause : "";
      const byId = typeof event.data.by_card === "string" ? event.data.by_card : null;
      const by = byId ? (lookup?.(byId) ?? prettyCardName(byId)) : null;
      const to = typeof event.data.to === "string" ? event.data.to : undefined;
      return `${card ?? "A permanent"} — ${exitPhrase(cause, by, to)}`;
    }
    // Triggers are most of what happens in Commander and used to appear in
    // neither the log nor the effects layer -- this switch and `beatsFor` are
    // independent, and both were missing a case.
    case "ability_triggered":
      return `${card ?? "An ability"} triggers`;
    case "ability_activated":
      return `${who} ${v("activate", "activates")} ${card ?? "an ability"}`;
    // Heroic and ward both fire as the spell goes on the stack, so a ward
    // prompt appears before anything has visibly happened. Without a line
    // saying what was targeted, the payment dialog arrives unexplained.
    case "became_target":
      // The player-target form needs no line: the cast above it already says
      // who was aimed at, and "targets a permanent" would be a lie.
      if (event.data.oid === undefined || event.data.oid === null) return null;
      return `${who} ${v("target", "targets")} ${card ?? "a permanent"}`;
    // Told from the attacker's side. The per-blocker `blocks` events say who
    // blocked; neither says anything to the creature being blocked, and
    // nothing at all is said when a creature goes unblocked.
    case "became_blocked": {
      const n = typeof event.data.blockers === "number" ? event.data.blockers : 1;
      return `${card ?? "An attacker"} is blocked${n > 1 ? ` by ${n} creatures` : ""}`;
    }
    case "attacked_unblocked":
      return `${card ?? "An attacker"} is unblocked`;
    case "token_created":
      return `${who} ${v("create", "creates")} ${card ?? "a token"}`;
    /*
     * Dice (rule 705.1). The faces themselves are the line, not how many were
     * thrown: what a Bobblehead's controller needs to check is *which* results
     * came up, because the Treasures that follow are one per even result and the
     * win condition counts the sixes. A roll moves no card, taps nothing and
     * changes no characteristic, so without this line the Treasures appear from
     * nowhere and their number looks arbitrary.
     */
    /*
     * A coin flip (rule 705). Won or lost is the whole line: what follows --
     * Negative Zone Portal sacrificing itself on a loss -- turns on it, and a
     * flip moves no card, so nothing else in the log would say why.
     */
    case "coin_flipped":
      return `${who} ${v("flip", "flips")} a coin and ${event.data.won ? v("win", "wins") : v("lose", "loses")}`;
    case "dice_rolled": {
      const results = Array.isArray(event.data.results) ? event.data.results : [];
      const sides = typeof event.data.sides === "number" ? event.data.sides : 6;
      const dice = results.length === 1 ? "a die" : `${results.length} dice`;
      return `${who} ${v("roll", "rolls")} ${dice} (d${sides}): ${results.join(", ")}`;
    }
    // The permanent does not change zones, so no zone_change line covers this.
    // Without a line of its own a creature simply appears on the other side of
    // the board with nothing in the log to say why.
    // Same reason as control_changed: no zone change happens, so the card on
    // the board becomes a different card with nothing in the log to say why.
    case "transformed":
      return `${card ?? "A permanent"} transforms`;
    /*
     * The crown changing hands.
     *
     * Nothing moves and no permanent is involved -- the monarch is a designation
     * the table shares -- so no other line in this switch covers it, and the
     * `default` below would have dropped it in silence. That silence would be
     * expensive: the monarch draws an extra card every one of their end steps and
     * the only ordinary way to take it is to connect in combat, so a player who
     * did not notice losing it sees a stream of unexplained draws.
     *
     * Named without the card that granted it on purpose. Most crowns move by the
     * game's own combat-damage rule, which has no source at all, and phrasing it
     * around one would leave the commonest case with a blank in it.
     */
    case "became_monarch":
      return `${who} ${v("become", "becomes")} the monarch`;
    /*
     * A player got an emblem (114.2).
     *
     * The same kind of silence as the crown: nothing moves, no permanent is
     * involved, and the emblem changes the table for the rest of the game --
     * Ob Nixilis's drains its owner on every card anyone draws. Without a line
     * the player sees life vanish on every draw with nothing to say why.
     *
     * Named after the card whose emblem it is (`data.card`), not the emblem
     * object: an ultimate usually kills its planeswalker before it resolves, so
     * the card is the one thing the player just watched.
     */
    case "emblem_created":
      return card
        ? `${who} ${v("get", "gets")} an emblem from ${card}`
        : `${who} ${v("get", "gets")} an emblem`;
    /*
     * A Saga reached a chapter.
     *
     * The `counter_placed` line beside it already says "Oath of Eorl gets 1
     * lore", and that is the bookkeeping rather than the event: what a player
     * needs to read is *which chapter is happening*, since the three do
     * different things and only one of them is about to end the card. A Saga
     * entering gets the same pair: the lore counter it enters with is "put on"
     * it too (122.6), so the engine emits `counter_placed` for it after the
     * enters event, and the chapter line follows.
     *
     * Numbered in Roman, as the card is. A Saga's chapters are printed "I", "II",
     * "III" and a log reading "chapter 2" would not match the card the player is
     * looking at. Beyond IV the numeral table runs out and the arabic number is
     * used, which no printed Saga reaches.
     */
    case "chapter_reached": {
      const n = typeof event.data.chapter === "number" ? event.data.chapter : 0;
      const roman = ["I", "II", "III", "IV"][n - 1] ?? String(n);
      return `${card ?? "A Saga"} — chapter ${roman}`;
    }
    /*
     * A Class gained a level (716.4). Not a counter, so no `counter_placed`
     * line says anything beside it, and it is the moment the next band of the
     * card's abilities switches on -- the one thing the player bought.
     */
    case "became_level": {
      const n = typeof event.data.level === "number" ? event.data.level : 0;
      return `${card ?? "A Class"} becomes level ${n}`;
    }
    case "control_changed":
      return `${who} ${v("gain", "gains")} control of ${card ?? "a permanent"}`;
    case "counter_placed":
      return `${card ?? "A permanent"} gets ${amount ?? 1} ${
        typeof event.data.counter === "string" ? event.data.counter : "counter"
      }`;
    /*
     * A combat trick, which the log used to miss entirely.
     *
     * `pump`, `animate` and `grant_keyword` mutated the board in silence, so
     * "target creature gets +3/+3 until end of turn" produced no line at all
     * and a creature simply survived damage that should have killed it. The
     * engine emits `stats_changed` for all three now.
     */
    case "stats_changed": {
      const power = typeof event.data.power === "number" ? event.data.power : null;
      const toughness = typeof event.data.toughness === "number" ? event.data.toughness : null;
      const keyword = typeof event.data.keyword === "string" ? event.data.keyword : null;
      const subject = card ?? "A permanent";
      if (keyword) return `${subject} gains ${keyword}`;
      if (power === null && toughness === null) return null;
      return `${subject} gets ${signed(power ?? 0)}/${signed(toughness ?? 0)}`;
    }
    case "mill":
      return `${who} ${v("mill", "mills")} ${event.data.count ?? amount ?? 1} cards`;
    case "draw":
      return `${who} ${v("draw", "draws")} a card`;
    case "discard":
      return `${who} ${v("discard", "discards")} ${card ?? "a card"}`;
    case "cycled":
      return `${who} ${v("cycle", "cycles")} ${card ?? "a card"}`;
    /*
     * A permanent connived (701.47). The draw and the discard already have
     * their own lines; this one says they were one connive, and it is the
     * moment "whenever a creature you control connives" triggers off.
     */
    case "connived":
      return `${card ?? "A creature"} connives`;
    /*
     * A library search (701.19) -- a tutor, a fetchland, landcycling.
     *
     * Nothing else in the log says it: the shuffle that ends a search emits
     * nothing, and a search that finds nothing moves no card. That silence is
     * what Archivist of Oghma's controller would be staring at -- life and a
     * card arriving with no line to say why -- so the search gets its own.
     *
     * `owner` is whose library it was. Every search the engine has is of the
     * searcher's own, which is "their library"; another player's is named, so
     * the line cannot claim the wrong library if one ever is.
     */
    case "library_searched": {
      const owner = typeof event.data.owner === "number" ? event.data.owner : event.player;
      if (owner === event.player) {
        return `${who} ${v("search your", "searches their")} library`;
      }
      const theirs = owner === null ? "a" : `${names[owner] ?? `P${owner}`}'s`;
      return `${who} ${v("search", "searches")} ${theirs} library`;
    }
    case "damage_dealt":
      if (amount === null || amount <= 0) return null;
      return event.data.to === "player"
        ? `${who} ${v("take", "takes")} ${amount} damage`
        : `${amount} damage to ${card ?? "a permanent"}`;
    /*
     * Prevention over a *player* -- Selfless Squire, Fog.
     *
     * The one damage event with nothing else to show for it. Prevented damage
     * was never dealt, so there is no `life_lost` line, no `damage_dealt` line
     * and no change on the board: left unnarrated, a fogged alpha strike is a
     * turn in which the log says nothing happened at all.
     *
     * The *permanent* shape (absorb, protection) is deliberately still silent.
     * Its payload carries an `oid` rather than a card id, so there is no name to
     * put in the sentence, and absorb's residue already prints its own
     * `damage_dealt` line with the reduced number -- the reader is not left
     * wondering there. Narrating it as "a permanent" would be a worse line than
     * none.
     */
    case "damage_prevented":
      if (amount === null || amount <= 0 || event.data.to !== "player") return null;
      return `${who} ${v("prevent", "prevents")} ${amount} damage`;
    // Ten poison ends the game at any life total, so a player quietly
    // accruing them with a healthy life total needs saying out loud.
    case "poison_added": {
      const total = typeof event.data.total === "number" ? event.data.total : null;
      const got = `${who} ${v("get", "gets")} ${amount ?? 1} poison`;
      return total === null ? got : `${got} (${total} total)`;
    }
    // Energy is spent later, so the running total is the useful half: a
    // player deciding whether to pay {E}{E}{E}{E}{E}{E}{E}{E} reads it here.
    case "energy_added": {
      const total = typeof event.data.total === "number" ? event.data.total : null;
      const got = `${who} ${v("get", "gets")} ${amount ?? 1} energy`;
      return total === null ? got : `${got} (${total} total)`;
    }
    case "energy_paid": {
      const total = typeof event.data.total === "number" ? event.data.total : null;
      const paid = `${who} ${v("pay", "pays")} ${amount ?? 1} energy`;
      return total === null ? paid : `${paid} (${total} left)`;
    }
    case "life_gained":
      return amount === null ? null : `${who} ${v("gain", "gains")} ${amount} life`;
    case "life_lost":
      return amount === null ? null : `${who} ${v("lose", "loses")} ${amount} life`;
    case "attackers_declared":
      return `${who} ${v("attack", "attacks")}`;
    /*
     * Deliberately silent, and listed rather than left to the fallthrough so
     * the decision is visible where the next person looks for it.
     *
     * `creatures_attacked_player` is fired *beside* `attackers_declared` for the
     * same declaration -- one per defending seat, so that "whenever one or more
     * creatures attack one of your opponents" can be told which seat. The line
     * above already narrates the declaration, and narrating both would read
     * "You attack" followed by "You attack Bob", once per opponent swung at.
     * The arrows on the board say who is being attacked, and say it better.
     */
    case "creatures_attacked_player":
      return null;
    /*
     * Silent for the same reason, one phase later.
     *
     * `creatures_dealt_combat_damage` is fired *beside* the per-creature
     * `combat_damage_to_player` for the very same hits -- once for the batch,
     * so that "whenever one or more creatures you control deal combat damage to
     * one or more players" can be told the whole of it. Every point of that
     * damage is already narrated as a life loss, and a line here would add a
     * summary of the three lines above it.
     */
    case "creatures_dealt_combat_damage":
      return null;
    /*
     * And the per-creature summary, silent for the same reason: fired once per
     * dealing creature per damage step, beside the per-hit events that already
     * narrate every point of that damage, so that "whenever this creature deals
     * combat damage" -- to anything -- can hear it once.
     */
    case "creature_dealt_combat_damage":
      return null;
    case "blockers_declared":
      return "Blockers declared";
    // Payment used to be entirely silent, then was narrated by a second switch
    // with no verb agreement at all -- "You pays {2}{G}".
    case "mana_spent":
      return typeof event.data.mana === "string"
        ? `${who} ${v("pay", "pays")} ${event.data.mana}`
        : null;
    case "mulligan_taken":
      return `${who} ${v("mulligan", "mulligans")}`;
    case "hand_kept":
      return `${who} ${v("keep", "keeps")} ${event.data.cards ?? 7} cards`;
    case "player_lost":
      return `${who} is eliminated (${lossReason(String(event.data.reason))})`;
    case "game_over":
      return `Game over: ${event.data.result}`;
    default:
      return null;
  }
}

export function playerNames(state: GameView): string[] {
  return state.players.map((player) => player.name);
}
