"""An activated-ability cost of "Sacrifice X <permanents>" (601.2b, 107.3).

    Insatiable Frugivore: "{3}{B}, Sacrifice X Foods: Creatures you control get
    +X/+0 and gain menace until end of turn."

107.3 lets a cost's number be X, and 601.2b (applied to abilities by 602.2b)
has the controller announce it as the ability is activated, before targets and
before any cost is paid. A cost is paid only by doing all of it (601.2h), so X
can be no more than the matching permanents the controller can sacrifice. The
permanents go as the cost, chosen by the payer, and the ability's effects read
the same X back.

Without this, `cost.sacrifice` is a count the card fixes, so a printed
"Sacrifice X Foods" had no spelling, and sacrificing in the effects would move
the payment to resolution. `sacrifice_x` is a selector on `discard_x`'s path:
`Game._activate` announces X through `ask_x` with `costs.sacrifice_x_ceiling`
as the ceiling, `costs.can_pay` and `costs.pay` read the announced X, and
`legality._ability_aims` offers one activation per X when the targets read it.

Witness: Insatiable Frugivore. `t_sx_engine`, `t_sx_squirrel` and `t_sx_aimer`
are its shapes.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, oids_of, only_oid, settle

ENGINE = "t_sx_engine"  # "{1}, Sacrifice X Foods: You gain X life."
SQUIRREL = "t_sx_squirrel"  # "Sacrifice X Squirrels: You gain X life." -- a Squirrel
AIMER = "t_sx_aimer"  # "Sacrifice X Foods: Destroy target creature with mana value X."


def position(builder, source: str = ENGINE, *, mine=("food_token",) * 3, theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [source] + list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, source, 0)


def choose_x(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def sacrifice_these(game, oids) -> None:
    """Answer the cost's pick with exactly these permanents.

    A pick whose pool is exactly the count is forced and asks nothing.
    """
    decision = game.pending()
    if decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def foods(game) -> list[int]:
    return oids_of(game, "food_token", 0)


class TestXIsAnnouncedAndPaidInPermanents:
    def test_activating_it_asks_for_x(self, builder):
        game, engine = position(builder)
        game.apply(activations(game, engine)[0])
        assert game.pending().kind is DecisionKind.CHOOSE_X

    def test_the_ceiling_is_the_matching_permanents(self, builder):
        """601.2h: a sacrifice of permanents that are not there cannot be paid,
        and a permanent that is not a Food is not among them."""
        game, engine = position(builder, mine=("food_token",) * 3 + ("grizzly_bears",))
        game.apply(activations(game, engine)[0])
        assert game.pending().context["max_x"] == 3

    @pytest.mark.parametrize("x", [1, 3])
    def test_x_are_sacrificed_and_the_effect_reads_x(self, builder, x):
        """Parametrised because a constant passes any single case."""
        game, engine = position(builder)
        life = game.state.players[0].life
        picked = foods(game)[:x]
        game.apply(activations(game, engine)[0])
        choose_x(game, x)
        sacrifice_these(game, picked)
        assert len(foods(game)) == 3 - x
        assert not set(picked) & set(foods(game))
        settle(game)
        assert game.state.players[0].life == life + x

    def test_the_payer_picks_which(self, builder):
        game, engine = position(builder)
        keep, *_ = foods(game)
        game.apply(activations(game, engine)[0])
        choose_x(game, 2)
        sacrifice_these(game, [oid for oid in foods(game) if oid != keep])
        assert foods(game) == [keep]

    def test_x_can_be_zero(self, builder):
        """107.3: zero is a legal announcement, so the ability is on offer with
        no Food, asks nothing, sacrifices nothing and reads 0."""
        game, engine = position(builder, mine=())
        life = game.state.players[0].life
        game.apply(activations(game, engine)[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        settle(game)
        assert game.state.players[0].life == life
        assert game.state.objects[engine].zone is Zone.BATTLEFIELD

    def test_choosing_zero_with_food_sacrifices_none(self, builder):
        game, engine = position(builder)
        life = game.state.players[0].life
        game.apply(activations(game, engine)[0])
        choose_x(game, 0)
        settle(game)
        assert len(foods(game)) == 3
        assert game.state.players[0].life == life

    def test_the_mana_half_is_still_paid(self, builder):
        game, engine = position(builder)
        game.apply(activations(game, engine)[0])
        choose_x(game, 1)
        sacrifice_these(game, foods(game)[:1])
        tapped = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "swamp" and o.tapped
        ]
        assert len(tapped) == 1

    def test_it_reads_as_sacrifice_x(self, registry):
        assert registry.get(ENGINE).abilities[0].cost.describe() == "{1}, Sacrifice X"


class TestTheSourceMayBeFodder:
    def test_a_squirrel_counts_itself(self, builder):
        """Chatterfang's shape: "Sacrifice X Squirrels" on a Squirrel may
        sacrifice that Squirrel, and the ability still resolves."""
        game, squirrel = position(builder, SQUIRREL, mine=())
        life = game.state.players[0].life
        game.apply(activations(game, squirrel)[0])
        assert game.pending().context["max_x"] == 1
        choose_x(game, 1)
        assert squirrel not in game.state.battlefield
        settle(game)
        assert game.state.players[0].life == life + 1


class TestTargetsThatReadX:
    """601.2b announces X before 601.2c chooses targets, so the number rides on
    the activation and each offer carries the targets legal at that X."""

    def test_one_offer_per_x_each_with_its_own_target(self, builder):
        game, aimer = position(builder, AIMER, theirs=["llanowar_elves", "grizzly_bears"])
        offered = {
            (a.x, game.state.objects[a.targets[0].id].def_id) for a in activations(game, aimer)
        }
        assert offered == {(1, "llanowar_elves"), (2, "grizzly_bears")}

    def test_no_x_above_the_foods(self, builder):
        game, aimer = position(
            builder, AIMER, mine=("food_token",), theirs=["llanowar_elves", "grizzly_bears"]
        )
        assert {a.x for a in activations(game, aimer)} == {1}

    def test_the_announced_x_is_paid_without_asking_again(self, builder):
        game, aimer = position(builder, AIMER, theirs=["grizzly_bears"])
        bears = only_oid(game, "grizzly_bears", 1)
        game.apply(next(a for a in activations(game, aimer) if a.x == 2))
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        sacrifice_these(game, foods(game)[:2])
        assert len(foods(game)) == 1
        settle(game)
        assert game.state.objects[bears].zone is Zone.GRAVEYARD


class TestTheLoaderChecksIt:
    def _card(self, cost: dict, kind: str = "activated") -> CardModel:
        ability = {
            "kind": kind,
            "text": "Sacrifice X Foods: You gain X life.",
            "cost": cost,
            "effects": [{"op": "gain_life", "player": "you", "amount": {"x": True}}],
        }
        return CardModel.model_validate(
            {
                "id": "t_sx_bad",
                "name": "Test Bad Sacrifice X",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": "Sacrifice X Foods: You gain X life.",
                "abilities": [ability],
            }
        )

    def test_a_selector_is_the_form(self):
        compile_card(self._card({"sacrifice_x": {"subtypes": ["Food"]}}))

    @pytest.mark.parametrize("key", ["count", "as"])
    def test_x_is_the_count_and_names_nothing(self, key):
        with pytest.raises(DslError, match=f"'{key}' may not be set"):
            compile_card(self._card({"sacrifice_x": {"subtypes": ["Food"], key: 2}}))

    def test_a_malformed_selector_is_refused(self):
        with pytest.raises(DslError, match="sacrifice_x"):
            compile_card(self._card({"sacrifice_x": {"subtype": ["Food"]}}))

    def test_not_beside_a_fixed_sacrifice(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card(
                    {"sacrifice_x": {"subtypes": ["Food"]}, "sacrifice": {"types": ["Creature"]}}
                )
            )

    @pytest.mark.parametrize(
        "second", [{"mana": "{X}"}, {"discard_x": True}, {"pay_life_x": True}]
    )
    def test_not_beside_a_second_x(self, second):
        with pytest.raises(DslError, match="second X"):
            compile_card(self._card({"sacrifice_x": {"subtypes": ["Food"]}, **second}))

    def test_not_on_a_spells_additional_cost(self):
        with pytest.raises(DslError, match="activated ability"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_sx_bad_spell",
                        "name": "Test Bad Sacrifice X Spell",
                        "mana_cost": "{B}",
                        "types": ["Sorcery"],
                        "oracle_text": (
                            "As an additional cost to cast this spell, sacrifice X Foods.\n"
                            "You gain X life."
                        ),
                        "additional_cost": {"sacrifice_x": {"subtypes": ["Food"]}},
                        "spell_effects": [
                            {"op": "gain_life", "player": "you", "amount": {"x": True}}
                        ],
                    }
                )
            )
