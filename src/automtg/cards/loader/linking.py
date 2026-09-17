"""Post-load linking: faces, meld results, token references, colour identity."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

from automtg.engine.carddef import (
    Ability,
    CardDef,
)
from automtg.engine.errors import DslError
from automtg.engine.mana import ManaCost, parse_mana_production

from .walk import (
    _walk_effect_specs,
)


def _derive_color_identity(
    colors: frozenset[str], mana_cost: ManaCost, abilities: tuple[Ability, ...]
) -> frozenset[str]:
    """Colour identity = colours in the cost, plus colours in any mana symbol on the card."""
    identity = set(colors)
    for ability in abilities:
        if ability.cost is not None:
            identity.update(c.value for c in ability.cost.mana.colors)
        # `mana_chosen_color` carries the five-colour superset in `mana_options`
        # so the ability is recognisable as a mana source, but the card prints no
        # mana symbol at all -- Heraldic Banner's colour identity is colourless,
        # and reading the superset here would make it five-colour.
        for option in () if ability.mana_chosen_color else ability.mana_options:
            for i, amount in enumerate(option[:5]):
                if amount:
                    identity.add(("W", "U", "B", "R", "G")[i])
        for effect in ability.effects:
            # A `{"chosen_color_of": "self"}` mana names no symbol on the card,
            # so it contributes no colour identity -- which is the printed
            # answer: Heraldic Banner's identity is colourless.
            if effect.get("op") in ("add_mana", "add_mana_per") and not isinstance(
                effect.get("mana"), Mapping
            ):
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
    link_prepared_faces(cards)
    link_meld_results(cards)


def link_prepared_faces(cards: dict[str, CardDef]) -> None:
    """Check every ``prepared_face`` points at a real spell, and only at one.

    The same derived back-link `link_second_faces` writes, reusing
    ``parent_face`` for the reason that one reuses it: what it guards is a
    **deck**. This entry is Emeritus's spell half and not a card anybody owns --
    the physical card is one card -- so leaving it deck-legal would let a player
    shuffle in a Demonic Tutor that has no printing of its own here.

    That it is *copied* rather than moved does not change the question. The copy
    is a token and vanishes on its own (111.7); the entry it copies is still a
    face.

    Two ways the pointer can be wrong and say nothing are refused outright:
    naming a card that is not there, and naming a **permanent**, which would put
    a creature on the stack as a spell that never leaves it.
    """
    for card in cards.values():
        if card.prepared_face is None:
            continue
        face = cards.get(card.prepared_face)
        if face is None:
            raise DslError(
                f"{card.id}: prepared_face references unknown card {card.prepared_face!r}"
            )
        if face.is_permanent:
            raise DslError(
                f"{card.id}: prepared_face {face.id!r} is a permanent -- "
                f"'a copy of its spell' is an instant or a sorcery"
            )
        if face.parent_face is not None and face.parent_face != card.id:
            raise DslError(
                f"{face.id}: is the spell face of both {face.parent_face!r} and {card.id!r}"
            )
        cards[face.id] = dataclasses.replace(face, parent_face=card.id)


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
            raise DslError(f"{card.id}: second_face references unknown card {card.second_face!r}")
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
            raise DslError(f"{card.id}: melds_with references unknown card {card.melds_with!r}")
        result = cards.get(card.melds_into)
        if result is None:
            raise DslError(f"{card.id}: melds_into references unknown card {card.melds_into!r}")
        if result.parent_face is not None and result.parent_face != card.id:
            raise DslError(
                f"{result.id}: is claimed by both {result.parent_face!r} and {card.id!r}"
            )
        cards[result.id] = dataclasses.replace(result, parent_face=card.id)


def validate_token_references(cards: Mapping[str, CardDef]) -> None:
    """Every ``create_token`` must name a card id that exists and is a token.

    ``create_instead`` on a `replace_token_creation` static is checked by the
    same rule and in the same place: it names token ids that
    `primitives.create_token` will put onto the battlefield, so an id that is
    missing or is a real card fails identically -- and it must fail *here*
    rather than at the moment somebody plays a Treasure into a Divine
    Visitation, which is a game already in progress.
    """

    def check(card: CardDef, token_id: str, where: str) -> None:
        token = cards.get(token_id)
        if token is None:
            raise DslError(f"{card.id}: {where} references unknown card {token_id!r}")
        if not token.is_token:
            raise DslError(f"{card.id}: {token_id!r} is not marked as a token")

    for card in cards.values():
        for effect in _walk_effects(card):
            if effect.get("op") == "create_token":
                check(card, str(effect.get("token")), "create_token")
                if "attached_to" in effect and not cards[str(effect.get("token"))].is_aura:
                    # Only an Aura is attached by `op_create_token`; anything
                    # else would be created and hang on nothing.
                    raise DslError(
                        f"{card.id}: create_token 'attached_to' needs an Aura token, "
                        f"and {effect.get('token')!r} is not one"
                    )
        for ability in card.abilities:
            static = ability.static or {}
            for token_id in static.get("create_instead", ()):
                check(card, str(token_id), "create_instead")


def _walk_effects(card: CardDef):
    yield from _walk_effect_specs(card.spell_effects)
    for ability in card.abilities:
        yield from _walk_effect_specs(ability.effects)
    # A quoted ability the card hands to something else makes tokens too --
    # Not Dead After All's Wicked Role is created by the creature it granted
    # the death trigger to -- and an unknown id there crashes mid-game instead.
    for ability in card.grantable_abilities:
        yield from _walk_effect_specs(ability.effects)
    for emblem in card.emblems:
        for ability in emblem.abilities:
            yield from _walk_effect_specs(ability.effects)
