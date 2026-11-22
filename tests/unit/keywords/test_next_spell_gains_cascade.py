"""A spell given cascade -- the `next_spell_gains_cascade` op.

    Sloppity Bilepiper — "Jolly Gutpipes — {2}, {T}, Sacrifice a creature: The
    next creature spell you cast this turn has cascade."

Rule 702.85a makes cascade a triggered ability **of the spell**: "When you cast
this spell, exile cards from the top of your library until you exile a nonland
card whose mana value is less than this spell's mana value." The arrangement it
replaces -- a `delayed_trigger` on the granting permanent running the `cascade`
op -- is a different ability: it belongs to the Bilepiper, its default ceiling
is the Bilepiper's mana value, and the spell never has cascade at all.

The rules claims:

* **702.85a -- the spell has it.** The trigger's source is the spell, and the
  ceiling is that spell's mana value -- the X it was cast with included
  (202.3e).
* **The filter is the printed one.** A noncreature spell leaves a creature
  grant waiting; the creature spell after it spends it.
* **"The next" is one spell.** The second creature spell has no cascade.
* **702.85c -- each instance triggers.** Two grants on one spell are two
  cascades.
* **611.2a -- it outlives its source.** The granter leaving after the ability
  resolved changes nothing.
* **514.2 -- "this turn".** An unspent grant is gone at cleanup.
* **"They" is the named player** (Bigger on the Inside): the target player's
  spell cascades down the target player's library.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import TEST_CARD_DIR, activations, library_ids, only_oid, pass_until, settle

PIPER = "t_gc_piper"  # {T}: the next creature spell you cast this turn has cascade
APOSTLE = "t_gc_apostle"  # {T}: the next noncreature spell ...
DOOR = "t_gc_door"  # {T}: target player's next spell this turn has cascade
BEAR = "t_bear"  # {1}{G} 2/2, mana value 2
BIG = "t_big"  # {5}{G} 6/6, mana value 6
HYDRA = "t_x_hydra"  # {X}{G}, printed mana value 1
RITE = "t_plain_instant"  # {W} instant, mana value 1
SORCERY = "t_cascader"  # {4}{R} sorcery, mana value 5 (its own cascade unused here)
FOREST = "forest"


def granter(card_id: str, name: str, text: str, effect: dict, **extra) -> dict:
    return {
        "id": card_id,
        "name": name,
        "oracle_text": text,
        "mana_cost": "{1}",
        "types": ["Artifact"],
        "abilities": [
            {"kind": "activated", "text": text, "cost": {"tap": True}, "effects": [effect], **extra}
        ],
    }


PIPER_SPEC = granter(
    PIPER,
    "Cascade Piper",
    "{T}: The next creature spell you cast this turn has cascade.",
    {"op": "next_spell_gains_cascade", "affects_spells": {"types": ["Creature"]}},
)


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    paths = authored_card_paths(Path("data/cards")) + sorted(TEST_CARD_DIR.glob("*.cards.json"))
    cards = {card.id: card for card in CardRegistry.from_paths(paths)}
    specs = (
        PIPER_SPEC,
        granter(
            APOSTLE,
            "Cascade Apostle",
            "{T}: The next noncreature spell you cast this turn has cascade.",
            {"op": "next_spell_gains_cascade", "affects_spells": {"not_types": ["Creature"]}},
        ),
        granter(
            DOOR,
            "Cascade Door",
            "{T}: The next spell target player casts this turn has cascade.",
            {"op": "next_spell_gains_cascade", "player": {"target": "t1"}},
            targets=[{"id": "t1", "kind": "player", "count": 1}],
        ),
    )
    for spec in specs:
        compiled = compile_spec(spec)
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


def position(pool, *, mine=(PIPER,), theirs=(), hand0=(BIG,), library0=(FOREST, BEAR, BIG), lands=6):
    """Player 0 has ``mine`` and ``lands`` Forests (plus a Mountain and a
    Plains) out, ``hand0`` in hand and ``library0`` on top of twenty Plains;
    player 1 has ``theirs``."""
    return (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, [*mine, *[FOREST] * lands, "mountain", "plains"])
        .battlefield(1, [*theirs, FOREST, FOREST])
        .hand(0, list(hand0))
        .library(0, [*library0, *["plains"] * 20])
        .library(1, [BEAR, *["plains"] * 20])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def grant(game, card_id: str = PIPER, target_player: int | None = None) -> None:
    oid = only_oid(game, card_id)
    pass_until(game, lambda g: bool(activations(g, oid)))
    options = activations(game, oid)
    if target_player is not None:
        options = [a for a in options if a.targets and a.targets[0].id == target_player]
    game.apply(options[0])
    settle(game)


def cast(game, card_id: str, pid: int = 0) -> int:
    def castable(g):
        return any(
            a.kind is ActionKind.CAST
            and g.state.objects[a.source].def_id == card_id
            and g.state.objects[a.source].owner == pid
            for a in g.legal_actions()
        )

    pass_until(game, castable)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and game.state.objects[a.source].owner == pid
    )
    game.apply(action)
    # Choose X at its maximum, as `pass_until` would.
    while (pending := game.pending()) is not None and pending.kind is DecisionKind.CHOOSE_X:
        game.apply(max(game.legal_actions(), key=lambda a: a.choice or 0))
    return action.source


def resolve_all(game, *, accept: bool = False) -> None:
    """Resolve everything, taking (or refusing) each free cast cascade offers."""

    def asked_or_done(g) -> bool:
        pending = g.pending()
        if pending is not None and pending.kind is DecisionKind.MAY:
            return True
        return not g.state.stack and not g.state.pending_triggers

    for _ in range(20):
        pass_until(game, asked_or_done)
        pending = game.pending()
        if pending is None or pending.kind is not DecisionKind.MAY:
            return
        want = ActionKind.YES if accept else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is want))
    raise AssertionError("the stack never emptied")


def cascades_on(game, oid: int, *, accept: bool = False) -> list:
    """Resolve the stack, then every cascade that walked a library with
    ``oid`` as its source -- one per instance that triggered."""
    resolve_all(game, accept=accept)
    return [e for e in game.state.events if e.type == "cascade" and e.source == oid]


def on_battlefield(game, card_id: str, pid: int = 0) -> int:
    return sum(1 for o in game.state.battlefield_objects(pid) if o.def_id == card_id)


class TestWithoutTheGrant:
    def test_a_creature_spell_has_no_cascade(self, pool):
        """The control: without the activation nothing triggers off the cast."""
        game = position(pool)
        big = cast(game, BIG)
        assert cascades_on(game, big) == []


class TestTheSpellHasCascade:
    def test_the_trigger_is_the_spells_own(self, pool):
        """702.85a: the trigger's source is the spell, and it is the rules'
        cascade trigger -- bound to the spell by the cast."""
        game = position(pool)
        grant(game)
        big = cast(game, BIG)
        assert game.state.cascade_grants[0].sid == game.state.stack[0].sid
        assert len(cascades_on(game, big)) == 1

    def test_it_casts_the_first_cheaper_nonland(self, pool):
        """The Forest is walked past and the bear, at 2 under 6, is cast free."""
        game = position(pool)
        grant(game)
        big = cast(game, BIG)
        assert len(cascades_on(game, big, accept=True)) == 1
        assert on_battlefield(game, BEAR) == 1
        assert on_battlefield(game, BIG) == 1

    def test_the_ceiling_counts_x(self, pool):
        """202.3e: the hydra cast with X = 5 has mana value 6, so the bear
        (2) comes in under it -- against the printed {X}{G}'s 1 it never would."""
        game = position(pool, hand0=(HYDRA,), library0=(BIG, BEAR), lands=4)
        grant(game)
        hydra = cast(game, HYDRA)
        assert game.state.stack[0].x == 5
        assert len(cascades_on(game, hydra, accept=True)) == 1
        assert on_battlefield(game, BEAR) == 1
        assert BIG in library_ids(game), "the giant, at 6, is not under 6"

    def test_it_outlives_its_source(self, pool):
        """611.2a: the grant is the player's, not the artifact's."""
        game = position(pool)
        grant(game)
        move_object(game.state, only_oid(game, PIPER), Zone.GRAVEYARD)
        big = cast(game, BIG)
        assert len(cascades_on(game, big)) == 1


class TestTheNextMatchingSpell:
    def test_a_noncreature_spell_leaves_it_waiting(self, pool):
        """The filter is the printed face: the instant does not spend it."""
        game = position(pool, hand0=(RITE, BIG))
        grant(game)
        rite = cast(game, RITE)
        assert cascades_on(game, rite) == []
        big = cast(game, BIG)
        assert len(cascades_on(game, big)) == 1

    def test_the_second_creature_spell_has_none(self, pool):
        """"The next" is one spell."""
        game = position(pool, hand0=(BEAR, BEAR), library0=())
        grant(game)
        first = cast(game, BEAR)
        assert len(cascades_on(game, first)) == 1
        second = cast(game, BEAR)
        assert cascades_on(game, second) == []

    def test_noncreature_names_the_other_half(self, pool):
        """Dark Apostle's "noncreature": the creature misses, the sorcery hits
        -- twice, its own printed cascade and the one it was given (702.85c)."""
        game = position(pool, mine=(APOSTLE,), hand0=(BEAR, SORCERY), lands=7)
        grant(game, APOSTLE)
        bear = cast(game, BEAR)
        assert cascades_on(game, bear) == []
        sorcery = cast(game, SORCERY)
        assert len(cascades_on(game, sorcery)) == 2

    def test_two_grants_are_two_cascades(self, pool):
        """702.85c: each instance triggers separately."""
        game = position(pool, mine=(PIPER, APOSTLE))
        grant(game)
        # A second creature grant, written straight to the table.
        game.state.cascade_grants.append(game.state.cascade_grants[0])
        big = cast(game, BIG)
        assert len(cascades_on(game, big)) == 2


class TestThisTurn:
    def test_an_unspent_grant_ends_at_cleanup(self, pool):
        """514.2: "this turn"."""
        game = position(pool)
        grant(game)
        assert game.state.cascade_grants
        pass_until(game, lambda g: g.state.active_player == 1)
        assert game.state.cascade_grants == []


class TestTheNamedPlayer:
    def test_they_cascade_down_their_own_library(self, pool):
        """Bigger on the Inside: the opponent's ability names player 0, so
        player 0's spell cascades, under player 0, down player 0's library --
        not the activator's, whose top card is a bear too."""
        game = position(pool, mine=(), theirs=(DOOR,))
        grant(game, DOOR, target_player=0)
        assert [g.player for g in game.state.cascade_grants] == [0]
        big = cast(game, BIG)
        (walk,) = cascades_on(game, big, accept=True)
        assert walk.player == 0
        assert on_battlefield(game, BEAR, 0) == 1
        assert library_ids(game, 1)[0] == BEAR, "the activator's library is untouched"

    def test_the_activator_is_not_granted(self, pool):
        game = position(pool, mine=(DOOR,))
        grant(game, DOOR, target_player=1)
        big = cast(game, BIG)
        assert cascades_on(game, big) == [], "the grant is player 1's next spell"


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "extra",
        [
            {"affects_spells": {"types": ["Creture"]}},
            {"affects_spells": {"controller": "you"}},
            {"affects_spells": {}},
            {"max_mana_value": {"const": 3}},
            {"duration": "this_turn"},
            {"player": "everybody"},
        ],
    )
    def test_a_malformed_grant(self, extra):
        spec = dict(PIPER_SPEC)
        effect = {"op": "next_spell_gains_cascade", **extra}
        spec["abilities"] = [{**PIPER_SPEC["abilities"][0], "effects": [effect]}]
        with pytest.raises(DslError):
            compile_spec(spec)
