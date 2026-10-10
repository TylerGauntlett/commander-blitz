"""Bruvac the Grandiloquent ("Millington"): double every mill, deck the table.

Bruvac doubles every card an opponent mills, so the deck lands him first and
holds its big mill spells -- Traumatize, Maddening Cacophony -- until he is on
the table, when one of them is half a library times two. Twenty Persistent
Petitioners are the engine: one mana and a tap mills two, four Advisors tapped
together mill twenty-four. Isochron Scepter with Dramatic Reversal imprinted
untaps them all again, which is the combo the list is built around; Thassa's
Oracle is cast only when it actually wins.

See docs/cpus/bruvac_the_grandiloquent.md for how the deck plays and what this
plan encodes.
"""

from __future__ import annotations

from commanderblitz.engine.enums import DecisionKind, Zone

from ..archetypes import Mill, activated_ability, cast_card
from ..base import Combo, DeckPlan
from ..board import card_effects, intent_of, lethal_on_board

BRUVAC = "bruvac_the_grandiloquent"
PETITIONERS = "persistent_petitioners"
SCEPTER = "isochron_scepter"
REVERSAL = "dramatic_reversal"
#: Spells that mill a fraction of a library, and so are worth twice as much
#: with Bruvac out -- held for him rather than spent at face value.
BIG_MILL = frozenset({"traumatize", "maddening_cacophony"})
#: What a tutor fetches, best first. Reversal only matters beside a Scepter.
TUTOR_ORDER = (REVERSAL, "brain_freeze", "traumatize", "maddening_cacophony", "cryptic_command")
TUTORS = frozenset({"merchant_scroll", "mystical_tutor"})
#: After this turn a held big mill spell is cast without Bruvac: a commander
#: that keeps dying is not coming back cheaply, and a spell in hand mills nobody.
HOLD_UNTIL = 12


class Millington(Mill):
    """The Mill archetype, plus Bruvac's doubling and the Scepter loop."""

    def priority_value(self, state, seat, action, base):
        card = cast_card(state, action)
        ability = activated_ability(state, action)
        if ability is not None:
            source = state.objects[action.source]
            if source.def_id == SCEPTER:
                return self._scepter_value(state, seat, action, base)
            if source.def_id == PETITIONERS:
                return self._petition_value(state, seat, action, ability, base)
        value = super().priority_value(state, seat, action, base)
        if card is None:
            return value
        if card.id == "thassa_s_oracle":
            # A 1/3 for two otherwise. Its own two {U} count once it is on the
            # battlefield, which is when the trigger checks.
            if devotion_to_blue(state, seat) + 2 >= len(state.players[seat].library):
                return max(value, base, 1.0) + 1000.0
            return 0.0
        if card.id == REVERSAL and self._scepter_needs(state, seat):
            return 0.0  # it is the imprint, not a spell to spend
        if card.id in BIG_MILL and value > 0:
            if bruvac_out(state, seat):
                value += 150.0 + (60.0 if action.kicked else 0.0)
            elif state.turn < HOLD_UNTIL and _in_command_zone(state, seat, BRUVAC):
                return 0.0
        if card.id == "brain_freeze" and value > 0:
            value = self._brain_freeze(state, seat, action, value)
        return value

    # -- the Scepter loop -------------------------------------------------------

    def _scepter_needs(self, state, seat) -> bool:
        """Is there a Scepter (in hand, or empty on the table) waiting for Reversal?"""
        player = state.players[seat]
        if any(state.objects[oid].def_id == SCEPTER for oid in player.hand):
            return True
        return any(
            o.def_id == SCEPTER and not _imprinted(state, o.oid, REVERSAL)
            for o in state.battlefield_objects(seat)
        )

    def _loop_live(self, state, seat) -> bool:
        return any(
            o.def_id == SCEPTER and not o.tapped and _imprinted(state, o.oid, REVERSAL)
            for o in state.battlefield_objects(seat)
        )

    def _scepter_value(self, state, seat, action, base) -> float:
        scepter = action.source
        if not _imprinted(state, scepter, REVERSAL):
            # Brain Freeze or a counterspell gets the agent's usual weight; an
            # empty Scepter (its imprint trigger still on the stack) copies nothing.
            return base if _imprinted(state, scepter, None) else 0.0
        if state.stack or not any(state.players[pid].library for pid in state.opponents(seat)):
            return 0.0
        # Untapping is only worth the {2} when an Advisor has already been
        # tapped to mill -- and that mill has *resolved*, hence the empty stack:
        # untapping in response stacks up mill abilities that never resolve,
        # and the loop spins for ever. That is also what ends it: each pass
        # needs a fresh mill that took cards, and libraries run out. Mana rocks
        # are left out on purpose -- the agent taps them by hand for nothing,
        # and counting them would let it spin the Scepter with no mill at all.
        tapped = [
            o
            for o in state.battlefield_objects(seat)
            if o.tapped and o.oid != scepter and "Advisor" in state.card_of(o).subtypes
        ]
        return 60.0 + 10.0 * len(tapped) if tapped else 0.0

    def _petition_value(self, state, seat, action, ability, base) -> float:
        targets = [ref.id for ref in action.targets if ref.kind == "player"]
        if not targets or targets[0] == seat or not state.players[targets[0]].library:
            return 0.0
        if base <= 0 and not self._loop_live(state, seat):
            # Used this turn and nothing will untap it: the agent's once-a-turn
            # rule stands.
            return 0.0
        value = 5.0 + self.player_score(state, seat, targets[0], "mill")
        if ability.cost is not None and ability.cost.tap_permanents:
            value += 40.0  # four Advisors: twelve cards (twenty-four) for no mana
        return value

    # -- Brain Freeze -------------------------------------------------------------

    def _brain_freeze(self, state, seat, action, value) -> float:
        storm = sum(state.turn_ledger.spells_cast.values())
        per_copy = 6 if bruvac_out(state, seat) else 3
        milled = per_copy * (storm + 1)
        targets = [ref.id for ref in action.targets if ref.kind == "player"]
        if not targets or not state.players[targets[0]].library:
            return 0.0
        if milled >= len(state.players[targets[0]].library):
            return value + 300.0
        # Three cards is a waste of a storm card: wait for a busy turn.
        return value + 30.0 * storm if storm >= 2 else 0.0

    # -- resolution questions -------------------------------------------------------

    def attack_value(self, state, seat, oid, defender, base):
        value = super().attack_value(state, seat, oid, defender, base)
        # An Advisor that attacks for one is not tapping to mill two. Only a
        # lethal swing (the baseline's alpha strike) sends them.
        card = state.card_of(state.objects[oid])
        if value > 0 and "Advisor" in card.subtypes and not lethal_on_board(state, seat, defender):
            return 0.0
        return value

    def choose(self, state, seat, decision, choices):
        source = self._source_card(state, decision)
        if source is not None and source.id == SCEPTER:
            picked = _prefer(state, choices, (REVERSAL, "brain_freeze", "muddle_the_mixture"))
            if picked is not None:
                return picked
        if (
            source is not None
            and source.id in TUTORS
            and decision.context.get("purpose") == "search"
        ):
            order = TUTOR_ORDER if self._scepter_needs(state, seat) else TUTOR_ORDER[1:]
            picked = _prefer(state, choices, order)
            if picked is not None:
                return picked
        if decision.kind is DecisionKind.CHOOSE_MODE and source is not None:
            picked = self._copy_target(state, seat, decision, choices, source)
            if picked is not None:
                return picked
        return super().choose(state, seat, decision, choices)

    def _copy_target(self, state, seat, decision, choices, source):
        """A storm (or Stormcaller) copy's new target, offered as a menu of players.

        The baseline reads modes off the card and finds none here, so the
        agent would take the first option -- our own seat, milling ourselves.
        """
        if intent_of(card_effects(source)) != "mill":
            return None
        by_name = {state.players[pid].name: pid for pid in state.opponents(seat)}
        scored = []
        for action in choices:
            if action.choice is None or not 0 <= action.choice < len(decision.options):
                continue
            pid = by_name.get(decision.options[action.choice].label)
            if pid is not None and state.players[pid].library:
                scored.append((self.player_score(state, seat, pid, "mill"), -action.choice, action))
        return max(scored, key=lambda t: (t[0], t[1]))[2] if scored else None


# ----------------------------------------------------------------------


def devotion_to_blue(state, seat: int) -> int:
    return sum(state.card_of(o).mana_cost.symbols_of("U") for o in state.battlefield_objects(seat))


def bruvac_out(state, seat: int) -> bool:
    return any(o.def_id == BRUVAC for o in state.battlefield_objects(seat))


def _in_command_zone(state, seat: int, card_id: str) -> bool:
    return any(state.objects[oid].def_id == card_id for oid in state.players[seat].command)


def _imprinted(state, scepter: int, card_id: str | None) -> bool:
    """Is ``card_id`` (or anything, for None) exiled under this Scepter?"""
    return any(
        o.zone is Zone.EXILE and o.exiled_by == scepter and card_id in (None, o.def_id)
        for o in state.objects.values()
    )


def _prefer(state, choices, order):
    """The choice naming the earliest card in ``order``, if any does."""
    ranked = []
    for action in choices:
        ref = next((r for r in action.targets if r.kind == "object"), None)
        obj = state.objects.get(ref.id) if ref is not None else None
        if obj is not None and obj.def_id in order:
            ranked.append((order.index(obj.def_id), action))
    return min(ranked, key=lambda t: t[0])[1] if ranked else None


STRATEGY = Millington(
    DeckPlan(
        deck_id="bruvac_the_grandiloquent",
        archetype="mill",
        commanders=frozenset({BRUVAC}),
        key_cards={
            BRUVAC: 120.0,
            "sol_ring": 80.0,
            "arcane_signet": 30.0,
            "drowned_secrets": 70.0,
            "memory_erosion": 60.0,
            "sphinx_s_tutelage": 60.0,
            "teferi_s_tutelage": 50.0,
            "altar_of_the_brood": 40.0,
            "rhystic_study": 50.0,
            PETITIONERS: 40.0,
            SCEPTER: 30.0,
            "folio_of_fancies": 30.0,
        },
        combos=(Combo("Isochron Reversal", frozenset({SCEPTER, REVERSAL}), 300.0),),
        win_cons=frozenset(
            {
                "traumatize",
                "maddening_cacophony",
                "brain_freeze",
                "fleet_swallower",
                "thassa_s_oracle",
                "jace_wielder_of_mysteries",
            }
        ),
        protect=frozenset({"drowned_secrets", "memory_erosion", "sphinx_s_tutelage"}),
        keep_lands=(2, 5),
        aggression=0.2,
    )
)
