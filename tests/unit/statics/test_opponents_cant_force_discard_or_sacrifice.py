"""A player opponents can't make discard or sacrifice.

    Tamiyo, Collector of Tales — "Spells and abilities your opponents control
    can't cause you to discard cards or sacrifice permanents."

The static reads the one fact the engine already carried for Orvar: *who
caused* the discard or sacrifice. It is not `cant_sacrifice`, which protects a
permanent from every sacrifice whoever asks -- written with it, Tamiyo's
controller could not sacrifice to their own Altar, and discard would not be
covered at all. The line is about the **cause's controller**:

- **An opponent's edict or Mind Rot does nothing to me.** My permanents are not
  in the edict's pool and my hand is not asked; the rest of the spell resolves
  (the other opponents still sacrifice).
- **My own spells and costs are untouched.** My discard spell, my own "each
  player sacrifices" and a sacrifice paid as my cost all still work.
- **I can't pay an opponent's "unless" with a discard or a sacrifice.** Torment
  of Hailfire's "unless that player sacrifices a nonland permanent or discards a
  card": the opponent's ability would be causing me to sacrifice, so the cost is
  not offered and the punishment lands (the printed ruling).

The `opponents_cant_force_discard_or_sacrifice` static, read through
`player_statics.forced_discard_or_sacrifice_barred` by `op_discard`, connive,
`op_sacrifice` and `may`'s `pay`.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.player_statics import forced_discard_or_sacrifice_barred
from automtg.engine.zones import move_object

TAMIYO = "t_tamiyo_shield"
BEAR = "t_bear"

DISCARD = {"op": "discard", "player": "each_player", "amount": 1}
EDICT = {"op": "sacrifice", "objects": {"controller": "any", "types": ["Creature"], "count": "all"}}
UNLESS = {
    "op": "may",
    "player": "each_opponent",
    "pay": {"sacrifice": {"types": ["Creature"]}},
    "effects": [],
    "else": [{"op": "lose_life", "player": "each_opponent", "amount": {"const": 3}}],
}


def position(builder, mine=(TAMIYO,)):
    """Player 0 holds Tamiyo; both players have two bears and two cards in hand."""
    return (
        builder(players=2)
        .battlefield(0, [*mine, BEAR, BEAR])
        .battlefield(1, [BEAR, BEAR])
        .hand(0, [BEAR, BEAR])
        .hand(1, [BEAR, BEAR])
        .life(0, 20)
        .life(1, 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def run(game, effects, controller: int, *, yes: bool = True) -> list:
    """Resolve ``effects``; take the first option, and answer every may ``yes``."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            if decision.kind is DecisionKind.MAY:
                answer = [0] if yes else [1]
            else:
                answer = list(range(decision.min_count or 1))
            decision = gen.send(answer)
    except StopIteration:
        pass
    return asked


def bears(game, pid: int) -> int:
    return sum(
        1 for o in game.state.battlefield_objects(pid) if o.def_id == BEAR
    )


class TestAnOpponentCannotMakeMe:
    def test_their_discard_spell_skips_me(self, builder):
        game = position(builder)
        run(game, [DISCARD], controller=1)
        assert len(game.state.players[0].hand) == 2
        assert len(game.state.players[1].hand) == 1, "the rest still resolves"

    def test_their_edict_skips_my_creatures(self, builder):
        game = position(builder)
        run(game, [EDICT], controller=1)
        assert bears(game, 0) == 2
        assert bears(game, 1) == 0

    def test_their_unless_cannot_be_paid_with_a_sacrifice(self, builder):
        game = position(builder)
        asked = run(game, [UNLESS], controller=1)
        assert asked == [], "the sacrifice is not offered"
        assert bears(game, 0) == 2
        assert game.state.players[0].life == 17


class TestMyOwnAreUntouched:
    def test_my_discard_spell_still_makes_me_discard(self, builder):
        game = position(builder)
        run(game, [DISCARD], controller=0)
        assert len(game.state.players[0].hand) == 1

    def test_my_edict_still_takes_my_creatures(self, builder):
        game = position(builder)
        run(game, [EDICT], controller=0)
        assert bears(game, 0) == 0

    def test_the_opponent_is_not_shielded(self, builder):
        """"…can't cause **you**" -- Tamiyo's opponents are not protected."""
        game = position(builder)
        assert not forced_discard_or_sacrifice_barred(game.state, 1, 0)

    def test_an_unless_the_opponent_is_asked_can_still_be_paid(self, builder):
        game = position(builder)
        spec = {**UNLESS, "player": "each_opponent"}
        run(game, [spec], controller=0)
        assert bears(game, 1) == 1
        assert game.state.players[1].life == 20

    def test_nothing_without_the_static(self, builder):
        game = position(builder, mine=())
        run(game, [DISCARD, EDICT], controller=1)
        assert len(game.state.players[0].hand) == 1
        assert bears(game, 0) == 0


class TestItFollowsItsSource:
    def test_it_lifts_when_tamiyo_leaves(self, builder):
        game = position(builder)
        tamiyo = next(o for o in game.state.battlefield if game.state.objects[o].def_id == TAMIYO)
        move_object(game.state, tamiyo, Zone.GRAVEYARD)
        assert not forced_discard_or_sacrifice_barred(game.state, 0, 1)
        run(game, [EDICT], controller=1)
        assert bears(game, 0) == 0

    def test_no_cause_is_never_barred(self, builder):
        """The cleanup discard and a cost are nobody's doing (``caused_by=None``)."""
        assert not forced_discard_or_sacrifice_barred(position(builder).state, 0, None)


class TestTheLoaderRefusesWhatIsNotACard:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_affects_player_is_required(self):
        card = _card()
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    @pytest.mark.parametrize(
        "extra", [{"affects": {"types": ["Creature"]}}, {"amount": {"const": 1}}]
    )
    def test_a_filter_or_an_amount_is_refused(self, extra):
        card = _card()
        card["abilities"][0].update(extra)
        with pytest.raises(DslError, match="opponents_cant_force_discard_or_sacrifice takes"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    text = (
        "Spells and abilities your opponents control can't cause you to "
        "discard cards or sacrifice permanents."
    )
    return {
        "id": "t_bad_tamiyo",
        "name": "Test Bad Tamiyo",
        "oracle_text": text,
        "mana_cost": "{2}{G}{U}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": text,
                "effect": "opponents_cant_force_discard_or_sacrifice",
                "affects_player": "you",
            }
        ],
    }
