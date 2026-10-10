"""Embalm: an ability activated from the graveyard, and a copy with an exception.

"Embalm {5}{W} ({5}{W}, Exile this card from your graveyard: Create a token
that's a copy of it, except it's a white Zombie Angel with no mana cost. Embalm
only as a sorcery.)" Angel of Sanctions is the shipped witness.

Two halves, and cycling had already paid for most of the first one.
`active_zones` is read on the activated branch, `legality._activate_zones` walks
zones other than the battlefield, and `Cost.exile_from_graveyard` and
`sorcery_speed_only` both already existed. What was left was adding the
graveyard to that walk and letting the loader's safety rule accept a second way
of satisfying itself.

**That safety rule is the interesting part.** An activated ability offered
outside the battlefield must have a cost that *removes its source from that
zone*, or it is an infinite engine — a card sitting in a zone whose ability
costs only mana could be activated again and again without ever leaving.
Cycling satisfies it by discarding itself; embalm satisfies it by exiling itself
from the graveyard. Both are checked, neither is optional.

The second half is the copy. A token copy in this engine is a token whose
`def_id` is the original's, which is exactly right — a copy copies the printed
card, not the counters and damage piled on it — but it leaves the printed
"except" clause with nowhere to live, because the token has no card of its own.
So the exception rides on the *object*, as `copy_overrides`, and is applied to
the printed face before any layer: it is part of what the token is, not an
effect on it, so an anthem afterwards should layer on top exactly as it would on
a real card.

What the tests pin is that the token is the right token. A plain copy is a
*black* Angel — Angel of Sanctions is `{3}{W}{W}` and white, so the colour
happens to survive here, but the Zombie type and the missing mana cost do not,
and neither shows on a board.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

ANGEL = "angel_of_sanctions"


def graveyard(builder, *, lands=7):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * lands)
        .graveyard(0, [ANGEL])
        .active(0)
        .max_turns(1)
        .build()
    )


def embalm_action(game):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == ANGEL
        ),
        None,
    )


def resolve(game) -> None:
    for _ in range(30):
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
            if choose is not None:
                game.apply(choose)
                continue
        if decision.kind is DecisionKind.PRIORITY and game.state.stack:
            game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
            continue
        return


def tokens(game) -> list[int]:
    return [o for o in game.state.battlefield if game.state.objects[o].is_token]


class TestActivatingFromTheGraveyard:
    def test_it_is_offered(self, builder):
        assert embalm_action(graveyard(builder)) is not None

    def test_it_is_not_offered_without_the_mana(self, builder):
        assert embalm_action(graveyard(builder, lands=2)) is None

    def test_it_leaves_the_graveyard(self, builder):
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        assert game.state.players[0].graveyard == [], (
            "the cost exiles it -- otherwise embalm could be activated forever"
        )

    def test_it_cannot_be_activated_twice(self, builder):
        game = graveyard(builder, lands=14)
        game.apply(embalm_action(game))
        resolve(game)
        assert embalm_action(game) is None, "the card is in exile now"


class TestTheToken:
    def test_one_is_made(self, builder):
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        assert len(tokens(game)) == 1

    def test_it_is_a_copy(self, builder):
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        c = chars(game.state, tokens(game)[0])
        assert (c.power, c.toughness) == (3, 4), "the printed body of the Angel"
        assert "Angel" in c.subtypes
        assert "flying" in c.keywords, "a copy keeps the printed abilities"

    def test_it_is_a_zombie_as_well(self, builder):
        """The "except" clause -- the half a plain copy would drop."""
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        c = chars(game.state, tokens(game)[0])
        assert "Zombie" in c.subtypes
        assert "Angel" in c.subtypes, "*added*, not replaced"

    def test_it_is_white(self, builder):
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        assert chars(game.state, tokens(game)[0]).colors == frozenset({"W"})

    def test_it_has_no_mana_cost(self, builder):
        game = graveyard(builder)
        game.apply(embalm_action(game))
        resolve(game)
        oid = tokens(game)[0]
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"mana_value_of": oid}) == 0, (
            "its def_id is the Angel's, so without the override it would still "
            "report mana value 5"
        )


def probe(**effect) -> dict:
    base = {
        "op": "copy_permanent",
        "objects": {"zone": "exile", "self_only": True},
        "except_": {"colors": ["W"], "add_subtypes": ["Zombie"]},
    }
    base.update(effect)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Embalm {1}",
        "mana_cost": "{2}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "activated",
                "text": "Embalm {1}",
                "active_zones": ["graveyard"],
                "cost": {
                    "mana": "{1}",
                    "exile_from_graveyard": {"self_only": True, "count": 1},
                },
                "effects": [base],
            }
        ],
    }


class TestTheLoader:
    def test_the_shipped_shape_loads(self):
        compile_card(CardModel.model_validate(probe()))

    def test_a_misspelled_exception_is_refused(self):
        """Silently dropped, the token would come back a plain copy."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(CardModel.model_validate(probe(except_={"subtypes": ["Zombie"]})))

    def test_an_unknown_colour_is_refused(self):
        with pytest.raises(DslError, match="unknown colour"):
            compile_card(CardModel.model_validate(probe(except_={"colors": ["Q"]})))

    def test_a_graveyard_ability_must_still_remove_its_source(self):
        """The infinite-engine guard, now satisfiable two ways.

        Cycling discards itself, embalm exiles itself from the graveyard. An
        ability that does neither could be activated forever.
        """
        payload = probe()
        payload["abilities"][0]["cost"] = {"mana": "{1}"}
        with pytest.raises(DslError, match="removes its source from that zone"):
            compile_card(CardModel.model_validate(payload))
