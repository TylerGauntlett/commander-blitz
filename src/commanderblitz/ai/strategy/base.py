"""The strategy interface: how a deck wants its CPU to play.

`HeuristicAgent` scores every legal action the same way for every deck. A
:class:`Strategy` sits beside it and adjusts those scores -- or answers a
question outright -- for one deck's plan: a mill deck points its mill at the
shortest library, a Voltron deck suits up its commander, a combo deck casts
its second piece when it is holding the first.

Every hook receives the score the agent would have used and returns the one to
use, so a hook that does nothing returns its input. The base class does
nothing at all, which makes it the **classic** agent exactly -- the behaviour
every seeded test before strategies was written against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.engine.actions import Action, PendingDecision
    from commanderblitz.engine.state import GameState


@dataclass(frozen=True)
class Combo:
    """Cards that win, or come close, when they are all on the table.

    ``pieces`` are card ids. A piece in hand is worth casting with a big bonus
    once every other piece is in hand or on the battlefield; while one is
    missing, the pieces in hand are held rather than fed to a removal spell.
    """

    name: str
    pieces: frozenset[str]
    bonus: float = 400.0


@dataclass(frozen=True)
class DeckPlan:
    """What one deck is trying to do, as data a strategy reads.

    Card ids throughout -- ``tests/ai/strategy/test_registry.py`` checks each
    one is really in the deck, so a typo cannot silently disable a bonus.
    """

    deck_id: str
    archetype: str
    commanders: frozenset[str] = frozenset()
    #: card id -> bonus added to its cast (or activation) score.
    key_cards: Mapping[str, float] = field(default_factory=dict)
    combos: tuple[Combo, ...] = ()
    #: The cards that actually end the game. Protected like combo pieces.
    win_cons: frozenset[str] = frozenset()
    #: Never discarded, never sacrificed while anything else will do.
    protect: frozenset[str] = frozenset()
    #: A hand outside this many lands is a mulligan.
    keep_lands: tuple[int, int] = (2, 5)
    #: 0 attacks only when it is safe; 1 accepts trades and races.
    aggression: float = 0.5

    def all_protected(self) -> frozenset[str]:
        pieces = frozenset(card for combo in self.combos for card in combo.pieces)
        return self.protect | self.win_cons | pieces | self.commanders


class Strategy:
    """The neutral strategy: every hook returns what it was given.

    Subclasses override only what they care about and call ``super()`` for the
    rest, so archetypes stack: a Voltron deck's attack rule runs on top of the
    baseline's "don't walk into an obvious block", not instead of it.
    """

    name = "classic"

    def __init__(self, plan: DeckPlan | None = None) -> None:
        self.plan = plan or DeckPlan(deck_id="", archetype=self.name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.plan.deck_id or '-'})"

    # -- the opening hand ----------------------------------------------------

    def keep_hand(self, state: GameState, seat: int) -> bool | None:
        """Keep (True), mulligan (False), or defer to the agent (None)."""
        return None

    # -- combat ---------------------------------------------------------------

    def defender(self, state: GameState, seat: int, default: int) -> int:
        """Which opponent to attack this combat."""
        return default

    def attack_value(
        self, state: GameState, seat: int, oid: int, defender: int, base: float
    ) -> float:
        """How good is sending this creature at this player? Non-positive holds it back."""
        return base

    def block_value(
        self, state: GameState, seat: int, blocker: int, attacker: int, base: float
    ) -> float:
        return base

    # -- priority -------------------------------------------------------------

    def priority_value(self, state: GameState, seat: int, action: Action, base: float) -> float:
        """Score for one priority action: a land, a cast, an activation, a pass."""
        return base

    # -- questions asked while something resolves -----------------------------

    def choose(
        self,
        state: GameState,
        seat: int,
        decision: PendingDecision,
        choices: Sequence[Action],
    ) -> Action | None:
        """Answer a resolution-time question, or None to let the agent answer."""
        return None

    def junk_value(self, state: GameState, seat: int, oid: int, base: float) -> float:
        """How willing are we to discard / sacrifice this? Higher goes first."""
        return base
