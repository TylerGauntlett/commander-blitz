"""The work packet: everything needed to implement one card, and nothing else.

The templates handle the shapes common enough to be worth a rule. What is left is
the long tail -- cards that need somebody to read the text and think. This module
is the interface to that somebody, and it is deliberately a *file format* rather
than an API call, because the same packet has to work for:

* a Claude Code session, where a person is watching, and
* an unattended worker calling the API on 10,000 cards.

Both read the same JSON and write the same answer, so the second can be added
later without changing anything the first proved.

A packet is self-contained. Nothing in it assumes the reader has the repository
open, has seen another card, or remembers what an op is -- because the API worker
has none of that, and a session that has to go looking is a session that guesses.

**The answer is a card *and* an expectation, always.** Gate 5 rejects a card
nobody asserted anything about, so a packet that asked only for the card would be
asking for work that cannot be accepted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..images import IndexEntry
from ..proxy import CardFacts, build_proxy, facts_from_index
from ..registry import CardRegistry, data_dir
from .verify import EXPECTATION_KEYS


def packets_dir() -> Path:
    return data_dir() / "authoring" / "packets"


def answers_dir() -> Path:
    return data_dir() / "authoring" / "answers"


def gaps_dir() -> Path:
    """Where a card that the DSL *cannot say* is recorded.

    The other half of answering a packet, and the more valuable half in bulk. A
    reader who cannot express a card must not approximate it -- gate 3 would
    reject the result anyway, and a card quietly missing a clause is the failure
    this whole package exists to prevent. Naming the missing capability instead
    turns one refusal into a measurement, and a thousand refusals into a ranked
    roadmap (``scripts/report_gaps.py``).

    One file per card rather than one shared report, for the same reason packets
    and answers are: a hundred workers write concurrently and must never contend.
    """
    return data_dir() / "authoring" / "gaps"


@dataclass
class Packet:
    """One card's worth of work."""

    card_id: str
    name: str
    type_line: str
    mana_cost: str
    power: str | None
    toughness: str | None
    colors: str
    color_identity: str
    oracle_text: str
    #: What the free tiers already worked out -- keywords, mana ability,
    #: enters-tapped. The answer should keep these and add to them.
    starting_point: dict
    #: The sentences still unaccounted for. Implementing these *exactly* is the
    #: job; gate 3 rejects the card if any survive.
    todo: list[str]
    #: Why the template tier could not finish it, so the reader does not retrace
    #: a path already known to be a dead end.
    template_said: str
    #: The **back face**, for a card that turns over or carries a second
    #: castable face -- `transform`, `modal_dfc`, `prepare`. Its own name, type
    #: line, cost, power/toughness and printed text.
    #:
    #: Empty for every other layout, including `split` and `adventure`, whose
    #: two halves are halves of one object and are joined into `oracle_text`.
    #:
    #: Without it a worker handed a transforming card was shown half of it and
    #: had no way to tell: the front face's text loaded, validated and rendered
    #: perfectly, and `todo` listed only the sentences the front prints. The one
    #: thing a worker must never do is invent a line, and this is the field that
    #: keeps the other half from having to be invented.
    back_face: dict = field(default_factory=dict)
    #: Cards already in the pool with a similar shape, as worked examples.
    examples: list[dict] = field(default_factory=list)
    #: The vocabulary. Copied in rather than referenced, because the API worker
    #: cannot open docs/card-dsl.md.
    reference: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def reference() -> dict:
    """The DSL, small enough to travel with every packet."""
    from automtg.engine.effects import known_ops
    from automtg.engine.effects.conditions import CONDITION_KEYS
    from automtg.engine.effects.selectors import SELECTOR_KEYS
    from automtg.engine.effects.values import VALUE_KEYS
    from automtg.engine.enums import CardType, Keyword, Supertype
    from automtg.engine.triggers import TRIGGER_EVENTS

    from ..loader import (
        STATIC_CONDITION_HEADS,
        STATIC_EFFECTS,
        STATIC_FILTER_KEYS,
        STATIC_VALUE_KEYS,
    )
    from ..schema import CostModel

    return {
        "ops": sorted(known_ops()),
        "keywords": sorted(k.value for k in Keyword),
        "types": sorted(t.value for t in CardType),
        "supertypes": sorted(s.value for s in Supertype),
        "trigger_events": sorted(TRIGGER_EVENTS),
        # Derived, not a literal.  This was hardcoded to five entries while
        # nine others existed -- protection, set_types, block_restriction and
        # the player-wide ones -- so a card needing any of them was filed as
        # blocked on a mechanic that already shipped.  Tromokratis was.
        "static_effects": sorted(STATIC_EFFECTS),
        "static_filter_keys": sorted(STATIC_FILTER_KEYS),
        # What a static's "as long as ..." clause may ask. A *third* language,
        # neither `condition_keys` (which is the effect-side `if`) nor
        # `static_filter_keys` -- and absent from the packet until Vampire
        # Nocturnus, so a worker had no way to know a static could be
        # conditional at all, let alone what it could be conditional on.
        "static_condition_keys": sorted(STATIC_CONDITION_HEADS),
        # What a static's *magnitude* may be -- a fourth language again, and the
        # one Door of Destinies was filed against. Shown `value_keys` alone, a
        # worker reads the effect-side list as the whole vocabulary and writes
        # a leaf a static cannot hold; shown nothing at all, it assumes an
        # anthem's `power` is a `const` and files a gap for "+1/+1 for each
        # charge counter on this artifact" instead of writing it.
        "static_value_keys": sorted(STATIC_VALUE_KEYS),
        #: The three vocabularies a packet used to omit, each of which cost a
        #: real card.  A worker that cannot see `counters_on` cannot know
        #: "if this creature has no +1/+1 counters on it" is sayable, and files
        #: a gap for a mechanic that already works -- Sharktocrab's `adapt` was
        #: exactly that.  `selector_keys` is the effect-side list;
        #: `static_filter_keys` above is the far smaller printed-only subset,
        #: and being shown only the subset reads as the whole language.
        "selector_keys": sorted(SELECTOR_KEYS),
        "condition_keys": sorted(CONDITION_KEYS),
        "value_keys": sorted(VALUE_KEYS),
        # What an activated ability may charge. Omitted entirely until
        # `tap_permanents` shipped and nothing could use it: a worker shown
        # `ops` but not `cost_keys` has no way to tell a cost from an effect,
        # so every "<cost>: <effect>" card either guesses or files a gap for a
        # cost that already exists. Derived from the model the loader
        # validates against, for the same reason `static_effects` is.
        "cost_keys": sorted(CostModel.model_fields),
        "expectation_keys": list(EXPECTATION_KEYS),
        "notes": [
            "A card either uses vocabulary in these lists or it fails to load.",
            "`condition_keys` and `value_keys` are what an `if` can ask and what"
            " an amount can be. `counters_on` reads a counter count off an"
            " object, so \"if this has no +1/+1 counters on it\" is a `cmp`"
            " against `{\"const\": 0}` and needs no new op.",
            "`static_condition_keys` is what a static ability's optional"
            " `condition` may ask -- an \"as long as ...\" clause that switches"
            " the whole static on and off as the board moves. It is a third"
            " language, neither `condition_keys` nor `static_filter_keys`.",
            "`static_value_keys` is what a static's *magnitude* may be -- its"
            " `power`, `toughness` or `amount`, and either side of a `cmp` in"
            " its condition. Smaller than `value_keys`, and a leaf outside it"
            " is a load error rather than a silent 0. `counters_on` is in it,"
            " so \"gets +1/+1 for each charge counter on this artifact\" is a"
            " `buff` whose `power` is"
            " `{\"counters_on\": {\"counter\": \"charge\", \"objects\":"
            " {\"self_only\": true}}}` -- an anthem with a size, which no op"
            " can be: `pump` wears off and `add_counters` would miss both the"
            " creatures already out and the ones cast later.",
            "`selector_keys` is what an effect's `objects` or a target spec's"
            " `selector` may contain. `static_filter_keys` is the much smaller"
            " set a *static ability* may read, because a static may only read"
            " printed characteristics -- do not mistake it for the whole"
            " selector language.",
            "An ability's `text` must be the printed sentence it implements: the"
            " residual gate asks each ability which line it claims, and anything"
            " unclaimed means the card is only half implemented.",
            "An instant or sorcery puts its effects in `spell_effects`; a"
            " permanent puts them in `abilities`.",
            "`cost_keys` is what an activated ability's `cost` may contain."
            " A printed \"<cost>: <effect>\" line splits into a `cost` from"
            " that list and `effects` from `ops` -- paying with an op instead"
            " moves the payment to resolution and lets the ability be"
            " activated when it could not be paid for.",
            "A static ability's filter may only read printed characteristics.",
            "`snapshot` is how a card reads a value after its target has left --"
            " there is no general last-known-information system.",
            "A mana ability may contain only `add_mana`, or one `choose_mode`"
            " whose modes each contain only `add_mana`.",
            "\"It can't be regenerated.\" is `no_regeneration: true` on the"
            " `destroy` op -- 701.15c, the victim's regeneration shields are"
            " not applied to that destruction (and not spent either)."
            " Indestructible and totem armor are unaffected. Refused on any"
            " other op, because nothing else replaces a destruction.",
            "A target spec may carry `mode`: the index of the mode that owns"
            " it, in a spell whose whole effect tree is one top-level"
            " `choose_mode`. That is how \"Choose up to two. * Target artifact"
            " card. * Target creature card. ...\" carries one target per"
            " bullet and binds two distinct ones -- the spec is declared only"
            " if its mode is chosen. It must be a fixed count, never"
            " `optional`, and no card-level target on the same card may be"
            " variable-size.",
            "The expectation is checked in a sandbox: player 0 at 40 life with a"
            " deep mana base, two creatures, and an opponent holding a creature,"
            " a flier, an artifact and an enchantment. The card under test is the"
            " only card in hand.",
        ],
    }


def examples_for(card: CardFacts, registry: CardRegistry, limit: int = 3) -> list[dict]:
    """Cards already in the pool that look like this one.

    Worked examples beat prose: the fastest way to show how a trigger is written
    is a card that already has one. Chosen by shared type and by whether they
    carry the kind of ability this card is going to need.
    """
    from ..schema import CardModel

    wanted_types = set(card.type_line.replace("—", " ").split())
    scored: list[tuple[int, dict]] = []
    for existing in registry:
        if existing.is_token or not existing.oracle_text:
            continue
        score = len(wanted_types & set(existing.types))
        if any(a.is_triggered for a in existing.abilities) and "When" in card.oracle_text:
            score += 2
        if any(a.is_activated and not a.is_mana_ability for a in existing.abilities) and (
            ":" in card.oracle_text
        ):
            score += 2
        if any(a.is_static for a in existing.abilities) and " get " in card.oracle_text:
            score += 2
        if score <= 0:
            continue
        try:
            payload = CardModel.model_validate(_as_payload(existing)).model_dump(
                exclude_defaults=True, exclude_none=True
            )
        except Exception:  # pragma: no cover -- an example is a nicety, not a gate
            continue
        scored.append((score, payload))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [payload for _, payload in scored[:limit]]


def _as_payload(card) -> dict:
    """A compiled card back into the JSON shape a packet shows."""
    return {
        "id": card.id,
        "name": card.name,
        "oracle_text": card.oracle_text,
        "mana_cost": str(card.mana_cost) or None,
        "types": sorted(card.types),
        "subtypes": sorted(card.subtypes),
        "power": card.power,
        "toughness": card.toughness,
        "abilities": [dict(a.raw) for a in card.abilities if getattr(a, "raw", None)],
    }



def back_face_of(entry: IndexEntry) -> dict:
    """The back face as a plain dict, or ``{}`` for a single-faced card.

    Read straight off the index rather than looked up by name: the back is not
    a row of its own -- the table is keyed ``(name, is_token)`` and a row under
    the back face's name would be a card the deck importer could add.
    """
    if not entry.back_name:
        return {}
    return {
        "name": entry.back_name,
        "type_line": entry.back_type_line,
        "mana_cost": entry.back_mana_cost,
        "power": entry.back_power,
        "toughness": entry.back_toughness,
        "oracle_text": entry.back_oracle_text,
    }

def build_packet(entry: IndexEntry, registry: CardRegistry, template_said: str) -> Packet:
    facts = facts_from_index(entry)
    proxy = build_proxy(facts)
    starting_point: dict = {}
    todo: list[str] = []
    if proxy.model is not None:
        starting_point = proxy.model.model_dump(exclude_defaults=True, exclude_none=True)
        for note in proxy.notes:
            if note.startswith("rules text not implemented:"):
                todo = [p.strip() for p in note.split(":", 1)[1].split(" / ") if p.strip()]

    return Packet(
        card_id=proxy.card_id,
        name=entry.name,
        type_line=entry.type_line,
        mana_cost=entry.mana_cost,
        power=entry.power,
        toughness=entry.toughness,
        colors=entry.colors,
        color_identity=entry.color_identity,
        oracle_text=entry.oracle_text,
        starting_point=starting_point,
        back_face=back_face_of(entry),
        todo=todo or [entry.oracle_text],
        template_said=template_said,
        examples=examples_for(facts, registry),
        reference=reference(),
    )


def write_packet(packet: Packet) -> Path:
    packets_dir().mkdir(parents=True, exist_ok=True)
    path = packets_dir() / f"{packet.card_id}.json"
    path.write_text(packet.to_json(), encoding="utf-8", newline="")
    return path


def read_answers() -> dict[str, dict]:
    """Every answer written so far, keyed by card id.

    An answer is ``{"card": {...}, "expectation": {...}}``. Both halves are
    required -- see the module docstring.
    """
    out: dict[str, dict] = {}
    if not answers_dir().exists():
        return out
    for path in sorted(answers_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        card = payload.get("card")
        if isinstance(card, dict) and card.get("id"):
            out[card["id"]] = payload
    return out
