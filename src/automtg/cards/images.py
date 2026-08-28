"""Card art: the catalog index, and how an engine card finds its printing.

The engine's cards are hand-written JSON in ``data/cards/`` with no art field, so
the art has to come from outside.  It comes from a Scryfall bulk dump, which
``scripts/build_card_index.py`` reduces to two committed artifacts:

``data/catalog/cards.sqlite``
    Every distinct English card name that has art -- ~37k rows.  Opened
    read-only and lazily, because loading 37k rows at import time would tax the
    trainer and the arena for a thing only the catalog search endpoint uses.

``data/catalog/registry_images.json``
    ~20 KB: one entry per card the engine actually ships.  This is what the
    server reads at boot, and it is the only one the game path touches.

Image *bytes* are not in the dump -- every record carries URLs on
``cards.scryfall.io``.  ``scripts/fetch_card_art.py`` downloads them once into
``data/art/``, after which nothing at runtime depends on Scryfall being up.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from .registry import data_dir, generated_dir

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.carddef import CardDef

#: Scryfall's image CDN.  Contacted by the fetch script and by the lazy fill in
#: the ``/art`` route -- never by the client, and never during a game.
IMAGE_HOST = "https://cards.scryfall.io"

#: The sizes Scryfall serves.  ``art_crop`` is the bare art band, which is what a
#: card frame wants; ``normal`` is the whole rendered card.
ART_CROP = "art_crop"
NORMAL = "normal"

#: ``.jpg`` for every size this code asks for.  The newer webp-only sizes
#: (``thumb``, ``grid``, ``display``) are deliberately not offered.
_JPG_SIZES = frozenset({"small", "normal", "large", ART_CROP, "border_crop"})


def catalog_path() -> Path:
    return data_dir() / "catalog" / "cards.sqlite"


def registry_images_path() -> Path:
    return data_dir() / "catalog" / "registry_images.json"


def generated_images_path() -> Path:
    """The same shape as :func:`registry_images_path`, for imported cards.

    A second file rather than an edit to the committed one, so that rebuilding
    the catalog can never sweep somebody's imported card into version control.
    """
    return generated_dir() / "cards" / "pool.images.json"


def art_dir() -> Path:
    return data_dir() / "art"


def image_url(scryfall_id: str, size: str = ART_CROP, *, back: bool = False) -> str:
    """The CDN URL for a printing.

    Every Scryfall image URL is a pure function of the card's 36-char id, so the
    index stores an id and derives the rest.  Storing the URLs verbatim instead
    would add ~180 bytes a row -- about 6.7 MB of pure redundancy across 37k
    rows.  The ``?<timestamp>`` cache-buster Scryfall appends is optional; the
    URL resolves without it.
    """
    if size not in _JPG_SIZES:
        raise ValueError(f"unsupported image size {size!r}")
    if len(scryfall_id) < 2:
        raise ValueError(f"implausible scryfall id {scryfall_id!r}")
    face = "back" if back else "front"
    return f"{IMAGE_HOST}/{size}/{face}/{scryfall_id[0]}/{scryfall_id[1]}/{scryfall_id}.jpg"


@dataclass(frozen=True)
class IndexEntry:
    """One printing, as the index stores it."""

    name: str
    scryfall_id: str
    oracle_id: str | None = None
    set_code: str = ""
    rarity: str = ""
    layout: str = "normal"
    type_line: str = ""
    mana_cost: str = ""
    cmc: float = 0.0
    power: str | None = None
    toughness: str | None = None
    colors: str = ""
    color_identity: str = ""
    is_token: bool = False
    artist: str | None = None
    #: Printed rules text, newlines intact.  The proxy generator reads it line by
    #: line, so joining the lines here would destroy the only signal separating a
    #: keyword line from a sentence.
    oracle_text: str = ""
    #: Scryfall's keyword list, comma-joined.  Beware: it includes keywords the
    #: card *grants* as well as ones it has, which is why ``proxy.py`` only ever
    #: uses it to cross-check what it found in ``oracle_text``.
    keywords: str = ""
    #: The mana symbols this card can produce, comma-joined.  Without it there is
    #: no honest way to give a generated land a mana ability, and a deck whose
    #: lands are inert is not a deck.
    produced_mana: str = ""
    #: EDHREC's popularity rank, 1 = most played.  ``None`` for the 12% of
    #: printings it does not cover.  The card-authoring queue orders by this:
    #: there are 32k cards and finite effort, so the ones people actually play
    #: are worth implementing first, and alphabetical order is worth nothing.
    edhrec_rank: int | None = None
    #: The **back face** of a double-faced card, whose two faces are separate
    #: objects -- `transform` and `modal_dfc`. Empty for every other layout,
    #: including `split` and `adventure`, whose halves are two halves of one
    #: object and are joined into `oracle_text` instead.
    #:
    #: There is one row per physical card and the back is not a card of its own,
    #: so it rides along in columns of its own rather than as a second row: a
    #: row keyed `(name, is_token)` on the back face's name would be a card the
    #: importer could put in a deck.
    #:
    #: Without these the back face's printed lines existed **nowhere in the
    #: repo** for 488 cards. Nothing said so -- the front face's text loaded,
    #: validated and rendered perfectly well -- and an authoring worker handed
    #: only the front had no way to know the rest of the card was missing.
    back_name: str = ""
    back_type_line: str = ""
    back_mana_cost: str = ""
    back_power: str | None = None
    back_toughness: str | None = None
    back_oracle_text: str = ""

    @property
    def has_back_face(self) -> bool:
        return bool(self.back_name)

    def art_url(self) -> str:
        return image_url(self.scryfall_id, ART_CROP)

    def normal_url(self) -> str:
        return image_url(self.scryfall_id, NORMAL)

    def keyword_list(self) -> tuple[str, ...]:
        return tuple(k for k in self.keywords.split(",") if k)

    def produced_list(self) -> tuple[str, ...]:
        return tuple(m for m in self.produced_mana.split(",") if m)


#: Column order shared by the writer and the reader, so the two cannot drift.
COLUMNS = (
    "name",
    "scryfall_id",
    "oracle_id",
    "set_code",
    "rarity",
    "layout",
    "type_line",
    "mana_cost",
    "cmc",
    "power",
    "toughness",
    "colors",
    "color_identity",
    "is_token",
    "artist",
    "oracle_text",
    "keywords",
    "produced_mana",
    "edhrec_rank",
    "back_name",
    "back_type_line",
    "back_mana_cost",
    "back_power",
    "back_toughness",
    "back_oracle_text",
)

SCHEMA = f"""
CREATE TABLE cards (
    {COLUMNS[0]} TEXT NOT NULL,
    {COLUMNS[1]} TEXT NOT NULL,
    {COLUMNS[2]} TEXT,
    {COLUMNS[3]} TEXT,
    {COLUMNS[4]} TEXT,
    {COLUMNS[5]} TEXT,
    {COLUMNS[6]} TEXT,
    {COLUMNS[7]} TEXT,
    {COLUMNS[8]} REAL,
    {COLUMNS[9]} TEXT,
    {COLUMNS[10]} TEXT,
    {COLUMNS[11]} TEXT,
    {COLUMNS[12]} TEXT,
    {COLUMNS[13]} INTEGER NOT NULL DEFAULT 0,
    {COLUMNS[14]} TEXT,
    {COLUMNS[15]} TEXT,
    {COLUMNS[16]} TEXT,
    {COLUMNS[17]} TEXT,
    {COLUMNS[18]} INTEGER,
    {COLUMNS[19]} TEXT,
    {COLUMNS[20]} TEXT,
    {COLUMNS[21]} TEXT,
    {COLUMNS[22]} TEXT,
    {COLUMNS[23]} TEXT,
    {COLUMNS[24]} TEXT,
    -- Not `name` alone.  87 names are printed both as a real card and as a
    -- token -- Tarmogoyf, Champion of Wits, Adorned Pouncer -- and with `name`
    -- as the sole key whichever printing happened to win the sort evicted the
    -- other.  That silently made 87 real Commander playables unreachable by
    -- name, which a deck importer notices immediately and a search box does not.
    PRIMARY KEY (name, is_token)
);
CREATE INDEX idx_cards_name_nocase ON cards(name COLLATE NOCASE);
CREATE INDEX idx_cards_token ON cards(is_token);
-- `name` is the primary key, so a lookup by uuid would otherwise scan all 32k
-- rows.  The catalog-card route and the importer's last-chance match both go
-- through it.
CREATE INDEX idx_cards_scryfall ON cards(scryfall_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _row_to_entry(row: sqlite3.Row | tuple) -> IndexEntry:
    values = tuple(row)
    return IndexEntry(
        name=values[0],
        scryfall_id=values[1],
        oracle_id=values[2],
        set_code=values[3] or "",
        rarity=values[4] or "",
        layout=values[5] or "normal",
        type_line=values[6] or "",
        mana_cost=values[7] or "",
        cmc=values[8] or 0.0,
        power=values[9],
        toughness=values[10],
        colors=values[11] or "",
        color_identity=values[12] or "",
        is_token=bool(values[13]),
        artist=values[14],
        oracle_text=values[15] or "",
        keywords=values[16] or "",
        produced_mana=values[17] or "",
        edhrec_rank=values[18],
        back_name=values[19] or "",
        back_type_line=values[20] or "",
        back_mana_cost=values[21] or "",
        back_power=values[22],
        back_toughness=values[23],
        back_oracle_text=values[24] or "",
    )


#: Columns added after the first build.  An index written before them is still
#: perfectly good for art, which is all the game path wants, so :class:`CardIndex`
#: selects ``NULL`` for whichever are absent rather than failing to open -- a
#: fresh clone must boot on whatever it was handed.
LATE_COLUMNS = frozenset(
    {
        "oracle_text",
        "keywords",
        "produced_mana",
        "edhrec_rank",
        "back_name",
        "back_type_line",
        "back_mana_cost",
        "back_power",
        "back_toughness",
        "back_oracle_text",
    }
)


def _select_for(present: set[str]) -> str:
    fields = [col if col in present else f"NULL AS {col}" for col in COLUMNS]
    return f"SELECT {', '.join(fields)} FROM cards"


_SELECT = _select_for(set(COLUMNS))


class CardIndex:
    """Read-only access to ``cards.sqlite``.

    Queries touch pages rather than materialising 37k dicts, which is the whole
    reason this is a database and not the newline-delimited JSON that would
    diff more nicely in git.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        # ``mode=ro`` so a bug here can never corrupt a committed artifact, and
        # ``check_same_thread=False`` because Starlette serves from a threadpool.
        self._con = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        present = {row[1] for row in self._con.execute("PRAGMA table_info(cards)")}
        self.late_columns_present = present >= LATE_COLUMNS
        self._select = _select_for(present)

    def close(self) -> None:
        self._con.close()

    def __len__(self) -> int:
        return int(self._con.execute("SELECT COUNT(*) FROM cards").fetchone()[0])

    def meta(self) -> dict[str, str]:
        try:
            return dict(self._con.execute("SELECT key, value FROM meta").fetchall())
        except sqlite3.Error:  # pragma: no cover -- an index built before `meta`
            return {}

    def lookup(
        self, name: str, *, token: bool | None = None, joined: bool = False
    ) -> IndexEntry | None:
        """One printing by exact name, case-insensitively.

        ``token=True`` restricts to token printings, which is what makes an
        engine token named "Vampire Lifelink Token" resolve to the Scryfall
        token named "Vampire" rather than to some real card that happens to
        share a word.

        Left unrestricted, a name printed as *both* -- there are 87 -- resolves
        to the **real card**.  A deck can hold Tarmogoyf and cannot hold the
        token that shares its name, so preferring the card is the only ordering
        that makes an unqualified lookup useful.

        ``joined=True`` matches one *face* of a double-faced card against the
        joined name the catalog stores it under: the index reduces every card to
        one row, and a transforming card's row is called "Bloodline Keeper //
        Lord of Lineage", so neither "Bloodline Keeper" nor "Lord of Lineage"
        finds it. Anchored on either side of the ``//`` so that a face name is
        never matched mid-word.
        """
        if not name:
            return None
        if joined:
            sql = (
                f"{self._select} WHERE is_token = 0 AND (name LIKE ? COLLATE NOCASE "
                f"OR name LIKE ? COLLATE NOCASE)"
            )
            row = self._con.execute(sql, [f"{name} // %", f"% // {name}"]).fetchone()
            return _row_to_entry(row) if row else None
        sql = f"{self._select} WHERE name = ? COLLATE NOCASE"
        params: list[object] = [name]
        if token is not None:
            sql += " AND is_token = ?"
            params.append(1 if token else 0)
        else:
            sql += " ORDER BY is_token"
        row = self._con.execute(sql, params).fetchone()
        return _row_to_entry(row) if row else None

    def by_scryfall_id(self, scryfall_id: str) -> IndexEntry | None:
        """One printing by uuid.

        The importer's last-chance match, for a card Moxfield knows under a name
        this dump does not carry -- a rename, or a printing newer than the
        bundle.  ``idx_cards_scryfall`` is what keeps it a lookup.
        """
        if not scryfall_id:
            return None
        row = self._con.execute(
            f"{self._select} WHERE scryfall_id = ?", (scryfall_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def search(
        self,
        query: str = "",
        *,
        colors: str | None = None,
        types: str | None = None,
        limit: int = 50,
    ) -> tuple[int, list[IndexEntry]]:
        """Substring search, ranked exact -> prefix -> contains -> alphabetical.

        Returns the *unclamped* match count alongside the clamped page, so a UI
        can say "showing 50 of 312" rather than silently truncating.
        """
        where: list[str] = []
        params: list[object] = []
        if query:
            where.append("name LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(query)}%")
        if types:
            where.append("type_line LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(types)}%")
        if colors:
            # Every requested colour must appear in the identity.
            for symbol in dict.fromkeys(colors.upper()):
                where.append("color_identity LIKE ? ESCAPE '\\'")
                params.append(f"%{_escape_like(symbol)}%")
        clause = f" WHERE {' AND '.join(where)}" if where else ""

        total = int(
            self._con.execute(f"SELECT COUNT(*) FROM cards{clause}", params).fetchone()[0]
        )

        order = "name COLLATE NOCASE"
        rank_params: list[object] = []
        if query:
            # Rank in SQL so the LIMIT applies after ordering, not before it.
            order = (
                "CASE WHEN name = ? COLLATE NOCASE THEN 0 "
                "WHEN name LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END, name COLLATE NOCASE"
            )
            rank_params = [query, f"{_escape_like(query)}%"]

        # Placeholders bind in statement order: WHERE, then ORDER BY, then LIMIT.
        rows = self._con.execute(
            f"{self._select}{clause} ORDER BY {order} LIMIT ?",
            [*params, *rank_params, limit],
        ).fetchall()
        return total, [_row_to_entry(row) for row in rows]

    def iter_all(self) -> Iterator[IndexEntry]:
        for row in self._con.execute(f"{self._select} ORDER BY name"):
            yield _row_to_entry(row)

    def iter_by_popularity(self, *, limit: int | None = None) -> Iterator[IndexEntry]:
        """Real cards, most-played first.

        The card-authoring queue's default order.  Cards EDHREC does not rank sort
        last rather than being dropped -- they are still cards, just not ones worth
        spending the first thousand units of effort on.  ``name`` breaks ties so a
        rebuild does not reshuffle the queue.
        """
        sql = (
            f"{self._select} WHERE is_token = 0 "
            "ORDER BY edhrec_rank IS NULL, edhrec_rank, name"
        )
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        for row in self._con.execute(sql):
            yield _row_to_entry(row)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@lru_cache(maxsize=2)
def load_index(path: str | None = None) -> CardIndex | None:
    """The big index, opened at most once per process.

    Returns ``None`` rather than raising when the file is absent: a fresh clone
    that has not run the build script must still be able to start a game, and
    every caller already has to handle "this card has no art".
    """
    target = Path(path) if path else catalog_path()
    if not target.exists():
        return None
    try:
        return CardIndex(target)
    except sqlite3.Error:  # pragma: no cover -- a truncated or non-sqlite file
        return None


# ----------------------------------------------------------------------
# engine card -> printing
# ----------------------------------------------------------------------


def strip_token_suffix(name: str) -> str:
    """``"Beast Token"`` -> ``"Beast"``."""
    return name[: -len(" Token")].strip() if name.endswith(" Token") else name


def token_key(card: CardDef) -> str:
    """What Scryfall calls this token: its subtypes, in printed order.

    A plain ``" Token"`` strip is *not* enough, and the failure is silent.
    ``data/cards/tokens.cards.json`` names one token "Vampire Lifelink Token";
    stripping the suffix gives "Vampire Lifelink", which has no printing at all,
    so the card would fall back to the no-art plate forever.  Its subtypes are
    ``{"Vampire"}``, and "Vampire" is exactly what Scryfall names the printing.

    ``build_type_line`` already sorts subtypes alphabetically, so a two-subtype
    token like ``{"Frog", "Lizard"}`` renders "Frog Lizard" here and there.
    """
    return " ".join(sorted(card.subtypes)) or card.name


def resolve(card: CardDef, index: CardIndex) -> IndexEntry | None:
    """The printing to take art from, or ``None`` when there is no such card.

    ``None`` is a real, expected answer: five cards in ``data/cards/`` are
    custom designs with no printing anywhere, and the client draws them a
    deliberate "no art" plate rather than a broken image.
    """
    if card.is_token:
        for key in (token_key(card), card.name, strip_token_suffix(card.name)):
            hit = index.lookup(key, token=True)
            if hit is not None:
                return hit
        # A few "tokens" have real printings -- Treasure and Food, for instance.
        return index.lookup(token_key(card))
    # A double-faced card is one row in the catalog, under the joined name
    # ("Bloodline Keeper // Lord of Lineage"), so neither face resolves on its
    # own. Both faces look up that row; which *image* they take from it is
    # `CardArt.back`, since `image_url` has always taken a face.
    if (joined := dfc_key(card, index)) is not None:
        return joined
    return index.lookup(card.name) or index.lookup(strip_token_suffix(card.name))


def dfc_key(card: CardDef, index: CardIndex) -> IndexEntry | None:
    """The catalog row for a two-faced card, from either of its faces.

    Both links, because the catalog does not distinguish them: a modal DFC, a
    split card and an Adventure are each one row under the joined name, exactly
    as a transforming card is. ``back_face``/``front_face`` is the transform
    link and ``second_face``/``parent_face`` is the second-castable-face one --
    Malakir Mire resolves through the second, and resolved to nothing until it
    was asked about.

    Returns ``None`` for a single-faced card, so the ordinary path is untouched.
    """
    if (
        card.back_face is None
        and card.front_face is None
        and card.second_face is None
        and card.parent_face is None
    ):
        return None
    return index.lookup(card.name, joined=True)


# ----------------------------------------------------------------------
# the small artifact the server actually reads
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class CardArt:
    """What the server knows about one engine card's art."""

    card_id: str
    scryfall_id: str | None = None
    artist: str | None = None
    #: The **back** face of a transforming card. Both faces share one catalog
    #: row and one scryfall id -- the id is the card, not the face -- so this is
    #: what tells the two apart. Without it Lord of Lineage would download
    #: Bloodline Keeper's illustration and a transformed permanent would show
    #: the face it just turned away from.
    back: bool = False

    @property
    def has_printing(self) -> bool:
        return self.scryfall_id is not None

    def remote_url(self, size: str = ART_CROP) -> str | None:
        """Only ever used server-side, by the fetch script and the lazy fill."""
        if not self.scryfall_id:
            return None
        return image_url(self.scryfall_id, size, back=self.back)


def build_registry_images(registry, index: CardIndex) -> dict[str, CardArt]:
    """Resolve every card the engine ships.  Cards with no printing map to a
    ``CardArt`` with ``scryfall_id=None`` -- present, and explicitly artless."""
    out: dict[str, CardArt] = {}
    for card in registry:
        entry = resolve(card, index)
        out[card.id] = CardArt(
            card_id=card.id,
            scryfall_id=entry.scryfall_id if entry else None,
            artist=entry.artist if entry else None,
            back=card.front_face is not None,
        )
    return out


def write_registry_images(images: dict[str, CardArt], path: Path) -> None:
    payload = {
        card_id: (
            None
            if not art.has_printing
            else (
                {"scryfall_id": art.scryfall_id, "artist": art.artist}
                | ({"back": True} if art.back else {})
            )
        )
        for card_id, art in sorted(images.items())
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_registry_images(path: Path | None = None) -> dict[str, CardArt]:
    """The boot-time read.  Missing file is not an error -- the app renders text
    frames and the client draws plates."""
    target = path or registry_images_path()
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover
        return {}
    out: dict[str, CardArt] = {}
    for card_id, entry in raw.items():
        if entry is None:
            out[card_id] = CardArt(card_id=card_id)
        else:
            out[card_id] = CardArt(
                card_id=card_id,
                scryfall_id=entry.get("scryfall_id"),
                artist=entry.get("artist"),
                back=bool(entry.get("back")),
            )
    return out
