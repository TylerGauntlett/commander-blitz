"""The fixed flat action space and its legality mask.

An RL policy needs a constant-size action space, but Magic offers a different set
of actions in every state.  The bridge is a *structured* index: a slot for each
hand position, each battlefield position, each ability, each target option.
Slots are assigned by a deterministic, stable sort, so index 37 tends to mean the
same kind of thing from step to step -- far better for learning than "the 37th
legal action", which shuffles constantly.

**The mask is built by walking ``legality.legal_actions()`` and encoding each
result.** There is no second implementation of what is legal, so the mask and the
HTTP action list cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from automtg.engine import legality
from automtg.engine.actions import Action
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.state import GameState

# -- capacities -------------------------------------------------------------
HAND_CAP = 20
BF_CAP = 40
CMD_CAP = 2
ABIL_CAP = 2
#: Target-option slots per castable object (index 0 also covers "no targets").
TGT_SLOTS = 5
#: Attack-target slots: every opponent, plus their planeswalkers **and
#: battles**. Eight rather than three because a planeswalker is a third kind of
#: thing to attack (506.2) and a pod board can hold several. Raising it shifts
#: every index above `IDX_ATTACK` and therefore invalidates trained checkpoints
#: -- see docs/adr/0002-flat-action-space.md, which is why battles were folded
#: into the existing slots (after each seat's walkers) rather than given their
#: own band.
DEF_CAP = 8
BLOCK_TARGET_CAP = 4
CHOICE_CAP = 10

# -- index layout -----------------------------------------------------------
IDX_PASS = 0
IDX_PLAY_LAND = 1
IDX_CAST = IDX_PLAY_LAND + HAND_CAP
IDX_CAST_COMMANDER = IDX_CAST + HAND_CAP * TGT_SLOTS
IDX_ACTIVATE = IDX_CAST_COMMANDER + CMD_CAP * TGT_SLOTS
IDX_ATTACK = IDX_ACTIVATE + BF_CAP * ABIL_CAP * TGT_SLOTS
IDX_BLOCK = IDX_ATTACK + BF_CAP * DEF_CAP
IDX_CHOOSE = IDX_BLOCK + BF_CAP * BLOCK_TARGET_CAP
IDX_YES = IDX_CHOOSE + CHOICE_CAP
IDX_NO = IDX_YES + 1
IDX_MULLIGAN = IDX_NO + 1
IDX_KEEP = IDX_MULLIGAN + 1

ACTION_SPACE_SIZE = IDX_KEEP + 1

#: Type groups used to order battlefield slots, so creatures stay near creatures.
_TYPE_GROUP = ("Land", "Creature", "Artifact", "Enchantment")


@dataclass
class ActionTable:
    """The encode/decode table for one decision point."""

    mask: np.ndarray
    by_index: dict[int, Action] = field(default_factory=dict)
    #: Actions legality offered that did not fit the fixed layout.
    dropped: list[Action] = field(default_factory=list)

    def decode(self, index: int) -> Action:
        try:
            return self.by_index[int(index)]
        except KeyError:
            raise KeyError(
                f"action index {index} is not legal here "
                f"(legal: {sorted(self.by_index)[:12]})"
            ) from None

    def encode(self, action: Action) -> int:
        for index, candidate in self.by_index.items():
            if candidate == action:
                return index
        raise KeyError(f"{action} has no index in this state")

    @property
    def legal_indices(self) -> list[int]:
        return sorted(self.by_index)


def build(state: GameState) -> ActionTable:
    """Build the action table (and therefore the mask) for the current decision."""

    mask = np.zeros(ACTION_SPACE_SIZE, dtype=np.int8)
    table = ActionTable(mask=mask)

    decision = state.pending_decision
    if decision is None or state.game_over:
        return table

    pid = decision.player
    actions = legality.legal_actions(state)
    slots = _Slots(state, pid, decision)

    # Target options are ordinals within the group of actions sharing the same
    # source and ability, in the order legality produced them.
    ordinals: dict[tuple, int] = {}

    for action in actions:
        key = (action.kind, action.source, action.ability_index)
        ordinal = ordinals.get(key, 0)
        ordinals[key] = ordinal + 1
        index = _encode(state, action, slots, ordinal, decision)
        if index is None or index in table.by_index:
            table.dropped.append(action)
            continue
        table.by_index[index] = action
        mask[index] = 1

    if not table.by_index and actions:
        # Never hand back an empty mask: fall back to the first legal action.
        table.by_index[IDX_PASS] = actions[0]
        mask[IDX_PASS] = 1
        table.dropped = list(actions[1:])

    return table


def mask_for(state: GameState) -> np.ndarray:
    return build(state).mask


# ----------------------------------------------------------------------
# slot assignment
# ----------------------------------------------------------------------


class _Slots:
    """Deterministic slot numbers for the acting player's zones."""

    def __init__(self, state: GameState, pid: int, decision) -> None:
        self.state = state
        self.pid = pid
        self.hand = _index_map(sorted(state.players[pid].hand, key=lambda o: _hand_key(state, o)))
        self.command = _index_map(
            sorted(state.players[pid].command, key=lambda o: state.objects[o].def_id)
        )
        own = [o for o in state.battlefield if state.objects[o].controller == pid]
        self.battlefield = _index_map(sorted(own, key=lambda o: _bf_key(state, o)))
        # Players first, then their planeswalkers, so a seat's slot does not
        # move when a planeswalker enters or dies mid-combat -- which would
        # relabel "attack Alice" as "attack Bob" between two decision points of
        # the same declaration.
        #
        # Keyed by a *tagged* id rather than a bare one: a player id and an
        # object id are both ints and 1 is a legal value of each, so an untagged
        # map would let "attack player 1" and "attack the planeswalker whose oid
        # is 1" collide on the same slot.
        seats = [("player", p) for p in state.turn_order(pid) if p != pid]
        # `"pw"` is the tag 506.2's non-seat defenders share -- planeswalkers
        # and battles alike. Kept as written rather than renamed with the
        # function: it is an internal key, and `encode` below has to spell the
        # same string, so the two changing together buys nothing.
        permanents = [("pw", oid) for oid in _attackable_permanents(state, pid)]
        self.defenders = _index_map(seats + permanents)
        attackers = sorted(state.combat.attackers) if state.combat else []
        self.attackers = _index_map(attackers)
        self.choices = _index_map(decision.remaining_options) if decision else {}


def _attackable_permanents(state: GameState, pid: int) -> list[int]:
    """Planeswalkers **and battles** this player could attack, in the seat order above.

    Grouped by controller rather than by oid, so a slot means "the first
    planeswalker of the next opponent round the table" and stays roughly stable
    as boards change -- the same reasoning `_bf_key` uses for battlefield slots.

    Battles are appended **after** each seat's planeswalkers rather than
    interleaved by oid, and that ordering is the whole reason this function was
    widened rather than a second one added: every walker keeps the slot it had,
    so `DEF_CAP` does not move and no trained checkpoint is invalidated. A board
    with more non-seat defenders than the cap simply loses the overflow from the
    mask, which `encode` has always handled by returning `None`.
    """

    out: list[int] = []
    for seat in state.turn_order(pid):
        if seat == pid:
            continue
        theirs = [
            oid
            for oid in state.battlefield
            if (obj := state.objects.get(oid)) is not None and obj.controller == seat
        ]
        walkers = [oid for oid in theirs if "Planeswalker" in chars(state, oid).types]
        out.extend(walkers)
        out.extend(
            oid
            for oid in theirs
            if "Battle" in chars(state, oid).types and oid not in walkers
        )
    return out


def _index_map(items) -> dict:
    return {item: i for i, item in enumerate(items)}


def _hand_key(state: GameState, oid: int) -> tuple:
    card = state.card(oid)
    return (card.mana_value, card.id, oid)


def _bf_key(state: GameState, oid: int) -> tuple:
    card = state.card_of(state.objects[oid])
    group = next((i for i, t in enumerate(_TYPE_GROUP) if t in card.types), len(_TYPE_GROUP))
    return (group, card.id, oid)


# ----------------------------------------------------------------------
# encoding
# ----------------------------------------------------------------------


def _encode(
    state: GameState, action: Action, slots: _Slots, ordinal: int, decision
) -> int | None:
    kind = action.kind

    if kind in (ActionKind.PASS, ActionKind.FINISH_DECLARATION):
        return IDX_PASS
    if kind is ActionKind.YES:
        return IDX_YES
    if kind is ActionKind.NO:
        return IDX_NO
    if kind is ActionKind.MULLIGAN:
        return IDX_MULLIGAN
    if kind is ActionKind.KEEP:
        return IDX_KEEP

    if kind is ActionKind.CHOOSE:
        slot = slots.choices.get(action.choice)
        if slot is None or slot >= CHOICE_CAP:
            return None
        return IDX_CHOOSE + slot

    if kind is ActionKind.PLAY_LAND:
        slot = slots.hand.get(action.source)
        if slot is None or slot >= HAND_CAP:
            return None
        return IDX_PLAY_LAND + slot

    if kind is ActionKind.CAST:
        if ordinal >= TGT_SLOTS:
            return None
        obj = state.objects.get(action.source)
        if obj is None:
            return None
        if obj.zone is Zone.COMMAND:
            slot = slots.command.get(action.source)
            if slot is None or slot >= CMD_CAP:
                return None
            return IDX_CAST_COMMANDER + slot * TGT_SLOTS + ordinal
        slot = slots.hand.get(action.source)
        if slot is None or slot >= HAND_CAP:
            return None
        return IDX_CAST + slot * TGT_SLOTS + ordinal

    if kind is ActionKind.ACTIVATE:
        slot = slots.battlefield.get(action.source)
        ability = action.ability_index or 0
        if slot is None or slot >= BF_CAP or ability >= ABIL_CAP or ordinal >= TGT_SLOTS:
            return None
        return IDX_ACTIVATE + (slot * ABIL_CAP + ability) * TGT_SLOTS + ordinal

    if kind is ActionKind.ADD_ATTACKER:
        slot = slots.battlefield.get(action.source)
        ref = action.targets[0] if action.targets else None
        key = (
            ("player", ref.id) if ref is not None and ref.kind == "player"
            else ("pw", ref.id) if ref is not None
            else None
        )
        defender_slot = slots.defenders.get(key)
        if slot is None or slot >= BF_CAP or defender_slot is None or defender_slot >= DEF_CAP:
            return None
        return IDX_ATTACK + slot * DEF_CAP + defender_slot

    if kind is ActionKind.ADD_BLOCKER:
        slot = slots.battlefield.get(action.source)
        attacker = action.targets[0].id if action.targets else None
        attacker_slot = slots.attackers.get(attacker)
        if (
            slot is None
            or slot >= BF_CAP
            or attacker_slot is None
            or attacker_slot >= BLOCK_TARGET_CAP
        ):
            return None
        return IDX_BLOCK + slot * BLOCK_TARGET_CAP + attacker_slot

    return None


def describe_index(index: int) -> str:
    """Human-readable name for an action index, for debugging and docs."""
    if index == IDX_PASS:
        return "pass/done"
    if IDX_PLAY_LAND <= index < IDX_CAST:
        return f"play_land[hand {index - IDX_PLAY_LAND}]"
    if IDX_CAST <= index < IDX_CAST_COMMANDER:
        offset = index - IDX_CAST
        return f"cast[hand {offset // TGT_SLOTS}, target {offset % TGT_SLOTS}]"
    if IDX_CAST_COMMANDER <= index < IDX_ACTIVATE:
        offset = index - IDX_CAST_COMMANDER
        return f"cast_commander[{offset // TGT_SLOTS}, target {offset % TGT_SLOTS}]"
    if IDX_ACTIVATE <= index < IDX_ATTACK:
        offset = index - IDX_ACTIVATE
        slot, rest = divmod(offset, ABIL_CAP * TGT_SLOTS)
        ability, target = divmod(rest, TGT_SLOTS)
        return f"activate[bf {slot}, ability {ability}, target {target}]"
    if IDX_ATTACK <= index < IDX_BLOCK:
        offset = index - IDX_ATTACK
        return f"attack[bf {offset // DEF_CAP} -> defender {offset % DEF_CAP}]"
    if IDX_BLOCK <= index < IDX_CHOOSE:
        offset = index - IDX_BLOCK
        return f"block[bf {offset // BLOCK_TARGET_CAP} -> attacker {offset % BLOCK_TARGET_CAP}]"
    if IDX_CHOOSE <= index < IDX_YES:
        return f"choose[{index - IDX_CHOOSE}]"
    return {IDX_YES: "yes", IDX_NO: "no", IDX_MULLIGAN: "mulligan", IDX_KEEP: "keep"}.get(
        index, f"index {index}"
    )
