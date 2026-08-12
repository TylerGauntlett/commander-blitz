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
    tap_permanents: dict[str, Any] | None = None
    discard: int = 0
    #: Narrows what ``discard`` may throw away -- "discarding a land card".
    #: A selector over the hand; omitted, any card will do.
    discard_selector: dict[str, Any] | None = None
    #: Cycling's "Discard this card": the source discards itself, no choice.
    discard_self: bool = False
    pay_life: int = 0
    remove_counters: dict[str, Any] | None = None
    exile_from_graveyard: dict[str, Any] | None = None


class TargetModel(BaseModel):
    """One target requirement."""

    model_config = Strict

    id: str
    kind: Literal["permanent", "player", "spell", "card_in_graveyard", "any"]
    selector: dict[str, Any] = Field(default_factory=dict)
    count: int = 1
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
    mana_restriction: str | None = None
    sorcery_speed_only: bool = False
    #: This activated ability *is* the cycling ability, so paying for it emits
    #: the `cycle` event a "When you cycle this card" trigger listens for.
    #: Declared rather than inferred: "Discard this card: draw" is a shape other
    #: cards print without being cycling, and a trigger firing on those would be
    #: a different card.
    is_cycling: bool = False

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
    #: "This spell can't be countered."
    uncounterable: bool = False
    #: "Kicker {1}{U}" -- an additional cost that may be paid as the spell is
    #: cast.  What being kicked then *does* is an ordinary ``if`` on the
    #: ``{"kicked": true}`` condition, so no card needs new effect vocabulary.
    kicker: str | None = None
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
