"""Per-player state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import LossReason, Zone
from .mana import ManaPool

#: Commander starting life total.
STARTING_LIFE = 40
#: Commander damage from a single commander that causes a loss.
COMMANDER_DAMAGE_THRESHOLD = 21
#: Maximum hand size at cleanup.
MAX_HAND_SIZE = 7


@dataclass
class PlayerState:
    """Everything private to one seat.

    Zones are ordered lists of object ids.  Library index 0 is the *top* of the
    library, which is what every "look at the top card" effect means.
    """

    pid: int
    name: str = ""
    deck_id: str = ""
    life: int = STARTING_LIFE

    library: list[int] = field(default_factory=list)
    hand: list[int] = field(default_factory=list)
    graveyard: list[int] = field(default_factory=list)
    exile: list[int] = field(default_factory=list)
    command: list[int] = field(default_factory=list)

    mana_pool: ManaPool = field(default_factory=ManaPool)

    lands_played: int = 0
    extra_land_drops: int = 0

    #: commander oid -> number of times it has been cast from the command zone
    commander_tax: dict[int, int] = field(default_factory=dict)
    #: source player id -> combat damage their commander has dealt to me
    commander_damage_taken: dict[int, int] = field(default_factory=dict)
    #: the oids this player owns as commanders
    commanders: list[int] = field(default_factory=list)

    has_lost: bool = False
    loss_reason: LossReason | None = None
    #: Set when a draw was attempted with an empty library; a state-based action
    #: then makes this player lose (rule 104.3c) rather than losing immediately.
    attempted_draw_from_empty: bool = False

    #: The city's blessing (rules 700.6, 702.131). Once you have it you have it
    #: **for the rest of the game**: it survives the permanents leaving, it
    #: survives the Ascend card itself leaving, and every card you control reads
    #: the same flag -- so a second Ascend card printed later sees the blessing
    #: an earlier one granted.
    #:
    #: The first genuinely per-player designation in the engine, and it is why
    #: this is player state rather than something on an object: ``monstrous`` is
    #: the closest existing one-way flag and lives on a `GameObject`, so it is
    #: cleared by `reset_permanent_state` on any zone change and cannot be
    #: shared between two cards.
    has_city_s_blessing: bool = False

    mulligans_taken: int = 0
    has_kept_hand: bool = False

    #: Skip priority windows where this player has nothing worth responding to.
    #: Off by default so the RL environment and the golden tests still see every
    #: window; the HTTP session turns it on for human seats only.
    auto_pass: bool = False
    #: Overrides ``auto_pass``: stop at every window, the way MTGO's full control
    #: does.  A human who wants an opponent's end step back asks for this.
    full_control: bool = False
    #: Offer this player's *tap-only* mana abilities as actions, so they choose
    #: which land to tap and which colour a dual makes instead of the payment
    #: solver deciding.  Off by default, which is what keeps the RL action space
    #: and every golden test exactly as they were: see
    #: `docs/rules-coverage.md`'s "Automatic mana payment" row.
    manual_mana: bool = False
    #: Offer a permanent's tap-only mana ability whenever that permanent offers
    #: *something else* too.  Narrower than ``manual_mana``: a Forest or a Sol
    #: Ring still belongs to the solver alone, because there is nothing to choose
    #: between, but a Mind Stone shows both "{T}: Add {C}" and its sacrifice
    #: ability rather than letting one click spend the artifact.  Off by default
    #: so AI seats keep the solver-only view -- ``heuristic_agent`` scores every
    #: activation alike and would tap its rocks for nothing.
    offer_all_abilities: bool = False

    def zone_list(self, zone: Zone) -> list[int]:
        """The ordered oid list for one of this player's zones."""
        if zone is Zone.LIBRARY:
            return self.library
        if zone is Zone.HAND:
            return self.hand
        if zone is Zone.GRAVEYARD:
            return self.graveyard
        if zone is Zone.EXILE:
            return self.exile
        if zone is Zone.COMMAND:
            return self.command
        raise ValueError(f"{zone} is not a player-owned zone")

    @property
    def land_drops_available(self) -> int:
        return 1 + self.extra_land_drops - self.lands_played

    def max_commander_damage(self) -> int:
        return max(self.commander_damage_taken.values(), default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "deck_id": self.deck_id,
            "life": self.life,
            "library": list(self.library),
            "hand": list(self.hand),
            "graveyard": list(self.graveyard),
            "exile": list(self.exile),
            "command": list(self.command),
            "mana_pool": self.mana_pool.to_dict(),
            "lands_played": self.lands_played,
            "extra_land_drops": self.extra_land_drops,
            "commander_tax": dict(self.commander_tax),
            "commander_damage_taken": dict(self.commander_damage_taken),
            "has_lost": self.has_lost,
            "has_city_s_blessing": self.has_city_s_blessing,
            "loss_reason": self.loss_reason.value if self.loss_reason else None,
        }
