"""An alternative cost printed on a *permanent*, and the line that names it.

    Sephara, Sky's Blade — "You may pay {W} and tap four untapped creatures you
    control with flying rather than pay this spell's mana cost. Flying, lifelink.
    Other creatures you control with flying have indestructible."

The mechanic was already whole. `alternative_cost` is a full `Cost` node (rule
118.9: an alternative cost replaces the mana cost, it is not added to it), so
"{W} and tap four untapped creatures you control with flying" is `mana` plus
`tap_permanents` -- the same `tap_permanents` Captivating Vampire's ability
pays with. `casting` offers the line beside the printed one and `game._cast`
charges it. What had never been asked of it is a creature, because the seven
cards shipped with one -- Daze, Force of Will, Snuff Out, Flare of Denial,
Fierce Guardianship, Flawless Maneuver, Submerge -- are all instants. That
proves out three rules points this file pins:

* **The spell does not tap itself.** It is in hand while 601.2h pays the cost,
  so a Sephara with three fliers beside her is not castable this way; the
  `tap_permanents` pool is read off the battlefield, which she is not on.
* **Summoning-sick fliers pay.** Rule 302.6 restricts a creature's own {T} and
  {Q} abilities. This cost taps *other* permanents, so the four Birds cast this
  turn are exactly the four the card is printed for.
* **Both prices are offered and are different actions**, so the heuristic agent
  takes the cheap one when the printed one is out of reach.

The other half is bookkeeping. The residual gate (`verify._covered`) had a
claimant for kicker, evoke, bestow, mutate and the rest, and none for
`alternative_cost` -- instants never needed one, because `spell_effects` claims
every line of a spell. A creature has no `spell_effects`, so Sephara's first
line stayed residual with the mechanic fully working. The new claimant is
strict in the way bestow's and multikicker's are: the printed mana must parse
to the declared `mana`, the printed "tap N untapped <things>" must be the
declared `tap_permanents` count and selector, and printed life must be the
declared `pay_life`. A card declaring `{U}` cannot claim a printed `{W}`, and a
card tapping three cannot claim "tap four": that would be a cheaper card wearing
the printed words.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.cards.authoring.verify import _covered, residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer, oids_of

BLADE = "t_sky_blade"  # {4}{W}{W}{W} 7/7 flier; or {W} + tap four fliers
FLIER = "t_sky_flier"  # vanilla 1/1 flier
BEAR = "t_ground_bear"  # vanilla 2/2, no flying

LINE = (
    "You may pay {W} and tap four untapped creatures you control with flying "
    "rather than pay this spell's mana cost."
)
POOL = Path(__file__).resolve().parents[3] / "data" / "cards" / "auto" / "templates.cards.json"


def shipped(card_id: str) -> dict:
    """The collected card as it ships -- not its answer, which collect retires."""
    cards = json.loads(POOL.read_text(encoding="utf-8"))["cards"]
    return next(c for c in cards if c["id"] == card_id)


def position(builder, *, fliers: int = 4, plains: int = 1, **flier_kwargs):
    """You hold the Blade over `plains` Plains and `fliers` Birds.

    A second Blade in hand keeps the main phase anchored: with a castable spell
    still held after the first resolves, the engine does not auto-pass on.
    """
    b = builder(players=2).hand(0, [BLADE, BLADE]).battlefield(0, ["plains"] * plains)
    if fliers:
        b = b.battlefield(0, [FLIER] * fliers, **flier_kwargs)
    for pid in range(2):
        b = b.library(pid, ["plains"] * 20)
    game = b.build()
    return game, game.state.players[0].hand[0]


def alternative_lines(game, oid: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.source == oid and a.alternative
    ]


def printed_lines(game, oid: int) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.source == oid and not a.alternative
    ]


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def tapped_fliers(game) -> int:
    return sum(1 for oid in oids_of(game, FLIER, 0) if game.state.objects[oid].tapped)


def cast_alternative(game, oid: int) -> None:
    """Cast the Blade for {W} and four fliers, answering any tap choice."""
    game.apply(alternative_lines(game, oid)[0])
    settle(game)


def variant(**alternative_cost) -> dict:
    """Sephara's shape with the `alternative_cost` node replaced."""
    spec = {
        "id": "t_sky_blade_variant",
        "name": "Test Sky Blade Variant",
        "oracle_text": f"{LINE}\nFlying",
        "mana_cost": "{4}{W}{W}{W}",
        "types": ["Creature"],
        "colors": ["W"],
        "color_identity": ["W"],
        "power": 7,
        "toughness": 7,
        "keywords": ["flying"],
        "alternative_cost": alternative_cost
        or {
            "mana": "{W}",
            "tap_permanents": {"types": ["Creature"], "keywords": ["flying"], "count": 4},
        },
    }
    return spec


def compiled(spec: dict):
    return compile_card(CardModel.model_validate(spec))


class TestWhenItIsOffered:
    def test_four_untapped_fliers_and_a_plains_offer_it(self, builder):
        game, blade = position(builder)
        assert alternative_lines(game, blade)
        assert printed_lines(game, blade) == [], "one Plains cannot pay {4}{W}{W}{W}"

    def test_three_fliers_do_not(self, builder):
        """Not payable-and-discounted: three fliers is a cheaper card."""
        game, blade = position(builder, fliers=3)
        assert alternative_lines(game, blade) == []

    def test_the_spell_does_not_count_itself(self, builder):
        """She has flying, but she is in hand while the cost is paid (601.2h).
        Three Birds and Sephara herself are three creatures on the battlefield,
        not four -- the pool is read off the battlefield, where she is not."""
        game, blade = position(builder, fliers=3)
        assert "flying" in game.state.card(blade).keywords
        assert alternative_lines(game, blade) == []

    def test_tapped_fliers_do_not_pay(self, builder):
        """"…four **untapped** creatures". Already-tapped ones cannot pay again."""
        game, blade = position(builder, tapped=True)
        assert alternative_lines(game, blade) == []

    def test_creatures_without_flying_do_not_pay(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BLADE])
            .battlefield(0, ["plains"])
            .battlefield(0, [FLIER] * 3)
            .battlefield(0, [BEAR] * 4)
            .build()
        )
        blade = game.state.players[0].hand[0]
        assert alternative_lines(game, blade) == []

    def test_summoning_sick_fliers_pay(self, builder):
        """Rule 302.6 restricts a creature's *own* {T}/{Q} abilities. This cost
        taps other permanents, so four Birds that arrived this turn pay it."""
        game, blade = position(builder, sick=True)
        assert alternative_lines(game, blade)

    def test_the_mana_half_is_still_owed(self, builder):
        """{W} *and* the four fliers -- the creatures alone are not the price."""
        game, blade = position(builder, plains=0)
        assert alternative_lines(game, blade) == []

    def test_both_prices_are_offered_when_both_are_payable(self, builder):
        game, blade = position(builder, plains=7)
        assert alternative_lines(game, blade) and printed_lines(game, blade)


class TestWhatItCosts:
    def test_it_taps_four_fliers_and_one_plains(self, builder):
        game, blade = position(builder, plains=2)
        cast_alternative(game, blade)
        assert game.state.objects[blade].zone is Zone.BATTLEFIELD
        assert tapped_fliers(game) == 4
        untapped_plains = [
            o
            for o in game.state.battlefield_objects(0)
            if o.def_id == "plains" and not o.tapped
        ]
        assert len(untapped_plains) == 1, "{W}, not {4}{W}{W}{W}"

    def test_the_payer_chooses_which_four(self, builder):
        """Five fliers, four to tap: the cost asks rather than picking for you."""
        game, blade = position(builder, fliers=5)
        game.apply(alternative_lines(game, blade)[0])
        seen = []
        for _ in range(10):
            decision = game.pending()
            if decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS:
                break
            seen.append(decision)
            game.apply(_default_answer(game, decision))
        assert seen, "five candidates for four slots is a choice"
        settle(game)
        assert tapped_fliers(game) == 4

    def test_sick_fliers_end_tapped(self, builder):
        game, blade = position(builder, sick=True)
        cast_alternative(game, blade)
        assert tapped_fliers(game) == 4
        assert game.state.objects[blade].zone is Zone.BATTLEFIELD

    def test_the_permanent_is_an_ordinary_permanent_afterwards(self, builder):
        """An alternative cost changes what was paid, nothing else (118.9c): no
        sacrifice trigger, no evoke flag, a 7/7 that stays."""
        game, blade = position(builder)
        cast_alternative(game, blade)
        obj = game.state.objects[blade]
        assert obj.zone is Zone.BATTLEFIELD
        assert not getattr(obj, "evoked", False)


class TestTheAgentTakesIt:
    def test_the_heuristic_agent_casts_it_for_the_alternative_cost(self, builder):
        """It cannot pay the printed seven, so the only creature cast it can
        score is the alternative one -- and it takes it."""
        game, blade = position(builder)
        agent = HeuristicAgent()
        action = agent.act(game, 0, game.legal_actions())
        assert action.kind is ActionKind.CAST and action.alternative
        assert game.state.objects[action.source].def_id == BLADE
        assert blade in game.state.players[0].hand


class TestTheResidualGateClaimsTheLine:
    def test_the_declared_cost_claims_its_printed_line(self):
        card = compiled(variant())
        assert _covered(card, LINE)
        assert residual_text(card, card.oracle_text) == ""

    def test_without_the_field_the_line_is_residual(self):
        """No `alternative_cost`, no claim: the words alone implement nothing."""
        spec = variant()
        del spec["alternative_cost"]
        card = compiled(spec)
        assert not _covered(card, LINE)
        assert "rather than pay" in residual_text(card, card.oracle_text)

    def test_the_wrong_colour_of_mana_does_not_claim_it(self):
        """A card charging {U} is not the card that prints {W}."""
        card = compiled(
            variant(
                mana="{U}",
                tap_permanents={"types": ["Creature"], "keywords": ["flying"], "count": 4},
            )
        )
        assert not _covered(card, LINE)

    @pytest.mark.parametrize("mana", ["{1}{W}", "{0}"])
    def test_more_or_less_mana_does_not_claim_it(self, mana):
        card = compiled(
            variant(
                mana=mana,
                tap_permanents={"types": ["Creature"], "keywords": ["flying"], "count": 4},
            )
        )
        assert not _covered(card, LINE)

    def test_a_different_count_does_not_claim_it(self):
        """Tapping three is a cheaper card than tapping four."""
        card = compiled(
            variant(
                mana="{W}",
                tap_permanents={"types": ["Creature"], "keywords": ["flying"], "count": 3},
            )
        )
        assert not _covered(card, LINE)

    def test_dropping_the_flying_narrowing_does_not_claim_it(self):
        """Any four creatures is a cheaper card than four fliers."""
        card = compiled(variant(mana="{W}", tap_permanents={"types": ["Creature"], "count": 4}))
        assert not _covered(card, LINE)

    def test_a_different_type_does_not_claim_it(self):
        card = compiled(
            variant(
                mana="{W}",
                tap_permanents={"types": ["Artifact"], "keywords": ["flying"], "count": 4},
            )
        )
        assert not _covered(card, LINE)

    def test_dropping_the_tap_half_does_not_claim_it(self):
        card = compiled(variant(mana="{W}", pay_life=2))
        assert not _covered(card, LINE)

    def test_an_unread_payment_fails_closed(self):
        """A field the claimant does not read is a payment it cannot vouch for."""
        card = compiled(
            variant(
                mana="{W}",
                tap_permanents={"types": ["Creature"], "keywords": ["flying"], "count": 4},
                mill=2,
            )
        )
        assert not _covered(card, LINE)

    def test_a_sentence_that_only_mentions_a_free_cast_is_not_the_price(self):
        """Anchored at both ends: an effect that casts *another* card free is
        not this card's alternative cost."""
        card = compiled(variant())
        assert not _covered(
            card, "You may cast a card exiled with this creature without paying its mana cost."
        )

    @pytest.mark.parametrize(
        "card_id",
        [
            "daze",
            "fierce_guardianship",
            "flare_of_denial",
            "flawless_maneuver",
            "force_of_will",
            "snuff_out",
            "submerge",
        ],
    )
    def test_every_shipped_alternative_cost_line_reads(self, card_id):
        """The seven instants never needed this claimant -- `spell_effects`
        claims their lines -- but their printed costs are the corpus it has to
        read: return an Island, pitch a blue card, sacrifice a creature, pay
        life, and the conditional free cast."""
        spec = shipped(card_id)
        card = compiled(spec)
        assert _covered(card, spec["oracle_text"].split("\n")[0])

    def test_a_shipped_line_with_the_wrong_life_does_not_read(self):
        spec = shipped("snuff_out")
        spec["alternative_cost"]["pay_life"] = 2
        card = compiled(spec)
        assert not _covered(card, spec["oracle_text"].split("\n")[0])
