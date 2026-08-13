"""Mutate — two cards, one permanent, and why that fits in one field.

    "Mutate {1}{G} (If you cast this spell for its mutate cost, put it over or
    under target non-Human creature you own. They mutate into the creature on
    top plus all abilities from under it.)"

The census called this the one genuine subsystem it had left: "a `GameObject` is
one card, and every choke point the other reversals leaned on — `card_of`,
`chars`, `zones.move_object` — assumes exactly that."

The first half of that is true and the conclusion is backwards. Because
`card_of` is a **single** choke point, a merged permanent can be one
`CardDef` **synthesised at merge time** — the card on top, carrying the abilities
of everything under it — and every reader in the engine gets the union with no
changes at all:

| reader | what it asks | what it gets |
|---|---|---|
| `chars` | name, types, P/T, colours | the **top** card's |
| `legality._activate_actions` | `card.abilities[i]` | the union, one index space |
| `triggers.fire` | the same list | the same list |
| `stack.ability_of` | the same list | the same list |
| the serializer | `card_of(obj).id` | the top card |

The alternative — a list of cards per permanent, and every one of those readers
taught to walk it — is the subsystem the census was afraid of. It is not needed,
and the reason is the same one `transform` and morph both leaned on.

What *is* new is the pile. The cards underneath stay in `state.objects` and in
**no zone list**, which is where a card on the stack already lives, so nothing
walking the battlefield sees them twice; and `move_object`, the single
zone-change path, sends them wherever the permanent goes.

"Over or under" is asked at **resolution**, not at cast time: 702.140b puts it
there, and a choice made as the spell was cast would be one made before anybody
could respond to it — a different card.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Keyword, Zone
from automtg.engine.zones import destroy
from tests.conftest import only_oid, pass_until

FOREST = "forest"
MUTATOR = "t_mutator"      # {3}{G} 4/4 trample, mutate {1}{G}, "{G}: +1/+1"
HOST = "t_mutant_host"     # {1}{G} 1/3 Beast, "{T}: gain 1 life"
HUMAN = "t_human"          # {1}{W} 2/2 Human Soldier


def position(builder, host: str = HOST, lands: int = 8):
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * lands)
        .battlefield(0, [host])
        .hand(0, [MUTATOR])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


def cast_lines(game) -> list[str]:
    return [a.base_label or "" for a in game.legal_actions() if a.kind is ActionKind.CAST]


def mutate(game, host: int, *, on_top: bool) -> int:
    """Cast the Mutator onto `host`, answering the over-or-under question."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.mutated and any(r.id == host for r in a.targets)
    )
    newcomer = action.source
    game.apply(action)
    # The spell sits on the stack until both players pass, so the over-or-under
    # question is several priority windows away -- which is the point of asking
    # it at resolution rather than at cast time.
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind.value == "may",
        limit=200,
    )
    want = ActionKind.YES if on_top else ActionKind.NO
    game.apply(next(a for a in game.legal_actions() if a.kind is want))
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return newcomer


class TestTheOffer:
    def test_both_lines_are_offered(self, builder):
        game = position(builder)
        assert sorted(set(cast_lines(game))) == [
            "Cast Test Mutator",
            "Cast Test Mutator (mutating)",
        ]

    def test_a_human_may_not_be_mutated_onto(self, builder):
        """"Target **non-Human** creature you own" -- the rule's own target."""
        game = position(builder, host=HUMAN)
        assert set(cast_lines(game)) == {"Cast Test Mutator"}

    def test_with_no_creature_at_all_only_the_creature_line(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 8)
            .hand(0, [MUTATOR])
            .library(0, [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        assert set(cast_lines(game)) == {"Cast Test Mutator"}

    def test_the_mutate_line_is_the_cheaper_one(self, builder):
        """{1}{G} against {3}{G}: with two lands only the mutation is payable."""
        game = position(builder, lands=2)
        assert set(cast_lines(game)) == {"Cast Test Mutator (mutating)"}


class TestOnTop:
    def test_the_permanent_becomes_the_top_card(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)

        c = chars(game.state, host)
        assert (c.power, c.toughness) == (4, 4), "the Mutator's body"
        assert "Elk" in c.subtypes
        assert Keyword.TRAMPLE.value in c.keywords

    def test_it_keeps_the_abilities_from_underneath(self, builder):
        """702.140b: "plus all abilities from under it"."""
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)

        texts = [a.text for a in game.state.card_of(game.state.objects[host]).abilities]
        assert any("+1/+1" in t for t in texts), "the Mutator's own"
        assert any("gain 1 life" in t for t in texts), "and the Host's"

    def test_both_are_offered_as_activated_abilities(self, builder):
        """One ability list means one index space, which legality already walks."""
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )

        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == host
        ]
        assert len(offered) == 2

    def test_there_is_one_permanent_on_the_battlefield(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        newcomer = mutate(game, host, on_top=True)

        creatures = [
            o
            for o in game.state.battlefield
            if "Creature" in chars(game.state, o).types
        ]
        assert creatures == [host]
        assert newcomer not in game.state.battlefield
        assert game.state.objects[newcomer].merged_into == host


class TestUnder:
    def test_the_permanent_stays_the_card_it_was(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=False)

        c = chars(game.state, host)
        assert (c.power, c.toughness) == (1, 3), "still the Host's body"
        assert "Beast" in c.subtypes

    def test_but_it_gains_the_abilities_from_underneath(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=False)

        texts = [a.text for a in game.state.card_of(game.state.objects[host]).abilities]
        assert any("gain 1 life" in t for t in texts)
        assert any("+1/+1" in t for t in texts)

    def test_the_keyword_on_the_buried_card_does_not_apply(self, builder):
        """Only the *abilities* come up, not the top card's characteristics."""
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=False)

        assert Keyword.TRAMPLE.value not in chars(game.state, host).keywords


class TestThePermanentIsUntouched:
    def test_counters_and_damage_stay(self, builder):
        """702.140c, and also simply what happens when nothing moves."""
        from automtg.engine.objects import PLUS_ONE
        from automtg.engine.primitives import add_counters

        game = position(builder)
        host = only_oid(game, HOST)
        add_counters(game.state, host, PLUS_ONE, 2)
        mutate(game, host, on_top=True)

        assert game.state.objects[host].counter(PLUS_ONE) == 2
        assert (chars(game.state, host).power, chars(game.state, host).toughness) == (6, 6)

    def test_it_is_the_same_object_throughout(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        entered = game.state.objects[host].entered_turn
        mutate(game, host, on_top=True)

        assert game.state.objects[host].entered_turn == entered, "no summoning sickness"


class TestThePileComesApart:
    def test_both_cards_go_to_the_graveyard(self, builder):
        """702.140f: the pile goes where the permanent goes."""
        game = position(builder)
        host = only_oid(game, HOST)
        newcomer = mutate(game, host, on_top=True)

        destroy(game.state, host)

        assert game.state.objects[host].zone is Zone.GRAVEYARD
        assert game.state.objects[newcomer].zone is Zone.GRAVEYARD
        assert set(game.state.players[0].graveyard) == {host, newcomer}

    def test_and_the_permanent_is_a_single_card_again(self, builder):
        game = position(builder)
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)

        destroy(game.state, host)

        obj = game.state.objects[host]
        assert obj.merged_card is None
        assert obj.merged_under == ()
        assert game.state.card_of(obj).id == HOST


class TestMutatingTwice:
    def test_the_abilities_accumulate(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 12)
            .battlefield(0, [HOST])
            .hand(0, [MUTATOR, MUTATOR])
            .library(0, [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        mutate(game, host, on_top=True)

        abilities = game.state.card_of(game.state.objects[host]).abilities
        assert len(abilities) == 3, "two Mutators' and the Host's"

    def test_the_whole_pile_comes_apart_together(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 12)
            .battlefield(0, [HOST])
            .hand(0, [MUTATOR, MUTATOR])
            .library(0, [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        host = only_oid(game, HOST)
        mutate(game, host, on_top=True)
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.player == 0, limit=200
        )
        mutate(game, host, on_top=True)

        destroy(game.state, host)

        assert len(game.state.players[0].graveyard) == 3


class TestTheLoaderGuards:
    def _card(self, **extra) -> CardModel:
        base = {
            "id": "t_mutate_probe",
            "name": "Mutate Probe",
            "mana_cost": "{3}{G}",
            "types": ["Creature"],
            "power": 4,
            "toughness": 4,
            "mutate": "{1}{G}",
        }
        base.update(extra)
        return CardModel.model_validate(base)

    def test_a_creature_with_mutate_loads(self):
        compile_card(self._card())

    def test_a_noncreature_with_mutate_is_refused(self):
        """The merged permanent is the card on top, and this one is not one."""
        with pytest.raises(DslError, match="only on creature cards"):
            compile_card(self._card(types=["Sorcery"], power=None, toughness=None))

    def test_bestow_and_mutate_together_are_refused(self):
        with pytest.raises(DslError, match="both 'bestow' and 'mutate'"):
            compile_card(self._card(bestow="{5}{W}"))
