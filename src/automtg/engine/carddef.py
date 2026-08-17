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
    #: A number, or ``"any"`` for "any number of target …" -- a size the caster
    #: chooses. At most one spec per card may be ``"any"``, and it must be the
    #: last, because `filter_legal` slices the stored refs spec by spec and a
    #: variable-size spec in the middle would make the split ambiguous.
    count: int | str = 1
    #: At most one chosen object per controller -- "for each player, up to one
    #: target permanent that player controls". Only meaningful with
    #: ``count == "any"``.
    one_per_player: bool = False
    optional: bool = False


#: What a **bestowed** spell targets, fixed by rule 702.103a rather than by the
#: card: "it's an Aura spell with **enchant creature**". Every other alternative
#: cost in the engine changes only the price; this is the one place a cast
#: variant brings its own target list, and the list is the rules' -- which is why
#: no bestow card writes one and none may.
#:
#: It lives here rather than in `legality` beside `MORPH_COST` because both
#: `legality` and `stack` need it, and `stack` may not import `legality`.
BESTOW_TARGET = TargetSpec(
    id="bestow",
    kind="permanent",
    selector={"zone": "battlefield", "types": ["Creature"]},
)


#: What a **mutating** spell targets, fixed by rule 702.140a: "target non-Human
#: creature you own". Tokens are excluded because a merged permanent is a *pile
#: of cards* and a token is not one -- there would be nothing to put underneath
#: and nothing to come back when the pile is broken up.
MUTATE_TARGET = TargetSpec(
    id="mutate",
    kind="permanent",
    selector={
        "zone": "battlefield",
        "controller": "you",
        "types": ["Creature"],
        "not_subtypes": ["Human"],
        "is_token": False,
    },
)


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
    #: An integer, or a value expression evaluated at payment time -- see
    #: `costs.life_cost`, which both `can_pay` and `pay` go through so the two
    #: cannot price the same cost differently.
    pay_life: int | Mapping[str, Any] = 0
    remove_counters: Mapping[str, Any] | None = None
    #: A loyalty cost (606.2), signed. `None` rather than `0` for "no loyalty
    #: cost", because `0:` is a real and different thing -- a printed zero
    #: ability still counts as the one loyalty ability that turn.
    loyalty: int | None = None
    exile_from_graveyard: Mapping[str, Any] | None = None
    #: How much less **this cost node** costs -- `{"count": filter}`,
    #: `{"total_power": filter}` or a flat `{"amount": N}`, any of them optionally
    #: gated on a `condition`. One language, in `costs.reduction_amount`, shared
    #: with the card-level `cost_reduction` so "for each" and "if" cannot drift.
    #:
    #: On an activated ability's cost: "This ability costs {1} less to activate
    #: for each Vampire you control", and Crown of Gondor's "{3} less to activate
    #: if you're the monarch". Applied by `costs.ability_mana`, which both
    #: `can_pay` and `pay` call so an ability offered at the reduced price is also
    #: paid at it.
    #:
    #: On `flashback` -- the one alternative cost that is a full `Cost` -- it is
    #: "this spell costs {X} less to cast **this way**", applied by
    #: `costs.variant_reduction` on the flashback branch alone, which is what
    #: keeps it off the printed hand cast.
    mana_reduction: Mapping[str, Any] | None = None

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
            pay_life=(
                dict(spec["pay_life"])
                if isinstance(spec.get("pay_life"), Mapping)
                else int(spec.get("pay_life", 0) or 0)
            ),
            remove_counters=(
                dict(spec["remove_counters"]) if spec.get("remove_counters") else None
            ),
            # `is not None`, not truthiness: `0:` is a printed loyalty cost and
            # a falsy one, and reading it as "no loyalty cost" would make a zero
            # ability free to use twice in a turn.
            loyalty=(
                int(spec["loyalty"]) if spec.get("loyalty") is not None else None
            ),
            exile_from_graveyard=(
                dict(spec["exile_from_graveyard"]) if spec.get("exile_from_graveyard") else None
            ),
            mana_reduction=(
                dict(spec["mana_reduction"]) if spec.get("mana_reduction") else None
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
            and not self.pay_life
            and self.remove_counters is None
            and self.loyalty is None
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
            amount = self.pay_life if isinstance(self.pay_life, int) else "X"
            parts.append(f"Pay {amount} life")
        if self.remove_counters:
            parts.append("Remove counters")
        if self.loyalty is not None:
            parts.append(f"{self.loyalty:+d}")
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
    #: ``ability_activated`` only: "…**if it isn't a mana ability**".  ``False``
    #: means only non-mana activations fire it, ``True`` only mana ones, and
    #: ``None`` is every activation.
    #:
    #: A restriction rather than a ``condition`` because no condition key can
    #: reach it: they ask about the board or about the trigger's own card, and
    #: this asks which *kind* of ability was used.  ``filter`` cannot reach it
    #: either -- it reads the source permanent's printed face, and the
    #: permanents this clause exists for are exactly the ones with both kinds on
    #: them (a fetchland's sacrifice ability and its mana tap; a Signet).
    mana_ability: bool | None = None
    #: "This ability triggers only once each turn." A cap on how many times this
    #: ability may *queue* in one turn, counted per permanent.
    #:
    #: It also stands in for "whenever **one or more** creatures enter" on every
    #: printed card carrying both clauses -- and both cards that asked for this
    #: carry both. Two tokens entering together queue the ability twice and the
    #: cap drops the second, which is the answer batching the events would give.
    #: A card printing "one or more" *without* a per-turn cap would still be
    #: wrong, and is still a gap.
    max_per_turn: int | None = None


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
    #: "…This land deals 1 damage to you."  The non-mana half of a painland or a
    #: Talisman, run by ``activate_mana_ability`` right after the mana is added.
    #:
    #: Held apart from ``effects`` rather than discovered there, because the two
    #: halves answer to different code: ``mana_options`` is a constant derived
    #: from the ``add_mana`` part alone and the solver reads it while planning a
    #: payment, whereas the rider is a real effect that must not run until the
    #: ability actually resolves.  Mixing them would either make the solver
    #: think a painland produces damage or make the damage never happen.
    mana_rider: tuple[Mapping[str, Any], ...] = ()
    #: "Add one mana of any color that a land an opponent controls could
    #: produce." Exotic Orchard. A selector over permanents whose own mana
    #: abilities decide which colours this one offers -- so the options are a
    #: question about the board rather than a constant on the card, which is
    #: what every other mana ability's `mana_options` is.
    #:
    #: `mana_options` still holds the five colours as a static superset, so the
    #: ability is recognisable as a mana source at load time; the narrowing to
    #: what the board actually offers happens in `costs.mana_options_of`, which
    #: both the payment solver and the activation read.
    mana_reflects: Mapping[str, Any] | None = None
    #: "…any color in your commander's color identity." The colours are a
    #: question about the command zone, asked when the ability is activated;
    #: `mana_options` holds the five-colour superset until then.
    mana_identity: bool = False
    #: "Spend this mana only to cast a creature spell" -- the card type the mana
    #: may pay for, lowercased.  ``None`` is ordinary mana.
    mana_restriction: str | None = None
    sorcery_speed_only: bool = False
    #: "Activate only if you control five or more Vampires." An *activation
    #: restriction*, checked by `legality` before the ability is offered, and
    #: re-checked nowhere else: rule 602.5c makes it a legality question, not a
    #: resolution one, so an ability that was legal when activated still
    #: resolves if the board changes underneath it.
    #:
    #: Deliberately not `sorcery_speed_only` with extra steps -- that is a
    #: timing restriction and this is a board one, and a card can print both.
    activation_condition: Mapping[str, Any] | None = None
    #: This ability is cycling, so activating it emits ``EventType.CYCLED``.
    is_cycling: bool = False
    # triggered
    trigger: TriggerSpec | None = None
    active_zones: tuple[Zone, ...] = (Zone.BATTLEFIELD,)
    #: Forecast: which steps this ability may be activated in, empty for any.
    activate_steps: tuple[str, ...] = ()
    #: Forecast: "only once each turn", counted per (object, ability index).
    once_each_turn: bool = False
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
    #: Starting loyalty. Kept as a characteristic as well as compiled into a
    #: replacement, because the client shows it on the card in hand where no
    #: object exists to carry counters yet.
    loyalty: int | None = None
    abilities: tuple[Ability, ...] = ()
    #: Abilities this card can *hand to something else* -- the quoted text in
    #: `gains trample and "Whenever this creature deals combat damage to a
    #: player, draw a card"`.  Kept apart from `abilities` because the card does
    #: not have them: they only exist on whatever it granted them to.
    grantable_abilities: tuple[Ability, ...] = ()
    type_line: str = ""
    is_token: bool = False
    #: The id of this card's back face -- a transforming double-faced card.
    #: The two faces are two ``CardDef``s and one ``GameObject``: ``transformed``
    #: on the object decides which one ``GameState.card_of`` returns, so every
    #: reader of a card's characteristics gets the right face with no changes at
    #: all. See ``docs/card-dsl.md``.
    back_face: str | None = None
    #: Set by the registry on the *back* face, naming the front. A back face is
    #: not a card anybody may cast, draw or put in a deck, and this is what the
    #: guards test. Derived rather than authored so the link cannot be written
    #: in one direction only.
    front_face: str | None = None
    #: The id of this card's **second castable face** -- adventure, aftermath,
    #: and the other half of a split card. Two ``CardDef``s and one
    #: ``GameObject``, exactly as ``back_face`` is; what differs is that this
    #: one is *cast*, so ``showing_second_face`` on the object is set as the
    #: spell goes on the stack rather than by anything on the battlefield.
    second_face: str | None = None
    #: Which zone the second face may be cast from -- ``"hand"`` for a split
    #: half or an Adventure, ``"graveyard"`` for aftermath.
    second_face_zone: str = "hand"
    #: **Adventure**: the card is exiled as the second face resolves, and the
    #: *front* face may then be cast from exile. The flag that separates
    #: adventure from the other two users of ``second_face``.
    adventure: bool = False
    #: **Fuse** (702.102a): a third cast line that is both halves at once -- both
    #: costs, both target lists, both effect lists, one spell.
    fuse: bool = False
    #: Set by the registry on the *second* face, naming the card it belongs to.
    #: A second face is not a card anybody may draw or put in a deck on its own,
    #: and it is castable only as part of the card that prints it -- the same
    #: derived back-link, in the same direction, that ``front_face`` is.
    parent_face: str | None = None
    #: "This spell can't be countered."  A printed property of the card
    #: rather than a granted one, read by the `counter` op -- a spell is on
    #: the stack, where static abilities do not reach it.
    uncounterable: bool = False
    #: Split second: read off the stack by `legality.split_second_active`.
    split_second: bool = False
    #: Buyback: a kicked spell returns to its owner's hand instead of the
    #: graveyard when it finishes resolving.
    buyback: bool = False
    #: **Rebound** (702.87a). The third rider on the destination a resolving
    #: spell goes to, beside flashback's exile and buyback's hand, and like both
    #: it only ever replaces the *graveyard*. The free cast at the next upkeep
    #: is `suspend.rebound_tick`, which shares `cast_for_free` with suspend
    #: because it is the same sentence.
    rebound: bool = False
    #: **Overload**. A third cast variant, and the only one that changes what
    #: the spell *targets* rather than what it costs: an overloaded spell is put
    #: on the stack with no targets at all, and the card branches on
    #: `{"overloaded": true}`.
    overload: ManaCost | None = None
    #: An additional cost paid at cast time -- casualty, replicate, Deadly
    #: Dispute. A full `Cost`, where `kicker` is mana-only, and offered as one
    #: cast line per number of times paid.
    additional_cost: Cost | None = None
    additional_optional: bool = False
    additional_repeatable: bool = False
    #: What the kicker is called on screen -- "kicked", "buyback".
    kicker_label: str = "kicked"
    #: "Kicker {1}{U}" -- an additional cost the caster may choose to pay.  It is
    #: not folded into `mana_cost` because mana value must stay what is printed,
    #: and because the choice is the mechanic: legality offers the spell twice.
    kicker: ManaCost | None = None
    #: "Evoke {2}{U}" -- an alternative cost that *replaces* the printed one.
    #: Subtractive where ``kicker`` is additive, and like it kept out of
    #: ``mana_cost`` so mana value stays what is printed: an evoked
    #: Mulldrifter is still a five-drop to anything that counts.
    evoke: ManaCost | None = None
    #: **Bestow** (702.103a). An alternative cost like ``evoke``, and the only
    #: one that changes what the spell *targets*: "enchant creature" is fixed by
    #: the rule, so `legality.BESTOW_TARGET` supplies it and no card writes one.
    bestow: ManaCost | None = None
    #: **Mutate** (702.140a). An alternative cost like ``bestow``, and like it
    #: the target comes from `MUTATE_TARGET` rather than from the card.
    mutate: ManaCost | None = None
    #: **Meld** (701.37): the card this one melds with, and the single oversized
    #: card the two become. Read by the `meld` op; the melded entry is linked
    #: back through ``parent_face`` so no deck may contain it.
    melds_with: str | None = None
    melds_into: str | None = None
    #: What that cost is called on the card -- "evoked", "dash", "blitz".
    evoke_label: str = "evoked"
    #: Prowl and spectacle: an alternative mana cost offered from hand only
    #: *while* ``alternative_condition`` holds.
    alternative_cost: ManaCost | None = None
    #: The condition gating it, in the ordinary `if`-effect language.
    alternative_condition: Any = None
    #: "Emerge {5}{U}{U}".  An alternative cost paid by sacrificing a
    #: creature, reduced by that creature's mana value.  The reduction is
    #: generic-only and clamped at zero, like every other cost reduction
    #: here: it never reaches the coloured pips however large the sacrifice.
    emerge: ManaCost | None = None
    #: Convoke and delve: `"tap_creatures"` or `"exile_from_graveyard"`.
    pay_generic_with: str | None = None
    #: Offering: the creature type the sacrifice must be. ``None`` is emerge
    #: proper, which takes any creature.
    emerge_subtype: str | None = None
    #: "This spell costs {X} less to cast."  See `costs.cost_reduction`, and
    #: `costs.reduction_amount` for the shapes -- it is **variant-blind** by
    #: design: Ghalta costs less however it is cast, so `_cast_variant` applies
    #: this to whichever price it picked. A discount that belongs to one cast
    #: variant goes on that variant's own cost node instead, as
    #: `Cost.mana_reduction`.
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
    #: Whether a spell cast from the graveyard for that cost is exiled when it
    #: finishes. True for flashback and jump-start; **False for escape**, which
    #: is reusable and is the only reason this is not a constant.
    graveyard_cast_exiles: bool = True
    #: Disturb: a graveyard cast that arrives on the **back** face.
    graveyard_cast_transformed: bool = False
    #: Dredge N -- the mill that replaces a draw. See `engine/replacements.py`.
    dredge: int = 0
    #: Madness -- the price of casting it out of the exile a discard sent it to.
    madness: ManaCost | None = None
    #: Miracle -- the price of casting it as the first card drawn this turn.
    miracle: ManaCost | None = None
    #: Foretell -- the price of casting it out of the exile it was foretold to.
    foretell: ManaCost | None = None
    #: Epic -- no more spells this game, and a free copy each of your upkeeps.
    epic: bool = False
    #: Morph / megamorph -- the price of turning it face up, and whether it
    #: arrives with a +1/+1 counter when it does.
    morph: ManaCost | None = None
    morph_counter: bool = False
    #: Splice -- the price, and the subtype it may be spliced onto.
    splice: ManaCost | None = None
    splice_onto: str = "Arcane"
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


#: Ward {2} on a **cloaked** permanent (701.61a).
#:
#: A rules-supplied ability, like `BESTOW_TARGET` above is a rules-supplied
#: target. It has to be: rule 707.2 says a face-down permanent has *no*
#: abilities, so the ward cannot come from the card underneath -- and it must
#: not, because that card is usually not even a creature. The cloak rule is what
#: grants it, so the engine is what carries it.
#:
#: The effect is the shipped ward idiom verbatim (`t_warded` in the test pool):
#: a `becomes_target` trigger, a `may` routed to the *caster* rather than to the
#: ability's controller, a mana `pay`, and a `counter` of the offending spell in
#: the `else`.
CLOAK_WARD = Ability(
    kind=AbilityKind.TRIGGERED,
    index=0,
    text="Ward {2}",
    trigger=TriggerSpec(event="becomes_target", controller="opponent", source="self"),
    effects=(
        {
            "op": "may",
            "player": {"binding": "event_player"},
            "prompt": "Pay {2} for ward?",
            "pay": {"mana": "{2}"},
            "else": [{"op": "counter", "sid": {"binding": "sid"}}],
        },
    ),
    active_zones=(Zone.BATTLEFIELD,),
)
