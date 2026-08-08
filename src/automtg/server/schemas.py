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
    #: Permanents the solver would tap to pay for this. A forecast for the UI,
    #: not a commitment -- payment is re-solved when the action is applied.
    pays: list[int] = Field(default_factory=list)


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


class OptionsRequest(BaseModel):
    """Per-seat play settings that are preferences, not rules."""

    seat: int
    #: Stop at every priority window instead of only the meaningful ones.
    full_control: bool


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
    #: Same-origin path, never a third-party URL.  ``None`` means this card has
    #: no printing and the client should draw its "no art" plate.
    art_url: str | None = None
    artist: str | None = None


class ImageRefDTO(BaseModel):
    """Where one card's art lives.

    Deliberately carries no ``cards.scryfall.io`` URL: the browser only ever
    talks to this server, so the board keeps working when Scryfall is rate
    limiting, down, or simply unreachable.
    """

    card_id: str
    art: str | None = None
    artist: str | None = None


class ImagesResponse(BaseModel):
    """Every card the engine ships, in one response.

    Fetched once at boot and cached forever, rather than riding along on
    ``card_view``.  The image is a function of the immutable ``card_id``, and
    ``player_view`` re-serialises ~90 cards on every poll of the AI pump -- so
    putting it there would re-send a constant thousands of times a game.
    """

    art_base: str = "/art"
    images: dict[str, ImageRefDTO | None] = Field(default_factory=dict)


class CatalogCardDTO(BaseModel):
    """One card from the Scryfall-derived catalog, which is far larger than the
    engine's own registry and is not playable -- it backs search and deck
    building, not the board."""

    name: str
    scryfall_id: str
    oracle_id: str | None = None
    type_line: str = ""
    mana_cost: str = ""
    cmc: float = 0.0
    power: str | None = None
    toughness: str | None = None
    colors: list[str] = Field(default_factory=list)
    color_identity: list[str] = Field(default_factory=list)
    rarity: str = ""
    set_code: str = ""
    layout: str = "normal"
    is_token: bool = False
    artist: str | None = None
    art_url: str | None = None


class CatalogResponse(BaseModel):
    #: Unclamped match count, so a UI can say "showing 50 of 312" rather than
    #: silently truncating.
    total: int = 0
    results: list[CatalogCardDTO] = Field(default_factory=list)
