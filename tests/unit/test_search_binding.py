"""Fabled Passage: naming the card the search just found.

"{T}, Sacrifice this land: Search your library for a basic land card, put it
onto the battlefield tapped, then shuffle. **Then if you control four or more
lands, untap that land.**"

Rule 608.2 resolves an ability's effects in order, and "that land" is a
referent: it means the specific object the *first* sentence produced, not a
description that could match anything else. Nothing in the DSL could say it --
`search_library` moved cards and then forgot them -- so the closest expressible
card was "untap a tapped basic land you control", which would happily untap a
Forest tapped for mana three turns earlier. That is a strictly better land than
the one printed, and it would look completely ordinary on screen.

So the search now writes an `as` binding, joining the eight ops that already
record. The witness here is `t_fetch_and_untap`, which is Fabled Passage's
second sentence hung off an enters trigger so the position stays small; the
shipped card exercises the same code through an activated ability.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer, action_for_card


def board(builder, *, lands: int, tapped_decoys: int = 0):
    """`lands` untapped basics out, plus `tapped_decoys` already-tapped ones."""
    b = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .hand(0, ["t_fetch_and_untap"])
        .library(0, ["island"] * 20)
    )
    if tapped_decoys:
        b = b.battlefield(0, ["mountain"] * tapped_decoys, tapped=True)
    return b.build()


def resolve(game, *, take: bool = True) -> None:
    """Cast the enchantment and answer the search, taking one card or none."""
    game.apply(action_for_card(game, ActionKind.CAST, "t_fetch_and_untap"))
    picked = False
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
            )
            if take and not picked and choose is not None:
                picked = True
                game.apply(choose)
                continue
            done = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.FINISH_DECLARATION
                ),
                None,
            )
            game.apply(done or _default_answer(game, decision))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


def fetched_island(game):
    """The one Island that reached the battlefield."""
    return next(
        game.state.objects[oid]
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "island"
    )


class TestTheBindingNamesWhatWasFound:
    def test_the_fetched_land_untaps_when_the_condition_holds(self, builder):
        """Three lands out plus the one fetched is four: "that land" untaps."""
        game = board(builder, lands=3)
        resolve(game)
        land = fetched_island(game)
        assert land.zone is Zone.BATTLEFIELD
        assert not land.tapped, "the land the search found should have untapped"

    def test_it_stays_tapped_when_the_condition_fails(self, builder):
        """Two lands plus one fetched is three -- below the printed threshold."""
        game = board(builder, lands=2)
        resolve(game)
        assert fetched_island(game).tapped, "no untap below four lands"

    def test_the_binding_does_not_reach_other_tapped_lands(self, builder):
        """The whole point. A filter for "a tapped basic" would free these too."""
        game = board(builder, lands=3, tapped_decoys=2)
        resolve(game)
        assert not fetched_island(game).tapped
        decoys = [
            game.state.objects[oid]
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == "mountain"
        ]
        assert len(decoys) == 2
        assert all(d.tapped for d in decoys), (
            "only the searched card is 'that land' -- a land tapped for mana "
            "earlier in the turn must stay tapped"
        )


class TestTheEmptySearch:
    def test_finding_nothing_binds_nothing_rather_than_going_stale(self, builder):
        """Declining the search must not leave a name pointing at old objects."""
        game = board(builder, lands=3)
        resolve(game, take=False)
        islands = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == "island"
        ]
        assert islands == [], "nothing was taken"
        # The `if` still ran -- three Forests is below four anyway, but the point
        # is that it resolved against an empty binding without raising.
        assert not game.over
