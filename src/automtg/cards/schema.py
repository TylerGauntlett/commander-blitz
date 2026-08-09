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
    discard: int = 0
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
    sorcery_speed_only: bool = False

    # triggered
    trigger: TriggerModel | None = None
    active_zones: list[Literal["battlefield", "command", "graveyard", "hand", "exile"]] = Field(
        default_factory=lambda: ["battlefield"]
    )

    # activated + triggered
    targets: list[TargetModel] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)

    # static
    effect: str | None = None
    affects: dict[str, Any] | None = None
    affects_player: Literal["you", "opponent", "any"] | None = None
    power: Any = None
    toughness: Any = None
    keywords: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    amount: Any = None


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
    is_token: bool = False

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
