"""Oracle sentences common enough to translate without asking anybody.

Magic's text is templated, and the residual left by ``proxy.py`` is dominated by
a small number of shapes. Measured over the 3,000 most-played cards: "When this
land enters, you gain 1 life" appears 14 times, "scry 1" 12, "surveil 1" 12,
"Draw a card" 19. Each of those is a sentence the DSL has been able to say since
the day it was written -- ``proxy.py`` simply never translated prose into ops.

So this module is the free tier: **deterministic, exact, and costs nothing per
card**. It runs before any model does, and every card it finishes is a card
nobody has to pay to have written.

Two rules keep it honest:

**All or nothing.** A card is only produced when *every* residual line is
consumed. A partial translation is the inert-proxy problem again, one sentence
smaller, and it would waste the verifier's residual gate on cards this module
already knew it had not finished.

**Every template carries its own assertion.** A template knows exactly what its
effect does, so it emits the expectation too -- which is what lets the six gates
check its work rather than take its word. A template that cannot say what to
observe does not belong here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..proxy import CardFacts, ProxyResult, build_proxy
from ..schema import CardModel

#: Starting life in the verifier's sandbox, so a lifegain template can say what
#: the total should be.
SANDBOX_LIFE = 40

WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _count(word: str) -> int:
    word = (word or "").strip().lower()
    if word.isdigit():
        return int(word)
    return WORDS.get(word, 1)


#: A written or numeric quantity, captured as ``n``.  Named because every builder
#: reads it by name; a pattern needing two counts wants its own groups.
N = r"(?P<n>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"


@dataclass
class Translation:
    """What one sentence became."""

    #: Effects to run, in DSL form.
    effects: list[dict]
    #: How the board should differ afterwards, merged into the card's expectation.
    expect: dict = field(default_factory=dict)


#: ``(pattern, build)`` where ``build`` turns a match into a :class:`Translation`.
#: The patterns are matched against a single sentence with its reminder text and
#: the card's own name already stripped.
Sentence = tuple[re.Pattern[str], Callable[[re.Match[str]], Translation]]


def _draw(match: re.Match[str]) -> Translation:
    n = _count(match.group("n"))
    return Translation(
        effects=[{"op": "draw", "player": "you", "amount": {"const": n}}],
        expect={"hand_size": {"0": n}},
    )


def _gain_life(match: re.Match[str]) -> Translation:
    n = _count(match.group("n"))
    return Translation(
        effects=[{"op": "gain_life", "player": "you", "amount": {"const": n}}],
        expect={"life": {"0": SANDBOX_LIFE + n}},
    )


def _each_opponent_loses(match: re.Match[str]) -> Translation:
    n = _count(match.group("n"))
    return Translation(
        effects=[{"op": "lose_life", "player": "each_opponent", "amount": {"const": n}}],
        expect={"life": {"1": SANDBOX_LIFE - n}},
    )


def _scry(match: re.Match[str]) -> Translation:
    # Scry changes no count, so there is nothing to assert about it. The
    # expectation is left empty on purpose and `translate` supplies the only
    # honest fallback -- "it resolved and ended where a card of this type ends".
    # Inventing a stronger claim here would be a gate that passes without
    # checking anything.
    return Translation(
        effects=[{"op": "scry", "player": "you", "amount": {"const": _count(match.group("n"))}}],
    )


def _surveil(match: re.Match[str]) -> Translation:
    n = _count(match.group("n"))
    return Translation(effects=[{"op": "surveil", "player": "you", "amount": {"const": n}}])


def _mill(match: re.Match[str]) -> Translation:
    n = _count(match.group("n"))
    return Translation(
        effects=[{"op": "mill", "player": "each_opponent", "amount": {"const": n}}],
        expect={"library_size": {"1": 20 - n}},
    )


#: Sentences whose whole meaning is one op with a countable outcome.
SENTENCES: list[Sentence] = [
    (re.compile(rf"^draw {N} cards?$", re.I), _draw),
    (re.compile(rf"^you draw {N} cards?$", re.I), _draw),
    (re.compile(rf"^target player draws {N} cards?$", re.I), _draw),
    (re.compile(rf"^you gain {N} life$", re.I), _gain_life),
    (re.compile(rf"^each opponent loses {N} life$", re.I), _each_opponent_loses),
    (re.compile(rf"^scry {N}$", re.I), _scry),
    (re.compile(rf"^surveil {N}$", re.I), _surveil),
    (re.compile(rf"^each opponent mills {N} cards?$", re.I), _mill),
]

#: ``Enchanted creature gets +2/+2`` / ``Equipped creature gets +1/+0``.  The
#: single most common thing an Aura or Equipment says, and between them they are
#: ~1,700 cards -- the largest block in the catalog.
_ATTACHED_BUFF = re.compile(
    r"^(?:enchanted|equipped) (?:creature|permanent) gets "
    r"(?P<p>[+-]\d+)/(?P<t>[+-]\d+)$",
    re.I,
)

#: ``Equipped creature has flying`` / ``Enchanted creature has trample and haste``.
#: The other half of what an Aura or Equipment says; without it a card that grants
#: rather than buffs still falls to the all-or-nothing rule.
_ATTACHED_GRANT = re.compile(
    r"^(?:enchanted|equipped) (?:creature|permanent) (?:has|have|gains?) (?P<kw>[^.]+)$",
    re.I,
)

#: ``Equipped creature gets +1/+2 and has vigilance`` -- one printed sentence
#: that is two abilities. Common enough on Auras and Equipment to be worth its
#: own pattern rather than leaving those cards to the all-or-nothing rule.
_ATTACHED_BUFF_AND_GRANT = re.compile(
    r"^(?:enchanted|equipped) (?:creature|permanent) gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+) "
    r"and (?:has|have|gains?) (?P<kw>[^.]+)$",
    re.I,
)

#: ``Enchant creature``, and the variants that only narrow *what* it may enchant.
#: "you control" and "an opponent controls" are real restrictions, so they are
#: carried into the selector rather than dropped.
_ENCHANT = re.compile(
    r"^enchant (?P<what>creature|permanent|land|artifact|player)"
    r"(?: (?P<whose>you control|an opponent controls))?$",
    re.I,
)

#: ``Devoid`` -- "this card has no color".  Self-implementing: the catalog already
#: reports the card as colourless, so the proxy's `colors` is already right and
#: there is nothing left to build.
_DEVOID = re.compile(r"^devoid$", re.I)

#: ``Changeling`` -- "this card is every creature type".  `add_subtype` covers it.
_CHANGELING = re.compile(r"^changeling$", re.I)

#: ``Prowess`` -- a triggered ability spelled as a keyword.
_PROWESS = re.compile(r"^prowess$", re.I)

#: Every creature type a shipped card mentions.  A real Changeling is *all* of
#: them, which is unbounded; this is the closed set the engine can actually be
#: asked about, and anything outside it could not be selected for anyway.
CHANGELING_SUBTYPES = (
    "Human", "Soldier", "Warrior", "Wizard", "Cleric", "Rogue", "Knight", "Elf",
    "Goblin", "Zombie", "Vampire", "Spirit", "Beast", "Elemental", "Dragon",
    "Angel", "Demon", "Sphinx", "Bird", "Cat", "Snake", "Insect", "Serpent",
    "Giant", "Orc", "Merfolk", "Druid", "Shaman", "Bear", "Wall",
)

#: ``Equip {2}``.  A sorcery-speed activated ability that re-attaches.
_EQUIP = re.compile(r"^equip (?P<cost>(?:\{[^}]+\})+)$", re.I)

_ENCHANT_TYPES = {
    "creature": ["Creature"],
    "land": ["Land"],
    "artifact": ["Artifact"],
    "permanent": [],
}


#: Sentences that are a whole static ability rather than an effect.
STATICS: list[tuple[re.Pattern[str], dict]] = [
    (
        re.compile(
            r"^you may play an additional land on each of your turns$", re.I
        ),
        {
            "kind": "static",
            "effect": "extra_land_drops",
            "affects_player": "you",
            "amount": {"const": 1},
        },
    ),
]

#: How a sentence is introduced.  ``None`` means the effect belongs to the spell
#: itself rather than to a trigger.
_ENTERS = re.compile(
    r"^when(?:ever)? (?:this|the) (?:land|creature|artifact|enchantment|permanent) enters,\s*(?P<rest>.+)$",
    re.I,
)


@dataclass
class TemplateResult:
    card_id: str
    model: CardModel | None = None
    expectation: dict = field(default_factory=dict)
    #: Which templates fired, for the queue's record of how a card was written.
    used: list[str] = field(default_factory=list)
    #: Why nothing was produced.
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.model is not None


def translate(facts: CardFacts, *, taken: set[str] | None = None) -> TemplateResult:
    """A fully-implemented card, or the reason there is not one.

    Starts from ``build_proxy`` -- which already gets the name, cost, types,
    stats, keywords, mana ability and enters-tapped right -- and tries to turn
    what it left over into real abilities.
    """
    proxy: ProxyResult = build_proxy(facts, taken=taken)
    if proxy.model is None:
        return TemplateResult(card_id=proxy.card_id, reason=proxy.error or "not generatable")

    leftover = _residual_lines(proxy)
    if not leftover and proxy.coverage == "full":
        # `proxy.py` finished it on its own: a vanilla creature, a plain dual, a
        # Signet. There is nothing left to translate and nothing lost -- the card
        # is complete, so it belongs in the authored pool rather than being
        # regenerated as an inert proxy for every deck that contains it.
        return TemplateResult(
            card_id=proxy.card_id,
            model=proxy.model,
            expectation=_fallback_expectation(proxy.model),
            used=["proxy:complete"],
        )
    if not leftover:
        # No leftover *sentences*, but the proxy still had to simplify something
        # -- a hybrid cost rewritten, a back face dropped. Those notes are real
        # divergences from the printed card, so this tier does not claim it.
        return TemplateResult(
            card_id=proxy.card_id,
            reason=f"proxy simplified it: {'; '.join(proxy.notes)[:80]}",
        )

    abilities: list[dict] = []
    spell_effects: list[dict] = []
    targets: list[dict] = []
    expectation: dict = {}
    used: list[str] = []
    is_spell = not _is_permanent(proxy.model)

    for line in leftover:
        handled = _translate_line(line, is_spell=is_spell)
        if handled is None:
            return TemplateResult(
                card_id=proxy.card_id,
                reason=f"no template for: {line[:90]}",
            )
        kind, produced, translation, name = handled
        used.append(name)
        if kind == "statics":
            # One printed sentence that is two abilities -- "gets +1/+2 and has
            # vigilance". Both carry the same `text`, which is correct: they
            # implement the same line between them.
            abilities.extend(produced)
        elif kind in ("static", "trigger"):
            abilities.append(produced)
        elif kind == "enchant":
            targets.append(produced)
        elif kind == "nothing":
            # A line that is already true of the generated card -- Devoid on a
            # card the catalog already reports as colourless. Consumed, with
            # nothing to build.
            pass
        else:
            spell_effects.extend(translation.effects)
        _merge(expectation, translation.expect)

    payload = proxy.model.model_dump(exclude_defaults=True, exclude_none=True)
    payload["abilities"] = [*payload.get("abilities", []), *abilities]
    if spell_effects:
        payload["spell_effects"] = [*payload.get("spell_effects", []), *spell_effects]
    if targets:
        payload["targets"] = [*payload.get("targets", []), *targets]
    if targets and "Aura" not in payload.get("subtypes", []):
        # "Enchant X" on something that is not an Aura means a mechanic this
        # module does not model -- an Aura-like Equipment, a bestow creature.
        # Attaching it would be a guess.
        return TemplateResult(
            card_id=proxy.card_id, reason="enchant clause on a non-Aura"
        )

    try:
        model = CardModel.model_validate(payload)
    except Exception as exc:
        return TemplateResult(card_id=proxy.card_id, reason=f"template output invalid: {exc}")

    if not expectation:
        expectation = _fallback_expectation(model)

    return TemplateResult(
        card_id=proxy.card_id, model=model, expectation=expectation, used=used
    )


def _translate_line(line: str, *, is_spell: bool):
    """``(kind, payload, translation, template_name)`` or ``None``."""
    bare = _bare(line)

    if _DEVOID.match(bare):
        # Nothing to build: "this card has no color" is already true of the
        # generated card, because the catalog reports it colourless.
        return (
            "nothing",
            None,
            Translation(effects=[], expect={}),
            "devoid",
        )

    if _CHANGELING.match(bare):
        return (
            "static",
            {
                "kind": "static",
                "text": line.strip(),
                "effect": "add_subtype",
                "affects": {"self_only": True},
                "subtypes": list(CHANGELING_SUBTYPES),
            },
            Translation(effects=[], expect={}),
            "changeling",
        )

    if _PROWESS.match(bare):
        return (
            "trigger",
            {
                "kind": "triggered",
                "text": line.strip(),
                "trigger": {
                    "event": "spell_cast",
                    "controller": "you",
                    "filter": {"not_types": ["Creature"]},
                },
                "effects": [
                    {
                        "op": "pump",
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "objects": {"zone": "battlefield", "self_only": True},
                    }
                ],
            },
            Translation(effects=[], expect={}),
            "prowess",
        )

    both = _ATTACHED_BUFF_AND_GRANT.match(bare)
    if both:
        keywords = _keywords_in(both.group("kw"))
        if keywords is None:
            return None
        return (
            "statics",
            [
                {
                    "kind": "static",
                    "text": line.strip(),
                    "effect": "buff",
                    "affects": {"attached": True},
                    "power": {"const": int(both.group("p"))},
                    "toughness": {"const": int(both.group("t"))},
                },
                {
                    "kind": "static",
                    "text": line.strip(),
                    "effect": "grant_keyword",
                    "affects": {"attached": True},
                    "keywords": keywords,
                },
            ],
            Translation(effects=[], expect={}),
            "attached:buff+grant",
        )

    grant = _ATTACHED_GRANT.match(bare)
    if grant:
        keywords = _keywords_in(grant.group("kw"))
        if keywords is None:
            # A parameterised or unimplemented keyword -- "ward {2}",
            # "protection from red". Claiming the line and granting nothing
            # would be a card that says it has protection and does not.
            return None
        return (
            "static",
            {
                "kind": "static",
                "text": line.strip(),
                "effect": "grant_keyword",
                "affects": {"attached": True},
                "keywords": keywords,
            },
            Translation(effects=[], expect={}),
            "attached:grant",
        )

    enchant = _ENCHANT.match(bare)
    if enchant:
        # Not an ability: the Aura's spell targets what it will enchant, and
        # `stack._attach_aura` attaches it once the permanent is on the
        # battlefield. So this produces a *target spec*, and `translate` puts it
        # on the card rather than in `abilities`.
        what = enchant.group("what").lower()
        if what == "player":
            # An Aura on a *player* has no `attached_to` to hang off -- the
            # engine attaches to objects only. Guessing would put it on nothing.
            return None
        selector: dict = {"zone": "battlefield"}
        if _ENCHANT_TYPES[what]:
            selector["types"] = _ENCHANT_TYPES[what]
        whose = (enchant.group("whose") or "").lower()
        if whose == "you control":
            selector["controller"] = "you"
        elif whose == "an opponent controls":
            selector["controller"] = "opponent"
        return (
            "enchant",
            {"id": "enchanted", "kind": "permanent", "selector": selector, "count": 1},
            Translation(effects=[], expect={}),
            "enchant",
        )

    buff = _ATTACHED_BUFF.match(bare)
    if buff:
        return (
            "static",
            {
                "kind": "static",
                "text": line.strip(),
                "effect": "buff",
                "affects": {"attached": True},
                "power": {"const": int(buff.group("p"))},
                "toughness": {"const": int(buff.group("t"))},
            },
            Translation(effects=[], expect={}),
            "attached:buff",
        )

    equip = _EQUIP.match(bare)
    if equip:
        return (
            "static",  # placed among the abilities, same as a static
            {
                "kind": "activated",
                "text": line.strip(),
                "sorcery_speed_only": True,
                "cost": {"mana": equip.group("cost")},
                "targets": [
                    {
                        "id": "equip_target",
                        "kind": "permanent",
                        "selector": {
                            "zone": "battlefield",
                            "controller": "you",
                            "types": ["Creature"],
                        },
                        "count": 1,
                    }
                ],
                "effects": [{"op": "attach", "objects": {"target": "equip_target"}}],
            },
            Translation(effects=[], expect={}),
            "equip",
        )

    for pattern, ability in STATICS:
        if pattern.match(bare):
            return (
                "static",
                {**ability, "text": line.strip()},
                Translation(effects=[], expect={}),
                "static:extra_land_drops",
            )

    enters = _ENTERS.match(bare)
    inner = _bare(enters.group("rest")) if enters else bare

    for pattern, build in SENTENCES:
        match = pattern.match(inner)
        if not match:
            continue
        translation = build(match)
        name = pattern.pattern[:40]
        if enters:
            return (
                "trigger",
                {
                    "kind": "triggered",
                    "text": line.strip(),
                    "trigger": {"event": "self_enters", "source": "self"},
                    "effects": translation.effects,
                },
                translation,
                f"etb:{name}",
            )
        if is_spell:
            return ("spell", None, translation, f"spell:{name}")
        # A bare sentence on a permanent is not a spell effect and not a
        # trigger -- it is a static or an activated ability this module cannot
        # place, and guessing where it goes is how a card ends up doing its
        # thing at the wrong time.
        return None
    return None


def _keywords_in(text: str) -> list[str] | None:
    """``"flying and haste"`` -> ``["flying", "haste"]``, or ``None``.

    ``None`` when any part is a keyword the engine does not implement -- "ward
    {2}", "protection from red". Claiming the line and granting nothing would
    produce a card that *says* it has protection and does not, which is the
    failure mode this whole pipeline is built to refuse.
    """
    from ..loader import KNOWN_KEYWORDS

    parts = [p.strip() for p in re.split(r",|\band\b", text) if p.strip()]
    out: list[str] = []
    for part in parts:
        word = part.lower().replace(" ", "_")
        if word not in KNOWN_KEYWORDS:
            return None
        out.append(word)
    return out or None


def _bare(line: str) -> str:
    """A sentence with reminder text and trailing punctuation removed."""
    text = re.sub(r"\([^()]*\)", "", line)
    return " ".join(text.split()).strip().rstrip(".").strip()


def _residual_lines(proxy: ProxyResult) -> list[str]:
    for note in proxy.notes:
        if note.startswith("rules text not implemented:"):
            body = note.split(":", 1)[1]
            return [p.strip() for p in body.split(" / ") if p.strip()]
    return []


def _fallback_expectation(model: CardModel) -> dict:
    """The weakest honest claim, for a card that changes no count.

    A vanilla bear, a scry land. "It resolved and ended where a card of its type
    ends" is still a real assertion -- a spell stuck on the stack or a permanent
    that fizzled into the graveyard fails it -- and it is the only thing that can
    be said without inventing a stronger one that checks nothing.
    """
    if "Aura" in (model.subtypes or []):
        # An Aura's destination depends on what its own static does to its host:
        # Dead Weight's -2/-2 can kill the creature, and state-based actions then
        # correctly put the Aura in the graveyard. Both are the card working.
        return {"zone": ["battlefield", "graveyard"]}
    return {"zone": "battlefield" if _is_permanent(model) else "graveyard"}


def _is_permanent(model: CardModel) -> bool:
    return bool(
        {"Creature", "Land", "Artifact", "Enchantment", "Planeswalker", "Battle"}
        & set(model.types)
    )


def _merge(into: dict, extra: dict) -> None:
    """Combine two expectations, summing what stacks.

    Two lifegain sentences on one card mean one total, not two assertions that
    disagree.
    """
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            for pid, amount in value.items():
                if pid in into[key] and isinstance(amount, int):
                    # Both are absolute totals against the same baseline, so the
                    # deltas add rather than the totals.
                    baseline = SANDBOX_LIFE if key == "life" else 0
                    into[key][pid] = into[key][pid] + (amount - baseline)
                else:
                    into[key][pid] = amount
        else:
            into.setdefault(key, value)


def describe(result: TemplateResult) -> str:
    if result.ok:
        return f"{result.card_id}: {', '.join(result.used)}"
    return f"{result.card_id}: {result.reason}"


def sentence_patterns() -> list[str]:
    """Every sentence this module can translate, for the report."""
    return [p.pattern for p, _ in SENTENCES] + [p.pattern for p, _ in STATICS]


def _unused(spec: Any) -> Any:  # pragma: no cover - keeps the public surface tidy
    return spec
