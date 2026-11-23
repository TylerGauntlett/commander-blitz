""""As this creature enters, choose a player" -- a player choice a static reads.

    Sawhorn Nemesis -- "As this creature enters, choose a player. If a source
    would deal damage to the chosen player or a permanent they control, it
    deals double that damage instead."
    Triarch Stalker -- "At the beginning of combat on your turn, choose an
    opponent. Creatures attacking the last chosen player have menace."

`choose_player` already asked the question, but it wrote the answer only into
the resolving ability's bindings, which a static never sees. The words a static
could name a seat with -- `you`, `opponent`, `any` -- are relative to its
controller, so written with them both cards are different cards at a pod:
"opponent" doubles damage to *every* opponent and can never pick yourself, and
gives menace to creatures attacking anybody but you.

``remember: true`` keeps the chosen seat on the source permanent
(`GameObject.chosen_player`), the player twin of `choose_color`'s slot, and a
static reads it back through ``{"chosen_player_of": "self"}`` in `affects`'
``controller`` and ``attacking_player`` and in `replace_damage`'s
``affects_player``. 607.2 is the rule that links them: the static refers to the
choice its own object made. Each later choice overwrites the slot, which is what
"the last chosen player" means.

Pinned below, each a different card if it goes the other way:

1. Before anything is chosen, nobody is named -- never everybody.
2. The choice names exactly one seat: other opponents are untouched, and
   Sawhorn may name its own controller.
3. A later choice replaces the earlier one.
4. The choice lives on the object: a permanent that leaves forgets it.
5. The loader admits exactly the one spelling, and only where a reader knows it.

The "as this enters" divergence is `choose_type`'s, recorded in
`docs/rules-coverage.md`: the choice is a `self_enters` trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent, damage_player
from tests.conftest import (
    _default_answer,
    keywords,
    oids_of,
    only_oid,
    pass_until,
    settle,
    static_probe,
)

NEMESIS = "t_nemesis"  # Sawhorn Nemesis's two lines
RELAY = "t_relay"  # Triarch Stalker's two lines, on an artifact
BEAR = "t_bear"
OGRE = "t_rd_ogre"  # 3/9: survives a doubled hit, so the mark can be read

CHOSEN = {"chosen_player_of": "self"}


def remember(game, oid: int, pid: int | None) -> None:
    game.state.objects[oid].chosen_player = pid
    game.state.bump_chars()


def run(game, source: int, spec: dict):
    """Run one ``choose_player`` from ``source``; return the generator."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    return ctx, execute(ctx, [{"op": "choose_player", **spec}])


def nemesis_board(builder):
    """Three seats, a Nemesis and an Ogre for player 0, an Ogre each for 1 and 2."""
    game = (
        builder(players=3)
        .battlefield(0, [NEMESIS, OGRE])
        .battlefield(1, [OGRE])
        .battlefield(2, [OGRE])
        .build(advance=False)
    )
    return game, only_oid(game, NEMESIS)


class TestTheChoiceIsRemembered:
    def test_it_is_written_on_the_source(self, builder):
        game, nemesis = nemesis_board(builder)
        ctx, gen = run(game, nemesis, {"players": "each_player", "remember": True})
        decision = next(gen)
        assert decision.kind is DecisionKind.CHOOSE_PLAYER
        assert [o.value for o in decision.options] == [0, 1, 2]
        with pytest.raises(StopIteration):
            gen.send([2])
        assert game.state.objects[nemesis].chosen_player == 2
        assert ctx.bindings == {}

    def test_as_still_binds_beside_it(self, builder):
        game, nemesis = nemesis_board(builder)
        ctx, gen = run(game, nemesis, {"remember": True, "as": "foe", "random": True})
        with pytest.raises(StopIteration):
            next(gen)
        assert ctx.bindings["foe"] == game.state.objects[nemesis].chosen_player
        assert ctx.bindings["foe"] in (1, 2)

    def test_without_remember_nothing_is_kept(self, builder):
        game, nemesis = nemesis_board(builder)
        _, gen = run(game, nemesis, {"as": "foe", "random": True})
        with pytest.raises(StopIteration):
            next(gen)
        assert game.state.objects[nemesis].chosen_player is None

    def test_a_later_choice_overwrites_it(self, builder):
        """"The **last** chosen player"."""
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        _, gen = run(game, nemesis, {"remember": True})
        next(gen)
        with pytest.raises(StopIteration):
            gen.send([1])  # the second opponent offered: seat 2
        assert game.state.objects[nemesis].chosen_player == 2

    def test_nobody_to_choose_leaves_the_last_choice(self, builder):
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        _, gen = run(game, nemesis, {"remember": True, "players": {"binding": "nobody"}})
        with pytest.raises(StopIteration):
            next(gen)
        assert game.state.objects[nemesis].chosen_player == 1

    def test_leaving_the_battlefield_forgets_it(self, builder):
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        game.state.objects[nemesis].reset_permanent_state()
        assert game.state.objects[nemesis].chosen_player is None


class TestTheEntersChoice:
    def test_casting_it_asks_among_every_player(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, ["swamp"] * 3)
            .hand(0, [NEMESIS])
            .library(0, ["swamp"] * 10)
            .active(0)
            .max_turns(1)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == NEMESIS
            )
        )
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_PLAYER,
        )
        decision = game.pending()
        assert decision.player == 0
        assert sorted(o.value for o in decision.options) == [0, 1, 2]
        index = [o.value for o in decision.options].index(0)
        game.apply(
            next(
                a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )
        assert game.state.objects[only_oid(game, NEMESIS)].chosen_player == 0


class TestTheDamageDoubling:
    def test_nobody_is_doubled_before_a_choice(self, builder):
        game, _ = nemesis_board(builder)
        for pid in (0, 1, 2):
            before = game.state.players[pid].life
            damage_player(game.state, pid, 3, None)
            assert before - game.state.players[pid].life == 3

    def test_the_chosen_player_takes_double(self, builder):
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        before = game.state.players[1].life
        damage_player(game.state, 1, 3, only_oid(game, OGRE, 2))
        assert before - game.state.players[1].life == 6

    def test_another_opponent_does_not(self, builder):
        """The whole difference from `affects_player: "opponent"`."""
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        before = game.state.players[2].life
        damage_player(game.state, 2, 3, only_oid(game, OGRE, 1))
        assert before - game.state.players[2].life == 3

    def test_a_permanent_the_chosen_player_controls_takes_double(self, builder):
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        assert damage_permanent(game.state, only_oid(game, OGRE, 1), 2, None) == 4

    def test_other_permanents_do_not(self, builder):
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 1)
        assert damage_permanent(game.state, only_oid(game, OGRE, 2), 2, None) == 2
        assert damage_permanent(game.state, only_oid(game, OGRE, 0), 2, None) == 2

    def test_it_may_name_its_own_controller(self, builder):
        """"Choose a player", not "an opponent": the controller is a legal answer."""
        game, nemesis = nemesis_board(builder)
        remember(game, nemesis, 0)
        before = game.state.players[0].life
        damage_player(game.state, 0, 2, None)
        assert before - game.state.players[0].life == 4
        assert damage_permanent(game.state, only_oid(game, OGRE, 0), 2, None) == 4
        assert damage_permanent(game.state, only_oid(game, OGRE, 1), 2, None) == 2


def relay_board(builder):
    """Player 0 controls the Relay and two Bears; players 1 and 2 defend."""
    b = builder(players=3).battlefield(0, [RELAY, BEAR, BEAR])
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    game = b.active(0).step(Step.UNTAP).max_turns(2).build()
    return game, only_oid(game, RELAY), list(oids_of(game, BEAR, 0))


def to_declare_attackers(game, chosen: int | None = None, limit: int = 80) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return
        if decision.kind is DecisionKind.CHOOSE_PLAYER and chosen is not None:
            index = [o.value for o in decision.options].index(chosen)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def declare(game, plan: list[tuple[int, int]]) -> None:
    """Send each ``(bear, seat)`` and stop with the attack still live."""
    for oid, seat in plan:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any((t.kind, t.id) == ("player", seat) for t in a.targets)
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game)
    assert game.state.combat is not None


class TestTheMenaceGrant:
    def test_the_combat_trigger_chooses_and_remembers(self, builder):
        game, relay, _ = relay_board(builder)
        to_declare_attackers(game, chosen=2)
        assert game.state.objects[relay].chosen_player == 2

    def test_creatures_attacking_the_chosen_player_have_menace(self, builder):
        game, _, (a, b) = relay_board(builder)
        to_declare_attackers(game, chosen=2)
        declare(game, [(a, 2), (b, 1)])
        assert "menace" in keywords(game, a)
        assert "menace" not in keywords(game, b)

    def test_nobody_has_it_before_a_choice(self, builder):
        game, relay, (a, b) = relay_board(builder)
        to_declare_attackers(game, chosen=1)
        remember(game, relay, None)
        declare(game, [(a, 1), (b, 2)])
        assert "menace" not in keywords(game, a)
        assert "menace" not in keywords(game, b)

    def test_and_nobody_out_of_combat(self, builder):
        game, relay, (a, _) = relay_board(builder)
        remember(game, relay, 1)
        assert "menace" not in keywords(game, a)


class TestTheLoader:
    @staticmethod
    def static(static: dict):
        return compile_card(CardModel.model_validate(static_probe(static)))

    @staticmethod
    def effect(effect: dict):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "probe",
                    "name": "Probe",
                    "oracle_text": "Probe.",
                    "mana_cost": "{W}",
                    "types": ["Sorcery"],
                    "spell_effects": [effect],
                }
            )
        )

    def test_both_witness_shapes_load(self):
        self.static(
            {
                "effect": "replace_damage",
                "affects": {"controller": CHOSEN},
                "affects_player": CHOSEN,
                "damage_multiplier": 2,
            }
        )
        self.static(
            {
                "effect": "grant_keyword",
                "keywords": ["menace"],
                "affects": {"types": ["Creature"], "controller": "any", "attacking_player": CHOSEN},
            }
        )
        self.effect({"op": "choose_player", "remember": True})

    @pytest.mark.parametrize("key", ["controller", "attacking_player"])
    @pytest.mark.parametrize("bad", [{"binding": "foe"}, {"chosen_player_of": "target"}])
    def test_another_dict_in_a_static_filter_is_refused(self, key, bad):
        with pytest.raises(DslError, match=key):
            self.static(
                {"effect": "grant_keyword", "keywords": ["menace"], "affects": {key: bad}}
            )

    def test_affects_player_is_read_by_replace_damage_only(self):
        with pytest.raises(DslError, match="replace_damage static only"):
            self.static(
                {"effect": "replace_life_loss", "affects_player": CHOSEN, "loss_multiplier": 2}
            )

    def test_a_malformed_affects_player_is_refused(self):
        with pytest.raises(DslError, match="affects_player"):
            self.static(
                {
                    "effect": "replace_damage",
                    "affects_player": {"binding": "foe"},
                    "damage_multiplier": 2,
                }
            )

    def test_remember_is_true_only(self):
        with pytest.raises(DslError, match="remember"):
            self.effect({"op": "choose_player", "remember": False, "as": "foe"})

    def test_an_answer_nothing_can_reach_is_refused(self):
        with pytest.raises(DslError, match="needs an 'as'"):
            self.effect({"op": "choose_player"})
