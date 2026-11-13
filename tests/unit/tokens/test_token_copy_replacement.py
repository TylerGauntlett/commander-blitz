"""Replacing a token creation with copies of a chosen creature.

Esix, Fractal Bloom: "... you may instead choose a creature other than Esix and
create that many tokens that are copies of that creature."

A 614.1a replacement of the creation, and `replace_token_creation`'s fourth
mode, `copy_instead`: a selector over the battlefield naming what may be
chosen. The near misses are each a different card. `create_instead` names a
fixed token id at load time and cannot name a creature chosen as the tokens
are made; `copy_permanent` after a `token_created` trigger uses the stack and
keeps the original tokens beside the copies.

The rules claims:

* **You may.** The static's controller is asked as the tokens are about to be
  made; choosing nothing leaves the creation alone.
* **That many.** The count the event would have made is kept, and every token
  becomes a copy -- of the creature's copiable values (707.2), a token's own
  creating-effect values included.
* **A creature other than Esix.** Anybody's, never the source itself.
* **Under your control.** An opponent's creation asks nothing.
* **616.1, the controller's order.** Not asked; the copy replacement goes after
  every other one, so beside a doubler one Treasure is two copies in either
  battlefield order.
* **Everything the creating effect said still applies** -- tapped, `as` --
  but not its `overrides`, which described the token never made.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import PendingDecision
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder

ESIX = "esix_probe"
BEARS = "grizzly_bears"
DOUBLING_SEASON = "doubling_season"
TREASURE = "treasure_token"
SHARK = "shark_x_x_u_flying"

LINE = (
    "If you would create one or more tokens, you may instead choose a creature "
    "other than this creature and create that many tokens that are copies of "
    "that creature."
)
COPY_INSTEAD = {"types": ["Creature"], "exclude_self": True}


def esix(**extra) -> dict:
    static = {
        "kind": "static",
        "text": LINE,
        "effect": "replace_token_creation",
        "copy_instead": dict(COPY_INSTEAD),
        **extra,
    }
    return {
        "id": ESIX,
        "name": "Esix Probe",
        "oracle_text": LINE,
        "mana_cost": "{4}{G}{U}",
        "types": ["Creature"],
        "subtypes": ["Fractal"],
        "power": 4,
        "toughness": 4,
        "abilities": [static],
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
    return with_cards(esix())


def board(pool: CardRegistry, mine=(ESIX, BEARS), theirs=()):
    """Player 0 with ``mine`` and player 1 with ``theirs``; returns ``(game, bears_oid)``."""
    game = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    bears = next((o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEARS), None)
    return game, bears


def run(game, effects: list[dict], choose=None, controller: int = 0):
    """Resolve ``effects`` as ``controller``'s; every decision asked is recorded.

    ``choose`` picks the oid to copy (``None`` declines).
    """
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, effects)
    asked: list[PendingDecision] = []
    answer = None
    while True:
        try:
            decision = gen.send(answer) if asked else next(gen)
        except StopIteration:
            return asked, ctx
        asked.append(decision)
        values = [opt.value for opt in decision.options]
        answer = [] if choose is None else [values.index(choose)]


def make(amount: int = 2, **extra) -> list[dict]:
    return [{"op": "create_token", "token": TREASURE, "amount": {"const": amount}, **extra}]


def tokens(game, pid: int = 0) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestYouMay:
    def test_choosing_a_creature_makes_that_many_copies_of_it(self, pool):
        game, bears = board(pool)
        asked, _ = run(game, make(2), choose=bears)
        assert len(asked) == 1 and asked[0].player == 0
        assert tokens(game) == {BEARS: 2}

    def test_declining_leaves_the_creation_alone(self, pool):
        game, _ = board(pool)
        asked, _ = run(game, make(2), choose=None)
        assert len(asked) == 1
        assert tokens(game) == {TREASURE: 2}

    def test_with_no_other_creature_nothing_is_asked(self, pool):
        game, _ = board(pool, mine=(ESIX,))
        asked, _ = run(game, make(1))
        assert asked == []
        assert tokens(game) == {TREASURE: 1}


class TestWhichCreature:
    def test_the_source_itself_is_not_offered(self, pool):
        game, bears = board(pool)
        esix_oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == ESIX)
        asked, _ = run(game, make(1), choose=bears)
        offered = {opt.value for opt in asked[0].options}
        assert esix_oid not in offered and bears in offered

    def test_an_opponents_creature_may_be_chosen(self, pool):
        game, _ = board(pool, mine=(ESIX,), theirs=(BEARS,))
        theirs = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEARS)
        run(game, make(1), choose=theirs)
        assert tokens(game, 0) == {BEARS: 1}

    def test_a_token_is_copied_with_the_values_its_creator_set(self, pool):
        game, _ = board(pool, mine=(ESIX,))
        run(
            game,
            [{"op": "create_token", "token": SHARK, "power": {"const": 3},
              "toughness": {"const": 3}}],
        )
        (shark,) = [o for o in game.state.battlefield_objects(0) if o.def_id == SHARK]
        run(game, make(1), choose=shark.oid)
        copies = [o for o in game.state.battlefield_objects(0) if o.def_id == SHARK]
        assert len(copies) == 2
        assert all(o.copy_overrides == {"power": 3, "toughness": 3} for o in copies)


class TestUnderYourControl:
    def test_an_opponents_creation_asks_nothing(self, pool):
        game, _ = board(pool)
        asked, _ = run(game, make(2, controller="opponent"))
        assert asked == []
        assert tokens(game, 1) == {TREASURE: 2}


class TestTheControllersOrder:
    @pytest.mark.parametrize(
        "mine", [(ESIX, BEARS, DOUBLING_SEASON), (DOUBLING_SEASON, ESIX, BEARS)]
    )
    def test_beside_a_doubler_every_doubled_token_is_a_copy(self, pool, mine):
        game, bears = board(pool, mine=mine)
        run(game, make(1), choose=bears)
        assert tokens(game) == {BEARS: 2}


class TestWhatTheCreatingEffectSaid:
    def test_tapped_and_as_still_apply(self, pool):
        game, bears = board(pool)
        _, ctx = run(game, make(2, tapped=True, **{"as": "made"}), choose=bears)
        made = ctx.bindings["made"]
        assert len(made) == 2
        assert all(game.state.objects[oid].tapped for oid in made)
        assert all(game.state.objects[oid].def_id == BEARS for oid in made)

    def test_an_investigation_is_still_an_investigation(self, pool):
        game, bears = board(pool)
        mark = len(game.state.events)
        run(game, [{"op": "investigate"}], choose=bears)
        assert tokens(game) == {BEARS: 1}
        assert any(e.type == "investigated" for e in game.state.events[mark:])


class TestTheCardFileMustSayWhatItMeans:
    def test_it_compiles(self):
        with_cards(esix())

    def test_a_token_filter_is_refused(self):
        with pytest.raises(DslError, match="affects_token"):
            compile_card(CardModel.model_validate(esix(affects_token={"types": ["Creature"]})))

    def test_beside_another_mode_it_is_refused(self):
        with pytest.raises(DslError, match="takes one of"):
            compile_card(CardModel.model_validate(esix(token_multiplier=2)))

    def test_an_empty_selector_is_refused(self):
        spec = esix()
        spec["abilities"][0]["copy_instead"] = {}
        with pytest.raises(DslError, match="copy_instead"):
            compile_card(CardModel.model_validate(spec))

    def test_a_card_off_the_battlefield_is_refused(self):
        spec = esix()
        spec["abilities"][0]["copy_instead"] = {"types": ["Creature"], "zone": "graveyard"}
        with pytest.raises(DslError, match="battlefield"):
            compile_card(CardModel.model_validate(spec))

    def test_on_another_effect_it_is_refused(self):
        spec = esix(effect="replace_dies", destination="exile", affects={"types": ["Creature"]})
        with pytest.raises(DslError, match="only mean anything on a replace_token_creation"):
            compile_card(CardModel.model_validate(spec))
