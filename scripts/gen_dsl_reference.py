"""Generate ``docs/card-dsl-reference.md`` -- the DSL's vocabulary, held to the engine.

    python scripts/gen_dsl_reference.py --write    rewrite the reference
    python scripts/gen_dsl_reference.py --check    exit 1 if it is stale or the map drifted

``docs/card-dsl.md`` used to open with "139 of them" above a hand-kept op table,
and every one of those numbers was wrong within a release: an op registered by
``/extend-dsl`` lands in ``OPS`` and nowhere else, so the prose kept describing a
smaller language than the one that shipped. The same drift hit every other
family -- selectors, values, conditions, statics -- each with its own count and
its own list, none of them checked.

So the **names** here are read off the engine's own registries and enums, and
only the **descriptions** are written by hand, in the maps below. The two are
held together in both directions: a name the engine knows that has no
description fails ``--check`` (and ``tests/cards/test_dsl_reference.py``), and
so does a description for a name the engine no longer has. Adding an op means
adding one line to ``OPS`` here and regenerating; forgetting either is a red
build rather than a stale page.

Links in the third column point at the heading that defines each item. The
heading *text* is what is curated; which file it lives in (``card-dsl.md`` or
``card-dsl-cookbook.md``) is looked up at generation time, so the reference
survives the cookbook split without a rewrite. A heading found in neither file
is an error under ``--check`` and a warning under ``--write``.

The pattern is ``tests/cards/test_keyword_census.py`` (docs held to enums) and
``scripts/report_gaps.py`` (a doc regenerated wholesale, never appended).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commanderblitz.cards.authoring.packet import (
    CARD_LEVEL_COST_KEYS,
    CARD_LEVEL_FACE_KEYS,
    CARD_LEVEL_RIDER_KEYS,
)
from commanderblitz.cards.loader.vocabulary import (
    COST_REDUCTION_FILTER_KEYS,
    COST_REDUCTION_KEYS,
    COST_REDUCTION_REFUSED_FILTER_KEYS,
    DELAYED_TRIGGER_KEYS,
    GRANTABLE_STATIC_EFFECTS,
    KEYWORD_ALIASES,
    MANA_RIDER_OPS,
    PLAYER_WIDE_STATIC_EFFECTS,
    SPELL_FILTER_KEYS,
    STATIC_AFFECTS_FILTER_KEYS,
    STATIC_CONDITION_HEADS,
    STATIC_EFFECTS,
    STATIC_VALUE_KEYS,
)
from commanderblitz.cards.schema import CostModel
from commanderblitz.engine.effects import known_ops
from commanderblitz.engine.effects.conditions import CONDITION_KEYS
from commanderblitz.engine.effects.registry import RECORDING_OPS
from commanderblitz.engine.effects.selectors import (
    PLAYER_SPEC_NAMES,
    SELECTOR_KEYS,
)
from commanderblitz.engine.effects.values import VALUE_KEYS
from commanderblitz.engine.enums import (
    CardType,
    DecisionKind,
    Keyword,
    Supertype,
)
from commanderblitz.engine.events import EventType
from commanderblitz.engine.objects import PLAYABLE_DURATIONS
from commanderblitz.engine.triggers import (
    TRIGGER_EVENTS,
    TRIGGER_FILTER_KEYS,
)

DOCS = ROOT / "docs"
OUTPUT = DOCS / "card-dsl-reference.md"
#: The files a heading may live in, searched in this order.
SOURCE_DOCS = ("card-dsl.md", "card-dsl-cookbook.md")

# --------------------------------------------------------------------------
# Curated descriptions.  Names come from the engine; only this text is by hand.
#
# Each entry is ``name: (description, heading)`` where ``heading`` is the exact
# text of the heading in card-dsl.md / card-dsl-cookbook.md that defines the
# item, or ``None`` to link to the family's main section.  Ops carry a group
# first.  Keep the description to one line; the heading is where the prose goes.
# --------------------------------------------------------------------------

Entry = tuple[str, str | None]

#: The op table's groups, in the order the original hand-written table used.
OP_GROUPS = (
    "Cards",
    "Board",
    "Modify",
    "Life & damage",
    "Players",
    "Mana",
    "Stack",
    "Turn structure",
    "Combat decisions",
    "Dice",
    "Control flow",
)

H_EFFECT_OPS = "Effect ops"
H_SELECTORS = 'Selectors — "which objects"'
H_VALUES = "Value expressions"
H_CONDITIONS = "Conditions"
H_TRIGGERS = "Triggers"
H_COSTS = "Costs"
H_PLAYER_SPECS = "Player specs"
H_STATICS = "Static abilities"
H_PLAYER_WIDE = "Player-wide statics"
H_COST_REDUCTION = "Cost reduction"
H_ALT_PLAY = "Alternative ways to play a card"
H_SHAPE = "The shape of a card"
H_KEYWORDS = "Which mechanism a printed keyword lands on"
H_PLAYABLE = 'How long "you may play it" lasts'
H_DELAYED = "`delayed_trigger` — an ability that watches an event"
H_MANA_RIDER = "A mana ability with a rider — the painland's drawback"
H_AS_LONG_AS = '"As long as…"'
H_STATIC_MAGNITUDE = '"+1/+1 for each charge counter on this artifact"'
H_RECORDING = 'Recording what an op consumed or produced — "this way", "the token"'
H_MONARCH = "The monarch"
H_GIFT = "Gift — a promise made to one opponent, for nothing"
H_BATCHED = '"Whenever **one or more** …" — `batched`'
H_SPREE = 'Spree — "choose **one or more** additional costs"'
H_TIERED = "Tiered, and reading back which price was paid"
H_DREDGE = "Dredge, madness and miracle — replacements that stop to ask"
H_SECOND_FACE = "A second castable face — adventure, aftermath and split cards"
H_MELD = "Meld — mutate's merged permanent, with the pair fixed by the card"
H_MORPH = "Face-down permanents — morph, megamorph and manifest"
H_ATTACKED = "Which creatures attacked this turn, and how many"
H_ENTERED = "Which permanents entered the battlefield this turn"
H_LEDGER = "Counting an event rather than the board"
H_PER_PLAYER = "Counting one player at a time"
H_CHEAPER = "An activated ability that gets cheaper"
H_EXERTED = '"If this creature hasn\'t been exerted this turn"'
H_CASTING_FROM_GY = "Casting from the graveyard"
H_UNTAP_NONE = "Not untapping at all"
H_LANDWALK = "Landwalk, and global attack prohibitions"
H_CANT_CAST_ZONES = '"Can\'t cast spells from anywhere other than their hands"'
H_CAST_CARD = '"You may cast that card" — a paid cast during resolution'
H_FLOOR = "Damage can't take you below 1"
H_CANT_COUNTER = '"This spell can\'t be countered"'
H_CHOOSE_PERMANENTS = "`choose_permanents` — marking without acting"
H_ROLL = "Rolling dice"
H_CASCADE = "Cascade, ripple and `reveal_until` — walking a library"
H_MONSTROSITY = "Monstrosity, and holding creatures down"
H_CLASSES = "Classes"
H_GAIN_CONTROL = "Gaining control of a permanent"
H_FIGHT = "`fight`"

OPS: dict[str, tuple[str, str, str | None]] = {
    # ---- Cards -----------------------------------------------------------
    "draw": ("Cards", "A player draws N cards; `as` records who drew.",
             "`draw`'s `as` — \"each opponent who drew a card this way\""),
    "discard": ("Cards", "A player discards N cards, chosen or at random; `as` records them.",
                "`discard`: `up_to` and `as`"),
    "mill": ("Cards", "Put the top N cards of a library into its graveyard.", None),
    "search_library": ("Cards", "Search a library for cards matching a selector, then shuffle.",
                       None),
    "search_zones": ("Cards", "One search over the union of two or more of your own zones.", None),
    "look_at_top": ("Cards", "Look at the top N cards; take some, send the rest somewhere.", None),
    "look_at_hand": ("Cards", "Look at a player's hand (private: only you see it).", None),
    "return_to_hand": ("Cards", "Return objects to their owners' hands.", None),
    "return_from_graveyard": ("Cards", "Return cards from a graveyard to hand or the battlefield.",
                              None),
    "reveal": ("Cards", "Reveal cards to the table; `as` records them.", None),
    "behold": ("Cards", "Choose a matching permanent you control or reveal a matching card from hand; `effects` is \"if you do\".",
               "behold — choose a permanent or reveal a card"),
    "scry": ("Cards", "Scry N; `chooser` separate from `player` is fateseal.", None),
    "surveil": ("Cards", "Surveil N: look at the top cards, graveyard any of them.", None),
    "shuffle": ("Cards", "Shuffle a library.", None),
    "put_on_top": ("Cards", "Put objects on top (or bottom) of their owners' libraries; `from_top` is the depth.",
                   None),
    "two_piles": ("Cards", "Separate cards into two piles; an opponent chooses one.", "Two piles"),
    "explore": ("Cards", "Explore: reveal the top card, land to hand or a +1/+1 counter.",
                "Explore"),
    "connive": ("Cards", "Connive: draw, discard, +1/+1 counter if a nonland was discarded.",
                "Connive"),
    "clash": ("Cards", "Clash with an opponent; the winner is bound for a later `if`.", "Clash"),
    "cascade": ("Cards", "Cascade: exile from the top until a cheaper nonland, cast it free.",
                H_CASCADE),
    "discover": ("Cards", "Discover N: exile until a nonland of mana value N or less; cast it free or take it.",
                 "Discover — cascade's walk, N or less, cast or hand"),
    "exile_until": ("Cards", "Exile from the top until a card matches; the rest stay exiled, the hit may be cast free.",
                    "exile_until — a walk that leaves its cards in exile"),
    "ripple": ("Cards", "Ripple N: reveal the top N, cast any with the same name free.",
               H_CASCADE),
    "reveal_until": ("Cards", "Reveal from the top until `amount` cards match (default one), move them together (under `controller: you` if named); bottom or shuffle the rest.",
                     H_CASCADE),
    "hideaway": ("Cards", "Hideaway: look at the top N, exile one face down, the rest to the bottom.",
                 'Hideaway — "that one, from there"'),
    "play_exiled": ("Cards", "Play or cast a card from exile this turn (impulse draw).",
                    '"You may play the exiled card this turn" — impulse draw'),
    "grant_playable": ("Cards", "Permit playing cards from a zone that normally forbids it, for a duration.",
                       H_PLAYABLE),
    "grant_graveyard_cast": ("Cards", "Permit casting matching spells from graveyards until end of turn.",
                             "Casting out of every graveyard, until end of turn"),
    "cast_from_hand": ("Cards", "Cast a spell from hand (or listed zones, or a named pool once per owner) without paying its mana cost.",
                       None),
    "cast_card": ("Cards", "Cast a named card during resolution, paying its mana cost; `as` records what was cast.",
                  H_CAST_CARD),
    "return_to_origin": ("Cards", "Return an exiled card to the zone it came from.",
                         '"…until this permanent leaves the battlefield" — giving it back'),
    "return_to_command_zone": ("Cards", "Return a commander from wherever it is to the command zone.",
                               '"Return it to the command zone" — `return_to_command_zone`'),
    # ---- Board -----------------------------------------------------------
    "destroy": ("Board", "Destroy permanents; `no_regeneration` forbids regeneration; `as` records what was destroyed.", None),
    "exile": ("Board", "Exile objects; `link`/`playable` tie them to the source or a permission.",
              None),
    "sacrifice": ("Board", "A player sacrifices permanents; `snapshot` remembers what they had.",
                  None),
    "put_onto_battlefield": ("Board", "Put cards onto the battlefield, optionally tapped or with counters.",
                             None),
    "create_token": ("Board", "Create N tokens by id; `as` records them; `power`/`toughness` size an X/X token.",
                     'An X/X token — "create an X/X blue Shark creature token"'),
    "add_counters": ("Board", "Put N counters of a kind on permanents or players; `counter: {\"binding\": \"counter\"}` on a `counter_placed` trigger is the kind that placement put.",
                     None),
    "empower": ("Board", "Empower Jace N: N loyalty on a Jace token you control, creating one first if none.",
                '`empower` — "Empower Jace N"'),
    "amass": ("Board", "Amass [subtype] N: N +1/+1 counters on an Army creature you control, creating a 0/0 black Army token first if none; it becomes that subtype too.",
              '`amass` — "Amass Zombies N"'),
    "incubate": ("Board", "Incubate N: create a double-faced Incubator artifact token with N +1/+1 counters on it, which transforms for {2} into a 0/0 Phyrexian artifact creature.",
                 '`incubate` — "Incubate N"'),
    "remove_counters": ("Board", "Remove N counters of a kind.", None),
    "tap": ("Board", "Tap permanents.", None),
    "untap": ("Board", "Untap permanents.", "Untapping on somebody else's turn"),
    "attach": ("Board", "Attach an Aura, Equipment or Fortification to a permanent or player.",
               "Auras and Equipment"),
    "unattach": ("Board", "Unattach the source (reconfigure).", "Reconfigure — taking it off again"),
    "lock_abilities": ("Board", "Its activated abilities can't be activated this turn.",
                       '"Its activated abilities can\'t be activated this turn"'),
    "monstrosity": ("Board", "Monstrosity N: become monstrous with N +1/+1 counters.", H_MONSTROSITY),
    "freeze": ("Board", "Tap and it doesn't untap during its controller's next untap step.", None),
    "copy_permanent": ("Board", "Create a token copy of a permanent; `as` records the copies.",
                       "Token copies"),
    "grant_ability": ("Board", "Give permanents one of the card's `grantable_abilities`.",
                      "Granting an ability"),
    "skip_untap": ("Board", "It doesn't untap during its controller's next untap step.",
                   H_UNTAP_NONE),
    "must_attack": ("Board", "Creatures attack this turn if able.", "Attack requirements"),
    "must_attack_planeswalker": ("Board", "Creatures attack a planeswalker this turn if able.",
                                 '"…creatures that player controls attack Gideon Jura if able"'),
    "must_block": ("Board", "Creatures block this turn if able.", None),
    "cant_attack_player": ("Board", "Creatures can't attack a player (or only their walkers of a subtype) until a duration ends.",
                           '"That player can\'t attack you"'),
    "goad": ("Board", "Goad creatures until your next turn, or for the rest of the game.", "Goad"),
    "redirect_attack": ("Board", "Reselect what an attacking creature attacks; nothing is declared.",
                        "Reselecting an attack — `redirect_attack`"),
    "cant_block": ("Board", "Creatures can't block this turn.",
                   "The `cant_block` **op** — the same sentence with a clock"),
    "unblockable": ("Board", "Creatures can't be blocked this turn (optionally except by blockers matching a filter).",
                    "The `unblockable` op — the same wire, read from the attacker's end"),
    "cant_sacrifice": ("Board", "Permanents can't be sacrificed for a duration.",
                       "The `cant_sacrifice` op — a prohibition on a *game action*, not a zone change"),
    "move_counters": ("Board", "Move counters from one permanent to another.", None),
    "set_flag": ("Board", "Write a word on the source for the game (renowned, …).", H_EXERTED),
    "proliferate": ("Board", "Proliferate: choose permanents and players, add one of each counter.",
                    "Proliferate — a choice over permanents and players"),
    "double_counters": ("Board", "Double the counters of a kind on a permanent.",
                        "Doubling the counters on a permanent"),
    "distribute_counters": ("Board", "Distribute N counters among targets as the player chooses.",
                            "Distributing counters among targets"),
    "detain": ("Board", "Detain permanents until your next turn.", None),
    "distribute_control_among_opponents": ("Board", "For each permanent, choose a different opponent; each gains control of theirs.",
                                           "Each opponent gains control of the one chosen for them"),
    "gain_control": ("Board", "Gain control of permanents, for a duration or for good.",
                     H_GAIN_CONTROL),
    "rotate_control": ("Board", "Pass permanents around the table to the left or right.",
                       '"Choose left or right" — passing the board around the table'),
    "haunt": ("Board", "Exile the source haunting a creature.",
              "Haunt — the exile link pointing the other way"),
    "pair": ("Board", "Soulbond: pair the source with another creature.",
             "Soulbond — a relationship that is not attachment"),
    "aura_swap": ("Board", "Exchange the source for an Aura card in hand.",
                  "Aura swap — an exchange, not two moves"),
    "encode": ("Board", "Cipher: exile the spell encoded on a creature.",
               "Cipher — the third direction an exile link can point"),
    "cast_copy": ("Board", "Cast a copy of an encoded or linked card without paying its cost.",
                  None),
    "manifest": ("Board", "Manifest the top card of a library face down as a 2/2.", H_MORPH),
    "meld": ("Board", "Meld the source with its named partner into one permanent.", H_MELD),
    "phase_out": ("Board", "Permanents phase out.", '"Target creature phases out"'),
    "regenerate": ("Board", "Regenerate permanents (a shield for the turn).",
                   '"It can\'t be regenerated."'),
    "replace_deaths": ("Board", "If it would die this turn, exile (or another zone) instead.",
                       '"If it would die this turn, exile it instead"'),
    "set_turn_flag": ("Board", "Write a word on the source for the turn (exerted, …).", H_EXERTED),
    "replace_leaves_battlefield": ("Board", "If it would leave the battlefield this turn, do something else.",
                                   None),
    "become_copy": ("Board", "A permanent becomes a copy of another.",
                    "A permanent that enters as a copy"),
    "exile_and_return": ("Board", "Exile permanents, then return them (transformed, under an owner).",
                         '"Exile it, then return it transformed under its owner\'s control"'),
    "become_prepared": ("Board", "Prepare the source so it may cast a copy of its `prepared_face`.",
                        "Prepared"),
    "phase_in": ("Board", "Phased-out permanents phase in.",
                 'Phasing — "does not exist", said by not being in a list'),
    "airbend": ("Board", "Airbend: exile and let owners cast for {2}; `as` records the pool.",
                'Airbend — "exile them, and their owners may cast them for {2}"'),
    "exchange_control": ("Board", "Exchange control of two permanents.", "Exchanging control"),
    # ---- Modify ----------------------------------------------------------
    "pump": ("Modify", "+N/+M until end of turn (or a duration).", None),
    "grant_keyword": ("Modify", "Permanents gain keywords for a duration.",
                      "How long a granted keyword lasts"),
    "grant_protection": ("Modify", "Permanents or players gain protection for a duration.",
                         "Granting protection"),
    "set_pt": ("Modify", "Set base power and toughness for a duration.", None),
    "animate": ("Modify", "A noncreature becomes a creature (types, P/T, colors) for a duration.",
                "Creature-lands"),
    "add_subtype": ("Modify", "Permanents gain a subtype in addition to their others, "
                    "for good or for a duration.",
                    '"It becomes a Vampire in addition to its other types"'),
    "change_text": ("Modify", "Replace one creature type or color word with another in its text.",
                    '`change_text` — "replacing all instances of one creature type"'),
    "transform": ("Modify", "Transform a double-faced permanent.", "Transforming double-faced cards"),
    "become_level": ("Modify", "A Class becomes level N.", H_CLASSES),
    "lose_all_abilities": ("Modify", "Permanents lose all abilities for a duration.",
                           "Losing all abilities because an effect said so"),
    "rename": ("Modify", "A permanent's name becomes the chosen or given name.",
               "Changing a permanent's name"),
    # ---- Life & damage ---------------------------------------------------
    "gain_life": ("Life & damage", "A player gains N life.", None),
    "lose_life": ("Life & damage", "A player loses N life; `as` records how much.", None),
    "damage": ("Life & damage", "A source deals N damage to objects or players; `excess_to` spills over; "
               "`defender_of` hits what a creature is attacking; `divided` splits it among a target spec "
               "as the spell is cast.",
               "`damage`'s `excess_to`"),
    "fight": ("Life & damage", "Two creatures fight.", H_FIGHT),
    "add_poison": ("Life & damage", "A player gets N poison counters.", None),
    "add_energy": ("Life & damage", "A player gets N energy counters ({E}).", "Energy"),
    "prevent_damage": ("Life & damage", "Prevent damage to a player this turn.",
                       "Preventing all damage to a player for the turn"),
    "prevent_combat_damage": ("Life & damage", "Prevent combat damage this turn, optionally only from sources matching `by`.",
                              "Fog — combat damage prevented by its source"),
    "prevent_damage_permanent": ("Life & damage", "Prevent damage dealt to or by a permanent for a duration.",
                                 "Preventing all damage to or by a **permanent**, for a while"),
    "lock_life_total": ("Life & damage", "A player's life total can't change for a duration.",
                        '"Your life total can\'t change"'),
    "damage_life_floor": ("Life & damage", "Damage can't reduce a player's life below N this turn.",
                          H_FLOOR),
    "cant_lose_the_game": ("Life & damage", "A player can't lose and opponents can't win, for a duration.",
                           None),
    # ---- Players ---------------------------------------------------------
    "become_monarch": ("Players", "A player becomes the monarch.", H_MONARCH),
    "extra_loyalty_activation": ("Players", "A player may activate loyalty abilities an extra time this turn.",
                                 None),
    "grant_flash_permission": ("Players", "A player may cast matching spells as though they had flash.",
                               None),
    "win_game": ("Players", "A player wins the game.", '"You win the game"'),
    "no_maximum_hand_size": ("Players", "A player has no maximum hand size for the rest of the game.",
                             '"No maximum hand size for the rest of the game"'),
    "emblem": ("Players", "A player gets an emblem with the given abilities.",
               'Emblems — "Target opponent gets an emblem with …"'),
    "cant_cast_spells_from_zones": ("Players", "A player can't cast spells from the listed zones.",
                                    H_CANT_CAST_ZONES),
    "cant_cast_spells": ("Players", "A player can't cast spells for a duration (the timed form of the static).",
                         H_CAST_CARD),
    "lose_game": ("Players", "A player loses the game.", '"That player loses the game"'),
    # ---- Mana ------------------------------------------------------------
    "add_mana": ("Mana", "Add mana to a player's pool.", "Mana abilities"),
    "add_mana_per": ("Mana", "Add one mana of a color for each object a selector finds.",
                     '"Add {G} for each …"'),
    "extra_land_drop": ("Mana", "A player may play an additional land this turn.", None),
    # ---- Stack -----------------------------------------------------------
    "counter": ("Stack", "Counter a spell or ability; `unless_pays` is the tax form.", None),
    "copy_spell": ("Stack", "Copy a spell; `new_targets` lets the copy be re-aimed.",
                   '"You may choose new targets for the copy"'),
    "grant_plot": ("Stack", "Plot a card: exile it, castable free on a later turn.", "Plot"),
    "grant_rebound": ("Stack", "Give a spell rebound as it resolves.",
                      "Granting rebound to a spell that does not print it"),
    "return_spell_to_hand": ("Stack", "Return a spell from the stack to its owner's hand.",
                             "Doing something to a spell that is not countering it"),
    "reflexive_trigger": ("Stack", "\"When you do\": queue a trigger off the preceding effect.",
                          '"When you do" — reflexive triggered abilities'),
    "copy_ability": ("Stack", "Copy an activated or triggered ability; `new_targets` re-aims it.",
                     None),
    # ---- Turn structure --------------------------------------------------
    "extra_combat": ("Turn structure", "An additional combat phase (and main phase) this turn.",
                     "An additional combat phase"),
    "extra_turn": ("Turn structure", "A player takes an extra turn after this one.", "An extra turn"),
    # ---- Combat decisions ------------------------------------------------
    "choose_blockers": ("Combat decisions", "Decide blocks on another player's behalf.", None),
    # ---- Dice ------------------------------------------------------------
    "roll_dice": ("Dice", "Roll N dice with F faces; `as` records the results.", H_ROLL),
    # ---- Control flow ----------------------------------------------------
    "if": ("Control flow", "Run `then` effects if a condition holds, else `else`.", None),
    "for_each": ("Control flow", "Run effects once per object a selector finds, bound as the loop value.",
                 None),
    "for_each_player": ("Control flow", "Run effects once per player of a spec.",
                        '"Each opponent sacrifices…" — a loop over players'),
    "may": ("Control flow", "Optional effects, with an optional `pay`; `as` records who said yes.",
            "`may`'s `as`, and `except` on a player spec"),
    "choose_mode": ("Control flow", "Choose one or more modes and run them.", "Modal spells with a target"),
    "choose_type": ("Control flow", "Choose a creature, permanent or card type (`of`), readable later.",
                    '"Choose a creature type"'),
    "choose_color": ("Control flow", "Choose a color, readable later.", '"Choose a color"'),
    "choose_card_name": ("Control flow", "Choose a card name; `as` records it.", '"Choose a card name"'),
    "choose_player": ("Control flow", "Choose a player; `as` records the seat.", None),
    "choose_permanents": ("Control flow", "Mark permanents without acting on them; `as` records them.",
                          H_CHOOSE_PERMANENTS),
    "repeat": ("Control flow", "Run effects N times.", None),
    "repeat_while": ("Control flow", "Run effects while a condition holds.", None),
    "snapshot": ("Control flow", "Remember what objects are now, for a later value or spec.",
                 "`sacrifice`'s `snapshot` — what the creature *had*"),
    "noop": ("Control flow", "Do nothing (a placeholder for text with no effect).", None),
    "delay": ("Control flow", "Run effects at the beginning of a named later step.",
              'Delayed triggers — "at the beginning of the next …"'),
    "delayed_trigger": ("Control flow", "Create a trigger that watches an event for a `duration` (the rest of the turn by default, or this combat).",
                        H_DELAYED),
    "join_forces": ("Control flow", "Each player may pay into one shared X.",
                    "Join forces — the one cost the whole table pays"),
}

SELECTORS: dict[str, Entry] = {
    "any_of": ("A union of whole selectors: any one may match.", None),
    "any_types": ("Any one of these card types is enough.", None),
    "attached": ("Attached to the named object (\"self\", a binding, a target).", None),
    "attacked_this_turn": ("Attacked this turn (read after combat).", H_ATTACKED),
    "attacking": ("Is attacking.", None),
    "attacking_player": ("Attacking this player (`you`/`opponent`/`any`/`most_life`), not their planeswalkers.",
                         '"Attacks **you**" is not "attacks you and/or your planeswalkers"'),
    "base_power": ("A comparison on base power (layer 7a/7b).",
                   "`power` / `toughness` — a *derived* characteristic, read at a fixed layer"),
    "base_toughness": ("A comparison on base toughness.",
                       "`power` / `toughness` — a *derived* characteristic, read at a fixed layer"),
    "binding": ("Exactly the objects a named `as` recorded.", H_RECORDING),
    "blocked": ("Is (or is not) blocked by anything.", None),
    "blocking": ("Is blocking.", None),
    "chooser": ("Who picks: `controller`, `owner` or `none`.",
                "`chooser` — when somebody else picks the mode"),
    "colors": ("Has one of these colors.", None),
    "controller": ("Controlled by `you`/`opponent`/`any` or a player spec.", None),
    "count": ("How many: an int or value, `all`, or `any`.", None),
    "created_with": ("Tokens created with the named permanent.",
                     'Tokens "created with this creature" — `created_with`'),
    "damaged": ("Was dealt damage this turn.", None),
    "damaged_by": ("Was dealt damage this turn by the named object.",
                   '"…dealt damage by this creature this turn"'),
    "drawn_this_turn": ("Cards drawn this turn (hand only).", "Cards in a hand drawn this turn"),
    "encoded_by": ("Cards encoded on the named creature (cipher).",
                   "Cipher — the third direction an exile link can point"),
    "entered_this_turn": ("Entered the battlefield this turn.",
                          "`entered_this_turn` — the same fact asked of **one** permanent"),
    "exclude_binding": ("Everything except the objects under a binding (\"each other\").", H_RECORDING),
    "exclude_self": ("Not this permanent (\"other\").", None),
    "exiled_with": ("Exiled with the named source.", "Targeting a card in exile"),
    "extreme": ("The greatest/least of power, toughness or mana value in the pool.", None),
    "has_counters": ("Has counters (of a kind) on it.", "`has_counters` — \"with counters on them\""),
    "haunted_by": ("Haunted by the named card.", "Haunt — the exile link pointing the other way"),
    "is_commander": ("Is (or is not) a commander.", None),
    "is_token": ("Is (or is not) a token.", None),
    "keywords": ("Has all of these keywords.", None),
    "mana_cost": ("Printed mana cost is one of these.", None),
    "mana_value": ("A comparison on mana value.", None),
    "min_colors": ("Has at least N colors (\"multicolored\").", '"Multicolored" — `min_colors`'),
    "colorless": ("Has no colors (105.2c); true only.", '"Colorless" — `colorless`'),
    "modified": ("Is modified (equipped, enchanted by you, or has counters).", None),
    "name": ("Named exactly this, or the name under a binding.", None),
    "not_colors": ("Has none of these colors.", None),
    "not_keywords": ("Has none of these keywords.", None),
    "not_name": ("Not named this (a list for two or more).", None),
    "not_subtypes": ("Has none of these subtypes.", None),
    "not_supertypes": ("Has none of these supertypes (\"nonbasic\").", None),
    "not_types": ("Has none of these card types (\"noncreature\").", None),
    "object_kind": ("Restrict to cards, tokens, spells or abilities.", None),
    "optional": ("Exactly N, or none at all (\"you may\").", None),
    "owner": ("Owned by `you`/`opponent`/`any` or a player spec.", None),
    "paid_by": ("A spell paid with mana from the named source.",
                '"When that mana is spent to cast…"'),
    "phased_out_with": ("Phased out by the named source.",
                        '"…phases out until this enchantment leaves the battlefield"'),
    "player": ("Whose zone to walk (for hand, library, graveyard, exile).", None),
    "power": ("A comparison on live power.",
              "`power` / `toughness` — a *derived* characteristic, read at a fixed layer"),
    "random": ("Pick at random rather than by choice.", None),
    "self_only": ("This permanent only.", None),
    "shares_a_color_with": ("Shares a color with the named object.",
                            "Describing objects relative to *another* object"),
    "shares_a_creature_type_with": ("Shares a creature type with the named object.",
                                    '"…that shares a creature type with this creature"'),
    "shares_a_name_with": ("Has the same name as the named object.",
                           "Describing objects relative to *another* object"),
    "shares_a_type_with": ("Shares a card type with the named object.",
                           "Describing objects relative to *another* object"),
    "shares_a_type_with_commander": ("Shares a creature type with your commander.",
                                     '"…that shares a creature type with your commander"'),
    "shares_permanent_type_with": ("Shares a permanent type with the named object.",
                                   "Describing objects relative to *another* object"),
    "subtypes": ("Has one of these subtypes.", None),
    "supertypes": ("Has one of these supertypes.", None),
    "tapped": ("Is (or is not) tapped.", None),
    "target": ("The objects a target id chose.", None),
    "toughness": ("A comparison on live toughness.",
                  "`power` / `toughness` — a *derived* characteristic, read at a fixed layer"),
    "types": ("Has all of these card types.", None),
    "union": ("One pool made of several zones' selectors.", "One choice across two zones — `union`"),
    "x_in_mana_cost": ("Has {X} in its printed mana cost.",
                       "A restriction that is not a name — `mana_value`, `x_in_mana_cost`"),
    "zone": ("Which zone to look in.", None),
}

#: Keys a static's `affects` filter answers that the effect-side selector does not.
STATIC_FILTER_EXTRAS: dict[str, Entry] = {
    "any_of": ("A union of whole static filters, each with its own `exclude_self`; `affects` only.",
               "`any_of` — a union of static filters"),
    "attached_to_host": ("Attached to the static's own source (\"equipped creature\").", None),
    "paired": ("Is paired (soulbond).", "Soulbond — a relationship that is not attachment"),
    "paired_with_source": ("Paired with the static's own source.",
                           "Soulbond — a relationship that is not attachment"),
}

PLAYER_SPECS: dict[str, Entry] = {
    "you": ("The ability's controller.", None),
    "opponent": ("An opponent (each of them, at a pod).", None),
    "each_opponent": ("Every opponent.", None),
    "each_player": ("Every player.", None),
    "all": ("Every player (a tally over the whole table).", None),
    "controller": ("The controller of the object in question.", None),
    "active_player": ("Whose turn it is.", None),
    "enchanted_player": ("The player the source Aura is attached to.", "An Aura that enchants a player"),
    "gift_recipient": ("The opponent promised a gift as this spell was cast.", H_GIFT),
}

VALUES: dict[str, Entry] = {
    "additional_paid": ("Whether (or how often) an additional cost was paid.", None),
    "attacked_this_turn": ("1 if the player attacked this turn, else 0 (raid).", H_ATTACKED),
    "attack_power_this_combat": ("Total power of the player's attackers as declared this combat (pack tactics).",
                                 "Pack tactics — attackers' total power as declared"),
    "attackers_this_turn": ("How many creatures the player attacked with this turn.", H_ATTACKED),
    "binding": ("A number a trigger or an `as` carried.", H_RECORDING),
    "cards_drawn_this_turn": ("Cards the player drew this turn.", H_LEDGER),
    "cards_from_graveyard_this_turn": ("Cards that left the player's graveyard this turn.", H_LEDGER),
    "cards_in_hand": ("Cards in the player's hand.", None),
    "cards_to_graveyard_this_turn": ("Cards put into any graveyard this turn (gravestorm).", H_LEDGER),
    "colors_of_mana_spent": ("Colors of mana spent to cast this (sunburst, converge).",
                             "Counting the mana that was actually spent"),
    "combats_this_turn": ("Which combat phase of the turn this is.",
                          "Which combat phase of the turn this is"),
    "commander_color_identity": ("Colors in your commander's color identity.",
                                 'Commander-identity mana — "any color in your commander\'s color identity"'),
    "commander_casts_this_game": ("Times the player has cast their commanders from the command zone this game (903.8's tally).",
                                  "Copying a spell for each commander cast"),
    "const": ("A literal number.", None),
    "count": ("How many objects a selector finds.", None),
    "counters_had": ("Counters of a kind (or \"any\", every kind) the permanent that just left had.", None),
    "counters_on": ("Counters of a kind on the objects a selector finds.", None),
    "creatures_died_this_turn": ("Creatures that died this turn (morbid).", H_LEDGER),
    "creatures_you_control": ("Creatures the player controls.", None),
    "damage_taken_this_turn": ("Damage the player was dealt this turn, summed over a plural spec (bloodthirst).", H_LEDGER),
    "most_sharing_a_name": ("The largest group in a pool sharing one name.", "Value expressions"),
    "distinct": ("Distinct values of a quality among a pool (domain, coven).",
                 "Counting different values rather than objects"),
    "extreme_value": ("The greatest/least of a quality in a pool, as one number.", None),
    "greatest_discarded_by_a_player": ("The greatest number of cards one player discarded this way.",
                                       "Discarding a whole hand, and reading the greatest that went"),
    "half": ("Half of a value, rounded `up` or `down`.", None),
    "lands_you_control": ("Lands the player controls.", None),
    "life_gained_this_turn": ("Life the player gained this turn.", H_LEDGER),
    "life_lost_this_turn": ("Life the player lost this turn (spectacle).", H_LEDGER),
    "life_of": ("A player's life total (summed over a plural spec).", None),
    "loop_value": ("The current item of an enclosing `for_each`.", None),
    "loyalty_activations_this_turn": ("Loyalty abilities the player activated this turn.", H_LEDGER),
    "mana_spent_of": ("Mana of a color actually spent to cast this.",
                      "`mana_spent_of` — what was paid, not what is printed"),
    "mana_symbols": ("Pips of a color among a pool's mana costs (chroma).", "Counting mana symbols"),
    "mana_value_of": ("Mana value of an object (summed over a pool).", None),
    "max": ("The greatest of several values.", None),
    "max_count_of": ("The most objects any one player of a spec has.", H_PER_PLAYER),
    "max_damage_taken_this_turn": ("The most damage any one of a spec's players was dealt this turn.", H_LEDGER),
    "max_life_of": ("The highest life total among a spec's players.", None),
    "max_poison_of": ("The most poison counters on any one of a spec's players (corrupted).",
                      'Corrupted — "an opponent has three or more poison counters"'),
    "min": ("The least of several values.", None),
    "player_count": ("How many players still in the game a player spec names (\"the number of opponents you have\").",
                     None),
    "times_tapped_this_turn": ("Times one object has become tapped this turn, counting every tap since the turn began.",
                               "How many times a permanent has become tapped this turn"),
    "unspent_mana_count": ("The unspent mana in a spec's players' mana pools.",
                           '"For each unspent mana you have"'),
    "min_count_of": ("The fewest objects any one player of a spec has.", H_PER_PLAYER),
    "min_life_of": ("The lowest life total among a spec's players.", None),
    "minus": ("a - b.", None),
    "permanents_entered_this_turn": ("How many matching permanents entered this turn.", H_ENTERED),
    "power_had": ("The power the dying creature had.", None),
    "power_of": ("An object's power.", None),
    "resolutions_this_turn": ("Times this ability has resolved this turn.", None),
    "rolled": ("Dice results under a binding: count, by face, parity or total.", H_ROLL),
    "spells_cast_this_game": ("Spells the player has cast this game, by filter.",
                              "Counting the spells you cast, by type"),
    "spells_cast_this_turn": ("Spells cast this turn (storm).", H_LEDGER),
    "starting_life_of": ("The life total a player began with.",
                         '"At least 7 life more than your starting life total"'),
    "sum": ("a + b + ….", None),
    "times": ("a * b.", None),
    "toughness_had": ("The toughness the dying creature had.", None),
    "toughness_of": ("An object's toughness.", None),
    "x": ("The X paid when this was cast or activated.", None),
}

CONDITIONS: dict[str, Entry] = {
    "all": ("Every listed condition holds.", None),
    "any": ("At least one listed condition holds.", None),
    "attacked_you_last_turn": ("One of these players attacked you (not your planeswalker or battle) during their last completed turn.",
                               None),
    "cast_during": ("The phase this spell was cast in (addendum).",
                    "Addendum — the phase a spell was cast in"),
    "cast_from_graveyard": ("This spell was cast from a graveyard.", None),
    "cast_from_hand": ("This spell was cast from hand.", None),
    "cmp": ("Compare `left` and `right` values with `op`.", None),
    "combat_damage_by": ("A player was dealt combat damage this turn by one of these subtypes (prowl).",
                         None),
    "cost_option": ("Which of the tiered additional costs was paid.", H_TIERED),
    "entered_from": ("The source entered from the named zone.", None),
    "evoked": ("The source was cast with evoke.", None),
    "impending": ("The permanent was cast for its impending cost (the rule's own reads).",
                  "Impending — a creature that is not one until it counts down"),
    "exists": ("A selector finds at least one object.", None),
    "gift_promised": ("A gift was promised as this spell was cast.", H_GIFT),
    "has_city_s_blessing": ("The player has the city's blessing (ascend).", "Ascend"),
    "has_flag": ("The source carries a word written by `set_flag`.", H_EXERTED),
    "has_turn_flag": ("The source carries a word written by `set_turn_flag` this turn.", H_EXERTED),
    "is_active_player": ("It is the given player's turn (\"during their turn\").",
                         '"During their turn" — whose turn a trigger means'),
    "is_monarch": ("The given player is the monarch.", H_MONARCH),
    "is_your_turn": ("It is the controller's turn.", None),
    "kicked": ("This spell was kicked.", "A permanent's own enters trigger can read it"),
    "left": ("`cmp`'s left operand.", None),
    "no_monarch": ("Nobody is the monarch.", H_MONARCH),
    "not": ("The condition does not hold.", None),
    "of": ("Which spell the cast-mode conditions ask about.", None),
    "overloaded": ("This spell was cast for its overload cost.", "Overload"),
    "right": ("`cmp`'s right operand.", None),
    "spree_mode": ("The given spree mode was bought.", H_SPREE),
    "step_is": ("The step the game is in now (\"during the declare attackers step\").", None),
    "two_share_a_color": ("Two cards in a pool share a color.",
                          '"Two cards that share a color" — `two_share_a_color`'),
    "was_cast": ("This arrival was a resolving spell (603.6e).", '"If it was cast" — 603.6e'),
    "zone_is": ("The source is in the named zone.", None),
}

#: Static-only value leaves, which the effect-side `VALUES` does not have.
#: Static-side entries, read before `VALUES`: a leaf in both languages whose
#: static reading is narrower or documented apart is described here.
STATIC_VALUE_EXTRAS: dict[str, Entry] = {
    "greatest_commander_mana_value": (
        "The greatest printed mana value among your commanders, wherever they are.", None),
    "spells_cast_this_turn": ("Spells a player spec's players have cast this turn; the bare spec only.",
                              '"As long as an opponent has cast a spell this turn"'),
}

STATIC_CONDITION_EXTRAS: dict[str, Entry] = {
    "counters": ("The source has (or lacks) counters of a kind.", None),
    "exists_derived": ("A permanent with these current characteristics exists (cant_attack, cant_block only).",
                       None),
    "is_attached": ("The source is attached to something.", None),
    "is_monstrous": ("The source is monstrous (701.37b).", H_MONSTROSITY),
    "top_of_library": ("The top card of a library matches a filter.",
                       '"The top card of your library is black"'),
}

TRIGGER_EVENT_DESCRIPTIONS: dict[str, Entry] = {
    "ability_activated": ("An ability is activated.", None),
    "attacks": ("A creature attacks.", None),
    "attacks_unblocked": ("An attacking creature goes unblocked; `batched` fires once per block declaration.",
                          H_BATCHED),
    "becomes_blocked": ("An attacking creature becomes blocked.", None),
    "becomes_level": ("A Class reaches a level.", '"When this Class becomes level N"'),
    "becomes_monarch": ("A player becomes the monarch.", H_MONARCH),
    "becomes_monstrous": ("A creature becomes monstrous.", H_MONSTROSITY),
    "becomes_tapped": ("A permanent becomes tapped.", None),
    "becomes_target": ("A permanent or player becomes the target of a spell or ability.", None),
    "becomes_untapped": ("A permanent becomes untapped.", None),
    "begin_combat": ("At the beginning of combat.", None),
    "blocks": ("A creature blocks.", None),
    "chapter": ("A Saga reaches a chapter (supplied by rule, never written).", "Sagas"),
    "counter_placed": ("Counters are put on a permanent or player; with `counter` and `nth`, the placement that puts the Nth counter of that kind on it.",
                       None),
    "creature_dies": ("A creature dies.", None),
    "creatures_attack_player": ("One or more creatures attack a player.",
                                '"Whenever one or more creatures attack one of your opponents"'),
    "creatures_deal_combat_damage": ("One or more creatures deal combat damage to one or more players.",
                                     '"One or more creatures … one or more players"'),
    "cycle": ("A card is cycled.", '"When you cycle this card…"'),
    "damage_prevented": ("Damage is prevented.", None),
    "deals_combat_damage": ("A creature deals combat damage to anything.",
                            '"…deals combat damage", to anything — `deals_combat_damage`'),
    "deals_combat_damage_to_planeswalker": ("A creature deals combat damage to a planeswalker.",
                                            '"…deals combat damage to a player or planeswalker"'),
    "deals_combat_damage_to_player": ("A creature deals combat damage to a player.", None),
    "deals_damage_to_player": ("A source deals any damage to a player.", None),
    "dealt_damage": ("A permanent is dealt damage; `batched` fires once per simultaneous damage event, `amount` its total.",
                     H_BATCHED),
    "dies": ("A permanent dies.", None),
    "discard": ("A player discards a card.", None),
    "draw": ("A player draws a card.", None),
    "draw_step": ("At the beginning of the draw step.", None),
    "end_step": ("At the beginning of the end step.", None),
    "land_played": ("A land is played.", None),
    "leaves_battlefield": ("A permanent leaves the battlefield.", None),
    "leaves_graveyard": ("A card leaves a graveyard.", None),
    "life_lost": ("A player loses life.", '"Whenever an opponent loses life"'),
    "mutates": ("A creature mutates.", '"Whenever this creature mutates…"'),
    "permanent_enters": ("A permanent enters the battlefield.", None),
    "postcombat_main": ("At the beginning of the postcombat main phase.", None),
    "precombat_main": ("At the beginning of the precombat main phase.", None),
    "sacrificed": ("A permanent is sacrificed.", None),
    "searches_library": ("A player searches a library.", None),
    "self_enters": ("This permanent enters the battlefield.", None),
    "spell_cast": ("A spell is cast.", None),
    "state": ("A state holds (603.8): the trigger's `state` condition; no event.",
              "`state` — \"When there are four or more page counters on this artifact\""),
    "spell_copied": ("A spell is copied (magecraft's other half).",
                     "`spell_copied`, and why magecraft is two abilities"),
    "token_created": ("A token is created.", None),
    "upkeep": ("At the beginning of the upkeep.", None),
    "you_attack": ("You attack with one or more creatures.", '"Whenever you attack"'),
    "you_gain_life": ("You gain life.", None),
}

STATICS: dict[str, Entry] = {
    "ability_cost_reduction": ("Activated abilities of matching permanents cost less.",
                               "A static that discounts another permanent's activated ability"),
    "activate_loyalty_as_though_instant": ("The player may activate loyalty abilities any time they could cast an instant.",
                                           None),
    "add_mana_on_tap": ("Whenever a matching permanent is tapped for mana, add extra mana.", None),
    "add_subtype": ("Matching permanents have an extra subtype.",
                    '"…is the chosen type in addition to its other types"'),
    "attack_tax": ("Matching creatures can't attack unless their controller pays.",
                   "Pricing an attack rather than forbidding it"),
    "attacks_if_able": ("Matching creatures attack each combat if able.", "The continuous form"),
    "black_mana_as_phyrexian": ("The player may pay life for each {B} in a cost.",
                                '`black_mana_as_phyrexian` — K\'rrik\'s "For each {B} in a cost"'),
    "block_restriction": ("Matching creatures can't block, or can only block under a rule.",
                          "Block restrictions"),
    "block_tax": ("Matching creatures can't block unless their controller pays.",
                  "Pricing a block rather than forbidding it"),
    "buff": ("Matching permanents get +N/+M.", H_STATIC_MAGNITUDE),
    "cant_activate_abilities": ("The player can't activate matching abilities.", None),
    "cant_attack": ("Matching creatures can't attack.", H_LANDWALK),
    "cant_attack_alone": ("Matching creatures can't attack alone.", "Can't attack or block **alone**"),
    "cant_attack_you": ("Matching creatures can't attack you or your planeswalkers "
                        "(`player_only`: you alone).",
                        "Forbidding an attack on you rather than pricing it"),
    "cant_block": ("Matching creatures can't block.", H_LANDWALK),
    "cant_block_alone": ("Matching creatures can't block alone.", "Can't attack or block **alone**"),
    "cant_cast_spells": ("The player can't cast matching spells.", None),
    "cant_cast_spells_from_zones": ("The player can't cast spells from the listed zones.",
                                    H_CANT_CAST_ZONES),
    "cant_gain_life": ("The player can't gain life.", '"Your opponents can\'t gain life"'),
    "cant_have_counters": ("Matching permanents can't have counters of the kind put on them.",
                           "`cant_have_counters` — a placement that doesn't happen"),
    "cant_lose_the_game": ("The player can't lose the game.", None),
    "cant_sacrifice": ("Matching permanents can't be sacrificed.", "Forbidding a sacrifice, continuously"),
    "cant_search_library": ("The player can't search libraries.",
                            '"Can\'t cause their controller to search their library"'),
    "cant_win_the_game": ("The player can't win the game.", None),
    "cast_as_though_flash": ("The player may cast matching spells as though they had flash.", None),
    "cast_from_graveyard": ("The player may cast matching spells from their graveyard; with "
                            "`active_zones: [\"graveyard\"]`, the card may cast itself from there.",
                            H_CASTING_FROM_GY),
    "cast_from_library_top": ("The player may cast spells from the top of their library: for life "
                              "with `pay_life_instead`, or matching `affects_spells` at the printed "
                              "cost, granting `cast_gains_keywords` to what is cast that way.",
                              None),
    "cast_only_at_sorcery_speed": ("The player may cast matching spells only at sorcery speed.", None),
    "crew_power_bonus": ("Matching creatures crew as though their power were N greater.",
                         "Crews Vehicles as though its power were N greater"),
    "damage_life_floor": ("Damage can't reduce the player's life below N.", H_FLOOR),
    "double_land_mana": ("Lands the player taps for mana add twice as much.", None),
    "double_land_triggers": ("The player's landfall-style triggers fire twice.", None),
    "double_nonland_mana": ("Nonland permanents the player taps for mana add twice as much.", None),
    "double_triggers": ("Matching permanents' triggered abilities trigger an additional time.",
                        "`double_triggers`, and its two axes"),
    "draw_limit": ("The player can't draw more than N cards each turn.",
                   '"Can\'t draw more than one card each turn"'),
    "enters_tapped": ("Matching permanents enter tapped.", None),
    "enters_with_additional_counters": ("Matching permanents enter with additional counters.",
                                        "`enters_with_additional_counters` — a static about other arrivals"),
    "extra_land_drops": ("The player may play N additional lands each turn.", None),
    "free_cast_permission": ("The player may cast matching spells without paying their mana cost.",
                             "`free_cast_permission` — Dracogenesis' standing free cast"),
    "freeze_opponent_lands": ("The player's lands don't untap during their untap step.", None),
    "grant_ability": ("Matching permanents have one of the card's `grantable_abilities`.",
                      "`grant_ability` as a static, and where the line now runs"),
    "grant_keyword": ("Matching permanents have keywords.", None),
    "granted_alternative_cost": ("The player may pay `cost` (energy or life) instead of matching spells' mana cost.",
                                 "`granted_alternative_cost` — paying energy instead of a spell's mana cost"),
    "grant_warp": ("Matching spells the player casts have warp for a price.",
                   "`grant_warp` — a card-level price handed to somebody else's cards"),
    "look_at_library_top": ("The player may look at the top card of their library any time.", None),
    "lose_all_abilities": ("Matching permanents lose all abilities.",
                           "`lose_all_abilities`, and why `abilities_of` exists"),
    "imprint_characteristics": ("This creature has the power, toughness and creature types of the last creature card exiled with it.",
                                "`imprint_characteristics` — Duplicant's size from a card in exile"),
    "lose_keyword": ("Matching permanents lose keywords and can't have or gain them.",
                     "`lose_keyword` — the other kind of removal, at the other end of the pipeline"),
    "mana_retention": ("The player doesn't lose unspent mana of the listed symbols as steps and phases end.",
                       "Player-wide statics"),
    "mana_becomes_colorless": ("Unspent mana the player would lose becomes colorless instead.",
                               "Player-wide statics"),
    "no_hand_limit": ("The player has no maximum hand size.", None),
    "player_hexproof": ("The player has hexproof: opponents' spells and abilities can't target them.",
                        "Player-wide statics"),
    "player_protection": ("The player has protection from a quality: damage, targeting and enchanting by it.",
                          "Protection"),
    "opponents_cant_force_discard_or_sacrifice": ("Opponents' spells and abilities can't make the player discard or sacrifice.",
                                                  '"Can\'t cause you to discard cards or sacrifice permanents"'),
    "play_lands_from_graveyard": ("The player may play lands from their graveyard.", None),
    "play_lands_from_library_top": ("The player may play lands from the top of their library.", None),
    "prevent_all_but": ("Prevent all but N of each instance of damage to matching permanents.",
                        "Prevent all but N of that damage"),
    "prevent_damage": ("Prevent damage dealt to matching permanents (absorb N, all of it, or all of it as that many +1/+1 counters) or N of each damage to a seat from a matching dealer.",
                       "Absorb, which is not protection with a number"),
    "protection": ("Matching permanents have protection from a quality.", "Protection"),
    "replace_counters": ("Counters put on matching permanents are replaced (doubled, redirected).",
                         "Counters replaced on the way in"),
    "replace_damage": ("Damage dealt by or to matching permanents is multiplied, increased by N or redirected.",
                       "Damage multiplied on the way out"),
    "replace_dies": ("If a matching permanent would die, exile it instead, optionally creating tokens.",
                     '"If a nontoken creature an opponent controls would die, instead exile that card"'),
    "replace_draw": ("If the player would draw a card, draw more instead.",
                     '"If you would draw a card, draw two cards instead"'),
    "replace_empty_draw": ("If the player would draw from an empty library, something else happens.",
                           None),
    "replace_graveyard": ("If a matching card would go to a graveyard, it goes elsewhere.", None),
    "replace_life_gain": ("If the player would gain life, they gain more instead.",
                          '"If you would gain life, you gain twice that much life instead"'),
    "replace_life_loss": ("If the player would lose life, they lose more instead.",
                          '"If a player would lose life, they lose twice that much instead"'),
    "replace_mill": ("If the player would mill, they mill more instead.", "Doubling a mill"),
    "replace_proliferate": ("If the player would proliferate, they proliferate again.",
                            "Proliferating twice"),
    "replace_token_creation": ("If the player would create tokens, create more or different ones instead.",
                               '"If you would create a … token, instead …"'),
    "reveal_library_top": ("The player plays with the top card of their library revealed.", None),
    "set_colors": ("Matching permanents are the given colors.", "`set_colors`"),
    "set_creature_types": ("Matching permanents' creature types are exactly the given ones; other subtypes and types stay.",
                           "`set_creature_types` — \"it loses all other creature types\""),
    "set_pt": ("Matching permanents have base P/T N/M.", None),
    "set_types": ("Matching permanents are the given card types and lose the others.",
                  "`set_types` now strips orphaned subtypes"),
    "skip_draw_step": ("The player skips their draw step.", None),
    "skip_extra_turn": ("The player skips extra turns.", None),
    "skip_untap_step": ("Matching permanents don't untap during their controller's untap step.",
                        H_UNTAP_NONE),
    "spell_cost_increase": ("Matching spells cost more (mana or life) to cast.",
                            "Making *other* spells cost more, in life"),
    "spell_cost_reduction": ("Matching spells cost less to cast.", "Making *other* spells cheaper"),
    "spells_cant_be_countered": ("Matching spells can't be countered.", H_CANT_COUNTER),
    "spend_mana_as_any_color": ("The player may spend mana as though it were any color.",
                                "`spend_mana_as_any_color` — Chromatic Orrery's colour waiver"),
    "untap_during_each_untap_step": ("Matching permanents untap during each other player's untap step too.",
                                     "Untapping on somebody else's turn"),
    "untap_limit": ("The player untaps at most N permanents during their untap step.", H_UNTAP_NONE),
    "ward": ("Matching permanents have ward with a cost.", "Ward with a cost"),
}

COST_REDUCTION: dict[str, Entry] = {
    "amount": ("Costs N less (usually gated on a `condition`).", H_CHEAPER),
    "count": ("Costs {1} less for each object a filter finds.", H_CHEAPER),
    "greatest_count": ("…for the greatest number any one player has.",
                       "A reduction that maximises a per-player tally"),
    "greatest_mana_value": ("…by the greatest mana value among a filter's objects.",
                            "…by the greatest mana value of a commander you own"),
    "total_mana_value": ("…by the total mana value of a filter's objects.",
                         "A reduction that sums mana values"),
    "total_power": ("…by the total power of a filter's objects.", None),
}

COST_REDUCTION_FILTER: dict[str, Entry] = {
    "any_of": ("Count an *or* of characteristics.", "A reduction that counts an *or* of characteristics"),
    "zone": ("Count in a zone other than the battlefield.", "Counting filters, and the `zone` key"),
}

ABILITY_COSTS: dict[str, Entry] = {
    "discard": ("Discard N cards.", None),
    "discard_selector": ("…matching this selector.", None),
    "discard_self": ("Discard this card (cycling).", "Cycling"),
    "exert": ("Exert the source.", "`exert` — the keyword as a cost"),
    "exile_from_graveyard": ("Exile matching cards from your graveyard.", None),
    "exile_from_hand": ("Exile a matching card from your hand (a pitch cost).",
                        "`exile_from_hand` — the pitch cost, and why it is not a discard"),
    "behold": ("Behold: choose matching permanents you control or reveal matching cards from hand.",
               "behold — choose a permanent or reveal a card"),
    "exile_self": ("Exile the source.", None),
    "exile_self_from_hand": ("Exile this card from your hand.", None),
    "loyalty": ("A loyalty cost (+N / -N).", "Planeswalkers"),
    # The heading prints a real minus sign (U+2212), and the slug keeps the
    # difference from a hyphen, so the glyph is load-bearing.
    "loyalty_x": ("A -X loyalty cost.", "`loyalty_x` — a −X loyalty cost"),  # noqa: RUF001
    "mana": ("A mana cost.", None),
    "mana_reduction": ("A reduction applied to this ability's mana cost.", H_CHEAPER),
    "mill": ("Mill N cards off your own library.", "`mill` — a cost, and never an effect"),
    "pay_energy": ("Pay N energy ({E}).", "Energy"),
    "pay_life": ("Pay N life, or a value expression (inside `may`, read with the effect's bindings).",
                 '"You may pay that much life. If you do…"'),
    "pay_life_x": ("Pay X life, X announced.", None),
    "put_counters": ("Put N counters of a kind on the source.",
                     "`put_counters` — counters on the source, paid on activation"),
    "remove_counters": ("Remove N counters of a kind from the source.", None),
    "remove_counters_from_among": ("Remove N counters of any kinds from among other permanents.",
                                   "`remove_counters_from_among` — counters of any kind, off other permanents"),
    "return_to_hand": ("Return a matching permanent to hand.", None),
    "sacrifice": ("Sacrifice a matching permanent; `as` names it for the effects.",
                  "Ghoulcaller Gisa — a sacrifice cost that names what it sacrificed"),
    "tap": ("{T}: tap the source.", None),
    "tap_permanents": ("Tap N other permanents, or `total_power` of them (crew).",
                       "Crew — a tap cost measured in power"),
    "times": ("Pay the whole cost that many times (cumulative upkeep).", None),
    "untap": ("{Q}: untap the source.", None),
    "untap_permanents": ("Untap N other permanents.", None),
    "x_value": ("X fixed by the card rather than announced.",
                "`x_value` — an X the card fixes, not the player"),
}

CARD_LEVEL_COSTS: dict[str, Entry] = {
    "additional_cost": ("A non-mana additional cost.", "An additional cost that is not mana"),
    "additional_cost_options": ("A choice between prices; tiered when each buys a different effect.",
                                H_TIERED),
    "additional_optional": ("An optional additional cost (kicker-like, non-mana).", None),
    "additional_repeatable": ("An additional cost that may be paid any number of times.", None),
    "alternative_cost": ("A non-mana alternative cost.", "An *alternative* cost that is not mana"),
    "ascend": ("Ascend (a state trigger, not a price).", "Ascend"),
    "bestow": ("Bestow cost.", "Bestow — the alternative cost that changes what the spell points at"),
    "buyback": ("Buyback cost.", None),
    "cost_reduction": ("This spell costs less to cast.", H_COST_REDUCTION),
    "dredge": ("Dredge N.", H_DREDGE),
    "emerge": ("Emerge cost.", None),
    "evoke": ("Evoke cost.", None),
    "impending": ("Impending N and its cost.", "Impending — a creature that is not one until it counts down"),
    "flashback": ("Flashback cost.", "Flashback"),
    "foretell": ("Foretell cost.", "Foretell"),
    "gift": ("The gift promised (a noun phrase).", H_GIFT),
    "kicker": ("Kicker cost.", "Kicker"),
    "madness": ("Madness cost.", H_DREDGE),
    "morph": ("Morph cost.", H_MORPH),
    "multikicker": ("Multikicker cost.", "Multikicker"),
    "escalate": ("Escalate cost, paid once per mode beyond the first.", "Escalate"),
    "mutate": ("Mutate cost.", "Mutate — two cards, one permanent, and one synthesised `CardDef`"),
    "overload": ("Overload cost.", "Overload"),
    "pay_generic_with": ("Convoke, improvise or delve: what may pay generic mana.",
                         "Convoke, improvise and delve"),
    "retrace": ("Retrace.", None),
    "splice": ("Splice cost.", "Splice"),
    "spree": ("Spree: priced modes, a non-empty subset bought on cast.", H_SPREE),
    "strive": ("Strive: more per target beyond the first.", "Strive"),
    "suspend": ("Suspend N and its cost.", None),
    "warp": ("Warp cost.", None),
}

FACE_KEYS: dict[str, Entry] = {
    "back_face": ("The face a transforming permanent turns over to.", "Transforming double-faced cards"),
    "second_face": ("A second spell the same card may be cast as.", H_SECOND_FACE),
    "second_face_zone": ("Where the second face is cast from: `hand` or `graveyard`.", H_SECOND_FACE),
    "prepared_face": ("The spell a prepared permanent may cast a copy of.", "Prepared"),
    "fuse": ("Both halves may be cast as one spell.", "Fuse — the case where the answer is *both* faces"),
    "adventure": ("The second face exiles and the front is cast from exile.", H_SECOND_FACE),
}

RIDER_KEYS: dict[str, Entry] = {
    "exiles_itself": ("Exile this card as it resolves.", '"Exile <this card>." -- a spell that exiles itself'),
    "tucks_itself": ("Put this card Nth from the top of its owner's library as it resolves.", None),
    "uncounterable": ("This spell can't be countered.", H_CANT_COUNTER),
    "rebound": ("Rebound.", "Rebound"),
    "split_second": ("Split second.", None),
    "epic": ("Epic.", "Epic"),
    "miracle": ("Miracle cost.", H_DREDGE),
    "graveyard_cast": ("Castable from a graveyard on its own say-so.", H_CASTING_FROM_GY),
    "graveyard_cost": ("…and what that costs.", H_CASTING_FROM_GY),
    "graveyard_cast_transformed": ("Disturb: cast from the graveyard onto the back face.", "Disturb"),
    "splice_onto": ("What this card may be spliced onto.", "Splice"),
    "melds_with": ("The card this one melds with.", H_MELD),
    "melds_into": ("The permanent the pair melds into.", H_MELD),
    "cant_cast_first_turns": ("Can't be cast during its controller's first N turns of the game.",
                              "Narrowing when a spell may be cast"),
    "toxic": ("Toxic N: the N, beside `toxic` in `keywords`.", "Toxic N"),
    "morph_counter": ("Megamorph: turns face up with a +1/+1 counter, beside `morph`.", H_MORPH),
}

DELAYED_TRIGGER: dict[str, Entry] = {
    "event": ("The trigger event to watch.", None),
    "controller": ("Whose action must it be.", None),
    "condition": ("An intervening if, checked on arming and on resolution.", None),
    "subject": ("Scope the watch to one chosen object; a watch on its own departure looks back (603.10a).",
                "A delayed trigger scoped to one chosen object"),
    "recipient": ("The permanent being hit, for damage events.", "`recipient` — the permanent being hit"),
}

KEYWORDS: dict[str, Entry] = {
    "banding": ("Banding.", "Banding"),
    "choose_a_background": ("Choose a Background (inert; deck-building only).",
                            "The inert keywords — partner, and choose a Background"),
    "compleated": ("Compleated.", "`compleated` — the keyword"),
    "daybound": ("Daybound.", "Daybound and nightbound — one field for the whole table"),
    "deathtouch": ("Deathtouch.", None),
    "defender": ("Defender.", None),
    "double_strike": ("Double strike.", None),
    "dethrone": ("Dethrone.", "Dethrone"),
    "exalted": ("Exalted.", "Exalted"),
    "fear": ("Fear.", "Fear, intimidate, horsemanship, shadow and nonbasic landwalk"),
    "first_strike": ("First strike.", None),
    "flash": ("Flash.", None),
    "flying": ("Flying.", None),
    "forestwalk": ("Forestwalk.", H_LANDWALK),
    "haste": ("Haste.", None),
    "hexproof": ("Hexproof.", None),
    "horsemanship": ("Horsemanship.", "Fear, intimidate, horsemanship, shadow and nonbasic landwalk"),
    "indestructible": ("Indestructible.", None),
    "infect": ("Infect.", "Wither and infect"),
    "intimidate": ("Intimidate.", "Fear, intimidate, horsemanship, shadow and nonbasic landwalk"),
    "islandwalk": ("Islandwalk.", H_LANDWALK),
    "lifelink": ("Lifelink.", None),
    "menace": ("Menace.", None),
    "mountainwalk": ("Mountainwalk.", H_LANDWALK),
    "nightbound": ("Nightbound.", "Daybound and nightbound — one field for the whole table"),
    "nonbasic_landwalk": ("Nonbasic landwalk.", "Fear, intimidate, horsemanship, shadow and nonbasic landwalk"),
    "partner": ("Partner (inert; deck-building only).",
                "The inert keywords — partner, and choose a Background"),
    "phasing": ("Phasing.", 'Phasing — "does not exist", said by not being in a list'),
    "plainswalk": ("Plainswalk.", H_LANDWALK),
    "reach": ("Reach.", None),
    "read_ahead": ("Read ahead; a Saga's starting chapter, chosen as it enters.", "Read ahead"),
    "riot": ("Riot.", "Riot"),
    "shadow": ("Shadow.", "Fear, intimidate, horsemanship, shadow and nonbasic landwalk"),
    "shroud": ("Shroud.", "Shroud, which is the third member of that family"),
    "skulk": ("Skulk.", "Skulk"),
    "swampwalk": ("Swampwalk.", H_LANDWALK),
    "totem_armor": ("Totem armor (umbra armor).", None),
    "toxic": ("Toxic; N is the card-level `toxic` field. Never granted.", "Toxic N"),
    "trample": ("Trample.", None),
    "vigilance": ("Vigilance.", None),
    "wither": ("Wither.", "Wither and infect"),
}

CARD_TYPES: dict[str, Entry] = {
    "Land": ("A land.", None),
    "Creature": ("A creature.", None),
    "Artifact": ("An artifact.", None),
    "Enchantment": ("An enchantment.", None),
    "Instant": ("An instant.", None),
    "Sorcery": ("A sorcery.", None),
    "Planeswalker": ("A planeswalker.", "Planeswalkers"),
    "Battle": ("A battle.", "Battles"),
    "Basic": ("Supertype: basic.", None),
    "Legendary": ("Supertype: legendary.", None),
    "Snow": ("Supertype: snow.", None),
}

DURATIONS: dict[str, Entry] = {
    "this_turn": ("Until this turn ends.", None),
    "your_next_end_step": ("Until your next end step begins.", None),
    "end_of_your_next_turn": ("Until the end of your next turn.", None),
    "later_turns": ("On a later turn only (plot, warp).", "Plot"),
    "while_exiled": ("For as long as it remains exiled.", None),
}

DECISIONS: dict[str, Entry] = {
    "priority": ("A player holds priority: pass, cast, activate, play a land.", None),
    "declare_attackers": ("Declare attackers.", None),
    "declare_blockers": ("Declare blockers.", None),
    "mulligan": ("Keep or mulligan an opening hand.", None),
    "discard_to_hand_size": ("Discard down to maximum hand size at cleanup.", None),
    "choose_objects": ("Choose objects from a pool (targets, searches, sacrifices).", None),
    "choose_mode": ("Choose a mode.", None),
    "choose_x": ("Announce X.", None),
    "may": ("Yes or no.", None),
    "choose_player": ("Choose a player.", None),
    "commander_zone_change": ("Send a commander to the command zone, or let it go.", None),
}

# --------------------------------------------------------------------------
# Families: a title, where the family is defined, the engine's names, and the
# curated map those names are held to.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    title: str  #: the exact `## ` heading in the generated file
    home: str | None  #: heading text of the family's main section in the source docs
    names: tuple[str, ...]  #: from the engine, in display order
    lookup: Callable[[str], Entry | None]  #: name -> (description, heading) or None
    intro: str
    #: The curated map held to ``names`` in the reverse direction, or None for a
    #: family that borrows another's descriptions (a subset cannot be checked
    #: for extras against its parent's map).
    own: dict[str, Entry] | None = None
    #: Extra columns: (header, cell function).
    columns: tuple[tuple[str, Callable[[str], str]], ...] = ()


def _yes(flag: bool) -> str:
    return "yes" if flag else ""


def _event_listeners() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for trigger, event in TRIGGER_EVENTS.items():
        out.setdefault(event, []).append(trigger)
    return out


def families() -> list[Family]:
    """Every family, in the order the reference prints them."""
    statics_lookup = STATICS.get
    listeners = _event_listeners()

    def selector_or_static(name: str) -> Entry | None:
        # The static entry first: `any_of` is in both languages and means a
        # different branch rule in each.
        return STATIC_FILTER_EXTRAS.get(name) or SELECTORS.get(name)

    def condition_or_static(name: str) -> Entry | None:
        return CONDITIONS.get(name) or STATIC_CONDITION_EXTRAS.get(name)

    def op_lookup(name: str) -> Entry | None:
        row = OPS.get(name)
        return None if row is None else (row[1], row[2])

    ops_sorted = tuple(
        sorted(known_ops(), key=lambda n: (OP_GROUPS.index(OPS[n][0]) if n in OPS else 99, n))
    )

    return [
        Family(
            "Effect ops", H_EFFECT_OPS, ops_sorted, op_lookup,
            "Every `op` an `effects` list may name. Each takes a spec dict; the common "
            "fields are `objects` (a selector), `player` (a player spec) and `amount` "
            "(a value expression). *Records `as`* marks the ops that write a binding "
            "when given an `as` name; the loader refuses `as` on any other.",
            own=OPS,  # type: ignore[arg-type]
            columns=(
                ("Group", lambda n: OPS[n][0] if n in OPS else ""),
                ("Records `as`", lambda n: _yes(n in RECORDING_OPS)),
            ),
        ),
        Family(
            "Selectors", H_SELECTORS, tuple(sorted(SELECTOR_KEYS)), SELECTORS.get,
            "Every key a selector (\"which objects\") may carry. All present keys must match.",
            own=SELECTORS,
        ),
        Family(
            "Player specs", H_PLAYER_SPECS, tuple(sorted(PLAYER_SPEC_NAMES)), PLAYER_SPECS.get,
            "The named player specs. The structured forms -- `{\"target\": …}`, "
            "`{\"controller_of_target\": …}`, `{\"controller_of\": …}`, `{\"owner_of\": …}`, "
            "`{\"binding\": …}`, `{\"not\": …}`, `{\"attacked_by\": …}`, "
            "`{\"dealt_combat_damage_by\": …}` -- are described "
            "under the same heading.",
            own=PLAYER_SPECS,
        ),
        Family(
            "Values", H_VALUES, tuple(sorted(VALUE_KEYS)), VALUES.get,
            "Every head a value expression may have, anywhere a number is expected.",
            own=VALUES,
        ),
        Family(
            "Conditions", H_CONDITIONS, tuple(sorted(CONDITION_KEYS)), CONDITIONS.get,
            "Every head a condition may have: an effect's `if`, a trigger's intervening "
            "`condition`, a `may`'s guard.",
            own=CONDITIONS,
        ),
        Family(
            "Trigger events", H_TRIGGERS, tuple(sorted(TRIGGER_EVENTS)), TRIGGER_EVENT_DESCRIPTIONS.get,
            "Every `event` a trigger may name, and the engine event each one listens to.",
            own=TRIGGER_EVENT_DESCRIPTIONS,
            columns=(("Engine event", lambda n: f"`{TRIGGER_EVENTS[n]}`"),),
        ),
        Family(
            "Trigger filters", H_TRIGGERS, tuple(sorted(TRIGGER_FILTER_KEYS)), SELECTORS.get,
            "The subset of the selector language a trigger's `filter` may use. The loader "
            "refuses any other selector key there.",
        ),
        Family(
            "Static effects", H_STATICS, tuple(sorted(STATIC_EFFECTS)), statics_lookup,
            "Every `effect` a `kind: \"static\"` ability may name. *Player-wide* ones take "
            "`affects_player` instead of `affects`; *grantable* ones may be handed to "
            "another permanent by a `grant_ability` static.",
            own=STATICS,
            columns=(
                ("Player-wide", lambda n: _yes(n in PLAYER_WIDE_STATIC_EFFECTS)),
                ("Grantable", lambda n: _yes(n in GRANTABLE_STATIC_EFFECTS)),
            ),
        ),
        Family(
            "Player-wide statics", H_PLAYER_WIDE, tuple(sorted(PLAYER_WIDE_STATIC_EFFECTS)),
            statics_lookup,
            "The static effects that describe the *player* rather than a characteristic, "
            "and so take `affects_player`.",
        ),
        Family(
            "Grantable statics", "`grant_ability` as a static, and where the line now runs",
            tuple(sorted(GRANTABLE_STATIC_EFFECTS)), statics_lookup,
            "The static effects a `grant_ability` static may hand to another permanent.",
        ),
        Family(
            "Cost reduction", H_COST_REDUCTION, tuple(sorted(COST_REDUCTION_KEYS)), COST_REDUCTION.get,
            "The arithmetic heads a card-level `cost_reduction`, a `spell_cost_reduction` "
            "static or an ability's `mana_reduction` may use. The filter beside them is "
            "the static filter plus the keys under *Cost-reduction filter keys* below, "
            "minus the refused ones.",
            own=COST_REDUCTION,
        ),
        Family(
            "Ability costs", H_COSTS, tuple(sorted(CostModel.model_fields)), ABILITY_COSTS.get,
            "Every field an activated ability's `cost` (or a `may`'s `pay`) may carry -- "
            "the fields of `CostModel`.",
            own=ABILITY_COSTS,
        ),
        Family(
            "Card-level costs", H_ALT_PLAY, tuple(CARD_LEVEL_COST_KEYS), CARD_LEVEL_COSTS.get,
            "The alternative and additional costs that live on the *card* rather than "
            "inside an ability's `cost`. Each is a bare mana cost unless noted.",
            own=CARD_LEVEL_COSTS,
        ),
        Family(
            "Keywords", H_KEYWORDS, tuple(sorted(k.value for k in Keyword)), KEYWORDS.get,
            "Every keyword the `keywords` list may carry -- the engine's `Keyword` enum. "
            "Aliases the loader accepts: "
            + ", ".join(f"`{a}` → `{k}`" for a, k in sorted(KEYWORD_ALIASES.items()))
            + ". The full census of printed keywords, shipped or not, is "
            "[keywords.md](keywords.md).",
            own=KEYWORDS,
        ),
        Family(
            "Card types and supertypes", H_SHAPE,
            tuple(t.value for t in CardType) + tuple(s.value for s in Supertype), CARD_TYPES.get,
            "The `types` and `supertypes` a card may print -- the engine's `CardType` and "
            "`Supertype` enums.",
            own=CARD_TYPES,
        ),
        Family(
            "Durations", H_PLAYABLE, tuple(PLAYABLE_DURATIONS), DURATIONS.get,
            "The values `playable` takes on `exile`, `look_at_top` and `grant_playable` -- "
            "how long \"you may play it\" lasts.",
            own=DURATIONS,
        ),
        Family(
            "Decision kinds", None, tuple(d.value for d in DecisionKind), DECISIONS.get,
            "Every question the engine can stop and ask a seat -- the `DecisionKind` enum. "
            "Not card vocabulary: a card never names one, but every `ask_*` an op makes "
            "becomes one of these on the wire.",
            own=DECISIONS,
        ),
        # ---- extra families ------------------------------------------------
        Family(
            "Static filter keys", H_STATICS, tuple(sorted(STATIC_AFFECTS_FILTER_KEYS)),
            selector_or_static,
            "The subset of the selector language a static's `affects` may use -- printed "
            "characteristics only, plus three relations to the static's own source.",
        ),
        Family(
            "Static conditions", H_AS_LONG_AS, tuple(sorted(STATIC_CONDITION_HEADS)),
            condition_or_static,
            "What a static's \"as long as …\" `condition` may ask.",
        ),
        Family(
            "Static values", H_STATIC_MAGNITUDE, tuple(sorted(STATIC_VALUE_KEYS)),
            lambda name: STATIC_VALUE_EXTRAS.get(name) or VALUES.get(name),
            "The subset of the value language a static's magnitude (`power`, `amount`, …) "
            "may use.",
        ),
        Family(
            "Spell filter keys", "What the filter may say", tuple(sorted(SPELL_FILTER_KEYS)),
            SELECTORS.get,
            "The keys an `affects_spells` filter may use.",
        ),
        Family(
            "Cost-reduction filter keys", H_COST_REDUCTION,
            tuple(sorted(COST_REDUCTION_FILTER_KEYS)), COST_REDUCTION_FILTER.get,
            "Keys a cost-reduction filter accepts beyond the static filter. Refused there: "
            + ", ".join(f"`{k}`" for k in sorted(COST_REDUCTION_REFUSED_FILTER_KEYS))
            + " -- a count cannot mean anything by them.",
            own=COST_REDUCTION_FILTER,
        ),
        Family(
            "Mana rider ops", H_MANA_RIDER, tuple(sorted(MANA_RIDER_OPS)), op_lookup,
            "The ops a mana ability may carry beside `add_mana` -- the painland's drawback.",
        ),
        Family(
            "Delayed-trigger keys", H_DELAYED, tuple(sorted(DELAYED_TRIGGER_KEYS)), DELAYED_TRIGGER.get,
            "What a `delayed_trigger`'s `trigger` object may carry.",
            own=DELAYED_TRIGGER,
        ),
        Family(
            "Card-level face keys", H_SHAPE, tuple(CARD_LEVEL_FACE_KEYS), FACE_KEYS.get,
            "The card-level fields that join two printed faces into one card entry.",
            own=FACE_KEYS,
        ),
        Family(
            "Card-level rider keys", H_ALT_PLAY, tuple(CARD_LEVEL_RIDER_KEYS), RIDER_KEYS.get,
            "Things a card says about itself that are neither a price nor a second face.",
            own=RIDER_KEYS,
        ),
        Family(
            "Engine events", H_TRIGGERS,
            tuple(sorted(v for k, v in vars(EventType).items() if k.isupper())),
            lambda n: ("", None),
            "Every `EventType` the engine emits, and which trigger events listen to it. "
            "An event nothing listens to is engine-internal (or waiting for a card).",
            columns=(
                ("Trigger events", lambda n: " ".join(f"`{t}`" for t in listeners.get(n, []))),
            ),
        ),
    ]


# --------------------------------------------------------------------------
# Headings and links.
# --------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def slugify(text: str) -> str:
    """GitHub's anchor rule: lowercase, drop punctuation but `-` and `_`, spaces to `-`."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def headings_in(path: Path) -> dict[str, str]:
    """``slug -> heading text`` for one markdown file, numbering duplicates as GitHub does."""
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not (m := _HEADING.match(line)):
            continue
        text = m.group(2)
        slug = slugify(text)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out[f"{slug}-{n}" if n else slug] = text
    return out


def heading_index(docs: Path = DOCS) -> dict[str, tuple[str, str]]:
    """``slug -> (file, heading text)`` over every source doc that exists.

    The first file wins a slug both define, in ``SOURCE_DOCS`` order.
    """
    index: dict[str, tuple[str, str]] = {}
    for name in SOURCE_DOCS:
        path = docs / name
        if not path.exists():
            continue
        for slug, text in headings_in(path).items():
            index.setdefault(slug, (name, text))
    return index


def resolve(heading: str, index: dict[str, tuple[str, str]]) -> str | None:
    """A markdown link to ``heading`` in whichever source doc holds it, else None."""
    slug = slugify(heading)
    found = index.get(slug)
    if found is None:
        return None
    file, text = found
    label = text.replace("`", "").replace("*", "").replace("|", "\\|")
    return f"[{label}]({file}#{slug})"


# --------------------------------------------------------------------------
# Generation.
# --------------------------------------------------------------------------


def coverage_problems(fam: Family) -> list[str]:
    """The names the engine has that the map lacks, and the reverse."""
    problems: list[str] = []
    missing = [n for n in fam.names if fam.lookup(n) is None]
    if missing:
        problems.append(
            f"{fam.title}: the engine has {missing} but the script has no description for "
            f"them -- add them to the map in scripts/gen_dsl_reference.py"
        )
    if fam.own is not None:
        extra = sorted(set(fam.own) - set(fam.names))
        if extra:
            problems.append(
                f"{fam.title}: the script describes {extra} but the engine no longer has "
                f"them -- remove them from scripts/gen_dsl_reference.py"
            )
    return problems


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _table(header: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    head = list(header)
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out.extend("| " + " | ".join(_cell(c) for c in row) + " |" for row in rows)
    return out


def _op_keys_section(index: dict[str, tuple[str, str]]) -> list[str]:
    """Where the per-op key lists live, and why they are not reproduced here.

    ``packet._op_options`` unions the keys an op's source reads with the keys the
    shipped pool writes, so a table of them would change with every card pull
    request; the authoring packet already hands that list to a worker at
    authoring time, which is the moment it is needed.
    """
    home = resolve(H_EFFECT_OPS, index) or "Effect ops"
    return [
        "## Effect op keys",
        "",
        f"The keys each op reads beside its `op` name are not tabulated here: that list "
        f"is derived from the op's source *and* from what the shipped pool writes, so it "
        f"would move with every card. `cards.authoring.packet.reference()` builds it for "
        f"the authoring packet, which is where a worker reads it. See {home}.",
        "",
    ]


def generate(docs: Path = DOCS) -> tuple[str, list[str], list[str]]:
    """The reference text, the coverage errors, and the unresolved-heading warnings.

    Errors mean the curated maps and the engine disagree. Warnings mean a curated
    heading was found in none of ``SOURCE_DOCS``; ``--check`` promotes them.
    """
    index = heading_index(docs)
    errors: list[str] = []
    warnings: list[str] = []
    fams = families()

    lines = [
        "<!-- GENERATED by scripts/gen_dsl_reference.py from the engine's own registries.",
        "     Do not hand-edit: change the maps in that script and run",
        "         python scripts/gen_dsl_reference.py --write",
        "     `--check` and tests/cards/test_dsl_reference.py fail when this file or the",
        "     script's descriptions drift from the engine. -->",
        "",
        "# Card DSL reference",
        "",
        "The vocabulary of the card DSL, one table per family, with the names read off "
        "the engine so the counts cannot go stale. The prose that explains each item "
        "lives in [card-dsl.md](card-dsl.md)"
        + (" and [card-dsl-cookbook.md](card-dsl-cookbook.md)" if (docs / SOURCE_DOCS[1]).exists() else "")
        + "; the last column links to the heading that defines it, or to the family's "
        "main section when it has no heading of its own.",
        "",
        "| Family | Count |",
        "|---|---|",
    ]
    lines.extend(f"| [{f.title}](#{slugify(f.title)}) | {len(f.names)} |" for f in fams)
    lines.append("")

    for fam in fams:
        errors.extend(coverage_problems(fam))
        home_link = resolve(fam.home, index) if fam.home else None
        if fam.home and home_link is None:
            warnings.append(f"{fam.title}: main-section heading {fam.home!r} is in no source doc")
        lines.append(f"## {fam.title}")
        lines.append("")
        intro = fam.intro
        if home_link:
            intro += f" Defined under {home_link}."
        lines.append(intro)
        lines.append("")
        rows = []
        for name in fam.names:
            entry = fam.lookup(name) or ("", None)
            description, heading = entry
            link = ""
            if heading:
                link = resolve(heading, index) or ""
                if not link:
                    warnings.append(
                        f"{fam.title}: {name!r} links to heading {heading!r}, which is in "
                        f"no source doc"
                    )
            if not link and home_link:
                link = home_link
            row = [f"`{name}`"]
            row.extend(fn(name) for _, fn in fam.columns)
            row.extend([description, link or "—"])
            rows.append(row)
        header = ["Name", *(h for h, _ in fam.columns), "Description", "Defined in"]
        lines.extend(_table(header, rows))
        lines.append("")

    lines.extend(_op_keys_section(index))
    text = "\n".join(lines).rstrip("\n") + "\n"
    return text, errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help=f"rewrite {OUTPUT.relative_to(ROOT)}")
    mode.add_argument(
        "--check", action="store_true",
        help="exit 1 if the committed file is stale, a map disagrees with the engine, "
        "or a curated heading is missing",
    )
    args = parser.parse_args(argv)

    text, errors, warnings = generate()
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    for w in warnings:
        print(f"{'error' if args.check else 'warning'}: {w}", file=sys.stderr)

    if args.write:
        if errors:
            return 1
        OUTPUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0

    status = 1 if errors or warnings else 0
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if current != text:
        status = 1
        diff = list(
            difflib.unified_diff(
                current.splitlines(), text.splitlines(),
                fromfile=str(OUTPUT.relative_to(ROOT)), tofile="generated", lineterm="", n=0,
            )
        )
        changed = sum(1 for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")))
        print(
            f"error: {OUTPUT.relative_to(ROOT)} is stale ({changed} lines differ); "
            f"run `python scripts/gen_dsl_reference.py --write`",
            file=sys.stderr,
        )
        for d in diff[:40]:
            print(f"  {d}", file=sys.stderr)
        if len(diff) > 40:
            print(f"  … {len(diff) - 40} more", file=sys.stderr)
    if status == 0:
        print("ok: docs/card-dsl-reference.md matches the engine")
    return status


if __name__ == "__main__":
    sys.exit(main())
