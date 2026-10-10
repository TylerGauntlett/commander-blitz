""""Copy the **next** instant or sorcery spell ... you cast **this turn**."

Sea Gate Stormcaller. A third value for a delayed trigger's ``duration``, and the
one the docstring on :data:`DELAYED_DURATIONS` said did not exist yet:

    The two axes -- repeating-or-once, and turn-scoped-or-not -- happen to be
    correlated in both printed cards ... a card that separated them would need a
    third entry here.

This card separates them. It fires **once**, like `until_it_fires`, and expires at
cleanup, like `this_turn` — and each existing value is wrong on exactly one axis,
which is what the two control classes below are:

- **`this_turn` re-arms.** Every matching spell fires it again, so a Stormcaller
  written that way is a Thousand-Year Storm. `TestThisTurnIsTheWrongOne` measures
  it: two casts, two gains.
- **`until_it_fires` outlives the turn.** `turn._cleanup_step` keeps it on purpose
  — the retention clause was written for Palace Jailer, whose crown may not move
  for six turns — so a Stormcaller whose controller casts nothing cheap copies a
  spell on some *later* turn instead. `TestUntilItFiresIsTheOtherWrongOne`
  measures that one.

`once_this_turn` needed one line of engine: `triggers._arm_delayed` strikes it off
as it arms, beside `until_it_fires`. The expiry was already right — `_cleanup_step`
keeps only `until_it_fires`, so anything else is dropped whether or not it fired.

**Latching it by hand is not a substitute**, and the gap record measured that too.
`set_turn_flag`'s `objects` go through `resolve_pool`, whose `self_only` finds the
source only while it is on the battlefield, so the latch stops working the moment
the 2/1 dies and the card copies every cheap spell for the rest of the turn. There
is no player-scoped flag, and `resolutions_this_turn` reads `ctx.resolutions`,
which `run_armed_delays` never sets.

The **filter** is the other half of Sea Gate Stormcaller and is deliberately not
built here. `_validate_delayed_trigger` refuses `filter` on a delayed trigger
because `matches_card_filter` reads eight clauses off the permanent hosting the
ability and a delayed one has none. A `condition` over the `subject` binding says
the same thing exactly — `t_once_cheap_gain` is that spelling, and
`TestTheConditionCarriesTheFilter` is the evidence it discriminates — at the cost
of being less obvious to read.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

ONCE = "t_once_gain"  # once_this_turn
EVERY = "t_every_gain"  # this_turn -- re-arms
FOREVER = "t_forever_gain"  # until_it_fires -- outlives the turn
CHEAP_WATCHER = "t_once_cheap_gain"  # once_this_turn, with the mana-value condition

CHEAP_SORCERY = "t_cheap_sorcery"  # {R} sorcery
DEAR_SORCERY = "t_dear_sorcery"  # {3}{R} sorcery -- mana value 4
CHEAP_CREATURE = "t_cheap_creature"  # {R} creature -- cheap, but not an instant


def position(builder, hand: list[str]):
    """One seat with enough Mountains to cast everything in ``hand`` twice over.

    Two players, and the turn limit is generous because two of the claims below
    are about what survives into the *next* turn.
    """
    b = builder(players=2)
    b.battlefield(0, ["mountain"] * 12)
    b.battlefield(1, ["mountain"] * 2)
    b.hand(0, list(hand))
    for pid in range(2):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.PRECOMBAT_MAIN).max_turns(6).build()


def cast(game, card_id: str, limit: int = 200) -> None:
    """Cast one copy of ``card_id`` from player 0's hand and let it resolve."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.PRIORITY and decision.player == 0:
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                settle(game)
                return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never got to cast {card_id}")


def settle(game, limit: int = 200) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.armed_delays:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))


def to_next_turn(game, limit: int = 400) -> None:
    """Pass until the active player has come back round to player 0."""
    start = game.state.turn
    for _ in range(limit):
        if game.state.turn > start + 1 and game.state.active_player == 0:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached the next turn")


def life(game) -> int:
    return game.state.players[0].life


class TestItFiresExactlyOnce:
    def test_the_first_matching_spell_fires_it(self, builder):
        game = position(builder, [ONCE, CHEAP_SORCERY])
        cast(game, ONCE)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 1

    def test_and_the_second_one_does_not(self, builder):
        """"The **next** spell", not "each spell"."""
        game = position(builder, [ONCE, CHEAP_SORCERY, CHEAP_SORCERY])
        cast(game, ONCE)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 1, "a second firing is a Thousand-Year Storm"

    def test_the_subscription_is_gone_from_the_state(self, builder):
        """Struck off as it arms, not merely ignored afterwards."""
        game = position(builder, [ONCE, CHEAP_SORCERY])
        cast(game, ONCE)
        assert any(d.trigger is not None for d in game.state.delayed_triggers)
        cast(game, CHEAP_SORCERY)
        assert not [d for d in game.state.delayed_triggers if d.trigger is not None]


class TestItExpiresAtEndOfTurn:
    def test_an_unfired_subscription_does_not_survive_the_turn(self, builder):
        game = position(builder, [ONCE, CHEAP_SORCERY])
        cast(game, ONCE)
        to_next_turn(game)
        assert not [d for d in game.state.delayed_triggers if d.trigger is not None]

    def test_and_so_a_later_spell_does_not_fire_it(self, builder):
        game = position(builder, [ONCE, CHEAP_SORCERY])
        cast(game, ONCE)
        to_next_turn(game)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before, "this turn means this turn"


class TestThisTurnIsTheWrongOne:
    """The first near miss: it re-arms, which on Sea Gate Stormcaller is a storm."""

    def test_it_fires_on_every_spell(self, builder):
        game = position(builder, [EVERY, CHEAP_SORCERY, CHEAP_SORCERY])
        cast(game, EVERY)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 2, "the control: this is what re-arming looks like"


class TestUntilItFiresIsTheOtherWrongOne:
    """The second near miss: `_cleanup_step` keeps it, for Palace Jailer's sake."""

    def test_it_survives_into_a_later_turn(self, builder):
        game = position(builder, [FOREVER, CHEAP_SORCERY])
        cast(game, FOREVER)
        to_next_turn(game)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 1, "the control: this is what outliving the turn looks like"


class TestTheConditionCarriesTheFilter:
    """A delayed trigger spells its filter as a condition over `subject`.

    Not merely accepted — actually discriminating, in both directions, which is
    what makes it an exact stand-in for the `filter` the loader refuses.
    """

    def test_a_cheap_instant_or_sorcery_fires_it(self, builder):
        game = position(builder, [CHEAP_WATCHER, CHEAP_SORCERY])
        cast(game, CHEAP_WATCHER)
        before = life(game)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 1

    def test_an_expensive_one_does_not(self, builder):
        game = position(builder, [CHEAP_WATCHER, DEAR_SORCERY])
        cast(game, CHEAP_WATCHER)
        before = life(game)
        cast(game, DEAR_SORCERY)
        assert life(game) == before, "mana value 4 is not 2 or less"

    def test_and_neither_does_a_cheap_creature(self, builder):
        game = position(builder, [CHEAP_WATCHER, CHEAP_CREATURE])
        cast(game, CHEAP_WATCHER)
        before = life(game)
        cast(game, CHEAP_CREATURE)
        assert life(game) == before, "cheap, but not an instant or sorcery"

    def test_a_passed_over_spell_does_not_spend_the_subscription(self, builder):
        """The interaction between the two halves, and the one that would make a
        Stormcaller copy nothing at all: a non-matching cast must leave the
        subscription armed for the spell the card is actually about."""
        game = position(builder, [CHEAP_WATCHER, DEAR_SORCERY, CHEAP_SORCERY])
        cast(game, CHEAP_WATCHER)
        before = life(game)
        cast(game, DEAR_SORCERY)
        cast(game, CHEAP_SORCERY)
        assert life(game) == before + 1


class TestTheLoader:
    def spell(self, duration):
        return {
            "id": "t_probe_delay",
            "name": "Probe Delay",
            "mana_cost": "{R}",
            "types": ["Instant"],
            "spell_effects": [
                {
                    "op": "delayed_trigger",
                    "text": "The next spell you cast this turn, you gain 1 life.",
                    "duration": duration,
                    "trigger": {"event": "spell_cast", "controller": "you"},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_the_new_duration_is_accepted(self):
        card = compile_card(CardModel.model_validate(self.spell("once_this_turn")))
        assert card.spell_effects[0]["duration"] == "once_this_turn"

    def test_a_misspelling_is_still_refused(self):
        """A typo falling through to the `this_turn` default would retime the card."""
        with pytest.raises(DslError, match="unknown delayed_trigger duration"):
            compile_card(CardModel.model_validate(self.spell("once_per_turn")))

    def test_a_filter_is_still_refused(self):
        """The half not built: `matches_card_filter` reads the hosting permanent."""
        spell = self.spell("once_this_turn")
        spell["spell_effects"][0]["trigger"]["filter"] = {"any_types": ["Instant"]}
        with pytest.raises(DslError, match="not supported on a delayed"):
            compile_card(CardModel.model_validate(spell))
