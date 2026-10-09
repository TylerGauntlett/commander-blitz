"""The baseline every deck gets: the mistakes no competent player makes.

The classic agent's worst habits, in order of how often a playtester saw them:

* attacking into an untapped creature that eats the attacker for free;
* swinging out and dying to the crack-back;
* pointing "target player mills / discards / loses life" at itself, because the
  first legal target in the list was its own seat;
* taking the first mode of a modal spell and the first player of a "choose a
  player" whatever they did;
* playing whichever land came first, with a hand full of the other colour.

None of this is deck-specific. Archetypes build on top of it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from automtg.engine.characteristics import chars
from automtg.engine.costs import available_mana, produced_symbols
from automtg.engine.enums import ActionKind, DecisionKind, Keyword

from .base import Strategy
from .board import (
    blockers_for,
    card_effects,
    colours_needed,
    crack_back,
    creatures,
    incoming_unblocked,
    intent_of,
    lethal_on_board,
    power,
    threat,
    untapped_blockers,
    walk_effects,
)

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.actions import Action, PendingDecision
    from automtg.engine.carddef import CardDef
    from automtg.engine.state import GameState

#: Life at or under which a shock land comes in tapped, whatever it would enable.
SHOCK_FLOOR = 15
#: Through this turn, a mana rock or dork is cast like ramp.
RAMP_TURNS = 8
#: Removal-shaped ops: a mode doing one of these is worth it when the other
#: side has something to point it at.
INTERACTION_OPS = frozenset(
    {"destroy", "exile", "return_to_hand", "damage", "fight", "tap", "gain_control"}
)


class DefaultStrategy(Strategy):
    name = "default"

    # -- the opening hand ----------------------------------------------------

    def keep_hand(self, state: GameState, seat: int) -> bool | None:
        player = state.players[seat]
        if player.mulligans_taken >= 2:
            return True
        hand = [state.card(oid) for oid in player.hand]
        lands = sum(1 for card in hand if card.is_land)
        low, high = self.plan.keep_lands
        if not low <= lands <= high:
            return False
        # Lands and nothing to do with them is a hand that loses on tempo: keep
        # it only once a mulligan has already been paid for.
        early = any(not card.is_land and card.mana_value <= 3 for card in hand)
        return early or player.mulligans_taken >= 1

    # -- combat ---------------------------------------------------------------

    def defender(self, state: GameState, seat: int, default: int) -> int:
        opponents = state.opponents(seat)
        lethal = [pid for pid in opponents if lethal_on_board(state, seat, pid)]
        if lethal:
            return min(lethal, key=lambda pid: (state.players[pid].life, pid))
        # The softest target: low life, few creatures standing in the way.
        return min(
            opponents,
            key=lambda pid: (
                state.players[pid].life + 3 * len(untapped_blockers(state, pid)),
                pid,
            ),
        )

    def attack_value(
        self, state: GameState, seat: int, oid: int, defender: int, base: float
    ) -> float:
        if power(state, oid) <= 0:
            return base
        if lethal_on_board(state, seat, defender):
            # Everything goes: the blockers cannot stop all of it.
            return max(base, power(state, oid) + 20.0)

        value = self._attack_worth(state, seat, oid, defender)
        if value <= 0:
            return value
        declared = set(state.combat.attackers) if state.combat is not None else set()
        if crack_back(state, seat, declared | {oid}) >= state.players[seat].life:
            return 0.0
        return value

    def _attack_worth(self, state: GameState, seat: int, oid: int, defender: int) -> float:
        """The classic agent's scale, asked of the blockers that could really block.

        The classic score is not built on: it asked `combat.can_block`, which
        says "no" for an attacker not yet declared, so it scored every attack
        as unblocked.
        """
        mine = power(state, oid)
        obj = state.objects[oid]
        blockers = blockers_for(state, oid, defender)
        if not blockers:
            return mine + (4.0 if obj.is_commander else 0.0)
        if any(_eats(state, b.oid, oid) for b in blockers):
            return 0.0
        killers = [b for b in blockers if _trades(state, oid, b.oid)]
        if not killers:
            # Nothing that blocks it kills it: a free hit or a free kill.
            kills = any(_kills(state, oid, b.oid) for b in blockers)
            return mine + 3.0 if kills else mine * 0.5
        # A trade is only a trade between equals: a 6/6 into an untapped 1/1
        # deathtoucher is a 6/6 for a 1/1.
        cheapest = min(_worth(state, b.oid) for b in killers)
        if self.plan.aggression >= 0.7:
            return 1.0 if _worth(state, oid) <= cheapest + 4 else 0.0
        if _worth(state, oid) > cheapest + 2:
            return 0.0
        return 1.0 if len(creatures(state, seat)) > len(creatures(state, defender)) else 0.0

    def block_value(
        self, state: GameState, seat: int, blocker: int, attacker: int, base: float
    ) -> float:
        obj = state.objects.get(blocker)
        dies = _kills(state, attacker, blocker)
        lethal = incoming_unblocked(state, seat) >= state.players[seat].life
        if lethal and base <= 0:
            return 1.0 + power(state, attacker) * 0.1  # chump: the alternative is losing
        if obj is not None and obj.is_commander and dies and not lethal:
            return 0.0  # the commander is worth more than one combat's damage
        return base

    # -- priority -------------------------------------------------------------

    def priority_value(self, state: GameState, seat: int, action: Action, base: float) -> float:
        if action.kind is ActionKind.PLAY_LAND:
            return base + self.land_score(state, seat, action)
        if action.kind is ActionKind.CAST:
            card = state.card(action.source)
            value = base
            if value > 0 and state.turn <= RAMP_TURNS and _makes_mana(card):
                # The classic agent calls only a land search "ramp"; a Signet or
                # a mana dork scored as a 100-point "other" and came down after
                # every creature, which is backwards early.
                value = max(value, 380.0 - 15.0 * state.turn)
            if value > 0:
                value += self.plan.key_cards.get(card.id, 0.0)
                value += self.combo_bonus(state, seat, card.id)
            return self.aim_at_players(state, seat, action, card.spell_effects, value)
        if action.kind is ActionKind.ACTIVATE and action.source is not None:
            obj = state.objects.get(action.source)
            if obj is None:
                return base
            card = state.card_of(obj)
            index = action.ability_index
            effects: Sequence[Mapping[str, Any]] = ()
            if index is not None and 0 <= index < len(card.abilities):
                effects = card.abilities[index].effects
            return self.aim_at_players(state, seat, action, effects, base)
        return base

    def land_score(self, state: GameState, seat: int, action: Action) -> float:
        card = state.card(action.source)
        needed = colours_needed(state, seat)
        score = 10.0 * len(needed & set(produced_symbols(card)))
        if getattr(action, "enters_paid", None) is not None:
            # A shock land: two life for an untapped land is worth it only when
            # the extra mana casts something this turn.
            enables = self._enables_a_cast(state, seat)
            if action.enters_paid:
                score += 2.0 if enables and state.players[seat].life > SHOCK_FLOOR else -2.0
        return score

    def _enables_a_cast(self, state: GameState, seat: int) -> bool:
        mana = available_mana(state, seat)
        return any(
            not state.card(oid).is_land and state.card(oid).mana_value == mana + 1
            for oid in state.players[seat].hand
        )

    def combo_bonus(self, state: GameState, seat: int, card_id: str) -> float:
        """Big when this card completes a combo, modest when it starts one."""
        best = 0.0
        if not self.plan.combos:
            return best
        have = _ids_in(state, seat)
        for combo in self.plan.combos:
            if card_id not in combo.pieces:
                continue
            others = combo.pieces - {card_id}
            if others <= have:
                best = max(best, combo.bonus)
            elif others & have:
                best = max(best, combo.bonus * 0.15)
        return best

    def aim_at_players(
        self,
        state: GameState,
        seat: int,
        action: Action,
        effects: Iterable[Mapping[str, Any]],
        value: float,
    ) -> float:
        """Never point harm at ourselves; point it at the opponent it hurts most."""
        players = [ref.id for ref in action.targets if ref.kind == "player"]
        if not players or value <= 0:
            return value
        intent = intent_of(effects)
        if intent is None:
            return value
        if intent == "help":
            return value if all(pid == seat for pid in players) else 0.0
        # Every player target, not the first: "target player draws X" pointed at
        # three players with us among them is still pointed at us.
        if seat in players:
            return 0.0
        return value + max(self.player_score(state, seat, pid, intent) for pid in players)

    def player_score(self, state: GameState, seat: int, pid: int, intent: str) -> float:
        """How good a target this opponent is for a harmful effect, 0..~15."""
        player = state.players[pid]
        if intent == "mill":
            return max(0.0, 10.0 - len(player.library) / 10.0)
        if intent == "damage":
            return max(0.0, 10.0 - player.life / 5.0) + threat(state, pid) * 0.05
        if intent == "discard":
            return float(min(len(player.hand), 10))
        if intent == "edict":
            return max(0.0, 10.0 - len(creatures(state, pid)) * 2.0)
        return threat(state, pid) * 0.2

    # -- resolution questions ---------------------------------------------------

    def choose(
        self,
        state: GameState,
        seat: int,
        decision: PendingDecision,
        choices: Sequence[Action],
    ) -> Action | None:
        if decision.kind is DecisionKind.CHOOSE_PLAYER:
            return self._choose_player(state, seat, decision, choices)
        purpose = decision.context.get("purpose")
        if decision.kind is DecisionKind.CHOOSE_MODE and not purpose:
            return self._choose_mode(state, seat, decision, choices)
        if purpose == "choose_x" and not decision.context.get("loyalty_cost"):
            return self._choose_x(state, seat, decision, choices)
        return None

    def _source_card(self, state: GameState, decision: PendingDecision) -> CardDef | None:
        oid = decision.context.get("source")
        obj = state.objects.get(oid) if isinstance(oid, int) else None
        return state.card_of(obj) if obj is not None else None

    def _choose_player(
        self, state: GameState, seat: int, decision: PendingDecision, choices: Sequence[Action]
    ) -> Action | None:
        card = self._source_card(state, decision)
        if card is None:
            return None
        intent = intent_of(card_effects(card))
        if intent is None:
            return None

        def pid_of(action: Action) -> int | None:
            for ref in action.targets:
                if ref.kind == "player":
                    return ref.id
            return None

        if intent == "help":
            mine = [a for a in choices if pid_of(a) == seat]
            return mine[0] if mine else None
        theirs = [a for a in choices if pid_of(a) not in (None, seat)]
        if not theirs:
            return None
        return max(theirs, key=lambda a: (self.player_score(state, seat, pid_of(a), intent), -a.choice))

    def _choose_mode(
        self, state: GameState, seat: int, decision: PendingDecision, choices: Sequence[Action]
    ) -> Action | None:
        card = self._source_card(state, decision)
        if card is None:
            return None
        by_label: dict[str, Sequence[Mapping[str, Any]]] = {}
        for effect in card_effects(card):
            for mode in effect.get("modes", []) or []:
                label = mode.get("label")
                if label and label not in by_label:
                    by_label[label] = mode.get("effects") or []
        scored = []
        for action in choices:
            if action.choice is None or not 0 <= action.choice < len(decision.options):
                continue
            effects = by_label.get(decision.options[action.choice].label)
            if effects is None:
                continue
            scored.append((self.mode_score(state, seat, effects), -action.choice, action))
        if not scored:
            return self._choose_player_by_label(state, seat, decision, choices, card)
        return max(scored, key=lambda t: (t[0], t[1]))[2]

    def _choose_player_by_label(
        self,
        state: GameState,
        seat: int,
        decision: PendingDecision,
        choices: Sequence[Action],
        card: CardDef,
    ) -> Action | None:
        """A storm copy's "choose new targets" is asked as modes labelled by seat.

        Taken as a plain mode, the first label -- often our own seat -- won, and
        Brain Freeze's copies milled the deck casting them.
        """
        names = {(p.name or f"Player {p.pid}"): p.pid for p in state.players}
        pids = {}
        for action in choices:
            if action.choice is None or not 0 <= action.choice < len(decision.options):
                return None
            pid = names.get(decision.options[action.choice].label)
            if pid is None:
                return None
            pids[action.choice] = pid
        intent = intent_of(card_effects(card))
        if intent is None:
            return None
        if intent == "help":
            mine = [a for a in choices if pids[a.choice] == seat]
            return mine[0] if mine else None
        theirs = [a for a in choices if pids[a.choice] != seat]
        if not theirs:
            return None
        return max(
            theirs,
            key=lambda a: (self.player_score(state, seat, pids[a.choice], intent), -a.choice),
        )

    def mode_score(
        self, state: GameState, seat: int, effects: Iterable[Mapping[str, Any]]
    ) -> float:
        """A rough worth for one mode, from what it does and what is on the table."""
        opposing_spell = any(item.controller != seat for item in state.stack)
        their_board = any(
            not state.card_of(o).is_land
            for pid in state.opponents(seat)
            for o in state.battlefield_objects(pid)
        )
        ours = creatures(state, seat)
        needed = colours_needed(state, seat)
        score = 0.0
        for effect in walk_effects(effects):
            op = effect.get("op")
            if op == "counter":
                score += 8.0 if opposing_spell else -5.0
            elif op in INTERACTION_OPS:
                score += 6.0 if their_board else -2.0
            elif op in ("draw", "create_token", "search_library", "put_onto_battlefield"):
                score += 4.0
            elif op == "add_counters" or op in ("pump", "grant_keyword"):
                score += 3.0 if ours else 0.0
            elif op == "return_from_graveyard":
                score += 3.0 if state.players[seat].graveyard else -1.0
            elif op == "gain_life":
                score += 3.0 if state.players[seat].life <= 15 else 1.0
            elif op == "add_mana":
                mana = str(effect.get("mana", ""))
                score += 3.0 if any(f"{{{c}}}" in mana for c in needed) else 1.0
            elif op in ("mill", "discard", "lose_life"):
                score += 2.0
            else:
                score += 0.5
        return score

    def _choose_x(
        self, state: GameState, seat: int, decision: PendingDecision, choices: Sequence[Action]
    ) -> Action | None:
        """Draw-X never decks us; everything else spends the lot (the agent's rule)."""
        card = self._source_card(state, decision)
        if card is None:
            return None
        ops = {effect.get("op") for effect in card_effects(card)}
        if "draw" not in ops or ops & INTERACTION_OPS:
            return None
        ceiling = max(0, len(state.players[seat].library) - 2)
        safe = [a for a in choices if (a.choice or 0) <= ceiling]
        if not safe:
            return None
        return max(safe, key=lambda a: a.choice or 0)

    def junk_value(self, state: GameState, seat: int, oid: int, base: float) -> float:
        obj = state.objects.get(oid)
        if obj is None:
            return base
        if obj.def_id in self.plan.all_protected() or obj.is_commander:
            return base - 1000.0
        if getattr(obj, "is_token", False) or state.card_of(obj).is_token:
            return base + 2.0
        return base


# ----------------------------------------------------------------------


def _eats(state: GameState, blocker: int, attacker: int) -> bool:
    """Does ``blocker`` kill ``attacker`` in a block and live through it?"""
    return _kills(state, blocker, attacker) and not _kills(state, attacker, blocker)


def _kills(state: GameState, source: int, victim: int) -> bool:
    """Does ``source``'s combat damage destroy ``victim``?"""
    s, v = chars(state, source), chars(state, victim)
    if Keyword.INDESTRUCTIBLE.value in v.keywords or s.power <= 0:
        return False
    return s.power >= v.toughness or Keyword.DEATHTOUCH.value in s.keywords


def _trades(state: GameState, attacker: int, blocker: int) -> bool:
    """Do these two kill each other?"""
    return _kills(state, attacker, blocker) and _kills(state, blocker, attacker)


def _makes_mana(card: CardDef) -> bool:
    """A nonland permanent that taps for mana: a rock or a dork."""
    return card.is_permanent and not card.is_land and bool(produced_symbols(card))


def _worth(state: GameState, oid: int) -> float:
    """A creature's rough value: its stats and what it cost, double for a commander."""
    c = chars(state, oid)
    obj = state.objects[oid]
    value = max(0, c.power) + max(0, c.toughness) + state.card_of(obj).mana_value
    return value * 2 if obj.is_commander else value


def _ids_in(state: GameState, seat: int) -> set[str]:
    """Card ids this seat holds or has on the battlefield (or in the command zone)."""
    player = state.players[seat]
    out = {state.objects[oid].def_id for oid in player.hand if oid in state.objects}
    out |= {state.objects[oid].def_id for oid in player.command if oid in state.objects}
    out |= {o.def_id for o in state.battlefield_objects(seat)}
    return out
