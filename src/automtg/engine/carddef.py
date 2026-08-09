"""Immutable card definitions.

One :class:`CardDef` exists per distinct card and is shared by every instance of
it in every game.  These objects are built by :mod:`automtg.cards.loader` from
JSON and are never mutated afterwards, so the engine can treat them as constants.

The effect bodies (``effects``, ``static``, selectors, conditions) stay as plain
dicts: they are *data* interpreted by :mod:`automtg.engine.effects`, and the
loader has already validated every key and op name against the registries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .enums import AbilityKind, CardType, Color, Keyword, Supertype, Zone
from .mana import ManaCost

#: Types whose subtypes contribute to Commander colour identity checks.
LAND_TYPE = CardType.LAND.value


@dataclass(frozen=True)
class TargetSpec:
    """A single target requirement of a spell or ability."""

    id: str
    kind: str  # "permanent" | "player" | "spell" | "card_in_graveyard" | "any"
    selector: Mapping[str, Any] = field(default_factory=dict)
    count: int = 1
    optional: bool = False


@dataclass(frozen=True)
class Cost:
    """The cost of an activated ability (or an additional cost of a spell)."""

    mana: ManaCost = field(default_factory=ManaCost)
    tap: bool = False
    untap: bool = False
    sacrifice: Mapping[str, Any] | None = None
    discard: int = 0
    pay_life: int = 0
    remove_counters: Mapping[str, Any] | None = None
    exile_from_graveyard: Mapping[str, Any] | None = None

    def is_tap_only(self) -> bool:
        """True when the only cost is ``{T}`` -- the shape mana sources must have."""
        return (
            self.tap
            and self.mana.is_free()
            and not self.untap
            and self.sacrifice is None
            and self.discard == 0
            and self.pay_life == 0
            and self.remove_counters is None
            and self.exile_from_graveyard is None
        )

    def describe(self) -> str:
        parts: list[str] = []
        if not self.mana.is_free():
            parts.append(str(self.mana))
        if self.tap:
            parts.append("{T}")
        if self.untap:
            parts.append("{Q}")
        if self.sacrifice:
            parts.append("Sacrifice")
        if self.discard:
            parts.append(f"Discard {self.discard}")
        if self.pay_life:
            parts.append(f"Pay {self.pay_life} life")
        if self.remove_counters:
            parts.append("Remove counters")
        if self.exile_from_graveyard:
            parts.append("Exile from graveyard")
        return ", ".join(parts) or "{0}"


@dataclass(frozen=True)
class TriggerSpec:
    """When a triggered ability fires."""

    event: str
    controller: str = "you"  # you | opponent | any
    source: str | None = None  # "self" restricts to this permanent
    filter: Mapping[str, Any] | None = None
    condition: Mapping[str, Any] | None = None  # intervening "if" clause
    #: Who is being attacked, for ``attacks``.  ``controller`` answers *whose
    #: creature* is attacking, which is a different question and not a
    #: substitute: in a pod, "whenever a creature attacks you" must not fire when
    #: one opponent swings at another.  ``you`` | ``opponent`` | ``any``.
    defending: str | None = None


@dataclass(frozen=True)
class Ability:
    """An activated, triggered or static ability printed on a card."""

    kind: AbilityKind
    index: int
    text: str = ""
    # activated
    cost: Cost | None = None
    is_mana_ability: bool = False
    mana_options: tuple[tuple[int, ...], ...] = ()
    sorcery_speed_only: bool = False
    # triggered
    trigger: TriggerSpec | None = None
    active_zones: tuple[Zone, ...] = (Zone.BATTLEFIELD,)
    # activated + triggered
    targets: tuple[TargetSpec, ...] = ()
    effects: tuple[Mapping[str, Any], ...] = ()
    # static
    static: Mapping[str, Any] | None = None

    @property
    def is_activated(self) -> bool:
        return self.kind is AbilityKind.ACTIVATED

    @property
    def is_triggered(self) -> bool:
        return self.kind is AbilityKind.TRIGGERED

    @property
    def is_static(self) -> bool:
        return self.kind is AbilityKind.STATIC


@dataclass(frozen=True)
class CardDef:
    """Everything printed on one card."""

    id: str
    name: str
    oracle_text: str = ""
    mana_cost: ManaCost = field(default_factory=ManaCost)
    supertypes: frozenset[str] = frozenset()
    types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    power: int | None = None
    toughness: int | None = None
    keywords: frozenset[str] = frozenset()
    colors: frozenset[str] = frozenset()
    color_identity: frozenset[str] = frozenset()
    targets: tuple[TargetSpec, ...] = ()
    spell_effects: tuple[Mapping[str, Any], ...] = ()
    replacements: tuple[Mapping[str, Any], ...] = ()
    abilities: tuple[Ability, ...] = ()
    type_line: str = ""
    is_token: bool = False

    # -- type predicates ----------------------------------------------------

    @property
    def is_land(self) -> bool:
        return CardType.LAND.value in self.types

    @property
    def is_creature(self) -> bool:
        return CardType.CREATURE.value in self.types

    @property
    def is_artifact(self) -> bool:
        return CardType.ARTIFACT.value in self.types

    @property
    def is_enchantment(self) -> bool:
        return CardType.ENCHANTMENT.value in self.types

    @property
    def is_instant(self) -> bool:
        return CardType.INSTANT.value in self.types

    @property
    def is_sorcery(self) -> bool:
        return CardType.SORCERY.value in self.types

    @property
    def is_permanent(self) -> bool:
        return not (self.is_instant or self.is_sorcery)

    @property
    def is_legendary(self) -> bool:
        return Supertype.LEGENDARY.value in self.supertypes

    @property
    def is_basic(self) -> bool:
        return Supertype.BASIC.value in self.supertypes

    @property
    def is_aura(self) -> bool:
        return self.is_enchantment and "Aura" in self.subtypes

    @property
    def is_equipment(self) -> bool:
        return self.is_artifact and "Equipment" in self.subtypes

    @property
    def mana_value(self) -> int:
        return self.mana_cost.mana_value()

    def has_keyword(self, keyword: Keyword | str) -> bool:
        value = keyword.value if isinstance(keyword, Keyword) else keyword
        return value in self.keywords

    def mana_abilities(self) -> tuple[Ability, ...]:
        return tuple(a for a in self.abilities if a.is_mana_ability)

    def color_set(self) -> frozenset[Color]:
        return frozenset(Color(c) for c in self.colors)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<CardDef {self.id}>"


def build_type_line(
    supertypes: frozenset[str], types: frozenset[str], subtypes: frozenset[str]
) -> str:
    """Render ``Legendary Creature - Vampire Knight`` in canonical printed order."""
    super_order = [s.value for s in Supertype if s.value in supertypes]
    type_order = [t.value for t in CardType if t.value in types]
    left = " ".join(super_order + type_order)
    if subtypes:
        return f"{left} - {' '.join(sorted(subtypes))}"
    return left
