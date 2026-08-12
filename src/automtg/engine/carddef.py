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
from dataclasses import dataclass, field, replace
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
    #: "Return a land you control to its owner's hand": a selector over the
    #: battlefield. Distinct from ``sacrifice`` because the permanent comes
    #: back -- Meloku and Trench Behemoth both replay it for landfall.
    return_to_hand: Mapping[str, Any] | None = None
    #: "Tap five untapped Vampires you control": a selector over the
    #: battlefield with a ``count``.  Distinct from ``tap``, which is the
    #: ``{T}`` symbol and only ever taps the source, and from ``sacrifice`` and
    #: ``return_to_hand``, because the permanents stay where they are and untap
    #: on the next untap step -- so a cost of this shape is repeatable in a way
    #: neither of those is.
    tap_permanents: Mapping[str, Any] | None = None
    discard: int = 0
    #: "…by discarding a **land** card": narrows what ``discard`` may take.
    discard_selector: Mapping[str, Any] | None = None
    #: Cycling's "**Discard this card**": the source discards *itself*, with no
    #: choice about which card goes. Deliberately not ``discard: 1`` narrowed by
    #: a selector -- ``_discard_pool`` offers the whole hand and ``ask_objects``
    #: lets the player pick, so a Krosan Tusker could be "cycled" by pitching
    #: something else and staying in hand.
    discard_self: bool = False
    pay_life: int = 0
    remove_counters: Mapping[str, Any] | None = None
    exile_from_graveyard: Mapping[str, Any] | None = None

    @staticmethod
    def from_spec(spec: Mapping[str, Any] | None) -> Cost | None:
        """Build a ``Cost`` from a raw effect-body mapping.

        Effect bodies stay as plain dicts (see the module docstring), so the
        ``pay`` on an optional effect -- Seer's Sundial's "you may pay {2}" --
        arrives here rather than through the loader's ``CostModel``.  Both go
        through this one constructor so the two spellings cannot drift; the
        loader validates the *keys* against ``CostModel`` at load time, which is
        what makes a typo a load error rather than a cost silently dropped.
        """
        if spec is None:
            return None
        return Cost(
            mana=ManaCost.parse(spec.get("mana")),
            tap=bool(spec.get("tap", False)),
            untap=bool(spec.get("untap", False)),
            sacrifice=dict(spec["sacrifice"]) if spec.get("sacrifice") else None,
            return_to_hand=(
                dict(spec["return_to_hand"]) if spec.get("return_to_hand") else None
            ),
            tap_permanents=(
                dict(spec["tap_permanents"]) if spec.get("tap_permanents") else None
            ),
            discard=int(spec.get("discard", 0) or 0),
            discard_selector=(
                dict(spec["discard_selector"]) if spec.get("discard_selector") else None
            ),
            discard_self=bool(spec.get("discard_self", False)),
            pay_life=int(spec.get("pay_life", 0) or 0),
            remove_counters=(
                dict(spec["remove_counters"]) if spec.get("remove_counters") else None
            ),
            exile_from_graveyard=(
                dict(spec["exile_from_graveyard"]) if spec.get("exile_from_graveyard") else None
            ),
        )

    def without_mana(self) -> Cost:
        """This cost with its mana removed -- the *additional* half.

        Flashback's mana replaces the printed cost and everything else is paid
        on top, the way `retrace_cost` is, so the two halves are charged at
        different moments and legality has to test them separately.
        """
        return replace(self, mana=ManaCost.parse(""))

    def is_tap_only(self) -> bool:
        """True when the only cost is ``{T}`` -- the shape mana sources must have."""
        return (
            self.tap
            and self.mana.is_free()
            and not self.untap
            and self.sacrifice is None
            and self.return_to_hand is None
            and self.tap_permanents is None
            and self.discard == 0
            and not self.discard_self
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
        if self.return_to_hand:
            parts.append("Return to hand")
        if self.tap_permanents:
            parts.append(f"Tap {self.tap_permanents.get('count', 1)} untapped permanents")
        if self.discard:
            parts.append(f"Discard {self.discard}")
        if self.discard_self:
            parts.append("Discard this card")
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
    #: A zone-change ``cause`` this trigger refuses to fire on -- the loop guard
    #: behind "if it wasn't put onto the battlefield with this ability".
    not_cause: str | None = None
    #: Which counter kind a ``counter_placed`` trigger cares about.  The event
    #: has always carried it; nothing read it, so every such trigger fired on
    #: every kind.  Fathom Mage is the witness.
    counter: str | None = None


def count_mode_specs(effects: Any) -> int:
    """How many ``choose_mode`` ops appear anywhere in an effect tree.

    Cast-time mode selection pre-answers *the* modal question a spell asks, and
    that is only well defined when it asks exactly one.  Counting the whole tree
    -- rather than trusting the first top-level op to be the only one -- makes
    the rule mechanical instead of an argument about document order.
    """
    if isinstance(effects, Mapping):
        total = 1 if effects.get("op") == "choose_mode" else 0
        return total + sum(count_mode_specs(v) for v in effects.values())
    if isinstance(effects, (list, tuple)):
        return sum(count_mode_specs(item) for item in effects)
    return 0


def top_level_mode_spec(effects: Any) -> Mapping[str, Any] | None:
    """The first ``choose_mode`` at the top level of ``effects``, if any."""
    for spec in effects or ():
        if isinstance(spec, Mapping) and spec.get("op") == "choose_mode":
            return spec
    return None


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
    #: "Add {G} for each +1/+1 counter on this creature."  A value expression
    #: evaluated **when the ability is activated**, multiplying the single
    #: option in ``mana_options``.  ``None`` means the ordinary fixed output.
    #:
    #: It cannot be folded into ``mana_options`` at load time, which is the
    #: whole difficulty: those tuples are constants, and this one is a question
    #: about the board.
    mana_amount: Mapping[str, Any] | None = None
    #: "Spend this mana only to cast a creature spell" -- the card type the mana
    #: may pay for, lowercased.  ``None`` is ordinary mana.
    mana_restriction: str | None = None
    sorcery_speed_only: bool = False
    #: This ability is cycling, so activating it emits ``EventType.CYCLED``.
    is_cycling: bool = False
    # triggered
    trigger: TriggerSpec | None = None
    active_zones: tuple[Zone, ...] = (Zone.BATTLEFIELD,)
    # activated + triggered
    targets: tuple[TargetSpec, ...] = ()
    effects: tuple[Mapping[str, Any], ...] = ()
    # static
    static: Mapping[str, Any] | None = None

    @property
    def cast_time_modes(self) -> Mapping[str, Any] | None:
        """The ``choose_mode`` to ask about on activation, or ``None``.

        Only for an *activated* ability, and only when the ability's whole
        effect tree contains exactly one ``choose_mode`` at its top level. A
        triggered ability has no activation to ask at, and a nested or repeated
        one keeps asking as it resolves.
        """
        if not self.is_activated or count_mode_specs(self.effects) != 1:
            return None
        return top_level_mode_spec(self.effects)

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
    #: Abilities this card can *hand to something else* -- the quoted text in
    #: `gains trample and "Whenever this creature deals combat damage to a
    #: player, draw a card"`.  Kept apart from `abilities` because the card does
    #: not have them: they only exist on whatever it granted them to.
    grantable_abilities: tuple[Ability, ...] = ()
    type_line: str = ""
    is_token: bool = False
    #: "This spell can't be countered."  A printed property of the card
    #: rather than a granted one, read by the `counter` op -- a spell is on
    #: the stack, where static abilities do not reach it.
    uncounterable: bool = False
    #: "Kicker {1}{U}" -- an additional cost the caster may choose to pay.  It is
    #: not folded into `mana_cost` because mana value must stay what is printed,
    #: and because the choice is the mechanic: legality offers the spell twice.
    kicker: ManaCost | None = None
    #: "Evoke {2}{U}" -- an alternative cost that *replaces* the printed one.
    #: Subtractive where ``kicker`` is additive, and like it kept out of
    #: ``mana_cost`` so mana value stays what is printed: an evoked
    #: Mulldrifter is still a five-drop to anything that counts.
    evoke: ManaCost | None = None
    #: "Emerge {5}{U}{U}".  An alternative cost paid by sacrificing a
    #: creature, reduced by that creature's mana value.  The reduction is
    #: generic-only and clamped at zero, like every other cost reduction
    #: here: it never reaches the coloured pips however large the sacrifice.
    emerge: ManaCost | None = None
    #: "This spell costs {X} less to cast."  See `costs.cost_reduction`.
    cost_reduction: Mapping[str, Any] | None = None
    #: Retrace: castable from the graveyard for its cost plus a discarded land.
    retrace: bool = False
    #: Ascend. Deliberately *not* a `Keyword`: the enum's members are
    #: read by `grant_keyword` and the evasion checks off derived
    #: characteristics, and Ascend is neither granted nor evasive --
    #: it is a state trigger watching a permanent count.
    ascend: bool = False
    #: "Flashback {1}{U}, Pay 3 life" -- an alternative cost offered only for a
    #: copy in the owner's *graveyard*, replacing the printed mana cost.
    #:
    #: A full `Cost` rather than a `ManaCost` like ``evoke``, because Deep
    #: Analysis charges life as well: the mana half replaces the printed cost
    #: and everything else is an additional cost paid after it, exactly as
    #: `retrace_cost` is.
    #:
    #: Once-only, and that is enforced elsewhere: a spell cast this way is
    #: exiled rather than put into a graveyard when it finishes, so it cannot be
    #: flashed back twice.
    flashback: Cost | None = None
    #: Suspend: ``(cost, counters)``, or ``None``.  See `engine/suspend.py`.
    suspend: tuple[ManaCost, int] | None = None

    @property
    def cast_time_modes(self) -> Mapping[str, Any] | None:
        """The ``choose_mode`` to ask about on cast, or ``None``.

        Rule 601.2b puts mode selection at cast time.  Only honoured when the
        spell's whole effect tree holds exactly one ``choose_mode`` and it sits
        at the top level: a nested one ("choose one -- ... ; then choose one
        --") is a second question that genuinely belongs to resolution, and
        pre-answering it would bind the wrong one.
        """
        if count_mode_specs(self.spell_effects) != 1:
            return None
        return top_level_mode_spec(self.spell_effects)

    @property
    def retrace_cost(self) -> Cost:
        """The additional cost of casting this from the graveyard."""
        return Cost(discard=1, discard_selector={"types": ["Land"]})

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
