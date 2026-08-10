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
    FIRST_STRIKE = "first_strike"
    DOUBLE_STRIKE = "double_strike"
    DEFENDER = "defender"
    HEXPROOF = "hexproof"
    INDESTRUCTIBLE = "indestructible"
    FLASH = "flash"
    #: Deck construction only -- "you can have two commanders if both have
    #: partner".  Listed here, and inert on purpose: the engine is handed a
    #: finished deck, so there is no game rule to implement.  It exists so a
    #: card carrying the word can say so instead of leaving the line unaccounted
    #: for, which the authoring verifier's residual gate would rightly reject.
    PARTNER = "partner"


EVASION_KEYWORDS = frozenset({Keyword.FLYING, Keyword.MENACE})

#: Keywords with no in-game effect, kept so a card can represent its own text.
#: `docs/rules-coverage.md` names them; anything added here must genuinely do
#: nothing during a game, or it belongs in the engine instead.
INERT_KEYWORDS = frozenset({Keyword.PARTNER})


class AbilityKind(str, Enum):
    ACTIVATED = "activated"
    TRIGGERED = "triggered"
    STATIC = "static"


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
    MAY = "may"
    CHOOSE_PLAYER = "choose_player"
    COMMANDER_ZONE_CHANGE = "commander_zone_change"


class LossReason(str, Enum):
    LIFE = "life"
    EMPTY_LIBRARY = "empty_library"
    COMMANDER_DAMAGE = "commander_damage"
    CONCEDE = "concede"
