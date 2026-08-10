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
from .costs import (
    commander_cost,
    land_drops_available,
    mana_availability,
    produced_symbols,
    sources_by_controller,
)
from .enums import Zone
from .legality import unplayable_reason

if TYPE_CHECKING:  # pragma: no cover
    from .mana import ManaSource
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
        # Printed, so it is the same in every zone.  Supertypes let the client
        # say "Basic"; `produces` is what the land actually taps for, which is
        # what colours it -- see costs.produced_symbols.
        "supertypes": sorted(card.supertypes),
        "produces": produced_symbols(card),
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
    # One walk of the battlefield for the whole response rather than one per
    # seat; `mana_availability` filters by controller either way.
    sources = sources_by_controller(state)
    return {
        "seat": seat,
        "turn": state.turn,
        # Full cycles of the table.  `turn` counts player-turns, which is what
        # the rules need but not what a player means by "my second turn"; the
        # client shows this and keeps `turn` in the tooltip.
        "round": state.round,
        "step": state.step.name,
        "phase": state.phase.value,
        "active_player": state.active_player,
        "priority_player": state.priority_player,
        "game_over": state.game_over,
        "winners": list(state.winners),
        "result": state.result,
        "players": [_player(state, p.pid, seat, sources.get(p.pid, [])) for p in state.players],
        "battlefield": [card_view(state, oid) for oid in state.battlefield],
        "stack": [_stack_item(state, item) for item in state.stack],
        "combat": state.combat.to_dict() if state.combat else None,
        "pending": _pending(state, seat),
        # A viewer preference rather than game state, but the client has to be
        # able to render the toggle in the position the engine actually holds it.
        "full_control": state.players[seat].full_control,
    }


def _pending(state: GameState, seat: int) -> dict[str, Any] | None:
    """The open decision, with a card face on every option that names an object.

    ``DecisionOption`` carries a label and a bare object ref, so the client had
    to find the card itself -- and ``findCard`` searches the zones ``player_view``
    sends, which excludes libraries.  Every "search your library", scry, surveil
    and mulligan-bottom prompt therefore degraded to a row of name-only buttons
    with no way to tell what you were choosing between.

    Attaching the face here rather than in ``PendingDecision.to_dict`` keeps
    ``actions.py`` free of display concerns and keeps the RL/agent path
    unchanged.  The ``seat`` guard is what stops it leaking: only the player who
    has to answer sees the cards, and they are entitled to -- ``_choice_actions``
    only generates buttons for that seat in the first place.
    """
    decision = state.pending_decision
    if decision is None:
        return None
    data = decision.to_dict()
    if decision.player != seat:
        return data
    for option, out in zip(decision.options, data["options"], strict=True):
        ref = option.ref
        if ref is not None and ref.kind == "object" and ref.id in state.objects:
            out["card"] = card_view(state, ref.id)
    return data


def _player(
    state: GameState, pid: int, seat: int, sources: list[ManaSource]
) -> dict[str, Any]:
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
        "land_drops_available": land_drops_available(state, pid),
        "mana_pool": player.mana_pool.to_dict(),
        # Untapped sources as well as floating mana: the client cannot work this
        # out from the battlefield alone, because whether a permanent taps for
        # mana lives in its abilities, not in its view.
        "mana": mana_availability(state, pid, sources),
        # The stored value is the number of prior casts; the tax is twice that.
        # Send both so the client never has to know the multiplier.
        "commander_tax": {str(k): v for k, v in player.commander_tax.items()},
        "commander_cost": {
            str(oid): commander_cost(state, oid) for oid in player.commanders
        },
        "commander_damage_taken": {
            str(k): v for k, v in player.commander_damage_taken.items()
        },
        # Hidden zones are counts for everyone; only the viewer sees their own hand.
        "library_count": len(player.library),
        "hand_count": len(player.hand),
        "hand": [card_view(state, oid) for oid in player.hand] if own else None,
        # Only the gates that are actually closed, keyed by oid.  A card absent
        # from this map is playable; see legality.unplayable_reason.
        "hand_reasons": (
            {
                str(oid): reason
                for oid in player.hand
                if (reason := unplayable_reason(state, pid, oid)) is not None
            }
            if own
            else None
        ),
        "graveyard": [card_view(state, oid) for oid in player.graveyard],
        "exile": [card_view(state, oid) for oid in player.exile],
        "command": [card_view(state, oid) for oid in player.command],
    }


def _stack_item(state: GameState, item) -> dict[str, Any]:
    data = item.to_dict()
    card = state.registry.get(item.def_id)
    data["name"] = card.name
    data["type_line"] = card.type_line
    # The client draws the stack as real cards rather than a list of names, so
    # it needs the same payload a battlefield card gets.  A triggered ability
    # has no object of its own; show the permanent that produced it.
    face_oid = item.oid if item.oid is not None else item.source_oid
    data["card"] = (
        card_view(state, face_oid) if face_oid is not None and face_oid in state.objects else None
    )
    return data


def full_view(state: GameState) -> dict[str, Any]:
    """Everything, hidden zones included.  Golden tests snapshot this."""
    view = {
        "turn": state.turn,
        "round": state.round,
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


#: Events whose payload names a card that moved between two hidden zones, or
#: into one.  Everything else in the log either concerns a public zone or
#: carries only counts, so it is safe for every seat verbatim.
_PRIVATE_EVENTS = frozenset({"draw", "discard", "mill"})


def event_log_for(state: GameState, seat: int, since: int = 0) -> list[dict[str, Any]]:
    """The event log as one seat is allowed to read it.

    ``player_view`` already hides other players' hands, but the log runs
    alongside it and is not filtered.  A ``draw`` fires with the object id of the
    card drawn, and a client that accumulates every id it has ever seen can
    identify that card retroactively the moment it is played -- so the hand was
    never really hidden.

    The event itself is kept, with its type and its ``player``, so "Priya drew a
    card" still narrates; only the id is dropped.  Nothing is *removed* from the
    log, because a client that silently receives a shorter list than its
    neighbour has no way to tell that from a bug.
    """
    out: list[dict[str, Any]] = []
    for event in state.events[since:]:
        row = event.to_dict()
        if row["type"] in _PRIVATE_EVENTS and row["player"] != seat:
            row["source"] = None
            row["data"] = {k: v for k, v in row["data"].items() if k != "oid"}
        out.append(row)
    return out


def fingerprint(state: GameState) -> str:
    """A stable hash of the event log, for golden replay comparisons."""
    import hashlib

    digest = hashlib.sha256()
    for event in state.events:
        digest.update(event.describe().encode("utf-8"))
    return digest.hexdigest()[:16]
