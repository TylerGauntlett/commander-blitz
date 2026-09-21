"""Text-changing effects: layer 3 (613.1c), for creature types.

"Change the text of that creature by replacing all instances of one creature
type with Vampire." New Blood -- and Artificial Evolution, which is the same
sentence with both halves chosen.

The engine had no layer 3 at all: `characteristics._compute` went straight from
copy effects to the type-granting statics, and nothing anywhere rewrote a word
inside another object's rules text. This module is that layer, and it is
deliberately **only** the creature-type word class. The other two the family
prints -- colour words (Glamerdye, Mind Bend, Sleight of Mind, and seven more)
and basic land types (Magical Hack, Whim of Volrath) -- are refused at load
time rather than half-done, because a colour word reaches `colors` filters,
protection qualities and mana, and a land type reaches landwalk keywords and
mana abilities. Each is its own surface with its own way of going quietly wrong.

## What "all instances" reaches, and why that is exactly two places

A creature type appears in exactly two kinds of place, and both are read off the
object rather than computed from another layer, so this can be a pipeline
*input* like a counter or a tapped flag -- no layer can come to depend on
another's output through it.

1. **The subtype line.** Handled by `apply_to_subtypes`, called from `_compute`
   (so `chars()` reports the new line) and from `_matches`, which feeds the
   object's printed subtypes to a *static filter* belonging to some other card.
   Both are needed and neither implies the other: `chars` is what a rules query
   asks, and `_matches_printed` is the path a Vampire lord's anthem takes. Miss
   the second and New Blood converts a creature that no lord can see, which is
   most of the card.

2. **Every `subtypes` list inside the object's own abilities.** Handled by
   `substitute` walking the compiled ability, called from `abilities_of`. This
   is the half that turns a stolen Goblin lord into a Vampire lord: "other
   Goblins you control get +1/+0" has to *become* "other Vampires…", and the
   selector that says so is a `subtypes` list nested somewhere inside a
   `TriggerSpec` filter, a `static`'s `affects`, an effect's `objects`, a
   target's selector or a value's count.

The key name `"subtypes"` is the whole surface for this word class, which is why
the walk keys on it rather than trying to recognise type names as strings. A
walk that substituted any string equal to "Goblin" would rewrite a token's name,
a binding label or a mode's prompt; a walk that missed a nesting level would
leave the stolen lord pumping its old tribe. Both failures are silent, so the
rule here is narrow and total: every `subtypes` list, wherever it is nested,
and nothing else.

Note that this deliberately **does** reach `create_token` and `add_subtype`
specs. 612.1 changes the text, and a token-making line that reads "create a 1/1
Goblin" is text; after the change it makes Vampires. That is the printed
consequence, not an overreach.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .carddef import Ability, CardDef
    from .state import GameState

#: The ability fields that can hold a spec with a ``subtypes`` list in it.
#:
#: Named rather than discovered by walking every field, because most of an
#: `Ability` is scalars and enums that a recursive walk would have to skip
#: anyway -- and because an ability field added later that can carry a selector
#: should fail loudly here (a card whose new field is not substituted keeps its
#: old tribe) rather than be silently missed by a `dataclasses.fields` loop that
#: looks like it covers everything.
ABILITY_SPEC_FIELDS = (
    "cost",
    "mana_amount",
    "mana_rider",
    "mana_reflects",
    "mana_colors_of",
    "mana_each_color_among",
    "mana_restriction",
    "activation_condition",
    "trigger",
    "targets",
    "mode_targets",
    "effects",
    "static",
)


def apply_to_subtypes(subtypes: set[str], changes: Sequence[tuple[str, str]]) -> set[str]:
    """The subtype line with each text change applied, in order.

    In order, and not as one simultaneous mapping: 612.4 applies text changes in
    timestamp order, so a Goblin changed to Vampire and then Vampire to Zombie
    is a Zombie. Folding them into a single dict would make the second change
    read the *printed* line and miss what the first one did.
    """
    if not changes:
        return subtypes
    out = set(subtypes)
    for old, new in changes:
        if old in out:
            out.discard(old)
            out.add(new)
    return out


def substitute(value: Any, changes: Sequence[tuple[str, str]]) -> Any:
    """``value`` with every ``subtypes`` list rewritten, however deeply nested.

    Structure-preserving: mappings come back as plain dicts, lists as lists and
    tuples as tuples, so a spec that was hashable stays hashable and a selector
    that was a Mapping stays one. Anything that is not a container is returned
    unchanged -- including strings, which is what stops the walk from rewriting
    a token name or a prompt that happens to read "Goblin".
    """
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key == "subtypes" and isinstance(item, Sequence) and not isinstance(item, str):
                out[key] = [_swap(entry, changes) for entry in item]
            else:
                out[key] = substitute(item, changes)
        return out
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return tuple(substitute(item, changes) for item in value)
    if isinstance(value, list):
        return [substitute(item, changes) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        replacements = {
            f.name: substitute(getattr(value, f.name), changes)
            for f in dataclasses.fields(value)
        }
        return dataclasses.replace(value, **replacements)
    return value


def _swap(entry: Any, changes: Sequence[tuple[str, str]]) -> Any:
    """One entry of a ``subtypes`` list, put through the changes in order.

    Entries are not always plain names: ``{"chosen_type_of": "self"}`` is a
    filter that resolves to a type at match time. Those pass through untouched,
    which is right -- the word is not in this object's text, it is a reference
    to a choice made elsewhere, and there is no instance of anything to replace.
    """
    if not isinstance(entry, str):
        return substitute(entry, changes)
    out = entry
    for old, new in changes:
        if out == old:
            out = new
    return out


def apply_to_ability(ability: Ability, changes: Sequence[tuple[str, str]]) -> Ability:
    """One compiled ability with the changes applied to every spec it carries."""
    if not changes:
        return ability
    patch = {
        name: substitute(getattr(ability, name), changes) for name in ABILITY_SPEC_FIELDS
    }
    return dataclasses.replace(ability, **patch)


def printed_type_instances(state: GameState, card: CardDef) -> set[str]:
    """Every creature type with an *instance* in this card's printed text.

    The subtype line plus every `subtypes` list in the printed abilities, which
    is the same surface `substitute` rewrites -- so the prompt offers exactly
    the choices that would change something.

    The rules let a player name **any** creature type (612.1), and this narrows
    to the ones with instances. That is observationally identical: naming a type
    the object's text never mentions replaces nothing, so the option removed is
    the option that does nothing. What it buys is a prompt of two or three real
    choices instead of the 400-entry list `choose_type` has to cap, on a card
    where the whole decision is *which of this creature's words* to rewrite.
    """
    found: set[str] = set(card.subtypes)
    for ability in card.abilities:
        for name in ABILITY_SPEC_FIELDS:
            _collect(getattr(ability, name), found)
    return {t for t in found if t in state.registry.creature_types()}


def _collect(value: Any, found: set[str]) -> None:
    """Every literal name in every nested ``subtypes`` list."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "subtypes" and isinstance(item, Sequence) and not isinstance(item, str):
                found.update(entry for entry in item if isinstance(entry, str))
            else:
                _collect(item, found)
        return
    if isinstance(value, str):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, found)
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            _collect(getattr(value, f.name), found)



def displayed(text: str, changes):
    """``text`` with the changed types rewritten, for the screen.

    The rules half of a text change is the specs the two functions above
    rewrite; this is the half a player reads. Without it a stolen lord is drawn
    with its printed line -- "other Goblins you control get +1/+0" -- while it
    is in fact pumping Vampires, and the type line under its art disagrees with
    the `subtypes` sent in the same payload. Nothing would be *wrong*, and the
    board would be unreadable to anyone who believed it.

    Whole words, and the simple plural with them, because that is how the word
    appears in printed text: "Goblins you control" and "another Goblin". The
    word boundary is what keeps the rewrite off a longer word that merely
    contains the type.

    Display only. Nothing reads the string back -- the rules all run off the
    structural walk above -- so an imperfect rewrite here costs legibility
    rather than correctness, which is the whole reason this one may be a regex.
    """
    out = text
    for old, new in changes:
        out = re.sub(r"\b" + re.escape(old) + r"s\b", new + "s", out)
        out = re.sub(r"\b" + re.escape(old) + r"\b", new, out)
    return out
