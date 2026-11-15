"""An activated-ability cost that sacrifices several distinct parts (118.3, 601.2h).

    Glass-Cast Heart: "{B}{B}, {T}, Sacrifice this artifact and thirteen Blood
    tokens: Each opponent loses 13 life and you gain 13 life."
    Jarad, Golgari Lich Lord: "Sacrifice a Swamp and a Forest: Return this card
    from your graveyard to your hand."

A cost is paid only by doing all of it (601.2h), and one that needs permanents
that are not there cannot be paid at all (118.3). "A Swamp and a Forest" is two
permanents: a Swamp Forest dual is one object and pays one part, so it alone
pays nothing. A single `sacrifice` selector with `count: 2` over Swamp-or-Forest
would take two Swamps; one with `count: 14` over "this or a Blood" would keep
the Heart and take fourteen tokens. The list form of `sacrifice` gives each
part its own selector and count, `costs.sacrifice_parts_payable` decides
legality as a matching of permanents to parts, and `costs.pay` asks the payer
for each part without ever offering a permanent another part took, or one
whose loss would strand a later part.

Witnesses: Glass-Cast Heart and Jarad. `t_sp_heart`, `t_sp_lands` and
`t_sp_overlap` are their shapes.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, oids_of, only_oid, settle

HEART = "t_sp_heart"  # "{1}, Sacrifice this artifact and three Blood tokens: gain 13."
LANDS = "t_sp_lands"  # "Sacrifice a Swamp and a Forest: You gain 2 life."
OVERLAP = "t_sp_overlap"  # "Sacrifice two creatures and a Vampire: You gain 3 life."


def position(builder, source: str, mine=(), *, tokens: int = 0):
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + [source] + list(mine) + ["blood_token"] * tokens)
        # A land to play keeps the turn here, so "not offered" is asked of
        # this priority and not of a position auto-passed into the next turn.
        .hand(0, ["plains"])
        .library(0, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    # Placed rather than created, so marked a token before anything auto-passes.
    for oid in oids_of(game, "blood_token", 0):
        game.state.objects[oid].is_token = True
    game._advance()
    assert game.pending().player == 0 and game.state.step is Step.PRECOMBAT_MAIN
    return game, only_oid(game, source, 0)


def offered(game) -> list[int]:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_OBJECTS, decision.kind
    return [option.ref.id for option in decision.options]


def pick(game, oid: int) -> None:
    """Answer a one-permanent pick with ``oid``."""
    index = offered(game).index(oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def on_battlefield(game, oid: int) -> bool:
    return oid in game.state.battlefield


class TestEveryPartMustBePayable:
    def test_the_source_and_its_tokens_are_payable(self, builder):
        game, heart = position(builder, HEART, tokens=3)
        assert activations(game, heart)

    def test_one_token_short_is_not(self, builder):
        """118.3: the Heart with two Blood tokens is never offered."""
        game, heart = position(builder, HEART, tokens=2)
        assert not activations(game, heart)

    def test_a_blood_that_is_not_a_token_does_not_count(self, builder):
        game, heart = position(builder, HEART, tokens=3)
        game.state.objects[oids_of(game, "blood_token", 0)[0]].is_token = False
        assert not activations(game, heart)

    def test_a_swamp_and_a_forest_are_payable(self, builder):
        game, lands = position(builder, LANDS, ["swamp", "forest"])
        assert activations(game, lands)

    @pytest.mark.parametrize(
        "mine", [("overgrown_tomb",), ("swamp", "swamp"), ("forest", "forest")]
    )
    def test_one_permanent_never_pays_two_parts(self, builder, mine):
        """A Swamp Forest is one permanent; two Swamps are no Forest."""
        game, lands = position(builder, LANDS, mine)
        assert not activations(game, lands)

    def test_a_dual_beside_a_basic_pays_the_other_part(self, builder):
        game, lands = position(builder, LANDS, ["overgrown_tomb", "swamp"])
        assert activations(game, lands)

    def test_a_shared_permanent_is_counted_once(self, builder):
        """Two creatures and a Vampire, with one Vampire and two other
        creatures: three permanents, but the Vampire must pay the Vampire part,
        and a count per part would have seen three creatures and one Vampire."""
        game, source = position(builder, OVERLAP, ["vampire_1_1_b", "grizzly_bears"])
        assert not activations(game, source)
        game, source = position(
            builder, OVERLAP, ["vampire_1_1_b", "grizzly_bears", "llanowar_elves"]
        )
        assert activations(game, source)


class TestPayingIt:
    def test_the_source_and_the_tokens_go_and_the_effect_resolves(self, builder):
        game, heart = position(builder, HEART, tokens=3)
        blood = oids_of(game, "blood_token", 0)
        life = game.state.players[0].life
        game.apply(activations(game, heart)[0])
        assert not on_battlefield(game, heart)
        assert not any(on_battlefield(game, oid) for oid in blood)
        settle(game)
        assert game.state.players[0].life == life + 13

    def test_the_payer_picks_which_tokens(self, builder):
        game, heart = position(builder, HEART, tokens=4)
        keep, *spend = oids_of(game, "blood_token", 0)
        game.apply(activations(game, heart)[0])
        # The source part is forced; the Blood part offers all four.
        assert sorted(offered(game)) == sorted([keep, *spend])
        decision = game.pending()
        for oid in spend:
            pick(game, oid)
        if game.pending() is decision:
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert oids_of(game, "blood_token", 0) == [keep]
        assert not on_battlefield(game, heart)

    def test_a_dual_may_pay_either_part_when_the_other_is_covered(self, builder):
        game, lands = position(builder, LANDS, ["overgrown_tomb", "swamp", "forest"])
        tomb = only_oid(game, "overgrown_tomb", 0)
        swamp = only_oid(game, "swamp", 0)
        forest = only_oid(game, "forest", 0)
        game.apply(activations(game, lands)[0])
        assert sorted(offered(game)) == sorted([tomb, swamp])
        pick(game, tomb)
        # The Forest part is then forced: the Tomb is taken, so the basic pays.
        assert game.state.objects[tomb].zone is Zone.GRAVEYARD
        assert game.state.objects[forest].zone is Zone.GRAVEYARD
        assert on_battlefield(game, swamp)

    def test_a_dual_needed_by_a_later_part_is_not_offered(self, builder):
        """The Tomb is the only Forest, so taking it as the Swamp would leave
        the cost half paid: the Swamp part is the basic, asked nothing."""
        game, lands = position(builder, LANDS, ["overgrown_tomb", "swamp"])
        tomb = only_oid(game, "overgrown_tomb", 0)
        swamp = only_oid(game, "swamp", 0)
        life = game.state.players[0].life
        game.apply(activations(game, lands)[0])
        assert game.pending().kind is not DecisionKind.CHOOSE_OBJECTS
        assert game.state.objects[tomb].zone is Zone.GRAVEYARD
        assert game.state.objects[swamp].zone is Zone.GRAVEYARD
        settle(game)
        assert game.state.players[0].life == life + 2

    def test_a_pick_that_would_strand_a_later_part_is_not_offered(self, builder):
        game, source = position(
            builder, OVERLAP, ["vampire_1_1_b", "vampire_1_1_b", "grizzly_bears"]
        )
        first, second = oids_of(game, "vampire_1_1_b", 0)
        bears = only_oid(game, "grizzly_bears", 0)
        game.apply(activations(game, source)[0])
        assert sorted(offered(game)) == sorted([first, second, bears])
        pick(game, first)
        # Taking the second Vampire too would leave no Vampire for the second
        # part, so the only creature offered is the Bears -- forced.
        assert all(
            game.state.objects[oid].zone is Zone.GRAVEYARD for oid in (first, second, bears)
        )
        settle(game)

    def test_it_reads_as_a_sacrifice(self, registry):
        assert registry.get(HEART).abilities[0].cost.describe() == "{1}, Sacrifice"


class TestTheLoaderChecksIt:
    def _card(self, cost: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_sp_bad",
                "name": "Test Bad Sacrifice Parts",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": "Sacrifice a Swamp and a Forest: You gain 2 life.",
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Sacrifice a Swamp and a Forest: You gain 2 life.",
                        "cost": cost,
                        "effects": [{"op": "gain_life", "player": "you", "amount": 2}],
                    }
                ],
            }
        )

    def test_two_parts_compile(self):
        card = compile_card(
            self._card({"sacrifice": [{"subtypes": ["Swamp"]}, {"subtypes": ["Forest"]}]})
        )
        cost = card.abilities[0].cost
        assert cost.sacrifice is None
        assert [dict(p) for p in cost.sacrifice_parts] == [
            {"subtypes": ["Swamp"]},
            {"subtypes": ["Forest"]},
        ]

    def test_one_part_is_the_plain_form(self):
        with pytest.raises(DslError, match="two or more"):
            compile_card(self._card({"sacrifice": [{"subtypes": ["Swamp"]}]}))

    def test_a_part_names_nothing(self):
        with pytest.raises(DslError, match="'as'"):
            compile_card(
                self._card(
                    {"sacrifice": [{"subtypes": ["Swamp"], "as": "it"}, {"subtypes": ["Forest"]}]}
                )
            )

    @pytest.mark.parametrize("count", [0, -1, "two", True])
    def test_a_count_is_a_positive_whole_number(self, count):
        with pytest.raises(DslError, match="count"):
            compile_card(
                self._card(
                    {"sacrifice": [{"subtypes": ["Swamp"], "count": count}, {"subtypes": ["Forest"]}]}
                )
            )

    def test_a_malformed_part_is_refused(self):
        with pytest.raises(DslError, match=r"sacrifice\[1\]"):
            compile_card(
                self._card({"sacrifice": [{"subtypes": ["Swamp"]}, {"subtype": ["Forest"]}]})
            )

    def test_not_beside_sacrifice_x(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card(
                    {
                        "sacrifice": [{"subtypes": ["Swamp"]}, {"subtypes": ["Forest"]}],
                        "sacrifice_x": {"subtypes": ["Food"]},
                    }
                )
            )

    def test_not_on_a_spells_additional_cost(self):
        with pytest.raises(DslError, match="activated ability"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_sp_bad_spell",
                        "name": "Test Bad Sacrifice Parts Spell",
                        "mana_cost": "{B}",
                        "types": ["Sorcery"],
                        "oracle_text": (
                            "As an additional cost to cast this spell, sacrifice a Swamp "
                            "and a Forest.\nYou gain 2 life."
                        ),
                        "additional_cost": {
                            "sacrifice": [{"subtypes": ["Swamp"]}, {"subtypes": ["Forest"]}]
                        },
                        "spell_effects": [{"op": "gain_life", "player": "you", "amount": 2}],
                    }
                )
            )
