"""Doubling a token creation: "twice that many of those tokens are created instead".

    Bard, King of Dale: "If one or more tokens would be created under your
    control, twice that many of those tokens are created instead."
    (Also Parallel Lives, Anointed Procession, Doubling Season's token half, and
    -- for every player -- Primal Vigor.)

`replace_token_creation` could already substitute *which* token is made
(Academy Manufactor, Divine Visitation, see `test_token_creation_replacement.py`)
and could not say *how many*. `create_instead` is a list of ids, and a doubler
names no token: listing one would turn every other token into it. So the static
gains a second axis, `token_multiplier`, that scales each matched pending entry
and leaves its identity alone.

The near misses are both wrong on an ordinary board. A `token_created` trigger
that makes another copy uses the stack, makes the extra token *later* and one at a
time, and -- because its own token is a token creation too -- re-triggers
forever. And `create_token`'s `amount` is on the *creating* effect, so it cannot
see a token some other card makes.

The rules claims:

* **614.1a / 614.5 -- a replacement modifies the event once.** A doubler does not
  double the tokens it just doubled.
* **Two doublers compound.** Each is a separate replacement of the one event and
  each applies once, to the event as the other left it: 1 -> 2 -> 4, and a third
  makes 8. The affected player orders them (616.1); the engine applies them in
  battlefield order without asking, which a product cannot show.
* **"Under your control" is the token's controller**, not whoever controls the
  effect creating it -- an opponent's Beast Within giving you an Elk is doubled
  by your Bard, and the token you give an opponent is not.
* **"Those tokens" are those tokens.** A copy token is doubled into two copies,
  and a token created tapped and attacking is doubled into two tapped attackers.
* It is a static, so it stops the moment its source leaves.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.structs import CombatState
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

BARD = "bard_doubler"
LIVES = "parallel_lives_doubler"
VIGOR = "primal_vigor_doubler"
VISITATION = "divine_visitation"
SOLDIER = "human_soldier_1_1_w"
TREASURE = "treasure_token"
ANGEL = "angel_4_4_w_flying_vigilance"
BEARS = "grizzly_bears"

TOKEN_LINE = (
    "If one or more tokens would be created under your control, twice that many "
    "of those tokens are created instead."
)


def doubler(card_id: str, name: str, **extra) -> dict:
    return {
        "id": card_id,
        "name": name,
        "mana_cost": "{3}{G}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": TOKEN_LINE,
                "effect": "replace_token_creation",
                "token_multiplier": 2,
                **extra,
            }
        ],
    }


def visitation() -> dict:
    return {
        "id": VISITATION,
        "name": "Divine Visitation",
        "mana_cost": "{3}{W}{W}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "If one or more creature tokens would be created under your "
                    "control, that many 4/4 white Angel creature tokens with "
                    "flying and vigilance are created instead."
                ),
                "effect": "replace_token_creation",
                "affects_token": {"types": ["Creature"]},
                "create_instead": [ANGEL],
            }
        ],
    }


def with_cards(*specs: dict) -> CardRegistry:
    cards = {
        card.id: card for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in specs:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    """The shipped pool plus three doublers and a Visitation, compiled through
    `compile_card` so every loader guard is the one a card file meets."""
    return with_cards(
        doubler(BARD, "Bard, King of Dale"),
        doubler(LIVES, "Parallel Lives"),
        doubler(VIGOR, "Primal Vigor", affects_player="any"),
        visitation(),
    )


def board(pool: CardRegistry, mine: list[str], theirs: list[str] = ()):
    builder = GameBuilder(pool, players=2, seed=0).battlefield(0, list(mine))
    if theirs:
        builder = builder.battlefield(1, list(theirs))
    return builder.build(advance=False)


def tokens(game, pid: int | None = None) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestTwiceThatMany:
    def test_one_token_becomes_two(self, pool):
        game = board(pool, [BARD])
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 2}

    def test_the_count_asked_for_is_what_is_doubled(self, pool):
        """ "Create three Treasures" is one event of three, so six."""
        game = board(pool, [BARD])
        create_token(game.state, TREASURE, 0, 3)
        assert tokens(game) == {TREASURE: 6}

    def test_every_token_is_a_token_created_event(self, pool):
        """ "Whenever you create a token" sees each doubled token arrive."""
        game = board(pool, [BARD])
        mark = len(game.state.events)
        create_token(game.state, SOLDIER, 0, 1)
        made = [e for e in game.state.events[mark:] if e.type == "token_created"]
        assert [e.data.get("card") for e in made] == [SOLDIER, SOLDIER]

    def test_no_doubler_means_the_ordinary_count(self, pool):
        game = board(pool, [])
        create_token(game.state, SOLDIER, 0, 2)
        assert tokens(game) == {SOLDIER: 2}


class TestDoublersCompound:
    """614.5 per replacement, and several replacements of one event."""

    def test_two_doublers_make_four(self, pool):
        game = board(pool, [BARD, LIVES])
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 4}

    def test_three_doublers_make_eight(self, pool):
        game = board(pool, [BARD, LIVES, VIGOR])
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 8}

    def test_the_order_they_arrived_in_does_not_change_the_answer(self, pool):
        """The engine does not ask the 616.1 question; for a product it cannot
        matter, and this pins that it does not."""
        first = board(pool, [BARD, LIVES])
        create_token(first.state, SOLDIER, 0, 3)
        second = board(pool, [LIVES, BARD])
        create_token(second.state, SOLDIER, 0, 3)
        assert tokens(first) == tokens(second) == {SOLDIER: 12}

    def test_a_doubler_does_not_redouble_its_own_output(self, pool):
        """Its two tokens are tokens created under your control; re-reading them
        would never terminate."""
        game = board(pool, [BARD])
        create_token(game.state, SOLDIER, 0, 1)
        assert sum(tokens(game).values()) == 2

    def test_a_doubler_and_a_visitation_make_twice_that_many_angels(self, pool):
        """Identity and count are separate axes, and either order gives two
        Angels for one Soldier."""
        for order in ([BARD, VISITATION], [VISITATION, BARD]):
            game = board(pool, order)
            create_token(game.state, SOLDIER, 0, 1)
            assert tokens(game) == {ANGEL: 2}, order


class TestWhoseTokensTheyAre:
    """ "Under your control" is where the token arrives, not who made it."""

    def test_an_opponents_token_creation_is_untouched(self, pool):
        game = board(pool, [BARD])
        create_token(game.state, SOLDIER, 1, 1)
        assert tokens(game, 1) == {SOLDIER: 1}

    def test_an_opponents_doubler_does_not_touch_your_tokens(self, pool):
        game = board(pool, [], theirs=[BARD])
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game, 0) == {SOLDIER: 1}

    def test_an_opponents_effect_giving_you_a_token_is_doubled(self, pool):
        """Beast Within's shape: the opponent's effect, your token, your Bard."""
        game = board(pool, [BARD])
        ctx = EffectContext(state=game.state, controller=1, source_oid=None)
        list(execute(ctx, [{"op": "create_token", "token": SOLDIER, "controller": "opponent"}]))
        assert tokens(game, 0) == {SOLDIER: 2}
        assert tokens(game, 1) == {}

    def test_your_effect_giving_an_opponent_a_token_is_not(self, pool):
        game = board(pool, [BARD])
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        list(execute(ctx, [{"op": "create_token", "token": SOLDIER, "controller": "opponent"}]))
        assert tokens(game, 1) == {SOLDIER: 1}

    def test_primal_vigor_doubles_every_players_tokens(self, pool):
        """`affects_player: "any"` -- the sentence that names nobody."""
        game = board(pool, [VIGOR])
        create_token(game.state, SOLDIER, 0, 1)
        create_token(game.state, SOLDIER, 1, 1)
        assert tokens(game, 0) == tokens(game, 1) == {SOLDIER: 2}


class TestThoseTokens:
    """What the creating effect said about the token still holds for each."""

    def test_copy_tokens_are_doubled_into_copies(self, pool):
        game = board(pool, [BARD, BEARS])
        bear = only_oid(game, BEARS)
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        list(execute(ctx, [{"op": "copy_permanent", "objects": {"self_only": True}}]))
        assert tokens(game) == {BEARS: 2}

    def test_a_doubled_copy_keeps_the_copy_exception(self, pool):
        """Embalm's "except it's a white Zombie" describes *those* tokens, so both
        carry it -- unlike a substitution, which drops it."""
        game = board(pool, [BARD, BEARS])
        create_token(game.state, BEARS, 0, 1, overrides={"colors": ["W"]})
        made = [o for o in game.state.battlefield_objects(0) if o.is_token]
        assert len(made) == 2
        assert all(chars(game.state, o.oid).colors == frozenset({"W"}) for o in made)

    def test_tapped_and_attacking_tokens_are_doubled_tapped_and_attacking(self, pool):
        game = board(pool, [BARD])
        game.state.combat = CombatState(declaring_player=0)
        made = create_token(game.state, SOLDIER, 0, 1, tapped=True, attacking=1)
        assert len(made) == 2
        assert all(game.state.objects[oid].tapped for oid in made)
        assert all(game.state.combat.attackers.get(oid) == 1 for oid in made)


class TestWhenItStopsApplying:
    def test_it_stops_when_the_source_leaves_the_battlefield(self, pool):
        game = board(pool, [BARD])
        create_token(game.state, SOLDIER, 0, 1)
        move_object(game.state, only_oid(game, BARD), Zone.GRAVEYARD, to_player=0)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 3}

    def test_one_of_two_leaving_drops_back_to_twice(self, pool):
        game = board(pool, [BARD, LIVES])
        move_object(game.state, only_oid(game, LIVES), Zone.GRAVEYARD, to_player=0)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 2}


class TestTheCardFileMustSayWhatItMeans:
    def test_the_doubler_compiles(self):
        with_cards(doubler(BARD, "Bard, King of Dale"))

    @pytest.mark.parametrize("bad", [0, 1])
    def test_a_multiplier_below_two_is_refused(self, bad):
        spec = doubler(BARD, "Bard", token_multiplier=bad)
        with pytest.raises(DslError, match="token_multiplier: must be 2 or more"):
            compile_card(CardModel.model_validate(spec))

    def test_both_axes_at_once_is_refused(self):
        spec = doubler(BARD, "Bard", create_instead=[TREASURE])
        with pytest.raises(DslError, match="not both"):
            compile_card(CardModel.model_validate(spec))

    def test_neither_axis_is_refused(self):
        spec = doubler(BARD, "Bard")
        del spec["abilities"][0]["token_multiplier"]
        with pytest.raises(DslError, match="or 'token_multiplier'"):
            compile_card(CardModel.model_validate(spec))

    def test_the_multiplier_means_nothing_on_another_static(self):
        spec = doubler(BARD, "Bard", affects_player="you")
        spec["abilities"][0]["effect"] = "no_hand_limit"
        with pytest.raises(DslError, match="only mean"):
            compile_card(CardModel.model_validate(spec))
