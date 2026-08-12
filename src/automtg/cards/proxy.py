"""Generating a playable card definition for a card nobody hand-wrote.

The engine plays the ~149 cards in ``data/cards/``.  An imported Commander deck
contains a hundred cards, most of which say things the DSL cannot express.  The
choice is between refusing every real deck and playing them with the text
simplified, and this module is the second answer:

    a generated card has the right name, art, mana cost, types, subtypes,
    power/toughness, colours and colour identity, plus any **keyword** abilities
    the engine implements and, for a permanent that taps for mana, a real mana
    ability.  Everything else its rules text claims does nothing.

That is a lie only if it is hidden, so every simplification is recorded in
``ProxyResult.notes`` verbatim and surfaced in the import report.  A card whose
whole text survives the trip is marked ``"full"`` and is not a simplification at
all -- a vanilla bear, a basic land and a Signet are all *exactly* right.

Two structural decisions:

**The input is always our own catalog row**, never the importer's payload.
Moxfield supplies a name and a quantity; every characteristic comes from
``cards.sqlite``, so a generated card's id, art and colour identity agree with
what ``/api/catalog`` already says, and a second importer would be an adapter
rather than a second generator.

**The output is a** :class:`~automtg.cards.schema.CardModel`, which then goes
through the ordinary :func:`~automtg.cards.loader.compile_card`.  A bug here is
therefore a ``DslError`` at import time rather than a mystery mid-game, and the
JSON is byte-for-byte the ``data/cards/*.cards.json`` format -- so *promoting* a
generated card is a copy-paste plus the abilities somebody writes by hand.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from automtg.engine.enums import CardType

from .images import IndexEntry
from .loader import KNOWN_KEYWORDS, KNOWN_SUPERTYPES, KNOWN_TYPES
from .schema import CardModel

#: Coverage of a generated card.  ``full`` means the printed text is *entirely*
#: represented -- there is nothing left over for the engine to be wrong about.
Coverage = Literal["full", "partial"]

#: The art path guard in ``server/art.py`` is stricter than the schema's id
#: validator, and the id becomes a filename, so the stricter one wins.
_ID_MAX = 72

#: Scryfall prints an em-dash; ``build_type_line`` emits ASCII " - "; older data
#: uses an en-dash.  Accepting all three costs nothing and mis-parsing the line
#: turns every subtype into a type.
#: The dashes are the literal characters printed on cards, not typos -- matching
#: them is the entire job, so RUF001's "did you mean a hyphen" does not apply.
_TYPE_SEPARATORS = ("—", "–", " - ")  # noqa: RUF001

#: Types that exist on cards but not in a game this engine models.  A card whose
#: types reduce to nothing but these cannot be generated at all.
_UNMODELLED_TYPES = frozenset(
    {
        "Dungeon", "Plane", "Scheme", "Phenomenon", "Vanguard",
        "Conspiracy", "Emblem", "Stickers", "Attraction", "Contraption",
    }
)

#: Always co-occur with a real type, so dropping them loses nothing structural.
_NOISE_TYPES = frozenset({"Kindred", "Tribal", "Summon"})

#: Layouts that are not a deck-legal card at all.
_UNPLAYABLE_LAYOUTS = frozenset(
    {
        "token", "double_faced_token", "emblem", "art_series",
        "planar", "scheme", "vanguard", "reversible_card",
    }
)

#: One physical card printed with two halves.  The front half is generated and
#: the other is noted as missing.
_SPLIT_LAYOUTS = frozenset({"split", "adventure", "flip"})

#: Two physical faces.  Same treatment, but worth a louder note: a modal DFC
#: land generated as its front face costs the deck a land it thought it had.
_TWO_FACED_LAYOUTS = frozenset({"transform", "modal_dfc", "meld"})

#: Characters NFKD does *not* decompose, because they are letters in their own
#: right rather than accented forms.  Without this, "Æther Vial" slugs to
#: "ther_vial" -- the leading letter silently vanishes.
_LIGATURES = str.maketrans(
    {"Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "Ø": "O", "ø": "o",
     "Ð": "D", "ð": "d", "Þ": "Th", "þ": "th", "ß": "ss", "Ł": "L", "ł": "l"}
)

_REMINDER = re.compile(r"\([^()]*\)")
_ENTERS_TAPPED = re.compile(r"\benters?\b[^.]*\btapped\b", re.I)

#: A tap-for-mana ability, capturing whatever the cost says *before* the ``{T}``.
#: That prefix is the whole point: ``{1}, {T}: Add {G}{U}`` is a Signet, and
#: dropping the ``{1}`` generates a card strictly cheaper than the real one.
_TAPS_FOR_MANA = re.compile(r"^(?P<pre>[^:]*?)\{T\}\s*(?:,\s*)?:\s*Add\b", re.I)

#: A cost prefix made only of mana symbols, which the engine can express.
_MANA_ONLY = re.compile(r"^(?:\{[^}]+\}[,\s]*)+$")

#: Lines that give the ability to *something else*.  Scryfall's text for an Aura
#: or a lord reads "Enchanted land has "{T}: Add {C}."" -- lifting that gives the
#: Aura its own mana ability.  Same trap as ``keywords`` listing what a card
#: grants; see :func:`lift_keywords`.
_GRANTS_TO_OTHERS = re.compile(
    r"^(enchanted|equipped|other|each other|creatures|lands|permanents|artifacts|"
    r"they|those)\b.*\b(has|have|gains?|gain)\b",
    re.I,
)


# ----------------------------------------------------------------------
# the shape the generator works in
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class CardFacts:
    """Everything the generator reads, decoupled from where it came from."""

    name: str
    scryfall_id: str
    type_line: str = ""
    mana_cost: str = ""
    oracle_text: str = ""
    keywords: tuple[str, ...] = ()
    produced_mana: tuple[str, ...] = ()
    power: str | None = None
    toughness: str | None = None
    colors: str = ""
    color_identity: str = ""
    layout: str = "normal"
    is_token: bool = False


@dataclass(frozen=True)
class ProxyResult:
    """A generated card, or the reason there is not one."""

    card_id: str
    model: CardModel | None = None
    coverage: Coverage = "partial"
    notes: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.model is not None


def facts_from_index(entry: IndexEntry) -> CardFacts:
    return CardFacts(
        name=entry.name,
        scryfall_id=entry.scryfall_id,
        type_line=entry.type_line,
        mana_cost=entry.mana_cost,
        oracle_text=entry.oracle_text,
        keywords=entry.keyword_list(),
        produced_mana=entry.produced_list(),
        power=entry.power,
        toughness=entry.toughness,
        colors=entry.colors,
        color_identity=entry.color_identity,
        layout=entry.layout or "normal",
        is_token=entry.is_token,
    )


# ----------------------------------------------------------------------
# ids
# ----------------------------------------------------------------------


def slug_for(name: str, scryfall_id: str = "", *, taken: set[str] | None = None) -> str:
    """A stable snake_case id for a card name.

    ``server/art.py``'s ``CARD_ID`` is ``^[a-z0-9_]{1,80}$`` and doubles as the
    path-traversal guard, since the id goes into a filename.  The schema's own
    validator is looser -- ``str.isalnum()`` is Unicode-aware and would happily
    accept ``Lim-Dûl`` -- so the guard is what this has to satisfy.

    Collisions resolve by appending six hex of the Scryfall id, **never** a
    counter: a counter makes the id depend on the order cards happened to be
    imported in, and these ids are filenames for art and keys in a deck list
    that has to survive a re-import unchanged.
    """
    folded = unicodedata.normalize("NFKD", name.translate(_LIGATURES))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "_", folded.casefold()).strip("_")
    if len(slug) > _ID_MAX:
        slug = slug[:_ID_MAX].rsplit("_", 1)[0] or slug[:_ID_MAX]
    if not slug:
        # A name that is entirely punctuation.  Rare, but "" is not an id.
        slug = f"card_{scryfall_id[:8]}" if scryfall_id else "card"
    if taken is not None and slug in taken:
        slug = f"{slug}_{scryfall_id[:6]}" if scryfall_id else slug
    return slug


# ----------------------------------------------------------------------
# type line
# ----------------------------------------------------------------------


def _front_half(type_line: str) -> str:
    return type_line.split("//")[0].strip()


def split_type_line(type_line: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """``(supertypes, types, subtypes, dropped)``.

    Subtypes are not validated against anything: ``compile_card`` checks types,
    supertypes and keywords only, so ``Kor Cleric`` and ``Praetor`` pass through
    untouched and no whitelist has to be maintained here.
    """
    front = _front_half(type_line)
    left, _, right = _partition(front)
    supertypes: list[str] = []
    types: list[str] = []
    dropped: list[str] = []
    for word in left.split():
        if word in KNOWN_SUPERTYPES:
            supertypes.append(word)
        elif word in KNOWN_TYPES:
            types.append(word)
        else:
            dropped.append(word)
    return supertypes, types, right.split(), dropped


def _partition(front: str) -> tuple[str, str, str]:
    for sep in _TYPE_SEPARATORS:
        if sep in front:
            left, _, right = front.partition(sep)
            return left.strip(), sep, right.strip()
    return front.strip(), "", ""


# ----------------------------------------------------------------------
# mana cost
# ----------------------------------------------------------------------


def simplify_mana_cost(cost: str, identity: str) -> tuple[str, list[str]]:
    """Rewrite symbols ``ManaCost.parse`` refuses, preserving mana value.

    This is not politeness: ``parse`` raises ``DslError`` on ``{W/U}``, and that
    exception travels all the way out through ``CardRegistry.from_paths``, so a
    single hybrid card in the generated pool would stop the *whole registry*
    loading at boot.  Rewriting here keeps the DSL's "unknown vocabulary is a
    load-time error" rule exactly as strict as it was.

    Every rewrite keeps the mana value the card was printed with, so curves,
    ``mana_value`` selectors and the AI's cost features stay honest even when the
    colour does not.
    """
    if not cost:
        return "", []
    notes: list[str] = []
    out: list[str] = []
    for symbol in re.findall(r"\{([^}]*)\}", _front_half(cost)):
        replacement = _simplify_symbol(symbol, identity)
        if replacement is None:
            out.append(f"{{{symbol}}}")
            continue
        notes.append(f"mana cost simplified: {{{symbol}}} -> {replacement}")
        out.append(replacement)
    return "".join(out), notes


def _simplify_symbol(symbol: str, identity: str) -> str | None:
    """``None`` means the symbol is already something the engine parses."""
    sym = symbol.strip().upper()
    if sym.isdigit() or sym == "X" or sym in ("W", "U", "B", "R", "G", "C"):
        return None
    if sym == "S":
        # Snow-ness is not a characteristic here, but the pip still costs one.
        return "{1}"
    if sym.startswith("H"):  # half mana, un-sets only
        return "{1}"
    if "/" in sym:
        left, _, right = sym.partition("/")
        if right == "P":  # phyrexian: paying life is not a mana payment here
            return f"{{{left}}}"
        # Ordinary hybrid -- {W/U} and {2/W} -- is parsed and paid properly now,
        # so it is left exactly as printed. Narrowing it to one half was always a
        # loss of the card's real flexibility; it only ever happened because
        # `parse` used to raise.
        return None
    # Something unrecognised entirely.  One generic keeps the curve plausible
    # and keeps `parse` from raising.
    return "{1}"


# ----------------------------------------------------------------------
# keywords
# ----------------------------------------------------------------------


def _strip_reminders(text: str) -> str:
    return _REMINDER.sub("", text)


def lift_keywords(
    oracle_text: str, printed: tuple[str, ...], *, strict: bool = False
) -> tuple[list[str], set[str]]:
    """``(keywords, the lines they consumed)``.

    Scryfall's ``keywords`` array lists keywords a card *grants* as well as ones
    it has, so a lord reading "Creatures you control have flying" carries
    ``Flying`` in it.  Lifting that blindly gives the lord flying.

    So the oracle text is the authority: a keyword is lifted only from a line
    that is *nothing but* keywords, separated by commas or semicolons.  Scryfall's
    array is used to cross-check, never as a source.  Parameterised keywords --
    "Ward {2}", "Protection from red", "Annihilator 2" -- are not in ``Keyword``
    at all, so they fall out of this on their own and land in the residual.

    The semicolon is Portal Three Kingdoms' house style -- "Haste; horsemanship"
    -- and it widens nothing: the check is still all-or-nothing over every part,
    so "Trample; rampage 2" and "First strike; banding" fail on their second
    part exactly as they did when the line was unsplittable.

    ``strict`` changes who ``printed`` is and therefore what consuming a line
    means.  Generating a proxy, ``printed`` is Scryfall's array and the line is
    consumed because the card being written is *about to be given* those
    keywords.  Auditing an existing card -- :func:`verify.claimed_lines` --
    ``printed`` is what that card actually has, and consuming a line it does not
    implement is the whole failure the residual gate exists to catch.  Simic Sky
    Swallower prints "Shroud" and shipped carrying ``hexproof``: a strictly
    better card, silently, and the moment ``shroud`` joined ``Keyword`` the
    permissive reading stopped reporting it.
    """
    printed_lower = {k.casefold().replace(" ", "_") for k in printed}
    found: list[str] = []
    consumed: set[str] = set()
    for line in oracle_text.split("\n"):
        bare = _strip_reminders(line).strip().rstrip(".")
        if not bare:
            continue
        parts = [p.strip().casefold().replace(" ", "_") for p in re.split(r"[,;]", bare)]
        parts = [p for p in parts if p]
        if not parts or not all(p in KNOWN_KEYWORDS for p in parts):
            continue
        if strict and not all(p in printed_lower for p in parts):
            continue
        for part in parts:
            if part not in found and (not printed_lower or part in printed_lower):
                found.append(part)
        consumed.add(line)
    return found, consumed


# ----------------------------------------------------------------------
# the generator
# ----------------------------------------------------------------------


def build_proxy(facts: CardFacts, *, taken: set[str] | None = None) -> ProxyResult:
    """A card definition for something nobody wrote rules for."""
    card_id = slug_for(facts.name, facts.scryfall_id, taken=taken)

    if facts.is_token or facts.layout in _UNPLAYABLE_LAYOUTS:
        return ProxyResult(card_id=card_id, error="not a card that can be in a deck")

    supertypes, types, subtypes, dropped = split_type_line(facts.type_line)
    notes: list[str] = []

    unmodelled = [d for d in dropped if d in _UNMODELLED_TYPES]
    if not types:
        reason = f"no card type this engine models ({facts.type_line!r})"
        return ProxyResult(card_id=card_id, error=reason)
    for word in dropped:
        if word in _NOISE_TYPES:
            notes.append(f"type {word!r} dropped; it has no effect here")
        elif word in _UNMODELLED_TYPES:
            notes.append(f"type {word!r} is not modelled")
    if unmodelled and len(types) == 0:  # pragma: no cover -- caught above
        return ProxyResult(card_id=card_id, error="unmodelled type")

    if CardType.PLANESWALKER.value in types:
        notes.append("planeswalkers enter play but have no loyalty or abilities here")
    if CardType.BATTLE.value in types:
        notes.append("battles enter play but have no defence or protector here")

    if facts.layout in _TWO_FACED_LAYOUTS:
        notes.append("only the front face exists; the back face is not modelled")
    elif facts.layout in _SPLIT_LAYOUTS:
        notes.append("only the first half exists; the other half is not modelled")

    mana_cost, cost_notes = simplify_mana_cost(facts.mana_cost, facts.color_identity)
    notes.extend(cost_notes)

    keywords, consumed = lift_keywords(facts.oracle_text, facts.keywords)

    abilities, mana_notes, mana_consumed = _mana_ability(facts, types)
    notes.extend(mana_notes)
    consumed |= mana_consumed

    replacements, tapped_notes, tapped_consumed = _enters_tapped(facts, types)
    notes.extend(tapped_notes)
    consumed |= tapped_consumed

    power, toughness, pt_notes = _power_toughness(facts, types)
    notes.extend(pt_notes)

    residual = _residual(facts, consumed)
    if residual:
        notes.append(f"rules text not implemented: {residual}")

    coverage: Coverage = "full" if not notes else "partial"

    model = CardModel(
        id=card_id,
        name=facts.name,
        oracle_text=facts.oracle_text,
        mana_cost=mana_cost or None,
        supertypes=supertypes,
        types=types,
        subtypes=subtypes,
        power=power,
        toughness=toughness,
        keywords=keywords,
        colors=list(facts.colors),
        # Never derived.  `_derive_color_identity` widens identity to every
        # colour a mana ability can make, which would give a generated Command
        # Tower a WUBRG identity and get it rejected from every deck by
        # `validate_deck`'s subset check.  The catalog already knows the answer.
        color_identity=list(facts.color_identity),
        abilities=abilities,
        replacements=replacements,
    )
    return ProxyResult(
        card_id=card_id, model=model, coverage=coverage, notes=tuple(notes)
    )


def _mana_ability(facts: CardFacts, types: list[str]) -> tuple[list[dict], list[str], set[str]]:
    """``{T}: Add ...``, when the card really is a permanent that taps for mana.

    The permanence check is not decoration: Dark Ritual has
    ``produced_mana: ["B"]`` and is an Instant, and a land that taps for nothing
    is the single most deck-breaking thing this generator could produce.
    """
    if not facts.produced_mana:
        return [], [], set()
    if not any(t in _PERMANENT_TYPE_NAMES for t in types):
        return [], [], set()

    line, prefix = _find_mana_line(facts.oracle_text)
    if line is None:
        return [], [], set()

    symbols = [s for s in facts.produced_mana if s in ("W", "U", "B", "R", "G", "C")]
    if not symbols:
        return [], [], set()

    # The cost beyond tapping.  Mana is expressible; a sacrifice, a life payment
    # or "return an Island you control" is not -- and generating those as *free*
    # would hand the deck a Signet that costs nothing and a bounce land with no
    # bounce.  A generated card must never be better than the printed one, which
    # is the same rule the conditional taplands follow.
    extra_cost = None
    if prefix:
        if not _MANA_ONLY.match(prefix):
            return [], [f"mana ability not generated; its cost is {prefix!r}"], set()
        extra_cost, _ = simplify_mana_cost(prefix.replace(",", "").replace(" ", ""), facts.color_identity)

    effects, quantity_note = _mana_effects(line, symbols)
    cost: dict = {"tap": True}
    if extra_cost:
        cost["mana"] = extra_cost
    ability = {
        "kind": "activated",
        # The printed line this implements, verbatim.  Not decoration: the
        # authoring verifier's residual gate decides "is every sentence
        # accounted for" by asking each ability which sentence it claims, and an
        # ability with no text claims nothing.
        "text": line.strip(),
        "is_mana_ability": True,
        "cost": cost,
        "effects": effects,
    }

    notes = [quantity_note] if quantity_note else []
    return [ability], notes, {line}


#: ``{T}: Add {C}{C}.`` -- everything after "Add", which is where the *amount*
#: lives.  ``produced_mana`` only lists which symbols a card can make, so reading
#: it alone turns every Signet and Sol Ring into a one-mana rock.
_ADD_CLAUSE = re.compile(r":\s*Add\s+(?P<what>[^.]+)", re.I)
_FIXED_MANA = re.compile(r"^(?:\{[WUBRGC]\})+$")
_ANY_COLOR = re.compile(r"^one mana of any (?:one )?color$", re.I)

#: ``Add {G} for each creature you control`` -- a payout that scales with the
#: board.  Read rather than approximated: a Gaea's Cradle that taps for one is a
#: Forest, and the difference does not show anywhere on screen.
_FOR_EACH = re.compile(r"^(?P<sym>(?:\{[WUBRGC]\})+)\s+for each\s+(?P<what>.+)$", re.I)

#: ``creature you control with defender`` -> the trailing quality.
_WITH_KEYWORD = re.compile(r"^(?P<noun>.+?)\s+with\s+(?P<keyword>[a-z ]+)$", re.I)


def _for_each_selector(what: str) -> dict | None:
    """``"Swamp you control"`` -> a counting selector, or ``None`` if unreadable.

    ``None`` is the important return. Anything this cannot read must fall back
    to a *noted* approximation rather than a silent one -- Kydele's "for each
    card you've drawn this turn" is not a board count at all, and there is
    nothing here to count it with.
    """
    from .loader import KNOWN_KEYWORDS, KNOWN_TYPES

    text = " ".join(what.split()).rstrip(".")
    selector: dict = {}

    # "with defender" comes *after* "you control" in print, so it has to come
    # off first -- otherwise the controller clause is no longer the suffix.
    keyword = _WITH_KEYWORD.match(text)
    if keyword:
        word = keyword.group("keyword").strip().lower()
        if word not in KNOWN_KEYWORDS:
            return None
        selector["keywords"] = [word]
        text = keyword.group("noun").strip()

    lowered = text.lower()
    if lowered.endswith("you control"):
        selector["controller"] = "you"
        text = text[: -len("you control")].strip()
    elif lowered.endswith("on the battlefield"):
        selector["controller"] = "any"
        text = text[: -len("on the battlefield")].strip()
    else:
        return None

    noun = text.strip()
    if not noun or " " in noun:
        # "card you've drawn this turn", "differently named land" -- not a
        # single type or subtype, so not something this tier may guess at.
        return None
    if noun.title() in KNOWN_TYPES:
        selector["types"] = [noun.title()]
    else:
        # A subtype: Swamp, Elf, Locus. Not validated against a closed list
        # because subtypes are not one, so a nonsense word would count nothing
        # rather than fail -- which is why the caller still notes it.
        selector["subtypes"] = [noun.title()]
    return selector


def _mana_effects(line: str, symbols: list[str]) -> tuple[list[dict], str | None]:
    """What the ability adds, read from the printed clause where possible.

    ``{T}: Add {C}{C}`` is two mana, and the difference between a Sol Ring that
    taps for two and one that taps for one is the difference between a fast deck
    and a slow one.  Falls back to one-of-each-symbol only when the clause is
    something this cannot read.
    """
    match = _ADD_CLAUSE.search(line)
    clause = " ".join(match.group("what").split()) if match else ""

    # "Add {C}{C}" / "Add {G}{U}" -- a fixed payout, taken verbatim.
    if _FIXED_MANA.match(clause.replace(" ", "")):
        return [{"op": "add_mana", "mana": clause.replace(" ", "")}], None

    # "Add {G} for each creature you control" -- a payout that scales.
    for_each = _FOR_EACH.match(clause)
    if for_each:
        selector = _for_each_selector(for_each.group("what"))
        if selector is not None:
            return [
                {
                    "op": "add_mana",
                    "mana": for_each.group("sym").replace(" ", ""),
                    "amount": {"count": selector},
                }
            ], None
        # Unreadable, so it stays one mana -- but *said out loud*. Without the
        # note this lands as a "full" card that taps for a sixth of what it
        # prints, which is how nine of these shipped in the first place.
        return [
            {"op": "add_mana", "mana": for_each.group("sym").replace(" ", "")}
        ], f"mana scales with {for_each.group('what')[:40]!r}; implemented as one"

    # "Add {G} or {U}" -- a choice, one mana either way.
    options = [p.strip() for p in re.split(r"\bor\b|,", clause) if p.strip()]
    if options and all(_FIXED_MANA.match(o.replace(" ", "")) for o in options):
        if len(options) == 1:
            return [{"op": "add_mana", "mana": options[0].replace(" ", "")}], None
        return [
            {
                "op": "choose_mode",
                "modes": [
                    {"effects": [{"op": "add_mana", "mana": o.replace(" ", "")}]}
                    for o in options
                ],
            }
        ], None

    # "Add one mana of any color" -- a choice across whatever it can produce.
    if _ANY_COLOR.match(clause) or len(symbols) > 1:
        note = None if _ANY_COLOR.match(clause) else f"mana clause read loosely: {clause[:40]!r}"
        return [
            {
                "op": "choose_mode",
                "modes": [{"effects": [{"op": "add_mana", "mana": f"{{{s}}}"}]} for s in symbols],
            }
        ], note

    return [{"op": "add_mana", "mana": f"{{{symbols[0]}}}"}], None


def _find_mana_line(oracle_text: str) -> tuple[str | None, str]:
    """The card's *own* tap-for-mana line, and whatever its cost says before ``{T}``.

    Skips a line that hands the ability to something else.  Scryfall writes an
    Aura as ``Enchanted land has "{T}: Add {C}."``, and lifting that gives the
    Aura a mana ability of its own -- the same trap as ``keywords`` listing what
    a card *grants* rather than what it has.
    """
    for line in oracle_text.split("\n"):
        # Parentheses are *unwrapped*, not stripped: a basic land's entire text
        # is the reminder "({T}: Add {G}.)", and deleting it leaves Forest with
        # no way to make mana -- which is the single most deck-breaking thing
        # this generator could do.
        bare = line.replace("(", "").replace(")", "").strip()
        if not bare or '"' in bare or _GRANTS_TO_OTHERS.match(bare):
            continue
        match = _TAPS_FOR_MANA.match(bare)
        if match:
            return line, match.group("pre").strip().rstrip(",").strip()
    return None, ""


_PERMANENT_TYPE_NAMES = frozenset(
    {
        CardType.LAND.value,
        CardType.CREATURE.value,
        CardType.ARTIFACT.value,
        CardType.ENCHANTMENT.value,
        CardType.PLANESWALKER.value,
        CardType.BATTLE.value,
    }
)


def _enters_tapped(facts: CardFacts, types: list[str]) -> tuple[list[dict], list[str], set[str]]:
    """The one replacement effect worth generating.

    Applied even when the printed condition is "unless you control two or fewer
    other lands": a conditional tapland generated as always-untapped is a strict
    upgrade over the real card, and a free dual distorts a game far more than an
    always-tapped one does.
    """
    if not any(t in _PERMANENT_TYPE_NAMES for t in types):
        return [], [], set()
    lines = [ln for ln in facts.oracle_text.split("\n") if _ENTERS_TAPPED.search(ln)]
    if not lines:
        return [], [], set()
    notes: list[str] = []
    if re.search(r"unless|if you control|as long as", " ".join(lines), re.I):
        notes.append("enters tapped unconditionally; the printed condition is not modelled")
    return [{"event": "self_enters_tapped"}], notes, set(lines)


def _power_toughness(
    facts: CardFacts, types: list[str]
) -> tuple[int | None, int | None, list[str]]:
    """``compile_card`` requires ints on a creature, and ``*`` is not an int."""
    if CardType.CREATURE.value not in types:
        return None, None, []
    power, p_note = _stat(facts.power, "power")
    toughness, t_note = _stat(facts.toughness, "toughness")
    return power, toughness, [n for n in (p_note, t_note) if n]


def _stat(raw: str | None, label: str) -> tuple[int, str | None]:
    if raw is None or raw == "":
        return 0, f"{label} was blank and reads as 0"
    try:
        return int(raw), None
    except ValueError:
        # "*", "1+*", "?".  The characteristic-defining ability behind it is not
        # modelled, so the printed base is the only honest guess, and 0 is it.
        return 0, f"{label} {raw!r} is variable and reads as 0"


def _residual(facts: CardFacts, consumed: set[str]) -> str:
    """What the card still claims to do that nothing above implemented."""
    leftover: list[str] = []
    for line in facts.oracle_text.split("\n"):
        if line in consumed:
            continue
        bare = _strip_reminders(line).strip()
        # A card whose whole text is its own name is doing nothing.
        bare = bare.replace(facts.name, "").strip(" .,;:")
        if bare:
            leftover.append(" ".join(bare.split()))
    return " / ".join(leftover)
