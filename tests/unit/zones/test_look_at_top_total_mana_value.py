"""`look_at_top`'s ``total_mana_value``: a cap on the **sum** of what is taken.

    Smelting Vat -- "Reveal the top eight cards of your library. Put up to two
    noncreature artifact cards with total mana value less than or equal to the
    sacrificed artifact's mana value from among them onto the battlefield…"

    Ao, the Dawn Sky -- "Look at the top seven cards of your library. Put any
    number of nonland permanent cards with total mana value 4 or less from
    among them onto the battlefield."

"Total" is a constraint between the picks, which no selector clause can state:
each clause judges one card alone. The near miss, a per-card `mana_value <= N`
filter, is a strictly better card -- Ao would put three 4-drops onto the
battlefield, and Smelting Vat two cards each as big as the artifact it ate.

The pick is asked one card at a time (the way `choose_permanents`'s
`max_total_power` is), each question offering only what still fits under what
is left, and stopping at the selector's count or whenever the chooser declines.
The cap is a value expression read as the op resolves, so Smelting Vat's
`{"mana_value_of": {"binding": "sacrificed"}}` reads the cost's last-known
snapshot of the artifact it sacrificed. Composed from `ask_objects`; no new
`DecisionKind`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, only_oid

VAT = "t_tmv_vat"
#: Mana values 1, 2, 3, 4 and a 4-mana artifact *creature* the Vat may not take.
RING, STONE, SPHERE, ARCHIVE, SOLEMN = (
    "sol_ring",
    "mind_stone",
    "commanders_sphere",
    "hedron_archive",
    "solemn_simulacrum",
)


def ao_spec(cap=4):
    return {
        "op": "look_at_top",
        "amount": 7,
        "objects": {
            "any_types": ["Artifact", "Creature", "Enchantment", "Planeswalker", "Battle"],
            "not_types": ["Land"],
            "count": "any",
        },
        "total_mana_value": cap,
        "destination": "battlefield",
        "rest_to_bottom": True,
    }


def a_library(builder, top):
    game = (
        builder(players=2)
        .library(0, [*top, "island", "island"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, list(game.state.players[0].library[: len(top)])


def mv(game, oid) -> int:
    return game.state.card_of(game.state.objects[oid]).mana_value


def run(game, spec, pick):
    """Run ``spec``; ``pick(decision)`` answers each question (indices into its options)."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [spec])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            decision = gen.send(pick(decision))
    except StopIteration:
        pass
    return asked


def take(game, *def_ids):
    """Answer each question with the next of ``def_ids``, then decline."""
    queue = list(def_ids)

    def pick(decision):
        if not queue:
            return []
        want = queue.pop(0)
        for i, option in enumerate(decision.options):
            if game.state.objects[option.value].def_id == want:
                return [i]
        raise AssertionError(f"{want} was not offered")

    return pick


def offered(game, decision) -> list[str]:
    return sorted(game.state.objects[o.value].def_id for o in decision.options)


def zone(game, oid) -> Zone:
    return game.state.objects[oid].zone


@pytest.fixture
def ao(builder):
    game, top = a_library(builder, [ARCHIVE, SPHERE, RING, STONE, "island", SOLEMN, ARCHIVE])
    return game, top


class TestTheSumIsCapped:
    def test_each_question_offers_only_what_still_fits(self, ao):
        game, _top = ao
        asked = run(game, ao_spec(), take(game, SPHERE, RING))
        assert [offered(game, d) for d in asked] == [
            sorted([ARCHIVE, SPHERE, RING, STONE, SOLEMN, ARCHIVE]),
            [RING],
        ], "after a 3, only the 1 fits under 4; after the 1, nothing does"
        assert all(d.kind is DecisionKind.CHOOSE_OBJECTS for d in asked)
        assert all((d.min_count, d.max_count) == (0, 1) for d in asked)

    def test_one_four_drop_and_nothing_else(self, ao):
        game, top = ao
        asked = run(game, ao_spec(), take(game, ARCHIVE))
        assert len(asked) == 1, "a 4-drop spends the whole cap; nothing is left to offer"
        on_field = [o for o in top if zone(game, o) is Zone.BATTLEFIELD]
        assert [game.state.objects[o].def_id for o in on_field] == [ARCHIVE]

    def test_the_picks_never_add_up_over_the_cap(self, ao):
        game, top = ao
        run(game, ao_spec(), lambda d: [0])
        taken = [o for o in top if zone(game, o) is Zone.BATTLEFIELD]
        assert taken and sum(mv(game, o) for o in taken) <= 4

    def test_the_cap_is_a_value_expression(self, ao):
        game, _top = ao
        asked = run(game, ao_spec({"const": 1}), lambda d: [])
        assert [offered(game, d) for d in asked] == [[RING]]


class TestItMayStopShort:
    def test_declining_the_first_question_takes_nothing(self, ao):
        game, top = ao
        asked = run(game, ao_spec(), lambda d: [])
        assert len(asked) == 1
        assert not any(zone(game, o) is Zone.BATTLEFIELD for o in top)

    def test_the_rest_go_to_the_bottom(self, ao):
        game, top = ao
        run(game, ao_spec(), take(game, STONE))
        library = game.state.players[0].library
        assert library[:2] == [o for o in library if game.state.objects[o].def_id == "island"][:2]
        assert set(library[2:]) == {o for o in top if zone(game, o) is Zone.LIBRARY}

    def test_a_count_caps_how_many_as_well_as_how_much(self, builder):
        game, top = a_library(builder, [RING, RING, RING, "island"])
        spec = {**ao_spec(), "objects": {"types": ["Artifact"], "count": 2, "optional": True}}
        asked = run(game, spec, lambda d: [0])
        assert len(asked) == 2, "three 1-drops fit under 4, but the count is two"
        assert [zone(game, o) for o in top].count(Zone.BATTLEFIELD) == 2


class TestSmeltingVat:
    def vat(self, builder, fodder):
        game = (
            builder(players=2)
            .battlefield(0, [VAT, fodder])
            .library(0, [SPHERE, SOLEMN, STONE, RING, ARCHIVE, "island", "island", "island", "island"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game

    def activate(self, game, fodder):
        game.apply(activations(game, only_oid(game, VAT))[0])
        decision = game.pending()
        if decision.kind is DecisionKind.CHOOSE_OBJECTS and decision.context.get("purpose") != "look_at_top":
            sac = only_oid(game, fodder)
            index = next(i for i, o in enumerate(decision.options) if o.value == sac)
            game.apply(find_action(game, ActionKind.CHOOSE, choice=index))
        for _ in range(20):
            decision = game.pending()
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                return decision
            game.apply(find_action(game, ActionKind.PASS))
        raise AssertionError("the Vat never asked")

    def test_the_cap_is_the_sacrificed_artifacts_mana_value(self, builder):
        game = self.vat(builder, SPHERE)
        decision = self.activate(game, SPHERE)
        assert offered(game, decision) == sorted([SPHERE, STONE, RING]), (
            "noncreature artifacts of mana value 3 or less; never Solemn or the Archive"
        )
        game.apply(find_action(game, ActionKind.CHOOSE, choice=offered_index(game, decision, STONE)))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert offered(game, decision) == [RING], "two of the three spent; one is left"

    def test_a_bigger_sacrifice_buys_a_bigger_card(self, builder):
        game = self.vat(builder, ARCHIVE)
        decision = self.activate(game, ARCHIVE)
        assert ARCHIVE in offered(game, decision) and SOLEMN not in offered(game, decision)


def offered_index(game, decision, def_id) -> int:
    return next(
        i for i, o in enumerate(decision.options) if game.state.objects[o.value].def_id == def_id
    )


class TestTheLoader:
    def card(self, **effect):
        return {
            "id": "t_bad_tmv",
            "name": "Test Bad Total",
            "oracle_text": "Dig.",
            "mana_cost": "{G}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "look_at_top", "amount": 7, **effect}],
        }

    def compile(self, **effect):
        return compile_card(CardModel.model_validate(self.card(**effect)))

    def test_an_any_number_pick_loads(self):
        self.compile(objects={"count": "any"}, total_mana_value=4)

    def test_an_up_to_pick_loads(self):
        self.compile(objects={"count": 2, "optional": True}, total_mana_value=4)

    @pytest.mark.parametrize(
        "objects",
        [{"count": "all"}, {"count": 2}, {}, None],
        ids=["all", "mandatory", "no-count", "no-objects"],
    )
    def test_a_count_the_cap_cannot_stop_short_of_is_refused(self, objects):
        effect = {"total_mana_value": 4}
        if objects is not None:
            effect["objects"] = objects
        with pytest.raises(DslError, match="total_mana_value"):
            self.compile(**effect)

    def test_beside_destinations_it_is_refused(self):
        with pytest.raises(DslError, match="destinations"):
            self.compile(
                total_mana_value=4,
                objects={"count": "any"},
                destinations=[{"to": "hand", "count": 1}],
            )

    def test_the_cap_is_validated_as_a_value(self):
        with pytest.raises(DslError):
            self.compile(objects={"count": "any"}, total_mana_value={"nonsense": 1})
