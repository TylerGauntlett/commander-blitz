"""Airbend: exile a pool, and hand each card back to *its owner* at a flat {2}.

    Airbend all other creatures. (Exile them. While each one is exiled, its
    owner may cast it for {2} rather than its mana cost.)

The reminder text is the whole mechanic, and it makes two claims the engine
could not make before -- one about *who* may cast, one about *what it costs*.

**Who.** `exile` with a `playable` permission is the near miss and writes
``obj.playable_by = ctx.controller`` (`effects/ops_removal.py`): one seat, the
resolving spell's. That is right for the impulse-draw family it was built for
and exactly wrong here, because airbend sweeps the *whole board* -- most of
what it exiles belongs to somebody else, and granting the permission to the
caster would let me cast my opponents' creatures. 108.3 makes ``owner`` the one
identity a card never loses, so the permission is written from the object, not
from the resolution, and a creature I had stolen goes back to the player who
brought it.

**What it costs.** No object could carry a price at all: `ObjectState` had
`playable_free`, `playable_any_color` and `playable_any_type`, and
`casting._cast_options` could pass `extra_generic` or `free` -- the printed
price or no price, never "{2} instead". A reduction cannot stand in for it at
any amount, because `cost_reduction.cost_reduction` clamps every reduction to the
*generic* part of a cost: a {G} creature "reduced" still owes its green pip,
and a {4}{U}{U} one still owes two blue. {2} is {2} for both.

The permission lasts "while each one is exiled" and so carries no clock: it
dies with `reset_permanent_state` as the card leaves exile, which is both what
the sentence says and what 400.7 would have said anyway.

Witness: Avatar's Wrath (`avatar_s_wrath` in `data/cards/auto/`), whose
first line this is. Without it the card exiles the board and gives it to the
wrong player at the wrong price.
"""

from __future__ import annotations

from automtg.engine.casting import _cast_actions
from automtg.engine.enums import ActionKind, Step

REVERSAL = "t_gale_reversal"  # {0} sorcery: airbend all creatures
SCATTER = "t_gale_scatter"  # {0} sorcery: plain `exile` + `playable` -- the near miss
YAK = "t_stone_yak"  # {G} 2/2 -- one green pip, and no seat here has green
DRAKE = "t_thunder_drake"  # {4}{U}{U} 3/3 -- six mana, two of them pips


def board(builder, *, spell=REVERSAL, p0_lands=2, p1_lands=2, drake_stolen=False):
    """p0 owns a Yak, p1 owns a Drake, and p0 holds one free sweeper.

    Two seats owning one creature each is the whole point of the position: a
    permission written to `ctx.controller` passes every test a one-sided board
    can ask.
    """
    game = (
        builder(players=2)
        .hand(0, [spell])
        .battlefield(0, [YAK] + ["plains"] * p0_lands)
        .battlefield(1, [DRAKE] + ["plains"] * p1_lands)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    if drake_stolen:
        # "…its **owner** may cast it", not its controller. The sharpest form
        # of the question: a creature p0 has taken control of is still p1's
        # card, and airbending it hands it back to p1.
        drake = next(
            o for o in game.state.battlefield if game.state.objects[o].def_id == DRAKE
        )
        game.state.objects[drake].controller = 0
        game.state.bump_chars()
    return game


def sweep(game, spell=REVERSAL):
    """Cast and resolve the sweeper from p0's hand."""
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == spell)
    cast = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid
    )
    game.apply(cast)
    # Nothing else is on the stack, so one pass from each seat resolves it.
    for _ in range(4):
        if not game.state.stack:
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    return game


def offered(game, pid, card_id):
    """Every cast line legality offers ``pid`` for ``card_id``, at sorcery speed.

    `_cast_actions` directly rather than `game.legal_actions()`, because the
    claim is about *two seats at once* and only one of them holds priority.
    """
    return [
        a
        for a in _cast_actions(game.state, pid, sorcery_speed=True)
        if game.state.objects[a.source].def_id == card_id
    ]


def exile_ids(game, pid):
    return [game.state.objects[o].def_id for o in game.state.players[pid].exile]


def only(game, card_id):
    return next(o for o, obj in game.state.objects.items() if obj.def_id == card_id)


def untapped_lands(game, pid):
    return sum(
        1 for o in game.state.battlefield_objects(pid) if o.def_id == "plains" and not o.tapped
    )


class TestThePermissionGoesToEachCardsOwner:
    """"…its **owner** may cast it", one grant per card and not one per spell."""

    def test_each_exiled_card_lands_in_its_owners_exile(self, builder):
        game = sweep(board(builder))
        assert exile_ids(game, 0) == [YAK]
        assert exile_ids(game, 1) == [DRAKE]

    def test_the_grant_names_the_owner_not_the_caster(self, builder):
        game = sweep(board(builder))
        assert game.state.objects[only(game, YAK)].playable_by == 0
        assert game.state.objects[only(game, DRAKE)].playable_by == 1

    def test_the_caster_is_not_offered_an_opponents_creature(self, builder):
        # The `ctx.controller` bug, stated: p0 swept the board and must not be
        # able to cast p1's Drake out of p1's exile.
        game = sweep(board(builder))
        assert offered(game, 0, DRAKE) == []

    def test_the_opponent_is_offered_their_own_creature(self, builder):
        game = sweep(board(builder))
        assert len(offered(game, 1, DRAKE)) == 1

    def test_the_opponent_is_not_offered_the_casters_creature(self, builder):
        game = sweep(board(builder))
        assert offered(game, 1, YAK) == []

    def test_a_stolen_creature_goes_back_to_the_player_who_brought_it(self, builder):
        # 108.3: control changes, ownership does not. p0 controls the Drake
        # when the sweeper resolves and still may not cast it.
        game = sweep(board(builder, drake_stolen=True))
        assert exile_ids(game, 1) == [DRAKE]
        assert game.state.objects[only(game, DRAKE)].playable_by == 1
        assert offered(game, 0, DRAKE) == []

    def test_plain_exile_grants_to_the_caster_instead(self, builder):
        # The near miss, measured rather than described: `exile` + `playable`
        # hands both cards to p0 and gives p1 nothing. That is a correct
        # impulse-draw and a wrong airbend.
        game = sweep(board(builder, spell=SCATTER), spell=SCATTER)
        assert game.state.objects[only(game, DRAKE)].playable_by == 0
        assert game.state.objects[only(game, YAK)].playable_by == 0


class TestThePriceIsAFlatTwoReplacingTheManaCost:
    """"…for {2} **rather than** its mana cost", not {2} off it."""

    def test_a_green_creature_is_castable_by_a_seat_with_no_green(self, builder):
        # The Yak costs {G} and p0 has two Plains. A discount of any size
        # leaves that pip owing, so this line exists only if the cost was
        # replaced outright.
        game = sweep(board(builder))
        assert len(offered(game, 0, YAK)) == 1

    def test_a_six_mana_creature_is_castable_off_two_lands(self, builder):
        game = sweep(board(builder))
        assert len(offered(game, 1, DRAKE)) == 1

    def test_the_price_is_stamped_on_the_card(self, builder):
        game = sweep(board(builder))
        assert game.state.objects[only(game, YAK)].playable_alt_cost == "{2}"
        assert game.state.objects[only(game, DRAKE)].playable_alt_cost == "{2}"

    def test_one_land_is_not_enough_and_two_are(self, builder):
        # The boundary: {2} is a real price, not a free cast. A seat with one
        # land is offered nothing.
        lean = sweep(board(builder, p0_lands=1))
        assert offered(lean, 0, YAK) == []
        rich = sweep(board(builder, p0_lands=2))
        assert len(offered(rich, 0, YAK)) == 1

    def test_casting_it_spends_exactly_two(self, builder):
        game = sweep(board(builder, p0_lands=3))
        game.apply(offered(game, 0, YAK)[0])
        assert YAK in [obj.def_id for obj in game.state.battlefield_objects(0)]
        assert untapped_lands(game, 0) == 1
        assert game.state.players[0].mana_pool.total() == 0

    def test_plain_exile_charges_the_printed_price_instead(self, builder):
        # The other half of the near miss. p0 holds Plains, so the Yak's {G}
        # and the Drake's {4}{U}{U} are both unpayable and neither line exists
        # -- which is what "the printed price" means here.
        game = sweep(board(builder, spell=SCATTER), spell=SCATTER)
        assert offered(game, 0, YAK) == []
        assert offered(game, 0, DRAKE) == []


class TestThePermissionLivesOnlyWhileTheCardIsExiled:
    """"**While each one is exiled**", which is also 400.7's answer."""

    def test_casting_it_clears_the_grant(self, builder):
        game = sweep(board(builder, p0_lands=3))
        game.apply(offered(game, 0, YAK)[0])
        yak = game.state.objects[only(game, YAK)]
        assert yak.playable_by is None
        assert yak.playable_alt_cost is None

    def test_the_grant_survives_the_turn_it_was_made_on(self, builder):
        # Not `this_turn`: the printed sentence has no clock on it at all, so a
        # card left in exile is still castable a turn later.
        from tests.conftest import pass_until

        game = sweep(board(builder))
        start = game.state.turn
        pass_until(game, lambda g: g.state.turn > start + 1)
        assert len(offered(game, 0, YAK)) == 1
