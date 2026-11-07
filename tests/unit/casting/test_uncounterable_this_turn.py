"""Spells that can't be countered this turn -- the `uncounterable_this_turn` op.

    Domri, Anarch of Bolas — "+1: Add {R} or {G}. Creature spells you cast this
    turn can't be countered."

The `spells_cant_be_countered` static says the same sentence without "this
turn", and it is read off a permanent for as long as that permanent is on the
battlefield. Domri's +1 is a resolved ability, and the continuous effect it
creates lasts for its stated duration whatever becomes of the walker (611.2a).
Granting the static to Domri would be a different card twice over: it would end
the moment he was attacked down, and it would never end while he stood.

The rules claims:

* **701.6a -- a covered spell stays on the stack.** A counterspell aimed at a
  creature spell cast after the +1 resolved does nothing to it.
* **The filter is the printed one.** A non-creature spell is countered as usual.
* **611.2a -- it outlives its source.** Domri leaving after the +1 resolved
  leaves the effect in force for the rest of the turn.
* **514.2 -- it ends at cleanup.** The next turn's creature spells can be
  countered.
* **"You cast" is the ability's controller**, fixed as it resolves: an
  opponent's creature spell is countered as usual, and so is a copy its
  controller never cast (707.10).
* **611.2c -- it modifies a rule, so it is asked at the counter.** Veil of
  Summer cast in response to a counterspell protects the spell already on the
  stack; Insist's "the next creature spell" covers that spell and no other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import TEST_CARD_DIR, only_oid, pass_until, settle

WALKER = "t_uncounterable_walker"  # Domri's +1, without the mana
VEIL = "t_uncounterable_veil"  # {G} instant: spells you control, this turn
INSIST = "t_uncounterable_insist"  # {G} instant: the next creature spell
FLASH_BEAR = "t_uncounterable_flash_bear"  # {1}{G} 2/2 flash
BEAR = "t_bear"  # {1}{G} 2/2
RITE = "t_plain_instant"  # {W} instant
COUNTER = "t_counterspell"  # {U}{U}, counter target spell

DOMRI_LINE = "+1: Creature spells you cast this turn can't be countered."
CREATURES_CAST = {
    "op": "uncounterable_this_turn",
    "affects_spells": {"types": ["Creature"]},
    "cast": True,
}


def walker(**op_extra) -> dict:
    return {
        "id": WALKER,
        "name": "Uncounterable Walker",
        "mana_cost": "{2}{R}{G}",
        "types": ["Planeswalker"],
        "subtypes": ["Domri"],
        "loyalty": 3,
        "abilities": [
            {
                "kind": "activated",
                "text": DOMRI_LINE,
                "cost": {"loyalty": 1},
                "effects": [{**CREATURES_CAST, **op_extra}],
            }
        ],
    }


def instant(card_id: str, name: str, text: str, effect: dict) -> dict:
    return {
        "id": card_id,
        "name": name,
        "oracle_text": text,
        "mana_cost": "{G}",
        "types": ["Instant"],
        "colors": ["G"],
        "spell_effects": [effect],
    }


def flash_bear() -> dict:
    return {
        "id": FLASH_BEAR,
        "name": "Uncounterable Flash Bear",
        "oracle_text": "Flash",
        "mana_cost": "{1}{G}",
        "types": ["Creature"],
        "subtypes": ["Bear"],
        "keywords": ["flash"],
        "power": 2,
        "toughness": 2,
    }


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    paths = authored_card_paths(Path("data/cards")) + sorted(TEST_CARD_DIR.glob("*.cards.json"))
    cards = {card.id: card for card in CardRegistry.from_paths(paths)}
    specs = (
        walker(),
        instant(
            VEIL,
            "Uncounterable Veil",
            "Spells you control can't be countered this turn.",
            {"op": "uncounterable_this_turn"},
        ),
        instant(
            INSIST,
            "Uncounterable Insist",
            "The next creature spell you cast this turn can't be countered.",
            {
                "op": "uncounterable_this_turn",
                "affects_spells": {"types": ["Creature"]},
                "next_spell": True,
            },
        ),
        flash_bear(),
    )
    for spec in specs:
        compiled = compile_spec(spec)
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


LANDS = ["island", "island", "forest", "forest", "forest", "forest", "plains"]


def position(pool: CardRegistry, *, mine=(WALKER,), hand0=(BEAR,), hand1=(COUNTER,)):
    """Player 0 has ``mine`` out and ``hand0`` in hand; player 1 holds ``hand1``.

    Both seats have two Islands for the counterspell and Forests for a bear.
    """
    return (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [*mine, *LANDS])
        .battlefield(1, list(LANDS))
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def plus_one(game) -> None:
    oid = only_oid(game, WALKER)
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    settle(game)


def _cast_action(game, card_id: str, pid: int, target_oid: int | None = None):
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or game.state.objects[action.source].def_id != card_id:
            continue
        if game.state.objects[action.source].owner != pid:
            continue
        if target_oid is not None:
            spell = game.state.stack_item(action.targets[0].id) if action.targets else None
            if spell is None or spell.oid != target_oid:
                continue
        return action
    return None


def cast(game, card_id: str, pid: int) -> int:
    """Cast ``card_id`` from ``pid``'s hand and return its oid; nothing resolves."""
    pass_until(game, lambda g: _cast_action(g, card_id, pid) is not None)
    action = _cast_action(game, card_id, pid)
    assert action is not None, f"{card_id} is castable"
    game.apply(action)
    return action.source


def counter(game, victim: int, *, by: int, then=None) -> Zone:
    """``by`` casts the counterspell at ``victim``; everything resolves.

    ``then`` runs with the counterspell on the stack, before anything resolves --
    a response from the victim's side. Returns where ``victim`` ended up.
    """
    pass_until(game, lambda g: _cast_action(g, COUNTER, by, victim) is not None)
    action = _cast_action(game, COUNTER, by, victim)
    assert action is not None, "the counterspell is castable -- it is not the target that failed"
    game.apply(action)
    if then is not None:
        then(game)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game.state.objects[victim].zone


class TestWithoutTheEffect:
    def test_the_counterspell_works(self, pool):
        """The control. Without it there is nothing to attribute the rest to."""
        game = position(pool)
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.GRAVEYARD


class TestItShieldsWhatItNames:
    def test_a_creature_spell_cast_after_it_resolves(self, pool):
        """701.6a: the counterspell resolves and the bear stays on the stack."""
        game = position(pool)
        plus_one(game)
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.BATTLEFIELD

    def test_a_noncreature_spell_is_countered(self, pool):
        """The filter is "creature spells", not "spells"."""
        game = position(pool, hand0=(RITE,))
        plus_one(game)
        rite = cast(game, RITE, 0)
        assert counter(game, rite, by=1) is Zone.GRAVEYARD

    def test_an_opponents_creature_spell_is_countered(self, pool):
        """"You cast" is Domri's controller: the opponent's flash bear is fair game."""
        game = position(pool, hand0=(COUNTER,), hand1=(FLASH_BEAR,))
        plus_one(game)
        bear = cast(game, FLASH_BEAR, 1)
        assert counter(game, bear, by=0) is Zone.GRAVEYARD

    def test_a_copy_was_never_cast(self, pool):
        """707.10: Domri's "cast" leaves a copy its controller never cast exposed."""
        game = position(pool)
        plus_one(game)
        cast(game, BEAR, 0)
        original = game.state.stack[-1]
        copy = put_copy_on_stack(game.state, 0, original)
        ctx = EffectContext(state=game.state, controller=1, source_oid=None)
        for sid in (copy.sid, original.sid):
            list(execute(ctx, [{"op": "counter", "sid": {"const": sid}}]))
        remaining = [item.sid for item in game.state.stack]
        assert copy.sid not in remaining, "the copy is countered"
        assert original.sid in remaining, "the cast original is not"


class TestItOutlivesItsSource:
    """611.2a: the effect of a resolved ability is not tied to the walker."""

    @pytest.mark.parametrize("zone", [Zone.GRAVEYARD, Zone.EXILE, Zone.HAND])
    def test_domri_leaving_keeps_it(self, pool, zone):
        game = position(pool)
        plus_one(game)
        move_object(game.state, only_oid(game, WALKER), zone)
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.BATTLEFIELD


class TestItEndsWithTheTurn:
    def test_cleanup_sweeps_it(self, pool):
        game = position(pool)
        plus_one(game)
        assert game.state.uncounterable_grants
        pass_until(game, lambda g: g.state.turn == 2)
        assert game.state.uncounterable_grants == []

    def test_next_turns_creature_spell_is_countered(self, pool):
        """514.2: "this turn" means this one. Two turns on, the bear is exposed."""
        game = position(pool)
        plus_one(game)
        pass_until(
            game,
            lambda g: g.state.turn == 3
            and g.state.active_player == 0
            and g.state.step is Step.PRECOMBAT_MAIN,
        )
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.GRAVEYARD


class TestItIsAskedAtTheCounter:
    """611.2c: a rule-modifying effect reaches spells it did not see resolve."""

    def test_veil_protects_the_spell_already_on_the_stack(self, pool):
        """Veil of Summer in response to the counterspell: the bear survives."""
        game = position(pool, hand0=(BEAR, VEIL))

        def respond_with_veil(game):
            cast(game, VEIL, 0)
            # Resolve the Veil alone; the counterspell is still beneath it.
            pass_until(game, lambda g: not g.state.stack or g.state.stack[-1].def_id != VEIL)

        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1, then=respond_with_veil) is Zone.BATTLEFIELD

    def test_insist_covers_the_next_creature_spell(self, pool):
        game = position(pool, hand0=(INSIST, BEAR))
        cast(game, INSIST, 0)
        settle(game)
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.BATTLEFIELD

    def test_insist_waits_past_a_spell_its_filter_misses(self, pool):
        """A non-creature spell cast in between neither spends it nor is covered."""
        game = position(pool, hand0=(INSIST, RITE, BEAR))
        cast(game, INSIST, 0)
        settle(game)
        rite = cast(game, RITE, 0)
        settle(game)
        assert game.state.objects[rite].zone is Zone.GRAVEYARD
        grant = game.state.uncounterable_grants[0]
        assert grant.sid is None, "the instant did not spend it"
        bear = cast(game, BEAR, 0)
        assert counter(game, bear, by=1) is Zone.BATTLEFIELD

    def test_insist_covers_only_the_one_spell(self, pool):
        """The first creature spell binds it; the second is exposed."""
        game = position(pool, hand0=(INSIST, BEAR, BEAR))
        cast(game, INSIST, 0)
        settle(game)
        first = cast(game, BEAR, 0)
        settle(game)
        assert game.state.objects[first].zone is Zone.BATTLEFIELD
        second = cast(game, BEAR, 0)
        assert counter(game, second, by=1) is Zone.GRAVEYARD


class TestTheLoaderGuards:
    @pytest.mark.parametrize(
        "extra, message",
        [
            ({"duration": "until_your_next_turn"}, "duration"),
            ({"affects_spells": {"controller": "you"}}, "unsupported keys"),
            ({"affects_spells": {"types": ["Creture"]}}, "unknown card type"),
            ({"cast": "yes"}, "true or false"),
            ({"player": "each_opponent"}, "takes no 'player'"),
            ({"countered_by": {"colors": ["U", "B"]}}, "takes no 'countered_by'"),
        ],
    )
    def test_refused(self, extra, message):
        with pytest.raises(DslError, match=message):
            compile_spec(walker(**extra))

    def test_domris_line_loads(self):
        assert compile_spec(walker()).id == WALKER
