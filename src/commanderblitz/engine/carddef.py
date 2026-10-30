"""Immutable card definitions.

One :class:`CardDef` exists per distinct card and is shared by every instance of
it in every game.  These objects are built by :mod:`commanderblitz.cards.loader` from
JSON and are never mutated afterwards, so the engine can treat them as constants.

The effect bodies (``effects``, ``static``, selectors, conditions) stay as plain
dicts: they are *data* interpreted by :mod:`commanderblitz.engine.effects`, and the
loader has already validated every key and op name against the registries.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .enums import AbilityKind, CardType, Keyword, Step, Supertype, Zone
from .mana import ManaCost, ManaKeywordGrant, ManaRestriction

#: Types whose subtypes contribute to Commander colour identity checks.
LAND_TYPE = CardType.LAND.value

#: The deck-construction exception of 903.5b, printed on the card that grants it:
#: "A deck can have any number of cards named Persistent Petitioners."  Matched
#: against the card's own name, because the sentence names the card it applies to
#: and Shadowborn Apostle does not license a playset of Relentless Rats.
#:
#: The sentence is *unbounded*; see :data:`_UP_TO` for the form that names a
#: number, which needs a different answer.
_ANY_NUMBER = re.compile(r"A deck can have any number of cards named ([^.\n]+)\.")

#: The same exception with a ceiling on it: "A deck can have up to nine cards
#: named Nazgûl."  Two cards in the whole catalog print it -- Nazgûl (nine) and
#: Seven Dwarves (seven) -- and both spell the number out, which is why this
#: reads a word rather than an integer.
_UP_TO = re.compile(r"A deck can have up to (\w+) cards named ([^.\n]+)\.")

#: 903.3's exception: "Teferi, Temporal Archmage can be your commander." A card
#: that is not a legendary creature may lead a deck only when its text says so.
_CAN_BE_COMMANDER = re.compile(r"(?m)^([^\n]+?) can be your commander\.$")

#: Magic spells its small numbers out in rules text.  A word outside this map
#: leaves :attr:`CardDef.deck_copy_limit` at the one-copy default rather than
#: guessing: an unread limit must reject a legal deck, never admit an illegal
#: one, which is the safe direction for the check to be incomplete in.
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


@dataclass(frozen=True)
class TargetSpec:
    """A single target requirement of a spell or ability."""

    id: str
    kind: str  # "permanent" | "player" | "spell" | "card_in_graveyard"
    #        | "card_in_exile" | "any" | "spell_or_permanent" | "ability_on_stack"
    selector: Mapping[str, Any] = field(default_factory=dict)
    #: A ``"spell_or_permanent"`` spec's selector for its **permanent** half,
    #: when the printed word narrows only that half -- "target spell or
    #: **creature**" (Fatehold Charm). ``None`` means both halves read
    #: `selector`. See :attr:`permanent_half`.
    permanent_selector: Mapping[str, Any] | None = None
    #: A number, or ``"any"`` for "any number of target …" -- a size the caster
    #: chooses. At most one spec per card may be ``"any"``, and it must be the
    #: last, because `filter_legal` slices the stored refs spec by spec and a
    #: variable-size spec in the middle would make the split ambiguous.
    count: int | str | Mapping[str, Any] = 1
    #: The ``count`` this spec takes instead **when the spell was kicked**.
    #:
    #: "Choose target creature you own. **If this spell was kicked, instead
    #: choose any number of target creatures you own.**" -- The Eagles Are
    #: Coming!. A second count rather than a value expression, because the two
    #: sizes are not two numbers: unkicked is exactly one and kicked is ``"any"``,
    #: which no arithmetic yields.
    #:
    #: Legal *because of the rules order*, which the note on
    #: `targeting.resolve_count` gets half right and half wrong. That note says a
    #: spell's own targets are fixed "before it has been paid for", and payment
    #: (601.2h) is indeed later -- but kicker is **announced** at 601.2b, one step
    #: *before* targets are declared at 601.2c. So the choice is known when the
    #: targets are chosen, which is exactly why this printing exists.
    #:
    #: Read by `casting._kicked_targets`, which hands the kicked cast line its own
    #: enumeration. Nothing outside that line ever sees it, so an unkicked cast is
    #: byte-for-byte the card it was before.
    count_if_kicked: int | str | Mapping[str, Any] | None = None
    #: Which side of the gift promise declares this spec: ``True`` only a
    #: promised cast, ``False`` only an unpromised one, ``None`` both. The
    #: loader has already split the card's specs into :attr:`CardDef.targets`
    #: (unpromised) and :attr:`CardDef.gift_targets` (promised) by it, so
    #: nothing in the engine reads the field itself -- it records the printed
    #: clause the way `mode` records which bullet owns a spec.
    gift_promised: bool | None = None
    #: "Return **up to X** target creature cards from your graveyard." The
    #: ``count`` is a *ceiling* rather than an exact number, so every size from
    #: zero through it is a legal choice. `optional` cannot say it -- that is
    #: "exactly N, or none", which forbids every size between 1 and N-1 -- and
    #: ``"any"`` cannot either, because it has no ceiling at all.
    up_to: bool = False
    #: At most one chosen object per controller -- "for each player, up to one
    #: target permanent that player controls". Only meaningful with
    #: ``count == "any"``.
    one_per_player: bool = False
    optional: bool = False
    #: A cap on the combined mana value of everything chosen for this spec --
    #: "any number of target creature cards **with total mana value 6 or
    #: less**" (Phoenix, Warden of Fire). A constraint *between* the picks, so
    #: it is applied where the combinations are built rather than in the
    #: selector: every selector clause is evaluated against one candidate in
    #: isolation, and `mana_value: {"op": "<=", "value": 6}` is a different and
    #: far wider card -- six one-drops pass it. ``None`` for no cap.
    total_mana_value: int | None = None
    #: The index of the **mode** that owns this target, or ``None`` for the
    #: ordinary card-level kind.  "Choose up to two. Return those cards from
    #: your graveyard to your hand. * Target artifact card. * Target creature
    #: card. ..." -- four modes, four separate targets, and two of them live at
    #: once.
    #:
    #: A mode-owned spec is *not* part of the cast action: it is declared after
    #: the modes are chosen (601.2b then 601.2c), which is the printed order and
    #: the reverse of the one legality enumerates in.  See
    #: :attr:`CardDef.mode_targets` and `game.Game._ask_mode_targets`.
    #:
    #: A **triggered** ability may own one too, and it is the same rule read at
    #: the other moment: 603.3d chooses a trigger's modes and its targets alike
    #: as the ability is put on the stack.  See :attr:`Ability.mode_targets` and
    #: `stack.push_triggered_ability`.
    mode: int | None = None

    @property
    def permanent_half(self) -> Mapping[str, Any]:
        """The selector a ``"spell_or_permanent"`` spec's battlefield half reads.

        `permanent_selector` when the card wrote one, else `selector`. The one
        accessor `candidates` and `still_legal` share, so the pool a target is
        offered from and the one it is re-checked against cannot disagree.
        """
        if self.permanent_selector is not None:
            return self.permanent_selector
        return self.selector

    @property
    def variable_size(self) -> bool:
        """Is the number of refs this spec stores unknowable from the card?

        ``"any"``, "up to X", and a count that is a value expression all are:
        the first two because the *caster* picks the size, the third because the
        number is computed from the game rather than printed. `filter_legal`
        slices the stored refs spec by spec, so every one of them has to be the
        last spec in its list and there may be only one -- see
        `loader.targets._compile_targets`.
        """
        return self.up_to or not isinstance(self.count, int)

    @property
    def x_sized(self) -> bool:
        """Is this "each of **X** targets", sized by the X paid to cast the spell?

        Crackle with Power: "{X}{R}{R}{R}: … deals 5 damage to each of X
        targets." The one computed count a *spell* may carry, and it is legal
        for the reason every other computed count is not: 601.2b announces X
        and 601.2c chooses targets, in that order, so by the time the targets
        are declared X is a number. `{"additional_paid": true}` reads a cost
        paid at 601.2h and would still read zero here, which is what
        `loader.targets._compile_targets` refuses.
        """
        return isinstance(self.count, dict) and bool(self.count.get("x"))


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
    #: "{R}, {T}, **Exert this land**:" -- Arena of Glory. Exert as a cost
    #: (702.121a): the source does not untap during its controller's next untap
    #: step, and `TurnLedger.object_flags` records the word for the turn.
    #:
    #: Distinct from ``tap``, which is the ``{T}`` symbol -- Arena's cost is
    #: both, and 702.121b exerts a permanent whether or not it is tapped -- and
    #: from the ``skip_untap`` **op**, which runs at resolution. A mana ability
    #: never resolves, so the op could not be reached from the only printing.
    exert: bool = False
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
    #: "Untap two tapped creatures you control": the mirror of
    #: ``tap_permanents``, pool forced to ``tapped: True``.  Distinct from
    #: ``untap``, which is the ``{Q}`` symbol and only ever untaps the source --
    #: Halo Fountain's cost carries ``tap`` *and* this, and they name different
    #: permanents.
    untap_permanents: Mapping[str, Any] | None = None
    #: "Remove N counters from among <permanents> you control" -- see
    #: `CostModel.remove_counters_from_among`. Any kinds, any split.
    remove_counters_from_among: Mapping[str, Any] | None = None
    #: "Mill a card" as a cost -- see `CostModel.mill`. No selector: the cards
    #: come off the top of the activating player's own library.
    mill: int = 0
    discard: int = 0
    #: "…by discarding a **land** card": narrows what ``discard`` may take.
    discard_selector: Mapping[str, Any] | None = None
    #: Cycling's "**Discard this card**": the source discards *itself*, with no
    #: choice about which card goes. Deliberately not ``discard: 1`` narrowed by
    #: a selector -- ``_discard_pool`` offers the whole hand and ``ask_objects``
    #: lets the player pick, so a Krosan Tusker could be "cycled" by pitching
    #: something else and staying in hand.
    discard_self: bool = False
    #: "{1}{W}, {T}, **Exile this artifact**:" -- Phoenix Down. The exile twin
    #: of `discard_self`, and deliberately not `sacrifice`, which puts the
    #: source in the graveyard. The difference is the whole card here: Phoenix
    #: Down is meant to be one-shot and graveyard-proof, and sacrificing it
    #: would leave it recurrable *and* feed its own first mode.
    #:
    #: Not the `exile` op either -- an op runs at resolution, so the ability
    #: could be activated and responded to with the source still on the
    #: battlefield, and 601.2h pays costs before any of that.
    exile_self: bool = False
    #: "**Exile a blue card from your hand**" -- the pitch cost of Force of
    #: Will, Misdirection, Pyrokinesis and the Modern Horizons elementals. A
    #: selector over the payer's own hand, with an optional ``count``.
    #:
    #: The exile twin of `discard` + `discard_selector`, and deliberately not
    #: that pair: a discarded card lands in the graveyard, where delirium,
    #: threshold, Tarmogoyf and every reanimation spell can see it. The printed
    #: cost exiles, and that difference is why these spells are priced as they
    #: are.
    exile_from_hand: Mapping[str, Any] | None = None
    #: "**Exile this card from your hand**: Add {R}" -- Simian Spirit Guide.
    #: The exile twin of `discard_self`.
    #:
    #: A separate flag from `exile_self`, which is "Exile this artifact" and
    #: whose `costs.can_pay` check requires the source to be on the
    #: battlefield -- Phoenix Down keeps that, and this one requires the hand.
    #: Merging them would mean either loosening Phoenix Down's check to any
    #: zone, or leaving a Spirit Guide that loads clean and can never be
    #: activated.
    exile_self_from_hand: bool = False
    #: "As an additional cost to cast this spell, **behold a Dragon** or pay
    #: {1}" -- Caustic Exhale. A selector (with an optional ``count``) naming
    #: what the payer must choose among the permanents they control or reveal
    #: from their own hand; see `effects.behold`. The source is never its own
    #: beholding (601.2a), and nothing moves: a permanent stays put, a card
    #: goes back among the hand, and the reveal is the whole price.
    behold: Mapping[str, Any] | None = None
    #: An integer, or a value expression evaluated at payment time -- see
    #: `costs.life_cost`, which both `can_pay` and `pay` go through so the two
    #: cannot price the same cost differently.
    pay_life: int | Mapping[str, Any] = 0
    #: "As an additional cost to cast this spell, **pay X life**" -- Toxic
    #: Deluge. The caster announces X as the spell is cast (601.2b), and the
    #: spell's own effects read it back with ``{"x": true}``.
    #:
    #: A flag rather than a value expression, because every other `pay_life` is
    #: a number the *board* decides -- a literal, or War Room's count of
    #: commander colours -- and this one is the player's choice. And not
    #: `additional_repeatable` with ``pay_life: 1``, which produces the same set
    #: of outcomes but caps at `legality.MAX_ADDITIONAL_TIMES` (six), turns one
    #: payment of X life into X payments of one, and describes an *optional*
    #: cost paid a number of times rather than one mandatory announced number.
    pay_life_x: bool = False
    #: "Pay {E}{E}": energy counters off the payer (107.14).
    pay_energy: int = 0
    remove_counters: Mapping[str, Any] | None = None
    #: "{T}, **Put a page counter on this artifact**: Scry 1." -- Mazemind
    #: Tome. ``{"counter": kind, "amount": N}`` put on the source as the
    #: ability is activated (602.2b, 601.2h), through `primitives.add_counters`
    #: with ``as_cost`` -- so ``counter_placed`` fires and the counter
    #: replacements that are not "if an effect would" apply. The mirror of
    #: ``remove_counters``, and not the `add_counters` op, which would move the
    #: payment to resolution.
    put_counters: Mapping[str, Any] | None = None
    #: A loyalty cost (606.2), signed. `None` rather than `0` for "no loyalty
    #: cost", because `0:` is a real and different thing -- a printed zero
    #: ability still counts as the one loyalty ability that turn.
    loyalty: int | None = None
    #: "-X" (606.4, 107.3): the controller announces X, bounded by the source's
    #: loyalty, and removes X loyalty counters. Always carried with
    #: ``loyalty == 0``, so every "is this a loyalty ability" check -- which asks
    #: ``loyalty is not None`` -- sees one; `costs.can_pay` and `costs.pay` read
    #: the announced ``x`` for the amount.
    loyalty_x: bool = False
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
    #: "X is the mana value of that card" -- Soul Foundry. A value expression
    #: that **defines** the ``{X}`` in `mana`, rather than the player announcing
    #: it. Evaluated by `costs.defined_x` at activation time, and applied by
    #: `costs.ability_mana`, which both `can_pay` and `pay` go through -- so the
    #: ability is offered at exactly the X it is charged, and `game._ask_x`
    #: hands the number back instead of asking for one.
    #:
    #: `None` means "X is announced" (601.2b), which is every other X cost.
    x_value: Mapping[str, Any] | None = None

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
            exert=bool(spec.get("exert", False)),
            sacrifice=dict(spec["sacrifice"]) if spec.get("sacrifice") else None,
            return_to_hand=(
                dict(spec["return_to_hand"]) if spec.get("return_to_hand") else None
            ),
            tap_permanents=(
                dict(spec["tap_permanents"]) if spec.get("tap_permanents") else None
            ),
            untap_permanents=(
                dict(spec["untap_permanents"]) if spec.get("untap_permanents") else None
            ),
            remove_counters_from_among=(
                dict(spec["remove_counters_from_among"])
                if spec.get("remove_counters_from_among")
                else None
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
            put_counters=(
                dict(spec["put_counters"]) if spec.get("put_counters") else None
            ),
            # `is not None`, not truthiness: `0:` is a printed loyalty cost and
            # a falsy one, and reading it as "no loyalty cost" would make a zero
            # ability free to use twice in a turn.
            # A -X ability is a loyalty ability whose fixed part is zero; the
            # flag carries the announced amount.
            loyalty=(
                int(spec["loyalty"])
                if spec.get("loyalty") is not None
                else (0 if spec.get("loyalty_x") else None)
            ),
            loyalty_x=bool(spec.get("loyalty_x")),
            exile_from_graveyard=(
                dict(spec["exile_from_graveyard"]) if spec.get("exile_from_graveyard") else None
            ),
            mill=int(spec.get("mill", 0) or 0),
            pay_life_x=bool(spec.get("pay_life_x")),
            pay_energy=int(spec.get("pay_energy", 0) or 0),
            exile_self=bool(spec.get("exile_self")),
            exile_from_hand=(
                dict(spec["exile_from_hand"]) if spec.get("exile_from_hand") else None
            ),
            exile_self_from_hand=bool(spec.get("exile_self_from_hand")),
            behold=(dict(spec["behold"]) if spec.get("behold") else None),
            mana_reduction=(
                dict(spec["mana_reduction"]) if spec.get("mana_reduction") else None
            ),
            x_value=(dict(spec["x_value"]) if spec.get("x_value") else None),
        )

    def without_mana(self) -> Cost:
        """This cost with its mana removed -- the *additional* half.

        Flashback's mana replaces the printed cost and everything else is paid
        on top, the way `retrace_cost` is, so the two halves are charged at
        different moments and legality has to test them separately.
        """
        return replace(self, mana=ManaCost.parse(""))

    def charges_nothing(self) -> bool:
        """True when this node takes nothing but (possibly) mana.

        Asked of an *alternative* cost, which replaces the printed one: a node
        with neither mana nor anything else on it is a card castable for free,
        and one with only mana on it is `evoke` under a second name. Written as
        an equality against a default cost carrying this one's mana, so a cost
        key added later is covered without anyone remembering to list it here.
        """
        return self == Cost(mana=self.mana)

    def is_tap_only(self) -> bool:
        """True when the only cost is ``{T}`` -- the shape mana sources must have."""
        return (
            self.tap
            and self.mana.is_free()
            and not self.untap
            # Arena of Glory's exerting ability is not a tap-for-mana source the
            # solver may fire on its own: exert is a price, and a solver that
            # paid it silently would keep a land down for a turn nobody agreed
            # to. Its `{R}` already disqualifies it; this is the claim itself.
            and not self.exert
            and self.sacrifice is None
            and self.return_to_hand is None
            and self.tap_permanents is None
            and self.untap_permanents is None
            and self.remove_counters_from_among is None
            and self.discard == 0
            and not self.discard_self
            # Without this the payment solver would treat Millikin as a plain
            # tap-for-mana source and take the {C} without ever milling.
            # `costs.solver_taps` reads this, and `legality._activate_actions`
            # reads its complement, so a mill cost moves the ability from
            # "tapped silently by the solver" to "offered to the player" --
            # the same place a Signet's {1} and a Vivid land's counter sit.
            and self.mill == 0
            and not self.exile_self
            # Simian Spirit Guide is a mana ability that costs a card, not a
            # tap. Left out of `is_tap_only` it would be invisible to the
            # payment solver *and* to the player; counted in, the solver would
            # exile cards out of a hand it was never asked about.
            and not self.exile_self_from_hand
            and self.exile_from_hand is None
            and self.behold is None
            and not self.pay_life
            and not self.pay_energy
            and self.remove_counters is None
            and self.put_counters is None
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
        if self.exert:
            parts.append("Exert this permanent")
        if self.sacrifice:
            parts.append("Sacrifice")
        if self.return_to_hand:
            parts.append("Return to hand")
        if self.tap_permanents:
            parts.append(f"Tap {self.tap_permanents.get('count', 1)} untapped permanents")
        if self.untap_permanents:
            parts.append(
                f"Untap {self.untap_permanents.get('count', 1)} tapped permanents"
            )
        if self.mill:
            parts.append(f"Mill {self.mill}")
        if self.discard:
            parts.append(f"Discard {self.discard}")
        if self.discard_self:
            parts.append("Discard this card")
        if self.exile_self:
            parts.append("Exile this permanent")
        if self.exile_self_from_hand:
            parts.append("Exile this card from your hand")
        if self.exile_from_hand:
            count = self.exile_from_hand.get("count", 1)
            parts.append(f"Exile {count} from your hand")
        if self.behold:
            count = self.behold.get("count", 1)
            parts.append("Behold" if count == 1 else f"Behold {count}")
        if self.pay_life:
            amount = self.pay_life if isinstance(self.pay_life, int) else "X"
            parts.append(f"Pay {amount} life")
        if self.pay_energy:
            parts.append("Pay " + "{E}" * self.pay_energy)
        if self.remove_counters:
            parts.append("Remove counters")
        if self.put_counters:
            amount = self.put_counters.get("amount", 1)
            kind = self.put_counters.get("counter", "")
            parts.append(f"Put {amount} {kind} counter{'s' if amount != 1 else ''} on this")
        if self.remove_counters_from_among:
            count = self.remove_counters_from_among.get("count", 1)
            parts.append(f"Remove {count} counters from among permanents")
        if self.loyalty_x:
            parts.append("-X")
        elif self.loyalty is not None:
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
    #: False for a "while" clause: ``condition`` is checked as the event
    #: happens and not again on resolution (603.4 names "if" only).
    recheck: bool = True
    #: Who is being attacked, for ``attacks``.  ``controller`` answers *whose
    #: creature* is attacking, which is a different question and not a
    #: substitute: in a pod, "whenever a creature attacks you" must not fire when
    #: one opponent swings at another.  ``you`` | ``opponent`` | ``any``, or
    #: ``most_life`` on ``attacks`` only: dethrone's "attacks **the player with
    #: the most life or tied for most life**" (702.105a), a player and not a
    #: planeswalker or battle, asked as part of the event; or ``monarch`` on
    #: ``attacks`` only, "attacks **the monarch**" (The Spear of Bashenga), the
    #: same two questions with the crown in place of the life totals.
    defending: str | None = None
    #: A zone-change ``cause`` this trigger refuses to fire on -- the loop guard
    #: behind "if it wasn't put onto the battlefield with this ability".
    not_cause: str | None = None
    #: Who controlled the spell or ability that *caused* this event, relative to
    #: the ability's controller -- "when a spell or ability **an opponent
    #: controls** causes you to discard this card" (Orvar, the All-Form).
    #: ``discard`` only, and deliberately not ``controller``: `_actor` answers
    #: that with the player who discarded, so `controller: "opponent"` would
    #: read "an opponent discarded a card", which is a different sentence.
    #: ``None`` on an event nobody caused -- the cleanup-step discard, and a
    #: discard paid as a cost -- so a trigger naming it never fires on either.
    cause_controller: str | None = None
    #: Which counter kind a ``counter_placed`` trigger cares about.  The event
    #: has always carried it; nothing read it, so every such trigger fired on
    #: every kind.  Fathom Mage is the witness.
    counter: str | None = None
    #: ``counter_placed`` only: "whenever **you** put one or more +1/+1
    #: counters on this creature" -- the event's ``put_by`` (the putter,
    #: 122.6a) must be this ability's controller.  Exemplar of Light.
    put_by: str | None = None
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
    #: ``becomes_target`` only: "becomes the target of **a spell**" (Goldspan
    #: Dragon), as against ward's "a spell or ability", which is the unclaused
    #: form.  ``"spell"`` fires on spells alone, ``"ability"`` on abilities
    #: alone, and ``None`` on both.
    #:
    #: A restriction rather than a ``filter`` or a ``condition``, because
    #: neither can reach it.  ``filter`` is matched against the trigger's
    #: *subject*, which for this event is the permanent being targeted -- so it
    #: can only ask what the Dragon is, never what aimed at it.  ``controller``
    #: asks *whose* spell or ability it was, which is the other axis entirely.
    #: And ``condition`` reads `event_bindings`, which copies only
    #: EVENT_BINDING_KEYS -- carrying the ``sid`` but not this.
    #:
    #: `stack.announce_targets` has put ``is_spell`` on every BECAME_TARGET
    #: event since the event existed, for both the object and the player half
    #: and at all four push sites (`put_copy_on_stack` included, so a **copy**
    #: of a spell is a spell here -- 706.10 puts one on the stack without
    #: casting it).  Nothing read the flag, so the only trigger that could be
    #: written also fired off an opponent's tapper, a fight ability, and your
    #: own equip.
    targeted_by: str | None = None
    #: ``draw`` and ``spell_cast`` only: "whenever you draw your **second**
    #: card each turn", "whenever an opponent casts their **second** spell each
    #: turn".  The ordinal the draw or cast must have had for its player this
    #: turn, compared against ``nth`` on the event.  On ``spell_cast`` with a
    #: ``filter`` it is the ordinal among that player's spells **matching** the
    #: filter -- "their first noncreature spell" -- see
    #: `triggers._spell_ordinal`.  On ``counter_placed`` it is "the **tenth**
    #: +1/+1 counter": the placement whose ``before`` and ``amount`` straddle
    #: it -- see `triggers._crosses_nth`.
    #:
    #: A restriction on the trigger rather than a ``condition``, and that is the
    #: whole of the feature.  The condition form -- ``cards_drawn_this_turn ==
    #: 2`` -- reads correctly at queue time and is then **re-asked on
    #: resolution** (603.4, `stack.resolve_top`), by which point the tally has
    #: moved: a spell that draws two takes it to 2 (queuing the trigger) and
    #: then to 3, and the re-check reads 3 and skips the ability.  Loosening to
    #: ``>=`` with ``max_per_turn: 1`` survives that, and then fires for a
    #: permanent that entered *after* two cards were already drawn, where the
    #: printed card does nothing at all that turn.  Only a queue-time predicate
    #: is both.
    nth: int | None = None
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
    #: "Whenever **one or more** cards leave your graveyard…" -- Spirit Mascot.
    #: The event fires once per card, because that is how cards move; this says
    #: the *ability* fires once per simultaneous group. Without it, Rise of the
    #: Dark Realms emptying a five-card graveyard would put five +1/+1 counters
    #: on the Mascot instead of one.
    #:
    #: Deliberately not `max_per_turn: 1`, which the codebase already documents
    #: as the stand-in for this shape and which is a *different card*: a printed
    #: "one or more" fires again later the same turn for a second, separate
    #: departure, and a per-turn cap does not.
    batched: bool = False
    #: Which chapter number a ``chapter`` trigger fires on -- the "II" in "II --
    #: Create two 2/2 red Human Knight creature tokens".
    #:
    #: On the spec rather than only on the :class:`Ability`, because
    #: ``triggers._matches`` is handed the spec and not the ability, and the
    #: number is a *filter on the event* in exactly the way ``counter`` is: one
    #: CHAPTER_REACHED event carries the number reached and every chapter ability
    #: on the Saga sees it. Without the comparison a three-chapter Saga would
    #: resolve all three chapters on its first lore counter.
    chapter: int | None = None
    #: Which level a ``becomes_level`` trigger fires on -- the "2" in "When this
    #: Class becomes level 2". On the spec for `chapter`'s reason: it is a filter
    #: on the event, and `triggers._matches` is handed the spec.
    level: int | None = None
    #: "…deal combat damage to a player **or battle**" -- Zurgo and Ojutai. The
    #: one widening key on a trigger, and it only means anything on
    #: ``creatures_deal_combat_damage``; the loader refuses it anywhere else.
    #:
    #: A flag rather than a second event name, because it is one printed
    #: sentence with a disjunction in it and the batch is the same batch:
    #: `_fire_damage_batch` fires one event per damaging player per step
    #: carrying `damaged` and `damaged_battles`, and splitting it in two would
    #: fire *both* on a swing that hit a seat and a battle, paying an ability
    #: twice for one combat-damage event (510.2).
    #:
    #: It is a widening and therefore **off** by default and checked as a
    #: presence: "whenever one or more creatures you control deal combat damage
    #: to one or more players" is printed on cards that say nothing about
    #: battles, and a battle-only swing must not fire them. `_matches` refuses a
    #: firing with no `damaged` seats unless this is set.
    #:
    #: Named for `or_planeswalker`, the effect-side key with the same job on
    #: `attacking` -- same word, same disjunction, same default.
    or_battle: bool = False
    #: "…deal combat damage to **a player**" / "…to **an opponent**", read the
    #: way the rulings read it: once for each player dealt damage, with "that
    #: player" bound. Only on ``creatures_deal_combat_damage``; `triggers.collect`
    #: hands the trigger one copy of the batch per seat in its ``hits``, each
    #: with ``damaged``, ``damagers`` and ``defender`` narrowed to that seat.
    #: Off by default: "…to one or more players" is one trigger for the batch.
    per_player: bool = False
    #: For ``leaves_battlefield``: the zone names the permanent must have gone
    #: to -- "when this creature dies **or is put into exile**" is
    #: ``("graveyard", "exile")``. Compared with the event's ``to_zone``, which
    #: `move_object` stamps on every departure. ``None`` is any destination.
    to_zones: tuple[str, ...] | None = None
    #: For ``spell_cast`` and ``land_played``: the zone names the card must
    #: have been played from -- "whenever you play a card **from exile**" is
    #: ``("exile",)``. A spell is asked `GameObject.cast_from_zone`, stamped by
    #: `stack.push_spell` before the card reaches the stack (601.2a); a land
    #: drop carries ``from_zone`` on its LAND_PLAYED payload. ``None`` is any
    #: origin.
    from_zones: tuple[str, ...] | None = None
    #: The ``state`` event only: the condition a **state trigger** watches
    #: (603.8) -- "When there are four or more page counters on this
    #: artifact…" (Mazemind Tome). Checked whenever state-based actions are, by
    #: `triggers.check_state_triggers`, and not re-asked on resolution: it is
    #: the trigger condition, not an intervening "if" (603.4), so a counter
    #: removed in response does not stop the ability.
    state: Mapping[str, Any] | None = None


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


def asks_another_player(spec: Mapping[str, Any] | None) -> bool:
    """Does this ``choose_mode`` hand the choice to somebody other than us?

    The Warring Triad: "Target player adds one mana of any color." "Any color"
    is spelled as a `choose_mode` over five `add_mana` modes, and the player
    *adding* the mana is the one who picks -- so the question cannot be
    pre-answered by the ability's controller at 601.2b/602.2b time, the way an
    ordinary modal spell's is. It belongs to resolution, for the same reason a
    nested `choose_mode` does, and both `cast_time_modes` properties decline it
    on that ground.
    """
    return bool(spec) and spec.get("chooser") is not None


def is_budgeted(spec: Mapping[str, Any] | None) -> bool:
    """Is this ``choose_mode`` a budget rather than a count?

    Season of Weaving: "choose up to five {P} worth of modes. You may choose the
    same mode more than once." The answer is a **multiset** picked one mode at a
    time, because what is affordable shrinks as the budget is spent -- which is
    a different question from the single "which of these" that `_ask_modes`
    puts at 601.2b, and one it has no shape for.

    Declined for the same reason `asks_another_player` is, so the op's own loop
    gets to ask. Season of Weaving owns no mode-targets, so nothing is lost by
    asking at resolution; a budgeted card that did would need this revisited.
    """
    return bool(spec) and spec.get("budget") is not None


def _specs_for_modes(
    base: tuple[TargetSpec, ...],
    mode_targets: Mapping[int, tuple[TargetSpec, ...]],
    modes: Sequence[int],
) -> tuple[TargetSpec, ...]:
    """The specs one declaration actually used: the flat list, then the modes'.

    One function for a card and for an ability, because the ordering is the
    whole content and two copies of it is two chances to disagree:
    `targeting.filter_legal` splits the stored refs **by position**, so
    whatever declared the targets and whatever re-checks them on resolution
    have to walk the modes in the same order -- ascending mode index, which is
    the printed order 700.2e executes them in.
    """
    if not mode_targets:
        return base
    extra: list[TargetSpec] = []
    for index in sorted(modes):
        extra.extend(mode_targets.get(index, ()))
    return tuple(base) + tuple(extra)


@dataclass(frozen=True)
class Ability:
    """An activated, triggered or static ability printed on a card."""

    kind: AbilityKind
    index: int
    text: str = ""
    #: The name a `reflexive_trigger` op calls a ``reflexive`` ability by.
    #: Empty on every other kind.
    reflex_id: str = ""
    # activated
    cost: Cost | None = None
    is_mana_ability: bool = False
    #: "Equip {2}" (702.6a), so a static can name equip abilities as a class.
    #: See `schema.AbilityModel.is_equip` for why it is declared and not
    #: inferred from the `attach` effect.
    is_equip: bool = False
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
    #: "Add one mana of any **type** that a land you control could produce."
    #: Reflecting Pool, Horizon of Progress. The same question as
    #: `mana_reflects` asked over 106.1b's six types of mana rather than over
    #: five colours, so `mana_options` carries `_ANY_TYPE_OPTIONS` at load time
    #: and `costs.mana_options_of` keeps the colorless index while polling the
    #: board instead of dropping it.
    #:
    #: A flag beside `mana_reflects` rather than a family of its own, because
    #: the *question* is identical -- "what could these permanents produce" --
    #: and only the answer's vocabulary widens. It is meaningless without
    #: `mana_reflects` and the loader refuses it there.
    mana_reflects_any_type: bool = False
    #: "{T}: Add one mana of any of **the exiled card's colors**." Chrome Mox.
    #: A selector over *cards*, whose printed colours decide which colours this
    #: ability offers -- the fifth member of the same family as `mana_reflects`
    #: and `mana_identity`, and the one that reads a characteristic rather than
    #: another ability.
    #:
    #: `mana_reflects` is the near miss and is a different card: it asks each
    #: matched object's own mana *abilities* what they could produce, and an
    #: imprinted nonartifact, nonland card sitting in exile has none -- so a
    #: Chrome Mox written that way taps for nothing, always. The other near miss
    #: is a `choose_mode` over five `add_mana`s, which taps for any colour with
    #: nothing imprinted at all: strictly better than the printed card.
    #:
    #: `mana_options` carries the five-colour superset until activation, for the
    #: same reason `mana_reflects` needs one, and `costs.mana_options_of` does
    #: the narrowing -- to nothing at all while the Mox is unimprinted.
    mana_colors_of: Mapping[str, Any] | None = None
    #: "Vivid — {T}: **For each color among permanents you control**, add one
    #: mana of that color." Bloom Tender. A selector whose matches' colours are
    #: read the way `mana_colors_of` reads them, and then *all of them are
    #: produced at once* rather than offered as a choice — so this is the one
    #: mana ability whose output is a variable multi-symbol bundle instead of a
    #: single pip picked from a set.
    #:
    #: `mana_colors_of` over the same selector is the near miss and is Mox
    #: Amber: "one mana of any color among …" is one mana, and a three-colour
    #: board would tap this card for one mana instead of three.
    #:
    #: `costs.mana_options_of` returns **exactly one option** here — the bundle —
    #: so there is nothing for the player or the solver to choose between, which
    #: is the printed card: Bloom Tender never asks which colour.
    #:
    #: `mana_options` carries the five-colour superset until activation for the
    #: same reason `mana_reflects` needs one, and unlike every other member of
    #: the family that superset is not *filtered* at activation — the narrowing
    #: builds a fresh tuple from the board's colours instead.
    mana_each_color_among: Mapping[str, Any] | None = None
    #: "…any color in your commander's color identity." The colours are a
    #: question about the command zone, asked when the ability is activated;
    #: `mana_options` holds the five-colour superset until then.
    mana_identity: bool = False
    #: "Add X mana in **any combination of {U} and/or {R}**" -- Vivi Ornitier.
    #: The colours the split may draw on. Fourth member of the same family as
    #: `mana_reflects`, `mana_identity` and `mana_chosen_color`: the options are
    #: a question that cannot be answered at load time, because the *size* of
    #: the split is `mana_amount` and that reads the board.
    #:
    #: A `choose_mode` of two `add_mana`s is the near miss and is a strictly
    #: worse card: it offers X of one colour or X of the other and can never
    #: make {U}{U}{R}{R} off a power-4 Vivi.
    mana_split: tuple[str, ...] = ()
    #: "{T}: Add X mana of **any one color**, where X is Helga's power" --
    #: Helga, Skittish Seer. The sixth member of the same family, and the one
    #: that needs no branch in `costs.mana_options_of` at all: the five
    #: one-symbol options really are what it offers, and `mana_amount` -- which
    #: has scaled a single option since Gyre Sage -- turns the chosen one into X
    #: of that colour.
    #:
    #: `mana_split` is the near miss and is a strictly *better* card: "any
    #: combination" at X=3 makes {W}{U}{G}, and "any one color" cannot. The
    #: other near miss is a `choose_mode` of five fixed `add_mana`s (Gilded
    #: Lotus), which needs a literal size at load time -- and Helga's size is
    #: her power, which starts at 1 and grows.
    #:
    #: A flag of its own rather than "five options and an amount", because the
    #: card prints **no mana symbol**: without a marker `_derive_color_identity`
    #: would read the superset and make a {2}{G}{U} creature five-colour, which
    #: is a deck-building rule (903.4) and not an approximation.
    mana_any_one_color: bool = False
    #: "{T}: Add one mana of **the chosen color**." Heraldic Banner. The third
    #: member of the same family as `mana_reflects` and `mana_identity`: the
    #: colour is a question about this permanent's own `chosen_color`, asked
    #: when the ability is offered, and `mana_options` carries the five-colour
    #: superset until then so the ability is recognisable as a mana source at
    #: load time. `costs.mana_options_of` does the narrowing, to the one colour
    #: that was chosen -- or to nothing at all before a colour has been named.
    #:
    #: This is what stops the card being written as a `choose_mode` of five
    #: `add_mana`s, which is the *any colour* card: that spelling would let the
    #: player pick freely on every activation instead of locking the ability to
    #: the colour named on entry, and would decouple the mana line from the
    #: anthem line that reads the same choice.
    mana_chosen_color: bool = False
    #: "Spend this mana only to cast a creature spell of the chosen type or
    #: activate an ability of a creature source of the chosen type."  ``None`` is
    #: ordinary mana.  See :class:`~commanderblitz.engine.mana.ManaRestriction` for the
    #: shape; a group may hold `mana.CHOSEN_TYPE`, resolved per permanent by
    #: `costs.resolve_mana_restriction` rather than at load time.
    mana_restriction: ManaRestriction | None = None
    #: "…**and that spell can't be countered**" -- Cavern of Souls, Delighted
    #: Halfling. A rider on the *mana*, so it travels on the pip
    #: (`mana.Pip.uncounterable`) rather than on this permanent: Cavern has two
    #: mana abilities and only one prints the clause, so anything recorded per
    #: permanent would make its plain ``{C}`` uncounterable too.
    #:
    #: Ability-level rather than card-level for the same reason, and distinct
    #: from `CardDef.uncounterable`, which is a spell speaking about itself.
    mana_uncounterable: bool = False
    #: "…**it gains haste until end of turn**" -- Arena of Glory. The other
    #: rider this ability's mana carries, and the one that has to outlive the
    #: spell: `mana_uncounterable` is read while the spell is still on the stack
    #: and thrown away, while this is owed to the *permanent* the spell becomes.
    #:
    #: On the ability for `mana_uncounterable`'s reason -- Arena has a plain
    #: `{T}: Add {R}` too, and recorded per permanent that one would grant haste
    #: for free. ``None`` is ordinary mana; the loader refuses it on an ability
    #: that is not a mana ability, where it would load and never be read.
    mana_grant: ManaKeywordGrant | None = None
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
    #: A station symbol (721): ``(counter kind, N)`` -- this permanent has the
    #: ability only while it has N or more of that counter. Read by
    #: `characteristics.abilities_of`, which leaves the ability out below N, so
    #: every reader that asks what a permanent can do agrees it is not there.
    #: The loader keeps these abilities after every ungated one and in rising
    #: order, which is what keeps `abilities_of`'s indices stable: below a
    #: threshold the list only ever loses a tail.
    threshold: tuple[str, int] | None = None
    # activated + triggered
    targets: tuple[TargetSpec, ...] = ()
    #: Target specs owned by one **mode** each, the ability-level twin of
    #: :attr:`CardDef.mode_targets`.  Only a *triggered* ability may have them:
    #: 603.3d puts both the modes and the targets at the moment the ability is
    #: put on the stack, so there is one moment that owns both questions.  An
    #: activated ability had no such moment for a long time -- `legality`
    #: enumerated one activation per legal target tuple, which is before
    #: `Game._activate` asks which mode. It has one now: `_ability_aims` offers
    #: one activation per **mode**, each with only that mode's targets, so the
    #: bullet is part of the action the way `kicked` is part of a cast.
    mode_targets: Mapping[int, tuple[TargetSpec, ...]] = field(default_factory=dict)
    effects: tuple[Mapping[str, Any], ...] = ()
    # static
    static: Mapping[str, Any] | None = None
    # Class (716)
    #: **The level this ability is printed under** -- the "Level 3" band a
    #: Class's "Creature tokens you control get +2/+2" sits in. ``None`` on every
    #: ability that is not gated, which includes a Class's level-1 abilities:
    #: 716.2c puts those on the permanent at every level, so there is nothing to
    #: record.
    #:
    #: A gate on *having* the ability, not on using it (716.2b: "a Class has the
    #: abilities of its level and of each level below it"). Below the level the
    #: ability is not there at all -- `characteristics.abilities_of` hands back a
    #: :attr:`AbilityKind.LATENT` stand-in -- so it is not offered, not
    #: collected as a trigger and not applied as a static. An `activation
    #: condition` spelling would only have refused the activation, and could not
    #: switch a static off.
    level: int | None = None
    #: **"{W}: Level 2"** -- this activated ability is a Class's level line, and
    #: this is the level it gains (716.2a): "[Cost]: This Class's level becomes
    #: N. Activate only if this Class is level N-1 and only as a sorcery."
    #:
    #: The restriction is `legality._ability_aims`' to enforce and is read off
    #: this number, which is why it is a field and not a condition: "only if
    #: level N-1" is what stops level 2 being bought twice and level 3 being
    #: bought first, and a card author has no reason ever to write it differently.
    #: The effect -- `become_level` -- is supplied by the loader, as a chapter's
    #: trigger is.
    becomes_level: int | None = None

    @property
    def cast_time_modes(self) -> Mapping[str, Any] | None:
        """The ``choose_mode`` to ask about before this goes on the stack.

        ``None`` unless the ability's whole effect tree contains exactly one
        ``choose_mode`` at its top level: a nested or repeated one is a second
        question that genuinely belongs to resolution, and pre-answering it
        would bind the wrong one.

        Answered for an **activated** ability (602.2b) and for a **triggered**
        one (603.3d) alike.  The triggered half is not a convenience: the modes
        have to be chosen at the moment the ability is put on the stack, because
        that is the only moment at which a mode-owned target could be declared
        -- and 601.2b, which 603.3d applies, says a mode with no legal target
        cannot be chosen at all.  A *static* ability never reaches the stack.
        """
        if self.is_static or count_mode_specs(self.effects) != 1:
            return None
        spec = top_level_mode_spec(self.effects)
        return None if asks_another_player(spec) or is_budgeted(spec) else spec

    def specs_for_modes(self, modes: Sequence[int]) -> tuple[TargetSpec, ...]:
        """The target specs this ability actually declared -- see
        :meth:`CardDef.specs_for_modes`, of which this is the ability-level
        twin, down to the ordering rule `targeting.filter_legal` depends on."""
        return _specs_for_modes(self.targets, self.mode_targets, modes)

    @property
    def is_activated(self) -> bool:
        return self.kind is AbilityKind.ACTIVATED

    @property
    def is_triggered(self) -> bool:
        """714.1b: "chapter abilities are triggered abilities".

        Not a convenience -- it is the sentence, and reading it any other way
        would mean a second copy of the trigger pipeline. Every caller of this
        property already pairs it with ``ability.trigger is not None``, and the
        loader gives a chapter ability a real ``TriggerSpec``, so a chapter is
        collected, queued in APNAP order, put on the stack and given its targets
        by exactly the code that does it for "when this enters".
        """
        return self.kind in (AbilityKind.TRIGGERED, AbilityKind.CHAPTER)

    @property
    def is_chapter(self) -> bool:
        return self.kind is AbilityKind.CHAPTER

    @property
    def chapter(self) -> int | None:
        """Which chapter this is, or ``None`` for any other kind of ability.

        Read off the trigger rather than stored twice. The number is the
        trigger's filter and the card's `final_chapter` is derived from it, and
        two fields holding one number is two things to disagree.
        """
        return self.trigger.chapter if self.trigger is not None else None

    @property
    def is_static(self) -> bool:
        return self.kind is AbilityKind.STATIC

    def present_at(self, class_level: int) -> bool:
        """Does a permanent at ``class_level`` have this ability? (716.2b-c)

        True for every ability without a printed level, which is every ability
        on every card that is not a Class.
        """
        return self.level is None or class_level >= self.level

    def latent(self) -> Ability:
        """The :attr:`AbilityKind.LATENT` stand-in that holds this ability's seat.

        Keeps ``index``, ``text`` and ``level`` -- enough to say *what* is
        missing and why -- and nothing any reader could act on: no cost, no
        trigger, no static, no effects, and not a mana ability.
        """
        return Ability(kind=AbilityKind.LATENT, index=self.index, text=self.text, level=self.level)


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
    #: Target specs owned by one **mode** each, keyed by mode index into this
    #: card's single top-level ``choose_mode``.  Deliberately kept out of
    #: :attr:`targets`: legality enumerates one cast action per legal target
    #: tuple, and a mode-owned target is not known to be needed until the mode
    #: has been chosen -- which happens inside the cast, after the action.  So
    #: legality never sees these, and `Game._ask_mode_targets` declares them.
    mode_targets: Mapping[int, tuple[TargetSpec, ...]] = field(default_factory=dict)
    #: The card-level specs a **gift-promised** cast declares, or ``None`` when
    #: the promise changes nothing about what the spell points at -- every card
    #: but the few printing "if the gift was promised, … target …".
    #: :attr:`targets` is then the *unpromised* list, which is what keeps every
    #: cast line that cannot promise -- flashback, a copy's default, a free cast
    #: -- correct without knowing gift exists. Read through
    #: :meth:`targets_for`, by legality's promised lines, `Game._cast` and
    #: `stack._resolve_spell`, which must agree on the list or the stored refs
    #: are split into the wrong buckets.
    gift_targets: tuple[TargetSpec, ...] | None = None
    spell_effects: tuple[Mapping[str, Any], ...] = ()
    replacements: tuple[Mapping[str, Any], ...] = ()
    #: Starting loyalty. Kept as a characteristic as well as compiled into a
    #: replacement, because the client shows it on the card in hand where no
    #: object exists to carry counters yet.
    loyalty: int | None = None
    #: A battle's printed defense (310.3). Kept as a characteristic as well as
    #: compiled into a replacement, for loyalty's reason: the client shows it on
    #: the card in hand, where no object exists to carry counters yet.
    defense: int | None = None
    #: A Saga's **final chapter number** (714.4). Set by the loader on any card
    #: with chapter abilities, and the one thing about a Saga that is not
    #: derivable from the board: it is what 704.5s compares the lore counters
    #: against to decide the Saga is finished, and it is *not* reliably the
    #: highest chapter the card implements -- a Saga whose last chapter the DSL
    #: could not express would otherwise be sacrificed a chapter early, which is
    #: silently a better card than the printed one.
    #:
    #: ``None`` means "not a Saga", and is what every reader tests rather than
    #: the subtype: a card carrying the word Saga and no chapters has no final
    #: chapter to reach, and 704.5s says so out loud ("with one or more chapter
    #: abilities").
    final_chapter: int | None = None
    abilities: tuple[Ability, ...] = ()
    #: Abilities this card can *hand to something else* -- the quoted text in
    #: `gains trample and "Whenever this creature deals combat damage to a
    #: player, draw a card"`.  Kept apart from `abilities` because the card does
    #: not have them: they only exist on whatever it granted them to.
    grantable_abilities: tuple[Ability, ...] = ()
    #: The emblems this card can give a player (114) -- "Target opponent gets an
    #: emblem with …". Each is a whole ``CardDef`` of its own, compiled by the
    #: loader, whose ``abilities`` all work from the command zone and which has
    #: no other characteristics. An emblem object points back here by
    #: ``GameObject.emblem``, and ``GameState.card_of`` returns the entry.
    emblems: tuple[CardDef, ...] = ()
    type_line: str = ""
    is_token: bool = False
    #: An X/X token whose size its creating effect sets; see the card model.
    variable_pt: bool = False
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
    #: The card id of the **spell** a prepared permanent may cast a copy of --
    #: Emeritus of Woe's {1}{B} Demonic Tutor half.
    #:
    #: A field of its own rather than a third `second_face_zone`, because it
    #: breaks the invariant that field's whole docstring rests on: casting a
    #: second face takes the object out of its zone, and this leaves the
    #: permanent exactly where it is and puts a **copy** on the stack. One card,
    #: two objects, which no other face relationship in the engine has.
    prepared_face: str | None = None
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
    #: "Cast this spell only before the combat damage step" (Berserk). The step
    #: at which the casting window **closes**, read by `casting._timing_ok`.
    #:
    #: The one card field that *narrows* when a spell may be cast. Everything
    #: else about timing widens -- `flash`, `cast_as_though_flash`,
    #: `sorcery_speed_only` on an ability -- and `_timing_ok` returns True for an
    #: instant before any of them are consulted, so a restriction written
    #: anywhere else could not be reached at all.
    cast_before_step: Step | None = None
    #: "You can't cast this during your first, second, or third turns of the
    #: game" (Serra Avenger). Read by `player_statics.player_cant_cast_spells`
    #: against `PlayerState.turns_begun`, so every cast path refuses it.
    cant_cast_first_turns: int | None = None
    #: Buyback: a kicked spell returns to its owner's hand instead of the
    #: graveyard when it finishes resolving.
    buyback: bool = False
    #: **Rebound** (702.87a). The third rider on the destination a resolving
    #: spell goes to, beside flashback's exile and buyback's hand, and like both
    #: it only ever replaces the *graveyard*. The free cast at the next upkeep
    #: is `suspend.rebound_tick`, which shares `cast_for_free` with suspend
    #: because it is the same sentence.
    rebound: bool = False
    #: "Exile Teferi's Protection." The sixth rider on the destination a
    #: resolving spell goes to, and like the five beside it, it only ever
    #: replaces the *graveyard*.
    exiles_itself: bool = False
    #: Approach of the Second Sun's "seventh from the top". The eighth rider
    #: on the resolution slot, and the only one whose destination is a library
    #: and whose value is a depth rather than a flag. The printed ordinal,
    #: counting from 1, or ``"bottom"`` for "on the bottom of its owner's
    #: library" (Ultimate Nullification).
    tucks_itself: int | str | None = None
    #: **Overload**. A third cast variant, and the only one that changes what
    #: the spell *targets* rather than what it costs: an overloaded spell is put
    #: on the stack with no targets at all, and the card branches on
    #: `{"overloaded": true}`.
    overload: ManaCost | None = None
    #: An additional cost paid at cast time -- casualty, replicate, Deadly
    #: Dispute. A full `Cost`, where `kicker` is mana-only, and offered as one
    #: cast line per number of times paid.
    additional_cost: Cost | None = None
    #: "…discard a card **or** pay 3 life" -- one cast line per payable branch.
    #: See `CostModel.additional_cost_options`.
    additional_cost_options: tuple[Cost, ...] = ()
    #: **Spree** (702.166a) -- "Choose one or more additional costs." A
    #: non-empty *subset* of these prices is paid as the spell is cast, and one
    #: cast line is offered per payable subset. Which modes were bought is read
    #: back on resolution with `{"spree_mode": n}`.
    #: See `CostModel.spree`.
    spree: tuple[Cost, ...] = ()
    additional_optional: bool = False
    additional_repeatable: bool = False
    #: What the kicker is called on screen -- "kicked", "buyback".
    kicker_label: str = "kicked"
    #: "Kicker {1}{U}" -- an additional cost the caster may choose to pay.  It is
    #: not folded into `mana_cost` because mana value must stay what is printed,
    #: and because the choice is the mechanic: legality offers the spell twice.
    kicker: ManaCost | None = None
    #: **Gift a tapped Fish** (702.164a) -- what is promised, as the printed noun
    #: phrase. Not a cost: a gift is paid for with nothing, so the promised line
    #: is offered at the printed price. What it names instead is a **seat**, so
    #: legality offers one promised line per opponent and the chosen one rides on
    #: `Action.gift_to`. Read back by `{"gift_promised": …}` and by the
    #: ``"gift_recipient"`` player spec.
    gift: str | None = None
    #: **Multikicker {1}{W}** (702.32b). Nothing in the engine reads this: the
    #: loader has already desugared it into the three fields above, which is the
    #: whole mechanic. What it records is the *name* the card declared the cost
    #: under, so the residual gate can say which printed line the cost claims and
    #: check that the symbols on that line are the ones actually charged.
    multikicker: ManaCost | None = None
    #: **Escalate {G}** (702.120a). Desugared by the loader into the
    #: repeatable optional additional cost above, like multikicker; this one is
    #: read too, by `casting._additional_ceiling` (at most one payment per mode
    #: beyond the first) and `Game._cast` (the cast chooses exactly one mode
    #: more than it paid for).
    escalate: ManaCost | None = None
    #: **Strive**: the mana added to the spell's total cost once for each target
    #: beyond the first (601.2f). Read by `casting.strive_surcharge`, which both
    #: legality and `Game._cast` price through, so the line offered and the
    #: amount charged cannot disagree. Kept out of ``mana_cost`` for the reason
    #: kicker is: mana value stays what is printed.
    strive: ManaCost | None = None
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
    #: A melded permanent's mana value: the total of its two front faces'
    #: (the Brisela ruling -- "Brisela's mana value is 11"). The melded card
    #: prints no mana cost, so ``mana_cost`` stays empty and this answers
    #: `mana_value` instead. Never authored -- `op_meld` writes it onto the
    #: `CardDef` it synthesises for the one permanent, the way mutate writes
    #: its merged card, and the printed entry in the pool keeps ``None``.
    melded_mana_value: int | None = None
    #: What that cost is called on the card -- "evoked", "dash", "blitz".
    evoke_label: str = "evoked"
    #: **Warp {1}{R}**: ``evoke``'s slot -- an alternative mana cost offered
    #: only from hand -- with the exile and the later cast supplied by the rule
    #: rather than by the card. Kept out of ``mana_cost`` for evoke's reason.
    #:
    #: ``None`` on every card Tannuk hands the mechanic to, since the grant is a
    #: static on a *different* permanent: `casting.warp_cost` is what asks both
    #: questions, and nothing reads this field directly.
    warp: ManaCost | None = None
    #: Prowl and spectacle: an alternative cost offered from hand, optionally
    #: only *while* ``alternative_condition`` holds.
    #:
    #: A full `Cost` rather than a bare `ManaCost`, which is what it was until
    #: the pitch spells arrived. Force of Will's alternative cost is "pay 1
    #: life and exile a blue card from your hand" and Pyrokinesis's has no mana
    #: component at all, so there has to be somewhere on the node to hang a
    #: payment that is not mana. `flashback` was the only alternative cost
    #: modelled this way; this is the second, and the two are now charged by
    #: the same halves in the same order -- the mana replaces the printed cost,
    #: and everything else on the node is paid after it (601.2g).
    alternative_cost: Cost | None = None
    #: The condition gating it, in the ordinary `if`-effect language. ``None``
    #: is unconditional, which only a cost charging something other than mana
    #: may be: an unconditional cheaper *mana* price is `evoke`.
    alternative_condition: Any = None
    #: "Emerge {5}{U}{U}".  An alternative cost paid by sacrificing a
    #: creature, reduced by that creature's mana value.  The reduction is
    #: generic-only and clamped at zero, like every other cost reduction
    #: here: it never reaches the coloured pips however large the sacrifice.
    emerge: ManaCost | None = None
    #: Convoke, improvise and delve: `"tap_creatures"`, `"tap_artifacts"` or
    #: `"exile_from_graveyard"`.
    pay_generic_with: str | None = None
    #: Offering: the creature type the sacrifice must be. ``None`` is emerge
    #: proper, which takes any creature.
    emerge_subtype: str | None = None
    #: "This spell costs {X} less to cast."  See `cost_reduction.cost_reduction`, and
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
    #: Mayhem (702.187a): the graveyard cost above is the mayhem price, and it
    #: is offered only while this object is in the graveyard because its
    #: owner discarded it this turn (`TurnLedger.discarded`). The card goes
    #: wherever it normally would, so `graveyard_cast_exiles` is False beside it.
    mayhem: bool = False
    #: Dredge N -- the mill that replaces a draw. See `engine/replacements.py`.
    dredge: int = 0
    #: Toxic N (702.164) -- the total N of every printed toxic instance, read
    #: with `Keyword.TOXIC` by `primitives.damage_player`. Zero means no toxic.
    toxic: int = 0
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
    #: Impending: ``(cost, time counters)``, or ``None`` (702.176a). The cost is
    #: an alternative one offered from hand beside the printed line; the
    #: counters, the type change and the end-step tick are the rule's -- see
    #: `loader._implied_replacements` and `characteristics._compute`.
    impending: tuple[ManaCost, int] | None = None

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
        spec = top_level_mode_spec(self.spell_effects)
        return None if asks_another_player(spec) or is_budgeted(spec) else spec

    def specs_for_modes(
        self, modes: Sequence[int], *, gift_promised: bool = False
    ) -> tuple[TargetSpec, ...]:
        """The target specs a cast of this spell actually declared.

        Card-level specs first, then one mode's specs after another in
        **ascending mode index** -- the order `Game._ask_mode_targets` asked
        them in, and the only order that matters: `targeting.filter_legal`
        splits the stored refs by position, so resolution has to rebuild the
        same list the cast built or every ref lands in the wrong bucket.

        A card with no mode-owned targets returns :attr:`targets` unchanged,
        which is every card in the pool but the modal ones.

        ``gift_promised`` picks the side of the promise the cast was on -- see
        :meth:`targets_for`.
        """
        return _specs_for_modes(
            self.targets_for(gift_promised=gift_promised), self.mode_targets, modes
        )

    def targets_for(self, *, gift_promised: bool) -> tuple[TargetSpec, ...]:
        """The card-level specs a cast declares, on its side of the gift promise.

        601.2b announces the promise and 601.2c declares the targets after it,
        so "if the gift was promised, return target creature card from your
        graveyard" (Consumed by Greed) is a target only the promised cast has.
        :attr:`targets` unchanged for an unpromised cast and for every card
        with no gift-gated spec.
        """
        if gift_promised and self.gift_targets is not None:
            return self.gift_targets
        return self.targets

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
    def any_number_in_deck(self) -> bool:
        """Does the card itself lift the one-copy limit of 903.5b?

        Basic lands are exempt by the rule; a handful of cards -- Persistent
        Petitioners, Relentless Rats, Rat Colony, Shadowborn Apostle, Dragon's
        Approach -- are exempt by their own printed sentence.  This reads that
        sentence, so a deck running twenty Petitioners imports as the legal deck
        it is instead of failing construction.

        *Lifts* it, not merely raises it: :attr:`deck_copy_limit` is the number
        to check a deck against, and this is the case where there is no number.
        """
        match = _ANY_NUMBER.search(self.oracle_text)
        return match is not None and match.group(1).strip() == self.name

    @property
    def can_be_commander(self) -> bool:
        """Does the card's own text let it lead a Commander deck (903.3)?

        "Teferi, Temporal Archmage can be your commander." -- the other
        deck-construction sentence a card can print, read the way
        :attr:`any_number_in_deck` reads its own: matched against the card's
        *own* name, so a card that merely quotes another's text gains nothing.
        A legendary creature needs no sentence; ``validate_deck`` asks this only
        of everything else.
        """
        match = _CAN_BE_COMMANDER.search(self.oracle_text)
        return match is not None and match.group(1).strip() == self.name

    @property
    def deck_copy_limit(self) -> int | None:
        """How many copies of this card a deck may hold; ``None`` for no limit.

        903.5b's whole answer in one place: one copy by default, no limit for a
        basic land or a card whose own text lifts it, and the printed number for
        the two cards that name one -- "A deck can have up to nine cards named
        Nazgûl." and Seven Dwarves' "up to seven".

        The number is matched against the card's *own* name for the same reason
        the unbounded form is: the sentence names the card it applies to, so a
        card that merely quotes another's text -- a copy effect's oracle, a
        reminder -- does not inherit its allowance.  A ceiling this cannot read
        falls back to one copy, which refuses a legal deck rather than admitting
        an illegal one.
        """
        if self.is_basic or self.any_number_in_deck:
            return None
        match = _UP_TO.search(self.oracle_text)
        if match is not None and match.group(2).strip() == self.name:
            return _NUMBER_WORDS.get(match.group(1).lower(), 1)
        return 1

    @property
    def is_aura(self) -> bool:
        return self.is_enchantment and "Aura" in self.subtypes

    @property
    def is_equipment(self) -> bool:
        return self.is_artifact and "Equipment" in self.subtypes

    @property
    def mana_value(self) -> int:
        if self.melded_mana_value is not None:
            return self.melded_mana_value
        return self.mana_cost.mana_value()

    def has_keyword(self, keyword: Keyword | str) -> bool:
        value = keyword.value if isinstance(keyword, Keyword) else keyword
        return value in self.keywords

    def mana_abilities(self) -> tuple[Ability, ...]:
        return tuple(a for a in self.abilities if a.is_mana_ability)

    @property
    def top_level(self) -> int:
        """The highest level this card's level lines reach, or 0 for a non-Class.

        What the client is told a level for: a permanent that prints no
        "{cost}: Level N" has no level worth showing.
        """
        return max((a.becomes_level or 0 for a in self.abilities), default=0)

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


# ----------------------------------------------------------------------
# ward -- an ability the *rules* supply, parameterised by a cost
# ----------------------------------------------------------------------

#: Every rules-supplied ability built so far, addressed by a **negative**
#: ``Ability.index``.
#:
#: A printed ability is found again by indexing the card it is printed on, and a
#: granted one by indexing the granter's ``grantable_abilities`` -- both are a
#: position in a list somebody wrote. Ward is neither: nothing prints the trigger
#: (a card prints the *keyword*, and the reminder text is the rules speaking),
#: and the permanent that has it need not be the permanent that gave it. So it is
#: interned here and addressed by a position in *this* list, negated so that
#: `stack.ability_of` can tell one apart from an index into a card at a glance
#: and without asking the board -- which matters, because by the time a ward
#: trigger resolves the static that granted it may be in a graveyard.
#:
#: Interning rather than rebuilding is what makes `triggers._granter_of`'s
#: identity comparison and `_queue`'s per-(object, index) tallies mean anything:
#: two permanents with ward {1} have the *same* ability object, as two creatures
#: with flying have the same keyword.
_RULES_ABILITIES: list[Ability] = []

#: Interned ward abilities, keyed by their canonicalised cost.
_WARD_ABILITIES: dict[str, Ability] = {}


def prune_cost(spec: Mapping[str, Any]) -> dict[str, Any]:
    """A cost spec with its unset fields dropped.

    A ``CostModel`` dump carries every field it did not use -- ``tap: false``,
    ``discard: 0``, ``mana: null`` -- and ward reads the survivors twice: once to
    key the intern table (so ``{"mana": "{1}"}`` written two ways is one ability)
    and once to decide whether the cost is plain enough to name in a prompt.
    """
    return {k: v for k, v in spec.items() if v not in (None, False, 0, "", (), [], {})}


def _mana_only(cost: Mapping[str, Any]) -> str | None:
    """The mana string when that is the whole cost, else ``None``."""
    return str(cost["mana"]) if set(cost) == {"mana"} else None


def ward_ability(cost: Mapping[str, Any]) -> Ability:
    """The rules-supplied triggered ability a permanent with ward {cost} has.

    "Whenever this permanent becomes the target of a spell or ability an
    opponent controls, counter it unless that player pays <cost>." The reminder
    text on every ward card, and it is the *rules'* sentence rather than the
    card's -- which is why one function builds it for every ward in the game
    instead of each card writing the trigger out.

    ``cost`` is an ordinary ``pay`` spec, the same mapping ``op_may`` charges, so
    ward is not restricted to mana: Vein Ripper's "Ward -- Sacrifice a creature"
    is ``{"sacrifice": {...}}`` and needs nothing here that ward {1} does not.

    The ability is **interned**: the same cost always returns the same object.
    """
    cost = prune_cost(cost)
    key = json.dumps(cost, sort_keys=True, default=str)
    existing = _WARD_ABILITIES.get(key)
    if existing is not None:
        return existing
    mana = _mana_only(cost)
    ability = Ability(
        kind=AbilityKind.TRIGGERED,
        index=-len(_RULES_ABILITIES) - 1,
        text=f"Ward {mana}" if mana else "Ward",
        trigger=TriggerSpec(event="becomes_target", controller="opponent", source="self"),
        effects=(
            {
                "op": "may",
                # The *caster*, not the ability's controller. Ward taxes the
                # player who pointed something at the permanent.
                "player": {"binding": "event_player"},
                "prompt": f"Pay {mana} for ward?" if mana else "Pay the ward cost?",
                "pay": dict(cost),
                "else": [{"op": "counter", "sid": {"binding": "sid"}}],
            },
        ),
        active_zones=(Zone.BATTLEFIELD,),
    )
    _RULES_ABILITIES.append(ability)
    _WARD_ABILITIES[key] = ability
    return ability


def rules_ability(index: int) -> Ability | None:
    """The rules-supplied ability a negative ``ability_index`` names.

    ``None`` for an index nothing was ever interned under, which resolves as a
    no-op rather than raising -- the same contract `stack.ability_of` has for
    every other lookup that comes up empty.
    """
    position = -index - 1
    if 0 <= position < len(_RULES_ABILITIES):
        return _RULES_ABILITIES[position]
    return None


#: Ward {2} on a **cloaked** permanent (701.61a).
#:
#: A rules-supplied ability, like `BESTOW_TARGET` above is a rules-supplied
#: target. It has to be: rule 707.2 says a face-down permanent has *no*
#: abilities, so the ward cannot come from the card underneath -- and it must
#: not, because that card is usually not even a creature. The cloak rule is what
#: grants it, so the engine is what carries it.
#:
#: Now literally `ward_ability({"mana": "{2}"})` rather than a second copy of the
#: same trigger: cloak's ward and a granted one are the same ability at the same
#: price, and were two hand-written twins only because the keyword had nowhere to
#: put its cost.
CLOAK_WARD = ward_ability({"mana": "{2}"})


#: Exalted's trigger (702.83a): "Whenever a creature you control attacks alone,
#: that creature gets +1/+1 until end of turn."
#:
#: Rules-supplied for ward's reason: the sentence is the rules', not the
#: card's, and the printing that made it necessary *grants* the keyword
#: (Merchant of Truth's Clues), so there is no card text to hang a trigger on.
#: `triggers._candidate_abilities` yields it once for every battlefield
#: permanent whose derived keywords include exalted, with that permanent as
#: the source -- so each exalted permanent triggers separately (702.83b), and
#: one that loses its abilities stops listening.
#:
#: "Attacks alone" (506.5) is the sentence the printed exalted cards already
#: carry: `you_attack` with exactly one creature in its ``attackers`` binding.
EXALTED_TRIGGER = Ability(
    kind=AbilityKind.TRIGGERED,
    index=-len(_RULES_ABILITIES) - 1,
    text="Exalted",
    trigger=TriggerSpec(
        event="you_attack",
        controller="you",
        condition={"cmp": "==", "left": {"count": {"binding": "attackers"}}, "right": {"const": 1}},
    ),
    effects=(
        {
            "op": "pump",
            "objects": {"binding": "attackers"},
            "power": {"const": 1},
            "toughness": {"const": 1},
        },
    ),
    active_zones=(Zone.BATTLEFIELD,),
)
_RULES_ABILITIES.append(EXALTED_TRIGGER)


#: Dethrone's trigger (702.105a): "Whenever this creature attacks the player
#: with the most life or tied for most life, put a +1/+1 counter on it."
#:
#: Rules-supplied for exalted's reason: Marchesa, the Black Rose and Dack's
#: Duplicate *grant* dethrone, so the sentence cannot live on the printed card.
#: `triggers._candidate_abilities` yields it once for every battlefield
#: permanent whose derived keywords include dethrone, with that permanent as
#: the source.
#:
#: "The player with the most life" is the `defending: "most_life"` clause, so
#: it is part of the trigger event and not an intervening-if: the life totals
#: are compared as attackers are declared and never again, and a counter is put
#: on the creature even if the defender's life total changes before the
#: ability resolves.
DETHRONE_TRIGGER = Ability(
    kind=AbilityKind.TRIGGERED,
    index=-len(_RULES_ABILITIES) - 1,
    text="Dethrone",
    trigger=TriggerSpec(event="attacks", controller="you", source="self", defending="most_life"),
    effects=(
        {
            "op": "add_counters",
            "counter": "+1/+1",
            "amount": {"const": 1},
            "objects": {"zone": "battlefield", "self_only": True},
        },
    ),
    active_zones=(Zone.BATTLEFIELD,),
)
_RULES_ABILITIES.append(DETHRONE_TRIGGER)


#: Melee's trigger (702.121a): "Whenever this creature attacks, it gets +1/+1
#: until end of turn for each opponent you attacked with a creature this
#: combat."
#:
#: Rules-supplied for exalted's reason: Titania, Proud Pummeler *grants*
#: melee, so the sentence cannot live on the printed card.
#: `triggers._candidate_abilities` yields it once for every battlefield
#: permanent whose derived keywords include melee, with that permanent as the
#: source.
#:
#: The bonus is counted as the ability resolves (702.121b), off
#: `TurnLedger.opponents_attacked_this_combat` -- the opponents its controller
#: declared attackers against in the combat in progress, a planeswalker's or
#: battle's controller included -- so an attacker removed before resolution
#: still counts its opponent, and a second combat counts afresh.
MELEE_TRIGGER = Ability(
    kind=AbilityKind.TRIGGERED,
    index=-len(_RULES_ABILITIES) - 1,
    text="Melee",
    trigger=TriggerSpec(event="attacks", controller="you", source="self"),
    effects=(
        {
            "op": "pump",
            "objects": {"zone": "battlefield", "self_only": True},
            "power": {"opponents_attacked_this_combat": "you"},
            "toughness": {"opponents_attacked_this_combat": "you"},
        },
    ),
    active_zones=(Zone.BATTLEFIELD,),
)
_RULES_ABILITIES.append(MELEE_TRIGGER)
