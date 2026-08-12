# Rules coverage

This is the honest artifact. It says what the engine does, where it takes a shortcut,
and what it refuses to model at all. If you want to know whether this engine can
handle your card, read this page.

The short version: **everything the two shipped decks need is implemented and tested.**
The simplifications below were chosen so that removing them later is additive work,
not a rewrite.

## Implemented

| Area | Detail |
|---|---|
| **Turn structure** | All 13 steps, turn-based actions, correct priority windows, cleanup repeating per rule 514.3a |
| **Priority** | APNAP order, retaining priority after acting, auto-pass when passing is the only option |
| **The stack** | LIFO resolution, responses, countering, fizzling when every target became illegal |
| **Casting** | Timing restrictions (sorcery speed vs instant vs flash), targets chosen at cast time and re-checked on resolution |
| **Mana** | Cost parsing, mana pools emptying per step, automatic payment with a backtracking solver, `X` costs |
| **Combat** | Attacker/blocker declaration, evasion, damage assignment order, simultaneous damage, first and double strike as separate sub-steps |
| **Keywords** | flying, reach, trample, deathtouch, lifelink, vigilance, haste, menace, first strike, double strike, defender, hexproof, shroud, indestructible, flash, the six landwalks (five basic types plus nonbasic), skulk, fear, intimidate, horsemanship, shadow. `partner` is accepted but inert — see below. Every Magic keyword, routed to a mechanism and marked shipped / free / routed / blocked, is censused in [keywords.md](keywords.md) |
| **Triggers** | ETB, dies, leaves-the-battlefield, landfall, land-played, spell-cast, attacks, blocks, combat damage to a player, upkeep, draw step, begin combat, end step, life gain, counters placed, draws, discards (every one of them: a discard effect, the cleanup trim to hand size, and a cycling cost), damage dealt to a permanent (enrage — the event was always fired and nothing subscribed to it; the subscription is scoped to the *victim*, because for this one event the subject and the source are two different creatures), becoming the target of a spell or ability (heroic and ward, fired as it goes on the stack per 603.2d, with the `controller` clause asking whose spell it is rather than whose permanent), becoming blocked or going unblocked (flanking, rampage, bushido, frenzy — a pair told from the attacker's side, both decided when the block declaration closes), and becoming untapped (inspired — the untap step now fires one event per permanent rather than one aggregate with a count). Intervening-if clauses re-checked on resolution. Delayed triggers ("at the beginning of the next end step, …") via the `delay` op |
| **Command zone** | Abilities that work from the command zone (Edgar Markov's eminence), commander tax, commander damage, the zone-change replacement |
| **Static abilities** | Anthems, keyword grants, P/T setting (including `*/*` read off the board), subtype grants, type replacement, "as long as" conditions (a boolean tree over counters, board and zone counts, and whose turn it is — Threshold), "can't block" (unleash — the mirror of `cant_attack`, checked in `can_block` because it is a fact about one creature rather than about the whole declaration, and a static rather than a keyword because it is a permission), and the player-wide ones: extra land drops, no hand limit, playing lands from the graveyard or the top of the library, doubling land triggers, doubling land *mana*, and freezing the lands an opponent taps |
| **State-based actions** | All nine listed in [engine-rules.md](engine-rules.md), plus **ten poison counters** (704.5c) |
| **Poison** | Poisonous: `add_poison` gives a player poison counters, and ten of them lose the game in the same state-based pass as life and commander damage. A counter on the *player*, not a second life total — its own field and its own `LossReason`, because a player eliminated at 40 life did not run out of life and the frontend prints that reason to them. No `remove_poison`: nothing in the pool removes poison, and the op would be vocabulary with no card behind it. **Infect is not this** — it needs damage *replaced* by counters, which the whitelist does not have |
| **Multiplayer** | N players, turn order that skips eliminated players, elimination mid-combat and mid-resolution, per-source commander damage |
| **Mulligans** | London mulligan with the bottoming step |
| **Costs** | Mana, tap, untap, sacrifice, discard, discard *this card*, pay life, remove counters, exile from graveyard, and tapping *other* permanents — "Tap five untapped Vampires you control", a selector with a count, charged at activation and leaving the permanents on the battlefield to untap next turn |
| **Cycling** | "Cycling {2}" — an activated ability offered from your **hand**, whose cost discards the card itself, plus "When you cycle this card…" as its own `cycle` event, fired after the cycling ability is on the stack so the trigger resolves *before* the draw (the printed "Do this before you draw"). Typecycling is still out: it fetches instead of drawing, which is a different ability |
| **Kicker** | The additional cost, offered as a second way to cast the same card, and the `kicked` condition its text reads — readable by the permanent's own enters trigger, not just during resolution |
| **Evoke, dash and blitz** | One mechanism: an alternative mana cost replacing the printed one, offered from hand only, plus the `evoked` condition the card reads back. Nothing in the engine sacrifices an evoked creature — Mulldrifter's own trigger does — so the same field carries **dash** (haste plus a `delay`ed return) and **blitz** (haste plus a delayed sacrifice) with no engine change. `evoke_label` is what the card calls the cost, because an action reading "Cast Goblin Rabblemaster (evoked)" for a dash card is wrong on screen about what the player is buying. Mana value stays what is printed |
| **Convoke and delve** | Paying part of the *generic* cost with something that is not mana — creatures tapped, or cards exiled from your graveyard. One capability, since both say "each of these pays for {1}" and only the currency differs. One cast line per number spent, the way emerge offers one per victim: the count changes the price and is the player's to choose. The saving is netted into the same `extra` the commander tax uses, so it goes through `pay`'s clamp and can never pay a coloured pip — which is convoke's one documented simplification, "or one mana of that creature's colour". The tap is charged *after* the mana (601.2g), which matters here: a creature that tapped for mana must not also be convoked |
| **Emerge and offering** | The alternative cost whose price depends on the creature sacrificed for it — one cast line per creature, reduced by its mana value. `emerge_subtype` narrows the fodder to one creature type, which is all **offering** is; "any time you could cast an instant" is the `flash` keyword. The subtype is read off *derived* characteristics, so a changeling and a creature granted the type are both legal fodder — reading the printed face would refuse them quietly, and those interactions are the reason the cards are played together |
| **Cast triggers** | "When you cast this spell", via `active_zones: ["stack"]` — an ability firing while its own card is the spell |
| **Ascend / the city's blessing** | "If you control ten or more permanents, you get the city's blessing for the rest of the game", as a **state trigger** in the state-based-action pass -- no stack, no response, checked continuously -- plus a `has_city_s_blessing` condition leaf in both condition languages. Player state, so it survives the permanents leaving, survives the Ascend card leaving, and is shared by every card that player controls |
| **Casting from the graveyard** | `graveyard_cost` — an alternative cost offered only from the owner's graveyard, replacing the printed mana cost, with the rest of it paid as an additional cost — plus `graveyard_cast`, where the card goes when it finishes. Three keywords: **flashback** ("Flashback—{1}{U}, Pay 3 life"), **jump-start** (the printed mana again plus a discard) and **escape** (an `exile_from_graveyard` cost, and `graveyard_cast: "graveyard"` so the card comes back and can be cast again). The exile rider applies on resolution and on fizzling alike, and the escape exemption applies to both. `flashback` is still accepted as the spelling that shipped first; giving both names is refused. `cast_from_graveyard` is readable inside `if`, so Increasing Devotion makes ten tokens rather than five |
| **Embalm** | An activated ability offered from the **graveyard**, paying by exiling its own card, producing a token copy with an "except" clause (replacement colours, added subtypes, no mana cost). The same infinite-engine guard cycling introduced, now satisfiable by either self-discard or self-exile |
| **Conditional alternative costs** | Spectacle: "you may cast this for its spectacle cost **if** an opponent lost life this turn" — `alternative_cost`, a mana cost plus the condition gating it. A field of its own rather than a condition on `evoke`, because evoke's flag is written onto the permanent and read back by "it's sacrificed when it enters": a spectacle spell reusing it would claim to have been evoked. The condition is checked when the line is *offered*, since it is permission to cast the card that way at all (601.2b) — offering it and then refusing payment would show a price that cannot be paid. An `alternative_cost` with no condition is refused: that is `evoke`, and a card spelling it this way would be offered twice at two prices with nothing to choose between |
| **Spell copying** | "Copy this spell" (706.10) — the `copy_spell` op, and with it storm, gravestorm and conspire. A copy is **not a card**: it is backed by a token object, which is what makes it vanish correctly, since an instant's copy resolves into a graveyard and the token state-based action removes it, leaving the original as the only card there. Copies go on top of the stack so they resolve before the original, and they emit `SPELL_COPIED` rather than `SPELL_CAST` — counting a copy as a cast would make the next storm spell exponential. `sid` defaults to the spell the ability belongs to, which is what storm and replicate copy. **"You may choose new targets" is not implemented**: every copy keeps the original's targets, because the choice is a decision per copy and a storm count of nine would ask nine times |
| **Fateseal** | "Look at the top card of target player's library. You may put that card on the bottom" — `scry` grew a `chooser` beside its `player`. Whose library and who decides are the same person for scry and different people for fateseal, which is the whole keyword: written without it the opponent would choose what to leave on top of their own deck, which is not a weaker fateseal but the opposite of one |
| **Proliferate** | "Another counter of each kind already there" (701.27a) — an op rather than an `add_counters` with a filter, because the kinds are read **per permanent at resolution** and differ between them: one proliferate grows a +1/+1 here and a charge counter there. It never starts a kind, and a kind pruned to zero is not a kind. Simplified in the documented way: it proliferates every permanent you control that has a counter rather than offering a free multi-select, since the choice only matters for counters you would rather not grow. `objects` narrows it |
| **One-way words** | "…and it becomes renowned" — the `set_flag` op and the `has_flag` condition, over a `flags` set on the object. Renown's whole content is that it happens once, and the counters cannot stand in for the flag: gating on "has no +1/+1 counters" would renown a creature again as soon as anything removed them. A set rather than a boolean per adjective, because each new printed word would otherwise be a field, a condition leaf and an op. `monstrous` keeps its own field — it carries an event and an op that read it. The flag clears with the rest of the battlefield state, so a creature that leaves and returns may be renowned again (400.7) |
| **Moving counters** | Graft and modular — the `move_counters` op. One op rather than `remove_counters` beside `add_counters`, because modular moves **all** of them and the number is not knowable when the card is written; two ops would thread the count through a binding nothing sets. The amount is clamped to what is actually on the source, and a move with no destination takes nothing off it. The default source is *this permanent wherever it is*, deliberately not the `{"self_only": true}` selector, which resolves through a battlefield scan and finds nothing for the modular creature that has just died |
| **Counters a dead creature had** | "…if it had no -1/-1 counters on it" — persist and undying. `counters_on` cannot answer it: `reset_permanent_state` empties `counters` on the way to the graveyard, so asked after the death it is always zero and both keywords would recur for ever. The counts are snapshotted onto the dies event beside `was_creature` and `was_attacking`, which are there for the same reason, and read back as `{"counters_had": "-1/-1"}`. `return_from_graveyard` grew a `counters` spec for the other half, which is the loop guard rather than decoration |
| **Damage history** | "Whenever a creature dealt damage by this creature this turn dies" — a per-turn ledger of victim → sources, cleared at cleanup with the damage itself, read by a `damaged_by` trigger filter. On the state rather than the object, because the creature it asks about has just died |
| **The per-turn ledger** | "If a creature died this turn", "if you attacked this turn", "if an opponent lost life this turn" — six tallies in one `GameState.turn_ledger`: creatures died (by controller), players who attacked, damage taken, life lost, spells cast, and cards put into graveyards. None is answerable from the board, because each is a count of an *event* and the board keeps no record that one happened. Folded in `GameState.emit` rather than counted at six primitives: every tally counts something already being logged, and `emit` is the one function all of them pass through, so no emitter changed and none can route around it. Damage to a player counts as life lost as well as damage (rule 118.2), which is what makes spectacle fire off a burn spell. Cleared at cleanup with `damage_ledger` — unlike the draw tally, nothing here can happen before turn 1 |
| **Draw history** | "Add {C} for each card you've drawn this turn" — a per-turn tally of draws per player, incremented in `draw_cards` so nothing routes around it, read as the `cards_drawn_this_turn` value expression. Cleared by the **untap step** and not by cleanup: the opening hand is drawn before turn 1 exists, and cleanup can still hand priority back inside the turn it is ending |
| **Exile until it leaves** | "Exile it until this permanent leaves the battlefield" — the O-Ring family. A link written on the *exiled card* naming the permanent that exiled it, so the exiler's own leaves-trigger returns its victims and nobody else's |
| **Cost reduction** | Both directions: "This spell costs {X} less to cast" as a card-level field (Ghalta), and "Creature spells with flying you cast cost {1} less" as a `spell_cost_reduction` static discounting *other* cards, filtered on the printed face of the spell being cast. Both go through one function, so legality and payment cannot disagree |
| **Ability locks** | "Its activated abilities can't be activated this turn", covering mana abilities |
| **Transforming double-faced cards** | Two `CardDef`s and one `GameObject`: `transformed` picks which face `GameState.card_of` returns, which is a single choke point, so the layers, legality, combat and the serializer all follow with no changes of their own. Enters front face up (712.13a). A back face is never cast, drawn or put in a deck, and the front→back link is authored while back→front is derived. Both faces share one Scryfall id and differ by `CardArt.back`. **Modal** double-faced cards are still absent — a back face here is a face, not a second castable card |
| **Split second** | "As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities" (702.61a). Priority is **not** suppressed — players still get it and still pass; what is withheld is almost everything they could do with it. Skipping the window instead would also skip state-based actions and trigger draining. Mana abilities survive because the rule says so, filtered out of the full activated list rather than re-derived; special actions (playing a land, suspending) survive too, being neither casting nor activating. Read off the stack rather than latched at cast time, so it ends exactly when the spell leaves — countered, resolved or fizzled alike |
| **Activation restrictions** | "Activate only if you control five or more Vampires" — a `condition` on an activated ability, in the full `if`-effect language, checked by `legality` before the ability is offered and nowhere else (602.5c). Distinct from `sorcery_speed_only`, which is a timing restriction rather than a board one |
| **The top card of a library** | Both halves of Vampire Nocturnus: `reveal_library_top`, a player-wide static that changes no rule and only makes one card public (sent to every seat, since "revealed" means revealed), and a `top_of_library` condition leaf reading that one card's printed face. A pipeline input like any zone count — and a strictly sharper question than `exists` over the library, which asks whether *any* black card is anywhere in ninety-nine |
| **Extremes, and event bindings in an intervening if** | "A creature with the least toughness among creatures you control" — the `extreme` selector clause (bolster), applied after every other clause because an extremum is a fact about the pool rather than about a candidate, and keeping ties so the player still chooses (701.36a). Separately, a trigger's intervening-`if` is now evaluated against **the event's bindings**, not just the board: evolve's "if that creature has greater power than this creature" read zero for "that creature" and never fired, silently. The condition and the ability it gates now build their bindings from one function, so they cannot disagree about what "that creature" means |
| **Relative selectors** | "…for each other attacking creature that **shares a creature type with it**" — `shares_a_type_with` and `exclude_binding`, both naming a trigger binding rather than a list written into the card. Derived subtypes on both sides, so changelings and granted types count; an unbound name matches nothing rather than everything |
| **One-shot type changes** | "It becomes a Vampire in addition to its other types" — the `add_subtype` **op**, distinct from the static of the same name: written onto one object and outliving the permanent that converted it. Recorded on the object, so a static's filter may read it without any static coming to depend on another's output |
| **Gaining control** | "Gain control of target creature" — permanently, via the `gain_control` op. The object never changes zones, so it is `controller` plus the three rules hanging off it: summoning sickness for the new controller (302.6), removal from combat (506.4), and zone destinations that still follow the **owner** (400.3). Its own `control_changed` event, because no zone change happens and the log would otherwise show a creature swapping sides in silence. The until-end-of-turn form (Act of Treason) is **not** implemented and the loader refuses a `duration` rather than ignoring it |
| **Monstrosity** | The counters, the one-way flag, and the "becomes monstrous" trigger |
| **Conditional statics** | "As long as this has a slumber counter on it, it's a land" — including type *replacement*, not just grants. The condition is a boolean tree (`all`/`any`/`not`/`exists`/`cmp`/`is_your_turn`) over counters on the source, printed characteristics of the board, and how many cards sit in a zone, so **Threshold** works: Nimble Mongoose is a 1/1 at six cards in the graveyard and a 3/3 at seven, in either direction |
| **Trigger doubling** | Ancient Greenwarden's "that ability triggers an additional time", for lands entering |
| **Hybrid mana** | `{W/U}` and `{2/W}` parsed, paid and counted towards colour identity |
| **Restricted mana** | "Spend this mana only to cast a creature spell", by filtering sources before the solver |
| **Detain** | "Until your next turn, that permanent can't attack or block and its activated abilities can't be activated" (701.30a) — one op, because detain is one printed word and the residual gate asks each *ability* which sentence it implements. Recorded as the **player** who detained rather than a turn number: "your next turn" moves when somebody is eliminated, so the untap step clears the detain belonging to whoever is untapping. Not a `TempEffect`, for the reason `must_attack` is not — `until_eot` is wiped at cleanup, and a detain that ended there would expire before the creature would ever have attacked |
| **Block requirements** | Provoke: "target creature blocks this creature this combat if able" — the `must_block` op, an oid on the blocker naming the attacker it owes, spent when blockers lock in. The mirror of `must_attack`, and it stops being a mirror at the enforcement point: attacking is not exclusive, so withholding "Done attacking" is enough, while a blocker that blocks the wrong creature cannot be retracted. So a block requirement narrows what `legal_blocks` **offers** as well as what `blocks_valid` accepts. Always "if able", checked with `can_block(..., ignore_existing=True)` — a creature that chose to block elsewhere was able to block this one, which is the whole thing provoke prevents |
| **Attack requirements** | Both forms: the one-shot `must_attack` op ("attacks this turn / next combat if able") and the continuous `attacks_if_able` static ("attacks each combat if able", including the goad-shaped "creatures your opponents control"). Enforced at one point by withholding "Done attacking", and always subject to "if able", so a tapped or summoning-sick creature owes nothing and the step cannot deadlock |
| **Variable mana abilities** | "Add {G} for each +1/+1 counter on this creature" / "for each creature you control" — an `amount` on `add_mana`, evaluated at activation and applied at the one point the payment solver and the payout already share, so the price offered and the mana made cannot differ. Rule 605 is intact: evaluating the amount asks nothing, it only looks |
| **Token copies** | "A token that's a copy of target creature", copying the printed card and nothing accumulated on it |
| **Protection** | From a type, subtype or colour, across all four of damage, enchant/equip, block and target |
| **Permanent keyword grants** | `grant_keyword` takes a `duration`: until end of turn (the default, unchanged) or `permanent`, meaning for as long as the permanent lasts. Riot's "enters with haste" is the second, and the difference is invisible on the turn the creature arrives and total afterwards — an until-end-of-turn haste evaporates at cleanup, leaving a riot creature that chose haste indistinguishable from one that chose the counter. Stored in `granted_keywords` rather than as a `TempEffect`, for the reason `hasted_by_suspend` is a field: only one of the two is swept by `clear_until_eot`. A misspelled duration is refused rather than defaulted |
| **Granted abilities** | "…and 'Whenever this creature deals combat damage to a player, draw a card'", until end of turn. Triggered abilities only |
| **Retrace** | Casting from the graveyard by discarding a land |
| **Suspend** | The special action, the upkeep tick, the free cast, and haste on what arrives |
| **Splitting into piles** | Fact or Fiction: an opponent splits, the caster chooses |
| **X costs** | The caster chooses X, as a `choose_x` decision raised before the cost is paid. Legality still computes the ceiling, but only to decide whether the spell is castable at all |
| **Manual mana** | A seat may tap its own permanents and pick which colour a modal mana ability makes. Mana abilities never use the stack, so this keeps priority |
| **Modal spells at cast time** | A single top-level `choose_mode` is answered as the spell or ability goes on the stack, and recorded on `StackItem.modes` |

## Simplified

Each of these is a deliberate trade. The rationale matters more than the rule.

| Simplification | What it means | Why |
|---|---|---|
| **No layers system** | Continuous effects apply in a fixed order; static filters and static "as long as" conditions read pipeline *inputs* only — printed characteristics, board state, counters, zone counts — never another static's output, enforced at load time | The full layer system with timestamps and dependency analysis is a large subsystem that would change no outcome for any card in these decks |
| **Automatic mana payment, by default** | The solver picks which land to tap, preferring to spend abundant colours so scarce ones stay open. A land doubled by Vorinclex doubles what it produced rather than offering a free choice of type, because a mana ability may never stop to ask. A seat can opt out with **manual mana** (`PlayerState.manual_mana`, the rail's Auto mana / Manual mana toggle), which offers every tap-only mana ability as an action and one action per colour a dual could make. Off for AI seats, so the RL action space is unchanged. Independently of the toggle, a permanent that offers something *besides* its tap-only mana ability offers both to a human seat (`PlayerState.offer_all_abilities`): a Forest stays the solver's, a Mind Stone shows its sacrifice ability *and* its tap | Removes an enormous branching factor for the RL agent and the worst tedium from the UI, without making "tap this land for blue" impossible to say — or letting one click spend a permanent that had more than one thing to do |
| **Automatic damage assignment order** | Blockers are ordered by effective toughness ascending; the attacker is never asked | One more decision point per combat for a choice that is nearly always forced |
| **Automatic trigger ordering** | Simultaneous triggers you control resolve in a fixed order rather than one you choose | Matters only for a handful of interactions, none of them in these decks |
| **Modes chosen before targets** | A modal spell now picks its mode as it is cast (rule 601.2b), but its *targets* are enumerated as part of the action, so they are chosen first — the reverse of the printed order. A **nested** `choose_mode`, and any `choose_mode` inside a **triggered** ability, still resolve late: neither has a single cast-time question to answer | Cast-time modes were the observable half — an opponent can now see the mode they are responding to. Target-before-mode is what the shared `optional: true` idiom in [card-dsl.md](card-dsl.md) exists to paper over, and closing it means moving target enumeration behind a decision |
| **X capped for the policy** | A human is offered every X from 0 up to what the board can pay. The RL policy sees X ∈ 0..9, because `CHOICE_CAP` in `ai/action_space.py` is 10 and `IDX_CHOOSE` sits below `IDX_YES` in the index layout | Raising the cap shifts every index above it and invalidates trained checkpoints, for a ceiling that only bites above ten spare mana |
| **"As this enters, choose…" is a trigger** | Vanquisher's Banner's "as this artifact enters, choose a creature type" is implemented as a `self_enters` trigger, so the type is chosen a moment *after* the permanent arrives rather than as it does. Until it is chosen, the filters it feeds match nothing | `zones._enter_battlefield` applies enter-replacements synchronously and cannot yield a decision. The window is observable only by another trigger ordered between the two, and closing it means making the replacement whitelist generator-driven |
| **Object identity survives zone changes** | The `oid` is preserved where the rules would create a new object; permanent state is reset instead | Simpler and equivalent for everything except effects that track "the new object" |
| **Last-known information is explicit** | A card that needs a value after its target has left declares a `snapshot` op (see Swords to Plowshares) | A global LKI system for two cards is not worth it; the explicit form is also easier to read |
| **Commander replacement is automatic** | A commander always returns to the command zone rather than being asked | It is what players choose in practice, and it keeps zone changes out of the decision system |
| **Legend rule keeps the newest** | Duplicated legends are resolved without asking the controller | The choice is nearly always irrelevant |
| **Target options capped at 12** | A spell offers at most 12 target combinations | Only bites on very wide boards; without it a single "target creature" can flood the action space |
| **Turn cap** | 30 turns per player (60 in a duel, 120 in a pod), then a draw | Self-play must terminate. Draws are counted and reported |
| **Trigger loop guard** | More than 200 triggers in one step raises `RulesLoopError`, scored as a draw | One pathological board must not abort a 10,000-game run |
| **Delayed triggers resolve off the stack** | "At the beginning of the next upkeep, draw a card" runs as the step begins rather than being put on the stack | Same trade as modes and trigger ordering: only observable when somebody would respond differently to the delayed half than to the spell that scheduled it |

### Simplifications *inside* a hand-written card

Everything above is a deliberate, engine-wide trade. There is a second kind that
was never decided and never written down: individual precon cards that implement
less than they print.

`data/decks/*.deck.json` records `substitutions` — Scute Swarm swapped for
Tireless Provisioner because copy effects did not exist. That mechanism only ever
covered swapping one card for another. It has nothing to say about Tireless
Provisioner itself dropping the Food-or-Treasure choice, Krosan Tusker shipping
as a vanilla 6/5 with no cycling, or Anticipate being implemented as Preordain.

Those cards predate the authoring pipeline and never cleared its gates. The
current count is in `tests/cards/precon_deficits.json`, which is generated, and
the whole picture is `python scripts/audit_cards.py`. They are not new bugs —
they are the cost of building the precons before the gates existed, measured for
the first time. Repair one with `/author-cards <name>`; the mechanics they are
waiting on are `/extend-dsl` jobs, and as of this sequence there are none left
in the report except Kydele's per-turn draw tally. Cycling was
one of them and now ships in full, trigger included, so Krosan Tusker is off
this list. Evolve went with it, on Gyre Sage. Skulk and threshold have both shipped since, and
Nimble Mongoose is off this list. So are intimidate (with the rest of the
evasion family) and investigate — the latter needed no vocabulary at all, only a
Clue in the token pool, and Bygone Bishop is off this list with it.

## Imported cards, which are simplified further

Everything above describes a **hand-written** card. A deck imported from Moxfield
is mostly cards nobody wrote rules for, generated by `src/automtg/cards/proxy.py`,
and those carry a second, much larger set of simplifications. Each is recorded on
the card and shown at import; the full list is in
[deck-import.md](deck-import.md). The ones that change how a game plays:

| Simplification | What it means |
|---|---|
| **Non-keyword rules text is inert** | The card is a real permanent with the right name, cost, types and stats. Its printed abilities do nothing |
| **Front faces only** | A transform or modal DFC generates as its front face. An MDFC land loses the land half |
| **Phyrexian and snow costs are rewritten** | `{W/P}` becomes `{W}`, `{S}` becomes `{1}`. Mana value is always preserved. Ordinary hybrid (`{W/U}`, `{2/W}`) is now kept exactly as printed |
| **No loyalty, no defence** | Planeswalkers and Battles enter play and then sit there |
| **One mana per activation** | Scryfall records *which* mana a permanent makes, not how much. A generated Sol Ring taps for one |
| **Taplands are unconditional** | "Enters tapped unless…" enters tapped. Generating the upgrade would hand every imported deck a better mana base than it was built with |
| **`*` power reads as 0** | The characteristic-defining ability behind it is not modelled |
| **Some lands do nothing** | A land whose whole ability the generator cannot express — a bounce land's "return an Island you control" — arrives as an inert permanent. The import report counts those separately from the ones that simply make no mana, because a fetchland makes no mana *by design*. Fetchlands and creature-lands themselves are now [authored](card-authoring.md) rather than generated |

## Not implemented

These are absent, and the curated decks avoid them. Adding any one is additive.

**Card types and mechanics**
Planeswalkers · battles · sagas · modal double-faced cards · split and adventure cards ·
companions · vehicles. **Transforming** cards are implemented (above); the modal
kind, whose back face is a second card you may cast rather than a face you turn
over to, is not.  **Partner** is accepted as an inert
keyword: it is a deck-construction rule, and the engine is handed a finished deck

**Costs and casting**
Alternative costs in general (evoke is implemented) · phyrexian and snow mana ·
convoke and similar · overload

**Effects**
Copying a permanent as anything but a token · gaining control of a permanent
*temporarily* (the permanent form is implemented; Act of Treason is not) ·
damage prevention or redirection other than protection · regeneration ·
granting a *static* or *activated* ability to
another permanent (triggered ones work) · general replacement effects (only four are
whitelisted: enters tapped, enters with counters, the commander zone change, and
tokens ceasing to exist)

**Combat**
Attacking planeswalkers or battles · banding · manual damage
division · attacking with creatures you do not control

**Structural**
Multiplayer politics (voting) · sideboards and companions · the monarch,
initiative, day/night and the other designated-player mechanics (the city's
blessing is implemented; the rest are not)

## How this is enforced

None of the above is a promise in prose — it is checked:

- The card loader validates every op name, selector key, value form, keyword, type and
  trigger event against the registries. An unknown one raises `DslError` at load time,
  which fails `pytest`, not a game.
- The "statics may not read statics" constraint is a load-time check on every static
  ability's filter.
- `tests/cards/test_every_card_works.py` plays every shipped card in a rigged sandbox
  and asserts it resolves into the right zone, with per-card outcome expectations from
  `tests/cards/expectations.json`.
- `tests/cards/test_hand_written_cards.py` runs all six authoring gates over every
  hand-written card, and separately checks that each card's `oracle_text` is what the
  catalog says it prints — the check that stops a card from being verified against a
  summary of itself. Cards that do not pass yet are listed, with reasons, in the
  generated `tests/cards/precon_deficits.json`; that list can only shrink.
- `tests/cards/test_auto_cards.py` does the same for every machine-authored card.
- Deck legality, colour identity and singleton rules are tested per deck.

If a card in this repo does not work, one of those tests fails.
