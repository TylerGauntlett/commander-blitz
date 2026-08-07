"""Turning game state into JSON.

Two views:

``full_view``
    Everything, including libraries.  Used by golden tests and the dev-only debug
    endpoint.

``player_view``
    What one seat is allowed to know.  Other players' hands and everybody's
    libraries are reduced to counts.  This is the *only* thing the HTTP layer
    sends to a client, so hidden information cannot leak through the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .characteristics import chars
from .enums import Zone

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def card_view(state: GameState, oid: int, *, revealed: bool = True) -> dict[str, Any]:
    """One object, rendered for display."""
    obj = state.objects[oid]
    if not revealed:
        return {"oid": oid, "hidden": True}

    card = state.card_of(obj)
    view: dict[str, Any] = {
        "oid": oid,
        "card_id": card.id,
        "name": card.name,
        "type_line": card.type_line,
        "mana_cost": str(card.mana_cost),
        "mana_value": card.mana_value,
        "colors": sorted(card.colors),
        "oracle_text": card.oracle_text,
        "controller": obj.controller,
        "owner": obj.owner,
        "zone": obj.zone.value,
        "is_token": obj.is_token,
        "is_commander": obj.is_commander,
    }
    if obj.on_battlefield:
        derived = chars(state, oid)
        view.update(
            {
                "power": derived.power,
                "toughness": derived.toughness,
                "damage": obj.damage,
                "tapped": obj.tapped,
                "summoning_sick": obj.summoning_sick(state.turn),
                "counters": dict(obj.counters),
                "keywords": sorted(derived.keywords),
                "types": sorted(derived.types),
                "subtypes": sorted(derived.subtypes),
                "attached_to": obj.attached_to,
                "attacking": bool(state.combat and state.combat.attacking(oid)),
                "blocking": bool(state.combat and state.combat.blocking(oid)),
            }
        )
    else:
        view.update(
            {
                "power": card.power,
                "toughness": card.toughness,
                "keywords": sorted(card.keywords),
                "types": sorted(card.types),
                "subtypes": sorted(card.subtypes),
            }
        )
    return view


def player_view(state: GameState, seat: int) -> dict[str, Any]:
    """The game as ``seat`` is allowed to see it."""
    return {
        "seat": seat,
        "turn": state.turn,
        "step": state.step.name,
        "phase": state.phase.value,
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "game_over": state.game_over,
        "winners": list(state.winners),
        "result": state.result,
        "players": [_player(state, p.pid, seat) for p in state.players],
        "battlefield": [card_view(state, oid) for oid in state.battlefield],
        "stack": [_stack_item(state, item) for item in state.stack],
        "combat": state.combat.to_dict() if state.combat else None,
        "pending": state.pending_decision.to_dict() if state.pending_decision else None,
    }


def _player(state: GameState, pid: int, seat: int) -> dict[str, Any]:
    player = state.players[pid]
    own = pid == seat
    return {
        "pid": pid,
        "name": player.name,
        "deck_id": player.deck_id,
        "life": player.life,
        "has_lost": player.has_lost,
        "loss_reason": player.loss_reason.value if player.loss_reason else None,
        "lands_played": player.lands_played,
        "mana_pool": player.mana_pool.to_dict(),
        "commander_tax": {str(k): v for k, v in player.commander_tax.items()},
        "commander_damage_taken": {
            str(k): v for k, v in player.commander_damage_taken.items()
        },
        # Hidden zones are counts for everyone; only the viewer sees their own hand.
        "library_count": len(player.library),
        "hand_count": len(player.hand),
        "hand": [card_view(state, oid) for oid in player.hand] if own else None,
        "graveyard": [card_view(state, oid) for oid in player.graveyard],
        "exile": [card_view(state, oid) for oid in player.exile],
        "command": [card_view(state, oid) for oid in player.command],
    }


def _stack_item(state: GameState, item) -> dict[str, Any]:
    data = item.to_dict()
    card = state.registry.get(item.def_id)
    data["name"] = card.name
    data["type_line"] = card.type_line
    return data


def full_view(state: GameState) -> dict[str, Any]:
    """Everything, hidden zones included.  Golden tests snapshot this."""
    view = {
        "turn": state.turn,
        "step": state.step.name,
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "passes_in_row": state.passes_in_row,
        "game_over": state.game_over,
        "winners": list(state.winners),
        "result": state.result,
        "battlefield": [state.objects[oid].to_dict() for oid in state.battlefield],
        "stack": [item.to_dict() for item in state.stack],
        "combat": state.combat.to_dict() if state.combat else None,
        "pending": state.pending_decision.to_dict() if state.pending_decision else None,
        "players": [],
    }
    for player in state.players:
        entry = player.to_dict()
        entry["zones"] = {
            zone.value: [state.objects[oid].def_id for oid in player.zone_list(zone)]
            for zone in (Zone.LIBRARY, Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.COMMAND)
        }
        view["players"].append(entry)
    return view


def event_log(state: GameState, since: int = 0) -> list[dict[str, Any]]:
    return [event.to_dict() for event in state.events[since:]]


def fingerprint(state: GameState) -> str:
    """A stable hash of the event log, for golden replay comparisons."""
    import hashlib

    digest = hashlib.sha256()
    for event in state.events:
        digest.update(event.describe().encode("utf-8"))
    return digest.hexdigest()[:16]
