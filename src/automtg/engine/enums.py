"""Enumerations shared across the engine.

``Step`` is an ``IntEnum`` so turn progression is a simple ordered walk.
Everything else is a ``str`` enum so serialization to JSON is free.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class Zone(str, Enum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    STACK = "stack"
    COMMAND = "command"


#: Zones whose contents are ordered and hidden from other players.
HIDDEN_ZONES = frozenset({Zone.LIBRARY, Zone.HAND})

#: Zones that belong to a specific player (as opposed to the shared battlefield/stack).
PLAYER_ZONES = frozenset(
    {Zone.LIBRARY, Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND}
)


class Phase(str, Enum):
    BEGINNING = "beginning"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT = "combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    ENDING = "ending"


class Step(IntEnum):
    """The 13 steps of a turn, in order."""

    UNTAP = 0
    UPKEEP = 1
    DRAW = 2
    PRECOMBAT_MAIN = 3
    BEGIN_COMBAT = 4
    DECLARE_ATTACKERS = 5
    DECLARE_BLOCKERS = 6
    FIRST_STRIKE_DAMAGE = 7
    COMBAT_DAMAGE = 8
    END_OF_COMBAT = 9
    POSTCOMBAT_MAIN = 10
    END_STEP = 11
    CLEANUP = 12


STEP_PHASE: dict[Step, Phase] = {
    Step.UNTAP: Phase.BEGINNING,
    Step.UPKEEP: Phase.BEGINNING,
    Step.DRAW: Phase.BEGINNING,
    Step.PRECOMBAT_MAIN: Phase.PRECOMBAT_MAIN,
    Step.BEGIN_COMBAT: Phase.COMBAT,
    Step.DECLARE_ATTACKERS: Phase.COMBAT,
    Step.DECLARE_BLOCKERS: Phase.COMBAT,
    Step.FIRST_STRIKE_DAMAGE: Phase.COMBAT,
    Step.COMBAT_DAMAGE: Phase.COMBAT,
    Step.END_OF_COMBAT: Phase.COMBAT,
    Step.POSTCOMBAT_MAIN: Phase.POSTCOMBAT_MAIN,
    Step.END_STEP: Phase.ENDING,
    Step.CLEANUP: Phase.ENDING,
}

MAIN_STEPS = frozenset({Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN})

#: Steps in which no player receives priority under normal circumstances.
#: (Cleanup grants priority only when a trigger fired or a discard was required.)
NO_PRIORITY_STEPS = frozenset({Step.UNTAP, Step.CLEANUP})


class Color(str, Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"


COLOR_ORDER: tuple[Color, ...] = (
    Color.WHITE,
    Color.BLUE,
    Color.BLACK,
    Color.RED,
    Color.GREEN,
)

#: Colorless is not a colour; it is tracked alongside colours in mana pools only.
COLORLESS = "C"


class CardType(str, Enum):
    LAND = "Land"
    CREATURE = "Creature"
    ARTIFACT = "Artifact"
    ENCHANTMENT = "Enchantment"
    INSTANT = "Instant"
    SORCERY = "Sorcery"
    PLANESWALKER = "Planeswalker"
    BATTLE = "Battle"


PERMANENT_TYPES = frozenset(
    {
        CardType.LAND,
        CardType.CREATURE,
        CardType.ARTIFACT,
        CardType.ENCHANTMENT,
        CardType.PLANESWALKER,
        CardType.BATTLE,
    }
)

SPELL_ONLY_TYPES = frozenset({CardType.INSTANT, CardType.SORCERY})


class Supertype(str, Enum):
    BASIC = "Basic"
    LEGENDARY = "Legendary"
    SNOW = "Snow"


class Keyword(str, Enum):
    """Keyword abilities the engine actually implements."""

    FLYING = "flying"
    REACH = "reach"
    TRAMPLE = "trample"
    DEATHTOUCH = "deathtouch"
    LIFELINK = "lifelink"
    VIGILANCE = "vigilance"
    HASTE = "haste"
    MENACE = "menace"
    #: Skulk (702.72).  "This creature can't be blocked by creatures with
    #: greater power."  A keyword rather than a `block_restriction` static for
    #: the same reason landwalk is: it takes no parameter, the whole content of
    #: the quality is the comparison itself.  And it *could* not be one -- a
    #: static's `blockers` filter reads printed characteristics by design, while
    #: skulk must read derived power on both sides, so an anthem, a pump spell
    #: or a +1/+1 counter on either creature changes who may block.
    SKULK = "skulk"
    #: Fear (702.36), intimidate (702.13), horsemanship (702.32) and shadow
    #: (702.28).  Four more evasions in the shape skulk opened: the condition is
    #: a quality of the *would-be blocker*, or a relation between the two
    #: creatures, and it is asked of **derived** characteristics when blockers
    #: are declared.  None takes a parameter -- "artifact and/or black" and
    #: "shares a color with it" are the whole content of the quality, not an
    #: argument to it -- so there is nothing for a static to carry, and a
    #: `block_restriction`'s `blockers` filter could not say them anyway: it is
    #: a prohibition and these are exemptions, and it reads printed
    #: characteristics while a creature made black may block a fear creature.
    FEAR = "fear"
    INTIMIDATE = "intimidate"
    HORSEMANSHIP = "horsemanship"
    #: Shadow is the only evasion that cuts both ways -- "can block or be
    #: blocked by only creatures with shadow" -- which is why it is a keyword
    #: read symmetrically rather than a restriction hung on the attacker.
    SHADOW = "shadow"
    FIRST_STRIKE = "first_strike"
    DOUBLE_STRIKE = "double_strike"
    DEFENDER = "defender"
    HEXPROOF = "hexproof"
    #: Rule 702.18a.  Not hexproof with a wider net: hexproof stops opponents
    #: and shroud stops *everyone*, so the controller cannot target their own
    #: creature either.  Read only by :func:`targeting.can_be_targeted` -- it is
    #: a target rule and nothing else, unlike protection, which four rules read.
    SHROUD = "shroud"
    #: Landwalk (702.14).  Five keywords rather than one parameterised
    #: ability because `Keyword` is a bare string and the whole point of the
    #: quality is *which* land type: `LANDWALK_SUBTYPE` maps each to the
    #: subtype the defending player must control.  Read only by
    #: `combat.can_block`, and unlike protection it is one rule.
    PLAINSWALK = "plainswalk"
    ISLANDWALK = "islandwalk"
    SWAMPWALK = "swampwalk"
    MOUNTAINWALK = "mountainwalk"
    FORESTWALK = "forestwalk"
    #: Nonbasic landwalk, the same rule with the test inverted: a *supertype*
    #: the land must lack rather than a subtype it must have.  So it cannot be a
    #: sixth `LANDWALK_SUBTYPE` row, and it is a separate keyword for the reason
    #: the other five are separate from each other -- `Keyword` is a bare string.
    NONBASIC_LANDWALK = "nonbasic_landwalk"
    INDESTRUCTIBLE = "indestructible"
    #: Wither (702.90b) and infect (702.90c).  Both change the *form* damage
    #: takes, and both are keywords rather than `replacements` entries for the
    #: reason deathtouch and lifelink are: the whitelist covers what happens as
    #: a permanent **enters the battlefield**, and this is a fact about damage,
    #: read by `damage_permanent` at the one point every damage source passes
    #: through.  Neither takes a parameter -- "-1/-1 counters instead" is the
    #: whole content of the quality.
    #:
    #: Infect is wither plus poison, and is a separate keyword rather than a
    #: pair because a creature has one or the other: 702.90c is written as its
    #: own ability and a card carrying both would double neither half.
    WITHER = "wither"
    INFECT = "infect"
    #: Totem armor (702.88a).  A keyword on the *Aura*: "if enchanted permanent
    #: would be destroyed, instead remove all damage from it and destroy this
    #: Aura."  Not a `replacements` entry, because that whitelist is about a
    #: permanent entering the battlefield and this is the moment one leaves --
    #: and not parameterised, because "destroy this Aura instead" is the whole
    #: content of the quality.  Read by `zones.destroy`, which every route to a
    #: destruction already goes through.
    TOTEM_ARMOR = "totem_armor"
    FLASH = "flash"
    #: Phasing (702.26a): "a static ability that modifies the untap step of the
    #: permanent's controller". A `Keyword` rather than a static, for
    #: horsemanship's reason -- it takes no parameter, and it is read by the
    #: *turn*, which cannot filter on a static.
    #:
    #: A phased-out permanent "is treated as though it does not exist"
    #: (702.26c), which the engine says by taking it out of `state.battlefield`
    #: while leaving it in `state.objects` -- the same nowhere a card on the
    #: stack and a card under a merged permanent already live. Every walk of the
    #: battlefield therefore misses it with no test of its own.
    PHASING = "phasing"
    #: Daybound / nightbound (702.145, 702.146). A pair of `Keyword`s on the two
    #: faces of one transforming card, and the pair is the point: daybound is
    #: printed on the front and nightbound on the back, so which one `chars`
    #: reports is already the answer to "which way round is this permanent".
    #:
    #: What they modify is the **game**, not the permanent -- day and night are
    #: a designation the whole table shares (`GameState.day_night`), which is
    #: why the switching lives in `turn` beside phasing rather than in a card.
    #: Banding (702.21). Two rules sharing a word: attacking as a band, and
    #: **who chooses the damage assignment order** of the creature on the other
    #: side. The engine already has damage assignment order as a concept -- it
    #: simply sorts it by effective toughness and asks nobody -- so banding is
    #: exactly "this one is asked, and the other player is who is asked".
    BANDING = "banding"
    DAYBOUND = "daybound"
    NIGHTBOUND = "nightbound"
    #: Deck construction only -- "you can have two commanders if both have
    #: partner".  Listed here, and inert on purpose: the engine is handed a
    #: finished deck, so there is no game rule to implement.  It exists so a
    #: card carrying the word can say so instead of leaving the line unaccounted
    #: for, which the authoring verifier's residual gate would rightly reject.
    PARTNER = "partner"
    #: Deck construction only, and the second of its kind -- "you can have a
    #: Background as a second commander" (702.124).  Inert for partner's exact
    #: reason: the engine is handed a finished deck, so the word has nothing
    #: left to do once a game starts, and it exists so a card printing the line
    #: can claim it instead of leaving the authoring verifier's residual gate an
    #: unaccounted sentence.
    #:
    #: Deliberately **not** folded onto `PARTNER`, which is the near miss: the
    #: two rules build different decks.  A partner pair is two commanders that
    #: both print the word; this is one commander plus a Background enchantment,
    #: which prints nothing at all.  One word meaning both would let a deck be
    #: validated against the wrong rule the moment `validate_deck` grows an
    #: opinion about either.
    CHOOSE_A_BACKGROUND = "choose_a_background"
    #: Riot (702.113): "this creature enters with your choice of a +1/+1
    #: counter or haste."  The first keyword whose whole content is a **614.1c
    #: replacement**, and it is a `Keyword` rather than a `ReplacementModel`
    #: entry for the one reason that family could not carry it: every
    #: `self_enters*` event is printed on the permanent it modifies, and riot's
    #: commonest printing -- Rhythm of the Wild's "nontoken creatures you
    #: control **have riot**" -- is one permanent handing the replacement to
    #: other creatures.  A replacement is not grantable; a keyword is, through
    #: the `grant_keyword` static that already exists, so writing riot as a
    #: keyword is what makes the granted form sayable at all.
    #:
    #: It takes no parameter -- "a +1/+1 counter or haste" is the whole of the
    #: quality -- which is the routing rule in `docs/keywords.md`, and it is
    #: read at exactly one point: `zones.offer_riot_choice`, called by every
    #: arrival path that can stop to ask.  Once the permanent is on the
    #: battlefield the keyword is spent and reads as a characteristic only,
    #: which is why it is **not** in `INERT_KEYWORDS`: it does something, and it
    #: does it during a zone change rather than on the board.
    RIOT = "riot"
    #: Compleated (702.150a): "If this permanent would enter with one or more
    #: loyalty counters on it, it enters with two fewer loyalty counters on it
    #: for each Phyrexian mana symbol life was paid for as it was cast."  A
    #: 614.1c replacement on the arrival, read in `zones._enter_battlefield`
    #: beside the starting-loyalty replacement it modifies, off
    #: `GameObject.cast_phyrexian_life` -- which `game._cast` writes at the one
    #: moment the answer exists, and which only an arrival that *was* this cast
    #: (`entered_by_cast`) may read.
    COMPLEATED = "compleated"


LANDWALK_SUBTYPE = {
    Keyword.PLAINSWALK.value: "Plains",
    Keyword.ISLANDWALK.value: "Island",
    Keyword.SWAMPWALK.value: "Swamp",
    Keyword.MOUNTAINWALK.value: "Mountain",
    Keyword.FORESTWALK.value: "Forest",
}

EVASION_KEYWORDS = frozenset(
    {
        Keyword.FLYING,
        Keyword.MENACE,
        Keyword.SKULK,
        Keyword.FEAR,
        Keyword.INTIMIDATE,
        Keyword.HORSEMANSHIP,
        Keyword.SHADOW,
        Keyword.NONBASIC_LANDWALK,
    }
    | {Keyword(k) for k in LANDWALK_SUBTYPE}
)

#: Keywords with no in-game effect, kept so a card can represent its own text.
#: `docs/rules-coverage.md` names them; anything added here must genuinely do
#: nothing during a game, or it belongs in the engine instead.
INERT_KEYWORDS = frozenset({Keyword.PARTNER, Keyword.CHOOSE_A_BACKGROUND})

#: Counter kinds that are **keyword counters** (122.1c): "a keyword counter is a
#: counter with a keyword ability's name, and a permanent with one has that
#: keyword ability".
#:
#: Derived from `Keyword` rather than listed, because the rule is the derivation
#: -- 122.1c names no subset, so any keyword the engine implements is a keyword
#: counter the moment a card asks for one. A hand-written list would be a second
#: place to forget: the next card printing a *menace* counter would place an
#: inert tally and load clean, which is the failure the authoring gates exist to
#: refuse.
#:
#: `INERT_KEYWORDS` is excluded for the reason it exists. Partner and choose a
#: Background are deck-construction words and the engine is handed a finished
#: deck, so neither counter could mean anything mid-game; a counter kind that
#: grants nothing is the inert tally in a costume.
#:
#: Read by `characteristics._compute` (the keyword-grant layer) and by
#: `cards.loader` (which refuses a near-miss spelling of one).
KEYWORD_COUNTERS = frozenset(k.value for k in Keyword) - {k.value for k in INERT_KEYWORDS}


class AbilityKind(str, Enum):
    ACTIVATED = "activated"
    TRIGGERED = "triggered"
    STATIC = "static"
    #: A Saga's **chapter ability** (714.1b).  A fourth kind rather than a
    #: `triggered` ability with an exotic event, because the printed line "I --
    #: …" is not a sentence any trigger vocabulary can spell: there is no word
    #: for *when* in it at all, and the whole of the timing comes from the
    #: rules.
    #:
    #: It is still a triggered ability where it counts -- 714.1b says so out
    #: loud -- so `Ability.is_triggered` answers True for it and the entire
    #: existing pipeline (matching, APNAP queueing, the stack, targets chosen as
    #: it goes on) carries it with no second implementation. What the new kind
    #: buys is the three things a `triggered` ability could not say: the chapter
    #: *number*, which the loader turns into the trigger's filter; the
    #: card-level `final_chapter` derived from those numbers; and a load-time
    #: refusal of a chapter ability on a card that is not a Saga.
    CHAPTER = "chapter"
    #: A **reflexive triggered ability** (603.11) -- "…exile each opponent's
    #: graveyard. **When you do**, choose up to one target creature card exiled
    #: this way." A fifth kind for the reason `CHAPTER` is a fourth: the printed
    #: line has no *event* in it that any trigger vocabulary could name. "When
    #: you do" means "when the instruction just above this one is carried out",
    #: which is not something the board can be watched for -- the effect that
    #: causes it has to say so itself, and the `reflexive_trigger` op is that
    #: saying.
    #:
    #: So `Ability.is_triggered` is deliberately **False** here and the ability
    #: carries no `TriggerSpec`: nothing must ever match it off an event, or a
    #: card would fire it on its own. Everything downstream of the queue is
    #: shared -- APNAP order, the stack, and targets chosen as it is put there,
    #: which is exactly what 603.11 asks for and the whole reason this is an
    #: ability on the card rather than more effects inside the spell.
    REFLEXIVE = "reflexive"
    #: **A place held for an ability this permanent does not have right now** --
    #: a Class's level-3 anthem on a Class that is level 1 (716.2b-c). Never
    #: written in a card file and never compiled by the loader: only
    #: `characteristics.abilities_of` produces one, standing in for the printed
    #: ability at the printed ability's position.
    #:
    #: A stand-in rather than a gap in the list, because positions are addresses.
    #: `Action.ability_index`, `StackItem.ability_index`, the per-turn trigger cap
    #: and the once-each-turn ledger all name an ability by where it sits, and
    #: `stack.ability_of` resolves an item against the *printed* list. Dropping a
    #: level-3 ability from the middle would renumber everything after it, and a
    #: "{3}{W}: Level 3" activated at level 2 would resolve as whatever printed
    #: ability happened to sit at its old number. So the ability keeps its seat
    #: and answers False to `is_activated`, `is_triggered` and `is_static`, which
    #: every reader already asks before doing anything with an ability.
    LATENT = "latent"


class ActionKind(str, Enum):
    PASS = "pass"
    PLAY_LAND = "play_land"
    CAST = "cast"
    #: "Rather than cast this card from your hand, you may pay {G} and exile it
    #: with two time counters on it."  A special action, not a cast: nothing
    #: goes on the stack and nothing can respond to it.
    SUSPEND = "suspend"
    ACTIVATE = "activate"
    ADD_ATTACKER = "add_attacker"
    ADD_BLOCKER = "add_blocker"
    FINISH_DECLARATION = "finish_declaration"
    CHOOSE = "choose"
    YES = "yes"
    NO = "no"
    MULLIGAN = "mulligan"
    KEEP = "keep"


class DecisionKind(str, Enum):
    PRIORITY = "priority"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    MULLIGAN = "mulligan"
    DISCARD_TO_HAND_SIZE = "discard_to_hand_size"
    CHOOSE_OBJECTS = "choose_objects"
    CHOOSE_MODE = "choose_mode"
    CHOOSE_X = "choose_x"
    MAY = "may"
    CHOOSE_PLAYER = "choose_player"
    COMMANDER_ZONE_CHANGE = "commander_zone_change"


class LossReason(str, Enum):
    LIFE = "life"
    EMPTY_LIBRARY = "empty_library"
    COMMANDER_DAMAGE = "commander_damage"
    POISON = "poison"
    CONCEDE = "concede"
    #: Somebody else's card said "you win the game" (104.2a). Its own reason for
    #: the argument POISON has: this seat did not run out of life, did not deck
    #: itself and did not concede, and the frontend prints the reason to them.
    OPPONENT_WON = "opponent_won"
    #: A card said "that player loses the game" (104.3a) -- Vraska the Unseen's
    #: Assassins, the Pact cycle's unpaid upkeep. Not OPPONENT_WON: nobody won,
    #: and in a pod the others play on.
    LOST_BY_EFFECT = "lost_by_effect"


#: Which card type each subtype belongs to -- 205.3, as one flat table.
#:
#: Read by `characteristics` when a `set_types` static replaces a permanent's
#: card types: 205.1b and 613.1d say the subtypes of a type it no longer has go
#: with it, so an Imprisoned in the Moon on a Goblin Warchief is a Land, not a
#: "Land - Goblin" that a Goblin anthem still pumps.
#:
#: **Creature types are the default and are deliberately absent.** There are 321
#: of them against 149 of everything else, the list grows with every set, and
#: a missing entry has to fail in the safe direction: an unknown subtype read as
#: a creature type is dropped when Creature is, which is right for every new
#: creature type and wrong only for a new artifact or enchantment type -- which
#: would be dropped from a permanent that stopped being a creature it never was.
#:
#: Derived from `data/catalog/cards.sqlite` over every printed type line whose
#: left half names exactly one card type (Kindred faces excluded -- "Tribal
#: Instant - Goblin" would file Goblin under Instant). That derivation is
#: reproduced as a test, so a catalog refresh that adds a type says so.
SUBTYPE_CLASS: dict[str, str] = {
    "Adventure": "Spell",
    "Ajani": "Planeswalker",
    "Aminatou": "Planeswalker",
    "Angrath": "Planeswalker",
    "Arcane": "Spell",
    "Arlinn": "Planeswalker",
    "Arzakon": "Planeswalker",
    "Ashiok": "Planeswalker",
    "Aura": "Enchantment",
    "Background": "Enchantment",
    "Bahamut": "Planeswalker",
    "Basri": "Planeswalker",
    "Blood": "Artifact",
    "Bobblehead": "Artifact",
    "Bolas": "Planeswalker",
    "Book": "Artifact",
    "Calix": "Planeswalker",
    "Cartouche": "Enchantment",
    "Case": "Enchantment",
    "Cave": "Land",
    "Chandra": "Planeswalker",
    "Class": "Enchantment",
    "Clue": "Artifact",
    "Comet": "Planeswalker",
    "Curse": "Enchantment",
    "Dack": "Planeswalker",
    "Dakkon": "Planeswalker",
    "Daretti": "Planeswalker",
    "Davriel": "Planeswalker",
    "Dellian": "Planeswalker",
    "Desert": "Land",
    "Dihada": "Planeswalker",
    "Domri": "Planeswalker",
    "Dovin": "Planeswalker",
    "Dyfed": "Planeswalker",
    "Ellywick": "Planeswalker",
    "Elminster": "Planeswalker",
    "Elspeth": "Planeswalker",
    "Equipment": "Artifact",
    "Estrid": "Planeswalker",
    "Feroz": "Planeswalker",
    "Food": "Artifact",
    "Forest": "Land",
    "Fortification": "Artifact",
    "Freyalise": "Planeswalker",
    "Garruk": "Planeswalker",
    "Gate": "Land",
    "Gideon": "Planeswalker",
    "Gold": "Artifact",
    "Greensleeves": "Planeswalker",
    "Grist": "Planeswalker",
    "Guff": "Planeswalker",
    "Heartwood": "Artifact",
    "Huatli": "Planeswalker",
    "Incubator": "Artifact",
    "Infinity": "Artifact",
    "Island": "Land",
    "Jace": "Planeswalker",
    "Jared": "Planeswalker",
    "Jaya": "Planeswalker",
    "Jeska": "Planeswalker",
    "Junk": "Artifact",
    "Kaito": "Planeswalker",
    "Karn": "Planeswalker",
    "Kasmina": "Planeswalker",
    "Kaya": "Planeswalker",
    "Kiora": "Planeswalker",
    "Koth": "Planeswalker",
    "Lair": "Land",
    "Lander": "Artifact",
    "Lesson": "Spell",
    "Liliana": "Planeswalker",
    "Locus": "Land",
    "Lolth": "Planeswalker",
    "Lukka": "Planeswalker",
    "Map": "Artifact",
    "Mine": "Land",
    "Minsc": "Planeswalker",
    "Mordenkainen": "Planeswalker",
    "Mountain": "Land",
    "Mutagen": "Artifact",
    "Nahiri": "Planeswalker",
    "Narset": "Planeswalker",
    "Niko": "Planeswalker",
    "Nissa": "Planeswalker",
    "Nixilis": "Planeswalker",
    "Oko": "Planeswalker",
    "Omen": "Spell",
    "Omenpath": "Land",
    "Plains": "Land",
    "Plan": "Enchantment",
    "Planet": "Land",
    "Power-Plant": "Land",
    "Powerstone": "Artifact",
    "Quest": "Enchantment",
    "Quintorius": "Planeswalker",
    "Ral": "Planeswalker",
    "Realm": "Enchantment",
    "Role": "Enchantment",
    "Room": "Enchantment",
    "Rowan": "Planeswalker",
    "Rune": "Enchantment",
    "Saga": "Enchantment",
    "Saheeli": "Planeswalker",
    "Samut": "Planeswalker",
    "Sarkhan": "Planeswalker",
    "Serra": "Planeswalker",
    "Shard": "Enchantment",
    "Shrine": "Enchantment",
    "Siege": "Battle",
    "Sifa": "Planeswalker",
    "Sivitri": "Planeswalker",
    "Sorin": "Planeswalker",
    "Spacecraft": "Artifact",
    "Sphere": "Land",
    "Stone": "Artifact",
    "Swamp": "Land",
    "Szat": "Planeswalker",
    "Tamiyo": "Planeswalker",
    "Tasha": "Planeswalker",
    "Teferi": "Planeswalker",
    "Teyo": "Planeswalker",
    "Tezzeret": "Planeswalker",
    "Thomil": "Planeswalker",
    "Tibalt": "Planeswalker",
    "Tower": "Land",
    "Town": "Land",
    "Trap": "Spell",
    "Treasure": "Artifact",
    "Tyvar": "Planeswalker",
    "Ugin": "Planeswalker",
    "Ulamog's": "Land",
    "Undercity": "Dungeon",
    "Urza": "Planeswalker",
    "Urza's": "Land",
    "Vehicle": "Artifact",
    "Venser": "Planeswalker",
    "Vibranium": "Artifact",
    "Vivien": "Planeswalker",
    "Vraska": "Planeswalker",
    "Vronos": "Planeswalker",
    "Will": "Planeswalker",
    "Windgrace": "Planeswalker",
    "Worzel": "Planeswalker",
    "Wrenn": "Planeswalker",
    "Xenagos": "Planeswalker",
    "Yanggu": "Planeswalker",
    "Yanling": "Planeswalker",
    "You": "Planeswalker",
    "Zariel": "Planeswalker",
}
