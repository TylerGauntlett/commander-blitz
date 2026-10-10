"""Summon: Esper Valigarmanda — casting somebody else's spell with the wrong mana.

    I — Exile an instant or sorcery card from each graveyard.
    II, III, IV — Add {R} for each lore counter on this Saga. You may cast an
    instant or sorcery card exiled with this Saga, and mana of any type can be
    spent to cast that spell.

Three things, and the chapter is only playable with all three.

**The link without the promise.** `until_leaves` was the only key that recorded
`exiled_by`, and it is the O-Ring name: it says the cards come back when the
permanent leaves. This Saga is sacrificed after its last chapter and takes cards
out of *every* graveyard at the table, so written that way it would read as
handing an opponent's instant back to them. `link` is the same record under the
neutral name, and it is only ever a record -- the return was always a separate
`leaves_battlefield` trigger on the card and never anything `exile` did.

**Where the permission has to reach.** Exile is kept per owner, so a card taken
from an opponent's graveyard sits in the *opponent's* exile, and legality walked
only the caster's. The flag is the permission, so widening the walk offers
nothing extra: nothing carries the flag that was not granted it.

**The colours.** Nothing in the engine relaxed a coloured pip. Every reduction
that exists -- `spell_cost_reduction`, convoke, delve, emerge -- is clamped to
the generic part precisely so it can never reach one, and `add_mana`'s "any
type" is about what a land *produces*. `ManaCost.as_any_type` sums the pips into
generic, which is the rule rather than a stand-in for it: a generic pip is the
one demand any mana already satisfies. `{C}` goes with them, since "any type"
names the colourless type too, and `X` does not, being a number rather than a
colour.

Read off the card and gated on the same turn the permission was granted, so it
expires with it: the caster's other spells that turn are paid for normally.

`t_strict_hoarder` is the counterfactual -- the same grant with the waiver
removed -- and the red spell is simply not on offer.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import only_oid

HOARDER = "t_hoarder"
STRICT = "t_strict_hoarder"
BOLT = "t_bolt"  # {R}


def board(builder, card: str = HOARDER, *, theirs=(BOLT,), mine=()):
    """White mana only, and a red card in the opponent's graveyard.

    The lands are Plains on purpose: a board that could pay {R} would prove
    nothing about whether the colour was waived.
    """
    return (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(0, ["plains"] * 4)
        .hand(0, ["forest"])
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .library(0, ["forest"] * 10)
        .build()
    )


def run(game, oid: int, index: int):
    """Drive one of the permanent's abilities directly, taking the first choice.

    Directly, because the printed trigger is *entering* and the printed
    permission is a chapter: this is about what they do, not about when.
    """
    state = game.state
    ctx = EffectContext(state=state, controller=0, source_oid=oid)
    gen = execute(ctx, state.card_of(state.objects[oid]).abilities[index].effects)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        send = [0]


def hoard(builder, card: str = HOARDER, **kwargs):
    game = board(builder, card, **kwargs)
    oid = only_oid(game, card)
    run(game, oid, 0)
    return game, oid


def castable(game):
    """Distinct *cards* on offer, not target permutations of them."""
    state = game.state
    return sorted(
        {
            state.card(a.source).id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
        }
    )


class TestTheLink:
    def test_the_exiled_card_remembers_who_took_it(self, builder):
        game, oid = hoard(builder)
        exiled = game.state.players[1].exile
        assert [game.state.card(o).id for o in exiled] == [BOLT]
        assert game.state.objects[exiled[0]].exiled_by == oid

    def test_it_is_taken_from_every_graveyard(self, builder):
        """"…from **each** graveyard", the caster's included."""
        game, _ = hoard(builder, mine=(BOLT,))
        assert len(game.state.players[0].exile) == 1
        assert len(game.state.players[1].exile) == 1

    def test_nothing_is_promised_back(self, builder):
        """`link` records and does nothing else -- the whole reason it is not
        spelled `until_leaves` on a card that is sacrificed after its last
        chapter."""
        game, oid = hoard(builder)
        exiled = game.state.players[1].exile[0]
        game.state.objects[oid].zone = Zone.GRAVEYARD
        assert exiled in game.state.players[1].exile


class TestThePermissionReachesTheOtherSeatsExile:
    def test_the_opponents_card_is_offered(self, builder):
        game, oid = hoard(builder)
        assert castable(game) == []
        run(game, oid, 1)
        assert castable(game) == [BOLT]


class TestTheColoursAreWaived:
    def test_without_the_waiver_it_is_not_offered(self, builder):
        """Same grant, one field different -- and {R} is unpayable on Plains."""
        game, oid = hoard(builder, STRICT)
        run(game, oid, 1)
        assert castable(game) == []

    def test_it_actually_resolves(self, builder):
        """Offered and then billed its printed cost is the failure mode: the
        spell goes on the stack and the payment quietly refuses."""
        game, oid = hoard(builder)
        run(game, oid, 1)
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
        game.apply(action)
        for _ in range(20):
            if not game.state.stack:
                break
            actions = game.legal_actions()
            if not actions:
                break
            game.apply(actions[0])
        assert [game.state.card(o).id for o in game.state.players[1].graveyard] == [BOLT]


class TestAsAnyType:
    def test_the_pips_become_generic(self):
        from commanderblitz.engine.mana import ManaCost

        relaxed = ManaCost.parse("{2}{U}{R}").as_any_type()
        assert relaxed.generic == 4
        assert not any(relaxed.colored)

    def test_the_colourless_pip_goes_too(self):
        """"any type" names the colourless type, which generic mana cannot
        otherwise pay."""
        from commanderblitz.engine.mana import ManaCost

        assert ManaCost.parse("{C}{C}").as_any_type().generic == 2

    def test_x_survives(self):
        """X is a number the caster chooses, not a colour."""
        from commanderblitz.engine.mana import ManaCost

        relaxed = ManaCost.parse("{X}{R}{R}").as_any_type()
        assert relaxed.x_count == 1
        assert relaxed.generic == 2

    def test_a_hybrid_pip_costs_what_it_did(self):
        from commanderblitz.engine.mana import ManaCost

        relaxed = ManaCost.parse("{2}{W/U}").as_any_type()
        assert relaxed.generic == 3
        assert relaxed.hybrid == ()

    def test_the_printed_cost_is_untouched(self):
        from commanderblitz.engine.mana import ManaCost

        assert ManaCost.parse("{2}{U}{R}").as_any_type().text == "{2}{U}{R}"


class TestTheLoaderGuards:
    def test_a_link_with_nothing_to_link_is_refused(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="'link' needs 'objects'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_link",
                        "name": "Test Bad Link",
                        "oracle_text": "Exile it.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "exile", "link": True}],
                    }
                ),
                source="test",
            )

    def test_a_grant_with_nothing_to_grant_on_is_refused(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="'grant_playable' needs 'objects'"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_grant",
                        "name": "Test Bad Grant",
                        "oracle_text": "You may cast it.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "grant_playable", "limit": 1}],
                    }
                ),
                source="test",
            )
