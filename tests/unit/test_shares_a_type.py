"""Counting the *other* attackers that share a type with this one.

    Shared Animosity — "Whenever a creature you control attacks, it gets +1/+0
    until end of turn for each other attacking creature that shares a creature
    type with it."

Everything about that sentence was already sayable except the amount, and the
amount needed two selector predicates that did not exist. Both are about the
same thing: a filter that describes objects *relative to another object* rather
than against a list written when the card was authored.

- **`shares_a_type_with`.** `subtypes` takes a literal list, so it can only name
  a type known at authoring time. The referent here is whatever attacked, and it
  is different every trigger. Written with `{"count": {"attacking": true}}`
  instead, the card counts every attacker regardless of type — a materially
  different card that would load and resolve without complaint.
- **`exclude_binding`.** `exclude_self` compares against the *ability source*,
  which for Shared Animosity is the enchantment: not a creature, never
  attacking, so it removes nothing from a set of attackers and every pump is
  over by exactly one.

Both read **derived** characteristics on both sides, so a changeling or a
granted type counts — which is most of what anybody plays Shared Animosity with.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.primitives import add_subtypes
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, pass_until


def board(builder, ids: list[str]):
    """Everything on player 0's battlefield, in the order given."""
    game = builder(players=2).battlefield(0, ids).build()
    return game, list(game.state.battlefield)


def pool(game, selector, *, subject=None, source=None):
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        bindings={"subject": subject} if subject is not None else {},
    )
    return resolve_pool(ctx, selector)


class TestSharesAType:
    def test_it_matches_a_creature_of_the_same_subtype(self, builder):
        game, oids = board(builder, ["t_bear", "t_bear"])
        first, second = oids
        assert pool(game, {"shares_a_type_with": "subject"}, subject=first) == [
            first,
            second,
        ]

    def test_it_refuses_a_creature_of_another_subtype(self, builder):
        """A Bird beside a Bear is the whole point: the count is not "attackers"."""
        game, oids = board(builder, ["t_bear", "t_flyer"])
        bear, _bird = oids
        assert pool(game, {"shares_a_type_with": "subject"}, subject=bear) == [bear]

    def test_one_shared_type_is_enough(self, builder):
        """"shares **a** creature type" -- Elf Druid and Elf is a match."""
        game, oids = board(builder, ["t_dork", "t_bear"])
        dork, bear = oids
        add_subtypes(game.state, bear, ["Elf"])
        assert set(pool(game, {"shares_a_type_with": "subject"}, subject=dork)) == {
            dork,
            bear,
        }

    def test_a_creature_matches_once_even_sharing_two_types(self, builder):
        """A Goblin Rogue among Goblins and Rogues is one attacker, not two."""
        game, oids = board(builder, ["t_dork", "t_bear"])
        dork, bear = oids
        add_subtypes(game.state, bear, ["Elf", "Druid"])
        assert pool(game, {"shares_a_type_with": "subject"}, subject=dork).count(bear) == 1

    def test_it_reads_derived_types_not_printed_ones(self, builder):
        """A type granted after the card was printed still counts -- changelings
        are most of what anybody plays this alongside."""
        game, oids = board(builder, ["t_bear", "t_flyer"])
        bear, bird = oids
        assert bird not in pool(game, {"shares_a_type_with": "subject"}, subject=bear)

        add_subtypes(game.state, bird, ["Bear"])
        assert bird in pool(game, {"shares_a_type_with": "subject"}, subject=bear)

    def test_an_unbound_name_matches_nothing(self, builder):
        """Not *everything*. A missing binding is a card whose trigger did not
        bind what it thought it did, and matching the whole board would turn a
        silent bug into a blowout."""
        game, _oids = board(builder, ["t_bear", "t_bear"])
        assert pool(game, {"shares_a_type_with": "subject"}) == []


class TestExcludeBinding:
    def test_it_removes_the_bound_object(self, builder):
        game, oids = board(builder, ["t_bear", "t_bear"])
        first, second = oids
        assert pool(
            game, {"types": ["Creature"], "exclude_binding": "subject"}, subject=first
        ) == [second]

    def test_exclude_self_is_not_a_substitute(self, builder):
        """The reason this key exists. `exclude_self` compares against the
        ability's source -- the enchantment -- so it removes nothing from a set
        of creatures and the count is over by exactly one."""
        game, oids = board(builder, ["t_bear", "t_bear", "t_anthem"])
        first, second, enchantment = oids

        both = pool(
            game,
            {"types": ["Creature"], "exclude_self": True},
            subject=first,
            source=enchantment,
        )
        assert both == [first, second], "exclude_self did not exclude the attacker"

        assert pool(
            game,
            {"types": ["Creature"], "exclude_binding": "subject"},
            subject=first,
            source=enchantment,
        ) == [second]

    def test_the_two_predicates_compose(self, builder):
        """Which is the printed sentence: "each **other** attacking creature
        that **shares a creature type** with it"."""
        game, oids = board(builder, ["t_bear", "t_bear", "t_flyer"])
        first, second, _bird = oids
        assert pool(
            game,
            {"shares_a_type_with": "subject", "exclude_binding": "subject"},
            subject=first,
        ) == [second]


class TestTheWholeCard:
    """`t_animosity` is Shared Animosity's printed text, loaded and attacked with.

    The unit tests above call `resolve_pool` directly with a binding handed to
    it. This is the part that cannot be faked: the binding has to arrive from a
    real `attacks` trigger, and the count has to be read while the attack is
    still declared.
    """

    def attack_with_all(self, builder, ids: list[str]):
        game = builder(players=2).battlefield(0, ["t_animosity", *ids]).build()
        creatures = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id != "t_animosity"
        ]
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        for oid in creatures:
            game.apply(
                find_action(
                    game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
                )
            )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        # The triggers go on the stack when the attack is declared; measure once
        # they have resolved but while the attack is still on, since the pumps
        # last only until end of turn.
        pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)
        return game, creatures

    def test_three_of_a_type_each_get_plus_two(self, builder):
        """Three Bears attacking: each sees the *other* two."""
        game, creatures = self.attack_with_all(builder, ["t_bear"] * 3)
        for oid in creatures:
            assert chars(game.state, oid).power == 2 + 2

    def test_a_lone_type_gets_nothing(self, builder):
        """The Bird shares with nobody, and the Bears do not count it."""
        game, creatures = self.attack_with_all(builder, ["t_bear", "t_bear", "t_flyer"])
        bears = [oid for oid in creatures if game.state.objects[oid].def_id == "t_bear"]
        bird = next(oid for oid in creatures if game.state.objects[oid].def_id == "t_flyer")

        for oid in bears:
            assert chars(game.state, oid).power == 2 + 1
        assert chars(game.state, bird).power == 2, "a lone type shares with nothing"
