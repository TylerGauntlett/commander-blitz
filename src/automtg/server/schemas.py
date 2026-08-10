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
    #: ``label`` without its ``" -> target"`` suffix, so the client can tell
    #: "six ways to aim one Simic Charm" from "six copies of Simic Charm" and
    #: render the first as one row with six chips.  Falls back to ``label`` for
    #: the kinds that never name a target, so it is always safe to group by.
    base_label: str = ""
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
    #: The session's mutation counter.  Feed it back as ``?since_version=`` to
    #: long-poll for somebody else's move.
    version: int = 1


class StateResponse(BaseModel):
    state: dict[str, Any]
    actions: list[LegalActionDTO]
    events: list[dict[str, Any]] = Field(default_factory=list)
    event_cursor: int = 0
    #: See :class:`GameCreatedResponse.version`.
    version: int = 1
    #: The seat this view is for.  Echoed back because a client arriving from a
    #: pod does not know it: the lobby's four chairs are compacted down to the
    #: players who are actually in the game, so lobby seat 2 is table seat 1.
    your_seat: int = 0
    #: Which seats are people.  The engine does not model this -- a seat is a
    #: seat to it -- but the client's behaviour turns on it: waiting for an AI
    #: means pumping it forward a decision at a time, and waiting for a human
    #: means long-polling until they move.
    human_seats: list[int] = Field(default_factory=list)


class DeckSummary(BaseModel):
    id: str
    name: str
    commanders: list[str]
    commander_names: list[str]
    color_identity: list[str]
    card_count: int
    notes: str = ""
    #: "precon" or "moxfield".  Lets a deck tile carry its own badge without the
    #: client fetching anything else.
    source: str = "precon"
    #: Cards whose printed text this engine represents in full, and cards whose
    #: non-keyword text does nothing.  A precon is all playable by construction.
    playable: int = 0
    simplified: int = 0
    #: Editorial, authored per deck.  Empty for an imported deck, and the client
    #: draws that state rather than inventing a strategy paragraph.
    tags: list[str] = Field(default_factory=list)


class DeckRatingsDTO(BaseModel):
    """Five 1-4 scales.  See ``DeckRatingsModel``."""

    speed: int
    complexity: int
    interaction: int
    resilience: int
    pilot: int


class SignatureCardDTO(BaseModel):
    card_id: str
    name: str
    why: str
    art_url: str | None = None


class DeckDetail(DeckSummary):
    """Everything the deck dossier shows.

    Split from :class:`DeckSummary` because the catalogue renders every deck as a
    tile and would otherwise pay for four strategy essays it is not showing.
    """

    ratings: DeckRatingsDTO | None = None
    strategy: str = ""
    signature: list[SignatureCardDTO] = Field(default_factory=list)
    #: Seven buckets -- mana values 1..6 and 7+ -- of non-land cards, weighted by
    #: quantity.  Lands are excluded: with 37 of them in a 100-card deck they
    #: would dominate the first bucket and tell you nothing about the deck.
    curve: list[int] = Field(default_factory=list)
    lands: int = 0
    #: Cards the deck could not run as printed.  Already recorded in every deck
    #: file and, until now, never sent to the client.
    swaps: int = 0
    swap_note: str = ""


# ----------------------------------------------------------------------
# pods -- the pre-game lobby
# ----------------------------------------------------------------------


class PodSeatView(BaseModel):
    """One of a pod's four chairs, as one viewer is allowed to see it."""

    index: int
    #: ``empty`` -- nobody, and not yet invited.
    #: ``open``  -- a chair held for a human who has not arrived.
    #: ``cpu``   -- an AI the host seated.
    #: ``human`` -- somebody in the pod.
    kind: Literal["empty", "cpu", "open", "human"]
    name: str | None = None
    #: ``None`` until this seat locks in.  The lobby's hidden-information rule,
    #: and the reason a pod is rendered through ``Pod.view_for`` and nothing
    #: else -- exactly as a game is rendered through ``player_view``.
    deck: DeckSummary | None = None
    locked: bool = False
    ready: bool = False
    is_you: bool = False
    is_host: bool = False
    #: CPU seats only.
    agent: str | None = None


class PodView(BaseModel):
    code: str
    #: Monotonic. Feed it back as ``?since=`` to long-poll for somebody else's
    #: move; the server blocks until it moves or the poll times out.
    version: int
    status: Literal["open", "starting", "in_game", "closed"]
    seats: list[PodSeatView]
    your_seat: int | None = None
    you_are_host: bool = False
    #: Set the moment the host deals.  Every client polling the pod learns where
    #: the table is from the same response, which is how they arrive together.
    game_id: str | None = None
    invite_link: str = ""


class CreatePodRequest(BaseModel):
    name: str = Field(default="You", max_length=24)
    deck_id: str | None = None
    seed: int | None = None


class JoinPodRequest(BaseModel):
    name: str = Field(default="Player", max_length=24)


class PodCredentials(BaseModel):
    """Returned exactly once, at create or join.  Never inside a ``PodView``."""

    player_token: str
    pod: PodView


class SeatUpdateRequest(BaseModel):
    """Your own seat: pick a deck, lock in, unlock.

    Both fields are optional and independently applied, so "pick a deck" and
    "lock in" are one request or two at the client's discretion.
    """

    deck_id: str | None = None
    locked: bool | None = None


class StartPodRequest(BaseModel):
    """Dealing the pod.

    The seed rides on the deal rather than on the pod, because that is when the
    host actually types it -- a seed set at create time would be a number chosen
    before anybody knows what game they are about to play.
    """

    seed: int | None = None


class SeatAdminRequest(BaseModel):
    """A seat that is not yours.  Host only."""

    action: Literal["add_cpu", "open_chair", "clear", "set_deck", "set_agent"]
    deck_id: str | None = None
    agent: Literal["random", "heuristic", "policy"] | None = None


class ImportDeckRequest(BaseModel):
    url: str = Field(max_length=400)
    #: Report what would happen without writing anything, so the coverage panel
    #: can be shown before the deck is committed to disk.
    dry_run: bool = False


class ImportedCardDTO(BaseModel):
    name: str
    qty: int
    card_id: str
    #: ``native`` -- a hand-written card, reused whole.
    #: ``full``   -- generated, and nothing was lost.
    #: ``partial``-- generated, non-keyword rules text inert.
    origin: Literal["native", "full", "partial"]
    notes: list[str] = Field(default_factory=list)


class DeckImportResponse(BaseModel):
    deck: DeckSummary
    source: str = "moxfield"
    source_id: str
    total: int
    playable: int
    simplified: int
    #: The mana base, called out on its own: a deck that looks like 37 lands and
    #: behaves like 34 is the most confusing thing an import can produce.
    #: ``lands_inert`` rather than ``lands - lands_producing_mana`` is what the
    #: screen warns about, because a fetchland makes no mana and is not broken.
    lands: int = 0
    lands_producing_mana: int = 0
    lands_inert: int = 0
    cards: list[ImportedCardDTO] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


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
