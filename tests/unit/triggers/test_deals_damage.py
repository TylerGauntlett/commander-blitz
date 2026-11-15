""""Whenever this creature deals damage" -- any damage, once per damage event.

    "Whenever this creature deals damage, you gain that much life."
                                                  -- Exalted Angel

**The rules argument.** The trigger event is the source dealing damage, to
anything and by any means: combat or noncombat, to a player, a planeswalker, a
battle or a creature. The existing triggers each hear one part of that --
`deals_combat_damage` misses a fight, `deals_damage_to_player` misses a blocked
creature's damage and every fight, and `dealt_damage` is the victim's side.

How often it triggers is the reading this test pins. 510.2: all combat damage
in one combat damage step is dealt simultaneously, as one event; and one effect
dealing damage to several things deals it at once. 603.2c: an ability triggers
once each time its trigger event occurs. So a creature that deals damage to two
recipients at once -- a trampler hitting its blocker and the player, a creature
blocked by two blockers, one ability hitting each creature and each player --
"deals damage" **once**, and "that much" is the total it dealt. First strike and regular combat
damage are two steps (510.4), so a double striker triggers twice. The engine's
unit of "at once" outside combat is one effect op (`state.event_batch`), the
grouping `dealt_damage`'s `batched` already uses; two creatures fighting are two
sources and so two events. Damage dealt **to** the creature is not damage it
dealt, and prevented damage was never dealt.

Wrong without the grouping: a trampler would gain twice, its blocker's share
and the player's, each as a separate trigger -- a different card under every
"whenever you gain life" payoff.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, pass_until, settle

LIFER = "t_dd_lifer"  # 4/5, gains that much whenever it deals damage
TRAMPLER = "t_dd_trampler"  # 5/5 trample, the same trigger
STRIKER = "t_dd_striker"  # 2/2 double strike, the same trigger
WALL = "t_dcd_wall"  # 0/3
BEAR = "t_bear"  # 2/2
ANGEL = "exalted_angel"


def board(builder, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 3 + list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def swing(game, attacker: int, *, blockers=()) -> None:
    """Attack the opponent with ``attacker``, blocked by ``blockers``, and settle
    at this turn's postcombat main."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == attacker
            and any(r.kind == "player" for r in a.targets)
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    if blockers:
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.DECLARE_BLOCKERS,
        )
        for blocker in blockers:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker
                )
            )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def run(game, specs: list[dict], *, source: int | None) -> None:
    """Resolve ``specs`` for player 0 as ``source``'s effect, then settle."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    for _ in execute(ctx, specs):
        raise AssertionError("asks nothing")
    settle(game)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def gains(game, oid: int) -> list[int]:
    """The amount of each `deals_damage` firing of ``oid``'s, in order."""
    return [
        int(e.data.get("amount", 0))
        for e in game.state.events
        if e.type == "life_gained" and e.source == oid
    ]


class TestCombat:
    def test_an_unblocked_hit_gains_that_much(self, builder):
        game = board(builder, mine=[LIFER])
        lifer = only_oid(game, LIFER, 0)
        before = life(game)
        swing(game, lifer)
        assert life(game) == before + 4
        assert gains(game, lifer) == [4]

    def test_damage_to_a_blocker_counts(self, builder):
        """What `deals_damage_to_player` cannot hear."""
        game = board(builder, mine=[LIFER], theirs=[WALL])
        lifer, wall = only_oid(game, LIFER, 0), only_oid(game, WALL, 1)
        before, theirs = life(game), life(game, 1)
        swing(game, lifer, blockers=[wall])
        assert life(game, 1) == theirs, "the blocker took it all"
        assert gains(game, lifer) == [4]
        assert life(game) == before + 4

    def test_a_trampler_hitting_two_things_triggers_once_for_all_of_it(self, builder):
        """510.2: one event. Three to the Wall, two trampling over, one gain of five."""
        game = board(builder, mine=[TRAMPLER], theirs=[WALL])
        trampler, wall = only_oid(game, TRAMPLER, 0), only_oid(game, WALL, 1)
        before, theirs = life(game), life(game, 1)
        swing(game, trampler, blockers=[wall])
        assert life(game, 1) < theirs, "the excess trampled over"
        assert gains(game, trampler) == [5]
        assert life(game) == before + 5

    def test_two_blockers_are_one_event(self, builder):
        game = board(builder, mine=[LIFER], theirs=[BEAR, BEAR])
        lifer = only_oid(game, LIFER, 0)
        bears = oids_of(game, BEAR, 1)
        before = life(game)
        swing(game, lifer, blockers=bears)
        assert gains(game, lifer) == [4]
        assert life(game) == before + 4

    def test_double_strike_is_two_steps_and_two_triggers(self, builder):
        """510.4: first-strike damage and regular damage are separate events."""
        game = board(builder, mine=[STRIKER])
        striker = only_oid(game, STRIKER, 0)
        before = life(game)
        swing(game, striker)
        assert gains(game, striker) == [2, 2]
        assert life(game) == before + 4


class TestNoncombat:
    def test_one_effect_hitting_everything_is_one_event(self, builder):
        """One effect dealing 1 to each creature and each player: four
        recipients, one firing, that much is four."""
        game = board(builder, mine=[LIFER, BEAR], theirs=[BEAR])
        lifer = only_oid(game, LIFER, 0)
        before = life(game)
        run(
            game,
            [
                {
                    "op": "damage",
                    "amount": {"const": 1},
                    "source_object": {"zone": "battlefield", "self_only": True},
                    "objects": {"zone": "battlefield", "types": ["Creature"], "count": "all"},
                    "player": "each_player",
                }
            ],
            source=lifer,
        )
        # Five recipients: the Lifer, two Bears and both players.
        assert gains(game, lifer) == [5]
        assert life(game) == before - 1 + 5

    def test_a_fight_counts(self, builder):
        """Noncombat damage to a creature -- what neither existing trigger hears."""
        game = board(builder, mine=[LIFER], theirs=[BEAR])
        lifer = only_oid(game, LIFER, 0)
        before = life(game)
        run(
            game,
            [
                {
                    "op": "fight",
                    "objects": {"zone": "battlefield", "self_only": True},
                    "other": {"zone": "battlefield", "controller": "opponent",
                              "types": ["Creature"]},
                }
            ],
            source=lifer,
        )
        assert oids_of(game, BEAR, 1) == [], "the Bear died"
        assert gains(game, lifer) == [4]
        assert life(game) == before + 4

    def test_damage_dealt_to_it_is_not_damage_it_dealt(self, builder):
        game = board(builder, mine=[LIFER], theirs=[BEAR])
        lifer, bear = only_oid(game, LIFER, 0), only_oid(game, BEAR, 1)
        run(
            game,
            [
                {
                    "op": "damage",
                    "amount": {"const": 2},
                    "objects": {"zone": "battlefield", "types": ["Creature"],
                                "controller": "you"},
                }
            ],
            source=bear,
        )
        assert game.state.objects[lifer].damage == 2
        assert gains(game, lifer) == []


class TestExaltedAngel:
    def test_the_witness_gains_off_a_fight(self, builder):
        game = board(builder, mine=[ANGEL], theirs=[BEAR])
        angel = only_oid(game, ANGEL, 0)
        before = life(game)
        run(
            game,
            [
                {
                    "op": "fight",
                    "objects": {"zone": "battlefield", "self_only": True},
                    "other": {"zone": "battlefield", "controller": "opponent",
                              "types": ["Creature"]},
                }
            ],
            source=angel,
        )
        assert gains(game, angel) == [4]
        assert life(game) == before + 4


class TestTheLoader:
    @staticmethod
    def probe(trigger: dict, *, delayed: bool = False) -> CardModel:
        effects = [{"op": "gain_life", "amount": {"binding": "amount"}}]
        if delayed:
            return CardModel.model_validate(
                {
                    "id": "probe", "name": "Probe", "oracle_text": "Probe.",
                    "mana_cost": "{W}", "types": ["Sorcery"],
                    "spell_effects": [
                        {"op": "delayed_trigger", "duration": "this_turn",
                         "trigger": trigger, "effects": effects}
                    ],
                }
            )
        return CardModel.model_validate(
            {
                "id": "probe", "name": "Probe", "oracle_text": "Probe.",
                "mana_cost": "{W}", "types": ["Creature"], "power": 1, "toughness": 1,
                "abilities": [{"kind": "triggered", "text": "Probe.",
                               "trigger": trigger, "effects": effects}],
            }
        )

    def test_it_loads(self):
        compile_card(self.probe({"event": "deals_damage", "source": "self"}))

    def test_batched_is_refused_since_the_grouping_is_the_events(self):
        with pytest.raises(DslError, match="batched"):
            compile_card(self.probe({"event": "deals_damage", "source": "self", "batched": True}))

    def test_a_delayed_trigger_is_refused(self):
        with pytest.raises(DslError, match="deals_damage"):
            compile_card(self.probe({"event": "deals_damage"}, delayed=True))
