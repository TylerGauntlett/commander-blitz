"""Unearth — the third way to leave a zone you were activated from.

    "Unearth {1}{B} ({1}{B}: Return this card from your graveyard to the
    battlefield. It gains haste. Exile it at the beginning of the next end step.
    Unearth only as a sorcery.)"

Every piece of this already existed — activating from the graveyard is embalm's,
permanent haste is riot's, and the delayed exile is `delay`. What refused the
card was the **guard**: an activated ability whose `active_zones` reach outside
the battlefield must have a cost that removes its source from that zone, or it
is an infinite engine. Cycling discards itself, embalm exiles itself, and
unearth pays plain mana.

The guard was right about the property and too narrow about how to get it. What
matters is that the source cannot still be sitting in that zone afterwards, and
unearth's *effect* is what takes it out. So a third satisfier: an unconditional
top-level effect that moves `self_only` out.

**Unconditional** and **top-level** are both load-bearing. An exit nested inside
an `if` or a `may` might not run, and an ability whose only way out is a branch
the player can decline is activatable again from the same graveyard — which is
exactly the shape the guard exists to refuse.

The reminder's other half — "**or if it would leave the battlefield**" — is a
replacement effect, and it was the recorded divergence here for a long time.
`replace_deaths` was the only zone-change redirect in the DSL and `move_object`
gates it on a battlefield → graveyard move, so it catches a death and nothing
else. Unearth's clause is the *whole* departure: bounced to hand, exiled by
removal, shuffled into a library, sent to the command zone.

That is now `replace_leaves_battlefield`, and the difference is not cosmetic on
the card that asked for it. Priest of Fell Rites sacrifices *itself* to
reanimate, and the replacement is what makes that a one-way trip; read as
death-only, an opponent's bounce hands the card back to be unearthed again.

The two markers stay separate because their **lifetimes** differ, which is the
part a wider gate on `dies_to` would have got wrong: "would die this turn" is
cleared at cleanup, while unearth's lasts exactly as long as the permanent is on
the battlefield. `t_unearther_death_only` is the counterfactual.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Keyword, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import advance_to_step, find_action, pass_until

SWAMP = "swamp"
ZOMBIE = "t_unearther"


def position(builder, lands: int = 4):
    game = (
        builder(players=2)
        .battlefield(0, [SWAMP] * lands)
        .graveyard(0, [ZOMBIE])
        .build()
    )
    zombie = game.state.players[0].graveyard[0]
    return game, zombie


def unearth(game, zombie: int):
    action = find_action(game, ActionKind.ACTIVATE, source=zombie)
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)


class TestTheAbilityIsOffered:
    def test_it_is_activatable_from_the_graveyard(self, builder):
        game, zombie = position(builder)
        assert find_action(game, ActionKind.ACTIVATE, source=zombie) is not None

    def test_it_is_not_offered_without_the_mana(self, builder):
        game, zombie = position(builder, lands=1)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == zombie
        ]


class TestWhatItDoes:
    def test_the_creature_arrives_on_the_battlefield(self, builder):
        game, zombie = position(builder)
        unearth(game, zombie)

        assert game.state.objects[zombie].zone is Zone.BATTLEFIELD
        assert game.state.objects[zombie].controller == 0

    def test_it_has_haste(self, builder):
        """`duration: "permanent"` — an until-EOT haste would evaporate before
        the very combat the card is unearthed for."""
        game, zombie = position(builder)
        unearth(game, zombie)

        assert Keyword.HASTE.value in chars(game.state, zombie).keywords

    def test_it_is_exiled_at_the_next_end_step(self, builder):
        game, zombie = position(builder)
        unearth(game, zombie)
        assert game.state.objects[zombie].zone is Zone.BATTLEFIELD

        advance_to_step(game, Step.END_STEP)
        pass_until(game, lambda g: g.state.objects[zombie].zone is not Zone.BATTLEFIELD)

        assert game.state.objects[zombie].zone is Zone.EXILE

    def test_it_is_gone_from_the_graveyard_so_it_cannot_be_unearthed_twice(self, builder):
        """The property the guard is actually about."""
        game, zombie = position(builder, lands=8)
        unearth(game, zombie)

        assert zombie not in game.state.players[0].graveyard
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == zombie
        ]


def graveyard_ability(*effects, cost=None) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_unearth_probe",
            "name": "Unearth Probe",
            "mana_cost": "{2}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "active_zones": ["graveyard"],
                    "cost": cost or {"mana": "{1}"},
                    "effects": list(effects),
                }
            ],
        }
    )


RETURN_SELF = {
    "op": "put_onto_battlefield",
    "controller": "you",
    "objects": {"zone": "graveyard", "self_only": True},
}


class TestTheWidenedGuard:
    def test_an_effect_that_returns_the_source_satisfies_it(self):
        compile_card(graveyard_ability(RETURN_SELF))

    def test_mana_alone_is_still_refused(self):
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(graveyard_ability({"op": "draw", "player": "you"}))

    def test_moving_somebody_elses_card_does_not_count(self):
        """"Return **a** creature card" has not moved this ability's source."""
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(
                graveyard_ability(
                    {
                        "op": "put_onto_battlefield",
                        "objects": {"zone": "graveyard", "types": ["Creature"]},
                    }
                )
            )

    def test_an_exit_inside_a_may_does_not_count(self):
        """Declining leaves the card in the graveyard, ready to be paid for again."""
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(
                graveyard_ability({"op": "may", "effects": [RETURN_SELF]})
            )

    def test_an_exit_inside_an_if_does_not_count(self):
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(
                graveyard_ability(
                    {"op": "if", "condition": {"is_your_turn": True}, "then": [RETURN_SELF]}
                )
            )

    def test_the_old_satisfiers_still_work(self):
        """Embalm's self-exile cost, unchanged."""
        compile_card(
            graveyard_ability(
                {"op": "draw", "player": "you"},
                cost={"mana": "{1}", "exile_from_graveyard": {"self_only": True, "count": 1}},
            )
        )


class TestItIsExiledHoweverItLeaves:
    """The half that used to be the recorded divergence.

    Every route off the battlefield, not just the death: the printed clause says
    "leave", and dying is one way of leaving.
    """

    def bounced(self, builder, card: str, to: Zone):
        game = (
            builder(players=2)
            .battlefield(0, [SWAMP] * 4)
            .graveyard(0, [card])
            .build()
        )
        oid = game.state.players[0].graveyard[0]
        game.apply(find_action(game, ActionKind.ACTIVATE, source=oid))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

        from commanderblitz.engine.zones import move_object

        move_object(game.state, oid, to, to_player=0, cause="test")
        return game.state.objects[oid].zone

    def test_a_bounce_exiles_it_instead(self, builder):
        assert self.bounced(builder, ZOMBIE, Zone.HAND) is Zone.EXILE

    def test_a_shuffle_back_exiles_it_instead(self, builder):
        assert self.bounced(builder, ZOMBIE, Zone.LIBRARY) is Zone.EXILE

    def test_a_death_still_exiles_it(self, builder):
        """The case `replace_deaths` already covered, and still does."""
        assert self.bounced(builder, ZOMBIE, Zone.GRAVEYARD) is Zone.EXILE

    def test_the_death_only_version_hands_the_card_back(self, builder):
        """The counterfactual, and the loop the printed clause closes.

        A bounced card sits in hand, ready to be cast and unearthed all over
        again -- which is a strictly better card than the printed one.
        """
        assert self.bounced(builder, "t_unearther_death_only", Zone.HAND) is Zone.HAND

    def test_and_still_gets_the_death_right(self, builder):
        """Which is why the near miss is so easy to ship: half of it works."""
        assert (
            self.bounced(builder, "t_unearther_death_only", Zone.GRAVEYARD)
            is Zone.EXILE
        )

