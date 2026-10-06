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

from ...engine.mana import ManaCost
from ..loader.vocabulary import KNOWN_KEYWORDS
from ..proxy import CardFacts, ProxyResult, build_proxy
from ..schema import CardModel

#: Starting life in the verifier's sandbox, so a lifegain template can say what
#: the total should be.
SANDBOX_LIFE = 40
#: What the hand holds once the card under test has been cast: the spare land
#: `verify.build_sandbox` deals beside it, so that a mandatory "as an additional
#: cost, discard a card" has fodder. Every drawn card lands on top of it, which
#: is why a "draw N" template asserts N + 1.
SANDBOX_HAND_AFTER_CAST = 1

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
        expect={"hand_size": {"0": SANDBOX_HAND_AFTER_CAST + n}},
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

#: ``Extort`` (702.101a) -- "whenever you cast a spell, you may pay {W/B}. If you
#: do, each opponent loses 1 life and you gain that much life."  Bare keyword
#: only: `_bare` strips the reminder, and every printing of extort is the same
#: ability, so there is no parameter to read.
_EXTORT = re.compile(r"^extort$", re.I)

#: The extort ability, shared by the template and by anything that must agree
#: with it. "That much life" is the life the opponents *actually* lost, read off
#: `lose_life`'s ``as`` binding -- not the opponent count, which a doubled or
#: locked loss would make wrong.
def extort_ability(text: str) -> dict:
    return {
        "kind": "triggered",
        "text": text,
        "trigger": {"event": "spell_cast", "controller": "you"},
        "effects": [
            {
                "op": "may",
                "prompt": "Extort: pay {W/B}?",
                "pay": {"mana": "{W/B}"},
                "effects": [
                    {
                        "op": "lose_life",
                        "player": "each_opponent",
                        "amount": {"const": 1},
                        "as": "extorted",
                    },
                    {"op": "gain_life", "player": "you", "amount": {"binding": "extorted"}},
                ],
            }
        ],
    }


#: "As an additional cost to cast this spell, sacrifice a creature."  The
#: *mandatory* shape only: "you may sacrifice" is a different card and almost
#: always drags a "When you do, ..." reflexive trigger along with it, which is
#: its own capability.
_ADDITIONAL_SAC = re.compile(
    r"^as an additional cost to cast this spell, sacrifice (?P<what>[^,.]+)$", re.I
)
_ADDITIONAL_DISCARD = re.compile(
    r"^as an additional cost to cast this spell, discard a card$", re.I
)

#: The noun phrases the sacrifice clause is read for, and nothing else.  A
#: phrase this does not know fails the whole card rather than guessing at a
#: selector -- templates are all-or-nothing by design, and a cost charged
#: against the wrong permanents is a different card, not an incomplete one.
_SAC_SELECTORS: dict[str, dict] = {
    "a creature": {"types": ["Creature"]},
    "an artifact": {"types": ["Artifact"]},
    "a land": {"types": ["Land"]},
    "an enchantment": {"types": ["Enchantment"]},
    "an artifact or creature": {"any_types": ["Artifact", "Creature"]},
    "a creature or artifact": {"any_types": ["Artifact", "Creature"]},
    "a creature or enchantment": {"any_types": ["Creature", "Enchantment"]},
    "an artifact or enchantment": {"any_types": ["Artifact", "Enchantment"]},
}

#: ``Cycling {2}`` -- an activated ability you play from your hand, whose cost
#: discards the card itself.  `_bare` has already stripped the reminder text
#: that spells the ability out, so only the keyword and its cost are left.
#:
#: Deliberately *only* plain cycling. Typecycling ("Landcycling {1}{G}") fetches
#: instead of drawing and basic landcycling narrows what it may fetch, so both
#: mean a different ability; and "When you cycle this card…" is a trigger the
#: engine has no event for. All three fail this pattern and keep their cards
#: honestly unimplemented rather than turning them into plain cyclers.
_CYCLING = re.compile(r"^cycling (?P<cost>(?:\{[^}]+\})+)$", re.I)

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


#: ``{T}, Pay 1 life, Sacrifice this land: Search your library for a Forest or
#: Plains card, put it onto the battlefield, then shuffle.``  A fetchland, and
#: the reason an imported deck's land count lies: `proxy.py` will not generate a
#: mana ability whose cost it cannot express, so the land arrives inert.  The
#: whole cost *is* expressible -- `Cost` has carried `tap`, `pay_life` and
#: `sacrifice` since before this module existed -- so all that was ever missing
#: was somebody translating the sentence.
#:
#: Anchored at both ends on purpose.  Fabled Passage adds "Then if you control
#: four or more lands, untap that land", which lands in the same residual line
#: and must not be claimed; the anchor makes it fail the whole card instead.
_FETCH = re.compile(
    r"^search your library for (?P<what>.+?) cards?, "
    r"put (?:it|them) onto the battlefield(?P<tapped> tapped)?, then shuffle$",
    re.I,
)

#: ``Until end of turn, this land becomes a 4/4 white and blue Elemental creature
#: with flying and vigilance. It's still a land.``  Both orderings of the
#: until-end-of-turn clause are printed -- Celestial Colonnade leads with it,
#: Faerie Conclave trails it -- so both are matched.
_ANIMATE = re.compile(
    r"^(?:until end of turn,\s+)?"
    r"this \w+ becomes an? (?P<p>\d+)/(?P<t>\d+) ?(?P<mid>.*?)"
    r"creature(?: with (?P<extra>.+?))?"
    r"(?: until end of turn)?"
    r"\. it(?:'s| is) still an? \w+$",
    re.I,
)

#: ``{T}, Pay 1 life, Sacrifice this land: ...`` -- an activated ability's cost,
#: split from its effect on the first colon that is not inside a quoted ability.
_ACTIVATED = re.compile(r"^(?P<cost>[^:\"]+): (?P<effect>.+)$", re.S)

_COST_MANA = re.compile(r"^(?:\{[^}]+\})+$")
_COST_LIFE = re.compile(r"^pay (?P<n>\d+) life$", re.I)
_COST_SACRIFICE_SELF = re.compile(r"^sacrifice this \w+$", re.I)

#: The colour words an animation may name, in the order `Color` spells them.
_COLOR_WORDS = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
}

#: Card types that may appear as an adjective inside an animation -- "a 1/1
#: Phyrexian Blinkmoth **artifact** creature".
_TYPE_WORDS = {"artifact": "Artifact", "enchantment": "Enchantment", "land": "Land"}

#: "becomes a 2/2 creature with **all creature types**" -- Mutavault.  Not a
#: keyword clause, which is why it is read before `_keywords_in` gets it and
#: would otherwise reject the card.
_ALL_CREATURE_TYPES = re.compile(r"^all creature types$", re.I)


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
    card_fields: dict = {}
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
        elif kind == "card":
            # A card-level field rather than an ability -- an additional cost is
            # part of what the spell costs, not something it does.
            card_fields.update(produced)
        elif kind == "nothing":
            # A line that is already true of the generated card -- Devoid on a
            # card the catalog already reports as colourless. Consumed, with
            # nothing to build.
            pass
        else:
            spell_effects.extend(translation.effects)
        _merge(expectation, translation.expect)

    payload = proxy.model.model_dump(exclude_defaults=True, exclude_none=True)
    payload.update(card_fields)
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

    if sac := _ADDITIONAL_SAC.match(bare):
        selector = _SAC_SELECTORS.get(sac.group("what").strip().lower())
        if selector is None:
            return None
        return (
            "card",
            {"additional_cost": {"sacrifice": {"controller": "you", **selector}}},
            # No expectation of its own. What the cost *did* shows up in the
            # card's own numbers -- a board one smaller, a graveyard one larger
            # -- and those belong to the sentence that drew the cards.
            Translation(effects=[], expect={}),
            "additional-cost:sacrifice",
        )

    if _ADDITIONAL_DISCARD.match(bare):
        return (
            "card",
            {"additional_cost": {"discard": 1}},
            Translation(effects=[], expect={}),
            "additional-cost:discard",
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

    if cycling := _CYCLING.match(bare):
        mana = cycling.group("cost")
        try:
            ManaCost.parse(mana)
        except Exception:
            # Phyrexian or snow in a cycling cost. `ManaCost.parse` raises on
            # those, and the exception would travel out through
            # `CardRegistry.from_paths` and stop the registry loading at boot.
            return None
        return (
            "static",
            {
                "kind": "activated",
                "text": line.strip(),
                "active_zones": ["hand"],
                "cost": {"mana": mana, "discard_self": True},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            },
            Translation(effects=[], expect={}),
            "cycling",
        )

    if _EXTORT.match(bare):
        # Nothing to assert: the sandbox casts no spell after the card under
        # test, so the trigger never fires there.
        return ("trigger", extort_ability(line.strip()), Translation(effects=[], expect={}), "extort")

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
                # 702.6a, declared here because this is the one place that knows
                # the printed word: everything below compiles to an ordinary
                # activated ability that attaches something, which reconfigure
                # and Vault 101 also do. The marker is what lets a static name
                # equip abilities as a class.
                "is_equip": True,
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

    activated = _ACTIVATED.match(bare)
    if activated:
        produced = _activated_ability(line, activated)
        if produced is not None:
            return produced

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


def _activated_ability(line: str, activated: re.Match[str]):
    """``<cost>: <effect>`` -- a fetchland or a creature-land, or ``None``.

    Returned as kind ``"static"`` because `translate` uses that for "one dict
    that belongs in `abilities`", which is what `equip` already does with its own
    activated ability.
    """
    cost = _activation_cost(activated.group("cost"))
    if cost is None:
        return None
    body = activated.group("effect").strip()

    effects: list[dict] | None = None
    name = ""

    fetch = _FETCH.match(body)
    if fetch:
        selector = _search_selector(fetch.group("what"))
        if selector is None:
            return None
        effects = [
            {
                "op": "search_library",
                "player": "you",
                "count": {"const": 1},
                "destination": "battlefield",
                "tapped": bool(fetch.group("tapped")),
                "selector": selector,
            }
        ]
        name = "fetchland"
    else:
        animation = _ANIMATE.match(body)
        if animation:
            effect = _animation(animation)
            if effect is None:
                return None
            effects = [effect]
            name = "creature-land"

    if effects is None:
        return None
    return (
        "static",
        {
            "kind": "activated",
            "text": line.strip(),
            "cost": cost,
            "effects": effects,
        },
        Translation(effects=[], expect={}),
        name,
    )


def _activation_cost(text: str) -> dict | None:
    """``"{T}, Pay 1 life, Sacrifice this land"`` -> a ``CostModel`` payload.

    ``None`` for anything with a clause this does not recognise, which is the
    point: an unrecognised clause dropped silently would make a *cheaper* card
    than the one printed, and `proxy.py` refuses to generate these abilities at
    all for exactly that reason.  Only self-sacrifice is accepted -- "sacrifice
    another creature" is a choice, and guessing which one is not this tier's job.
    """

    cost: dict = {}
    for raw in text.split(","):
        clause = raw.strip()
        if not clause:
            return None
        if clause.upper() == "{T}":
            if cost.get("tap"):
                return None
            cost["tap"] = True
        elif _COST_MANA.match(clause):
            if "mana" in cost:
                return None
            try:
                ManaCost.parse(clause)
            except Exception:
                # Phyrexian or snow. `ManaCost.parse` raises on those, and the
                # exception would travel out through `CardRegistry.from_paths`
                # and stop the whole registry loading at boot.
                return None
            cost["mana"] = clause
        elif life := _COST_LIFE.match(clause):
            cost["pay_life"] = int(life.group("n"))
        elif _COST_SACRIFICE_SELF.match(clause):
            cost["sacrifice"] = {"zone": "battlefield", "self_only": True}
        else:
            return None
    return cost or None


def _search_selector(what: str) -> dict | None:
    """``"a basic Plains, Island, or Swamp"`` -> a selector over the library.

    Subtypes are any-of in `selectors.matches`, which is exactly what "a Forest
    **or** Plains card" means.  ``Land`` is only asserted when the text says
    "land": "a Forest or Plains card" is already narrow enough, and a card that
    fetches something that is not a land would be quietly changed by adding it.
    """
    words = re.split(r",|\bor\b|\band\b", what)
    selector: dict = {}
    subtypes: list[str] = []
    for raw in words:
        word = raw.strip()
        if not word or word.lower() in ("a", "an"):
            continue
        word = re.sub(r"^(?:a|an) ", "", word, flags=re.I).strip()
        if word.lower() == "basic":
            selector["supertypes"] = ["Basic"]
            continue
        if word.lower().startswith("basic "):
            selector["supertypes"] = ["Basic"]
            word = word[len("basic "):].strip()
        if word.lower() == "land":
            selector["types"] = ["Land"]
        elif word[:1].isupper() and word.isalpha():
            subtypes.append(word)
        else:
            # "up to two", "another", a colour, anything else: not something
            # this tier can turn into a selector without guessing.
            return None
    if subtypes:
        selector["subtypes"] = subtypes
    return selector or None


def _animation(match: re.Match[str]) -> dict | None:
    """The body of "becomes a 4/4 white and blue Elemental creature with X"."""
    types = ["Creature"]
    subtypes: list[str] = []
    colors: list[str] = []

    for raw in re.split(r"\band\b|\s+", match.group("mid") or ""):
        word = raw.strip()
        if not word:
            continue
        if word.lower() in _COLOR_WORDS:
            colors.append(_COLOR_WORDS[word.lower()])
        elif word.lower() in _TYPE_WORDS:
            types.append(_TYPE_WORDS[word.lower()])
        elif word[:1].isupper() and word.isalpha():
            subtypes.append(word)
        else:
            return None

    keywords: list[str] = []
    extra = match.group("extra")
    if extra:
        if _ALL_CREATURE_TYPES.match(extra.strip()):
            # Mutavault. A changeling clause, not a keyword clause -- and the
            # engine's answer to changeling is the same closed subtype set.
            subtypes.extend(CHANGELING_SUBTYPES)
        else:
            found = _keywords_in(extra)
            if found is None:
                # A granted triggered ability in quotes (Raging Ravine, Den of
                # the Bugbear) or a keyword the engine does not implement.
                return None
            keywords = found

    effect: dict = {
        "op": "animate",
        "power": {"const": int(match.group("p"))},
        "toughness": {"const": int(match.group("t"))},
        "types": types,
        "objects": {"zone": "battlefield", "self_only": True},
    }
    if subtypes:
        effect["subtypes"] = subtypes
    if colors:
        effect["colors"] = colors
    if keywords:
        effect["keywords"] = keywords
    return effect


def _keywords_in(text: str) -> list[str] | None:
    """``"flying and haste"`` -> ``["flying", "haste"]``, or ``None``.

    ``None`` when any part is a keyword the engine does not implement -- "ward
    {2}", "protection from red". Claiming the line and granting nothing would
    produce a card that *says* it has protection and does not, which is the
    failure mode this whole pipeline is built to refuse.
    """

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


def _unused(spec: Any) -> Any:  # pragma: no cover - keeps the public surface tidy
    return spec
