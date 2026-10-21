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

import hashlib
from typing import TYPE_CHECKING, Any

from .characteristics import chars, top_of_library
from .costs import (
    commander_cost,
    land_drops_available,
    mana_availability,
    produced_symbols,
    sources_by_controller,
)
from .enums import Zone
from .game import FREE_MULLIGANS, MAX_MULLIGANS
from .legality import unplayable_reason
from .player_statics import player_looks_at_library_top, player_reveals_library_top
from .text_change import displayed as displayed_text

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
        # Rewritten for a text-changed permanent (613.1c), so the type line and
        # the rules text a player reads agree with what the card now does -- and
        # with the derived `subtypes` sent in the same payload. `text_changes`
        # is empty for every other card, so this is one attribute check.
        "type_line": displayed_text(card.type_line, obj.text_changes),
        "mana_cost": str(card.mana_cost),
        "mana_value": card.mana_value,
        "colors": sorted(card.colors),
        "oracle_text": displayed_text(card.oracle_text, obj.text_changes),
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
        if card.top_level:
            # A Class's level (716). Not a counter, so `counters` above never
            # carries it, and it is the one thing on the permanent that says
            # which of its printed abilities are switched on. Sent only for a
            # card with level lines, so every other permanent's view is as it
            # was.
            view["level"] = obj.class_level
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
        "manual_mana": state.players[seat].manual_mana,
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


def _library_top(state: GameState, pid: int, seat: int) -> tuple[dict[str, Any] | None, bool]:
    """The top card of ``pid``'s library as ``seat`` is allowed to see it.

    Two statics can show it, and they differ only in *who*:

    ``reveal_library_top``
        "Play with the top card of your library revealed." Vampire Nocturnus.
        The card is public, so it goes to every seat -- an opponent who cannot
        see a revealed card is playing against information they are entitled to.

    ``look_at_library_top``
        "You may look at the top card of your library any time." Verge Rangers.
        Nobody is shown anything, so it goes to ``pid``'s own seat and stops
        there. Sending it to an opponent would be showing them a card the
        printed card never shows.

    Returns the face and whether it is *public*, because the client cannot work
    the second out from the first: the payload is identical either way, and a UI
    that calls a private look "revealed" tells its own player their opponent
    shares the knowledge. That is the same mistake as leaking it, made in the
    reader's head instead of on the wire.
    """
    public = player_reveals_library_top(state, pid)
    if not public and not (pid == seat and player_looks_at_library_top(state, pid)):
        return None, False
    top = top_of_library(state, pid)
    if top is None:
        return None, False
    return card_view(state, top.oid), public


def _player(
    state: GameState, pid: int, seat: int, sources: list[ManaSource]
) -> dict[str, Any]:
    player = state.players[pid]
    own = pid == seat
    library_top, library_top_public = _library_top(state, pid, seat)
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
        # How many mulligans this seat has taken.
        #
        # It was on `Player` from the first London-mulligan commit and reachable
        # only through `full_view`, the dev endpoint -- so the count the engine
        # writes into the decision's own prompt (`"Mulligan? (2 taken)"`) had
        # never been on a client. `OpeningHand` draws it as the lamps that say
        # how many are left, and the alternative was regex-parsing a sentence
        # written for a human.
        #
        # Sent for every seat, not just the viewer: how many times the table
        # went back for a new hand is public at a real table, and it is the
        # first thing a pod knows about each other.
        "mulligans_taken": player.mulligans_taken,
        # The rules the lamps are drawn against, sent rather than copied so the
        # screen cannot say "keep 6" for a mulligan the engine gives away free.
        "mulligans_free": FREE_MULLIGANS,
        "mulligans_max": MAX_MULLIGANS,
        # Hidden zones are counts for everyone; only the viewer sees their own hand.
        "library_count": len(player.library),
        # The top card, if this seat may see it at all -- `None` otherwise, so
        # the client needs no separate flag to know whether to draw one. Which
        # seats get it, and what `library_top_public` means, is `_library_top`.
        "library_top": library_top,
        "library_top_public": library_top_public,
        "hand_count": len(player.hand),
        "hand": [card_view(state, oid) for oid in player.hand] if own else None,
        # "Look at target player's hand." Private information, so it is sent to
        # the one seat entitled to it and nobody else -- the `seat in
        # revealed_to` test is what keeps this from being `reveal`. Empty for
        # your own hand, which `hand` already sends in full.
        "hand_revealed": (
            []
            if own
            else [
                card_view(state, oid)
                for oid in player.hand
                if seat in state.objects[oid].revealed_to
            ]
        ),
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
        # Exile is a **public** zone and is sent in full -- except for the cards
        # put there face down (Necropotence). Those are dropped from the list
        # for every seat not in `revealed_to`, rather than sent redacted: a
        # `CardView` promises a name and a type line, and half a card is a shape
        # every consumer would have to learn. What stays public is that a card
        # is *there*, which is `exile_hidden_count` below -- the pile is visible
        # at a real table even when its faces are not.
        "exile": [
            card_view(state, oid)
            for oid in player.exile
            if not state.objects[oid].hidden_in_exile or seat in state.objects[oid].revealed_to
        ],
        "exile_hidden_count": sum(
            1
            for oid in player.exile
            if state.objects[oid].hidden_in_exile and seat not in state.objects[oid].revealed_to
        ),
        "command": [card_view(state, oid) for oid in player.command],
        "commanders_unseen": _commanders_unseen(state, pid),
    }


def _commanders_unseen(state: GameState, pid: int) -> list[dict[str, Any]]:
    """``pid``'s commanders that are in no zone this view otherwise sends.

    The client draws a seat's commander as its portrait and finds it by
    searching the zones above -- so a commander that left all of them took the
    seat's identity with it. Oubliette is the common case: a phased-out
    permanent leaves `state.battlefield` (702.26) and is in no list at all. A
    commander bounced to hand or tucked into the library is the other.

    Sent to every seat, because which card is a player's commander is public
    from the first turn (903.3) and moving it into a hidden zone happened in
    front of the table. Only the identity is new information here -- the hand
    and library contents around it stay counts. ``phased_out`` is added because
    `zone` cannot say it: the object never left the battlefield zone, it is
    only treated as though it does not exist.
    """
    out: list[dict[str, Any]] = []
    for oid in state.players[pid].commanders:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.phased_out:
            out.append({**card_view(state, oid), "phased_out": True})
        elif obj.zone in (Zone.HAND, Zone.LIBRARY):
            out.append(card_view(state, oid))
    return out


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

    digest = hashlib.sha256()
    for event in state.events:
        digest.update(event.describe().encode("utf-8"))
    return digest.hexdigest()[:16]
