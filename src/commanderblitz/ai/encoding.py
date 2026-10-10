"""Observation encoding.

The observation has two parts:

* a dense ``scalar`` vector of normalised game quantities, and
* a parallel ``card_ids`` integer array naming the card in each hand,
  battlefield and stack slot.

The second part is what lets a model learn *per-card* behaviour through an
embedding table.  With only a couple of hundred distinct cards in the pool this
is cheap, and it is the single biggest quality-per-line win in the ML layer:
without it the policy can only see "a 2/2 creature", not "Legion Lieutenant".

Slot ordering matches :mod:`commanderblitz.ai.action_space`, so observation slot *k* and
action slot *k* refer to the same object.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.costs import can_pay_mana, land_drops_available
from commanderblitz.engine.enums import COLOR_ORDER, Keyword, Step
from commanderblitz.engine.player import COMMANDER_DAMAGE_THRESHOLD, STARTING_LIFE

from .action_space import BF_CAP, HAND_CAP, _bf_key, _hand_key

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.cards.registry import CardRegistry
    from commanderblitz.engine.state import GameState

STACK_CAP = 8
SEAT_CAP = 4

GLOBAL_FEATURES = 21
SEAT_FEATURES = 24
BF_FEATURES = 24
HAND_FEATURES = 12
STACK_FEATURES = 6

OBS_DIM = (
    GLOBAL_FEATURES
    + SEAT_CAP * SEAT_FEATURES
    + BF_CAP * BF_FEATURES
    + HAND_CAP * HAND_FEATURES
    + STACK_CAP * STACK_FEATURES
)

CARD_SLOTS = HAND_CAP + BF_CAP + STACK_CAP

#: Keyword bits, in a fixed order, exposed per battlefield slot.
KEYWORD_BITS = (
    Keyword.FLYING,
    Keyword.REACH,
    Keyword.TRAMPLE,
    Keyword.DEATHTOUCH,
    Keyword.LIFELINK,
    Keyword.VIGILANCE,
    Keyword.HASTE,
    Keyword.MENACE,
    Keyword.FIRST_STRIKE,
    Keyword.DOUBLE_STRIKE,
)

TYPE_BITS = ("Creature", "Land", "Artifact", "Enchantment")


class CardVocabulary:
    """Maps card ids to embedding indices.  Index 0 means "empty slot".

    ``ids`` may be given explicitly, and a checkpoint must always do so.  The
    list is ``sorted(registry.ids())``, so adding a card that sorts early shifts
    the index of every card after it -- a saved network would then load without
    complaint and read the wrong embedding for most of the pool.  That is a
    silent failure, and it is worse than the loud one: growing the registry past
    ``n_cards`` raises ``IndexError`` inside the embedding lookup instead.

    Both happen the moment a new precon ships, which is why the ids travel with
    the weights.
    """

    __slots__ = ("_index", "ids")

    def __init__(self, registry: CardRegistry, ids: Sequence[str] | None = None) -> None:
        self.ids = list(ids) if ids is not None else ["<empty>", *registry.ids()]
        self._index = {card_id: i for i, card_id in enumerate(self.ids)}

    def __len__(self) -> int:
        return len(self.ids)

    def index(self, def_id: str | None) -> int:
        if def_id is None:
            return 0
        return self._index.get(def_id, 0)


def encode(state: GameState, seat: int, vocab: CardVocabulary) -> dict[str, np.ndarray]:
    """Encode the game from ``seat``'s point of view."""
    scalar = np.zeros(OBS_DIM, dtype=np.float32)
    cards = np.zeros(CARD_SLOTS, dtype=np.int32)
    cursor = 0

    cursor = _encode_global(state, seat, scalar, cursor)
    cursor = _encode_seats(state, seat, scalar, cursor)
    cursor = _encode_battlefield(state, seat, scalar, cards, cursor, vocab)
    cursor = _encode_hand(state, seat, scalar, cards, cursor, vocab)
    cursor = _encode_stack(state, seat, scalar, cards, cursor, vocab)

    assert cursor == OBS_DIM, f"encoder wrote {cursor} features, expected {OBS_DIM}"
    np.clip(scalar, -1.0, 1.0, out=scalar)
    return {"scalar": scalar, "card_ids": cards}


# ----------------------------------------------------------------------


def _encode_global(state: GameState, seat: int, out: np.ndarray, cursor: int) -> int:
    out[cursor] = min(state.turn / 60.0, 1.0)
    cursor += 1
    out[cursor + int(state.step)] = 1.0
    cursor += len(Step)
    out[cursor] = 1.0 if state.active_player == seat else 0.0
    cursor += 1
    out[cursor] = 1.0 if state.priority_player == seat else 0.0
    cursor += 1
    out[cursor] = min(len(state.stack) / 8.0, 1.0)
    cursor += 1
    out[cursor] = state.num_players / 4.0
    cursor += 1
    out[cursor] = min(land_drops_available(state, seat) / 3.0, 1.0)
    cursor += 1
    out[cursor] = min(len(state.alive()) / 4.0, 1.0)
    cursor += 1
    decision = state.pending_decision
    out[cursor] = 1.0 if decision is not None and decision.player == seat else 0.0
    cursor += 1
    return cursor


def _encode_seats(state: GameState, seat: int, out: np.ndarray, cursor: int) -> int:
    """Self first, then the other seats clockwise, so the layout is seat-relative."""
    order = [(seat + i) % state.num_players for i in range(state.num_players)]
    for slot in range(SEAT_CAP):
        if slot >= len(order):
            continue
        base = cursor + slot * SEAT_FEATURES
        pid = order[slot]
        player = state.players[pid]
        own = state.battlefield_objects(pid)
        creatures = [o for o in own if "Creature" in chars(state, o.oid).types]
        lands = [o for o in own if "Land" in chars(state, o.oid).types]

        out[base + 0] = player.life / (STARTING_LIFE * 2)
        out[base + 1] = min(len(player.hand) / 15.0, 1.0)
        out[base + 2] = min(len(player.library) / 60.0, 1.0)
        out[base + 3] = min(len(player.graveyard) / 40.0, 1.0)
        out[base + 4] = min(len(player.exile) / 20.0, 1.0)
        out[base + 5] = min(len(lands) / 20.0, 1.0)
        out[base + 6] = min(len(creatures) / 20.0, 1.0)
        out[base + 7] = min(sum(chars(state, o.oid).power for o in creatures) / 30.0, 1.0)
        out[base + 8] = min(sum(chars(state, o.oid).toughness for o in creatures) / 30.0, 1.0)
        for i in range(len(COLOR_ORDER)):
            out[base + 9 + i] = min(player.mana_pool.amounts[i] / 10.0, 1.0)
        out[base + 14] = min(max(player.commander_tax.values(), default=0) / 5.0, 1.0)
        out[base + 15] = min(player.max_commander_damage() / COMMANDER_DAMAGE_THRESHOLD, 1.0)
        out[base + 16] = 0.0 if player.has_lost else 1.0
        out[base + 17] = 1.0 if pid == seat else 0.0
        out[base + 18] = 1.0 if pid == state.active_player else 0.0
        out[base + 19] = min(len(player.command) / 2.0, 1.0)
        out[base + 20] = min(player.lands_played / 3.0, 1.0)
        out[base + 21] = min(sum(1 for o in own if o.tapped) / 20.0, 1.0)
        out[base + 22] = min(len(own) / 40.0, 1.0)
        out[base + 23] = 1.0 if state.combat and pid in state.combat.attackers.values() else 0.0
    return cursor + SEAT_CAP * SEAT_FEATURES


def _encode_battlefield(
    state: GameState,
    seat: int,
    out: np.ndarray,
    cards: np.ndarray,
    cursor: int,
    vocab: CardVocabulary,
) -> int:
    own = sorted(
        (o for o in state.battlefield if state.objects[o].controller == seat),
        key=lambda oid: _bf_key(state, oid),
    )
    others = sorted(
        (o for o in state.battlefield if state.objects[o].controller != seat),
        key=lambda oid: _bf_key(state, oid),
    )
    ordered = (own + others)[:BF_CAP]
    combat = state.combat

    for slot, oid in enumerate(ordered):
        obj = state.objects[oid]
        c = chars(state, oid)
        base = cursor + slot * BF_FEATURES
        out[base + 0] = 1.0
        out[base + 1] = 1.0 if obj.controller == seat else 0.0
        out[base + 2] = min(c.power / 10.0, 1.0)
        out[base + 3] = min(c.toughness / 10.0, 1.0)
        out[base + 4] = min(obj.damage / 10.0, 1.0)
        out[base + 5] = 1.0 if obj.tapped else 0.0
        out[base + 6] = 1.0 if obj.summoning_sick(state.turn) else 0.0
        out[base + 7] = 1.0 if combat and combat.attacking(oid) else 0.0
        out[base + 8] = 1.0 if combat and combat.blocking(oid) else 0.0
        out[base + 9] = 1.0 if obj.is_commander else 0.0
        out[base + 10] = 1.0 if obj.is_token else 0.0
        out[base + 11] = min(obj.counter("+1/+1") / 5.0, 1.0)
        for i, type_name in enumerate(TYPE_BITS):
            out[base + 12 + i] = 1.0 if type_name in c.types else 0.0
        for i, keyword in enumerate(KEYWORD_BITS):
            out[base + 16 + i] = 1.0 if keyword.value in c.keywords else 0.0
        cards[HAND_CAP + slot] = vocab.index(obj.def_id)
    return cursor + BF_CAP * BF_FEATURES


def _encode_hand(
    state: GameState,
    seat: int,
    out: np.ndarray,
    cards: np.ndarray,
    cursor: int,
    vocab: CardVocabulary,
) -> int:
    hand = sorted(state.players[seat].hand, key=lambda oid: _hand_key(state, oid))[:HAND_CAP]
    for slot, oid in enumerate(hand):
        card = state.card(oid)
        base = cursor + slot * HAND_FEATURES
        out[base + 0] = 1.0
        out[base + 1] = min(card.mana_value / 8.0, 1.0)
        for i, colour in enumerate(COLOR_ORDER):
            out[base + 2 + i] = 1.0 if colour.value in card.colors else 0.0
        for i, type_name in enumerate(TYPE_BITS):
            out[base + 7 + i] = 1.0 if type_name in card.types else 0.0
        out[base + 11] = 1.0 if can_pay_mana(state, seat, card.mana_cost) else 0.0
        cards[slot] = vocab.index(card.id)
    return cursor + HAND_CAP * HAND_FEATURES


def _encode_stack(
    state: GameState,
    seat: int,
    out: np.ndarray,
    cards: np.ndarray,
    cursor: int,
    vocab: CardVocabulary,
) -> int:
    for slot, item in enumerate(state.stack[-STACK_CAP:]):
        card = state.registry.get(item.def_id)
        base = cursor + slot * STACK_FEATURES
        out[base + 0] = 1.0
        out[base + 1] = 1.0 if item.controller == seat else 0.0
        out[base + 2] = 1.0 if "Creature" in card.types else 0.0
        out[base + 3] = 1.0 if "Instant" in card.types else 0.0
        out[base + 4] = min(card.mana_value / 8.0, 1.0)
        out[base + 5] = (
            1.0
            if any(
                ref.kind == "object"
                and state.objects.get(ref.id) is not None
                and state.objects[ref.id].controller == seat
                for ref in item.targets
            )
            else 0.0
        )
        cards[HAND_CAP + BF_CAP + slot] = vocab.index(item.def_id)
    return cursor + STACK_CAP * STACK_FEATURES
