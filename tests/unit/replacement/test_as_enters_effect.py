"""An "as this enters" effect whose result the permanent enters with -- 614.1c.

    "As Sin enters, remove all counters from any number of artifacts,
     creatures, and enchantments. Sin enters with X +1/+1 counters on it,
     where X is twice the number of counters removed this way."
                                        -- Sin, Unending Cataclysm

A `self_enters_with_counters` replacement's ``as_enters`` effects run as part
of the arrival, and a name they bind is what its ``amount`` reads. The cheaper
spelling -- a `self_enters` trigger running `remove_counters` and then
`add_counters` -- puts the permanent on the battlefield at its printed size
first: a printed 0/0 is binned by state-based actions before the trigger
resolves, every other enters trigger reads a size the replacement says was
never on the board, and an opponent holds priority with the counters still
where they were. `TestTheCountersArePartOfTheArrival` is that argument.

The choice is made as the permanent enters, by its controller, out of every
artifact, creature and enchantment on the battlefield -- anybody's, and no
land. "All counters" is every kind, so the number removed is the multiset's
size, not the +1/+1 count. `t_ae_cataclysm` is Sin's line on a printed 0/0.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card, only_oid, pass_until

CATACLYSM = "t_ae_cataclysm"
RELIC, BEAR, SHRINE, VAULT = "t_ae_relic", "t_ae_bear", "t_ae_shrine", "t_ae_vault"
WATCHER = "t_ae_watcher"
RAISE = "t_riot_raise"  # returns a creature card from your graveyard


def position(builder, *, hand=(CATACLYSM,), graveyard=(), mine=(), theirs=()):
    """Eight Swamps, a main phase, and ``mine``/``theirs`` as (id, counters)."""
    b = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 8)
        .hand(0, list(hand))
        .graveyard(0, list(graveyard))
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
    )
    for card_id, counters in mine:
        b = b.battlefield(0, [card_id], counters=counters)
    for card_id, counters in theirs:
        b = b.battlefield(1, [card_id], counters=counters)
    game = b.build(advance=False)
    game._advance()
    return game


def the_choice(game):
    """The pending "remove all counters from" pick, or None."""
    pending = game.pending()
    if pending is None or pending.kind is not DecisionKind.CHOOSE_OBJECTS:
        return None
    return pending


def offered(game) -> set[int]:
    return {o.ref.id for o in the_choice(game).options if o.ref is not None}


def choose(game, oids) -> None:
    """Pick exactly ``oids`` from the pending pick, then finish it."""
    decision = the_choice(game)
    assert decision is not None
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
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )


def cast_choosing(game, card_id, oids) -> None:
    """Cast ``card_id``, resolve it, and answer the as-enters pick with ``oids``."""
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    for _ in range(100):
        if the_choice(game) is not None:
            choose(game, oids)
            break
        decision = game.pending()
        assert decision is not None
        game.apply(_default_answer(game, decision))
    else:
        raise AssertionError("the as-enters choice was never asked")
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def resolve_until_choice(game, card_id) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    for _ in range(100):
        if the_choice(game) is not None:
            return
        game.apply(_default_answer(game, game.pending()))
    raise AssertionError("the as-enters choice was never asked")


def cataclysm(game):
    return next(o for o in game.state.objects.values() if o.def_id == CATACLYSM)


class TestThePool:
    def test_artifacts_creatures_and_enchantments_of_anybody_are_offered(self, builder):
        game = position(
            builder,
            mine=[(RELIC, {"charge": 1}), (BEAR, {"+1/+1": 1})],
            theirs=[(SHRINE, {"lore": 1})],
        )
        resolve_until_choice(game, CATACLYSM)
        assert offered(game) == {
            only_oid(game, RELIC),
            only_oid(game, BEAR),
            only_oid(game, SHRINE),
        }

    def test_a_land_is_not_offered(self, builder):
        game = position(builder, mine=[(BEAR, {"+1/+1": 1}), (VAULT, {"charge": 2})])
        resolve_until_choice(game, CATACLYSM)
        assert only_oid(game, VAULT) not in offered(game)

    def test_the_entering_permanent_is_not_offered(self, builder):
        """It is not on the battlefield yet, so it is not one of the
        "artifacts, creatures, and enchantments"."""
        game = position(builder, mine=[(BEAR, {})])
        resolve_until_choice(game, CATACLYSM)
        assert cataclysm(game).oid not in offered(game)

    def test_the_controller_is_asked(self, builder):
        game = position(builder, mine=[(BEAR, {})])
        resolve_until_choice(game, CATACLYSM)
        assert the_choice(game).player == 0


class TestWhatComesOff:
    def test_every_counter_of_every_kind_comes_off_the_chosen(self, builder):
        game = position(builder, mine=[(BEAR, {"+1/+1": 2, "stun": 1, "shield": 1})])
        cast_choosing(game, CATACLYSM, [only_oid(game, BEAR)])
        assert game.state.objects[only_oid(game, BEAR)].counters.get("+1/+1", 0) == 0
        assert not any(game.state.objects[only_oid(game, BEAR)].counters.values())

    def test_what_is_not_chosen_keeps_its_counters(self, builder):
        game = position(
            builder, mine=[(BEAR, {"+1/+1": 1})], theirs=[(RELIC, {"charge": 3})]
        )
        cast_choosing(game, CATACLYSM, [only_oid(game, BEAR)])
        assert game.state.objects[only_oid(game, RELIC)].counters["charge"] == 3

    def test_an_opponents_permanent_may_be_stripped(self, builder):
        game = position(builder, theirs=[(SHRINE, {"lore": 2})])
        cast_choosing(game, CATACLYSM, [only_oid(game, SHRINE)])
        assert not any(game.state.objects[only_oid(game, SHRINE)].counters.values())


class TestTheCountersArePartOfTheArrival:
    def test_it_enters_with_twice_the_number_removed(self, builder):
        """Four counters of three kinds off two permanents: eight +1/+1."""
        game = position(
            builder,
            mine=[(BEAR, {"+1/+1": 1, "shield": 1})],
            theirs=[(RELIC, {"charge": 2})],
        )
        cast_choosing(game, CATACLYSM, [only_oid(game, BEAR), only_oid(game, RELIC)])
        obj = cataclysm(game)
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.counters["+1/+1"] == 8
        seen = chars(game.state, obj.oid)
        assert (seen.power, seen.toughness) == (8, 8)

    def test_an_enters_trigger_reads_the_size_with_the_counters(self, builder):
        """The watcher's trigger reads the arrival's power: the counters were
        on before any enters trigger looked, so it gains 4 and not 0."""
        game = position(builder, mine=[(WATCHER, {}), (RELIC, {"charge": 2})])
        life = game.state.players[0].life
        cast_choosing(game, CATACLYSM, [only_oid(game, RELIC)])
        assert game.state.players[0].life == life + 4

    def test_choosing_nothing_removes_nothing_and_adds_nothing(self, builder):
        """"Any number" includes none, and the printed 0/0 then dies to
        state-based actions -- the printed answer."""
        game = position(builder, mine=[(BEAR, {"+1/+1": 2})])
        cast_choosing(game, CATACLYSM, [])
        assert game.state.objects[only_oid(game, BEAR)].counters["+1/+1"] == 2
        assert cataclysm(game).zone is Zone.GRAVEYARD

    def test_the_binding_does_not_outlive_the_arrival(self, builder):
        game = position(builder, mine=[(RELIC, {"charge": 1})])
        cast_choosing(game, CATACLYSM, [only_oid(game, RELIC)])
        assert cataclysm(game).as_enters_bindings is None


class TestEveryArrival:
    def test_a_reanimated_permanent_is_asked_too(self, builder):
        """The clause is about any arrival, not only a cast one."""
        game = position(
            builder, hand=(RAISE,), graveyard=(CATACLYSM,), mine=[(RELIC, {"charge": 3})]
        )
        cast_choosing(game, RAISE, [only_oid(game, RELIC)])
        obj = cataclysm(game)
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.counters["+1/+1"] == 6


def _card(replacement) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "types": ["Creature"],
            "mana_cost": "{1}",
            "power": 0,
            "toughness": 0,
            "replacements": [replacement],
        }
    )


STRIP = {
    "op": "remove_counters",
    "all_kinds": True,
    "objects": {"zone": "battlefield", "types": ["Creature"], "count": "any"},
    "as": "removed",
}


class TestLoadTimeRefusals:
    def test_the_written_shape_loads(self):
        card = compile_card(
            _card(
                {
                    "event": "self_enters_with_counters",
                    "counter": "+1/+1",
                    "amount": {"binding": "removed"},
                    "as_enters": [STRIP],
                }
            )
        )
        assert card.replacements[0]["as_enters"][0]["op"] == "remove_counters"

    def test_as_enters_on_another_event_is_refused(self):
        with pytest.raises(DslError, match="as_enters"):
            compile_card(_card({"event": "self_enters_tapped", "as_enters": [STRIP]}))

    def test_an_empty_as_enters_is_refused(self):
        with pytest.raises(DslError, match="as_enters"):
            compile_card(_card({"event": "self_enters_with_counters", "as_enters": []}))

    def test_an_effect_inside_is_validated(self):
        with pytest.raises(DslError):
            compile_card(
                _card(
                    {
                        "event": "self_enters_with_counters",
                        "as_enters": [{"op": "no_such_op"}],
                    }
                )
            )

    @pytest.mark.parametrize("extra", [{"counter": "+1/+1"}, {"amount": 1}, {"any_kind": True}])
    def test_all_kinds_beside_a_kind_or_number_is_refused(self, extra):
        with pytest.raises(DslError, match="all_kinds"):
            compile_card(
                _card(
                    {
                        "event": "self_enters_with_counters",
                        "as_enters": [{**STRIP, **extra}],
                    }
                )
            )

    def test_all_kinds_needs_objects(self):
        strip = {k: v for k, v in STRIP.items() if k != "objects"}
        with pytest.raises(DslError, match="objects"):
            compile_card(_card({"event": "self_enters_with_counters", "as_enters": [strip]}))
