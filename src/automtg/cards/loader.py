"""Compile validated card JSON into immutable engine objects.

Validation happens in three passes:

1. **Shape** -- pydantic models in :mod:`automtg.cards.schema`.
2. **Vocabulary** -- every effect op, selector key, value form, trigger event,
   keyword and type name must be one the engine actually implements.
3. **Constraints** -- static ability filters may only read printed
   characteristics (see :mod:`automtg.engine.characteristics`), and abilities
   flagged as mana abilities must really be mana abilities.

Anything that fails raises :class:`~automtg.engine.errors.DslError` at load time.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from automtg.engine.carddef import (
    Ability,
    CardDef,
    Cost,
    TargetSpec,
    TriggerSpec,
    build_type_line,
    prune_cost,
)
from automtg.engine.effects import RECORDING_OPS, known_ops
from automtg.engine.effects.conditions import validate_condition
from automtg.engine.effects.ops_cards import DESTINATIONS, SEARCHABLE
from automtg.engine.effects.selectors import PLAYER_SPEC_NAMES, validate_selector
from automtg.engine.effects.values import (
    PER_PLAYER_COUNT_KEYS,
    validate_counter_kind,
    validate_counters_on,
    validate_mana_symbols,
    validate_per_player_count,
    validate_value,
)
from automtg.engine.enums import (
    AbilityKind,
    CardType,
    Color,
    Keyword,
    Supertype,
    Zone,
)
from automtg.engine.errors import DslError
from automtg.engine.mana import CHOSEN_TYPE, ManaCost, ManaRestriction, parse_mana_production
from automtg.engine.structs import (
    ATTACK_RESTRICTION_DURATIONS,
    BLOCK_PROHIBITION_DURATIONS,
    CONTROL_DURATIONS,
    UNBLOCKABLE_DURATIONS,
)
from automtg.engine.triggers import TRIGGER_EVENTS
from automtg.engine.turn import DELAY_STEPS

from .schema import AbilityModel, CardModel, CostModel, DeckModel, TargetModel

KNOWN_TYPES = frozenset(t.value for t in CardType)
KNOWN_SUPERTYPES = frozenset(s.value for s in Supertype)
KNOWN_KEYWORDS = frozenset(k.value for k in Keyword)
KNOWN_COLORS = frozenset(c.value for c in Color)

#: Static ability effects the characteristics pipeline understands.
STATIC_EFFECTS = frozenset(
    {
        "buff",
        "grant_keyword",
        "set_pt",
        "add_subtype",
        # "As long as Arixmethes has a slumber counter on it, it's a land."
        # Replaces the printed types rather than adding to them, which is the
        # whole point: the parenthetical says "it's not a creature".
        "set_types",
        "extra_land_drops",
        # Player-wide, like `extra_land_drops`: a fact about the player rather
        # than a characteristic, with no object for it to attach to.
        "no_hand_limit",
        "play_lands_from_graveyard",
        "play_lands_from_library_top",
        # "Play with the top card of your library revealed." Player-wide, and
        # the only static here that changes nothing about the rules: it grants
        # no permission and moves no card, it makes one card public. Read by
        # `serialize`, and by nothing else.
        "reveal_library_top",
        # Parameterised, so it cannot be a keyword: "protection from Wizards"
        # names a quality, and four separate rules (damage, enchant/equip,
        # block, target) ask about it.
        "protection",
        # Absorb (702.63a): "If a source would deal damage to this creature,
        # prevent N of that damage." Parameterised on N, so a static and not a
        # keyword -- and *not* protection, which prevents all of it and three
        # other things besides. Read by `damage_permanent` alone.
        "prevent_damage",
        # Ancient Greenwarden.  A fact about the *player*, like the two above:
        # it is read by `triggers.collect` rather than by the characteristics
        # pipeline, and there is no object for it to attach to.
        "double_land_triggers",
        # Vorinclex's two halves.  Both are read at the mana choke point rather
        # than as triggers, because tapping for mana happens inside payment
        # where nothing can go on the stack.
        "double_land_mana",
        "freeze_opponent_lands",
        # "This creature can't be blocked by Humans", and Tromokratis'
        # "can't be blocked unless all creatures defending player controls
        # block it".  Read by `combat`, not by the characteristics pipeline.
        "block_restriction",
        # Murkfiend Liege.  Read by `turn._untap_step`, not by the
        # characteristics pipeline: it is a fact about when a set of
        # permanents untaps, which no characteristic can carry.
        "untap_during_each_untap_step",
        # Stormtide Leviathan.  Read by `combat.can_attack`.  A global
        # prohibition, so unlike every other static here its `affects`
        # routinely names creatures its own controller does not control.
        "cant_attack",
        # Unleash, and the "can't block" printed on aggressive commons. The
        # mirror of `cant_attack`, read by `combat.can_block`, and a static
        # rather than a keyword for the same reason `block_restriction` is: a
        # keyword is a characteristic and this is a permission.
        "cant_block",
        # Marauding Maulhorn.  The obligation to `cant_attack`'s prohibition,
        # read by `combat.attack_required` at the same enforcement point the
        # `must_attack` op uses.  A static rather than that op because a
        # printed "attacks each combat if able" is true again every turn, where
        # the op writes a one-shot flag that is spent on declaration.
        "attacks_if_able",
        # Ward. Parameterised on a *cost*, so it cannot be a keyword for the
        # reason `protection` cannot: `KNOWN_KEYWORDS` is a set of bare strings
        # and there is nowhere in one to put the `{1}`. Read by
        # `triggers._candidate_abilities` rather than by the characteristics
        # pipeline, because what it hands out is a triggered ability -- and it
        # hands it to the *warded* permanent, so killing the granter in response
        # does not escape the tax.
        "ward",
        # Warden of Evos Isle.  Read by `costs.cost_reduction`, not by the
        # characteristics pipeline: it prices a card that is still in hand, so
        # its filter (`affects_spells`) matches a printed face rather than a
        # permanent, and is a different list from `affects`.
        "spell_cost_reduction",
    }
)

#: Keys a ``spell_cost_reduction`` static's ``affects_spells`` filter may use.
#:
#: Deliberately not `STATIC_FILTER_KEYS`: that list describes *permanents* and
#: carries board state (`tapped`, `attacking`, `attached`) which a card in hand
#: does not have.  These are the printed face plus who is casting it, which is
#: all `characteristics._matches_printed` reads.
SPELL_FILTER_KEYS = frozenset(
    {
        "controller",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
        "name",
    }
)

#: Keys a *static* ability's filter may use.  Deliberately smaller than the full
#: selector language: static filters are matched against printed characteristics
#: so that no static can depend on another static's output.
STATIC_FILTER_KEYS = frozenset(
    {
        "exclude_self",
        "self_only",
        "controller",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        # "Creatures **without** flying or islandwalk can't attack."  The
        # negated form, which the effect-side selector language always had
        # and the static one did not.
        "not_keywords",
        "tapped",
        "is_commander",
        "is_token",
        "attacking",
        "blocking",
        # "Enchanted creature gets +2/+2".  Reads `attached_to`, which is board
        # state rather than a derived characteristic, so it cannot depend on
        # another static's output and belongs in this list rather than outside it.
        "attached",
        # Soulbond: "as long as this creature is paired, **both** creatures
        # have…". `paired: true` matches the source while it has a partner, and
        # `paired_with_source: true` matches the partner. Board state like
        # `attached`, and safe for the same reason.
        "paired",
        "paired_with_source",
    }
)


# ----------------------------------------------------------------------
# public API
# ----------------------------------------------------------------------


def load_cards(paths: Iterable[Path]) -> dict[str, CardDef]:
    """Load every card file into a ``{card_id: CardDef}`` mapping."""
    cards: dict[str, CardDef] = {}
    for path in paths:
        for card in load_card_file(path):
            if card.id in cards:
                raise DslError(f"duplicate card id {card.id!r} (second definition in {path})")
            cards[card.id] = card
    return cards


def load_card_file(path: Path) -> list[CardDef]:
    """Load one ``*.cards.json`` file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw["cards"] if isinstance(raw, dict) else raw
    out: list[CardDef] = []
    for entry in entries:
        try:
            model = CardModel.model_validate(entry)
        except Exception as exc:  # pydantic ValidationError
            name = entry.get("id", entry.get("name", "<unknown>")) if isinstance(entry, dict) else "?"
            raise DslError(f"{path.name}: card {name!r} failed validation: {exc}") from exc
        out.append(compile_card(model, source=path.name))
    return out


def load_deck_file(path: Path) -> DeckModel:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        return DeckModel.model_validate(raw)
    except Exception as exc:
        raise DslError(f"{Path(path).name}: deck failed validation: {exc}") from exc


# ----------------------------------------------------------------------
# compilation
# ----------------------------------------------------------------------


def _replacements_with_loyalty(model: CardModel) -> tuple[dict[str, Any], ...]:
    """A card's replacements, plus the one its starting loyalty implies.

    Loyalty **is** counters (306.5b), so a planeswalker's starting loyalty is an
    enters-with-counters replacement and nothing new runs when one arrives.
    Everything the engine already does with counters -- proliferate, the client's
    badge, `counters_on` -- reads loyalty for free because there is nothing else
    to read.

    Written here rather than asked of the card's author, because a planeswalker
    that entered with no loyalty would be binned by the zero-loyalty state-based
    action the instant it resolved, and nothing would say why.
    """
    out = [r.model_dump() for r in model.replacements]
    if model.loyalty is not None:
        out.append(
            {
                "event": "self_enters_with_counters",
                "counter": "loyalty",
                "amount": model.loyalty,
                "modify": {},
                "condition": None,
            }
        )
    return tuple(out)


def compile_card(model: CardModel, *, source: str = "") -> CardDef:
    where = f"{source}:{model.id}" if source else model.id

    for t in model.types:
        if t not in KNOWN_TYPES:
            raise DslError(f"{where}: unknown card type {t!r}")
    for s in model.supertypes:
        if s not in KNOWN_SUPERTYPES:
            raise DslError(f"{where}: unknown supertype {s!r}")
    for k in model.keywords:
        if k not in KNOWN_KEYWORDS:
            raise DslError(f"{where}: unknown keyword {k!r} (implemented: {sorted(KNOWN_KEYWORDS)})")

    mana_cost = ManaCost.parse(model.mana_cost)
    kicker = ManaCost.parse(model.kicker) if model.kicker else None
    if kicker is not None:
        if kicker.x_count:
            raise DslError(f"{where}: a kicker cost with X is not implemented")
        if kicker.mana_value() == 0:
            raise DslError(f"{where}: kicker {model.kicker!r} costs nothing")

    if CardType.CREATURE.value in model.types and (model.power is None or model.toughness is None):
        raise DslError(f"{where}: creatures need power and toughness")

    targets = _compile_targets(model.targets, where)
    target_ids = {t.id for t in targets}
    for i, effect in enumerate(model.spell_effects):
        _validate_effect(effect, f"{where}.spell_effects[{i}]", target_ids)

    for i, replacement in enumerate(model.replacements):
        if replacement.counter is not None:
            # "…enters with a vigilance counter on it." Checked here for the
            # reason the condition below is: the kind is only looked at when a
            # permanent actually enters, so a near-miss spelling of a keyword
            # counter would arrive as an inert tally mid-game rather than being
            # refused at load.
            _check_counter_kind(
                replacement.counter, f"{where}.replacements[{i}].counter"
            )
        # How many, which may be a value expression -- "a +1/+1 counter on it
        # for each other Human you control". Checked for the same reason the
        # condition below is: `zones._enter_battlefield` only evaluates it when
        # a permanent actually enters, so an unknown value key would be a
        # mid-game crash rather than a card that refuses to load.
        validate_value(replacement.amount, f"{where}.replacements[{i}].amount")
        for kind, amount in ((replacement.modify or {}).get("counters") or {}).items():
            # The other spelling of the same clause: `modify: {"counters": {...}}`
            # keyed by kind. `zones._enter_battlefield` reads whichever is there,
            # and evaluates either as a value -- so both are checked as one.
            _check_counter_kind(kind, f"{where}.replacements[{i}].modify.counters")
            validate_value(amount, f"{where}.replacements[{i}].modify.counters.{kind}")
        if replacement.condition is None:
            continue
        # Without this the tree is only checked when a permanent actually
        # enters, which turns a typo in a land into a mid-game crash instead of
        # a card that refuses to load.
        validate_condition(replacement.condition, f"{where}.replacements[{i}].condition")

    abilities = tuple(
        _compile_ability(a, i, where) for i, a in enumerate(model.abilities)
    )
    grantable = tuple(
        _compile_ability(a, i, f"{where}.grantable")
        for i, a in enumerate(model.grantable_abilities)
    )
    for ability in grantable:
        if not ability.is_triggered:
            # Only triggered abilities can be granted so far. A granted *static*
            # would have to join the characteristics pipeline from an object
            # that is not its source, and a granted *activated* one would need
            # `Action` to carry where it came from before legality could offer
            # it -- so it would be accepted here and then never appear, which is
            # the exact "looks implemented, does nothing" failure this pass
            # exists to refuse. Granting a keyword is what `grant_keyword` is
            # for; `docs/rules-coverage.md` records the rest as not implemented.
            raise DslError(
                f"{where}: only triggered abilities can be granted, not {ability.kind.value}"
            )

    if model.cost_reduction is not None:
        _validate_cost_reduction(model.cost_reduction, f"{where}.cost_reduction")

    suspend = None
    if model.suspend is not None:
        unknown = set(model.suspend) - {"cost", "counters"}
        if unknown:
            raise DslError(f"{where}.suspend: unsupported keys {sorted(unknown)}")
        counters = int(model.suspend.get("counters", 0))
        if counters < 1:
            # Suspend 0 would resolve on the upkeep it was suspended, which is
            # not what any printed card says and would hide a typo.
            raise DslError(f"{where}.suspend: 'counters' must be at least 1")
        suspend = (ManaCost.parse(model.suspend.get("cost")), counters)

    # Kicker is two halves that only mean anything together: the extra cost, and
    # an `if` that reads it.  Half a kicker is the failure this pass exists to
    # catch -- a spell that charges more and does the same thing, or one whose
    # kicked clause can never fire, and nothing on the board would say so.
    # `buyback` reads it too, and not through an effect: the rider in
    # `_place_after_resolution` is what the extra mana buys, so a buyback card
    # has no `kicked` clause anywhere in its effects and is not half a kicker.
    reads_kicked = _mentions_kicked(model) or model.buyback
    if _mentions_kicked(model) and kicker is None:
        raise DslError(f"{where}: reads the 'kicked' condition but has no 'kicker' cost")
    if kicker is not None and not reads_kicked:
        raise DslError(f"{where}: has a 'kicker' cost that no effect reads via 'kicked'")

    # Evoke is two halves the same way, and half of it is the same silent
    # failure: a cheaper cast that never dies, or a sacrifice clause that can
    # never fire.  Both would load cleanly.
    evoke = ManaCost.parse(model.evoke) if model.evoke else None
    emerge = ManaCost.parse(model.emerge) if model.emerge else None
    if emerge is not None and evoke is not None:
        # Checked before either half-a-cost guard below, because a card
        # carrying both trips those first and the message would name the
        # wrong problem.
        raise DslError(f"{where}: a card may not have both 'evoke' and 'emerge'")
    if evoke is not None and evoke.x_count:
        raise DslError(f"{where}: an evoke cost with X is not implemented")
    # Bestow (702.103a). An alternative cost like evoke, and the two guards it
    # needs are both about the *type line*: a non-creature with bestow has
    # nothing to "become a creature again" as, and a card that is already an
    # Aura would be one twice over -- the second Aura-ness silently doing
    # nothing while the card looks implemented.
    bestow = ManaCost.parse(model.bestow) if model.bestow else None
    if bestow is not None:
        if "Creature" not in model.types:
            raise DslError(
                f"{where}: 'bestow' is only on creature cards (702.103a) -- there is "
                f"nothing for it to become a creature again as"
            )
        if "Aura" in model.subtypes:
            raise DslError(
                f"{where}: 'bestow' on a card that is already an Aura -- bestow is "
                f"what makes it one, and this card would be an Aura twice"
            )
    # Meld needs both halves of its own sentence: a partner with nothing to
    # become, or a result with no partner to meld with, is a trigger that can
    # never fire and a card that looks implemented.
    if (model.melds_with is None) != (model.melds_into is None):
        raise DslError(
            f"{where}: 'melds_with' and 'melds_into' come as a pair -- one alone is "
            f"a meld that can never happen"
        )
    # Mutate (702.140a). A creature card, for bestow's reason and one more: the
    # merged permanent *is* the top card, so a non-creature on top would make a
    # creature stop being one -- which is a different keyword.
    mutate = ManaCost.parse(model.mutate) if model.mutate else None
    if mutate is not None and "Creature" not in model.types:
        raise DslError(
            f"{where}: 'mutate' is only on creature cards (702.140a) -- the merged "
            f"permanent is the card on top, and this one is not a creature"
        )
    if mutate is not None and bestow is not None:
        # Both are alternative costs that land somewhere other than the
        # battlefield on their own, and no printing has both. Offered together
        # they would be two lines whose targets mean different things.
        raise DslError(f"{where}: a card may not have both 'bestow' and 'mutate'")
    reads_evoked = _mentions_condition(model, "evoked")
    if reads_evoked and evoke is None:
        raise DslError(f"{where}: reads the 'evoked' condition but has no 'evoke' cost")
    if evoke is not None and not reads_evoked:
        raise DslError(f"{where}: has an 'evoke' cost that no effect reads via 'evoked'")
    if emerge is not None and emerge.x_count:
        raise DslError(f"{where}: an emerge cost with X is not implemented")
    if evoke is not None:
        # What no alternative may ever be is *the same price as the printed
        # one*: that is one cast offered twice, and the second line is dead
        # weight nobody would notice however the card labels it.
        if evoke.mana_value() == mana_cost.mana_value():
            raise DslError(
                f"{where}: evoke {model.evoke!r} costs the same as the printed cost -- "
                f"the same cast offered twice, and nobody would take the second"
            )
        # Costlier than printed is dead weight too, but only for evoke *proper*,
        # which buys nothing at all with the price: a Mulldrifter evoked is a
        # Mulldrifter that dies, so paying more for it is a line no player takes.
        # It is not dead weight for **dash**, which is this same mechanism under
        # a different word and where the extra mana buys haste plus the enters
        # trigger for a turn before the body goes back -- Riders of Rohan is
        # printed {3}{R}{W} with dash {4}{R}{W}, and that is a trade players
        # take. `evoke_label` is the card saying which of the two it is, in the
        # action list and on screen, so it is what this guard reads: the default
        # label keeps evoke's discount-only invariant, and a card that has
        # renamed the cost has already said out loud that it is not evoke.
        if evoke.mana_value() > mana_cost.mana_value() and model.evoke_label == "evoked":
            raise DslError(
                f"{where}: evoke {model.evoke!r} is not cheaper than the printed cost"
            )

    if model.rebound and set(model.types) & {"Creature", "Land", "Artifact", "Enchantment"}:
        # Rebound replaces the *graveyard* a spell would go to, so a permanent
        # spell never reaches the rider -- it enters the battlefield instead.
        # A permanent card carrying it would load, look implemented and never
        # rebound once. No printing has it, either: 702.87 is instants and
        # sorceries only.
        raise DslError(
            f"{where}: 'rebound' only means anything on an instant or sorcery -- "
            f"a permanent spell enters the battlefield and never reaches the rider"
        )
    # An additional cost paid at cast time -- casualty, replicate, Deadly
    # Dispute. Unlike kicker it is a full `Cost`, and unlike kicker it need not
    # be read by anything: "sacrifice an artifact" is the whole of Deadly
    # Dispute's cost and no clause reads it back. So there is no half-a-cost
    # guard here; what is guarded is the two modifiers, which mean nothing alone.
    if model.additional_cost is not None and model.additional_cost.mana_reduction:
        # `_cast_variant` folds an additional cost's mana *into* the spell's price
        # with `card.additional_cost.mana.scaled(...)`, so nothing ever prices
        # this node on its own and a reduction here is never read. Refused rather
        # than dropped: it would load clean and cost the player the full amount.
        raise DslError(
            f"{where}.additional_cost: 'mana_reduction' is not read here -- an "
            f"additional cost's mana is folded into the spell's price. Put the "
            f"reduction on the card's 'cost_reduction' instead"
        )
    additional_cost = _compile_cost(model.additional_cost, where) if model.additional_cost else None
    if additional_cost is None and (model.additional_optional or model.additional_repeatable):
        raise DslError(
            f"{where}: 'additional_optional' and 'additional_repeatable' need an "
            f"'additional_cost' to modify"
        )
    if model.additional_repeatable and not model.additional_optional:
        # "Any number of times" includes zero. A mandatory repeatable cost would
        # be offered from one upwards, which is not a printing and would make
        # every replicate card unplayable without the extra mana.
        raise DslError(
            f"{where}: 'additional_repeatable' needs 'additional_optional' -- "
            f"\"any number of times\" includes none"
        )
    if _mentions_condition(model, "additional_paid") and additional_cost is None:
        raise DslError(
            f"{where}: reads 'additional_paid' but has no 'additional_cost', so it "
            f"would always read 0"
        )
    if model.dredge < 0:
        raise DslError(f"{where}: 'dredge' is how many cards are milled, so it cannot be negative")
    if model.morph_counter and model.morph is None:
        raise DslError(f"{where}: 'morph_counter' is megamorph's rider and needs a 'morph' cost")
    if model.morph is not None and "Creature" not in model.types:
        # 702.37a: only a creature card may be cast face down, because what it
        # becomes is a 2/2 *creature*. A non-creature carrying it would be
        # castable face down and unable to turn up into anything.
        raise DslError(f"{where}: 'morph' is only on creature cards")
    if model.splice is not None and model.targets:
        # A spliced card's effects run inside the *host* spell's context, so a
        # target id written here would either be missing or -- worse -- collide
        # with one of the host's and quietly point somewhere else. Refused
        # rather than resolved: the divergence is recorded in
        # rules-coverage.md, and a card that needs its own target is a card this
        # cannot express yet.
        raise DslError(
            f"{where}: a spliced card may not declare its own targets -- its "
            f"effects run in the host spell's context"
        )
    # Disturb needs both halves, and each is silent alone. Without a
    # `graveyard_cost` there is no cast to arrive transformed; without a
    # `back_face` there is nothing to transform *into*, so the card would be
    # cast for its disturb cost and arrive as its front face -- which is
    # flashback wearing the wrong word.
    if model.graveyard_cast_transformed:
        if model.graveyard_cost is None and model.flashback is None:
            raise DslError(
                f"{where}: 'graveyard_cast_transformed' needs a 'graveyard_cost' -- "
                f"there is no cast for it to transform"
            )
        if model.back_face is None:
            raise DslError(
                f"{where}: 'graveyard_cast_transformed' needs a 'back_face' to "
                f"transform into; without one the card arrives as its front face"
            )
    # A second castable face, and the two ways to write half of one. `adventure`
    # with nothing to adventure *from* is a card that exiles itself on
    # resolution and is never seen again -- which is aftermath, silently, under
    # the wrong word. `second_face_zone` alone is a restriction on a cast nobody
    # offers.
    if model.second_face is None:
        if model.adventure:
            raise DslError(
                f"{where}: 'adventure' needs a 'second_face' -- the Adventure is "
                f"the half that gets cast, and there is nothing here to cast"
            )
        if model.second_face_zone != "hand":
            raise DslError(
                f"{where}: 'second_face_zone' needs a 'second_face' -- there is no "
                f"second cast for it to restrict"
            )
    # Fuse is a *third* line on a split card, so it needs the other two: a card
    # with nothing to fuse to is an ordinary spell that says a word, and fusing
    # onto a graveyard-only half would offer from hand a line that half may not
    # be cast from.
    if model.fuse:
        if model.second_face is None:
            raise DslError(
                f"{where}: 'fuse' needs a 'second_face' -- there is only one half here"
            )
        if model.second_face_zone != "hand":
            raise DslError(
                f"{where}: 'fuse' is cast from hand (702.102a), and this card's second "
                f"half may only be cast from the {model.second_face_zone}"
            )
        if model.adventure:
            raise DslError(f"{where}: a card may not have both 'adventure' and 'fuse'")
    # 715.1: an adventurer card is a creature card, and the Adventure is an
    # instant or sorcery. Without the first half the front face would resolve
    # straight back to the graveyard from exile and the "cast it later" half of
    # the keyword would be unreachable; both are checked once the pool is known,
    # where the second face can actually be looked up.
    # Overload is two halves like kicker, and half of it fails the same silent
    # way: a cost nobody reads is a more expensive cast that does the same
    # thing, and an `{"overloaded": true}` clause with no cost can never fire.
    overload = ManaCost.parse(model.overload) if model.overload else None
    reads_overloaded = _mentions_condition(model, "overloaded")
    if reads_overloaded and overload is None:
        raise DslError(f"{where}: reads the 'overloaded' condition but has no 'overload' cost")
    if overload is not None and not reads_overloaded:
        raise DslError(
            f"{where}: has an 'overload' cost that no effect reads via 'overloaded' -- "
            f"the text change is what the extra mana buys"
        )
    if overload is not None and any(not t.optional for t in model.targets):
        # An overloaded spell is cast with **no** targets (702.96a replaces every
        # "target" with "each"), so a required target would make the overload
        # line uncastable -- silently, since the printed line is still offered.
        raise DslError(
            f"{where}: an overload card's targets must all be 'optional' -- an "
            f"overloaded spell is cast with no targets at all"
        )
    if model.buyback and model.kicker is None:
        # Buyback *is* a kicker with a rider. Without the cost there is nothing
        # to pay and the rider never fires, so the card reads "buyback" and
        # goes to the graveyard like anything else.
        raise DslError(f"{where}: 'buyback' needs a 'kicker' cost to attach to")
    if model.emerge_subtype is not None and model.emerge is None:
        # A narrowing with nothing to narrow. The card would look like an
        # offering card and have no alternative cast line at all.
        raise DslError(
            f"{where}: 'emerge_subtype' needs an 'emerge' cost to narrow"
        )
    alternative_cost = None
    alternative_condition = None
    if model.alternative_cost is not None:
        spec = dict(model.alternative_cost)
        unknown = set(spec) - {"mana", "condition"}
        if unknown:
            raise DslError(
                f"{where}.alternative_cost: unsupported keys {sorted(unknown)}"
            )
        if not spec.get("mana"):
            # It *replaces* the printed cost, so without mana the card would be
            # castable for free whenever the condition happened to hold.
            raise DslError(f"{where}.alternative_cost: needs 'mana'")
        alternative_cost = ManaCost.parse(str(spec["mana"]))
        alternative_condition = spec.get("condition")
        if alternative_condition is None:
            # Unconditional is what `evoke` already is. A card spelling it this
            # way would be offered twice at two prices with nothing to choose
            # between them.
            raise DslError(
                f"{where}.alternative_cost: needs a 'condition' -- an "
                f"unconditional alternative cost is 'evoke'"
            )
        validate_condition(alternative_condition, f"{where}.alternative_cost.condition")

    # `flashback` and `graveyard_cost` are one slot under two names -- the
    # keyword that shipped first, and the mechanic it turned out to be. Escape
    # and jump-start are the same capability with a different price and a
    # different destination, and neither should have to say "flashback".
    if model.flashback is not None and model.graveyard_cost is not None:
        raise DslError(
            f"{where}: give 'graveyard_cost' or 'flashback', not both -- they are "
            f"the same field, and a card with two prices from the graveyard has "
            f"no answer to what it costs from there"
        )
    graveyard_spec = model.graveyard_cost or model.flashback
    flashback = Cost.from_spec(graveyard_spec.model_dump()) if graveyard_spec else None
    if flashback is not None:
        if not flashback.mana.text:
            # The mana half *replaces* the printed cost, so without it the card
            # would be castable from the graveyard for free.
            raise DslError(f"{where}: a graveyard cost needs mana")
        if flashback.mana.x_count:
            raise DslError(f"{where}: a graveyard cost with X is not implemented")
        if flashback.mana_reduction is not None:
            # "…costs {X} less to cast **this way**". The one alternative cost
            # modelled as a full `Cost`, so the one that can carry a variant-
            # scoped rider; read by the flashback branch of
            # `legality._cast_variant` and `game._cast` via
            # `costs.variant_reduction`, and by nothing on the hand-cast path.
            _validate_cost_reduction(
                flashback.mana_reduction, f"{where}.graveyard_cost.mana_reduction"
            )
        if model.retrace:
            # Both widen legality to the graveyard and each replaces the other's
            # answer to "what does it cost from there".
            raise DslError(
                f"{where}: a card may not have both a graveyard cost and 'retrace'"
            )
    if graveyard_spec is None and model.graveyard_cast != "exile":
        # A destination with nothing to send there. Silently ignoring it would
        # let a card claim to be an escape card and never be castable at all.
        raise DslError(
            f"{where}: 'graveyard_cast' needs a 'graveyard_cost' to describe"
        )
    # Clash is two halves the same way kicker is, and half of it fails just as
    # silently. Every printed clash card reads "Clash with an opponent. If you
    # win, …", so a `clash` nothing reads is a spell that reveals two cards and
    # does nothing, and a `clash_won` binding with no clash behind it is a
    # clause that reads 0 and can never fire. Both load cleanly.
    clashes = _mentions_pair(model, "op", "clash")
    reads_clash = _mentions_pair(model, "binding", "clash_won")
    if clashes and not reads_clash:
        raise DslError(
            f"{where}: has a 'clash' that no effect reads via "
            f"{{'binding': 'clash_won'}} -- a clash nobody wins is not a card"
        )
    if reads_clash and not clashes:
        raise DslError(
            f"{where}: reads the 'clash_won' binding but never clashes, so it "
            f"would always read 0"
        )

    reads_from_graveyard = _mentions_condition(model, "cast_from_graveyard")
    if reads_from_graveyard and flashback is None:
        raise DslError(
            f"{where}: reads the 'cast_from_graveyard' condition but has no "
            f"'graveyard_cost', so it could never be true"
        )

    colors = (
        frozenset(model.colors)
        if model.colors is not None
        else frozenset(c.value for c in mana_cost.colors)
    )
    for c in colors:
        if c not in KNOWN_COLORS:
            raise DslError(f"{where}: unknown color {c!r}")

    identity = (
        frozenset(model.color_identity)
        if model.color_identity is not None
        else _derive_color_identity(colors, mana_cost, abilities)
    )

    supertypes = frozenset(model.supertypes)
    types = frozenset(model.types)
    subtypes = frozenset(model.subtypes)

    return CardDef(
        id=model.id,
        name=model.name,
        oracle_text=model.oracle_text,
        mana_cost=mana_cost,
        supertypes=supertypes,
        types=types,
        subtypes=subtypes,
        power=model.power,
        toughness=model.toughness,
        loyalty=model.loyalty,
        keywords=frozenset(model.keywords),
        colors=colors,
        color_identity=identity,
        targets=targets,
        spell_effects=tuple(model.spell_effects),
        replacements=_replacements_with_loyalty(model),
        abilities=abilities,
        grantable_abilities=grantable,
        type_line=build_type_line(supertypes, types, subtypes),
        is_token=model.is_token,
        back_face=model.back_face,
        second_face=model.second_face,
        second_face_zone=model.second_face_zone,
        adventure=model.adventure,
        fuse=model.fuse,
        uncounterable=model.uncounterable,
        split_second=model.split_second,
        buyback=model.buyback,
        rebound=model.rebound,
        overload=overload,
        graveyard_cast_transformed=model.graveyard_cast_transformed,
        dredge=model.dredge,
        madness=ManaCost.parse(model.madness) if model.madness else None,
        miracle=ManaCost.parse(model.miracle) if model.miracle else None,
        foretell=ManaCost.parse(model.foretell) if model.foretell else None,
        epic=model.epic,
        morph=ManaCost.parse(model.morph) if model.morph else None,
        morph_counter=model.morph_counter,
        splice=ManaCost.parse(model.splice) if model.splice else None,
        splice_onto=model.splice_onto,
        additional_cost=additional_cost,
        additional_optional=model.additional_optional,
        additional_repeatable=model.additional_repeatable,
        kicker_label=model.kicker_label,
        kicker=kicker,
        evoke=evoke,
        bestow=bestow,
        mutate=mutate,
        melds_with=model.melds_with,
        melds_into=model.melds_into,
        emerge=emerge,
        cost_reduction=dict(model.cost_reduction) if model.cost_reduction else None,
        retrace=model.retrace,
        flashback=flashback,
        evoke_label=model.evoke_label,
        pay_generic_with=model.pay_generic_with,
        emerge_subtype=model.emerge_subtype,
        alternative_cost=alternative_cost,
        alternative_condition=alternative_condition,
        graveyard_cast_exiles=model.graveyard_cast == "exile",
        ascend=model.ascend,
        suspend=suspend,
    )


def _mentions_kicked(model: CardModel) -> bool:
    """Does anything on this card read ``{"kicked": ...}``?"""
    return _mentions_condition(model, "kicked")


#: Ops that take an object out of the zone an ability was activated from.
#: Unearth's `put_onto_battlefield`, and the three other destinations a card
#: could plausibly be sent to by its own ability.
SOURCE_MOVING_OPS = frozenset(
    {"put_onto_battlefield", "exile", "return_to_hand", "put_on_top"}
)


def _effects_move_source(effects: Any) -> bool:
    """Does this ability *unconditionally* move its own source out of its zone?

    The third way to satisfy the outside-the-battlefield guard, after cycling's
    self-discard and embalm's self-exile. Unearth pays neither: its cost is
    plain mana and the card leaves because the effect returns it to the
    battlefield.

    Only the **top level** counts. An effect nested inside an `if` or a `may`
    might not run, and an ability whose only exit is a branch the player can
    decline is activatable again from the same zone -- which is the shape the
    guard exists to refuse. `self_only` is likewise required: an ability that
    moves *some other* card out of a graveyard has not moved itself.
    """
    for effect in effects or ():
        if not isinstance(effect, Mapping):
            continue
        if effect.get("op") not in SOURCE_MOVING_OPS:
            continue
        objects = effect.get("objects")
        if isinstance(objects, Mapping) and objects.get("self_only"):
            return True
    return False


def _mentions_condition(model: CardModel, key: str) -> bool:
    """Does anything on this card read the ``key`` condition?"""
    return _mentions(model, lambda node: key in node)


def _mentions_pair(model: CardModel, key: str, value: str) -> bool:
    """Does anything on this card carry ``{key: value}``?

    The ``key in node`` test `_mentions_condition` uses is too coarse for
    ``{"op": "clash"}`` and ``{"binding": "clash_won"}`` — every effect has an
    ``op`` and dozens have a ``binding``, so the key alone matches everything.
    """
    return _mentions(model, lambda node: node.get(key) == value)


def _mentions(model: CardModel, predicate: Any) -> bool:
    def walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return bool(predicate(node)) or any(walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(walk(v) for v in node)
        return False

    if walk(model.spell_effects):
        return True
    return any(
        walk(a.effects) or walk(a.trigger.condition if a.trigger else None)
        for a in model.abilities
    )


def _compile_targets(models, where: str) -> tuple[TargetSpec, ...]:
    """Compile a card's or ability's target list, with the one ordering rule.

    At most one spec may be ``count: "any"``, and it must come last.
    `targeting.filter_legal` splits the stored refs spec by spec, and a
    variable-size spec in the middle leaves no way to say where its refs end and
    the next spec's begin -- so the spell would fizzle or keep the wrong targets
    depending on how many the caster chose, which is a bug no board would show.
    """
    specs = tuple(_compile_target(t, where) for t in models)
    for spec in specs:
        # A per-player cap is a constraint on how many of a *variable-size*
        # choice may share a controller. On a fixed-size spec it either changes
        # nothing or makes the spec unsatisfiable, and both are silent.
        if spec.one_per_player and spec.count != "any":
            raise DslError(
                f"{where}: 'one_per_player' needs 'count': 'any' -- "
                f"it caps a variable-size choice, and a fixed one has no room to cap"
            )
    variable = [i for i, spec in enumerate(specs) if spec.count == "any"]
    if len(variable) > 1:
        raise DslError(
            f"{where}: only one target may be 'any number of' -- "
            f"two variable-size specs cannot be told apart once chosen"
        )
    if variable and variable[0] != len(specs) - 1:
        raise DslError(
            f"{where}: an 'any number of' target must come last, "
            f"or the targets after it cannot be identified"
        )
    return specs


def _compile_target(model: TargetModel, where: str) -> TargetSpec:
    validate_selector(model.selector, f"{where}.target[{model.id}]")
    return TargetSpec(
        id=model.id,
        kind=model.kind,
        selector=dict(model.selector),
        count=model.count,
        one_per_player=model.one_per_player,
        optional=model.optional,
    )


def _compile_ability(model: AbilityModel, index: int, card_where: str) -> Ability:
    where = f"{card_where}.abilities[{index}]"
    kind = AbilityKind(model.kind)
    if (model.activate_steps or model.once_each_turn) and kind is not AbilityKind.ACTIVATED:
        # Both are activation restrictions. On a trigger or a static they would
        # load and be ignored, leaving a card that reads "only once each turn"
        # and fires every time. Checked before the static branch returns.
        raise DslError(
            f"{where}: 'activate_steps' and 'once_each_turn' restrict *activating*, "
            f"so they only mean anything on an activated ability"
        )

    if kind is AbilityKind.STATIC:
        return _compile_static(model, index, where)

    targets = _compile_targets(model.targets, where)
    target_ids = {t.id for t in targets}
    for i, effect in enumerate(model.effects):
        _validate_effect(effect, f"{where}.effects[{i}]", target_ids)

    cost = _compile_cost(model.cost, where) if model.cost else None
    trigger = None
    active_zones: tuple[Zone, ...] = (Zone.BATTLEFIELD,)

    if kind is AbilityKind.ACTIVATED:
        if cost is None:
            raise DslError(f"{where}: activated abilities need a cost")
        if model.condition is not None:
            # "Activate only if you control five or more Vampires." The full
            # condition language, not the static one: nothing is being computed
            # here that another condition could come to depend on, so the
            # narrowing that protects the characteristics pipeline buys nothing.
            validate_condition(model.condition, f"{where}.condition")
        active_zones = tuple(Zone(z) for z in model.active_zones)
        # Cycling is an ability you activate *from your hand*, so the zone list
        # has to be read here as well as on the triggered branch -- it was
        # pinned to the battlefield, which silently dropped the schema's own
        # "hand" value.
        #
        # Anywhere but the battlefield, the cost must also *remove the source
        # from that zone*, or the ability is an infinite engine: a card sitting
        # in hand whose ability only costs mana could be activated again and
        # again without ever leaving. Cycling pays for itself by discarding
        # itself, which is exactly the property that makes it safe and is why
        # the two arrived together.
        if model.is_cycling and not cost.discard_self:
            # Rule 702.29: cycling *is* "Discard this card:". Without the
            # discard the `cycle` event would fire for an ability that never
            # cycled anything, and Krosan Tusker would fetch a land every time.
            raise DslError(
                f"{where}: 'is_cycling' needs a cost that discards this card "
                f"(got {cost.describe()!r})"
            )
        # Two costs remove the source from a non-battlefield zone: cycling
        # discards this card from hand, embalm exiles it from the graveyard.
        # Unearth is the third shape and pays neither -- its *effect* is what
        # takes the card out ("return this card from your graveyard to the
        # battlefield"), so the property the guard is really after is that the
        # source cannot still be sitting there afterwards, however it left.
        # Forecast is the fourth satisfier and the only one that does not move
        # the card: "activate only during your upkeep, and only once each turn"
        # is not an infinite engine because it may be activated once. Both
        # halves are required -- `once_each_turn` alone would still be a card in
        # hand with a free ability every turn for the whole game, which is what
        # forecast's upkeep window is there to price.
        gated_once = model.once_each_turn and bool(model.activate_steps)
        removes_source = (
            cost.discard_self
            or cost.exile_from_graveyard is not None
            or _effects_move_source(model.effects)
            or gated_once
        )
        if set(active_zones) - {Zone.BATTLEFIELD} and not removes_source:
            raise DslError(
                f"{where}: an activated ability outside the battlefield needs a cost "
                f"or an unconditional effect that removes its source from that zone "
                f"(got {cost.describe()!r}); "
                f"otherwise it can be activated repeatedly without ever leaving"
            )
    else:
        if model.trigger is None:
            raise DslError(f"{where}: triggered abilities need a trigger")
        if model.trigger.event not in TRIGGER_EVENTS:
            raise DslError(
                f"{where}: unknown trigger event {model.trigger.event!r} "
                f"(implemented: {sorted(TRIGGER_EVENTS)})"
            )
        validate_selector(model.trigger.filter, f"{where}.trigger.filter")
        validate_condition(model.trigger.condition, f"{where}.trigger.condition")
        if model.trigger.defending is not None and model.trigger.event != "attacks":
            # Silently ignoring it would produce a card that looks like it reads
            # "attacks you" and fires on everything.
            raise DslError(
                f"{where}: 'defending' only means anything on an 'attacks' trigger, "
                f"not on {model.trigger.event!r}"
            )
        # `self_enters` and `permanent_enters` are the same engine event, and
        # what separates them is `source: "self"`. Omitting it on `self_enters`
        # therefore produced a card that fired on *every* permanent entering --
        # silently, and only visibly wrong once a second permanent showed up.
        # The name can only mean one thing, so the loader makes it mean it.
        source = model.trigger.source
        if model.trigger.event == "self_enters":
            source = "self"

        if model.trigger.not_cause is not None and model.trigger.event not in (
            "self_enters",
            "permanent_enters",
        ):
            # Only zone changes carry a cause. Accepting it elsewhere would look
            # like a guard and be one that never fires.
            raise DslError(
                f"{where}: 'not_cause' only means anything on an enters trigger, "
                f"not on {model.trigger.event!r}"
            )

        if model.trigger.counter is not None and model.trigger.event != "counter_placed":
            # Same reasoning as `not_cause` above: only `counter_placed` carries
            # a counter kind, so accepting it elsewhere would look like a filter
            # and be one that never applies.
            raise DslError(
                f"{where}: 'counter' only means anything on a counter_placed trigger, "
                f"not on {model.trigger.event!r}"
            )
        if model.trigger.counter is not None:
            # "Whenever a vigilance counter is put on this creature." The filter
            # is compared to the kind the primitive was handed, so a near-miss
            # spelling matches nothing and the trigger never fires.
            _check_counter_kind(model.trigger.counter, f"{where}.trigger.counter")

        if model.trigger.mana_ability is not None and model.trigger.event != "ability_activated":
            # Same reasoning as `counter` and `defending` above: only
            # `ability_activated` carries the flag, so accepting it elsewhere
            # would look like the "if it isn't a mana ability" clause and be a
            # restriction that never applies.
            raise DslError(
                f"{where}: 'mana_ability' only means anything on an "
                f"ability_activated trigger, not on {model.trigger.event!r}"
            )

        trigger = TriggerSpec(
            event=model.trigger.event,
            controller=model.trigger.controller,
            source=source,
            filter=dict(model.trigger.filter) if model.trigger.filter else None,
            condition=dict(model.trigger.condition) if model.trigger.condition else None,
            defending=model.trigger.defending,
            not_cause=model.trigger.not_cause,
            counter=model.trigger.counter,
            mana_ability=model.trigger.mana_ability,
            max_per_turn=model.trigger.max_per_turn,
        )
        if trigger.max_per_turn is not None and trigger.max_per_turn < 1:
            raise DslError(
                f"{where}: 'max_per_turn' is a cap of at least 1; "
                f"an ability that may never trigger is not a card"
            )
        active_zones = tuple(Zone(z) for z in model.active_zones)

    mana_options: tuple[tuple[int, ...], ...] = ()
    mana_amount: Mapping[str, Any] | None = None
    mana_rider: tuple[Mapping[str, Any], ...] = ()
    mana_reflects: Mapping[str, Any] | None = None
    mana_identity = False
    if model.is_mana_ability:
        if kind is not AbilityKind.ACTIVATED:
            raise DslError(f"{where}: only activated abilities can be mana abilities")
        if targets:
            raise DslError(f"{where}: a mana ability cannot have targets")
        mana_effects, mana_rider = _split_mana_rider(model.effects, where)
        # "Add one mana of any color that a land an opponent controls could
        # produce." The colours are a question about the board, so the card
        # names the permanents to ask rather than the colours to make.
        reflect = next(
            (
                e.get("reflecting")
                for e in mana_effects
                if isinstance(e, Mapping) and e.get("reflecting")
            ),
            None,
        )
        if reflect is not None:
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a reflecting mana ability is a single 'add_mana' -- "
                    f"there is no second thing for the board's colours to join"
                )
            validate_selector(reflect, f"{where}.reflecting")
            mana_reflects = dict(reflect)
            # The static superset. Load time cannot know which colours the board
            # will offer, and an empty tuple here would make `solver_taps` and
            # `offerable_mana_ability` both decide this is not a mana source at
            # all -- so the ability would never be offered or tapped, whatever
            # the opponent's lands did.
            mana_options = _ANY_COLOR_OPTIONS
            mana_amount = None
        elif any(
            isinstance(e, Mapping) and e.get("in_commander_identity") for e in mana_effects
        ):
            # "Add one mana of any color in your commander's color identity."
            # Command Tower, Arcane Signet, Path of Ancestry. The same shape as
            # `reflecting` and for the same reason -- the colours are a question
            # about the game, not about the card -- but the question is asked of
            # the command zone rather than of the board.
            if len(mana_effects) != 1:
                raise DslError(
                    f"{where}: a commander-identity mana ability is a single 'add_mana' -- "
                    f"there is no second thing for the identity's colours to join"
                )
            mana_identity = True
            # The static superset, for the same reason `reflecting` needs one:
            # an empty tuple at load time makes `solver_taps` and
            # `offerable_mana_ability` decide this is not a mana source, so the
            # ability would never be offered whatever the commander's colours.
            mana_options = _ANY_COLOR_OPTIONS
            mana_amount = None
        else:
            mana_options = _mana_options(mana_effects, where)
            mana_amount = _mana_amount(mana_effects, where)
    mana_restriction: ManaRestriction | None = None
    if model.mana_restriction is not None:
        if not model.is_mana_ability:
            raise DslError(f"{where}: 'mana_restriction' needs 'is_mana_ability'")
        mana_restriction = _mana_restriction(model.mana_restriction, where)

    return Ability(
        kind=kind,
        index=index,
        text=model.text,
        cost=cost,
        is_mana_ability=model.is_mana_ability,
        mana_options=mana_options,
        mana_amount=mana_amount,
        mana_rider=mana_rider,
        mana_reflects=mana_reflects,
        mana_identity=mana_identity,
        mana_restriction=mana_restriction,
        # 606.3: a loyalty ability may be activated "any time they could cast a
        # sorcery". That is the rule speaking, not the card, so it is applied
        # here rather than left to an author to remember -- one omitted flag and
        # the planeswalker ticks up at instant speed on somebody else's turn.
        sorcery_speed_only=model.sorcery_speed_only or (cost is not None
        and cost.loyalty is not None),
        activation_condition=(
            dict(model.condition) if kind is AbilityKind.ACTIVATED and model.condition else None
        ),
        is_cycling=model.is_cycling,
        activate_steps=tuple(model.activate_steps),
        once_each_turn=model.once_each_turn,
        trigger=trigger,
        active_zones=active_zones,
        targets=targets,
        effects=tuple(model.effects),
        static=None,
    )


def _compile_static(model: AbilityModel, index: int, where: str) -> Ability:
    if model.effect is None:
        raise DslError(f"{where}: static abilities need an 'effect' name")
    if model.effect == "prevent_damage" and model.amount is None:
        # Absorb 0 prevents nothing. A static that reads as damage prevention
        # and prevents none of it is the failure this whole pass exists to
        # refuse -- it would load, appear in the card's text, and never fire.
        raise DslError(f"{where}: 'prevent_damage' needs an 'amount' -- absorb N")
    if model.effect not in STATIC_EFFECTS:
        raise DslError(
            f"{where}: unknown static effect {model.effect!r} (implemented: {sorted(STATIC_EFFECTS)})"
        )
    if model.effects:
        raise DslError(f"{where}: static abilities cannot have 'effects'")

    if model.affects is not None:
        unknown = set(model.affects) - STATIC_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}: static filters may only read printed characteristics; "
                f"unsupported keys {sorted(unknown)}"
            )
    if model.effect == "block_restriction":
        # Exactly one of the two forms, because they are evaluated at different
        # moments and a static carrying neither is an evasion ability that
        # evades nothing -- which loads clean and shows nothing on the board.
        if (model.blockers is None) == (not model.require_all):
            raise DslError(
                f"{where}: block_restriction needs exactly one of 'blockers' "
                f"(a filter on the would-be blocker) or 'require_all'"
            )
        if model.blockers is not None:
            unknown = set(model.blockers) - STATIC_FILTER_KEYS
            if unknown:
                raise DslError(
                    f"{where}: block_restriction 'blockers' may only read printed "
                    f"characteristics; unsupported keys {sorted(unknown)}"
                )
    elif model.blockers is not None or model.require_all:
        raise DslError(
            f"{where}: 'blockers'/'require_all' only mean anything on a "
            f"block_restriction static, not on {model.effect!r}"
        )
    if model.effect == "spell_cost_reduction":
        # `affects_spells`, not `affects`: this filter is matched against a card
        # in hand while legality prices it, so it may only read the printed
        # face. A static that reduced nothing would load clean and show
        # nothing, so both halves are required.
        if model.affects is not None:
            raise DslError(
                f"{where}: spell_cost_reduction filters spells with "
                f"'affects_spells', not 'affects' (which picks out permanents)"
            )
        if model.affects_spells is None:
            raise DslError(f"{where}: spell_cost_reduction needs 'affects_spells'")
        unknown = set(model.affects_spells) - SPELL_FILTER_KEYS
        if unknown:
            raise DslError(
                f"{where}.affects_spells: a spell has a printed face and a caster "
                f"and no board state; unsupported keys {sorted(unknown)}"
            )
        if model.amount is None:
            raise DslError(
                f"{where}: spell_cost_reduction needs an 'amount' -- a reduction "
                f"of nothing is not a card"
            )
        _validate_static_value(model.amount, f"{where}.amount")
    elif model.affects_spells is not None:
        raise DslError(
            f"{where}: 'affects_spells' only means anything on a "
            f"spell_cost_reduction static, not on {model.effect!r}"
        )
    if model.effect in (
        "extra_land_drops",
        "no_hand_limit",
        "play_lands_from_graveyard",
        "play_lands_from_library_top",
        "reveal_library_top",
        "double_land_triggers",
        "double_land_mana",
        "freeze_opponent_lands",
    ):
        if model.affects_player is None:
            raise DslError(f"{where}: {model.effect} needs 'affects_player'")
    elif model.effect == "spell_cost_reduction":
        # Picks out *spells*, through `affects_spells`, checked above. There are
        # no permanents for `affects` to name.
        pass
    elif model.affects is None:
        raise DslError(f"{where}: static effect {model.effect!r} needs 'affects'")

    if model.effect == "ward":
        # Ward with no cost is ward {0}: a keyword that prints on the card, shows
        # in the log, taxes nothing and can never be declined. The same refusal
        # `prevent_damage` makes about absorb 0.
        if model.cost is None:
            raise DslError(
                f"{where}: ward needs a 'cost' -- ward that taxes nothing is not a card"
            )
        # Through the same validator an activated ability's cost goes through, so
        # ward inherits every selector check rather than growing its own. The
        # `Cost` is discarded: what the static stores is the raw spec, because
        # `op_may` charges it from a mapping and building it twice is two places
        # for the price to drift.
        _compile_cost(model.cost, where)
    elif model.cost is not None:
        raise DslError(
            f"{where}: a static ability has no cost to pay; 'cost' means "
            f"something only on 'ward' (and on activated abilities)"
        )

    for field_name in ("power", "toughness", "amount"):
        value = getattr(model, field_name)
        if value is not None:
            _validate_static_value(value, f"{where}.{field_name}")

    for k in model.keywords:
        if k not in KNOWN_KEYWORDS:
            raise DslError(f"{where}: unknown keyword {k!r}")

    if model.effect == "set_types" and not model.types:
        raise DslError(f"{where}: set_types needs the types it sets")

    qualities = [*model.from_types, *model.from_subtypes, *model.from_colors]
    if model.effect == "protection":
        # A protection static that names nothing protects from nothing -- a card
        # that looks implemented and is not, which is the one failure this pass
        # exists to stop.
        if not qualities:
            raise DslError(f"{where}: protection needs from_types/from_subtypes/from_colors")
        for t in model.from_types:
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown type {t!r} in from_types")
        for c in model.from_colors:
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown color {c!r} in from_colors")
    elif qualities:
        raise DslError(f"{where}: from_types/from_subtypes/from_colors need effect 'protection'")

    _validate_static_condition(model.condition, f"{where}.condition")

    static: dict[str, Any] = {"effect": model.effect}
    if model.condition is not None:
        static["condition"] = dict(model.condition)
    if model.affects is not None:
        static["affects"] = dict(model.affects)
    if model.affects_spells is not None:
        static["affects_spells"] = dict(model.affects_spells)
    if model.affects_player is not None:
        static["affects_player"] = model.affects_player
    for field_name in ("power", "toughness", "amount"):
        value = getattr(model, field_name)
        if value is not None:
            static[field_name] = value
    if model.keywords:
        static["keywords"] = list(model.keywords)
    if model.subtypes:
        static["subtypes"] = list(model.subtypes)
    if model.types:
        static["types"] = list(model.types)
    for field_name in ("from_types", "from_subtypes", "from_colors"):
        value = getattr(model, field_name)
        if value:
            static[field_name] = list(value)
    if model.blockers is not None:
        static["blockers"] = dict(model.blockers)
    if model.require_all:
        static["require_all"] = True
    if model.effect == "ward":
        # Pruned of the fields the model dump carries unset, because this
        # mapping is also what `carddef.ward_ability` keys its intern table on:
        # two cards writing ward {1} must land on one ability, not two that only
        # differ by a `tap: false` nobody wrote.
        static["cost"] = prune_cost(model.cost.model_dump())

    return Ability(kind=AbilityKind.STATIC, index=index, text=model.text, static=static)


#: Ways a card may say how much less it costs.  ``count`` is "{1} less for each
#: X"; ``total_power`` is Ghalta's "the total power of creatures you control";
#: ``amount`` is a flat "{3} less", which only means anything gated on a
#: ``condition`` -- an ungated flat reduction is a smaller printed cost;
#: ``greatest_mana_value`` is Visions of Glory's "the greatest mana value of a
#: commander you own", a **maximum** rather than a sum and so its own key --
#: written as a `count` or a `total_power` it would add two partners' mana
#: values together and quietly hand out a bigger discount than the card says.
COST_REDUCTION_KEYS = frozenset({"count", "total_power", "amount", "greatest_mana_value"})

#: Zones a cost reduction's filter may count.  Mirrors `costs.REDUCTION_ZONES`,
#: which is what actually walks them; anything else would load and match nothing.
#: `total_power` is battlefield-only whatever this says -- see below.
COST_REDUCTION_ZONES = frozenset({"battlefield", "command"})

#: Extra filter keys a cost reduction accepts on top of `STATIC_FILTER_KEYS`.
#: ``owner`` is not a static filter key and should not become one -- a static
#: applies to permanents, where control is the question. A reduction reading the
#: command zone is the one place the printed word is "own": "a commander you own
#: on the battlefield or in the command zone" still counts the commander an
#: opponent stole from you.
COST_REDUCTION_FILTER_KEYS = frozenset({"zone", "owner"})

#: Condition heads a *cost* reduction may use.
#:
#: A reduction is evaluated while deciding what is castable or activatable --
#: before the spell is on the stack and before any cost is paid -- so the four
#: cast-variant flags (`kicked`, `evoked`, `overloaded`, `cast_from_graveyard`)
#: are not merely useless here, they read ``False`` every time and would give a
#: card a discount clause that can never fire.  Refused rather than allowed to
#: load, because nothing on a board would ever say so.
COST_CONDITION_HEADS = frozenset(
    {
        "all",
        "any",
        "not",
        "cmp",
        "left",
        "right",
        "exists",
        "is_your_turn",
        "has_city_s_blessing",
        "is_monarch",
        "no_monarch",
        "combat_damage_by",
        # Both read the reduction's own source, which is a real object at
        # pricing time: the permanent whose ability is being activated, or the
        # card in the graveyard being cast.
        "zone_is",
        "has_flag",
    }
)


def _validate_cost_condition(cond: Any, where: str) -> None:
    """A cost reduction's condition: the shared condition DSL, narrowed."""
    validate_condition(cond, where)
    if not isinstance(cond, Mapping):
        return
    unusable = set(cond) - COST_CONDITION_HEADS
    if unusable:
        raise DslError(
            f"{where}: {sorted(unusable)} cannot be answered while a cost is being "
            f"priced -- nothing is on the stack yet (usable: "
            f"{sorted(COST_CONDITION_HEADS)})"
        )
    for key in ("all", "any"):
        for i, sub in enumerate(cond.get(key) or ()):
            _validate_cost_condition(sub, f"{where}.{key}[{i}]")
    if "not" in cond:
        _validate_cost_condition(cond["not"], f"{where}.not")


def _validate_reduction_zones(filt: Mapping[str, Any], key: str, where: str) -> None:
    """Which zones one reduction filter is allowed to count.

    A string or a list of strings, drawn from `COST_REDUCTION_ZONES`: the
    battlefield and the command zone are the two `costs._reduction_matches`
    walks, and a filter naming any other would load clean and match nothing --
    the silent failure this validator exists for.

    ``total_power`` is battlefield-only however the list is written. Power is a
    characteristic of a permanent; a card in the command zone has none, and
    summing the printed face there would be answering a question the pipeline
    was never asked.
    """
    if "zone" not in filt:
        return
    raw = filt["zone"]
    zones = [raw] if isinstance(raw, str) else list(raw)
    if not zones:
        raise DslError(f"{where}.zone: names no zone at all")
    bad = [z for z in zones if z not in COST_REDUCTION_ZONES]
    if bad:
        raise DslError(
            f"{where}.zone: a cost reduction counts "
            f"{sorted(COST_REDUCTION_ZONES)} only, got {bad!r}"
        )
    if key == "total_power" and set(zones) != {"battlefield"}:
        raise DslError(
            f"{where}.zone: 'total_power' sums a characteristic only permanents "
            f"have, so it counts the battlefield only, got {raw!r}"
        )


def _validate_cost_reduction(spec: Any, where: str) -> None:
    """One validator for every "costs {N} less", wherever it is written.

    A card's own `cost_reduction`, an activated ability's
    `cost.mana_reduction` and a graveyard cast's `mana_reduction` are three
    readers of one language -- `costs.reduction_amount` -- so they get one
    validator, or they drift about what "for each" and "if" mean.
    """
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must name exactly one of {sorted(COST_REDUCTION_KEYS)}")
    arithmetic = set(spec) & COST_REDUCTION_KEYS
    unknown = set(spec) - COST_REDUCTION_KEYS - {"condition"}
    if unknown:
        raise DslError(
            f"{where}: unknown reduction keys {sorted(unknown)} "
            f"(implemented: {sorted(COST_REDUCTION_KEYS)} plus an optional 'condition')"
        )
    if len(arithmetic) != 1:
        # Two would be paid at whichever the code read first, which is not
        # something a printed line ever says; none is a condition with nothing
        # to reduce.
        raise DslError(f"{where}: must name exactly one of {sorted(COST_REDUCTION_KEYS)}")
    key = next(iter(arithmetic))
    if key == "amount":
        amount = spec["amount"]
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise DslError(
                f"{where}.amount: a flat reduction is a positive integer, got {amount!r}"
            )
        if "condition" not in spec:
            # "Costs {3} less" with nothing to gate it is a card with a smaller
            # printed cost, written the long way -- and it would load clean.
            raise DslError(
                f"{where}: a flat 'amount' needs a 'condition' -- an unconditional "
                f"flat reduction is just a cheaper printed cost"
            )
    else:
        filt = spec[key]
        if not isinstance(filt, Mapping):
            raise DslError(f"{where}.{key}: needs a filter")
        # Same restriction as a static filter, for the same reason: this is
        # evaluated while deciding what is castable, before anything is on the
        # stack, so it may only read printed characteristics of the board.
        unknown = set(filt) - STATIC_FILTER_KEYS - COST_REDUCTION_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}.{key}: unsupported filter keys {sorted(unknown)}")
        if (owner := filt.get("owner")) is not None and owner not in ("you", "opponent"):
            raise DslError(
                f"{where}.{key}.owner: must be 'you' or 'opponent', got {owner!r}"
            )
        _validate_reduction_zones(filt, key, f"{where}.{key}")
    if "condition" in spec:
        _validate_cost_condition(spec["condition"], f"{where}.condition")


#: Comparisons a static's "as long as..." clause may use.
STATIC_CONDITION_OPS = frozenset({">=", "<=", ">", "<", "=", "==", "!="})

#: The forms a static's condition may take, one per node.
STATIC_CONDITION_HEADS = (
    "counters", "all", "any", "not", "exists", "is_your_turn",
    "has_city_s_blessing", "cmp",
    # "Attached permanents with reconfigure aren't creatures" (702.151d).
    # `attached_to` is a field the `attach` primitive writes, so it is a
    # pipeline input like a counter and no layer can change it. Distinct from
    # the `attached` *filter* key, which points the other way -- at the
    # permanent this one is attached to.
    "is_attached",
    # "As long as the top card of your library is black". A pipeline *input*
    # for the same reason a zone count is -- nothing in the characteristics
    # pipeline can change what is on top of a library -- but a strictly
    # sharper question than `exists` over the library, which asks whether any
    # black card is anywhere in ninety-nine and is nearly always true.
    "top_of_library",
)

#: Zones a static's *counting* filter may name.  The stack is absent: a static
#: is read while the pipeline computes characteristics, including for objects
#: that are themselves resolving, and "how many spells are on the stack" would
#: change under a card mid-resolution.
STATIC_COUNT_ZONES = frozenset({"battlefield", "graveyard", "hand", "exile", "library", "command"})

#: Keys a static's *counting* filter may use -- the selection keys, plus the
#: zone.  ``affects`` and ``blockers`` deliberately do not get ``zone``: they
#: pick out permanents the static applies to, and there are no permanents
#: outside the battlefield, so a zone there would load and match nothing.
#: ``name`` is here and deliberately *not* in ``STATIC_FILTER_KEYS``. "…unless
#: you control a creature named Advocate of the Beast" is a question the
#: condition asks about the board; "each creature named X gets +1/+1" is not a
#: card, so `affects` has no use for it and allowing it there would only invite
#: one.
STATIC_COUNT_FILTER_KEYS = STATIC_FILTER_KEYS | {"zone", "name"}

#: ...and once it names a zone other than the battlefield, only these.  A card
#: in a graveyard has a printed face and an owner; it is not tapped, attacking,
#: attached to anything or a token, so those keys are refused here rather than
#: loading and silently matching nothing.
STATIC_ZONE_FILTER_KEYS = frozenset(
    {
        "zone",
        "controller",
        # A card in a graveyard has no board state, but it does have a name.
        "name",
        "types",
        "not_types",
        "subtypes",
        "supertypes",
        "colors",
        "keywords",
        "not_keywords",
    }
)


def _validate_static_count_filter(spec: Any, where: str) -> None:
    """A filter in a *counting* position -- ``{"count": ...}`` or ``exists``."""
    if not isinstance(spec, Mapping):
        raise DslError(f"{where}: must be an object")
    zone = str(spec.get("zone", "battlefield"))
    if zone not in STATIC_COUNT_ZONES:
        raise DslError(f"{where}.zone: unknown zone {zone!r} (countable: {sorted(STATIC_COUNT_ZONES)})")
    if zone == "battlefield":
        unknown = set(spec) - STATIC_COUNT_FILTER_KEYS
        if unknown:
            raise DslError(f"{where}: unsupported filter keys {sorted(unknown)}")
        return
    unknown = set(spec) - STATIC_ZONE_FILTER_KEYS
    if unknown:
        raise DslError(
            f"{where}: a card in {zone} has a printed face and an owner and nothing else; "
            f"unsupported keys {sorted(unknown)}"
        )
    controller = spec.get("controller", "you")
    if controller not in ("you", "opponent", "any"):
        raise DslError(f"{where}.controller: must be 'you', 'opponent' or 'any', got {controller!r}")


def _validate_static_condition(condition: Any, where: str) -> None:
    """A static may ask about pipeline *inputs* only.

    Much smaller than the ``if``-effect condition language, and for the same
    reason ``affects`` filters are: anything that reads a *derived*
    characteristic would let one static depend on another's output, and the
    fixed-order pipeline has no way to resolve that.  Counters on the source,
    printed characteristics of the board, the contents of a zone and whose turn
    it is are all inputs, so all four are safe; every one of them is settled
    before the first layer applies.
    """
    if condition is None or isinstance(condition, bool):
        return
    if not isinstance(condition, Mapping):
        raise DslError(f"{where}: a static condition must be an object")
    heads = [k for k in STATIC_CONDITION_HEADS if k in condition]
    if len(heads) != 1:
        raise DslError(
            f"{where}: a static condition names exactly one of "
            f"{list(STATIC_CONDITION_HEADS)}, got {sorted(condition)}"
        )
    head = heads[0]
    extra = set(condition) - {head} - ({"left", "right"} if head == "cmp" else set())
    if extra:
        raise DslError(f"{where}: unsupported keys {sorted(extra)} beside {head!r}")

    if head == "counters":
        spec = condition["counters"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.counters: must be an object")
        unknown = set(spec) - {"counter", "amount", "op"}
        if unknown:
            raise DslError(f"{where}.counters: unsupported keys {sorted(unknown)}")
        op = str(spec.get("op", ">="))
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.counters: unknown comparison {op!r}")
        if "counter" in spec:
            # "As long as it has an indestructible counter on it…" -- read off
            # the source's own `counters` dict by exact key, so a near-miss
            # spelling switches the static off for ever.
            _check_counter_kind(spec["counter"], f"{where}.counters.counter")
    elif head in ("all", "any"):
        if not isinstance(condition[head], list) or not condition[head]:
            raise DslError(f"{where}.{head}: takes a non-empty list of conditions")
        for i, sub in enumerate(condition[head]):
            _validate_static_condition(sub, f"{where}.{head}[{i}]")
    elif head == "not":
        _validate_static_condition(condition["not"], f"{where}.not")
    elif head == "exists":
        _validate_static_count_filter(condition["exists"], f"{where}.exists")
    elif head == "is_your_turn":
        if not isinstance(condition["is_your_turn"], bool):
            raise DslError(f"{where}.is_your_turn: must be true or false")
    elif head == "is_attached":
        # Not defaulted: `{"is_attached": false}` is the other half of
        # reconfigure ("it is a creature while unattached"), and a bare
        # truthiness test would read a typo'd string as `true`.
        if not isinstance(condition["is_attached"], bool):
            raise DslError(f"{where}.is_attached: must be true or false")
    elif head == "top_of_library":
        spec = condition["top_of_library"]
        if not isinstance(spec, Mapping):
            raise DslError(f"{where}.top_of_library: must be an object")
        # The same printed-face-and-owner rule every off-battlefield filter
        # follows: the top card of a library is not tapped, attacking or
        # attached to anything, and a key that loads and matches nothing is
        # how a card comes to do less than it prints.
        unknown = set(spec) - (STATIC_ZONE_FILTER_KEYS - {"zone"})
        if unknown:
            raise DslError(
                f"{where}.top_of_library: a card in a library has a printed face and "
                f"an owner and nothing else; unsupported keys {sorted(unknown)}"
            )
        controller = spec.get("controller", "you")
        if controller not in ("you", "opponent", "any"):
            raise DslError(
                f"{where}.top_of_library.controller: must be 'you', 'opponent' or "
                f"'any', got {controller!r}"
            )
    elif head == "has_city_s_blessing":
        who = condition["has_city_s_blessing"]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.has_city_s_blessing: must name one of "
                f"{sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )
    elif head == "cmp":
        op = str(condition["cmp"])
        if op not in STATIC_CONDITION_OPS:
            raise DslError(f"{where}.cmp: unknown comparison {op!r}")
        for side in ("left", "right"):
            if side not in condition:
                raise DslError(f"{where}: a 'cmp' condition needs both 'left' and 'right'")
            _validate_static_value(condition[side], f"{where}.{side}")


#: Player specs a static's per-player life leaf may name.  Smaller than the
#: effect-side list: `active_player` and the binding forms read something that
#: is not settled while characteristics are being computed.
STATIC_LIFE_PLAYERS = frozenset({"you", "opponent", "each_opponent", "each_player", "all"})

#: The per-player life leaves.  Safe inside a static for the same reason a zone
#: count is: a life total is a pipeline *input*, and nothing in the fixed-order
#: characteristics pipeline can change one.
STATIC_LIFE_KEYS = frozenset({"min_life_of", "max_life_of"})


#: Every leaf a static ability's magnitude may use -- a `buff`'s `power`, a
#: `set_pt`, a `spell_cost_reduction`'s `amount`, either side of a `cmp`.
#:
#: A **fourth** language, and much smaller than the effect-side `VALUE_KEYS`:
#: every leaf here reads a pipeline *input*, because anything reading a derived
#: characteristic would let one static depend on another's output and the fixed
#: order of layers-lite has no way to resolve that. Named rather than built
#: inline so the authoring packet can show it -- a worker shown `value_keys` and
#: not this one reads the effect-side list as the whole language, which is how
#: Door of Destinies came to be filed as a gap.
STATIC_VALUE_KEYS = (
    frozenset({"const", "count", "mana_symbols", "counters_on"})
    | STATIC_LIFE_KEYS
    | PER_PLAYER_COUNT_KEYS
)


def _validate_static_value(value: Any, where: str) -> None:
    """Static abilities allow ``const``, ``count`` and the per-player leaves."""
    if isinstance(value, int):
        return
    if not isinstance(value, Mapping):
        raise DslError(f"{where}: static values must be an int, 'const' or 'count'")
    if set(value) - STATIC_VALUE_KEYS:
        raise DslError(
            f"{where}: static values may only use {sorted(STATIC_VALUE_KEYS)}, "
            f"got {sorted(value)}"
        )
    if not value:
        # `{}` passes the difference check above and then falls off the end of
        # `_static_value` -- which used to mean 0, and now means a crash. Named
        # here so it is a load error with a name on it instead.
        raise DslError(f"{where}: an empty object is not a static value")
    if "count" in value:
        _validate_static_count_filter(value["count"], f"{where}.count")
    if "counters_on" in value:
        # "Creatures you control of the chosen type get +1/+1 for each charge
        # counter on this artifact" -- Door of Destinies. Safe inside a static
        # for exactly the reason the `counters` *condition* head already is: a
        # counter is a pipeline **input**, placed and removed by primitives, and
        # no layer can change one. So an anthem sized by a counter count cannot
        # come to depend on another static's output, and the fixed order stays
        # acyclic. The condition head could only switch a fixed anthem on and
        # off; this scales one.
        #
        # The filter goes through the *static* counting validator, so it obeys
        # the same printed-face-and-owner rule every static filter does.
        validate_counters_on(
            value["counters_on"],
            f"{where}.counters_on",
            validate_objects=_validate_static_count_filter,
        )
    if "mana_symbols" in value:
        # Chroma, and Primalcrux is the reason it is here as well as in the
        # effect language: "its power and toughness are each equal to the number
        # of green mana symbols in the mana costs of permanents you control" is
        # a `set_pt` static. Safe for the reason a zone count is -- a *printed*
        # mana cost is a pipeline input, and no layer can change one.
        validate_mana_symbols(
            value["mana_symbols"],
            f"{where}.mana_symbols",
            validate_objects=_validate_static_count_filter,
        )
    for key in STATIC_LIFE_KEYS & set(value):
        who = value[key]
        if not isinstance(who, str) or who not in STATIC_LIFE_PLAYERS:
            raise DslError(
                f"{where}.{key}: must name one of {sorted(STATIC_LIFE_PLAYERS)}, got {who!r}"
            )
    for key in PER_PLAYER_COUNT_KEYS & set(value):
        # "As long as an opponent controls more lands than you" -- Verge Rangers.
        # Here as well as in the effect language, because the same printed clause
        # arrives as an intervening-`if` on one card and an "as long as" on the
        # next, and a leaf in one language only would load and read 0 in the
        # other. The filter is checked by the *static* counting validator, so it
        # obeys the same printed-face-and-owner rule every static filter does.
        validate_per_player_count(
            value[key],
            f"{where}.{key}",
            validate_objects=_validate_static_count_filter,
        )


def _compile_cost(model, where: str) -> Cost:
    validate_selector(model.sacrifice, f"{where}.cost.sacrifice")
    validate_selector(model.return_to_hand, f"{where}.cost.return_to_hand")
    validate_selector(model.exile_from_graveyard, f"{where}.cost.exile_from_graveyard")
    validate_selector(model.discard_selector, f"{where}.cost.discard_selector")
    # `total_power` is crew's, and it is a property of the *cost* rather than a
    # test on any one candidate -- a selector cannot say "these together" -- so
    # it is lifted out before the selector language sees it.
    tap_selector = dict(model.tap_permanents) if model.tap_permanents is not None else None
    total_power = tap_selector.pop("total_power", None) if tap_selector is not None else None
    validate_selector(tap_selector, f"{where}.cost.tap_permanents")
    if total_power is not None:
        if not isinstance(total_power, int) or total_power < 1:
            raise DslError(
                f"{where}.cost.tap_permanents.total_power: crew N is a positive "
                f"integer, got {total_power!r}"
            )
        if "count" in (tap_selector or {}):
            # Two different questions -- "how many" and "how much power" -- and
            # a card giving both would be paid by whichever the code checked
            # first, which is not something the printed line ever says.
            raise DslError(
                f"{where}.cost.tap_permanents: give 'count' or 'total_power', not both"
            )
    if model.mana_reduction is not None:
        if not model.mana:
            # "Costs {3} less" with no mana half to take it off. Clamped at zero,
            # so it would load clean and do nothing at all.
            raise DslError(
                f"{where}.cost: 'mana_reduction' needs a 'mana' cost to reduce"
            )
        _validate_cost_reduction(model.mana_reduction, f"{where}.cost.mana_reduction")
    if model.discard_selector is not None and not model.discard:
        raise DslError(f"{where}: 'discard_selector' needs a 'discard' count to narrow")
    if model.tap_permanents is not None and "tapped" in model.tap_permanents:
        # The pool forces `tapped: False` -- "untapped" is part of every printed
        # line of this shape, and a cost that could re-tap something already
        # tapped is free. Spelling it in the card would read as a knob that
        # works, so it is refused rather than overridden in silence.
        raise DslError(
            f"{where}.cost.tap_permanents: 'tapped' is implied and may not be set; "
            f"this cost always taps untapped permanents"
        )
    # One constructor for both spellings of a cost -- the model here, and the
    # raw mapping an optional effect's `pay` arrives as.  See `Cost.from_spec`.
    cost = Cost.from_spec(model.model_dump())
    assert cost is not None  # model_dump() is never None
    return cost


#: Ops a mana ability's rider may use -- "this land deals 1 damage to you".
#:
#: A mana ability is activated inside cost payment and **must never stop to
#: ask**: there is no stack to put a decision on and no priority window to
#: answer it in, so an op that yields would hang the payment solver mid-tap.
#: These six change a number and return. Anything else is refused at load, which
#: is the difference between a card that will not compile and a game that locks
#: up the first time somebody taps a Talisman.
MANA_RIDER_OPS = frozenset(
    {"damage", "lose_life", "gain_life", "add_poison", "add_counters", "remove_counters"}
)


#: The five colours, as single-symbol production tuples. The static superset a
#: reflecting mana ability advertises before the board narrows it.
_ANY_COLOR_OPTIONS: tuple[tuple[int, ...], ...] = tuple(
    parse_mana_production(f"{{{sym}}}") for sym in ("W", "U", "B", "R", "G")
)


def _split_mana_rider(
    effects: list[dict[str, Any]], where: str
) -> tuple[list[dict[str, Any]], tuple[Mapping[str, Any], ...]]:
    """``(the mana half, the rider)``.

    The rider is the run of effects after the mana, so the printed order is the
    order they happen in. The mana half must come first and must not be empty:
    an "ability" whose every effect is a rider is not a mana ability at all, and
    accepting one would put an ordinary activated ability inside cost payment.
    """
    split = 0
    for effect in effects:
        op = effect.get("op") if isinstance(effect, Mapping) else None
        if op not in ("add_mana", "choose_mode"):
            break
        split += 1
    mana, rider = effects[:split], effects[split:]
    for i, effect in enumerate(rider):
        op = effect.get("op") if isinstance(effect, Mapping) else None
        if op not in MANA_RIDER_OPS:
            raise DslError(
                f"{where}: mana abilities may only contain 'add_mana' (or a single "
                f"'choose_mode' of them), optionally followed by a rider from "
                f"{sorted(MANA_RIDER_OPS)} -- got {op!r} at effects[{split + i}]"
            )
    return mana, tuple(rider)


def _mana_options(effects: list[dict[str, Any]], where: str) -> tuple[tuple[int, ...], ...]:
    """Flatten a mana ability's effects into every 6-tuple it could produce."""
    if len(effects) == 1 and effects[0].get("op") == "choose_mode":
        options = []
        for mode in effects[0].get("modes", []):
            options.append(_sum_mana(mode.get("effects", []), where))
        if not options:
            raise DslError(f"{where}: modal mana ability has no modes")
        return tuple(options)
    return (_sum_mana(effects, where),)


#: Value forms a mana ability's ``amount`` may NOT use.
#:
#: A mana ability is activated inside cost payment, with nothing on the stack:
#: there is no X, no target, no trigger binding and no enclosing loop. Each of
#: these would evaluate to 0 and make a card that silently produces no mana, so
#: they are refused at load rather than at the table.
MANA_AMOUNT_FORBIDDEN = frozenset({"x", "target", "binding", "loop_value"})


def _validate_mana_amount(amount: Any, where: str) -> None:
    validate_value(amount, where)
    if isinstance(amount, str) and amount == "x":
        raise DslError(f"{where}: a mana ability has no X to read")
    if not isinstance(amount, Mapping):
        return
    bad = MANA_AMOUNT_FORBIDDEN & set(amount)
    if bad:
        raise DslError(
            f"{where}: a mana ability is activated during payment, with no X, "
            f"targets, bindings or loop -- {sorted(bad)} would always read 0"
        )


def _sum_mana(effects: list[dict[str, Any]], where: str) -> tuple[int, ...]:
    total = [0] * 6
    for effect in effects:
        if effect.get("op") != "add_mana":
            raise DslError(
                f"{where}: mana abilities may only contain 'add_mana' "
                f"(or a single 'choose_mode' of them), got {effect.get('op')!r}"
            )
        for i, v in enumerate(parse_mana_production(str(effect.get("mana", "")))):
            total[i] += v
    if not any(total):
        raise DslError(f"{where}: mana ability produces no mana")
    return tuple(total)


def _mana_amount(effects: list[dict[str, Any]], where: str) -> Mapping[str, Any] | None:
    """The ``amount`` on a variable mana ability -- "Add {G} for each ...".

    Deliberately narrow. The amount scales *one* symbol tuple, so a card that
    carried one would be ambiguous if it also summed several `add_mana`s or
    offered modes: "for each counter" would have no single thing to multiply.
    One `add_mana`, or no amount at all.
    """
    carriers = [e for e in effects if isinstance(e, Mapping) and "amount" in e]
    if not carriers:
        return None
    if len(effects) != 1:
        raise DslError(
            f"{where}: a mana ability with an 'amount' must be a single 'add_mana' "
            f"-- there is otherwise no one symbol for the amount to scale"
        )
    amount = carriers[0]["amount"]
    _validate_mana_amount(amount, f"{where}.amount")
    return dict(amount) if isinstance(amount, Mapping) else amount


def _mana_restriction(spec: Any, where: str) -> ManaRestriction:
    """"Spend this mana only to cast …" compiled to a :class:`ManaRestriction`.

    A bare string or list is the **cast** half alone, which is what every card
    printed before Secluded Courtyard says and why the old spelling still means
    exactly what it meant:

    - ``"creature"`` -- one name, Ancient Ziggurat.
    - ``["Vampire", "Cleric", "Demon"]`` -- the printed "and/or", which is an
      any-of: one matching name is enough (Master of Dark Rites).

    An **object** names the halves separately, because the printed sentence
    does: "…only to cast a creature spell of the chosen type **or activate an
    ability of** a creature source of the chosen type" gives them different
    subjects, and a card that says nothing about activating abilities must not
    permit it.

    ```jsonc
    "mana_restriction": {
      "cast":     [["creature", {"chosen_type_of": "self"}]],
      "activate": [["creature", {"chosen_type_of": "self"}]]
    }
    ```

    A nested list is an **all-of**, and this card needs it: "a creature spell
    **of** the chosen type" is a conjunction, and flattening it into the any-of
    above would offer the mana for every creature ever printed -- a strictly
    better card than the printed one.

    ``{"chosen_type_of": "self"}`` is the one entry that is not a literal name.
    It compiles to `mana.CHOSEN_TYPE` and is substituted per permanent by
    `costs.resolve_mana_restriction`, because the type does not exist until the
    permanent is on the battlefield. Spelled the same way `subtypes` filters
    already spell it (Vanquisher's Banner, Door of Destinies) rather than as a
    new key meaning the same thing.
    """
    if isinstance(spec, Mapping):
        unknown = sorted(set(spec) - {"cast", "activate"})
        if unknown:
            raise DslError(
                f"{where}: 'mana_restriction' names {unknown}; mana is only ever spent "
                f"to 'cast' a spell or 'activate' an ability"
            )
        restriction = ManaRestriction(
            cast=_restriction_groups(spec.get("cast"), f"{where}.cast"),
            activate=_restriction_groups(spec.get("activate"), f"{where}.activate"),
        )
        if not restriction.cast and not restriction.activate:
            raise DslError(
                f"{where}: 'mana_restriction' permits nothing at all; "
                f"omit it for ordinary mana"
            )
        return restriction
    return ManaRestriction(cast=_restriction_groups(spec, where))


def _restriction_groups(spec: Any, where: str) -> tuple[frozenset[str], ...]:
    """One half of a restriction: the groups, any of which may be satisfied.

    ``None`` is an omitted half and means "never", which is the whole of how a
    card that says only "to cast" refuses to fund an activation.
    """
    if spec is None:
        return ()
    groups = [spec] if isinstance(spec, str) else list(spec)
    if not groups:
        raise DslError(f"{where}: 'mana_restriction' is empty; omit it for ordinary mana")
    out: list[frozenset[str]] = []
    for group in groups:
        entries = [group] if isinstance(group, (str, Mapping)) else list(group)
        if not entries:
            raise DslError(
                f"{where}: an empty group in 'mana_restriction' restricts nothing; "
                f"omit it for ordinary mana"
            )
        out.append(frozenset(_restriction_name(entry, where) for entry in entries))
    return tuple(out)


def _restriction_name(entry: Any, where: str) -> str:
    """One name inside a restriction group: a literal, or the chosen type."""
    if isinstance(entry, Mapping):
        # Exactly the one dynamic leaf, and validated as such: a near-miss
        # spelling that fell through would freeze into a literal name no card
        # has, producing mana that can never be spent.
        if set(entry) != {"chosen_type_of"} or entry["chosen_type_of"] != "self":
            raise DslError(
                f"{where}: the only dynamic mana restriction is "
                f'{{"chosen_type_of": "self"}}, not {dict(entry)!r}'
            )
        return CHOSEN_TYPE
    # A card type, or a subtype. Subtypes are open-ended in Magic and there is no
    # closed list to check one against, so the guard is the weaker "looks like a
    # word": a typo here produces mana that can never be spent, which is a
    # strictly worse card than the printed one -- the safe direction, but a
    # silent one, so it is worth the shape check.
    if (
        not isinstance(entry, str)
        or not entry
        or not entry.replace("-", "").replace(" ", "").isalpha()
    ):
        raise DslError(
            f"{where}: unparsable mana restriction {entry!r} "
            f"(a card type or subtype, lowercased)"
        )
    return entry.lower()


#: Refuse a counter kind that *nearly* names a keyword (122.1c).  Lives in
#: ``effects/values.py`` because ``counters_on`` reads a kind in both value
#: languages and one copy of the near-miss rule is the point; aliased here for
#: the trigger, replacement and ``add_counters`` call sites that predate it.
_check_counter_kind = validate_counter_kind


def _validate_effect(effect: Any, where: str, target_ids: set[str]) -> None:
    """Recursively validate one effect dict."""
    if not isinstance(effect, Mapping):
        raise DslError(f"{where}: effect must be an object")
    op = effect.get("op")
    if op is None:
        raise DslError(f"{where}: effect is missing 'op'")
    if op not in known_ops():
        raise DslError(f"{where}: unknown effect op {op!r} (implemented: {sorted(known_ops())})")

    for key in ("objects", "per", "selector", "affects"):
        if key in effect:
            validate_selector(effect[key], f"{where}.{key}")
    for key in ("amount", "count", "power", "toughness"):
        if key in effect:
            validate_value(effect[key], f"{where}.{key}")
    if "condition" in effect:
        validate_condition(effect["condition"], f"{where}.condition")
    # Every op that names a counter kind spells it `counter` -- `add_counters`,
    # `remove_counters`, `move_counters` -- so this is checked once here rather
    # than per op, and the next op to grow one is covered before it is written.
    if "counter" in effect:
        _check_counter_kind(effect["counter"], f"{where}.counter")
    # `return_from_graveyard`'s "return it with a lifelink counter on it" spells
    # the same thing as a kind-keyed map, so both spellings are covered.
    if isinstance(effect.get("counters"), Mapping):
        for kind in effect["counters"]:
            _check_counter_kind(kind, f"{where}.counters")

    if "target" in effect and str(effect["target"]) not in target_ids:
        raise DslError(
            f"{where}: references target {effect['target']!r} which the card does not declare"
        )
    for key in ("objects", "per", "selector"):
        sub = effect.get(key)
        if isinstance(sub, Mapping) and "target" in sub and str(sub["target"]) not in target_ids:
            raise DslError(
                f"{where}.{key}: references target {sub['target']!r} which the card does not declare"
            )

    if op == "may" and "pay" in effect:
        # "You may pay {2}. If you do, draw a card." Validated through the same
        # CostModel an activated ability's cost uses, so an unknown key here is a
        # load error rather than a cost quietly dropped -- which would turn a
        # card that draws for {2} into one that draws free.
        if not isinstance(effect["pay"], dict):
            raise DslError(f"{where}: 'pay' must be an object")
        try:
            CostModel.model_validate(effect["pay"])
        except Exception as exc:  # pydantic ValidationError
            raise DslError(f"{where}: bad 'pay' cost: {exc}") from exc
        # A payment has to buy *something*, but there are two things it can buy.
        # "You may pay {2}. If you do, draw a card" buys the `effects`. Rhystic
        # Study's "unless that player pays {1}" buys the **absence** of the
        # `else` -- the payer gets nothing and that is the whole point, because
        # what they are paying for is to stop the other branch happening. So
        # `effects` alone is not the test; having neither branch is.
        if not effect.get("effects") and not effect.get("else"):
            raise DslError(
                f"{where}: 'pay' needs 'effects' or 'else' -- paying for nothing is not a card"
            )
        if effect["pay"].get("mana_reduction") is not None:
            # Read: an optional `pay` is charged through `pay`, which prices its
            # mana half with `ability_mana` like any other cost node. Validated
            # here for the same reason an ability's is -- a malformed reduction
            # should be a load error, not a mid-resolution crash.
            _validate_cost_reduction(
                effect["pay"]["mana_reduction"], f"{where}.pay.mana_reduction"
            )
        if (times := effect["pay"].get("times")) is not None:
            # Cumulative upkeep's multiplier. It scales the *mana* half and
            # nothing else, so a `times` beside a cost with no mana would load
            # and multiply nothing -- a card that reads "for each age counter"
            # and charges a flat price.
            validate_value(times, f"{where}.pay.times")
            if not effect["pay"].get("mana"):
                raise DslError(
                    f"{where}.pay: 'times' multiplies the mana cost, and there is none"
                )
    if op == "become_monarch" and "player" in effect:
        # Who gets the crown is the whole op, and it is the one op whose `player`
        # can be a *target* -- Éomer's "target player becomes the monarch". Both
        # halves of that are silent when wrong: a misspelled name raises only
        # once the ability resolves, and a target id the card never declared
        # resolves to nobody, so the printed line does nothing at all. The
        # generic target check above covers `objects`/`per`/`selector` and not
        # this.
        who = effect["player"]
        if isinstance(who, str) and who not in PLAYER_SPEC_NAMES:
            raise DslError(
                f"{where}.player: unknown player spec {who!r} "
                f"(implemented: {sorted(PLAYER_SPEC_NAMES)}, or a target)"
            )
        if isinstance(who, Mapping) and "target" in who and str(who["target"]) not in target_ids:
            raise DslError(
                f"{where}.player: references target {who['target']!r} "
                f"which the card does not declare"
            )
    if "from_top" in effect:
        # "…into its owner's library second from the top." The depth is the whole
        # of the difference between Hinder and a plain tuck, and both ways of
        # getting it wrong are silent: written on an op that does not read it the
        # card is a strictly better one than printed (the permanent comes back
        # next turn), and a zero or a negative ordinal is not a position on a
        # library at all -- `put_on_top` clamps it, but a card that says it meant
        # something the engine had to correct is a card that was authored wrong.
        if op != "put_on_top":
            raise DslError(
                f"{where}: 'from_top' is a library depth and only put_on_top reads it, not {op!r}"
            )
        validate_value(effect["from_top"], f"{where}.from_top")
        depth = effect["from_top"]
        if isinstance(depth, Mapping) and "const" in depth:
            depth = depth["const"]
        if isinstance(depth, int) and not isinstance(depth, bool) and depth < 1:
            raise DslError(
                f"{where}.from_top: depth counts from 1 (1 is the top card); got {depth}"
            )
    if op == "look_at_hand" and "player" not in effect:
        # Whose hand is the whole ability. Defaulted, Glasses of Urza would
        # silently pick a player instead of targeting one.
        raise DslError(f"{where}: look_at_hand needs a 'player' -- whose hand")
    if op == "search_zones":
        zones = effect.get("zones")
        # A missing or single-zone list is `search_library` spelled the long way,
        # and the whole point of this op is that the count is over the *union*.
        if not isinstance(zones, (list, tuple)) or len(zones) < 2:
            raise DslError(
                f"{where}: search_zones needs 'zones' with at least two of "
                f"{list(SEARCHABLE)}; use search_library for one"
            )
        unknown = [z for z in zones if z not in SEARCHABLE]
        if unknown:
            raise DslError(
                f"{where}: cannot search {unknown} (searchable: {list(SEARCHABLE)})"
            )
        if len(set(zones)) != len(zones):
            # A repeated zone would put every card in it into the pool twice.
            raise DslError(f"{where}: search_zones lists a zone twice: {list(zones)}")
        # The op builds its pool one zone at a time and tests each half against
        # the zone that half came from, so a `zone` written here is overridden
        # rather than honoured -- a card asking for one would not get it.
        if isinstance(effect.get("selector"), Mapping) and "zone" in effect["selector"]:
            raise DslError(
                f"{where}.selector: drop 'zone' -- search_zones takes its zones "
                f"from 'zones', and each half is matched in its own"
            )
    if op == "look_at_top":
        # The depth is the card. Without an amount the op would look at one
        # card and Through the Forest Gate would silently become a cantrip,
        # so it is required rather than defaulted.
        if "amount" not in effect:
            raise DslError(f"{where}: look_at_top needs an 'amount' -- how deep it looks")
        destination = str(effect.get("destination", "hand"))
        if destination not in DESTINATIONS:
            raise DslError(
                f"{where}: unknown look_at_top destination {destination!r} "
                f"(implemented: {sorted(DESTINATIONS)})"
            )
    if op == "reveal_until":
        # The selector *is* the "until", so an omitted one is not a smaller
        # version of the card -- an empty selector matches the very first card
        # revealed, and "reveal until you reveal a creature card that shares a
        # type" would quietly become "put the top card into your hand".
        selector = effect.get("objects") or effect.get("selector")
        if not isinstance(selector, Mapping) or not selector:
            raise DslError(
                f"{where}: reveal_until needs a non-empty 'objects' -- "
                f"the selector is the card it stops at"
            )
        # An `amount` would be read by nobody: the depth is the library's, not
        # the card's, and a card that wrote one would believe it was bounded.
        if "amount" in effect:
            raise DslError(
                f"{where}: reveal_until takes no 'amount' -- the scan is unbounded; "
                f"use look_at_top for a bounded window"
            )
        destination = str(effect.get("destination", "hand"))
        if destination not in DESTINATIONS:
            raise DslError(
                f"{where}: unknown reveal_until destination {destination!r} "
                f"(implemented: {sorted(DESTINATIONS)})"
            )
    # Same argument as look_at_top, and the printed keyword is *named* for the
    # number -- "hideaway 4". Defaulted it would look at one card, and the
    # ability that later plays it would still work, so nothing downstream would
    # ever complain.
    if op == "hideaway" and "amount" not in effect:
        raise DslError(f"{where}: hideaway needs an 'amount' -- hideaway N")
    if op == "cant_attack_player":
        # All three keys are required, and each omission is silent in its own
        # way. Without `attacker`/`defender` the spec defaults to the controller
        # on both sides, which `restrict_attack` refuses as a self-restriction --
        # the card would load, resolve, log nothing and prohibit nothing. And the
        # two durations are not a long and a short version of one restriction:
        # `this_turn` read for `this_combat` blanks the extra combat a Relentless
        # Assault bought, `this_combat` read for `this_turn` gives it away free.
        for side in ("attacker", "defender"):
            if side not in effect:
                raise DslError(
                    f"{where}: cant_attack_player needs '{side}' -- "
                    f"the restriction names both players"
                )
            who = effect[side]
            if isinstance(who, str) and who not in PLAYER_SPEC_NAMES:
                raise DslError(
                    f"{where}.{side}: unknown player spec {who!r} "
                    f"(implemented: {sorted(PLAYER_SPEC_NAMES)}, or a target)"
                )
            if (
                isinstance(who, Mapping)
                and "target" in who
                and str(who["target"]) not in target_ids
            ):
                raise DslError(
                    f"{where}.{side}: references target {who['target']!r} "
                    f"which the card does not declare"
                )
        if "duration" not in effect:
            raise DslError(
                f"{where}: cant_attack_player needs a 'duration' "
                f"(implemented: 'this_turn', 'this_combat')"
            )
        if str(effect["duration"]) not in ATTACK_RESTRICTION_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_attack_player duration {effect['duration']!r} "
                f"(implemented: {sorted(ATTACK_RESTRICTION_DURATIONS)})"
            )
    if op == "cant_block":
        # Two keys, and every way of getting them wrong loads cleanly and plays
        # a different card.
        #
        # Exactly one of `objects` and `all_creatures`, because the two are not
        # a general and a special case: a `cant_block` with neither would have
        # to guess, and both guesses are bad -- "nobody" makes the ability do
        # nothing, "everybody" turns Aragorn's *targeted* half into a one-sided
        # Falter. Both together is a card that says two things at once.
        #
        # And the duration is required for the reason `cant_attack_player`'s is:
        # `this_turn` read for `until_your_next_turn` gives the blockers back a
        # turn early, and the reverse keeps them away for a whole turn cycle.
        has_objects = "objects" in effect
        has_all = bool(effect.get("all_creatures"))
        if has_objects == has_all:
            raise DslError(
                f"{where}: cant_block needs exactly one of 'objects' "
                f"(the creatures chosen when it resolves) and 'all_creatures': true "
                f"(every creature, including ones that enter later)"
            )
        if "duration" not in effect:
            raise DslError(
                f"{where}: cant_block needs a 'duration' "
                f"(implemented: {sorted(BLOCK_PROHIBITION_DURATIONS)})"
            )
        if str(effect["duration"]) not in BLOCK_PROHIBITION_DURATIONS:
            raise DslError(
                f"{where}: unknown cant_block duration {effect['duration']!r} "
                f"(implemented: {sorted(BLOCK_PROHIBITION_DURATIONS)})"
            )
    if op == "unblockable":
        # `objects` is required and there is no wildcard shorthand, which is the
        # one difference from `cant_block` above. Defaulting an absent `objects`
        # to "every creature" there would be a one-sided Falter; here it would be
        # a one-sided *unblockable board*, which is worse, and no printed card
        # says it -- so the omission is a mistake and is refused as one.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: unblockable needs 'objects' (the creatures that "
                f"can't be blocked, chosen when it resolves)"
            )
        # And the duration is required for the reason `cant_block`'s is: an
        # evasion read a turn long when it was a turn cycle, or the reverse, is a
        # different card both ways round.
        if "duration" not in effect:
            raise DslError(
                f"{where}: unblockable needs a 'duration' "
                f"(implemented: {sorted(UNBLOCKABLE_DURATIONS)})"
            )
        if str(effect["duration"]) not in UNBLOCKABLE_DURATIONS:
            raise DslError(
                f"{where}: unknown unblockable duration {effect['duration']!r} "
                f"(implemented: {sorted(UNBLOCKABLE_DURATIONS)})"
            )
    if op == "must_attack":
        duration = str(effect.get("duration", "next_combat"))
        if duration not in ("this_turn", "next_combat"):
            # A misspelled duration would set a requirement nothing ever
            # discharges, or one that expires before the combat it names.
            raise DslError(
                f"{where}: unknown must_attack duration {duration!r} "
                f"(implemented: 'this_turn', 'next_combat')"
            )
    # The link is written on the exiled card and points at the source of the
    # ability that exiled it. With nothing to exile there is nothing to link,
    # and the card would load as a permanent exile with no way to say so.
    if op == "exile" and effect.get("until_leaves") and "objects" not in effect:
        raise DslError(
            f"{where}: 'until_leaves' needs 'objects' -- there is nothing to link"
        )
    # Same shape as the link above: the permission is written on the exiled
    # card, so with nothing selected there is no card to write it on and the
    # key is silently doing nothing.
    if op == "exile" and effect.get("playable_this_turn") and "objects" not in effect:
        raise DslError(
            f"{where}: 'playable_this_turn' needs 'objects' -- "
            f"there is nothing to grant permission on"
        )
    if op == "copy_permanent" and (overrides := effect.get("except_") or effect.get("except")):
        # "…except it's a white Zombie Angel with no mana cost." A misspelled
        # key here would be silently dropped, and the token would come back a
        # plain copy -- which is a different card and looks identical until
        # somebody reads its colour.
        if not isinstance(overrides, Mapping):
            raise DslError(f"{where}: 'except_' must be an object")
        unknown = set(overrides) - {"colors", "add_subtypes", "no_mana_cost"}
        if unknown:
            raise DslError(
                f"{where}.except_: unsupported keys {sorted(unknown)} "
                f"(implemented: 'colors', 'add_subtypes', 'no_mana_cost')"
            )
        for color in overrides.get("colors") or ():
            if color not in KNOWN_COLORS:
                raise DslError(f"{where}.except_.colors: unknown colour {color!r}")
    if op == "add_subtype":
        # An op that names no subtype is a printed sentence that does nothing,
        # and it would load and resolve exactly like one that works.
        if not effect.get("subtypes"):
            raise DslError(f"{where}: add_subtype needs 'subtypes'")
        if "objects" not in effect:
            raise DslError(f"{where}: add_subtype needs 'objects' -- there is nothing to change")
        if "types" in effect:
            # Only subtypes. "Becomes an artifact in addition to its other
            # types" is a different sentence and would need the type to reach
            # the same places subtypes do; accepting the key and dropping it is
            # how a card silently half-works.
            raise DslError(
                f"{where}: add_subtype changes subtypes only; use 'animate' for card types"
            )
    if op == "gain_control":
        # "Gain control of" with nothing named is a card that reads like removal
        # and does nothing at all.
        if "objects" not in effect:
            raise DslError(f"{where}: gain_control needs 'objects' -- there is nothing to take")
        # Both forms exist now, and the guard stays for the reason it was
        # written: a `duration` nobody checked would be read as "until end of
        # turn" by whoever wrote it and ignored by the engine, which turns Act
        # of Treason into a strictly better card than the printed one. What
        # changed is that `until_end_of_turn` is now implemented rather than
        # refused -- every other spelling is still a load error, exactly as
        # `grant_keyword`'s is below.
        if "duration" in effect and str(effect["duration"]) not in CONTROL_DURATIONS:
            raise DslError(
                f"{where}: unknown gain_control duration {effect['duration']!r} "
                f"(use 'until_end_of_turn' or 'permanent')"
            )
    if op == "create_token" and "token" not in effect:
        raise DslError(f"{where}: create_token needs a 'token' id")
    # A misspelled duration would silently fall back to until-end-of-turn,
    # which is the *wrong half* of riot rather than a smaller version of it.
    if op == "grant_keyword" and effect.get("duration", "until_end_of_turn") not in (
        "until_end_of_turn",
        "permanent",
    ):
        raise DslError(
            f"{where}: unknown grant_keyword duration {effect['duration']!r} "
            f"(use 'until_end_of_turn' or 'permanent')"
        )
    if op == "add_poison" and "amount" in effect:
        validate_value(effect["amount"], f"{where}.amount")
    if op == "detain" and not effect.get("objects"):
        # Detain with no selector restricts nobody: the card resolves, the log
        # says nothing, and the creature attacks anyway.
        raise DslError(f"{where}: detain needs 'objects' naming what is detained")
    if op == "extra_combat":
        # "…followed by an additional main phase" is half of what Relentless
        # Assault and Resurgence print, and a misspelled key here drops it
        # silently -- leaving a four-mana sorcery that grants a bare extra
        # combat, which is a different and worse card. So the flag is checked by
        # name and by type.
        if "extra_main" in effect and not isinstance(effect["extra_main"], bool):
            raise DslError(
                f"{where}: extra_combat's 'extra_main' is a flag (true/false), "
                f"got {effect['extra_main']!r}"
            )
        # A phase belongs to the *turn*, not to a player: an extra combat granted
        # during somebody else's turn is theirs (Seize the Day). Accepting a
        # `player` and ignoring it would read as "your extra combat" and be
        # neither.
        for key in ("player", "controller"):
            if key in effect:
                raise DslError(
                    f"{where}: extra_combat takes no {key!r} -- an extra phase belongs "
                    f"to the turn in progress, whoever's turn that is"
                )
    if op == "set_flag" and not effect.get("flag"):
        # A flag with no name writes nothing, so renown's once-only guard never
        # closes and the creature grows on every combat damage for ever.
        raise DslError(f"{where}: set_flag needs a 'flag' to write")
    if op == "set_turn_flag":
        if not effect.get("flag"):
            # Same failure as `set_flag` above with a worse tell: the guard that
            # reads it back never bites, so Combat Celebrant offers its exert on
            # every attack of the turn and the card that prints a once-per-turn
            # clause plays as though it does not.
            raise DslError(f"{where}: set_turn_flag needs a 'flag' to write")
        if "duration" in effect:
            # There is exactly one duration here, and it is in the name. A card
            # asking for another one is asking for `set_flag`, whose word is
            # permanent -- accepting and ignoring the key would give whichever
            # of the two the author did not want.
            raise DslError(
                f"{where}: set_turn_flag takes no 'duration' -- it lasts the turn "
                f"(use set_flag for a word that never wears off)"
            )
    if op == "move_counters":
        # Without a destination the counters come off the source and go
        # nowhere, which is a card that reads "move a +1/+1 counter onto it"
        # and quietly shrinks its own creature.
        if not effect.get("objects"):
            raise DslError(
                f"{where}: move_counters needs 'objects' naming where the counters go "
                f"(the source is 'from', defaulting to this permanent)"
            )
        if "amount" in effect:
            validate_value(effect["amount"], f"{where}.amount")
        if "from" in effect:
            validate_selector(effect["from"], f"{where}.from")
    if op == "must_block" and not effect.get("objects"):
        # Without `objects` the op resolves an empty pool and requires nothing
        # of anybody, which is a provoke that loads clean and does nothing --
        # the failure this whole pass exists to refuse.
        raise DslError(
            f"{where}: must_block needs 'objects' naming who has to block "
            f"(the attacker defaults to the ability's own source)"
        )
    if op == "counter" and "sid" in effect:
        # Ward's "counter it": the victim is named by value, not chosen. A
        # malformed expression here would evaluate to 0, match no stack item and
        # counter nothing -- a ward that reads as printed and never protects
        # anything, which is the failure this whole pass exists to refuse.
        validate_value(effect["sid"], f"{where}.sid")
        if "target" in effect:
            raise DslError(
                f"{where}: counter takes 'sid' or 'target', not both -- one names "
                f"the spell that targeted this permanent, the other lets its "
                f"controller pick a different spell"
            )
    if "all_if" in effect:
        # Entwine. Only `choose_mode` has modes to take all of, so anywhere else
        # the key would load, be ignored, and leave a card that reads "choose
        # both" and chooses one.
        if op != "choose_mode":
            raise DslError(f"{where}: 'all_if' only means anything on choose_mode, not {op!r}")
        validate_condition(effect["all_if"], f"{where}.all_if")
    if "up_to_if" in effect:
        # The same guard for entwine's mirror image, and it was missing -- which
        # is how a card carrying `up_to_if` compiled, played and cleared every
        # gate while its first printed sentence did nothing at all.
        if op != "choose_mode":
            raise DslError(f"{where}: 'up_to_if' only means anything on choose_mode, not {op!r}")
        more = effect["up_to_if"]
        if not isinstance(more, Mapping) or "condition" not in more:
            raise DslError(
                f"{where}: 'up_to_if' takes a 'condition' saying when the extra "
                f"modes are offered, and optionally a 'count'"
            )
        validate_condition(more["condition"], f"{where}.up_to_if.condition")
        if "count" in more:
            validate_value(more["count"], f"{where}.up_to_if.count")
    if "as" in effect:
        # `as` names a binding -- `snapshot`'s, and the record `reveal`,
        # `sacrifice`, `exile` and the two token-making ops write of what they
        # consumed or produced. A non-string would be stringified into a name
        # nothing reads back, so the count it feeds would be 0 and amplify would
        # enter with no counters.
        if not (isinstance(effect["as"], str) and effect["as"]):
            raise DslError(
                f"{where}: 'as' must be a non-empty binding name, got {effect['as']!r}"
            )
        if op not in RECORDING_OPS:
            # And an `as` on an op that writes no binding fails exactly the same
            # way while looking right on the page: "destroy the creatures, then
            # draw a card for each destroyed this way" would load, resolve, and
            # draw nothing. Only these ops record, so only these may be asked
            # to -- the next op to grow one adds itself here.
            raise DslError(
                f"{where}: {op!r} records no binding, so its 'as' would name one "
                f"nothing writes and every read of it would be 0 "
                f"(ops that record: {sorted(RECORDING_OPS)})"
            )
    if op == "join_forces":
        # The total is the card -- "for each mana paid this way" -- so an effect
        # that collects it and names no binding has taxed the whole table for
        # nothing, and would resolve without complaint.
        if not effect.get("as"):
            raise DslError(
                f"{where}: join_forces needs an 'as' naming the binding the total "
                f"lands in; without it nothing can read what was paid"
            )
        if "pay" in effect:
            if not isinstance(effect["pay"], dict):
                raise DslError(f"{where}: 'pay' must be an object")
            try:
                CostModel.model_validate(effect["pay"])
            except Exception as exc:  # pydantic ValidationError
                raise DslError(f"{where}: bad 'pay' cost: {exc}") from exc
            if effect["pay"].get("mana_reduction") is not None:
                _validate_cost_reduction(
                    effect["pay"]["mana_reduction"], f"{where}.pay.mana_reduction"
                )
    if op == "regenerate" and not effect.get("objects"):
        # A shield with nothing to put it on. The ability would cost mana, log
        # nothing and save nobody -- and "Regenerate this creature" is three
        # words away from being right.
        raise DslError(
            f"{where}: regenerate needs 'objects' naming what is shielded "
            f"(use {{\"self_only\": true}} for \"regenerate this creature\")"
        )
    if op == "phase_out" and not effect.get("objects"):
        # The same trap as `regenerate` below. `choose_objects` with no selector
        # finds nothing, so the spell would resolve, log nothing and phase
        # nobody out -- and "this permanent phases out" is three words away.
        raise DslError(
            f"{where}: phase_out needs 'objects' naming what phases out "
            f"(use {{\"self_only\": true}} for \"this permanent phases out\")"
        )
    if op == "unattach" and not effect.get("objects"):
        # Explore's trap once more: "unattach this permanent" is three words on
        # the Equipment that prints it, and a default would silently unattach
        # the spell object on anything that is not a permanent's own ability.
        raise DslError(
            f"{where}: unattach needs 'objects' naming what comes off "
            f"(use {{\"self_only\": true}} for \"unattach this permanent\")"
        )
    if op == "explore" and not effect.get("objects"):
        # 701.40a puts the +1/+1 counter on the *exploring* permanent, so the op
        # has to be told which one that is. Defaulted to this permanent it would
        # read correctly on a creature and silently do nothing on a sorcery,
        # whose source is a spell on the stack -- so the card would reveal no
        # card, place no counter, and load perfectly cleanly.
        raise DslError(
            f"{where}: explore needs 'objects' naming what explores "
            f"(use {{\"self_only\": true}} for \"it explores\")"
        )
    if op == "connive" and not effect.get("objects"):
        # Same trap as explore, and the same three words fix it: the +1/+1
        # counters go on the *conniving* permanent, so a defaulted `self_only`
        # would be right on "whenever this creature attacks, it connives" and
        # would draw and discard for nobody on "target creature connives".
        raise DslError(
            f"{where}: connive needs 'objects' naming what connives "
            f"(use {{\"self_only\": true}} for \"it connives\")"
        )
    # `reflecting` is the one add_mana that names no symbols: "one mana of any
    # color that a land an opponent controls could produce" reads them off the
    # board, so the card names the permanents to ask instead.
    if (
        op == "add_mana"
        and "mana" not in effect
        and "reflecting" not in effect
        and not effect.get("in_commander_identity")
    ):
        raise DslError(
            f"{where}: add_mana needs 'mana' (or 'reflecting', or 'in_commander_identity')"
        )
    if op == "animate":
        # "Becomes a 4/4 creature" is the whole point, and an animation with no
        # size would silently make a 0/0 that dies to state-based actions the
        # moment it arrives.
        if "power" not in effect or "toughness" not in effect:
            raise DslError(f"{where}: animate needs 'power' and 'toughness'")
        for t in effect.get("types", ()) or ():
            if t not in KNOWN_TYPES:
                raise DslError(f"{where}: unknown card type {t!r}")
        for k in effect.get("keywords", ()) or ():
            if k not in KNOWN_KEYWORDS:
                raise DslError(f"{where}: unknown keyword {k!r}")
        for c in effect.get("colors", ()) or ():
            if c not in KNOWN_COLORS:
                raise DslError(f"{where}: unknown colour {c!r}")
    if op == "delay":
        # A misspelled step would schedule something that never comes due -- a
        # card that reads "at the beginning of the next upkeep, draw a card" and
        # silently draws nothing, which is exactly what this pass exists to stop.
        step = str(effect.get("step", "end_step"))
        if step not in DELAY_STEPS:
            raise DslError(
                f"{where}: unknown delay step {step!r} (implemented: {sorted(DELAY_STEPS)})"
            )
        if not effect.get("effects"):
            raise DslError(f"{where}: delay needs 'effects' to schedule")

    # A grant naming an ability the card does not have is a silent no-op: the
    # index defaults to 0 and every miss lands on the first grantable, or on
    # nothing at all. Both spellings are accepted by the op, so both are checked.
    if op == "grant_ability" and "ability" not in effect and "ability_index" not in effect:
        raise DslError(
            f"{where}: grant_ability needs 'ability' -- the index into the "
            f"card's own 'grantable_abilities'"
        )

    # A loop with no body is a card that does nothing, and the whole point of
    # this op is the body -- without it the printed "each opponent sacrifices"
    # silently becomes "nobody does".
    if op == "for_each_player" and not effect.get("effects"):
        raise DslError(f"{where}: for_each_player needs 'effects' to run per player")

    # "Choose one that hasn't been chosen" belongs to a permanent's repeated
    # ability, not to a spell. A spell's top-level modes are picked at *cast*
    # time (601.2b, `Game._ask_modes`), which never sees this filter -- so the
    # spent modes would still be offered and the flag written for nothing. And
    # the clause is meaningless there anyway: a spell is a new object each cast,
    # with no record of the last one.
    if op == "choose_mode" and effect.get("once_each") and ".spell_effects[" in where:
        raise DslError(
            f"{where}: 'once_each' is for a permanent's repeated modal ability; "
            f"a spell chooses its modes as it is cast and remembers nothing"
        )

    for key in ("then", "else", "effects"):
        if key in effect:
            for i, sub in enumerate(effect[key] or []):
                _validate_effect(sub, f"{where}.{key}[{i}]", target_ids)
    for i, mode in enumerate(effect.get("modes", []) or []):
        if not isinstance(mode, Mapping):
            raise DslError(f"{where}.modes[{i}]: must be an object")
        for j, sub in enumerate(mode.get("effects", []) or []):
            _validate_effect(sub, f"{where}.modes[{i}].effects[{j}]", target_ids)


def _derive_color_identity(
    colors: frozenset[str], mana_cost: ManaCost, abilities: tuple[Ability, ...]
) -> frozenset[str]:
    """Colour identity = colours in the cost, plus colours in any mana symbol on the card."""
    identity = set(colors)
    for ability in abilities:
        if ability.cost is not None:
            identity.update(c.value for c in ability.cost.mana.colors)
        for option in ability.mana_options:
            for i, amount in enumerate(option[:5]):
                if amount:
                    identity.add(("W", "U", "B", "R", "G")[i])
        for effect in ability.effects:
            if effect.get("op") in ("add_mana", "add_mana_per"):
                for i, amount in enumerate(parse_mana_production(str(effect.get("mana", "")))[:5]):
                    if amount:
                        identity.add(("W", "U", "B", "R", "G")[i])
    return frozenset(identity)


def link_faces(cards: dict[str, CardDef]) -> None:
    """Point every back face at its front, and refuse a half-written link.

    The two faces of a transforming card are two ``CardDef``s and one
    ``GameObject``; ``GameState.card_of`` picks between them. That works only if
    the link is complete in both directions, so the *back* pointer is derived
    here rather than authored -- a card file that named a front face by hand
    could name a different one than the front names, and nothing would say so.

    A back face is never cast, drawn or shuffled into a deck. The guards that
    enforce that all ask ``front_face is not None``, so an unlinked back face
    would quietly become a playable card with no mana cost.
    """
    for card in cards.values():
        if card.back_face is None:
            continue
        back = cards.get(card.back_face)
        if back is None:
            raise DslError(f"{card.id}: back_face references unknown card {card.back_face!r}")
        if back.back_face is not None:
            # Two-faced, not three. A cycle here would make `card_of` a walk
            # rather than a lookup.
            raise DslError(f"{card.id}: back face {back.id!r} may not have a back face of its own")
        if back.front_face is not None and back.front_face != card.id:
            raise DslError(
                f"{back.id}: is the back face of both {back.front_face!r} and {card.id!r}"
            )
        cards[back.id] = dataclasses.replace(back, front_face=card.id)
    link_second_faces(cards)
    link_meld_results(cards)


def link_second_faces(cards: dict[str, CardDef]) -> None:
    """Point every second castable face at the card that prints it.

    The same derived back-link ``front_face`` is, in the same direction and for
    the same reason -- but what it guards is different. A back face is never
    *cast*; a second face is nothing but a cast, and the thing to keep it out of
    is a **deck**. The Adventure half of a card is not a card you can own.
    """
    for card in cards.values():
        if card.second_face is None:
            continue
        face = cards.get(card.second_face)
        if face is None:
            raise DslError(
                f"{card.id}: second_face references unknown card {card.second_face!r}"
            )
        if face.second_face is not None:
            # Two castable faces, not three -- `card_of` is a lookup, not a walk.
            raise DslError(
                f"{card.id}: second face {face.id!r} may not have a second face of its own"
            )
        if face.parent_face is not None and face.parent_face != card.id:
            raise DslError(
                f"{face.id}: is the second face of both {face.parent_face!r} and {card.id!r}"
            )
        if face.mana_cost.mana_value() == 0 and not face.is_land:
            # An unwritten `mana_cost` parses to the same empty cost a back face
            # has, so this is the guard against pointing `second_face` at one:
            # it would be a free spell stapled to a creature. No printed second
            # face costs {0}, and one that did would be indistinguishable here.
            #
            # A **land** half is the exception, and not a loophole: a land is
            # played rather than cast, so it has no mana cost to write and
            # costing nothing is not a discount -- it still spends the land drop.
            # Malakir Rebirth // Malakir Mire is the shape.
            raise DslError(f"{face.id}: a second castable face needs a mana cost of its own")
        # 715.1. Both halves, because each is silent alone: an Adventure that is
        # a permanent never reaches the exile that makes it an Adventure, and a
        # non-creature adventurer resolves out of that exile straight back to
        # the graveyard with the whole second half unreachable.
        if card.adventure:
            if not card.is_permanent:
                raise DslError(
                    f"{card.id}: an adventurer card must be a permanent -- it is cast "
                    f"from exile after the Adventure and has to stay somewhere"
                )
            if face.is_permanent:
                raise DslError(
                    f"{face.id}: an Adventure must be an instant or a sorcery (715.1); "
                    f"a permanent one never reaches the exile it is cast from"
                )
        # A fused spell runs both halves through one `EffectContext`, exactly as
        # a spliced card runs through its host's, so two targets named the same
        # thing would not merely be ambiguous -- one would silently answer for
        # the other and the spell would point somewhere nobody chose.
        if card.fuse:
            clash = {t.id for t in card.targets} & {t.id for t in face.targets}
            if clash:
                raise DslError(
                    f"{card.id}: the two fused halves both name target(s) "
                    f"{sorted(clash)} -- they resolve in one context and would collide"
                )
        cards[face.id] = dataclasses.replace(face, parent_face=card.id)


def link_meld_results(cards: dict[str, CardDef]) -> None:
    """Point every melded card back at the half that names it.

    701.37's result is an oversized card that exists only as something two
    permanents *become*, so it is kept out of decks the same way a back face
    and a second castable face are: with a derived back-link that the deck
    guard already tests. Reusing ``parent_face`` rather than inventing a third
    field, because the guard's question is the same one -- "is this a card
    anybody owns a copy of?" -- and three fields answering it would be three
    places to forget.
    """
    for card in cards.values():
        if card.melds_into is None or card.melds_with is None:
            continue
        if card.melds_with not in cards:
            raise DslError(
                f"{card.id}: melds_with references unknown card {card.melds_with!r}"
            )
        result = cards.get(card.melds_into)
        if result is None:
            raise DslError(
                f"{card.id}: melds_into references unknown card {card.melds_into!r}"
            )
        if result.parent_face is not None and result.parent_face != card.id:
            raise DslError(
                f"{result.id}: is claimed by both {result.parent_face!r} and {card.id!r}"
            )
        cards[result.id] = dataclasses.replace(result, parent_face=card.id)


def validate_token_references(cards: Mapping[str, CardDef]) -> None:
    """Every ``create_token`` must name a card id that exists and is a token."""
    for card in cards.values():
        for effect in _walk_effects(card):
            if effect.get("op") != "create_token":
                continue
            token_id = str(effect.get("token"))
            token = cards.get(token_id)
            if token is None:
                raise DslError(f"{card.id}: create_token references unknown card {token_id!r}")
            if not token.is_token:
                raise DslError(f"{card.id}: {token_id!r} is not marked as a token")


def _walk_effects(card: CardDef):
    def walk(effects):
        for effect in effects:
            yield effect
            for key in ("then", "else", "effects"):
                yield from walk(effect.get(key) or [])
            for mode in effect.get("modes", []) or []:
                yield from walk(mode.get("effects") or [])

    yield from walk(card.spell_effects)
    for ability in card.abilities:
        yield from walk(ability.effects)
