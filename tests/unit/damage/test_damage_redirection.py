"""`redirect_damage` -- damage dealt to another object instead.

    Heroic Sacrifice -- "Choose target creature you control. Until end of turn,
    all damage that would be dealt to you and creatures you control is dealt to
    the chosen creature instead (if it's still on the battlefield)."

614.9: a replacement effect can change who is dealt the damage, and the
redirected damage keeps its source (120.3), so lifelink and deathtouch still
apply. Nothing else in the engine can say this: every prevention, multiplier
and addend answers how much damage lands, never where.

616.1 lets the affected player order the replacements; the primitives cannot
ask, so the redirect is read first and the chosen creature's own replacements
apply, not the original recipient's. A redirect applies to an event once
(614.5), and ends when the chosen creature leaves the battlefield -- its oid
survives the move, and the creature that comes back is a new object (400.7).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import become_monarch, damage_permanent, damage_player
from commanderblitz.engine.temp_effects import clear_damage_redirects, shield_player
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

WALL = "t_f_3_3"  # the chosen creature, 3/3
BEAR = "t_rd_bear"  # another creature you control, 2/2
LIFELINK = "t_f_lifelink"  # 3/3 lifelink
DEATHTOUCH = "t_f_deathtouch"  # 1/1 deathtouch
YOURS = {"types": ["Creature"], "controller": "you"}


def board(builder, *, active: int = 0):
    return (
        builder(players=2)
        .battlefield(0, [WALL, BEAR])
        .battlefield(1, [LIFELINK, DEATHTOUCH, BEAR])
        .library(0, ["forest"] * 5)
        .library(1, ["forest"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )


def oid(game, pid: int, def_id: str) -> int:
    return next(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == def_id)


def sacrifice(game, pid: int = 0) -> int:
    """Seat ``pid`` resolves Heroic Sacrifice's first sentence on its Wall."""
    wall = oid(game, pid, WALL)
    ctx = EffectContext(state=game.state, controller=pid, source_oid=None)
    spec = {
        "op": "redirect_damage", "duration": "this_turn", "to": {"oids": [wall]},
        "player": "you", "permanents": YOURS,
    }
    for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
        raise AssertionError("redirect_damage asked a decision")
    return wall


class TestDamageLandsOnTheChosenCreature:
    def test_damage_to_you(self, builder):
        game = board(builder)
        wall = sacrifice(game)
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, oid(game, 1, BEAR))

        assert game.state.players[0].life == life
        assert game.state.objects[wall].damage == 2

    def test_damage_to_another_creature_you_control(self, builder):
        game = board(builder)
        wall = sacrifice(game)
        bear = oid(game, 0, BEAR)

        damage_permanent(game.state, bear, 2, oid(game, 1, BEAR))

        assert game.state.objects[bear].damage == 0
        assert game.state.objects[wall].damage == 2

    def test_combat_damage_to_you(self, builder):
        """The opponent swings an unblocked 3/3 lifelinker: the chosen 3/3 is
        dealt it and dies, its controller keeps their life, and the attacker
        still gains. (Read as the death, because the swing runs on past
        cleanup, which would have wiped a mark.)"""
        game = board(builder, active=1)
        wall = sacrifice(game)
        life, their_life = game.state.players[0].life, game.state.players[1].life

        swing(game, oid(game, 1, LIFELINK))

        assert game.state.players[0].life == life
        assert game.state.objects[wall].zone is Zone.GRAVEYARD
        assert game.state.players[1].life == their_life + 3

    def test_redirected_combat_damage_is_not_dealt_to_the_monarch(self, builder):
        """The crown moves on combat damage dealt *to the monarch* (721.3); a
        blow the Wall took instead was never dealt to them."""
        game = board(builder, active=1)
        sacrifice(game)
        become_monarch(game.state, 0)

        swing(game, oid(game, 1, LIFELINK))

        assert game.state.monarch == 0

    def test_damage_to_an_opponents_creature_is_not_redirected(self, builder):
        game = board(builder)
        wall = sacrifice(game)
        theirs = oid(game, 1, BEAR)

        damage_permanent(game.state, theirs, 1, oid(game, 0, BEAR))

        assert game.state.objects[theirs].damage == 1
        assert game.state.objects[wall].damage == 0


class TestDamageToTheChosenCreatureIsDealtOnce:
    def test_it_is_not_redirected_to_itself(self, builder):
        game = board(builder)
        wall = sacrifice(game)

        assert damage_permanent(game.state, wall, 2, oid(game, 1, BEAR)) == 2
        assert game.state.objects[wall].damage == 2

    def test_two_redirects_each_apply_once_and_stop(self, builder):
        """614.5: each replacement applies to the event once. A second
        Sacrifice onto the Bear sends the Wall's damage there, the first sends
        it back to the Wall, and then neither can apply again -- so the damage
        is dealt once, and the walk ends."""
        game = board(builder)
        wall = sacrifice(game)
        bear = oid(game, 0, BEAR)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        for _ in execute_one(ctx, {"op": "redirect_damage", "duration": "this_turn",
                                   "to": {"oids": [bear]}, "permanents": YOURS}):
            raise AssertionError("redirect_damage asked a decision")

        damage_permanent(game.state, wall, 1, oid(game, 1, BEAR))

        assert game.state.objects[wall].damage == 1
        assert game.state.objects[bear].damage == 0


class TestTheSourceIsUnchanged:
    def test_lifelink_still_applies(self, builder):
        game = board(builder)
        sacrifice(game)
        life = game.state.players[1].life

        damage_player(game.state, 0, 3, oid(game, 1, LIFELINK))

        assert game.state.players[1].life == life + 3

    def test_deathtouch_still_applies(self, builder):
        game = board(builder)
        wall = sacrifice(game)

        damage_player(game.state, 0, 1, oid(game, 1, DEATHTOUCH))
        sba.run(game.state)

        assert game.state.objects[wall].zone is Zone.GRAVEYARD


class TestTheOrderAgainstPrevention:
    def test_your_own_shield_does_not_reach_the_redirected_damage(self, builder):
        """Redirect first (616.1, the engine's choice): the damage is no longer
        being dealt to you, so a prevention over you does not apply to it."""
        game = board(builder)
        wall = sacrifice(game)
        shield_player(game.state, 0, "this_turn")

        damage_player(game.state, 0, 2, oid(game, 1, BEAR))

        assert game.state.objects[wall].damage == 2


class TestItEnds:
    def test_once_the_chosen_creature_leaves_damage_goes_where_it_was_aimed(self, builder):
        game = board(builder)
        wall = sacrifice(game)
        move_object(game.state, wall, Zone.GRAVEYARD)
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, oid(game, 1, BEAR))

        assert game.state.players[0].life == life - 2

    def test_the_creature_that_comes_back_is_not_the_chosen_one(self, builder):
        """400.7: the same oid, a new object. Without ending the redirect as it
        left, the returned Wall would soak damage the spell never chose for it."""
        game = board(builder)
        wall = sacrifice(game)
        move_object(game.state, wall, Zone.GRAVEYARD)
        move_object(game.state, wall, Zone.BATTLEFIELD, to_player=0)
        bear = oid(game, 0, BEAR)

        damage_permanent(game.state, bear, 1, oid(game, 1, BEAR))

        assert game.state.objects[bear].damage == 1
        assert game.state.objects[wall].damage == 0

    def test_cleanup_ends_it(self, builder):
        game = board(builder)
        sacrifice(game)
        clear_damage_redirects(game.state, "this_turn")
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, oid(game, 1, BEAR))

        assert game.state.players[0].life == life - 2

    def test_the_turn_ending_clears_it(self, builder):
        game = board(builder)
        sacrifice(game)
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn)

        assert game.state.damage_redirects == []


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {"id": "t_redirect_probe", "name": "Redirect Probe", "mana_cost": "{W}",
             "types": ["Instant"],
             "targets": [{"id": "t1", "kind": "permanent",
                          "selector": {"types": ["Creature"], "controller": "you"}}],
             "spell_effects": [effect]}
        )

    def _effect(self, **overrides) -> dict:
        effect = {"op": "redirect_damage", "duration": "this_turn", "to": {"target": "t1"},
                  "player": "you", "permanents": YOURS}
        effect.update(overrides)
        return {k: v for k, v in effect.items() if v is not None}

    def test_it_loads(self):
        compile_card(self._card(self._effect()))

    def test_a_duration_is_required(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card(self._effect(duration=None)))

    def test_to_is_required(self):
        with pytest.raises(DslError, match="'to'"):
            compile_card(self._card(self._effect(to=None)))

    def test_it_must_redirect_something(self):
        with pytest.raises(DslError, match="'player', 'permanents' or both"):
            compile_card(self._card(self._effect(player=None, permanents=None)))

    def test_permanents_cannot_name_a_target(self):
        with pytest.raises(DslError, match="mean nothing there"):
            compile_card(self._card(self._effect(permanents={"target": "t1"})))


def swing(game, attacker: int) -> None:
    """Seat 1 attacks seat 0 with ``attacker``, unblocked, and the damage lands."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    game.apply(next(
        a for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == attacker
        and any(ref.kind == "player" and ref.id == 0 for ref in a.targets)
    ))
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)
