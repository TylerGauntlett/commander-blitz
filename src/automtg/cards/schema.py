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
    #: "Untap two tapped creatures you control" -- Halo Fountain. The mirror of
    #: ``tap_permanents``: a selector over the battlefield with a ``count``,
    #: whose pool is forced to ``tapped: True`` instead of ``tapped: False``.
    #: Not ``untap``, which is the ``{Q}`` symbol and only ever untaps the
    #: source -- Halo Fountain taps *itself* and untaps *other* creatures, so
    #: the two appear on the same cost and mean different permanents. No
    #: ``total_power``: crew is a printed sum, and no printed line unbends a
    #: board by power.
    untap_permanents: dict[str, Any] | None = None
    #: "**Mill a card**" as part of an activation cost -- Millikin, Deranged
    #: Assistant, The Warring Triad. Cards come off the top of the *activating*
    #: player's library, so there is nothing to choose and no selector.
    #:
    #: Deliberately not the ``mill`` **op**. Writing it in ``effects`` moves the
    #: payment to resolution, so the ability could be activated and responded to
    #: before the cards moved -- which is observable on The Warring Triad, whose
    #: other ability counts cards in that same graveyard. It is doubly wrong on
    #: Millikin, a mana ability, since a mana ability may contain only
    #: ``add_mana``.
    mill: int = 0
    discard: int = 0
    #: Narrows what ``discard`` may throw away -- "discarding a land card".
    #: A selector over the hand; omitted, any card will do.
    discard_selector: dict[str, Any] | None = None
    #: Cycling's "Discard this card": the source discards itself, no choice.
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
    #: "**Exile a blue card from your hand**" -- Force of Will's pitch. A
    #: selector over the payer's own hand with an optional ``count``, and the
    #: exile twin of ``discard`` + ``discard_selector``.
    #:
    #: Deliberately not that pair: a discarded card is in the graveyard, where
    #: delirium, threshold, Tarmogoyf and every reanimation spell can see it.
    #: The printed pitch costs exile, and the difference is the whole reason
    #: they are priced the way they are.
    #:
    #: The source is never its own fodder -- see `costs._hand_exile_pool`.
    exile_from_hand: dict[str, Any] | None = None
    #: "**Exile this card from your hand**: Add {R}" -- Simian Spirit Guide.
    #: The exile twin of ``discard_self``, and a separate flag from
    #: ``exile_self`` because that one is "Exile this artifact" and
    #: `costs.can_pay` requires its source to be on the *battlefield*. Phoenix
    #: Down keeps that stricter check; this one requires the source to be in
    #: the activating player's hand instead.
    #:
    #: Not ``exile_from_hand`` narrowed by a selector, for the same reason
    #: cycling is not ``discard: 1``: the pool would offer the whole hand and
    #: the player could "activate" the Spirit Guide by exiling something else
    #: and keeping it.
    exile_self_from_hand: bool = False
    #: Usually an integer. A mapping is a value expression evaluated when the
    #: cost is paid -- War Room's "pay life equal to the number of colors in
    #: your commanders' color identity", the only life cost that is not fixed
    #: when the card is written.
    pay_life: int | dict[str, Any] = 0
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
    #: "X is the mana value of that card" -- Soul Foundry. A value expression
    #: that **defines** X instead of the player announcing it: evaluated when
    #: the ability is activated, and the whole of what it decides is what the
    #: ``{X}`` in this cost's ``mana`` is worth.
    #:
    #: Read by `costs.ability_mana`, which both `costs.can_pay` and `costs.pay`
    #: go through, so the ability is *offered* at exactly the X it will be
    #: *charged* -- and by `game._ask_x`, which returns it rather than putting a
    #: ``CHOOSE_X`` decision to the player. Without it a `{"mana": "{X}"}` cost
    #: is an ordinary announced X (601.2b) and the player says zero, which on an
    #: imprint card copies a Griselbrand for nothing.
    #:
    #: Only on an **activated ability's** cost, and only beside a ``mana`` cost
    #: containing ``{X}``; refused anywhere else, because nowhere else prices its
    #: mana through `ability_mana` and a field that is read in one cost node and
    #: ignored in another is a discount nobody wrote.
    #:
    #: Not ``times`` below, which multiplies the whole mana half rather than
    #: filling in one symbol, and is read only by `may`'s ``pay``.
    x_value: dict[str, Any] | None = None
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
    #: ``"spell_or_permanent"`` is the one kind whose pool spans two zones at
    #: once -- "target **spell or nonland permanent** an opponent controls"
    #: (Sink into Stupor). It is one instance of the word "target", so it is one
    #: spec: writing two, one of each kind, is a card that targets twice and
    #: needs both to be legal. The `selector` narrows both halves, since the
    #: printed clause ("nonland", "an opponent controls") is meant to.
    kind: Literal[
        "permanent",
        "player",
        "spell",
        "card_in_graveyard",
        "card_in_exile",
        "any",
        "spell_or_permanent",
    ]
    #: "…any number of target creature cards **with total mana value 6 or
    #: less**" (Phoenix, Warden of Fire). A cap on the picks **together**, not
    #: on each of them: no selector clause can say it, because every clause is
    #: evaluated against one candidate in isolation and `mana_value: {"op":
    #: "<=", "value": 6}` is a different and much wider card -- six one-drops
    #: pass it and are six mana of creatures.
    total_mana_value: int | None = None
    selector: dict[str, Any] = Field(default_factory=dict)
    #: How many. ``"any"`` is "any number of target …" -- a size the *caster*
    #: chooses, including zero, rather than a number written into the card.
    #: `count: N, optional: true` is not the same thing and cannot stand in: it
    #: means "exactly N, or none", forbidding every size between 1 and N-1.
    #:
    #: A **value expression** is the third form: "return up to X target creature
    #: cards…, where X is the number of times this enchantment was kicked" is
    #: ``{"additional_paid": true}``, evaluated when the targets are declared.
    #: Only on an *ability's* targets -- see `loader.targets._compile_targets`, which
    #: refuses one on a card's own `targets` because a spell's are chosen before
    #: it has been paid for and the expression would read zero.
    count: int | Literal["any"] | dict[str, Any] = 1
    #: "Return **up to** X target creature cards." The `count` is a ceiling and
    #: every size from zero through it is legal, which is the one reading none
    #: of the three above can give: a number forces exactly that many,
    #: `optional` makes it "exactly N or none", and ``"any"`` has no ceiling.
    #: Pairs with either a literal or a value expression.
    up_to: bool = False
    #: "**For each player**, exile up to one target nonland permanent that
    #: player controls." The same set of legal choices as "any number of target
    #: nonland permanents, no two controlled by the same player" -- which is
    #: what this says, and why it is a constraint on the *combination* rather
    #: than one spec per seat. Requires ``count: "any"``.
    one_per_player: bool = False
    optional: bool = False
    #: "Choose up to two. Return those cards from your graveyard to your hand.
    #: * Target artifact card. * Target creature card. ..." -- the index of the
    #: **mode** that owns this target, into the card's single top-level
    #: ``choose_mode``.  Such a spec is declared only when that mode is chosen,
    #: which is what lets one spell carry four different targets and bind two of
    #: them.  Only on a card's own `targets`, and only on a card whose whole
    #: effect tree is one top-level ``choose_mode`` -- `loader.targets._compile_targets`
    #: refuses it anywhere else, because nowhere else is there a moment between
    #: choosing the mode and declaring the target.
    mode: int | None = None


class TriggerModel(BaseModel):
    """When a triggered ability fires."""

    model_config = Strict

    event: str
    controller: Literal["you", "opponent", "any"] = "you"
    source: Literal["self"] | None = None
    filter: dict[str, Any] | None = None
    condition: dict[str, Any] | None = None
    #: For ``becomes_level``: the level it waits for -- "When this Class becomes
    #: level **2**". Required there and refused on every other event.
    level: int | None = None
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
    #: For ``ability_activated``: "…if it isn't a mana ability".  ``false``
    #: excludes mana abilities, ``true`` keeps only them, omitted is both.
    #: Both activation paths tag the event, so the two stop being
    #: indistinguishable to a listener; without this clause Harsh Mentor is a
    #: Manabarbs that pings every land tap.
    mana_ability: bool | None = None
    #: For ``draw``: "whenever you draw your **second** card each turn".  The
    #: ordinal that draw must have had for its player this turn.  For
    #: ``spell_cast``: "whenever an opponent casts their second spell each
    #: turn", counted over the spells matching ``filter`` when there is one
    #: ("their first **noncreature** spell").  Matched where
    #: the ability queues and never re-asked, unlike a ``condition`` on the same
    #: tally, which rule 603.4 re-evaluates after the tally has moved on.
    nth: int | None = None
    #: "This ability triggers only once each turn." A per-permanent cap on how
    #: many times this ability may queue in one turn.
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


class AbilityModel(BaseModel):
    """An activated, triggered or static ability.

    Static abilities flatten their parameters onto the ability object
    (``effect``, ``affects``, ``power``, ...) rather than nesting them, which is
    what makes the card files readable.
    """

    model_config = Strict

    kind: Literal["activated", "triggered", "static", "chapter", "reflexive", "level"]
    #: The name a `reflexive_trigger` op calls this ability by -- "when you do"
    #: has to point at *which* do. Required on ``kind: "reflexive"`` and refused
    #: on every other kind, and the loader checks the two halves name each
    #: other, so a reflexive ability nothing fires is a load error rather than a
    #: line of the card that never happens.
    id: str | None = None
    text: str = ""
    #: **A Saga's chapter number** -- the "II" in "II — Create two 2/2 red Human
    #: Knight creature tokens with trample and haste". Required on
    #: ``kind: "chapter"`` and refused on every other kind.
    #:
    #: The ability writes no ``trigger`` of its own: the loader builds one, for
    #: the reason it supplies ``source: "self"`` on ``self_enters``. The printed
    #: line contains no word saying *when*, so there is nothing for a card author
    #: to write and every Saga in print would have to write the same thing.
    chapter: int | None = None
    #: **A Class's level** (716). Two readings of one number, both "the level
    #: band this printed line belongs to":
    #:
    #: - on ``kind: "level"`` it is required, and it is the level the line
    #:   *gains* -- "{W}: Level 2" is ``{"kind": "level", "level": 2, "cost":
    #:   {"mana": "{W}"}}``. Nothing else goes on such a line: the loader supplies
    #:   the sorcery-speed timing, the "only if level N-1" restriction and the
    #:   effect, because 716.2a says all three and the printed line says none.
    #: - on any other kind it is the level the ability is printed **under**, and
    #:   the ability exists only while the Class is at that level or higher
    #:   (716.2b). Omitted for a level-1 ability, which is always there.
    level: int | None = None

    # activated
    cost: CostModel | None = None
    is_mana_ability: bool = False
    #: "Spend this mana only to cast a creature spell."  A card type, lowercased.
    #: A *list* is the "and/or" form -- "Spend this mana only to cast Vampire,
    #: Cleric, and/or Demon spells" -- and its entries may be subtypes as well as
    #: types, matched as an any-of.
    #:
    #: An entry may itself be a **list**, and then every name in it must match at
    #: once: "a creature spell **of the chosen type**" is
    #: ``[["creature", {"chosen_type_of": "self"}]]``, because either half alone
    #: is a different card -- ``"creature"`` casts any creature ever printed.
    #: ``{"chosen_type_of": "self"}`` is the one entry that is not a literal
    #: name; it reads the type this permanent chose as it entered.
    #:
    #: An **object** with ``cast`` and/or ``activate`` keys says which of the two
    #: the mana is allowed to pay for -- Secluded Courtyard's "…or activate an
    #: ability of a creature source of the chosen type". A bare string or list is
    #: the ``cast`` half alone, which is what every other printing says.
    #:
    #: Either half of the object may be the word ``"any"`` instead of a list of
    #: groups -- "Spend this mana only to activate abilities" (Cryptic Trilobite,
    #: Omen Hawker), which names no type at all. The loader refuses it on both
    #: halves at once and refuses it bare, where it would read as the ``cast``
    #: half and quietly make ordinary mana.
    mana_restriction: (
        str
        | list[str | dict[str, Any] | list[str | dict[str, Any]]]
        | dict[str, str | list[str | dict[str, Any] | list[str | dict[str, Any]]]]
        | None
    ) = None
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
    #: A station symbol (721): "12+ | {U}, {T}: Add {U} for each artifact you
    #: control" -- ``{"counter": "charge", "at_least": 12}``. The permanent
    #: **has** this ability only while it has that many counters; below it the
    #: ability does not exist, so it is not offered, not a mana source and not
    #: listed. Not ``condition``, which refuses an activation of an ability the
    #: permanent still has. Activated abilities only, printed after every
    #: ungated ability and in rising order.
    threshold: dict[str, Any] | None = None

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
    #: ``cast_from_graveyard``: this permission is **flashback** -- Lier's "each
    #: instant and sorcery card in your graveyard has flashback. The flashback
    #: cost is equal to that card's mana cost."
    #:
    #: It carries no behaviour of its own, and that is the point. A spell cast
    #: out of a graveyard already exiles as it resolves (`graveyard_cast_exiles`
    #: defaults True, and escape is the only thing that turns it off), so the
    #: exile half of flashback was already there. What this says is that the
    #: permission needs **no `max_per_turn`**: the exile is the rate limit, card
    #: by card, so a graveyard that runs out is the whole of the cap. Without it
    #: the loader refuses an uncapped permission, correctly -- one that neither
    #: meters nor exiles recasts the same card every turn for ever.
    grants_flashback: bool = False
    #: ``double_triggers``: which EVENT counts as the cause. Veyran's "if **you
    #: casting or copying an instant or sorcery spell** causes a triggered
    #: ability ... to trigger" -- a clause about what happened, not about whose
    #: ability answered it.
    #:
    #: Separate from `affects`, which is the other axis the same effect scopes
    #: on: Harmonic Prodigy filters the *permanent whose ability fired* ("a
    #: Shaman or another Wizard you control") and does not care what caused it.
    #: A card writes whichever of the two it prints; omitting these three means
    #: "any cause".
    cause_events: list[str] | None = None
    #: ``double_triggers``: whose cause it must be, read against the static's own
    #: controller. Veyran's "**you** casting or copying".
    cause_controller: Literal["you", "opponent", "any"] | None = None
    #: ``double_triggers``: what the cause must have been, as a card filter on
    #: the event's subject. Veyran's "an **instant or sorcery** spell".
    cause_filter: dict[str, Any] | None = None
    #: "**Once during each of your turns**, you may cast an artifact spell from
    #: your graveyard." Edgar, Master Machinist. How many times a
    #: `cast_from_graveyard` permission may be used per turn, counted per
    #: granting permanent -- two Edgars are two casts, the way two Welcoming
    #: Vampires each draw.
    #:
    #: Required on that static, because a permission with no rate limit is an
    #: unbounded engine rather than the printed line. Named for the trigger
    #: field it mirrors and meaning the same thing one ability kind over.
    static_max_per_turn: int | None = None
    #: "…that artifact **enters tapped**." A rider on the permission, applied to
    #: the permanent that was cast under it rather than to the permanent
    #: granting it -- `self_enters_tapped` is a card's own replacement and is
    #: the wrong permanent entirely here.
    enters_tapped: bool = False
    #: "…cards in your graveyard that were **put there from anywhere other than
    #: the battlefield this turn**." Banon, the Returners' Leader. A list of
    #: zone names the card must have arrived from, this turn; prefix one with
    #: `!` for the complement, which is what Banon prints -- listing the four
    #: zones a card could otherwise have come from would silently miss a fifth.
    #:
    #: Beside `affects_spells` rather than inside it, because when a card
    #: reached a graveyard and from where are facts about *this copy* and not
    #: about the card, and `affects_spells` may only read the printed face.
    arrived_this_turn_from: list[str] | None = None
    #: "…pay life equal to its **mana value** rather than pay its mana cost."
    #: Bolas's Citadel, on a `cast_from_library_top` static. An alternative cost
    #: imposed on somebody else's spell, which `spell_cost_reduction` cannot
    #: express: that one lowers a mana cost by an amount and cannot swap the
    #: payment to a different resource entirely.
    #:
    #: Required on that static, because the permission without its price is
    #: every spell in the deck castable off the top at its printed cost.
    pay_life_instead: bool = False
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
    #: "Protection from each color that's not in your commander's color
    #: identity" -- Commander's Plate. A colour set no printed list can name,
    #: because it is the five colours minus a set read off the *controller's*
    #: commanders, and it moves when the Equipment changes hands. Computed where
    #: protection is read (`characteristics.protection_from`); no commander at
    #: all is protection from all five (903.4).
    from_colors_outside_commander_identity: bool = False
    #: ``set_colors``: the colours that *replace* the printed ones. The empty
    #: list is colourless and is the whole point of the effect -- "enchanted
    #: permanent is a **colorless** land" -- so it is `None` that means "not
    #: given", never `[]`.
    colors: list[str] | None = None
    #: ``grant_ability``: which of the granting card's `grantable_abilities` the
    #: permanents this affects get, by index.
    ability: int | None = None
    #: ``block_restriction``: which would-be blockers are refused. A static
    #: filter over the *blocker*, so "can't be blocked by Humans" is
    #: ``{"subtypes": ["Human"]}``.
    blockers: dict[str, Any] | None = None
    #: ``block_restriction``: Tromokratis' "can't be blocked unless all
    #: creatures defending player controls block it". Judged on the whole
    #: declaration rather than per pair, so it cannot be a ``blockers``
    #: filter.
    require_all: bool = False
    #: ``replace_token_creation``: which token is about to be made. A filter on
    #: a *printed face* and not on `affects`, which picks out permanents on the
    #: battlefield: the token this asks about does not exist yet, has no
    #: controller of its own and no board state to read. Academy Manufactor's is
    #: ``{"subtypes": ["Clue", "Food", "Treasure"]}``, Divine Visitation's is
    #: ``{"types": ["Creature"]}``. Omitted means "any token", which is a shape
    #: printed cards really take.
    affects_token: dict[str, Any] | None = None
    #: ``replace_token_creation``: the token ids created instead. **One of each,
    #: per token that was about to be made** -- so Academy Manufactor's three
    #: ids turn one Treasure into a Clue, a Food and a Treasure, and Divine
    #: Visitation's single id turns N Soldiers into N Angels. The list is why
    #: two very differently worded cards need one field: "instead create one of
    #: each" is a list of three and "that many are created instead" is a list of
    #: one. See `primitives._token_creation_plan`.
    create_instead: list[str] = Field(default_factory=list)
    #: ``replace_token_creation``: what the count of each token about to be made
    #: is multiplied by, the token itself unchanged. Bard, King of Dale's and
    #: Parallel Lives' "twice that many of those tokens are created instead" is
    #: ``2``. The other axis of the same static from `create_instead`, and a
    #: static carries exactly one of the two: the doublers name no token, so no
    #: id could be listed, and listing one would convert every token into it.
    #: Refused below 2 for the reason `loss_multiplier` is.
    token_multiplier: int | None = None
    #: ``replace_life_loss``: what a life loss is multiplied by. Bloodletter of
    #: Aclazotz's "they lose **twice** that much life instead" is ``2``.
    #:
    #: A multiplier rather than a flat amount because that is what the printed
    #: line says, and because the replaced event carries an amount the card
    #: never names. Required, and refused below at 0 and 1: a multiplier of 1
    #: replaces a loss with itself, and 0 is "they lose no life" -- a
    #: prevention, which is a different sentence and a much stronger card.
    loss_multiplier: int | None = None
    #: ``replace_life_gain``: what a life gain is multiplied by. Alhammarret's
    #: Archive's "you gain **twice** that much life instead" is ``2``. Required,
    #: and refused below 2 for `loss_multiplier`'s reasons: 1 replaces a gain
    #: with itself, and 0 is "you gain no life" -- `cant_gain_life`, a
    #: different sentence.
    gain_multiplier: int | None = None
    #: ``replace_draw``: how many cards each replaced draw becomes. Thought
    #: Reflection's and Bard, King of Dale's "draw **two** cards instead" is
    #: ``2``. Required, and refused below 2 for `loss_multiplier`'s reasons: 1
    #: replaces a draw with itself and 0 is "you draw nothing", a different card.
    draw_multiplier: int | None = None
    #: ``replace_draw``: "…except the first one you draw in each of your draw
    #: steps" (Bard, King of Dale; Alhammarret's Archive). The first *card*
    #: drawn while its controller's own draw step is running is left alone;
    #: every other draw, that step's second included, is replaced.
    except_first_in_draw_step: bool = False
    #: ``replace_mill``: how many cards each replaced mill becomes. Bruvac the
    #: Grandiloquent's and Fraying Sanity's "mill **twice** that many cards
    #: instead" is ``2``. Required, and refused below 2 for `draw_multiplier`'s
    #: reasons: 1 replaces a mill with itself and 0 mills nothing.
    #:
    #: Unlike `draw_multiplier` this scales a **count**, not a number of events:
    #: 701.13a makes milling N cards one event, where 121.2 makes drawing N
    #: cards N draws.
    mill_multiplier: int | None = None
    #: ``add_mana_on_tap``: what a tapped permanent must be for the static to
    #: add mana -- Crypt Ghast's ``{"subtypes": ["Swamp"]}``. Only
    #: `loader.TAPPED_PERMANENT_KEYS`.
    tapped_permanent: dict[str, Any] | None = None
    #: ``add_mana_on_tap``: the fixed mana added -- Crypt Ghast's ``"{B}"``.
    add_mana: str | None = None


class ReplacementModel(BaseModel):
    """One of the four whitelisted replacement effects.

    Every one of them modifies the permanent that is *already arriving*, which
    is why token creation is not here and could not be: there is no object yet.
    "If you would create a Clue, Food, or Treasure token" is a
    ``replace_token_creation`` static instead -- see `AbilityModel.create_instead`.
    """

    model_config = Strict

    event: Literal[
        "self_enters",
        "self_enters_tapped",
        "self_enters_with_counters",
        "self_enters_prepared",
    ]
    modify: dict[str, Any] = Field(default_factory=dict)
    counter: str | None = None
    #: How many, as a plain integer or a **value expression** -- "enters with a
    #: +1/+1 counter on it for each other Human you control" is
    #: ``{"count": {"zone": "battlefield", "controller": "you",
    #: "subtypes": ["Human"], "exclude_self": true}}``.  Evaluated where the
    #: `condition` below is, with the same source and controller, so it counts
    #: the board the permanent is arriving on.  It has to live here rather than
    #: in an `add_counters` trigger: 614.1c means the permanent is never seen
    #: without the counters, and Éomer, King of Rohan -- who deals damage equal
    #: to his own power from a second enters trigger -- would otherwise have a
    #: payload that depended on which of two simultaneous triggers his
    #: controller happened to order first.
    amount: int | dict[str, Any] = 1
    #: Applied only when this holds, evaluated as the permanent enters with the
    #: entering object as the source -- so `exclude_self` means "other lands you
    #: control" and counts the board the land is arriving on.  The printed
    #: sentence is "enters tapped **unless** you control a Mountain", so the
    #: card writes the negation: a condition here says when the replacement
    #: *applies*, matching every other `condition` in the DSL.
    condition: dict[str, Any] | None = None
    #: "As this land enters, you may pay 3 life. If you don't, it enters
    #: tapped." (Sink into Stupor // Soporific Springs, and the shock lands.)
    #: A price the controller may pay to *avoid* the replacement, offered as
    #: the permanent enters and taking a whole `Cost` -- `pay_life` for this
    #: cycle, and the same node the rest of the DSL prices things with.
    #:
    #: The question is asked **just before** the move rather than inside it, by
    #: whichever path is putting the permanent onto the battlefield. That is
    #: observationally the same moment: 614 replacements are applied during the
    #: zone change and nobody receives priority in between, so there is no
    #: window in which the permanent exists un-replaced. It is also the only
    #: reachable moment -- `move_object` is not a generator and cannot stop to
    #: ask, and making it one would put a suspend point inside every zone
    #: change in the engine.
    unless_cost: dict[str, Any] | None = None


class EmblemModel(BaseModel):
    """The abilities printed in one emblem's quotation marks (114.1).

    An emblem has abilities and **no other characteristics** (114.3), so
    abilities are the whole of it: no name, types, cost or colour to write.
    """

    model_config = Strict

    abilities: list[AbilityModel] = Field(default_factory=list)


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
    #: A Saga's **final chapter number** (714.4). Omit it and the loader takes the
    #: highest chapter the card prints, which is right for every Saga whose text
    #: the DSL can say in full.
    #:
    #: Worth writing by hand in exactly one case, and it is the case that makes
    #: the field exist: a Saga whose last chapter is *unimplemented*. Derived, its
    #: final chapter would be the last one written, and 704.5s would sacrifice it
    #: a chapter early -- a strictly better card than the printed one, arriving
    #: silently. Written down, the Saga sits out its last chapter doing nothing,
    #: which is visibly the printed card minus a line.
    final_chapter: int | None = None
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
    #: Emblems this card can give a player (114), referenced by index from an
    #: ``emblem`` effect. Each entry is the quoted text of one emblem, written
    #: as ordinary abilities -- "You get an emblem with "Whenever you cast a
    #: spell, …"". Like ``grantable_abilities`` the card does not have them; an
    #: emblem is its own object in the command zone and has nothing else.
    emblems: list[EmblemModel] = Field(default_factory=list)
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
    #: The card id of the **spell** a prepared permanent may cast a copy of --
    #: "While it's prepared, you may cast a copy of its spell" (Emeritus of Woe
    #: // Demonic Tutor). Its own field rather than a third `second_face_zone`
    #: value: casting a second face takes the object out of its zone, and this
    #: leaves the permanent where it is and puts a copy on the stack.
    prepared_face: str | None = None
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
    #: "**Exile Teferi's Protection.**" -- the printed last line of a spell that
    #: exiles *itself* as it finishes resolving.
    #:
    #: The sixth rider on the same slot as flashback's exile, buyback's hand,
    #: rebound's exile, cipher's and adventure's, and like all of them it only
    #: ever replaces the *graveyard*. Not the `exile` op: a spell is off the
    #: stack list by the time its effects run, so `{"zone": "stack",
    #: "self_only": true}` reaches nothing and the line would silently do
    #: nothing at all. Not `exile_self` either, which is a **cost** key.
    exiles_itself: bool = False
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
    #: "As an additional cost to cast this spell, discard a card **or** pay 3
    #: life" -- Bitter Triumph. Two whole alternative payments, one of which the
    #: caster picks as the spell is cast.
    #:
    #: A sibling of ``additional_cost`` rather than a shape of it, because a
    #: `CostModel`'s entries are **conjunctive**: writing `discard` and
    #: `pay_life` on one cost charges both, which is a strictly worse card, and
    #: writing either alone silently drops half the printed line.
    #: ``additional_optional`` is the nearest existing thing and only makes one
    #: fixed price skippable; `choose_mode` runs at resolution and so can
    #: neither be a cost nor decide whether the spell is castable.
    #:
    #: Legality offers one cast line per **payable** branch, exactly as emerge
    #: offers one per sacrificeable creature: the player is choosing, and the
    #: choice changes the price.
    additional_cost_options: list[CostModel] = Field(default_factory=list)
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
    #: **Gift a tapped Fish** (702.164a): "You may promise an opponent a gift as
    #: you cast this spell." The string is *what is promised* -- ``"a tapped
    #: Fish"``, ``"a card"``, ``"a Food"`` -- and it is the printed noun phrase,
    #: because the residual gate compares it against the printed line.
    #:
    #: The kicker slot pointed at a **recipient** instead of at a price. Kicker
    #: is an additional cost the caster pays; a gift costs nothing at all and
    #: names one opponent, so legality offers one promised cast line **per
    #: opponent** at the printed price -- emerge's shape ("one line per victim"),
    #: not kicker's bool, because a promise made to the wrong seat is a
    #: different card.
    #:
    #: The reward is an ordinary effect the card writes **first** in
    #: ``spell_effects`` (702.164b: the gift happens before the spell's other
    #: effects), aimed with the ``"gift_recipient"`` player spec. Whether the
    #: promise was made is read back with ``{"gift_promised": true}``.
    gift: str | None = None
    #: **Multikicker {1}{W}** (702.32b): "You may pay an additional {1}{W} any
    #: number of times as you cast this spell."
    #:
    #: The name for a shape that already existed unnamed: it *desugars* to
    #: ``additional_cost: {mana: ...}`` with both ``additional_optional`` and
    #: ``additional_repeatable`` -- replicate's slot -- so legality offers one
    #: cast line per number of kicks and the count is read back with
    #: ``{"additional_paid": true}``.
    #:
    #: Not ``kicker``, which is one-shot: its cast variant is a bool on the
    #: action and ``{"kicked": true}`` can only answer yes or no, never how many.
    #: Give one or the other, not both spellings of the same slot.
    multikicker: str | None = None
    #: **Strive** (Journey into Nyx): "This spell costs {1}{W} more to cast for
    #: each target beyond the first." The mana string charged once per target
    #: past the first, on a card whose one target spec is ``count: "any"``. A
    #: cost *increase* under 601.2f, fixed by the targets chosen at 601.2c, so
    #: legality prices each target count as its own cast line and never offers
    #: a count the caster cannot pay for.
    strive: str | None = None
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
    #: Which browser library imported this -- the id a client mints once into
    #: its own ``localStorage`` and sends as ``X-Library-Id``.  There are no
    #: accounts here, so this is the whole of "mine": the deck list filters on
    #: it and delete checks it.
    #:
    #: ``""`` is a precon, or a deck imported before libraries existed.  Those
    #: stay visible to everybody and deletable by anybody, which is the only way
    #: an already-imported deck can be cleaned up from the screen rather than by
    #: hand.  Defaulted for ``source``'s reason, and it matters more here: every
    #: deck file already on disk lacks the field.
    owner: str = ""

    # -- editorial metadata, for the lobby's deck catalogue ----------------
    # All optional and all defaulted, for the same ``extra="forbid"`` reason as
    # ``source``: an imported deck has none of it and must still load.
    tags: list[str] = Field(default_factory=list)
    ratings: DeckRatingsModel | None = None
    strategy: str = ""
    signature: list[SignatureCardModel] = Field(default_factory=list)
