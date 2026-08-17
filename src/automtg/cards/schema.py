"""Pydantic models mirroring the card JSON format.

These models are the *contract* every card file must satisfy.  They are
deliberately strict (``extra="forbid"``) so that a misspelled field is caught
rather than silently ignored -- the failure mode that would otherwise produce a
card that looks implemented but does nothing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Strict = ConfigDict(extra="forbid")


class CostModel(BaseModel):
    """The cost of an activated ability."""

    model_config = Strict

    mana: str | None = None
    tap: bool = False
    untap: bool = False
    sacrifice: dict[str, Any] | None = None
    #: "Return a land you control to its owner's hand" -- Meloku and Trench
    #: Behemoth. A selector over the battlefield, like ``sacrifice``, and
    #: deliberately not that one: sacrificing graveyards the land, which
    #: breaks the replay-for-landfall loop those cards are built on.
    return_to_hand: dict[str, Any] | None = None
    #: "Tap five untapped Vampires you control" -- Captivating Vampire. A
    #: selector over the battlefield with a ``count``, and the permanents come
    #: back untapped next untap step, which is what separates it from
    #: ``sacrifice`` and ``return_to_hand``. Not the same as ``tap``, which is
    #: the ``{T}`` symbol and only ever taps the source.
    #: ``tap_permanents`` also carries **crew**'s ``total_power``: "tap any
    #: number of untapped creatures you control with total power N or greater".
    #: A sum rather than a headcount, read off *derived* power, so one 4/4 crews
    #: a Vehicle that four 0/1s cannot and an anthem changes who can.
    tap_permanents: dict[str, Any] | None = None
    discard: int = 0
    #: Narrows what ``discard`` may throw away -- "discarding a land card".
    #: A selector over the hand; omitted, any card will do.
    discard_selector: dict[str, Any] | None = None
    #: Cycling's "Discard this card": the source discards itself, no choice.
    discard_self: bool = False
    #: Usually an integer. A mapping is a value expression evaluated when the
    #: cost is paid -- War Room's "pay life equal to the number of colors in
    #: your commanders' color identity", the only life cost that is not fixed
    #: when the card is written.
    pay_life: int | dict[str, Any] = 0
    remove_counters: dict[str, Any] | None = None
    #: A loyalty cost (606.2), signed: `+1`, `0`, `-3`. Not `remove_counters`,
    #: which only ever takes them off -- a plus ability *adds* loyalty, and it
    #: is a cost rather than an effect, so it is paid whether or not the ability
    #: resolves and cannot be responded to in between.
    loyalty: int | None = None
    exile_from_graveyard: dict[str, Any] | None = None
    #: How much less **this cost node** costs -- the same language a card's
    #: `cost_reduction` speaks, read by `costs.reduction_amount`:
    #: ``{"count": {filter}}`` for "{1} less to activate for each Vampire you
    #: control", ``{"total_power": {filter}}``, or ``{"amount": N}`` for a flat
    #: "{3} less" -- which needs a ``condition``, since an ungated flat reduction
    #: is only a cheaper printed cost.
    #:
    #: ``condition`` is an ordinary condition, narrowed by the loader to the heads
    #: that can be answered *at pricing time*: Crown of Gondor's "Equip {4}. This
    #: ability costs {3} less to activate if you're the monarch."
    #:
    #: Two cost nodes read it. On an activated ability's ``cost`` it is applied by
    #: `costs.ability_mana`, which the *activation* path goes through -- the
    #: card-level field never reaches there. On ``flashback``/``graveyard_cost``
    #: it is the "costs {X} less to cast **this way**" rider, applied by
    #: `costs.variant_reduction` from the flashback branch of
    #: `legality._cast_variant` and `game._cast` only, so it discounts the
    #: graveyard cast and not the printed one. Refused on ``additional_cost``,
    #: whose mana is folded into the spell's price and never priced on its own.
    #:
    #: Generic only and clamped at zero, like every other reduction.
    mana_reduction: dict[str, Any] | None = None
    #: Cumulative upkeep: "pay its upkeep cost **for each age counter on it**".
    #: A value expression multiplying the ``mana`` half, and the only part of a
    #: cost that is not fixed when the card is written. Read only where an
    #: ``EffectContext`` exists to evaluate it -- i.e. by `may`'s `pay`, not by
    #: an activated ability's cost, which is charged before any effect runs.
    times: dict[str, Any] | int | None = None


class TargetModel(BaseModel):
    """One target requirement."""

    model_config = Strict

    id: str
    kind: Literal["permanent", "player", "spell", "card_in_graveyard", "any"]
    selector: dict[str, Any] = Field(default_factory=dict)
    #: How many. ``"any"`` is "any number of target …" -- a size the *caster*
    #: chooses, including zero, rather than a number written into the card.
    #: `count: N, optional: true` is not the same thing and cannot stand in: it
    #: means "exactly N, or none", forbidding every size between 1 and N-1.
    count: int | Literal["any"] = 1
    #: "**For each player**, exile up to one target nonland permanent that
    #: player controls." The same set of legal choices as "any number of target
    #: nonland permanents, no two controlled by the same player" -- which is
    #: what this says, and why it is a constraint on the *combination* rather
    #: than one spec per seat. Requires ``count: "any"``.
    one_per_player: bool = False
    optional: bool = False


class TriggerModel(BaseModel):
    """When a triggered ability fires."""

    model_config = Strict

    event: str
    controller: Literal["you", "opponent", "any"] = "you"
    source: Literal["self"] | None = None
    filter: dict[str, Any] | None = None
    condition: dict[str, Any] | None = None
    #: For ``attacks``: whom the creature is attacking.  ``controller`` says
    #: whose creature is swinging, which is a different question -- "attacks you"
    #: needs this one.
    defending: Literal["you", "opponent", "any"] | None = None
    #: "…if it wasn't put onto the battlefield with this ability."  Names the
    #: ``cause`` this trigger refuses to fire on, which is how an ability that
    #: puts permanents onto the battlefield avoids triggering on its own output.
    not_cause: str | None = None
    #: For ``counter_placed``: which kind of counter this cares about.  Without
    #: it "whenever a +1/+1 counter is put on this creature" also fires on
    #: charge, slumber and -1/-1 counters, all of which the shipped pool places.
    counter: str | None = None
    #: "This ability triggers only once each turn." A per-permanent cap on how
    #: many times this ability may queue in one turn.
    max_per_turn: int | None = None


class AbilityModel(BaseModel):
    """An activated, triggered or static ability.

    Static abilities flatten their parameters onto the ability object
    (``effect``, ``affects``, ``power``, ...) rather than nesting them, which is
    what makes the card files readable.
    """

    model_config = Strict

    kind: Literal["activated", "triggered", "static"]
    text: str = ""

    # activated
    cost: CostModel | None = None
    is_mana_ability: bool = False
    #: "Spend this mana only to cast a creature spell."  A card type, lowercased.
    #: A *list* is the "and/or" form -- "Spend this mana only to cast Vampire,
    #: Cleric, and/or Demon spells" -- and its entries may be subtypes as well as
    #: types, matched as an any-of.
    mana_restriction: str | list[str] | None = None
    sorcery_speed_only: bool = False
    #: This activated ability *is* the cycling ability, so paying for it emits
    #: the `cycle` event a "When you cycle this card" trigger listens for.
    #: Declared rather than inferred: "Discard this card: draw" is a shape other
    #: cards print without being cycling, and a trigger firing on those would be
    #: a different card.
    is_cycling: bool = False
    #: **Forecast**: "Activate only during your upkeep, and only once each turn."
    #: Two restrictions and they only make sense together -- an ability offered
    #: from *hand* that does not remove its source is an infinite engine, and
    #: what makes forecast safe is that it may be activated once. So
    #: ``once_each_turn`` is the third satisfier of the outside-the-battlefield
    #: guard, beside cycling's self-discard and unearth's self-move.
    #:
    #: ``activate_steps`` restricts *when*; "your" is the ordinary
    #: ``condition: {"is_your_turn": true}`` and is not folded in here, because
    #: they are separable and one card prints only the timing half.
    activate_steps: list[
        Literal["upkeep", "draw_step", "precombat_main", "end_step"]
    ] = Field(default_factory=list)
    once_each_turn: bool = False

    # triggered
    trigger: TriggerModel | None = None
    active_zones: list[
        Literal["battlefield", "command", "graveyard", "hand", "exile", "stack"]
    ] = Field(
        default_factory=lambda: ["battlefield"]
    )

    # activated + triggered
    targets: list[TargetModel] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)

    # static
    effect: str | None = None
    affects: dict[str, Any] | None = None
    #: "Creature spells with flying you cast cost {1} less." Filters a *card
    #: being cast* by its printed face, which is a different question from
    #: `affects` (which picks out permanents on the battlefield).
    affects_spells: dict[str, Any] | None = None
    affects_player: Literal["you", "opponent", "any"] | None = None
    power: Any = None
    toughness: Any = None
    keywords: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    amount: Any = None
    #: Two different clauses sharing one field, because the card files read
    #: better for it and the two can never collide -- an ability is static or
    #: activated, never both.
    #:
    #: On a **static**: the "as long as..." clause. A condition tree over
    #: pipeline *inputs* only -- counters on the source, printed
    #: characteristics, zone contents, whose turn it is. See
    #: ``characteristics._condition_met``.
    #:
    #: On an **activated** ability: "Activate only if you control five or more
    #: Vampires." Checked by ``legality`` before the ability is offered, in the
    #: *full* condition language, because nothing is being computed here that
    #: another condition could depend on.
    condition: dict[str, Any] | None = None
    #: The qualities a ``protection`` static protects from.  Three lists rather
    #: than one so the card file reads like the card: "protection from
    #: planeswalkers and from Wizards" is a type and a subtype, not two nouns.
    from_types: list[str] = Field(default_factory=list)
    from_subtypes: list[str] = Field(default_factory=list)
    from_colors: list[str] = Field(default_factory=list)
    #: ``block_restriction``: which would-be blockers are refused. A static
    #: filter over the *blocker*, so "can't be blocked by Humans" is
    #: ``{"subtypes": ["Human"]}``.
    blockers: dict[str, Any] | None = None
    #: ``block_restriction``: Tromokratis' "can't be blocked unless all
    #: creatures defending player controls block it". Judged on the whole
    #: declaration rather than per pair, so it cannot be a ``blockers``
    #: filter.
    require_all: bool = False


class ReplacementModel(BaseModel):
    """One of the four whitelisted replacement effects."""

    model_config = Strict

    event: Literal["self_enters", "self_enters_tapped", "self_enters_with_counters"]
    modify: dict[str, Any] = Field(default_factory=dict)
    counter: str | None = None
    amount: int = 1
    #: Applied only when this holds, evaluated as the permanent enters with the
    #: entering object as the source -- so `exclude_self` means "other lands you
    #: control" and counts the board the land is arriving on.  The printed
    #: sentence is "enters tapped **unless** you control a Mountain", so the
    #: card writes the negation: a condition here says when the replacement
    #: *applies*, matching every other `condition` in the DSL.
    condition: dict[str, Any] | None = None


class CardModel(BaseModel):
    """One card definition."""

    model_config = Strict

    id: str
    name: str
    oracle_text: str = ""
    mana_cost: str | None = None
    supertypes: list[str] = Field(default_factory=list)
    types: list[str]
    subtypes: list[str] = Field(default_factory=list)
    power: int | None = None
    toughness: int | None = None
    #: Starting loyalty (306.5b). Written as a number on the card and compiled
    #: into a `self_enters_with_counters` replacement, so nothing new runs when
    #: a planeswalker arrives -- loyalty *is* counters, and every reader the
    #: engine already has for counters is a reader for loyalty.
    loyalty: int | None = None
    keywords: list[str] = Field(default_factory=list)
    colors: list[str] | None = None
    color_identity: list[str] | None = None
    targets: list[TargetModel] = Field(default_factory=list)
    spell_effects: list[dict[str, Any]] = Field(default_factory=list)
    replacements: list[ReplacementModel] = Field(default_factory=list)
    abilities: list[AbilityModel] = Field(default_factory=list)
    #: Abilities this card grants to *another* permanent, referenced by index
    #: from a ``grant_ability`` effect.  Separate from ``abilities`` because the
    #: card itself does not have them.
    grantable_abilities: list[AbilityModel] = Field(default_factory=list)
    is_token: bool = False
    #: The id of this card's **back face**, for a transforming double-faced
    #: card. The back face is an ordinary card entry in the same pool, marked
    #: with no mana cost -- it is never cast, never shuffled into a deck, and
    #: exists only as the face a permanent shows once it has transformed.
    back_face: str | None = None
    #: The id of this card's **second castable face** — the Adventure half, the
    #: Aftermath half, the other half of a split card. An ordinary card entry in
    #: the same pool with its own name, mana cost, type line and effects,
    #: exactly as ``back_face`` is.
    #:
    #: The difference from a back face is the whole reason this is a second
    #: field rather than a reuse: a back face is one you **turn over**, and it
    #: is never cast, never drawn and never shuffled into a deck. A second face
    #: is the one thing a back face is not — a *second spell* the same card in
    #: the same zone may be cast as, at a different price, with a different type
    #: line, going somewhere different afterwards.
    second_face: str | None = None
    #: Where the second face may be cast from. Split halves and Adventures are
    #: cast from hand; an **Aftermath** half may be cast *only* from the
    #: graveyard (702.127a), which is the whole of what that keyword says.
    second_face_zone: Literal["hand", "graveyard"] = "hand"
    #: **Fuse** (702.102a): "You may cast one or both halves of this card from
    #: your hand." The third cast line on a split card, and the only one that is
    #: **one spell made of two faces** -- both costs paid together, both halves'
    #: targets chosen together, both halves' effects run on one resolution.
    fuse: bool = False
    #: **Adventure** (715.3c and 715.3d): the card is exiled as the Adventure spell
    #: resolves, and its owner may then cast the *front* face from exile.
    #:
    #: Off for a split card, whose halves are done with each other, and off for
    #: aftermath, which exiles for good. Set it and the second face becomes an
    #: Adventure rather than merely a second half — so this is the flag that
    #: separates the three keywords sharing the field above.
    adventure: bool = False
    #: "This spell can't be countered."
    uncounterable: bool = False
    #: Split second (702.61a): "As long as this spell is on the stack, players
    #: can't cast spells or activate abilities that aren't mana abilities."
    #: A card-level flag rather than an ability, because it is true of the
    #: *spell on the stack* and there is no permanent for it to sit on.
    split_second: bool = False
    #: **Buyback**: "You may pay an additional cost as you cast this spell. If
    #: you do, put it into your hand instead of your graveyard as it resolves."
    #:
    #: The additional cost is the ordinary `kicker` -- buyback *is* a kicker
    #: with a rider -- and this is the rider. Set it and the card's kicker
    #: becomes a buyback cost.
    buyback: bool = False
    #: **Rebound** (702.87a): "If you cast this spell from your hand, exile it as
    #: it resolves. At the beginning of your next upkeep, you may cast this card
    #: from exile without paying its mana cost."
    #:
    #: The third rider on the same slot as flashback's exile and buyback's hand,
    #: and like both it only ever replaces the *graveyard*. "From your hand" is
    #: the loop guard rather than flavour: the free cast happens from exile.
    rebound: bool = False
    #: **Overload** (702.96a): "You may cast this spell for its overload cost.
    #: If you do, change its text by replacing all instances of 'target' with
    #: 'each'." A third cast variant beside kicked and evoked, and the text
    #: change is written by the card as an `if` on `{"overloaded": true}` --
    #: there is no way to rewrite a printed sentence, and the two halves really
    #: are two different effects ("destroy target artifact" / "destroy each
    #: artifact"). An overloaded spell is cast with **no targets**, so every
    #: target the card declares must be `optional`.
    overload: str | None = None
    #: An **additional cost** paid as the spell is cast from hand -- casualty,
    #: replicate, and the "as an additional cost, sacrifice an artifact" family.
    #: A full ``CostModel``, unlike `kicker`, which is mana-only.
    #:
    #: ``additional_optional`` makes it "you **may**", and
    #: ``additional_repeatable`` makes it payable "any number of times"
    #: (replicate). Legality offers one cast line per number of times paid,
    #: exactly as convoke offers one per number convoked -- the count changes
    #: the price and is the player's to choose. How many times it was paid is
    #: read back with ``{"additional_paid": true}``.
    additional_cost: CostModel | None = None
    additional_optional: bool = False
    additional_repeatable: bool = False
    #: What that additional cost is called on screen. `kicker` is the engine's
    #: name for the general thing; "buyback" and "kicker" are two words for it,
    #: and an action reading "(kicked)" on a buyback card is wrong about what
    #: the player is buying -- the same problem `evoke_label` solves.
    kicker_label: str = "kicked"
    #: "Kicker {1}{U}" -- an additional cost that may be paid as the spell is
    #: cast.  What being kicked then *does* is an ordinary ``if`` on the
    #: ``{"kicked": true}`` condition, so no card needs new effect vocabulary.
    kicker: str | None = None
    #: **Bestow {5}{W}** (702.103a): "If you cast this card for its bestow cost,
    #: it's an Aura spell with enchant creature. It becomes a creature again if
    #: it's not attached to a creature."
    #:
    #: An alternative cost like ``evoke``, and unlike every other one it changes
    #: what the spell **targets**: the "enchant creature" is fixed by the rule,
    #: not by the card, so no bestow card writes a target of its own.
    bestow: str | None = None
    #: **Meld** (701.37): "exile them, then meld them into <name>". The id of the
    #: card this one melds *with*, and the id of the single oversized card the
    #: two become. The melded entry is an ordinary card in the same pool, and
    #: like a back face it is not a card anybody owns a copy of.
    #:
    #: Only the half that prints the meld trigger needs these -- Bruna carries
    #: it and Gisela does not -- so they are not required to be symmetric.
    melds_with: str | None = None
    melds_into: str | None = None
    #: **Mutate {1}{G}** (702.140a): "If you cast this spell for its mutate cost,
    #: put it over or under target non-Human creature you own. They mutate into
    #: the creature on top plus all abilities from under it."
    #:
    #: An alternative cost like ``bestow``, with a target the rule supplies
    #: rather than the card. What makes it different from every other keyword is
    #: what it *lands* as: not a permanent of its own, but a **pile** merged
    #: into one that already exists.
    mutate: str | None = None
    #: "Evoke {2}{U}" -- an *alternative* cost that replaces the printed one
    #: while casting from hand.  Subtractive where kicker is additive, and the
    #: printed mana value is unchanged: a Mulldrifter evoked is still a
    #: five-drop for anything that counts mana value.
    evoke: str | None = None
    #: What to call that cost on screen. ``evoke`` is the engine's name for a
    #: general thing — an alternative mana cost offered from hand, plus a flag
    #: the card can read back — and **dash** and **blitz** are the same
    #: mechanism under different words. Without this the action list offers
    #: "Cast Goblin Rabblemaster (evoked)" for a card that says dash, which is
    #: a lie about what the player is doing.
    #:
    #: It is not only cosmetic: the loader's price guard reads it. Evoke proper
    #: buys nothing but the discount, so an evoke cost above the printed one is
    #: a line nobody takes and is refused. Dash buys haste and the enters
    #: trigger for a turn, so a *renamed* cost may be the dearer one — Riders of
    #: Rohan is printed {3}{R}{W} with dash {4}{R}{W}. Equal to the printed cost
    #: stays refused under every label: that is one cast offered twice.
    evoke_label: str = "evoked"
    #: ``{"mana": "{R}", "condition": {...}}`` -- **prowl** and **spectacle**.
    #: An alternative cost like evoke, and unlike evoke it is only *offered*
    #: when the condition holds: "you may cast this for its spectacle cost if
    #: an opponent lost life this turn".
    #:
    #: A field of its own rather than a condition bolted onto ``evoke``,
    #: because evoke's flag is read back on the permanent by "it's sacrificed
    #: when it enters" -- a spectacle spell reporting `cast_evoked` would be a
    #: card quietly claiming to have been evoked.
    alternative_cost: dict[str, Any] | None = None
    #: "Emerge {5}{U}{U}" -- an alternative cost that sacrifices a creature
    #: and is then reduced by that creature's mana value. Like ``evoke`` it
    #: replaces the printed cost; unlike it, how much you pay depends on
    #: what you sacrifice, which is why it cannot be a fixed ManaCost alone.
    emerge: str | None = None
    #: **Convoke** and **delve**: a way to pay part of the *generic* cost with
    #: something other than mana. ``"tap_creatures"`` taps creatures you
    #: control; ``"exile_from_graveyard"`` exiles cards from your graveyard.
    #: One cast line per number spent, the way ``emerge`` offers one per
    #: victim, because the number changes the price and is the player's to
    #: choose.
    #:
    #: Generic only, and clamped at what the spell actually costs. Convoke's
    #: "or one mana of that creature's colour" is a documented simplification:
    #: it is the same trade `cost_reduction` already makes, and it bites only
    #: on a spell whose coloured pips a creature could have paid.
    pay_generic_with: Literal["tap_creatures", "exile_from_graveyard"] | None = None
    #: **Offering**: the creature type the emerge sacrifice must be —
    #: "sacrifice a Goblin". Offering is emerge with the fodder narrowed and
    #: the timing widened, so it is a qualifier on that field rather than a
    #: field of its own.
    emerge_subtype: str | None = None
    #: "This spell costs {X} less to cast, where X is the total power of
    #: creatures you control."  Reduces the *generic* part of the cost only,
    #: never below zero and never the coloured pips -- which is what the rules
    #: say and also the only thing the payment solver could honour.
    cost_reduction: dict[str, Any] | None = None
    #: "Retrace -- you may cast this card from your graveyard by discarding a
    #: land card in addition to paying its other costs."  A whole extra way to
    #: cast the card, so it is a card-level field rather than an ability.
    retrace: bool = False
    #: Ascend: "If you control ten or more permanents, you get the
    #: city's blessing for the rest of the game." A bare keyword with
    #: no parameters, so a card-level flag rather than an ability.
    ascend: bool = False
    #: "Flashback {1}{U}, Pay 3 life" -- an alternative cost offered only from
    #: the owner's graveyard. A full cost, not just mana, because Deep Analysis
    #: charges life too. Card-level like ``retrace``, because it changes which
    #: zone the card may be cast from.
    flashback: CostModel | None = None
    #: The same field under the name the general mechanic deserves. Flashback,
    #: escape and jump-start are one capability -- an alternative cost offered
    #: only from the owner's graveyard -- and only ``flashback`` shipped first,
    #: so a card with escape on it should not have to say "flashback". Exactly
    #: one of the two may be given.
    graveyard_cost: CostModel | None = None
    #: Where the card goes when it finishes resolving, having been cast from a
    #: graveyard. The only thing that separates the three keywords:
    #:
    #: ``exile``      flashback and jump-start -- once only.
    #: ``graveyard``  **escape**, which is reusable, and which is the whole
    #:                reason this is a field rather than a hard-coded exile.
    graveyard_cast: Literal["exile", "graveyard"] = "exile"
    #: **Disturb** (702.146a): "You may cast this card **transformed** from your
    #: graveyard for its disturb cost." The graveyard cast is `graveyard_cost`,
    #: already shipped for flashback; this is the one bit disturb adds -- the
    #: card is the *back* face from the moment it goes on the stack, so its
    #: name, types and effects are the back face's and not the front's.
    graveyard_cast_transformed: bool = False
    #: **Dredge N** (702.51a): "If you would draw a card, you may instead return
    #: this card from your graveyard to your hand and mill N." The number is the
    #: mill, and it is also the price -- a player with fewer than N cards left is
    #: not offered the replacement at all.
    dredge: int = 0
    #: **Madness** (702.35a): "If you would discard this card, exile it instead.
    #: Then you may cast it for its madness cost." The exile happens whether or
    #: not the cast is taken.
    madness: str | None = None
    #: **Miracle** (702.94a): "You may cast this card for its miracle cost when
    #: you draw it, if it's the first card you drew this turn."
    miracle: str | None = None
    #: **Foretell** (702.143a): "During your turn, you may pay {2} and exile this
    #: card from your hand face down. Cast it on a later turn for its foretell
    #: cost." This names the *later* cost; the {2} is fixed by the rule.
    #:
    #: The nearest shipped shape is suspend, and it is near enough to share the
    #: special action: both exile a card from hand to be cast later, neither
    #: uses the stack, and neither can be countered.
    foretell: str | None = None
    #: **Epic** (702.50a): "Spend the rest of the game casting no spells. At the
    #: beginning of each of your upkeeps, copy this spell except for its epic
    #: ability."
    #:
    #: A card-level flag rather than an ability, for `split_second`'s reason: it
    #: is a fact about the *spell* and about the player who cast it, and there
    #: is no permanent for it to sit on -- an epic spell is in a graveyard for
    #: the rest of the game while the restriction and the copies go on.
    epic: bool = False
    #: **Splice onto Arcane** (702.47a): "As you cast an Arcane spell, you may
    #: reveal this card from your hand and pay its splice cost. If you do, add
    #: this card's effects to that spell."
    #:
    #: The only keyword that changes what a **different** card does, so it is
    #: paid and recorded as the host goes on the stack and its effects run after
    #: the host's on resolution. ``onto`` is the subtype it may be spliced onto.
    #: **Morph** (702.37a) / **megamorph**: "You may cast this card face down as
    #: a 2/2 creature for {3}. Turn it face up any time for its morph cost."
    #: This names the *turn-face-up* price; the {3} is fixed by the rule.
    morph: str | None = None
    #: Megamorph: the creature turns up with a +1/+1 counter (702.109a).
    morph_counter: bool = False
    splice: str | None = None
    splice_onto: str = "Arcane"
    #: ``{"cost": "{G}", "counters": 2}`` -- "Suspend 2—{G}".  Another whole way
    #: to play the card, so like ``retrace`` it is card-level rather than an
    #: ability: the card has no suspend ability while it sits in your hand.
    suspend: dict[str, Any] | None = None
    #: Who wrote this card.  ``""`` means a person did.  ``"auto"`` means
    #: ``automtg.cards.authoring`` did, and it only got here by clearing the six
    #: gates in ``authoring/verify.py`` -- including one that casts it and checks
    #: the board.  Provenance rather than rules: the loader ignores it, and it
    #: exists so a diff shows at a glance which cards a machine wrote.
    source: str = ""

    @field_validator("id")
    @classmethod
    def _snake_case_id(cls, value: str) -> str:
        if not value or not all(c.isalnum() or c == "_" for c in value):
            raise ValueError(f"card id {value!r} must be snake_case alphanumeric")
        return value


class DeckEntryModel(BaseModel):
    model_config = Strict

    id: str
    qty: int = 1


class SubstitutionModel(BaseModel):
    """A card swapped out because its text is not expressible in the DSL."""

    model_config = Strict

    slot: str
    replaced_with: str
    reason: str


class DeckRatingsModel(BaseModel):
    """How a deck plays, on five 1-4 scales.

    Editorial, not derived: nothing in a card list tells you a deck is hard to
    pilot.  An imported deck simply has none of this, and the client draws that
    state honestly rather than inventing numbers.
    """

    model_config = Strict

    speed: int = Field(ge=1, le=4)
    complexity: int = Field(ge=1, le=4)
    interaction: int = Field(ge=1, le=4)
    resilience: int = Field(ge=1, le=4)
    pilot: int = Field(ge=1, le=4)


class SignatureCardModel(BaseModel):
    """A card the deck is *about*, and one line on why."""

    model_config = Strict

    card_id: str
    why: str


class DeckModel(BaseModel):
    """One 100-card Commander deck list."""

    model_config = Strict

    id: str
    name: str
    commanders: list[str]
    color_identity: list[str] = Field(default_factory=list)
    cards: list[DeckEntryModel]
    substitutions: list[SubstitutionModel] = Field(default_factory=list)
    notes: str = ""
    #: Where the list came from.  Defaulted so the two committed precons stay
    #: valid untouched -- the model is ``extra="forbid"``, so a required field
    #: here would have broken every deck file in the repository.
    source: Literal["precon", "moxfield"] = "precon"

    # -- editorial metadata, for the lobby's deck catalogue ----------------
    # All optional and all defaulted, for the same ``extra="forbid"`` reason as
    # ``source``: an imported deck has none of it and must still load.
    tags: list[str] = Field(default_factory=list)
    ratings: DeckRatingsModel | None = None
    strategy: str = ""
    signature: list[SignatureCardModel] = Field(default_factory=list)
