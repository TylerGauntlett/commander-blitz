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

import ast
import inspect
import json
import re
import textwrap
import typing
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from commanderblitz.engine.effects import OPS, known_ops
from commanderblitz.engine.effects.conditions import CONDITION_KEYS
from commanderblitz.engine.effects.selectors import SELECTOR_KEYS
from commanderblitz.engine.effects.values import VALUE_KEYS
from commanderblitz.engine.enums import CardType, Keyword, Supertype
from commanderblitz.engine.objects import PLAYABLE_DURATIONS
from commanderblitz.engine.structs import DELAYED_DURATIONS
from commanderblitz.engine.triggers import TRIGGER_EVENTS, TRIGGER_FILTER_KEYS

from ..images import IndexEntry
from ..loader.vocabulary import (
    COST_REDUCTION_FILTER_KEYS,
    COST_REDUCTION_KEYS,
    COST_REDUCTION_REFUSED_FILTER_KEYS,
    DELAYED_TRIGGER_KEYS,
    MANA_RIDER_OPS,
    STATIC_AFFECTS_FILTER_KEYS,
    STATIC_CONDITION_HEADS,
    STATIC_EFFECTS,
    STATIC_FILTER_KEYS,
    STATIC_VALUE_KEYS,
    TAPPED_PERMANENT_KEYS,
)
from ..proxy import CardFacts, build_proxy, facts_from_index
from ..registry import CardRegistry, authored_card_paths, data_dir
from ..schema import AbilityModel, CardModel, CostModel, TargetModel, TriggerModel
from .verify import EXPECTATION_KEYS

#: The card-level alternative and additional costs, which live on the *card*
#: rather than inside an ability's ``cost``.  A packet advertised ``cost_keys``
#: -- what an activated ability may charge -- and stopped there, so a printed
#: "Bestow {1}{G}" or "Evoke {2}{U}" had no sanctioned vocabulary at all: the
#: word is not a keyword, not an op, and not a ``CostModel`` field, and a worker
#: reading only those three lists correctly concludes it cannot say the line.
#: Springheart Nantuko was filed as a gap on exactly that reasoning, with the
#: mechanic already built and shipping.
#:
#: Curated rather than derived, because ``CardModel`` carries sixty-odd fields
#: and only these are a *price*: handing a worker the whole model would bury the
#: dozen that answer "what else can this line be?" among faces, splices and
#: bookkeeping.  Each one is a bare mana cost unless noted.
CARD_LEVEL_COST_KEYS = (
    "additional_cost",  # a non-mana Cost, e.g. "sacrifice a creature"
    #: A choice BETWEEN prices, exactly one paid -- Bitter Triumph's "discard a
    #: card or pay 3 life", and **tiered** (Fire Magic, Ice Magic), where each
    #: price buys a different effect and the card branches on
    #: `{"cost_option": n}`. Omitted from this list until now, so two workers
    #: reading it correctly reported the mechanic missing while Bitter Triumph
    #: shipped using it.
    "additional_cost_options",
    #: **Spree** (702.166a): "Choose one or more additional costs." A list of
    #: priced modes of which a non-empty *subset* is bought as the spell is
    #: cast; each printed "+ <cost> — <effect>" line is an `if` on
    #: `{"spree_mode": n}`. Every mode is a bare mana cost.
    "spree",
    "additional_optional",
    "additional_repeatable",
    "alternative_cost",
    "ascend",  # bool; a state trigger, not a price
    "bestow",
    "buyback",
    "cost_reduction",  # int; "this spell costs {X} less to cast"
    "dredge",  # int
    "emerge",
    #: "Escalate {G}": paid once per mode beyond the first, on a spell that is
    #: one top-level choose_mode with or_more.
    "escalate",
    "evoke",
    "flashback",
    "foretell",
    "gift",  # str; the noun phrase promised
    #: ``{"cost": "{2}{W}{W}", "counters": 4}`` -- "Impending 4—{2}{W}{W}". The
    #: time counters, "isn't a creature" and the end-step tick are the rule's;
    #: the card writes none of them.
    "impending",
    "kicker",
    "madness",
    #: "Mayhem {4}{R}": the price from the graveyard, offered only after this
    #: card was discarded this turn. Never beside `graveyard_cost`.
    "mayhem",
    "morph",
    "multikicker",
    "mutate",
    "overload",
    "pay_generic_with",  # str; convoke and its relatives
    "retrace",  # bool
    "splice",
    #: "This spell costs {1}{W} more to cast for each target beyond the first";
    #: needs exactly one target spec, with count "any".
    "strive",
    "suspend",
    #: "Warp {1}{R}" -- evoke's slot, with the exile at the next end step and
    #: the cast from exile on a later turn supplied by the *rule*. Nothing is
    #: written on the card for those, deliberately: the printed card says only
    #: the price, so a `delayed_trigger` ability spelling out the riders would
    #: be a line with no printed sentence to claim.
    "warp",
)

#: The card-level fields that join two printed faces into one card entry.
#:
#: Same argument as ``CARD_LEVEL_COST_KEYS``, and it was found the same way: a
#: worker shown neither list reads a printed second face as vocabulary nobody
#: has given it and files a gap for a mechanic that already works. Riverglide
#: Pathway was recorded as ``modal-double-faced-card``/``engine`` with high
#: confidence while seven cards in the shipped pool -- Bloodline Keeper,
#: Malakir Rebirth, Response // Resurgence among them -- already use these
#: fields, because the reference block named no way to say "the other half".
#:
#: Curated for the same reason too: a face is not a price, so it needs its own
#: heading rather than being buried in the cost list.
CARD_LEVEL_FACE_KEYS = (
    "back_face",  # the face you TURN OVER to; never cast, never drawn
    "second_face",  # a second SPELL the same card may be cast as
    "second_face_zone",  # "hand" (split, adventure) or "graveyard" (aftermath)
    "prepared_face",  # the spell a prepared permanent may cast a copy of
    "fuse",  # bool; one spell made of both halves at once
    "adventure",  # bool; the second face exiles and the front is cast from exile
)


#: Card-level **riders**: things a card says about itself that are neither a
#: price nor a second face.
#:
#: The third list for the third time. `CARD_LEVEL_COST_KEYS` was added because a
#: printed "Bestow {1}{G}" matched nothing a worker had been shown;
#: `CARD_LEVEL_FACE_KEYS` because a printed second face did; and this because
#: "Exile Mizzix's Mastery." did. Each time the mechanic already shipped and the
#: gap record was written in good faith against a reference that did not name
#: it.
#:
#: Curated, and the test is the same one the other two lists pass: would a
#: worker reading a printed sentence go looking for this? A `melds_with` or an
#: `evoke_label` is bookkeeping the pipeline fills in; `exiles_itself` and
#: `uncounterable` are sentences on the card.
CARD_LEVEL_RIDER_KEYS = (
    "exiles_itself",  # "Exile <this card>." -- instead of the graveyard, on resolution
    # "…put it into its owner's library seventh from the top" -- the printed
    # ordinal, counting from 1. `exiles_itself`'s sibling on the same slot, and a
    # sentence on the card by exactly the test above, so a worker reading it goes
    # looking for this.
    "tucks_itself",
    "uncounterable",  # "This spell can't be countered."
    "rebound",  # exiled as it resolves, cast free from exile next upkeep
    "split_second",  # "…players can't cast spells or activate abilities"
    "epic",  # "…copy it at the beginning of each of your upkeeps. You can't cast spells"
    "miracle",  # the price of casting it as the first card drawn this turn
    "graveyard_cast",  # castable from a graveyard on its own say-so
    "graveyard_cost",  # what that costs
    "graveyard_cast_transformed",  # disturb: it arrives on the back face
    "splice_onto",  # which spells this may be spliced onto
    "melds_with",  # the other half of a meld pair
    "melds_into",  # what the pair becomes
    "cant_cast_first_turns",  # "You can't cast this during your first N turns of the game"
    "toxic",  # int; "Toxic N" -- the N, beside "toxic" in keywords
    "morph_counter",  # bool; megamorph -- turns face up with a +1/+1 counter, beside `morph`
)


#: Spelled out because a token is printed in words ("a 2/2 blue Drake") and the
#: worker is matching printed text against `_token_ids`, not colour codes.
_COLOR_WORDS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}


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
    #: **Meld** (701.37): the card this half and its partner become, for the
    #: half that prints "exile them, then meld them into <name>". The catalog
    #: keeps the melded card as a row of its own and links nothing, so without
    #: this a worker would have to invent the result's text. Same shape as
    #: ``back_face``; empty for everything else.
    meld_result: dict = field(default_factory=dict)
    #: Cards already in the pool with a similar shape, as worked examples.
    examples: list[dict] = field(default_factory=list)
    #: The vocabulary. Copied in rather than referenced, because the API worker
    #: cannot open docs/card-dsl.md.
    reference: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _op_options() -> dict[str, list[str]]:
    """Every key each op reads out of its own effect dict.

    ``ops`` alone is a list of *names*, and a name is not a language: a worker
    shown ``copy_spell`` and no keys has no way to learn that ``new_targets``
    exists, so "You may choose new targets for the copy" reads as unsayable.
    Expansion // Explosion, Deflecting Swat and Misdirection were all filed
    against a ``choose-new-targets`` capability that has shipped since
    Jin-Gitaxias, purely because the reference never named the flag.

    Derived by walking each op's own source for the literal it hands to
    ``spec.get``/``spec[...]``/``in spec``, rather than curated, for the reason
    ``static_effects`` and ``cost_keys`` are derived: a hand-written list goes
    stale the first time somebody adds a key and does not think of this file.

    It is a **lower bound**. An op that forwards ``spec`` to a helper hides that
    helper's keys, so a key's absence here is not proof it does not exist --
    which the note beside it says, because the failure this exists to prevent is
    a worker treating silence as a "no".
    """

    def read_keys(fn, seen: set) -> set[str]:
        """Keys ``fn`` reads out of a mapping parameter, following it one hop.

        The hop is not a refinement. An op that hands ``spec`` to a helper
        reports none of that helper's keys, and the result is *misleading*
        rather than merely short: after `playable` moved into a shared
        `playable_duration_of(spec)`, `exile` and `look_at_top` went on
        advertising only the boolean it replaced, and a worker reading that as
        the whole of it would write the shorter card. Following the call is the
        fix at the source; the union with the shipped pool below stays, because
        a helper reached through two hops or a dynamic dispatch is still
        invisible.
        """
        if fn in seen:
            return set()
        seen.add(fn)
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        except (OSError, TypeError, SyntaxError):  # pragma: no cover - defensive
            return set()
        # Whatever the mapping is called here: `spec` in every op, but a helper
        # is free to name its own parameter something else.
        params = {a.arg for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  for a in node.args.args}
        names = params & {"spec", "effect"}
        keys: set[str] = set()
        for node in ast.walk(tree):
            match node:
                # spec.get("x"), spec.get("x", default), spec.pop("x")
                case ast.Call(
                    func=ast.Attribute(value=ast.Name(id=str() as who), attr="get" | "pop"),
                    args=[ast.Constant(value=str() as key), *_],
                ) if who in names:
                    keys.add(key)
                # spec["x"]
                case ast.Subscript(
                    value=ast.Name(id=str() as who), slice=ast.Constant(value=str() as key)
                ) if who in names:
                    keys.add(key)
                # "x" in spec
                case ast.Compare(
                    left=ast.Constant(value=str() as key),
                    ops=[ast.In()],
                    comparators=[ast.Name(id=str() as who)],
                ) if who in names:
                    keys.add(key)
                # helper(spec) -- follow it, once
                case ast.Call(func=ast.Name(id=str() as called), args=args) if any(
                    isinstance(a, ast.Name) and a.id in names for a in args
                ):
                    target = getattr(inspect.getmodule(fn), called, None)
                    if inspect.isfunction(target):
                        keys |= read_keys(target, seen)
        return keys

    options: dict[str, list[str]] = {}
    for name, fn in OPS.items():
        keys = read_keys(fn, set())
        if keys:
            options[name] = set(keys)

    # Union with what the shipped pool actually writes, because the scan alone
    # is not merely incomplete but *misleading*: `add_mana` forwards `spec` to a
    # helper and so reports only `player`, and a worker reading that as the
    # whole of it would conclude the op cannot name a colour. Every effect dict
    # in the pool is a key some op demonstrably accepts, which is the one source
    # that cannot be wrong about it.
    for card in _pool_cards():
        for effect in _walk_effects(card):
            op = effect.get("op")
            if isinstance(op, str):
                options.setdefault(op, set()).update(k for k in effect if k != "op")

    return {name: sorted(keys) for name, keys in sorted(options.items())}


def _pool_cards() -> list[dict]:
    """Every shipped card entry, hand-written and authored."""
    cards: list[dict] = []
    for path in sorted((data_dir() / "cards").glob("*.cards.json")) + sorted(
        (data_dir() / "cards" / "auto").glob("*.cards.json")
    ):
        try:
            cards.extend(json.loads(path.read_text(encoding="utf-8")).get("cards", []))
        except (OSError, ValueError):  # pragma: no cover - defensive
            continue
    return cards


def _walk_effects(node: object):
    """Yield every ``{"op": ...}`` mapping anywhere inside a card entry.

    Recursive because effects nest: `choose_mode` holds modes holding effects,
    `if` holds branches, `may` and `delay` hold payloads.
    """
    if isinstance(node, dict):
        if isinstance(node.get("op"), str):
            yield node
        for value in node.values():
            yield from _walk_effects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_effects(item)



def _token_ids() -> dict[str, str]:
    """Every token id `create_token` may name, with what it puts on the board.

    Not a convenience. `loader.validate_token_references` refuses a card whose
    `create_token` names an id that does not exist or is not a token, and that
    check runs inside the authoring gates -- so a worker guessing `drake_2_2_u`
    for "create a 2/2 blue Drake creature token" writes a card that cannot load.
    Shown nothing, a worker has exactly two moves and both are wrong: invent an
    id, or file a gap record against `create_token`, which has shipped since the
    first Saproling.

    The value is the token as printed, because the id alone does not settle the
    question the worker is actually asking -- whether the token the card wants
    already exists. `beast_4_4_w_alone` and `knight_2_2_w_vigilance` are the
    cases: two ids differing from a near neighbour by one printed word.
    """
    out: dict[str, str] = {}
    for entry in _pool_cards():
        if not entry.get("is_token"):
            continue
        bits: list[str] = []
        power, toughness = entry.get("power"), entry.get("toughness")
        if power is not None and toughness is not None:
            bits.append(f"{power}/{toughness}")
        bits.extend(_COLOR_WORDS.get(c, c) for c in entry.get("colors") or ())
        if not entry.get("colors"):
            bits.append("colorless")
        bits.extend(entry.get("subtypes") or ())
        bits.extend(t.lower() for t in entry.get("types") or ())
        if entry.get("keywords"):
            bits.append("with " + " and ".join(entry["keywords"]))
        if entry.get("abilities"):
            bits.append(f'-- {entry["abilities"][0].get("text", "")}')
        out[str(entry["id"])] = " ".join(bits)
    return out


def _required_keys() -> dict:
    """Which fields each nested model REFUSES to be built without.

    Derived, because a name in `ability_keys` says a field exists and says
    nothing about whether omitting it is fatal. Four gate-1 rejections in one
    run were exactly that reading: three targets written with no `id`/`kind`,
    and Arcane Bombardment's triggered ability with no `kind` -- every one of
    them a worker that had the right key list and no way to see the asterisk.
    """

    models = {
        "ability": AbilityModel,
        "cost": CostModel,
        "target": TargetModel,
        "trigger": TriggerModel,
    }
    return {
        label: sorted(n for n, f in model.model_fields.items() if f.is_required())
        for label, model in models.items()
    }


def _literal_options(model, field: str) -> list[str]:
    """The values a Literal-typed field accepts, or [] if it is not one.

    `kind` is a closed vocabulary of five and the reference named none of them,
    so the only way to learn the spelling was to find a shipped card using it.
    """

    annotation = model.model_fields[field].annotation
    if typing.get_origin(annotation) is typing.Literal:
        return [str(v) for v in typing.get_args(annotation)]
    return []


def reference() -> dict:
    """The DSL, small enough to travel with every packet."""

    return {
        "ops": sorted(known_ops()),
        # What each op may carry beside its `op` name. See _op_options: without
        # this, an op's optional flags are invisible and a card that needs one
        # becomes a gap record for something that already ships.
        "op_options": _op_options(),
        # The fields an entry in `abilities` may have. Derived from the model
        # the loader validates against, as `cost_keys` is. `sorcery_speed_only`
        # is the witness: 81 shipped cards set it, the reference named it
        # nowhere, and Ojer Pakpatiq was filed against a
        # `sorcery-speed-activation` capability because a worker looked in
        # `cost_keys` -- the only list it had -- and correctly did not find it.
        "ability_keys": sorted(AbilityModel.model_fields),
        # The five spellings of `kind`, which is required and was named
        # nowhere: a worker could only learn it by finding a shipped card that
        # used it.
        "ability_kinds": _literal_options(AbilityModel, "kind"),
        # What a `trigger` object may carry, beside `event`. Derived from the
        # model, as `cost_keys` and `ability_keys` are, and for the reason those
        # two exist: Arcane Bombardment's "whenever you cast your FIRST instant
        # or sorcery spell each turn" was filed as a missing trigger event by a
        # worker that had looked in `ability_keys` -- the only list it had --
        # while `max_per_turn` sat on TriggerModel, already shipping on
        # Jin-Gitaxias' own spell_cast trigger.
        "trigger_keys": sorted(TriggerModel.model_fields),
        # A `delayed_trigger`'s `trigger` is a narrower object than a printed
        # one, and `subject` -- "whenever **either of those creatures**" -- is
        # on it and on no TriggerModel. Love on the Battlefield was filed as a
        # gap partly because `trigger_keys` did not list it; `delayed_durations`
        # is how long the subscription lasts ("this turn", "this combat").
        "delayed_trigger_keys": sorted(DELAYED_TRIGGER_KEYS),
        "delayed_durations": sorted(DELAYED_DURATIONS),
        # And what a target spec may carry. `id` and `kind` are required, and
        # three gate-1 rejections in this run were a worker writing neither.
        "target_keys": sorted(TargetModel.model_fields),
        # Which of all the above are not optional. See _required_keys: a key
        # list says a field exists, never that leaving it out is fatal.
        "required_keys": _required_keys(),
        "keywords": sorted(k.value for k in Keyword),
        "types": sorted(t.value for t in CardType),
        "supertypes": sorted(s.value for s in Supertype),
        "trigger_events": sorted(TRIGGER_EVENTS),
        # Derived, not a literal.  This was hardcoded to five entries while
        # nine others existed -- protection, set_types, block_restriction and
        # the player-wide ones -- so a card needing any of them was filed as
        # blocked on a mechanic that already shipped.  Tromokratis was.
        "static_effects": sorted(STATIC_EFFECTS),
        # The values `playable` takes on `exile`, `look_at_top` and
        # `grant_playable` -- "you may play it" and how long for. `op_options`
        # names the key and nothing its value may be, so a worker had no way to
        # tell "until your next end step" or "for as long as it remains exiled"
        # already shipped short of a load error.
        "playable_durations": sorted(PLAYABLE_DURATIONS),
        "static_filter_keys": sorted(STATIC_FILTER_KEYS),
        # What a static's `affects` may use: the list above plus `any_of`, a
        # union of whole filters ("Skeletons and **other** Zombies"). Its own
        # entry because the other static filters -- `blockers`, `targeting`,
        # the counts -- do not take the word, and a worker shown it in the
        # shared list would write it where it does not load.
        "static_affects_filter_keys": sorted(STATIC_AFFECTS_FILTER_KEYS),
        # `add_mana_on_tap`'s `tapped_permanent` -- "whenever you tap a Swamp
        # for mana" -- is not a static filter and takes its own short list,
        # including `produced`, the mana the tap made ("tap a permanent for
        # {C}"). Without it a worker had only the examples to go on.
        "tapped_permanent_keys": sorted(TAPPED_PERMANENT_KEYS),
        # "This spell costs {1} less to cast for each ..." -- the arithmetic
        # heads, and the filter language beside them. The filter is
        # `static_filter_keys` plus `zone` and minus the three relational keys a
        # count cannot mean anything by, so a worker shown the static list alone
        # has no way to know that `zone` is available (a reduction may count a
        # graveyard or the command zone) or that `attached` is refused.
        "cost_reduction_keys": sorted(COST_REDUCTION_KEYS),
        "cost_reduction_filter_keys": sorted(
            (STATIC_FILTER_KEYS | COST_REDUCTION_FILTER_KEYS)
            - COST_REDUCTION_REFUSED_FILTER_KEYS
        ),
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
        # The part of `selector_keys` a trigger's `filter` may use. A trigger
        # filter is matched against the event's subject by its own function,
        # which answers fewer keys than the effect-side selector; the loader
        # refuses the rest, so a worker shown only `selector_keys` would write
        # a filter that does not load.
        "trigger_filter_keys": sorted(TRIGGER_FILTER_KEYS),
        "condition_keys": sorted(CONDITION_KEYS),
        "value_keys": sorted(VALUE_KEYS),
        # What an activated ability may charge. Omitted entirely until
        # `tap_permanents` shipped and nothing could use it: a worker shown
        # `ops` but not `cost_keys` has no way to tell a cost from an effect,
        # so every "<cost>: <effect>" card either guesses or files a gap for a
        # cost that already exists. Derived from the model the loader
        # validates against, for the same reason `static_effects` is.
        "cost_keys": sorted(CostModel.model_fields),
        # What the *card* may charge, as opposed to what an ability may. See
        # CARD_LEVEL_COST_KEYS: without this list a printed "Bestow {1}{G}"
        # matches nothing a worker has been shown and becomes a gap record for
        # a mechanic that already works.
        "card_level_cost_keys": list(CARD_LEVEL_COST_KEYS),
        # How a card says "the other half". See CARD_LEVEL_FACE_KEYS: without
        # this, every double-faced, split and Adventure card becomes a gap
        # record for a mechanic seven shipped cards already use.
        "card_level_face_keys": list(CARD_LEVEL_FACE_KEYS),
        # What the card says about ITSELF that is neither a price nor a face.
        # See CARD_LEVEL_RIDER_KEYS: "Exile Mizzix's Mastery." was filed as a
        # missing capability against a reference that named no such field,
        # while `exiles_itself` had shipped with Teferi's Protection.
        "card_level_rider_keys": list(CARD_LEVEL_RIDER_KEYS),
        # Which tokens exist. `create_token` names a token by id and
        # `validate_token_references` refuses an id that is not one, so a worker
        # shown `create_token`'s options but never the ids can only guess -- and
        # a guessed id is a card that does not load. See _token_ids.
        "token_ids": _token_ids(),
        "expectation_keys": list(EXPECTATION_KEYS),
        "notes": [
            "A card either uses vocabulary in these lists or it fails to load.",
            "`token_ids` is every token `create_token` may name, and it is a"
            " CLOSED list: an id that is not in it does not load, so do not"
            " invent one from the printed words. Match the printed token"
            " against the descriptions -- \"create a 1/1 white Human Soldier"
            " creature token\" is `human_soldier_1_1_w`. If the token your card"
            " prints is genuinely not there, that IS a gap record, with"
            " `kind: \"token\"` and the printed token in `what` -- it is a data"
            " change somebody makes in one line, and it is the cheapest gap in"
            " this whole pipeline to close. Do not substitute a token that is"
            " nearly right: a 2/2 Knight with vigilance is not a 2/2 Knight.",
            "`op_options` is what each op may carry beside its `op` name, and"
            " `ability_keys` is what an entry in `abilities` may have. Read both"
            " before concluding a line cannot be said: `copy_spell` takes"
            " `new_targets` (\"you may choose new targets for the copy\"), an"
            " ability takes `sorcery_speed_only`, `once_each_turn` and"
            " `activate_steps` for printed activation limits, and"
            " `mana_restriction` for \"spend this mana only to ...\". Each of"
            " those has been filed as a missing capability by a worker that had"
            " only the op *names*.",
            "A **mana ability may say things about the mana it makes** without"
            " writing an effect for them, which is the only way to say them: a"
            " mana ability may contain nothing but `add_mana`. `mana_restriction`"
            " narrows what the mana may be spent on; `mana_uncounterable` is"
            " \"...and that spell can't be countered\"; and `mana_grant` is"
            " \"...it gains haste until end of turn\" --"
            " `{\"keywords\": [\"haste\"], \"spell_types\": [\"Creature\"]}`,"
            " where `spell_types` narrows *who is given* the keyword rather than"
            " what the mana may buy. The keyword reaches the permanent the spell"
            " becomes, which no trigger can do. And `exert` in `cost_keys` is"
            " \"Exert this permanent\" as a **cost** (Arena of Glory): it does"
            " not untap during its controller's next untap step, and it is not"
            " `tap`, which a card may charge alongside it.",
            "`op_options` is a **lower bound**, gathered from each op's own"
            " source and from every effect the shipped pool writes. An op that"
            " forwards its spec to a helper can accept a key listed for neither,"
            " so a key's absence is not proof it does not exist -- check the"
            " `examples` too, and prefer a gap record only when both are silent.",
            "`trigger_keys` is what a trigger object may carry beside `event`,"
            " and it is where a printed rate limit lives: `max_per_turn: 1` is"
            " \"whenever you cast your FIRST ... each turn\" and \"this"
            " ability triggers only once each turn\" (a cap per permanent, so"
            " never \"an opponent casts THEIR first ... each turn\"), and"
            " `nth` is \"your second card each turn\" on a `draw` trigger and"
            " \"a player casts their Nth spell each turn\" on a `spell_cast`"
            " trigger -- counted per caster, and over the spells matching the"
            " trigger's `filter` when it has one (\"their first noncreature"
            " spell\"). A trigger's FILTER keys go inside"
            " `filter`, never on the trigger itself. A `delayed_trigger`'s own"
            " `trigger` takes `delayed_trigger_keys` instead (`subject` is"
            " \"whenever either of those creatures\"), and its `duration` is one"
            " of `delayed_durations` (`this_combat` is \"... this combat\").",
            "`target_keys` is what a card-level or ability `targets` entry may"
            " carry, and `ability_kinds` is the closed vocabulary of an"
            " ability's `kind`.",
            "A key being listed does not make it legal everywhere. `id` on an"
            " ability is accepted only on a **reflexive** one and the compiler"
            " refuses it on any other -- it is in `ability_keys` because it is"
            " a real field, and writing it on a triggered ability is a gate-2"
            " rejection.",
            "A **Class** (\"(Gain the next level as a sorcery to add its"
            " ability.)\") is `subtypes: [\"Class\"]` plus two spellings of"
            " `level`. A printed \"{W}: Level 2\" line is"
            " `{\"kind\": \"level\", \"level\": 2, \"text\": \"{W}: Level 2\","
            " \"cost\": {\"mana\": \"{W}\"}}` and nothing else -- the sorcery"
            " timing, the \"only from level 1\" restriction and the effect are"
            " rule 716.2a and the compiler supplies them. Every ability printed"
            " BELOW that line, up to the next level line, carries `\"level\": 2`"
            " whatever its kind; the abilities above the first level line carry"
            " no `level`. The reminder line needs no ability. \"When this"
            " Class becomes level 2, ...\" is a triggered ability with"
            " `\"level\": 2` and `trigger: {\"event\": \"becomes_level\","
            " \"level\": 2}`.",
            "`required_keys` is the subset of each of those lists that is NOT"
            " optional -- every ability needs a `kind`, every target an `id`"
            " and a `kind`, every trigger an `event`. A spec missing one fails"
            " schema validation before anything else about the card is looked"
            " at, so check this list against what you wrote before filing"
            " anything.",
            "`card_level_rider_keys` is what a card says about ITSELF that is"
            " neither a price nor a face -- `exiles_itself` for \"Exile <this"
            " card>.\" instead of the graveyard, `uncounterable` for \"This"
            " spell can't be countered\", `rebound`, `split_second`, `miracle`."
            " Look here before concluding a sentence about the card's own fate"
            " cannot be said.",
            "`card_level_face_keys` is how a card carries a second printed"
            " face, and which key you want turns on one question: is the other"
            " half something you TURN OVER to, or a second spell you may CAST?"
            " `back_face` is the first -- a transforming DFC, never cast, never"
            " drawn, reached only by the `transform` op. `second_face` is the"
            " second -- a split half, an Adventure, an Aftermath half -- with"
            " its own name, cost and type line, cast instead of the front from"
            " `second_face_zone` (\"hand\", or \"graveyard\" for Aftermath). A"
            " **modal double-faced card** is a `second_face` whose other half is"
            " a permanent: you play one face or the other and nothing turns"
            " over. Either way the other half is an ordinary card entry in the"
            " same pool, and your packet's `back_face` block carries its printed"
            " text -- write it as a second entry, do not file a gap.",
            "A **meld** half -- the one printing \"exile them, then meld them"
            " into <name>\" -- carries `melds_with` (its partner's card id) and"
            " `melds_into` (the result's id), and its end-step trigger is"
            " `effects: [{\"op\": \"meld\"}]` with the \"if you both own and"
            " control\" clause as `trigger.condition` (an `all` of two `exists`,"
            " each with `owner: \"you\"`, `controller: \"you\"`, the partner"
            " by `name`). The melded card goes in your answer's `back` -- your"
            " packet's `meld_result` block carries its printed text -- and the"
            " PARTNER does not: it is a card of its own with its own answer,"
            " and `--collect` brings it into the pool. The partner's"
            " \"(Melds with ...)\" line is reminder text and needs nothing.",
            "A `tap_permanents` cost may carry `as`, naming THE one permanent it"
            " tapped so the ability's effects can read it: Station (\"Tap another"
            " creature you control: Put charge counters equal to its power on"
            " this Planet\") is `{\"tap_permanents\": {\"types\": [\"Creature\"],"
            " \"exclude_self\": true, \"as\": \"stationed\"}}` with"
            " `sorcery_speed_only` and an `add_counters` whose amount is"
            " `{\"power_of\": {\"binding\": \"stationed\"}}`. Never a `count`"
            " above 1 or a `total_power` beside it.",
            "A station striation -- \"12+ | {U}, {T}: Add {U} for each artifact"
            " you control.\" -- is an activated ability with `threshold:"
            " {\"counter\": \"charge\", \"at_least\": 12}` whose `text` is the"
            " whole printed line, prefix included. The permanent HAS it only at"
            " that many counters. Activated abilities only; gated abilities go"
            " after every ungated one, in rising order. Not `condition`, which"
            " leaves the ability on the permanent.",
            "`condition_keys` and `value_keys` are what an `if` can ask and what"
            " an amount can be. `counters_on` reads a counter count off an"
            " object, so \"if this has no +1/+1 counters on it\" is a `cmp`"
            " against `{\"const\": 0}` and needs no new op.",
            "\"Your opponents can't cast spells during your turn\" is the"
            " player-wide static `cant_cast_spells` with `affects_player:"
            " \"opponent\"` and `condition: {\"is_your_turn\": true}`. It stops"
            " every spell from every zone, free casts included. \"Can't cast"
            " noncreature spells\" is the same static with `affects_spells:"
            " {\"not_types\": [\"Creature\"]}` (a spell filter: types, any_types,"
            " not_types, subtypes, colors, name, ... -- no `controller`,"
            " `affects_player` says whose). \"Can't cast spells with mana value"
            " 3 or less\" is `affects_spells: {\"mana_value\": {\"op\": \"<=\","
            " \"value\": 3}}` -- this filter only, and the engine counts an X"
            " spell's chosen X. \"More than one spell each turn\" is still a"
            " gap.",
            "\"Your opponents can't cast spells from anywhere other than their"
            " hands\" on a permanent is the player-wide static"
            " `cant_cast_spells_from_zones` with `affects_player: \"opponent\"`"
            " and `except_zones: [\"hand\"]` (or `zones: [\"graveyard\"]` for"
            " \"from graveyards\"; exactly one of the two). It lasts while the"
            " permanent does and shuts every road out of those zones, the"
            " command zone included. The timed \"until your next turn\" form on"
            " a spell is the op of the same name.",
            "\"You may spend mana as though it were mana of any color\" is the"
            " player-wide static `spend_mana_as_any_color` with `affects_player:"
            " \"you\"`; \"...to cast planeswalker spells\" is the same static"
            " with `affects_spells: {\"types\": [\"Planeswalker\"]}` (the"
            " `cant_cast_spells` spell filter), which loosens only the cast of"
            " a matching spell and never an activated ability.",
            "\"You may play them without paying their mana costs\" on cards an"
            " effect exiles is `playable_free: true` beside that effect's"
            " `playable` duration (`exile`, `look_at_top` to exile,"
            " `grant_playable`); \"for as long as they remain exiled\" is"
            " `playable: \"while_exiled\"`. The permission is always the"
            " effect controller's, cards from an opponent's library included;"
            " a land still uses a land drop, a spell keeps its timing and its"
            " additional costs, and X is 0.",
            "\"You don't lose unspent red mana as steps and phases end\" is the"
            " player-wide static `mana_retention` with `affects_player: \"you\"`"
            " and `colors: [\"R\"]`; \"Players don't lose unspent mana\" is"
            " `affects_player: \"any\"` with all six symbols (`C` included)."
            " The mana is kept across turns while the permanent stays. It is"
            " NOT `persists_until_end_of_turn`, which is one ability's mana"
            " until end of turn. \"If you would lose unspent mana, that mana"
            " becomes colorless instead\" (Kruphix, Horizon Stone) is the"
            " different player-wide static `mana_becomes_colorless` with"
            " `affects_player: \"you\"` and no `colors`: the mana is kept as"
            " {C}, not in its colours.",
            "\"You may pay any amount of {R}. When you do, it deals that much"
            " damage to any target\" is `may` with `pay: {\"mana\": \"{R}\"}` and"
            " `any_amount: {\"as\": \"paid\"}`, its `effects` a"
            " `reflexive_trigger` whose ability reads `{\"binding\": \"paid\"}`."
            " The player picks 1..what they can pay in that colour. NOT `x`"
            " with `{X}` (any colour would pay), NOT `pay.times`, NOT `repeat`.",
            "\"If you would gain life, you gain twice that much life instead\""
            " is the player-wide static `replace_life_gain` with"
            " `affects_player: \"you\"` and `gain_multiplier: 2`. It is a real"
            " replacement read wherever life is gained, lifelink included, so"
            " it is NOT a `you_gain_life` trigger that gains again. \"You gain"
            " that much life plus 1 instead\" is the same static with"
            " `gain_addend: 1` in place of `gain_multiplier` (one or the other,"
            " never both).",
            "\"It deals that much damage plus 1 instead\" is the static"
            " `replace_damage` with `damage_addend: 1` in place of"
            " `damage_multiplier` (one or the other, never both), filtered as"
            " the doubler is: \"another source you control\" is"
            " `damage_source: {\"controller\": \"you\", \"exclude_self\": true}`"
            " (any zone, burn spells included), \"to an opponent or a permanent"
            " an opponent controls\" is `affects_player: \"opponent\"` with"
            " `affects: {\"controller\": \"opponent\"}`. NOT a damage trigger"
            " dealing 1 more.",
            "\"If you gained life this turn\" is the value"
            " `{\"life_gained_this_turn\": \"you\"}` compared `>` against"
            " `{\"const\": 0}` -- on a trigger, as its `condition` (an"
            " intervening if). It is the turn's ledger, so it counts gains made"
            " before the permanent entered; never an unprinted `you_gain_life`"
            " trigger setting a flag.",
            "\"If you didn't activate a loyalty ability of a planeswalker this"
            " turn\" is the value `{\"loyalty_activations_this_turn\": \"you\"}`"
            " compared `==` against `{\"const\": 0}`, as the trigger's"
            " `condition`. A per-player tally counted at activation, so it"
            " remembers a planeswalker that has since left.",
            "\"Your opponents can't gain life\" is the player-wide static"
            " `cant_gain_life` with `affects_player: \"opponent\"` (\"you\""
            " and \"any\" for the other sentences). Every gain is stopped,"
            " lifelink included, and no life-gain trigger fires; it beats a"
            " `replace_life_gain`. \"Damage can't be prevented\" and \"your"
            " life total can't change\" are other effects.",
            "\"Each opponent can't draw more than one card each turn\" is the"
            " player-wide static `draw_limit` with `affects_player:"
            " \"opponent\"` and `amount: {\"const\": 1}` (\"each player\" is"
            " `\"any\"`). It counts every card drawn that turn, and a draw past"
            " the cap simply does not happen.",
            "\"Spells and abilities your opponents control can't cause their"
            " controller to search their library\" is the player-wide static"
            " `cant_search_library` with `affects_player: \"opponent\"`. Their"
            " own searches find nothing in their library but still shuffle.",
            "\"Spells and abilities your opponents control can't cause you to"
            " discard cards or sacrifice permanents\" is the player-wide static"
            " `opponents_cant_force_discard_or_sacrifice` with `affects_player:"
            " \"you\"` -- keyed on who controls the cause, so your own spells"
            " and costs still discard and sacrifice. Not `cant_sacrifice`.",
            "\"Choose a (nonland) card name\" is the op `choose_card_name` with"
            " `as` (and `not_types: [\"Land\"]`); a later selector matches it"
            " with `name: {\"binding\": <as>}` -- e.g. a `look_at_top` whose"
            " `objects` is `{\"name\": {\"binding\": \"named\"}, \"count\":"
            " \"all\"}` with `rest_to: \"graveyard\"`.",
            "\"If you would draw a card, draw two cards instead\" is the"
            " player-wide static `replace_draw` with `affects_player: \"you\"`"
            " and `draw_multiplier: 2`; \"...except the first one you draw in"
            " each of your draw steps\" adds `except_first_in_draw_step: true`."
            " It is a real replacement of each draw, so it is NOT a `draw`"
            " trigger that draws an extra card. \"Skip your draw step\" is"
            " `skip_draw_step`, and a replacement that does something other"
            " than draw more cards (\"exile the top card instead\") is still a"
            " gap.",
            "\"Crew N\" is an activated ability whose `cost` is `tap_permanents`"
            " with `total_power: N`. \"This creature crews Vehicles as though"
            " its power were 2 greater\" is the static `crew_power_bonus` with"
            " `affects: {\"self_only\": true}` and `amount: {\"const\": 2}` --"
            " not `buff`, which changes real power. The Pilot token printing"
            " that line is `pilot_1_1_c_crew2`; a Pilot that also \"saddles"
            " Mounts\" is a different token and is still a gap.",
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
            " selector language. A static's `affects` reads"
            " `static_affects_filter_keys`, which adds `any_of`: a union of"
            " whole filters, each branch the outer filter plus its own keys, so"
            " \"Skeletons you control and other Zombies you control\" is one"
            " `affects` with `exclude_self` on the Zombie branch only -- never"
            " two statics, which pump a creature that is both twice.",
            "A selector's `controller` (and `player`, for a zone somebody owns)"
            " takes a player spec as well as \"you\"/\"opponent\"/\"any\"."
            " `{\"target\": \"t1\"}` there means EVERY player target t1 chose, so"
            " \"the number of creatures those opponents control\" after \"choose"
            " any number of target opponents\" is `{\"count\": {\"types\":"
            " [\"Creature\"], \"controller\": {\"target\": \"t1\"}}}` -- and"
            " \"creatures they control\" after one target player is the same"
            " clause. Targets that became illegal are dropped on resolution."
            " `controller: \"opponent\"` is NOT it: that counts every opponent,"
            " targeted or not.",
            "\"This spell/ability costs {N} less\" is `cost_reduction` on the"
            " card, or `mana_reduction` on an activated ability's `cost` or a"
            " `flashback` node. It takes exactly one of `cost_reduction_keys`"
            " -- `count`, `total_power` and `greatest_mana_value` each take a"
            " filter, `amount` is a flat number and needs a `condition` -- and"
            " a filter may use `cost_reduction_filter_keys` only. Every key in"
            " that list is honoured, so \"for each legendary creature you"
            " control\" is"
            " `{\"count\": {\"controller\": \"you\", \"types\": [\"Creature\"],"
            " \"supertypes\": [\"Legendary\"]}}`; anything outside it is a load"
            " error rather than a discount counted wrong.",
            "An ability's `text` must be the printed sentence it implements: the"
            " residual gate asks each ability which line it claims, and anything"
            " unclaimed means the card is only half implemented.",
            "An instant or sorcery puts its effects in `spell_effects`; a"
            " permanent puts them in `abilities`.",
            "`card_level_cost_keys` is what the *card* may charge -- an"
            " alternative or additional cost, set as a field on the card"
            " itself rather than inside an ability. A printed line that is"
            " just a mechanic and a price (\"Bestow {1}{G}\", \"Evoke"
            " {2}{U}\", \"Kicker {1}{R}\") is one of these, and no ability"
            " can carry it: an ability is activated, triggered or static, and"
            " a cost is none of the three. Do not invent an ability to hold"
            " the line, and do not put the mechanic in `keywords` -- the"
            " loader knows only the 34 ability keywords and rejects the rest.",
            "`cost_keys` is what an activated ability's `cost` may contain."
            " A printed \"<cost>: <effect>\" line splits into a `cost` from"
            " that list and `effects` from `ops` -- paying with an op instead"
            " moves the payment to resolution and lets the ability be"
            " activated when it could not be paid for.",
            "`alternative_cost` takes a whole cost from `cost_keys` plus an"
            " optional `condition`, not just a mana string: \"You may pay 1"
            " life and exile a blue card from your hand rather than pay this"
            " spell's mana cost\" is `{\"pay_life\": 1, \"exile_from_hand\":"
            " {\"colors\": [\"U\"]}}`, with no mana at all. The `condition` is"
            " needed only when the price is mana and nothing else -- an"
            " unconditional cheaper mana price is `evoke`.",
            "`evoke` is the mechanism, not the keyword: an unconditional"
            " alternative mana cost plus the `evoked` condition that reads"
            " whether it was paid, with `evoke_label` naming the cost on the"
            " cast line (\"dash\", or \"paying {1}{B}\" for a card that gives"
            " it no name). It works on an instant or sorcery too, read inside"
            " `spell_effects`: \"You may pay {1}{B} rather than pay this"
            " spell's mana cost. If the {1}{B} cost was paid, ...\" is"
            " `\"evoke\": \"{1}{B}\"` plus an `if` on `{\"evoked\": true}`.",
            "Exiling from hand as a cost is two keys, the way discarding is:"
            " `exile_from_hand` picks a card by selector (\"a blue card\"),"
            " and `exile_self_from_hand` is \"Exile this card from your hand\""
            " with no choice about which card goes -- Simian Spirit Guide, on"
            " an ability with `active_zones: [\"hand\"]`. `exile_self` is a"
            " different cost: it is \"Exile this artifact\" and requires the"
            " source to be on the battlefield.",
            "A quoted ability a permanent GAINS (\"This Saga gains \\\"{T}: Add"
            " {C}.\\\"\", \"It gains \\\"When this creature dies, ...\\\"\") is"
            " written once under the card's `grantable_abilities` and handed"
            " over by index. A one-shot gain is the `grant_ability` op --"
            " `duration: \"permanent\"` when no duration is printed, and"
            " `objects: {\"self_only\": true}` for \"this Saga gains\" -- and"
            " it may grant a triggered or an activated ability, mana or not."
            " \"As long as ...\" / \"have ...\" is the `grant_ability` static,"
            " which may also grant a static. A granted activated ability works"
            " on the battlefield only.",
            "\"You get an emblem with \\\"...\\\"\" / \"Target opponent gets an"
            " emblem with \\\"...\\\"\" writes the quoted abilities once under the"
            " card's `emblems` -- `[{\"abilities\": [...]}]`, no `active_zones`,"
            " the loader puts them in the command zone -- and gives one with the"
            " `emblem` op: `{\"op\": \"emblem\", \"player\": \"you\" | {\"target\":"
            " \"t1\"}, \"emblem\": 0}`. `player` is required. \"You\" on the"
            " emblem is the player who got it. Triggered and static abilities"
            " may both be on an emblem; an activated one is still a gap,"
            " because nothing offers an activation from the command zone.",
            "Eminence and any other static that works from the command zone is"
            " `active_zones` on the static: \"As long as this is in the command"
            " zone or on the battlefield, ...\" is one ability with"
            " `\"active_zones\": [\"battlefield\", \"command\"]`, because being"
            " gathered from either zone IS the \"as long as\" -- the same"
            " argument as `[\"graveyard\"]` on Anger. Do not write a condition"
            " for the zone. \"**Other** ... spells you cast cost {N} less\" adds"
            " `\"exclude_self\": true` to a `spell_cost_reduction`'s"
            " `affects_spells`, which matters exactly here: a commander is cast"
            " out of the zone its own eminence static is read from.",
            "\"You may cast this card from your graveyard [as long as ...]\" --"
            " the card's own permission, at its printed price -- is a"
            " `cast_from_graveyard` static with `\"active_zones\":"
            " [\"graveyard\"]`, `\"affects_player\": \"you\"` and the \"as long"
            " as\" as its `condition`; no `affects_spells` or `max_per_turn`,"
            " since it frees only the card carrying it. Permanent cards only."
            " It is not `graveyard_cost`, which is an alternative price with no"
            " condition, offered always.",
            "\"Create a <Name> Role token attached to <it>\" is `create_token`"
            " with `attached_to`, a selector naming the host -- never"
            " `create_token` then `attach`, which makes the Role even when the"
            " host is gone. The Role rule (one Role per player per permanent)"
            " is a state-based action and is not written on the card. Only Role"
            " tokens that exist in `token_ids` can be created.",
            "A static ability's filter may only read printed characteristics.",
            "\"If one or more tokens would be created under your control, twice"
            " that many of those tokens are created instead\" (Parallel Lives,"
            " Anointed Procession, Doubling Season's token half) is a"
            " `replace_token_creation` static with `token_multiplier: 2` and no"
            " `create_instead` -- the tokens keep their identity, so copies stay"
            " copies. `create_instead` is the OTHER axis (which token is made"
            " instead) and a static takes one or the other. \"Creature tokens\""
            " is an `affects_token` filter; a sentence naming no player (\"if one"
            " or more tokens would be created\") adds `affects_player: \"any\"`.",
            "\"If an effect would put one or more counters on a permanent you"
            " control, it puts twice that many…\" (Doubling Season) is a"
            " `replace_counters` static with `counter_multiplier: 2`,"
            " `affects: {controller: you}` and `effects_only: true` -- \"an"
            " effect\" excludes a cost, so a planeswalker's +1 still puts one"
            " loyalty counter. Without \"an effect\" in the sentence (Hardened"
            " Scales' \"would be put\") leave `effects_only` out: costs count.",
            "\"If you would put one or more counters on a permanent or player,"
            " put twice that many…\" (Innkeeper's Talent, Vorinclex) is"
            " `replace_counters` with `counter_multiplier: 2`, `put_by: \"you\"`"
            " and `affects_player: \"any\"`, and no `affects` -- keyed on who"
            " puts the counters, any permanent, and players (poison).",
            "\"…with counters on them\" / \"…with a counter on it\" is the"
            " filter key `has_counters: true` (any kind of counter), valid in a"
            " static's `affects` and in an effect selector.",
            "\"Distribute N +1/+1 counters among up to N target creatures\" on an"
            " ACTIVATED ability (a planeswalker's loyalty line) is"
            " `distribute_counters` with `counter`, a printed `amount` and"
            " `objects: {\"target\": \"t1\"}`, the target spec `count: N,"
            " up_to: true`; the division is asked on activation. Not available"
            " on spells or triggered abilities.",
            "\"…tapped and attacking that player or a planeswalker they control\""
            " (Adeline, Resplendent Cathar) is `attacking` naming the seat -- e.g."
            " `{\"binding\": \"each_player\"}` inside a `for_each_player` -- plus"
            " `or_planeswalker: true`, on `create_token`, `copy_permanent` or"
            " `put_onto_battlefield`. The creature's controller then chooses the"
            " seat or one of its planeswalkers (508.4). Without the key the token"
            " can only attack the player, which is a narrower card.",
            "`snapshot` is how a card reads a value after its target has left --"
            " there is no general last-known-information system.",
            "A mana ability's MANA half may contain only `add_mana`, or one"
            " `choose_mode` whose modes each contain only `add_mana` -- and it"
            " may then be followed by a **rider**, one or more of"
            f" {sorted(MANA_RIDER_OPS)}, which happen on activation without the"
            " stack exactly as the mana does. That is how"
            " \"{T}: Add {U}. Remove a time counter from this land.\" is"
            " written (Temple of Cyclical Time), and \"{T}: Add {B}. This"
            " creature deals 1 damage to you.\" The rider belongs to the"
            " ABILITY, not to `add_mana`, so it is not in `op_options` -- this"
            " note used to say a mana ability may contain only `add_mana`, and"
            " a worker filed a gap against a rider the loader has always"
            " accepted.",
            "\"Add one mana of any **type** that a land you control could"
            " produce\" (Reflecting Pool, Horizon of Progress, Naga Vitalist) is"
            " `reflecting` plus `any_type: true` on the same `add_mana`. 106.1b"
            " names six types of mana, so \"any type\" is \"any color\" plus"
            " `{C}`, and plain `reflecting` drops `{C}` on purpose -- a Pool"
            " written without the flag cannot tap off a Wastes. The flag is read"
            " by the LOADER rather than by `op_add_mana`, so until a card using"
            " it ships it is not in `op_options`; it is refused on any `add_mana`"
            " that has no `reflecting`, because nothing else reads it.",
            "\"Add one mana of any of **the exiled card's colors**\" (Chrome"
            " Mox) is `colors_of` on the `add_mana`, holding a selector over"
            " the CARDS whose printed colours are offered --"
            " `{\"zone\": \"exile\", \"controller\": \"any\","
            " \"exiled_with\": \"self\"}` for an imprint. It is the fifth way an"
            " `add_mana` may name its colours and is read by the LOADER, so it"
            " is not in `op_options`. `reflecting` is the near miss and is a"
            " different card: it asks each matched object's own mana ABILITIES"
            " what they could produce, and an imprinted nonartifact, nonland"
            " card in exile has none -- so a Mox written that way taps for"
            " nothing for ever. A `choose_mode` over five `add_mana`s is the"
            " other near miss and is strictly BETTER than the printed card,"
            " because it taps for any colour with nothing imprinted at all."
            " Nothing imprinted offers nothing, and so does a colourless"
            " imprint (105.1); there is no `any_type` here, and it is refused"
            " beside `colors_of`.",
            "\"Vivid -- {T}: **For each color among permanents you control,"
            " add one mana of that color**\" (Bloom Tender) is"
            " `each_color_among` on the `add_mana`, holding the selector whose"
            " matches are read for colour --"
            " `{\"zone\": \"battlefield\", \"controller\": \"you\"}`. It is the"
            " sixth way an `add_mana` may name its colours, it is read by the"
            " LOADER (so it is not in `op_options`), and it is the only one"
            " whose output is a BUNDLE: a board showing three colours taps it"
            " for three mana, one of each, with nothing asked. `colors_of` over"
            " the same selector is the near miss and is Mox Amber -- one mana"
            " of a colour the payer picks -- and `add_mana_per` is the other,"
            " adding one mana per matching PERMANENT rather than one per"
            " colour (and it is not a legal mana effect at all). Colourless is"
            " not a colour (105.1), so an all-artifact board adds nothing;"
            " there is no `any_type` here and no `amount`, and the key is"
            " refused beside `mana`, `reflecting`, `colors_of`,"
            " `in_commander_identity` and `split`.",
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

    The registry should be the whole pool, machine-authored cards included:
    every one of them passed the same six gates, and some shapes exist *only*
    there. No hand-written card is a planeswalker, so a packet drawn from the
    hand-written files alone showed a planeswalker three creatures and never
    the signed `cost.loyalty` its every ability is written with.
    """

    wanted_types = set(card.type_line.replace("—", " ").split())
    scored: list[tuple[int, dict]] = []
    for existing in registry:
        if existing.is_token or not existing.oracle_text or existing.name == card.name:
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


@lru_cache(maxsize=1)
def _authored_json() -> dict[str, dict]:
    """Every authored card as it was written, keyed by id.

    A compiled `Ability` does not keep the JSON it came from, so a worked
    example rebuilt from the registry would show a card's name and types and
    none of its abilities -- which are the whole point of showing it.
    """
    out: dict[str, dict] = {}
    for path in authored_card_paths():
        raw = json.loads(path.read_text(encoding="utf-8"))
        for entry in raw["cards"] if isinstance(raw, dict) else raw:
            if isinstance(entry, dict) and "id" in entry:
                out[entry["id"]] = entry
    return out


def _as_payload(card) -> dict:
    """A compiled card back into the JSON shape a packet shows: the card as it
    was authored when its file can be found, else the characteristics alone."""
    authored = _authored_json().get(card.id)
    if authored is not None:
        return {k: v for k, v in authored.items() if not k.startswith("_")}
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

_MELDS_INTO = re.compile(r"\bmeld them into ([^.]+)\.")


def meld_result_of(entry: IndexEntry, index) -> dict:
    """The melded card this half names, as a plain dict, or ``{}``.

    Looked up by the name the printed sentence gives, because the catalog has no
    other link between a meld half and its result.
    """
    found = _MELDS_INTO.search(entry.oracle_text or "")
    if index is None or found is None:
        return {}
    result = index.lookup(found.group(1).strip(), token=False)
    if result is None:
        return {}
    return {
        "name": result.name,
        "type_line": result.type_line,
        "mana_cost": result.mana_cost,
        "power": result.power,
        "toughness": result.toughness,
        "oracle_text": result.oracle_text,
    }


def build_packet(
    entry: IndexEntry, registry: CardRegistry, template_said: str, index=None
) -> Packet:
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
        meld_result=meld_result_of(entry, index),
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
    return {card_id: payload for card_id, (_, payload) in _answer_files().items()}


def _answer_files() -> dict[str, tuple[Path, dict]]:
    """Every readable answer, keyed by the card id it carries, with its path.

    Keyed by ``card.id`` rather than by file name, as :func:`read_answers` always
    was: the two normally agree, but `bloodline_keeper_lord_of_lineage.json`
    carried `bloodline_keeper`, and retiring by file name would have left it.
    """
    out: dict[str, tuple[Path, dict]] = {}
    if not answers_dir().exists():
        return out
    for path in sorted(answers_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        card = payload.get("card")
        if isinstance(card, dict) and card.get("id"):
            out[card["id"]] = (path, payload)
    return out


def retire(card_ids: set[str]) -> int:
    """Delete the answer and the packet of every card id given; return how many files.

    Called by ``author_cards.py --collect`` for each card it has just written
    into ``data/cards/auto/``. From that moment the pool is the card's only
    source of truth: an answer left on disk is re-verified and rewritten into
    ``templates.cards.json`` on every later collect, which silently reverts any
    fix made to the collected card. So ``answers/`` holds work in progress and
    nothing else, and the packet -- regenerable by ``--tier agent`` -- goes with it.
    """
    removed = 0
    paths = [path for card_id, (path, _) in _answer_files().items() if card_id in card_ids]
    paths += [packets_dir() / f"{card_id}.json" for card_id in sorted(card_ids)]
    for path in paths:
        if path.exists():
            path.unlink()
            removed += 1
    return removed
