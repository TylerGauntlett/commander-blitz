"""Modes are chosen as the spell is cast, not as it resolves.

Rule 601.2b puts mode selection at cast time. The engine used to ask inside
`op_choose_mode`, i.e. on resolution -- a documented simplification whose one
observable consequence was that an opponent holding a counterspell could not see
which mode they were responding to.

`Game._cast` now asks first and records the answer on `StackItem.modes`;
`EffectContext.modes` carries it to `op_choose_mode`, which consumes it instead
of asking. Both of those fields existed and were never assigned by anything
until now.

Two shapes deliberately keep resolution-time modes, and the negative tests below
are the point of the change rather than an afterthought: a **triggered** ability
has no cast to be asked at, and a **nested** `choose_mode` is a second question
that really does belong to resolution.

The residual divergence, which this does *not* fix: targets are enumerated as
part of the action, so they are still picked before modes -- the reverse of the
printed order. That is why the shared `optional: true` target idiom in
docs/card-dsl.md is still required.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import pass_until

PUMP, HEXPROOF, BOUNCE = 0, 1, 2


def cast_charm(builder):
    """Cast Simic Charm at the opponent's bear, stopping at the mode question."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "island", "grizzly_bears"])
        .battlefield(1, ["grizzly_bears"])
        .hand(0, ["simic_charm"])
        .build()
    )
    theirs = next(
        o.oid for o in game.state.battlefield_objects(1) if o.def_id == "grizzly_bears"
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "simic_charm"
        and any(ref.id == theirs for ref in a.targets)
    )
    game.apply(action)
    return game, theirs


def answer(game, mode: int):
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode
    )
    game.apply(action)


def untapped_lands(game, pid: int = 0) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(pid)
        if not o.tapped and "Land" in chars(game.state, o.oid).types
    )


class TestTheQuestionMovesToCastTime:
    def test_the_mode_is_asked_immediately(self, builder):
        game, _ = cast_charm(builder)
        assert game.pending().kind is DecisionKind.CHOOSE_MODE

    def test_it_is_asked_before_the_spell_reaches_the_stack(self, builder):
        # The observable half of the old simplification: an opponent could not
        # see the mode they were responding to, because it was not chosen yet.
        game, _ = cast_charm(builder)
        assert game.state.stack == []

    def test_it_is_asked_before_the_cost_is_paid(self, builder):
        # Rule 601.2b puts modes ahead of 601.2h. Both lands are still up.
        game, _ = cast_charm(builder)
        assert untapped_lands(game) == 2

    def test_the_answer_is_recorded_on_the_stack_item(self, builder):
        game, _ = cast_charm(builder)
        answer(game, BOUNCE)
        # `StackItem.modes` existed for exactly this and was never written to.
        item = next((i for i in game.state.stack if i.kind == "spell"), None)
        if item is not None:
            assert item.modes == (BOUNCE,)

    def test_the_mode_is_not_asked_twice(self, builder):
        game, _ = cast_charm(builder)
        answer(game, BOUNCE)
        pass_until(game, lambda g: g.state.objects[_bear(g)].zone is Zone.HAND)
        assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_MODE


def _bear(game):
    return next(
        oid
        for oid, obj in game.state.objects.items()
        if obj.def_id == "grizzly_bears" and obj.owner == 1
    )


class TestEveryModeStillWorks:
    def test_pump(self, builder):
        game, theirs = cast_charm(builder)
        answer(game, PUMP)
        pass_until(game, lambda g: chars(g.state, theirs).power == 5)
        got = chars(game.state, theirs)
        assert (got.power, got.toughness) == (5, 5)

    def test_hexproof(self, builder):
        game, theirs = cast_charm(builder)
        answer(game, HEXPROOF)
        pass_until(
            game, lambda g: "hexproof" in chars(g.state, _mine(g)).keywords
        )
        assert all(
            "hexproof" in chars(game.state, o.oid).keywords
            for o in game.state.battlefield_objects(0)
        )
        assert "hexproof" not in chars(game.state, theirs).keywords

    def test_bounce(self, builder):
        game, theirs = cast_charm(builder)
        answer(game, BOUNCE)
        pass_until(game, lambda g: g.state.objects[theirs].zone is Zone.HAND)
        assert theirs in game.state.players[1].hand


def _mine(game):
    return next(o.oid for o in game.state.battlefield_objects(0))


class TestWhatKeepsAskingLate:
    """The negatives. Pre-answering these would bind the wrong question."""

    def test_a_triggered_ability_still_asks_on_resolution(self, registry):
        # Lotus Cobra's landfall trigger has a `choose_mode` in it. There is no
        # cast for it to be asked at, so `cast_time_modes` must decline.
        card = registry.get("lotus_cobra")
        assert card.cast_time_modes is None
        for ability in card.abilities:
            assert not ability.is_activated or ability.cast_time_modes is None

    def test_a_mana_ability_is_never_pre_asked(self, registry):
        # Commander's Sphere's colour choice is compiled into `mana_options` and
        # resolved by the payment solver or by `Action.mana_option`. Routing it
        # through a cast-time question would put a mana ability on the stack.
        sphere = registry.get("commanders_sphere")
        mana = next(a for a in sphere.abilities if a.is_mana_ability)
        assert mana.mana_options, "the solver still reads these"

    def test_an_activated_ability_is_pre_asked(self, registry):
        # The other half: Koma's activated ability is modal and does have a
        # moment of activation to ask at.
        koma = registry.get("koma_cosmos_serpent")
        assert any(a.is_activated and a.cast_time_modes for a in koma.abilities)


class TestTheRuleIsMechanical:
    """`cast_time_modes` counts the whole tree rather than trusting position."""

    def test_a_card_with_no_modes_declines(self, registry):
        assert registry.get("grizzly_bears").cast_time_modes is None

    def test_one_top_level_choose_mode_qualifies(self, registry):
        assert registry.get("simic_charm").cast_time_modes is not None

    def test_a_nested_choose_mode_disqualifies_the_card(self):
        # Two questions, and only one `modes` slot to answer with -- so the card
        # keeps asking as it resolves rather than binding the outer answer to
        # whichever `choose_mode` happens to run first.
        from commanderblitz.engine.carddef import CardDef, count_mode_specs

        nested = (
            {
                "op": "choose_mode",
                "modes": [
                    {"label": "A", "effects": [{"op": "draw"}]},
                    {
                        "label": "B",
                        "effects": [
                            {"op": "choose_mode", "modes": [{"label": "B1", "effects": []}]}
                        ],
                    },
                ],
            },
        )
        assert count_mode_specs(nested) == 2
        assert CardDef(id="x", name="X", spell_effects=nested).cast_time_modes is None
