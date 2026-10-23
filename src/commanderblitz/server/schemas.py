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
    #: What this copy's chip says when the row is a group and the difference is
    #: not the target -- "{R}" for one yield of "Add one mana of any colour".
    #: Empty means "name it by its target", which is the common case.
    option_label: str = ""
    source_oid: int | None = None
    ability_index: int | None = None
    targets: list[dict[str, Any]] = Field(default_factory=list)
    choice: int | None = None
    x: int = 0
    #: Permanents the solver would tap to pay for this. A forecast for the UI,
    #: not a commitment -- payment is re-solved when the action is applied.
    pays: list[int] = Field(default_factory=list)
    #: For an action that names targets: oid -> why that permanent could not be
    #: named by this spell or ability at all ("Hexproof", "Shroud", "Protection
    #: from red"). Display only, so a player hovering a card the targeting skips
    #: is told why; the action list is still the whole of what is legal.
    untargetable: dict[str, str] = Field(default_factory=dict)


class ApplyActionRequest(BaseModel):
    seat: int
    action_id: str
    #: The ``version`` of the state response ``action_id`` was read from.
    #: Action ids are positional, so they only mean something against the list
    #: they came from; with this the server can tell a click on a list it has
    #: since replaced (409 ``stale_action``) from a bad id (400).  Optional so a
    #: script or an older client keeps working.
    version: int | None = None


class DeclareRequest(BaseModel):
    """A whole attacker or blocker declaration, submitted in one go.

    The engine declares combat incrementally; the server loops the increments so
    the human UX stays "select everything, then confirm".
    """

    seat: int
    kind: Literal["attackers", "blockers"]
    pairs: list[list[int]] = Field(default_factory=list)


class ChooseRequest(BaseModel):
    """A pick-several decision answered with the whole set at once.

    ``choices`` are ordinals into the pending decision's ``options``.
    """

    seat: int
    choices: list[int] = Field(default_factory=list)


class OptionsRequest(BaseModel):
    """Per-seat play settings that are preferences, not rules."""

    seat: int
    #: Stop at every priority window instead of only the meaningful ones.
    full_control: bool
    #: Choose which permanent to tap for mana, and which colour a dual makes,
    #: instead of letting the payment solver decide.  Optional so a client that
    #: predates it can still send an options request without turning it off.
    manual_mana: bool | None = None


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
    #: The Moxfield public id an import came from, case preserved; ``""`` for a
    #: precon.  The desktop sends these to the hosted server so a deck imported
    #: at home can be imported there too.
    source_id: str = ""
    #: Cards whose printed text this engine represents in full, and cards whose
    #: non-keyword text does nothing.  A precon is all playable by construction.
    playable: int = 0
    simplified: int = 0
    #: Editorial, authored per deck.  Empty for an imported deck, and the client
    #: draws that state rather than inventing a strategy paragraph.
    tags: list[str] = Field(default_factory=list)
    #: ``False`` when this machine is still missing illustrations the deck can
    #: have, so it would play with blank plates offline (ADR 0022).  ``None``
    #: means nobody checked, which is every deck the hosted server lists.
    complete: bool | None = None


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
    #: The pod's address in the client, relative: `/pods/GYRE-8412`.  Relative
    #: because the server does not know what host the browser reached it on --
    #: over a LAN that is a machine address it has no way to guess -- so an
    #: absolute link it built would say `localhost` and work for one person.
    #: The client resolves it against `window.location`.
    invite_link: str = ""


#: The longest a player may call themselves.  One number, because the door, the
#: join and the seat plate are three ways into the same field.
MAX_NAME_LENGTH = 24


class CreatePodRequest(BaseModel):
    #: Omitted by the client: the front door asks for a code, not a name, and
    #: the lobby's own seat plate is where you say who you are.  ``None`` rather
    #: than a literal default so the seat-numbered fallback in ``PodRegistry``
    #: is the only place that decides what an unnamed chair is called.
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    deck_id: str | None = None
    seed: int | None = None


class JoinPodRequest(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)


class PodCredentials(BaseModel):
    """Returned exactly once, at create or join.  Never inside a ``PodView``."""

    player_token: str
    pod: PodView


class SeatUpdateRequest(BaseModel):
    """Your own seat: say who you are, pick a deck, lock in, unlock.

    Every field is optional and independently applied, so "pick a deck" and
    "lock in" are one request or two at the client's discretion.
    """

    deck_id: str | None = None
    locked: bool | None = None
    #: What you want to be called at this table.  Deliberately *not* gated on
    #: ``locked``: the lock is a commitment to a deck, and making somebody
    #: unlock -- which un-readies the pod for everybody else -- to fix a typo in
    #: their own name would be a worse rule than the one it enforced.
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)


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


class ArtPrefetchDTO(BaseModel):
    """What an eager art fetch did, and whether the deck is done (ADR 0022)."""

    fetched: int
    cached: int
    failed: list[str] = Field(default_factory=list)
    #: The verdict: every illustration the deck can have is on this machine.
    complete: bool = False
    #: Card ids that have a printing somewhere and no file here yet.  A card
    #: with no printing anywhere is in ``failed`` and never in ``missing``.
    missing: list[str] = Field(default_factory=list)


class DeckCompletionDTO(BaseModel):
    """One deck that ``POST /api/decks/complete`` looked at."""

    deck_id: str
    fetched: int
    complete: bool
    missing: list[str] = Field(default_factory=list)


class DeckBundle(BaseModel):
    """A deck as a machine needs it to play the deck offline (ADR 0022).

    ``deck`` is the deck file exactly as the site wrote it.  ``cards`` holds
    the definition of every card it names, plus the faces and tokens those
    reach, in the card-file shape.  ``coverage`` is the importer's verdict on
    each generated card in it, for the cards the site wrote as proxies.
    ``images`` is which printing shows each card, ``None`` for a card with
    none: a machine that has never seen a card has no other way to know.
    """

    deck: dict
    cards: list[dict]
    coverage: dict[str, dict] = Field(default_factory=dict)
    images: dict[str, dict | None] = Field(default_factory=dict)


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
    #: Present only when the server fetches a deck's art at import time (the
    #: desktop build does; the site fills lazily and sends nothing here).
    art_prefetch: ArtPrefetchDTO | None = None


class AppConfig(BaseModel):
    """What kind of server answered, and whether the other kind is reachable.

    The client's one source for "am I the desktop build" and "can I play
    online right now".  It reads neither from its origin: a desktop that lost
    its connection is still on ``127.0.0.1`` and still cannot join a pod.
    """

    mode: Literal["desktop", "hosted"]
    #: Whether the hosted server answered a recent probe.  Always true when
    #: this *is* the hosted server.
    online: bool
    #: Where to go to play with friends.  ``None`` on the hosted server.
    remote_origin: str | None = None
    #: The package version, and the content package version the desktop shell
    #: is running (the same number on the hosted server).
    app_version: str
    content_version: str


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
    #: ``seat index -> card id -> ref``, for the cards a seat's deck prints
    #: differently from the catalog's pick.  Empty without ``?game_id=``, and
    #: empty for a deck that named no printings -- which is every precon.
    #:
    #: A second layer rather than an edit to ``images`` because two seats can
    #: hold the same card id and want different illustrations; a flat map cannot
    #: say that.  Keyed by seat index because that is what ``CardView.owner``
    #: already carries, so the client needs nothing it does not have.
    #:
    #: Entries are **whole refs, never patches**.  An override whose illustrator
    #: we do not know carries ``artist: null``; merging field by field would
    #: credit the catalog printing's artist for somebody else's painting.
    seats: dict[str, dict[str, ImageRefDTO]] = Field(default_factory=dict)


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
