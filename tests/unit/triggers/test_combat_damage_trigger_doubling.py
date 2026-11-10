""""If a creature you control dealing combat damage to a player causes a
triggered ability of a permanent you control to trigger, that ability triggers
an additional time."                                   -- Felix Five-Boots

The cause is one fact about combat (510.2) and the trigger layer hears it as up
to four events, because an ability triggers off whatever its own trigger event
is (603.2): the per-connection `deals_combat_damage_to_player`, the batched
`creatures_deal_combat_damage`, the per-source `deals_combat_damage` and the
generic `deals_damage_to_player`. `cause_events` can only name event types, and
every list of them is wrong somewhere: listing the per-source event doubles a
blocked creature's "deals combat damage" trigger that never touched a player,
leaving it out undoubles a trampler's that did, and listing
`deals_damage_to_player` doubles a ping.

`cause_combat_damage_to_player` asks each event the same question in its own
terms -- the batch when it hit a seat, the per-source event when that creature
reached a player, the damage event when it was combat damage to a player --
and `cause_controller: "you"` reads the dealing creature's controller.

Without it the card is wrong at each of the boundaries pinned below: a
planeswalker hit, a blocker hit, a battle-only swing, a noncombat ping, an
opponent's trigger and an opponent's creature must each trigger exactly once.

The witness is Felix Five-Boots; `t_fx_felix` is its doubling line on a body
that stays home. Counts are read off what the abilities *did* -- cards drawn,
life gained -- because "an additional time" is a claim about how often the
ability happens.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until, settle, static_probe

FELIX = "t_fx_felix"  # the doubler, 0/4, stays home
PER_CONNECTION = "t_cdpw_player_only"  # 3/3: "deals combat damage to a player, draw"
BOTH_HALVES = "t_cdpw_saboteur"  # 3/3: the same, plus the planeswalker half
PER_SOURCE = "t_dcd_scout"  # 2/2: "deals combat damage, draw"
TRAMPLER = "t_dcd_trampler"  # 5/5 trample: "deals combat damage, draw"
WALL = "t_dcd_wall"  # 0/3
BATCH = "t_bcd_players_only"  # "creatures you control deal combat damage to a player, gain 1"
OR_BATTLE = "t_bcd_or_battle"  # the same "…to a player or battle"
BATTLE = "t_battle_wall"  # Siege, defense 3
ANY_DAMAGE = "t_fx_any_damage"  # "a source you control deals damage to a player, draw"
HIT_ME = "t_fx_hit_me"  # "creatures deal combat damage to you, gain 1"
BRAWLER = "t_fx_brawler"  # 2/4: "whenever this creature is dealt damage, draw"
PINGER = "t_pinger"  # "{T}: 1 damage to target player"
WALKER = "t_walker"
BEAR = "t_bear"


def board(builder, *, mine=(), theirs=(), active: int = 0):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3 + list(mine))
        .battlefield(1, ["swamp"] * 3 + list(theirs))
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )


def swing(game, attacker: int, *, at: TargetRef | None = None, blocker: int | None = None):
    """Attack with ``attacker`` (at the other seat unless ``at``), blocked by
    ``blocker`` if given, and settle at this turn's postcombat main or later."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == attacker
            and (a.targets == (at,) if at is not None else a.targets[0].kind == "player")
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    if blocker is not None:
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.DECLARE_BLOCKERS,
        )
        game.apply(find_action(game, ActionKind.ADD_BLOCKER, source=blocker))
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def draws_from(builder, attacker: str, *, felix: bool, theirs=(), others=(), **kw) -> int:
    mine = [attacker, *others, *([FELIX] if felix else [])]
    game = board(builder, mine=mine, theirs=theirs)
    before = len(game.state.players[0].library)
    oid = only_oid(game, attacker, 0)
    target = kw.pop("at", None)
    blocker = kw.pop("blocker", None)
    swing(
        game,
        oid,
        at=None if target is None else TargetRef.obj(only_oid(game, target, 1)),
        blocker=None if blocker is None else only_oid(game, blocker, 1),
    )
    return before - len(game.state.players[0].library)


def life_from(builder, listener: str, *, felix: bool, theirs=(), at: str | None = None) -> int:
    game = board(builder, mine=[listener, BEAR, *([FELIX] if felix else [])], theirs=theirs)
    life = game.state.players[0].life
    swing(
        game,
        only_oid(game, BEAR, 0),
        at=None if at is None else TargetRef.obj(only_oid(game, at, 1)),
    )
    return game.state.players[0].life - life


class TestEveryShapeOfTheConnectionDoubles:
    def test_a_per_connection_trigger(self, builder):
        assert draws_from(builder, PER_CONNECTION, felix=False) == 1
        assert draws_from(builder, PER_CONNECTION, felix=True) == 2

    def test_a_per_source_trigger_on_an_unblocked_hit(self, builder):
        assert draws_from(builder, PER_SOURCE, felix=False) == 1
        assert draws_from(builder, PER_SOURCE, felix=True) == 2

    def test_a_trampler_that_hit_its_blocker_and_the_player(self, builder):
        """One "deals combat damage" firing, and the player was part of it."""
        assert draws_from(builder, TRAMPLER, felix=True, theirs=[WALL], blocker=WALL) == 2

    def test_a_batch_trigger(self, builder):
        assert life_from(builder, BATCH, felix=False) == 1
        assert life_from(builder, BATCH, felix=True) == 2

    def test_a_generic_damage_trigger_on_combat_damage(self, builder):
        assert draws_from(builder, BEAR, felix=False, others=[ANY_DAMAGE]) == 1
        assert draws_from(builder, BEAR, felix=True, others=[ANY_DAMAGE]) == 2

    def test_two_doublers_add_one_each(self, builder):
        game = board(builder, mine=[PER_CONNECTION, FELIX, FELIX])
        before = len(game.state.players[0].library)
        swing(game, only_oid(game, PER_CONNECTION, 0))
        assert before - len(game.state.players[0].library) == 3


class TestDamageThatIsNotToAPlayerDoesNot:
    def test_a_planeswalker_hit(self, builder):
        """306.8: the walker is dealt the damage; its controller is not."""
        assert draws_from(builder, BOTH_HALVES, felix=True, theirs=[WALKER], at=WALKER) == 1

    def test_a_blocked_creature_that_hit_only_its_blocker(self, builder):
        assert draws_from(builder, PER_SOURCE, felix=True, theirs=[WALL], blocker=WALL) == 1

    def test_a_creature_being_dealt_combat_damage(self, builder):
        assert draws_from(builder, BRAWLER, felix=True, theirs=[BEAR], blocker=BEAR) == 1

    def test_a_battle_only_swing(self, builder):
        """310.6: a battle is a permanent, not a player."""
        assert life_from(builder, OR_BATTLE, felix=True, theirs=[BATTLE], at=BATTLE) == 1


class TestNoncombatDamageDoesNot:
    def test_a_creature_pinging_a_player(self, builder):
        game = board(builder, mine=[PINGER, ANY_DAMAGE, FELIX])
        before = len(game.state.players[0].library)
        game.apply(
            find_action(
                game,
                ActionKind.ACTIVATE,
                source=only_oid(game, PINGER, 0),
                targets=(TargetRef.player(1),),
            )
        )
        settle(game)
        assert before - len(game.state.players[0].library) == 1


class TestYouControl:
    def test_an_opponents_trigger_is_not_doubled(self, builder):
        """"…of a permanent **you** control": my Bear, their ability."""
        game = board(builder, mine=[BEAR, FELIX], theirs=[HIT_ME])
        life = game.state.players[1].life
        swing(game, only_oid(game, BEAR, 0))
        assert game.state.players[1].life == life - 2 + 1

    def test_an_opponents_creature_is_not_the_cause(self, builder):
        """"…a creature **you** control dealing combat damage": their Bear, my
        ability."""
        game = board(builder, mine=[HIT_ME, FELIX], theirs=[BEAR], active=1)
        life = game.state.players[0].life
        swing(game, only_oid(game, BEAR, 1))
        assert game.state.players[0].life == life - 2 + 1


class TestTheLoaderRefuses:
    def _doubler(self, **clause) -> CardModel:
        return CardModel.model_validate(
            static_probe(
                {
                    "effect": "double_triggers",
                    "affects": {"controller": "you"},
                    "cause_combat_damage_to_player": True,
                    **clause,
                }
            )
        )

    def test_it_alone_loads(self):
        compile_card(self._doubler(cause_controller="you"))

    def test_it_beside_cause_events(self):
        with pytest.raises(DslError, match="does not combine"):
            compile_card(self._doubler(cause_events=["deals_combat_damage_to_player"]))

    def test_it_beside_cause_filter(self):
        with pytest.raises(DslError, match="does not combine"):
            compile_card(self._doubler(cause_filter={"types": ["Creature"]}))

    def test_it_on_another_static(self):
        probe = static_probe(
            {"effect": "cant_block", "affects": {"types": ["Creature"]}, "cause_combat_damage_to_player": True}
        )
        with pytest.raises(DslError, match="cause clause"):
            compile_card(CardModel.model_validate(probe))
