"""Spells a static gives cascade -- the `spells_have_cascade` static.

    Abaddon the Despoiler — "Mark of Chaos Ascendant — During your turn,
    spells you cast from your hand with mana value X or less have cascade,
    where X is the total amount of life your opponents have lost this turn."

The spells **have** cascade (702.85a): each matching spell carries the rules'
cascade trigger, sourced from the spell, so its ceiling is the spell's own
mana value and it resolves whatever becomes of Abaddon. A `spell_cast` trigger
printed on Abaddon running the `cascade` op is a different ability -- it is
Abaddon's, and it dies with him.

The rules claims:

* **The ceiling is live.** X is the opponents' life lost this turn as the spell
  is cast, summed over them (`life_lost_this_turn` as a static value), and the
  spell's mana value counts its X (202.3e). "X or less" admits X itself.
* **Your own life lost is not counted**, and nor are the opponents' gains.
* **"From your hand".** A spell cast from anywhere else -- the bear a cascade
  itself casts out of exile -- has no cascade.
* **"During your turn".** On an opponent's turn nothing cascades.
* **"Spells you cast".** An opponent's spell has none.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import gain_life, lose_life
from commanderblitz.engine.sandbox import GameBuilder
from tests.conftest import TEST_CARD_DIR, pass_until

LORD = "t_shc_lord"  # Abaddon's static on a vanilla body
BEAR = "t_bear"  # {1}{G}, mana value 2
BIG = "t_big"  # {5}{G}, mana value 6
HYDRA = "t_x_hydra"  # {X}{G}
RITE = "t_plain_instant"  # {W} instant, mana value 1
FOREST = "forest"

MARK = (
    "Mark of Chaos Ascendant — During your turn, spells you cast from your hand "
    "with mana value X or less have cascade, where X is the total amount of life "
    "your opponents have lost this turn."
)
STATIC = {
    "kind": "static",
    "text": MARK,
    "effect": "spells_have_cascade",
    "affects_spells": {"from_zone": "hand"},
    "max_mana_value": {"life_lost_this_turn": "opponent"},
    "condition": {"is_your_turn": True},
}


def lord(**static_extra) -> dict:
    return {
        "id": LORD,
        "name": "Cascade Lord",
        "oracle_text": MARK,
        "mana_cost": "{4}{U}{B}{R}",
        "types": ["Creature"],
        "power": 5,
        "toughness": 5,
        "abilities": [{**STATIC, **static_extra}],
    }


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    paths = authored_card_paths(Path("data/cards")) + sorted(TEST_CARD_DIR.glob("*.cards.json"))
    cards = {card.id: card for card in CardRegistry.from_paths(paths)}
    compiled = compile_spec(lord())
    cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


def position(pool, *, hand0=(BIG,), hand1=(), lands=6, active=0, lord_seat=0):
    """``lord_seat`` has the Cascade Lord; both seats have ``lands`` Forests and
    a Plains, and a bear on top of their libraries."""
    lands_out = [*[FOREST] * lands, "plains"]
    builder = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [*([LORD] if lord_seat == 0 else []), *lands_out])
        .battlefield(1, [*([LORD] if lord_seat == 1 else []), *lands_out])
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, [BEAR, *["plains"] * 20])
        .library(1, [BEAR, *["plains"] * 20])
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
    )
    return builder.build()


def cast(game, card_id: str, pid: int = 0) -> int:
    def options(g):
        return [
            a
            for a in g.legal_actions()
            if a.kind is ActionKind.CAST
            and g.state.objects[a.source].def_id == card_id
            and g.state.objects[a.source].owner == pid
        ]

    pass_until(game, lambda g: bool(options(g)))
    action = options(game)[0]
    game.apply(action)
    while (pending := game.pending()) is not None and pending.kind is DecisionKind.CHOOSE_X:
        game.apply(max(game.legal_actions(), key=lambda a: a.choice or 0))
    return action.source


def cascades_on(game, oid: int, *, accept: bool = False) -> list:
    """Resolve the stack, then every cascade walked with ``oid`` as its source."""

    def asked_or_done(g) -> bool:
        pending = g.pending()
        if pending is not None and pending.kind is DecisionKind.MAY:
            return True
        return not g.state.stack and not g.state.pending_triggers

    for _ in range(20):
        pass_until(game, asked_or_done)
        pending = game.pending()
        if pending is None or pending.kind is not DecisionKind.MAY:
            break
        want = ActionKind.YES if accept else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is want))
    return [e for e in game.state.events if e.type == "cascade" and e.source == oid]


class TestTheCeiling:
    def test_no_life_lost_is_x_zero(self, pool):
        """The control: X is 0 and the bear's 2 is over it."""
        game = position(pool, hand0=(BEAR,))
        bear = cast(game, BEAR)
        assert cascades_on(game, bear) == []

    def test_x_or_less_admits_x(self, pool):
        """Two life lost makes X 2, and the bear's 2 is "X or less"."""
        game = position(pool, hand0=(BEAR,))
        lose_life(game.state, 1, 2)
        bear = cast(game, BEAR)
        assert len(cascades_on(game, bear)) == 1

    def test_a_dearer_spell_is_over_it(self, pool):
        game = position(pool, hand0=(BIG,))
        lose_life(game.state, 1, 5)
        big = cast(game, BIG)
        assert cascades_on(game, big) == []

    def test_the_ceiling_is_read_as_the_spell_is_cast(self, pool):
        """X rises with the turn's losses: six lost lets the giant in."""
        game = position(pool, hand0=(BIG,))
        lose_life(game.state, 1, 6)
        big = cast(game, BIG)
        assert len(cascades_on(game, big)) == 1

    def test_the_spells_x_counts(self, pool):
        """202.3e: the hydra cast with all seven lands (X = 6) has mana value 7,
        over a ceiling of 3 that its printed {X}{G}'s 1 would come in under --
        and inside a ceiling of 7."""
        game = position(pool, hand0=(HYDRA,))
        lose_life(game.state, 1, 3)
        hydra = cast(game, HYDRA)
        assert cascades_on(game, hydra) == []

        game = position(pool, hand0=(HYDRA,))
        lose_life(game.state, 1, 7)
        hydra = cast(game, HYDRA)
        assert len(cascades_on(game, hydra)) == 1

    def test_your_own_loss_is_not_counted(self, pool):
        game = position(pool, hand0=(BEAR,))
        lose_life(game.state, 0, 5)
        bear = cast(game, BEAR)
        assert cascades_on(game, bear) == []

    def test_a_gain_does_not_take_a_loss_back(self, pool):
        """"Life lost this turn", not the net change."""
        game = position(pool, hand0=(BEAR,))
        lose_life(game.state, 1, 2)
        gain_life(game.state, 1, 2)
        bear = cast(game, BEAR)
        assert len(cascades_on(game, bear)) == 1


class TestWhichSpells:
    def test_a_spell_cast_from_exile_has_none(self, pool):
        """The bear the giant's cascade casts comes from exile, not the hand."""
        game = position(pool, hand0=(BIG,))
        lose_life(game.state, 1, 6)
        big = cast(game, BIG)
        assert len(cascades_on(game, big, accept=True)) == 1
        bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        assert cascades_on(game, bear) == []

    def test_not_during_an_opponents_turn(self, pool):
        """"During your turn": the instant cast on player 1's turn has none."""
        game = position(pool, hand0=(RITE,), active=1)
        lose_life(game.state, 1, 2)
        rite = cast(game, RITE)
        assert cascades_on(game, rite) == []

    def test_during_your_turn_the_same_instant_has_it(self, pool):
        """The control for the case above."""
        game = position(pool, hand0=(RITE,))
        lose_life(game.state, 1, 2)
        rite = cast(game, RITE)
        assert len(cascades_on(game, rite)) == 1

    def test_an_opponents_spell_has_none(self, pool):
        """"Spells you cast": the Lord is player 1's, the bear player 0's."""
        game = position(pool, hand0=(BEAR,), lord_seat=1)
        lose_life(game.state, 0, 2)
        lose_life(game.state, 1, 2)
        bear = cast(game, BEAR)
        assert cascades_on(game, bear) == []


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "extra",
        [
            {"affects_spells": None},
            {"affects_spells": {"controller": "you", "from_zone": "hand"}},
            {"affects_spells": {"from_zone": "hands"}},
            {"max_mana_value": {"life_lost_this_turn": "everybody"}},
            {"max_mana_value": {"binding": "x"}},
            {"amount": 3},
        ],
    )
    def test_a_malformed_static(self, extra):
        with pytest.raises(DslError):
            compile_spec(lord(**extra))

    def test_the_ceiling_on_another_static(self):
        spec = lord()
        spec["abilities"] = [
            {
                "kind": "static",
                "text": MARK,
                "effect": "spells_cant_be_countered",
                "max_mana_value": {"const": 3},
            }
        ]
        with pytest.raises(DslError):
            compile_spec(spec)
