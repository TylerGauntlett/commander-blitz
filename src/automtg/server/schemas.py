"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SeatConfig(BaseModel):
    """One seat in a new game."""

    deck_id: str
    kind: Literal["human", "ai"] = "ai"
    agent: Literal["random", "heuristic", "policy"] = "heuristic"
    name: str | None = None


class NewGameRequest(BaseModel):
    seats: list[SeatConfig] = Field(min_length=2, max_length=4)
    seed: int | None = None
    max_turns: int | None = None


class LegalActionDTO(BaseModel):
    """One thing the client may do.

    ``id`` is opaque and server-generated.  The client echoes it back rather than
    reconstructing an action, so client and engine cannot disagree about what an
    action means, and adding a new action kind needs no client change.
    """

    id: str
    kind: str
    label: str
    source_oid: int | None = None
    ability_index: int | None = None
    targets: list[dict[str, Any]] = Field(default_factory=list)
    choice: int | None = None
    x: int = 0


class ApplyActionRequest(BaseModel):
    seat: int
    action_id: str


class DeclareRequest(BaseModel):
    """A whole attacker or blocker declaration, submitted in one go.

    The engine declares combat incrementally; the server loops the increments so
    the human UX stays "select everything, then confirm".
    """

    seat: int
    kind: Literal["attackers", "blockers"]
    pairs: list[list[int]] = Field(default_factory=list)


class GameCreatedResponse(BaseModel):
    game_id: str
    your_seat: int
    state: dict[str, Any]
    actions: list[LegalActionDTO]


class StateResponse(BaseModel):
    state: dict[str, Any]
    actions: list[LegalActionDTO]
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_cursor: int = 0


class DeckSummary(BaseModel):
    id: str
    name: str
    commanders: list[str]
    commander_names: list[str]
    color_identity: list[str]
    card_count: int
    notes: str = ""


class CardResponse(BaseModel):
    id: str
    name: str
    type_line: str
    mana_cost: str
    mana_value: int
    oracle_text: str
    power: int | None = None
    toughness: int | None = None
    keywords: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list)
