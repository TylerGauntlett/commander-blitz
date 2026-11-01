/**
 * The selection audit: every question the engine can ask, the surface that
 * answers it today, the surface the rule gives it, and the presses it may cost.
 *
 * The client answers one question -- *which of these things do I mean?* -- on
 * six surfaces: the board, the action panel, `PromptDialog`, the `ChoiceCombo`
 * inside it, `AbilityMenu` and the `OpeningHand` screen. Each was the right
 * call for the decision it was built for, and nothing recorded which decision
 * used which, so a new surface could move a question and nothing would fail.
 * This table is that record, and the rule every surface is converging on:
 *
 *   **A choice among things on the table is made on the table, staged, and
 *   committed once. A choice among things that are not on the table is made in
 *   the panel or a dialog. The panel remains the universal fallback under
 *   which every legal action is one control, exactly once (ADR 0015).**
 *
 * `ruleFor` is that rule as a function of what a decision is choosing among,
 * so the "rule" column is derived and cannot drift from the sentence above.
 * Two kinds the enum declares are raised by nothing today and say so with an
 * empty `today`; the Python test holds that claim against the engine too.
 *
 * ## What holds it
 *
 * - `tests/unit/choices/test_decision_audit.py` reads `DecisionKind` and walks
 *   the engine's source for every purpose tag it stamps on a decision: a kind
 *   or a purpose with no row here fails there, and a row naming a purpose the
 *   engine no longer stamps fails too. It parses the rows by their first two
 *   fields, so **`kind` and `purpose` come first in every row, on one line.**
 * - `tests/decisionAudit.test.ts` holds the shape: every journey a row names
 *   has a ceiling, every ceiling is spent by a row, and the derived rule never
 *   leaves the panel out of a table pick.
 * - `Journeys.stories.tsx` and `e2e/journeys-handheld.spec.ts` import their
 *   ceilings from `BUDGET`, so the number a journey is held to lives here once;
 *   `e2e/phone.spec.ts` imports the touch column, `TAP_BUDGET`, the same way.
 *
 * ## The ceilings
 *
 * Each is what the journey measured at the Deck's panel (1280x800) and is
 * asserted as `toBeLessThanOrEqual`, never an exact count: an improvement
 * passes and a regression fails, which is the only direction worth being
 * strict in. A ceiling is lowered when a surface changes and the journey
 * measures less; it is never raised to make a story pass.
 */

/** The eleven values of `engine/enums.DecisionKind`, by their wire name. */
export type DecisionKindName =
  | "priority"
  | "declare_attackers"
  | "declare_blockers"
  | "mulligan"
  | "discard_to_hand_size"
  | "choose_objects"
  | "choose_mode"
  | "choose_x"
  | "may"
  | "choose_player"
  | "commander_zone_change";

/** Where a question is answered. */
export type Surface =
  /** The cards and seats on the table are the stops; a spell on the stack counts. */
  | "board"
  /** The action panel: its rows, the "all" mark, the slab, the X stepper. */
  | "panel"
  /** `PromptDialog`, a modal of options drawn as faces or labels. */
  | "dialog"
  /** `ChoiceCombo`, the filtered list the dialog hands a wall of labels to. */
  | "combo"
  /** `AbilityMenu`, the modal a press on a many-ability permanent opens. */
  | "menu"
  /** `OpeningHand`, the whole screen the first decision owns. */
  | "screen";

/**
 * What a decision is choosing among, which is what the rule turns on.
 *
 * `cards` is a selector-driven pool (`effects/selectors.choose_objects`) that
 * can resolve to any zone: a permanent on the table or a card in a graveyard,
 * depending on the card that asked. The rule then depends on the pool.
 */
export type Subject =
  | "table"
  | "players"
  | "hand"
  | "library"
  | "graveyard"
  | "exile"
  | "cards"
  | "labels"
  | "actions";

/**
 * The rule, as code.
 *
 * On the table (or a player, who is a seat on it): the board, with the panel
 * as the mirror for whatever the layout does not draw -- an opponent's lane at
 * the handheld size -- and as the fallback ADR 0015 requires. Anything that is
 * not on the table: the panel or a dialog, and a wall of labels the combo. A
 * selector pool that could be either gets both answers, by what it resolves to.
 */
export function ruleFor(of: Subject): Surface[] {
  switch (of) {
    case "table":
    case "players":
    case "actions":
      return ["board", "panel"];
    case "cards":
      return ["board", "panel", "dialog"];
    case "labels":
      return ["panel", "dialog", "combo"];
    case "hand":
      // The first decision of the game keeps its screen: it is the hand.
      return ["dialog", "screen"];
    default:
      return ["dialog"];
  }
}

/**
 * The journeys, each counted in presses, and the ceiling each is held to.
 *
 * The key is the story in `Journeys.stories.tsx` (or the e2e test) that
 * measures it, so a reader can find the walk behind a number. A journey that
 * answers a decision one pick at a time is costed per pick.
 */
export const BUDGET = {
  /** `X` passes from wherever the ring is. */
  PassInOnePress: 1,
  /** Cast a spell at a target: the card, then the target. */
  AimASpell: 2,
  /** Jump to the dock, stage the ranked attackers, step to the slab, declare. */
  DeclareAnAttack: 4,
  /** The same declaration as two presses of `X`. */
  CommitFromAnywhere: 2,
  /** The second press on the "all" mark sends everything. */
  SendEverythingAnyway: 3,
  /** Your blocker is picked; the ring is already on the best block. */
  AimABlocker: 1,
  /** Keep the opening hand from where the screen puts the ring. */
  KeepTheHand: 1,
  /** Put one card on the bottom after a mulligan. */
  BottomACard: 1,
  /** One pick in the dialog: the first option, or any option in one step. */
  PickOneInTheDialog: 1,
  /** One pick of a permanent: the ring opens on the first option's card. */
  PickOneOnTheBoard: 1,
  /** One pick among library faces the dialog drew. */
  PickFromTheLibrary: 1,
  /** `X` fills the set from the "all" mark, and `X` again sends it. */
  PickSeveralInThePanel: 2,
  /** A modal spell's first mode. */
  ChooseAMode: 1,
  /** A creature type in a list of hundreds, by paging. */
  ChooseATypeByPaging: 5,
  /** Raise X to 2 on the stepper, step down to the slab, pay. */
  PayX: 5,
  /** Decline a "you may". */
  SayNo: 2,
  /** Point at an opponent. */
  ChooseAPlayer: 1,
} as const;

export type JourneyName = keyof typeof BUDGET;

export interface DecisionRow {
  kind: DecisionKindName;
  /**
   * The `purpose` tag the engine stamps in `context`, or `null` for the kind's
   * own question (and for a `choose_objects` raised with no tag, which the
   * triggered-ability target pick in `engine/stack.py` is).
   */
  purpose: string | null;
  /** The question, in the words a player would use. */
  asks: string;
  of: Subject;
  /**
   * The surfaces that answer it today, in the order a player meets them.
   * Empty for a kind the enum declares and nothing raises.
   */
  today: Surface[];
  /** The journeys whose ceilings this row is held to. */
  journeys: JourneyName[];
}

/** The surface the rule gives a row, derived; never written by hand. */
export const ruleOf = (row: DecisionRow): Surface[] => ruleFor(row.of);

/*
 * The rows. `kind` and `purpose` first, on one line, for the Python test.
 *
 * Every `choose_objects` purpose below is one `ask_objects`, `ask_targets`,
 * `choose_objects` or `pick_from_pool` call in the engine; the test lists the
 * call site for any that goes missing. A pick whose options are permanents
 * is the board's, mirrored in the panel (`logic/pickSeveral.isBoardPick`),
 * whatever its purpose; one whose options are off the table is the dialog's.
 * A selector pool (`cards`) is either, by what it resolves to.
 */
export const DECISION_AUDIT: readonly DecisionRow[] = [
  // ---------------------------------------------------------------- turn
  {
    kind: "priority",
    purpose: null,
    asks: "Act, or pass",
    of: "actions",
    today: ["board", "panel", "menu"],
    journeys: ["PassInOnePress", "AimASpell"],
  },
  {
    kind: "declare_attackers",
    purpose: null,
    asks: "Which creatures attack, and whom",
    of: "table",
    today: ["board", "panel"],
    journeys: ["DeclareAnAttack", "CommitFromAnywhere", "SendEverythingAnyway"],
  },
  {
    kind: "declare_blockers",
    purpose: null,
    asks: "Which creatures block, and what",
    of: "table",
    today: ["board", "panel"],
    journeys: ["AimABlocker"],
  },
  {
    kind: "mulligan",
    purpose: null,
    asks: "Keep this hand?",
    of: "hand",
    today: ["screen"],
    journeys: ["KeepTheHand"],
  },
  {
    kind: "discard_to_hand_size",
    purpose: null,
    asks: "Discard down to hand size",
    of: "hand",
    // Declared by the enum and raised by nothing: cleanup asks through
    // `choose_objects` with the `discard` purpose (`engine/turn.py`). The
    // dialog would draw it if it ever arrived (`PromptDialog.stories`).
    today: [],
    journeys: [],
  },

  // ------------------------------------------------------ choose_objects
  {
    kind: "choose_objects",
    purpose: null,
    asks: "Which targets for this triggered ability",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "choose",
    asks: "Choose (a selector's pool, with no closer name)",
    of: "cards",
    today: ["board", "panel", "dialog"],
    journeys: ["PickOneOnTheBoard", "PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "target",
    asks: "Which targets, chosen as the spell resolves its modes",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickSeveralInThePanel", "PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "proliferate",
    asks: "Which permanents and players get another counter",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickSeveralInThePanel"],
  },
  {
    kind: "choose_objects",
    purpose: "attack",
    asks: "Whom the token enters attacking",
    of: "players",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "attach",
    asks: "What to attach it to",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "banding",
    asks: "Which attackers form a band",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "become_copy",
    asks: "What it becomes a copy of",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "blight_cost",
    asks: "Which creature takes the -1/-1 counters to pay",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "choose_permanents",
    asks: "Which permanents",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "damage_order",
    asks: "In what order the blockers take damage",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "destroy",
    asks: "Which permanent to destroy",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "distribute",
    asks: "Which target takes the next counter",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "divide_damage",
    asks: "Which target takes the next point of damage",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "encode",
    asks: "Which creature to encode on",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "enters_as_copy",
    asks: "What it enters as a copy of",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "haunt",
    asks: "Which creature to haunt",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "pair",
    asks: "Which creature to pair with",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "phase_in",
    asks: "Which permanents phase in",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "phase_out",
    asks: "Which permanents phase out",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "regenerate",
    asks: "Which creature gets the shield",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "remove_counter",
    asks: "Which permanent loses a counter next, or stop",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "remove_counter_cost",
    asks: "Which permanent loses a counter to pay",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "replace",
    asks: "Which of these goes somewhere else instead",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "return_cost",
    asks: "Which permanent returns to hand to pay",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "sacrifice",
    asks: "Which permanent to sacrifice",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "tap_cost",
    asks: "Which permanents tap to pay",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "unattach",
    asks: "Which attachment comes off",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "untap",
    asks: "Which permanents untap under the cap",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "untap_cost",
    asks: "Which permanents untap to pay",
    of: "table",
    today: ["board", "panel"],
    journeys: ["PickOneOnTheBoard"],
  },
  {
    kind: "choose_objects",
    purpose: "mulligan_bottom",
    asks: "Which cards go on the bottom",
    of: "hand",
    today: ["screen"],
    journeys: ["BottomACard"],
  },
  {
    kind: "choose_objects",
    purpose: "aura_swap",
    asks: "Which Aura in hand swaps in",
    of: "hand",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "cast_from_hand",
    asks: "Which card in hand to cast free",
    of: "hand",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "connive",
    asks: "Which card to discard to connive",
    of: "hand",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "discard",
    asks: "Which cards to discard",
    of: "hand",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "reveal",
    asks: "Which cards to reveal",
    of: "hand",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "explore",
    asks: "Keep the revealed card on top, or bin it",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "hideaway",
    asks: "Which of the top cards to exile face down",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "library_order",
    asks: "Which card goes back on top next",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "look_at_top",
    asks: "Which of the top cards to take",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "scry_bottom",
    asks: "Which scried cards go to the bottom",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "search",
    asks: "Which card to find",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "split_piles",
    asks: "Which revealed cards make the first pile",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "surveil",
    asks: "Which surveilled cards go to the graveyard",
    of: "library",
    today: ["dialog"],
    journeys: ["PickFromTheLibrary"],
  },
  {
    kind: "choose_objects",
    purpose: "dredge",
    asks: "Dredge which card instead of drawing",
    of: "graveyard",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "exile_cost",
    asks: "Which cards to exile to pay",
    of: "cards",
    today: ["board", "panel", "dialog"],
    journeys: ["PickOneOnTheBoard", "PickOneInTheDialog"],
  },
  {
    kind: "choose_objects",
    purpose: "play_exiled",
    asks: "Which exiled card to play",
    of: "exile",
    today: ["dialog"],
    journeys: ["PickOneInTheDialog"],
  },

  // --------------------------------------------------------- choose_mode
  {
    kind: "choose_mode",
    purpose: null,
    asks: "Which mode",
    of: "labels",
    today: ["dialog", "combo"],
    journeys: ["ChooseAMode", "ChooseATypeByPaging"],
  },
  {
    kind: "choose_mode",
    purpose: "choose_card_name",
    asks: "Which card name",
    of: "labels",
    today: ["dialog", "combo"],
    journeys: ["ChooseATypeByPaging"],
  },
  {
    kind: "choose_mode",
    purpose: "choose_direction",
    asks: "Left or right",
    of: "labels",
    today: ["dialog"],
    journeys: ["ChooseAMode"],
  },
  {
    kind: "choose_mode",
    purpose: "read_ahead",
    asks: "Which chapter the Saga starts on",
    of: "labels",
    today: ["dialog"],
    journeys: ["ChooseAMode"],
  },

  // ---------------------------------------------------------- the others
  {
    kind: "choose_x",
    purpose: "choose_x",
    asks: "How much is X",
    of: "labels",
    today: ["panel"],
    journeys: ["PayX"],
  },
  {
    kind: "may",
    purpose: null,
    asks: "Yes or no",
    of: "labels",
    today: ["dialog"],
    journeys: ["SayNo"],
  },
  {
    kind: "choose_player",
    purpose: null,
    asks: "Which player",
    of: "players",
    today: ["dialog"],
    journeys: ["ChooseAPlayer"],
  },
  {
    kind: "commander_zone_change",
    purpose: null,
    asks: "Command zone, or where it was going",
    of: "labels",
    // Declared by the enum and raised by nothing: the engine applies the
    // command-zone replacement without asking (`engine/zones.py`). The dialog
    // would draw it if it ever arrived (`PromptDialog.stories`).
    today: [],
    journeys: [],
  },
];

/** The ceiling a journey is held to. */
export function ceiling(journey: JourneyName): number {
  return BUDGET[journey];
}

/**
 * THE TOUCH COLUMN: the same journeys, in taps (ADR 0025).
 *
 * A finger points at what it means, so a journey never costs more taps than
 * it costs presses -- there is no walk -- and `tests/decisionAudit.test.ts`
 * holds that. Each is what `e2e/phone.spec.ts` measured against the real
 * engine on every phone `testing/devices.ts` names, under the same rule as
 * the presses: a ceiling, lowered when a journey gets cheaper and never
 * raised to make a test pass. Only the journeys the phone spec walks have a
 * row; the rest are answered from the same sheet and held by its "every
 * decision answerable from the sheet" assertion instead.
 */
export const TAP_BUDGET = {
  /** The Pass row in the sheet. */
  PassInOnePress: 1,
  /** The Keep button the opening-hand screen draws. */
  KeepTheHand: 1,
  /** The "all" mark, then the slab: the same two steps `X` takes, by finger. */
  CommitFromAnywhere: 2,
} as const satisfies Partial<Record<JourneyName, number>>;

export type TapJourneyName = keyof typeof TAP_BUDGET;

/** The tap ceiling a journey is held to on a phone. */
export function tapCeiling(journey: TapJourneyName): number {
  return TAP_BUDGET[journey];
}
