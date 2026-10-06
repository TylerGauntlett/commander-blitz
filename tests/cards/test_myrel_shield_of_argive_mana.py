"""The Myrel deck's mana base, its rocks and its gear -- card by card, doing what
it prints.

Every card here cleared the six authoring gates, and this is the group where that
proves the least. Gate 5 casts a card **once** into one fixed sandbox and reads
the board, and its two documented limits take this group apart:

- **It never activates an ability.** Every mana ability, every fetch, every
  Equip, every "{T}: ..." land below got no behavioural check at all. The recorded
  expectation for Sol Ring, Rogue's Passage, Windbrisk Heights and Worn Powerstone
  is `{"zone": "battlefield"}` -- it exists, and that is the whole of what anybody
  knew.
- **A trigger that never fires cannot be asserted.** Nothing in the sandbox
  attacks, draws a second card, or spends a particular land's mana on a
  particular spell, so Windbrisk Heights' unlock, Gleaming Splendor's Treasure
  and Path of Ancestry's scry were all unobserved.

And this is the group whose defects are hardest to see from the board: a land
generated as an inert permanent leaves a deck that looks like 36 lands and plays
like 30. So each class below asserts the printed sentence *and* the near miss --
the sentence that would be true of the card mis-written. For a mana base the near
misses are almost all **quantities and conditions**, which a test that merely
shows mana appearing will not catch:

- how much, and of what: Sol Ring is two generic and not two white, Mind Stone is
  one and not two, Pearl Medallion reduces *white* spells and cannot eat a
  coloured pip;
- enters tapped, and the condition on it, asserted on **both** sides -- ten cards
  on this branch turned out to carry a mis-written flag;
- activation costs and restrictions, measured at the boundary rather than on a
  board that could pay anything;
- fetches: which zone the card came out of, how many, and whether it arrives
  tapped. Library size is asserted beside the battlefield, or a fetch that
  conjures a land from nowhere passes.

One thing is **not** asserted here:

- Archaeomancer's Map's second sentence (the land-drop catch-up) is already
  pinned in `tests/cards/test_bard_king_of_dale_deck.py::TestArchaeomancersMap`,
  so only its enters-trigger is here.

Skipped as already covered: nothing else. `sol_ring`, `mind_stone`,
`commanders_sphere` and `wayfarers_bauble` are hand-written cards with **no**
expectation entry at all; what `tests/` had for them was a doubler's arithmetic
(`test_the_ur_dragon_mana.py`), an action-list shape (`test_manual_mana.py`) and
a capability on a test-only card. None of those is the shipped card making its
printed mana.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars, prevents_all_damage
from automtg.engine.costs import available_mana, cost_reduction, mana_options_of
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.mana import SYMBOLS
from automtg.engine.targeting import can_be_targeted
from tests.conftest import _default_answer, oids_of, only_oid, pass_until

# A castable instant in a seat's hand, and it is load bearing rather than
# scenery. `Game._should_auto_pass` treats "Pass, or add some mana" as no
# decision at all, so a seat whose only option is to pass rolls whole turns
# forward inside one `apply` -- which walks past the combat step half of these
# tests have to be read in. `t_plain_instant` is {W}: a Plains beside it is the
# cheapest way to keep a window open.
ANCHOR = "t_plain_instant"  # {W} instant, gain 1 life
PLAINS = "plains"
BEAR = "t_bear"  # a vanilla 2/2, and not a Soldier
WALL = "t_wall"  # a 0/4 defender, for the blocks that must be refused

# The commander, in the command zone. Mono-white, and a Human **Soldier** -- both
# halves matter: the colour identity is what Path of Ancestry narrows to, and the
# creature type is what its scry trigger compares against.
MYREL = "myrel_shield_of_argive"

# Deck cards used as the spells the mana does or does not buy, and as the
# creatures the gear is strapped to.
SOLDIER = "recruitment_officer"  # {W} 2/1 Human Soldier -- one toughness, on purpose
CAT = "ocelot_pride"  # {W} Cat: a creature spell sharing no type with Myrel
WHITE_ONE = "soul_warden"  # {W} 1/1
WHITE_TWO = "ballyrush_banneret"  # {1}{W} -- the boundary Pearl Medallion moves
COLOURLESS_TWO = "mind_stone"  # {2} artifact: a spell that is not a white spell
REMOVAL = "swords_to_plowshares"  # {W} instant -- a white *noncreature* spell
HIDDEN = "moonshaker_cavalry"  # {5}{W}{W}{W}: unpayable, so Windbrisk's "free" shows
DRAW_TWO = "divination"  # {2}{U} sorcery, "Draw two cards."


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def acts(game, oid: int, index: int | None = None) -> list:
    """Every ACTIVATE row legality offers for this permanent right now.

    A tap-only mana ability never appears here -- mana payment is the solver's,
    not the action list's -- so an empty list means "no *non*-mana ability", and
    the mana abilities are read through `mana_options_of` instead.
    """
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def resolve(game, *, take: int = 0, limit: int = 200) -> None:
    """Answer decisions until nothing is resolving.

    ``take`` objects are chosen at each choose-objects prompt before it is closed,
    and every "you may" is answered yes -- which is what a player who activated
    the ability meant. Prompts past ``take`` are finished empty.
    """
    taken = 0
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        if (
            not game.state.stack
            and not game.state.pending_triggers
            and decision.kind is DecisionKind.PRIORITY
        ):
            return
        if decision.kind is DecisionKind.MAY:
            yes = next((a for a in game.legal_actions() if a.kind is ActionKind.YES), None)
            if yes is not None:
                game.apply(yes)
                continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            chooses = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            if chooses and taken < take:
                taken += 1
                game.apply(chooses[0])
                continue
            finish = [a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION]
            if finish:
                game.apply(finish[0])
                continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("resolve did not settle")


def play_land(game, card_id: str) -> int:
    """Play ``card_id`` from hand and hand back the oid that arrived.

    Not `only_oid`: several of these tests stand a land up beside three more of
    the same card, and the assertion is about the copy that just entered.
    """
    before = {obj.oid for obj in game.state.battlefield_objects(0)}
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    return next(obj.oid for obj in game.state.battlefield_objects(0) if obj.oid not in before)


def cast(game, card_id: str, pid: int = 0, *, take: int = 0) -> int:
    """Cast ``card_id`` from ``pid``'s hand, let it resolve, return its oid."""
    pass_until(
        game,
        lambda g: (
            g.pending() is not None
            and g.pending().player == pid
            and any(
                a.kind is ActionKind.CAST
                and a.source is not None
                and g.state.objects[a.source].def_id == card_id
                for a in g.legal_actions()
            )
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    resolve(game, take=take)
    return action.source


def castable(game) -> set[str]:
    """The def_ids this seat may cast right now."""
    return {
        game.state.objects[a.source].def_id
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.source is not None
    }


def mana_ability_of(game, oid: int, index: int = 0):
    """The ``index``-th *mana* ability of the permanent at ``oid``.

    By position among the mana abilities, not among all of them: Windbrisk
    Heights' first ability is a hideaway trigger and Idyllic Grange's second is a
    targeted one.
    """
    return [a for a in game.state.card(oid).abilities if a.is_mana_ability][index]


def offered_symbols(game, oid: int, index: int = 0) -> set[str]:
    """Every symbol this permanent's mana ability offers on this board, now."""
    ability = mana_ability_of(game, oid, index)
    return {
        SYMBOLS[i]
        for option in mana_options_of(game.state, oid, ability)
        for i, count in enumerate(option)
        if count
    }


def offered_amount(game, oid: int, index: int = 0) -> int:
    """How much mana the one option this ability offers actually makes."""
    ability = mana_ability_of(game, oid, index)
    options = mana_options_of(game.state, oid, ability)
    assert len(options) == 1, f"{len(options)} options; the amount is not a single number"
    return sum(options[0])


def library(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


def hand_ids(game, pid: int = 0) -> list[str]:
    return sorted(game.state.objects[oid].def_id for oid in game.state.players[pid].hand)


def tokens(game, pid: int = 0) -> list:
    return [obj for obj in game.state.battlefield_objects(pid) if obj.is_token]


def to_declaration(game, kind: DecisionKind) -> None:
    """Walk to **this** turn's declare-attackers or declare-blockers decision.

    The turn is asserted, not assumed. Without it a creature that could not act
    this turn simply waits for the next such step two turns later, by which time
    summoning sickness and every `this_turn` effect have gone -- and both halves
    of an equipment test look alike.
    """
    turn = game.state.turn
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is kind)
    assert game.state.turn == turn, "walked past the turn under test"


def attack_with(game, *oids: int) -> None:
    for oid in oids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == "player" for t in a.targets)
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def blocks_offered(game) -> list[tuple[int, int]]:
    return sorted(
        (a.source, a.targets[0].id)
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_BLOCKER and a.source is not None
    )


def keywords_of(game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def scries(game, mark: int) -> list[dict]:
    return [e.data for e in game.state.events[mark:] if e.type == "scry"]


# ----------------------------------------------------------------------
# the lands
# ----------------------------------------------------------------------


class TestCastleArdenvale:
    """ "This land enters tapped unless you control a Plains." / "{T}: Add {W}." /
    "{2}{W}{W}, {T}: Create a 1/1 white Human creature token."

    Gate 5's expectation is `{"battlefield_count": 33, "zone": "battlefield"}`,
    which is every word of this untested: it does not record the tapped state, it
    never taps the land, and it never pays four mana for anything.
    """

    def test_it_enters_tapped_on_an_empty_board(self, builder):
        game = builder(players=2).hand(0, ["castle_ardenvale"]).build()
        assert game.state.objects[play_land(game, "castle_ardenvale")].tapped

    def test_a_plains_and_it_enters_untapped(self, builder):
        """The other side of the condition, and the reason the card is played."""
        game = builder(players=2).battlefield(0, [PLAINS]).hand(0, ["castle_ardenvale"]).build()
        assert not game.state.objects[play_land(game, "castle_ardenvale")].tapped

    def test_a_nonbasic_plains_counts(self, builder):
        """ "…you control a **Plains**", the subtype, not the basic land.

        Idyllic Grange is this deck's own nonbasic Plains, so the contrast is
        played rather than claimed: a condition written on `supertypes: ["Basic"]`
        reads this board as empty and the Castle arrives tapped.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["idyllic_grange"])
            .hand(0, ["castle_ardenvale"])
            .build()
        )
        assert not game.state.objects[play_land(game, "castle_ardenvale")].tapped

    def test_it_taps_for_white_and_not_colourless(self, builder):
        game = builder(players=2).battlefield(0, ["castle_ardenvale"]).build(advance=False)
        castle = only_oid(game, "castle_ardenvale", 0)
        assert offered_symbols(game, castle) == {"W"}
        assert offered_amount(game, castle) == 1

    def board(self, builder, plains: int):
        """The Castle beside ``plains`` untapped Plains, in a main phase.

        The Castle's own `{T}` is spent by the ability, so it cannot help pay for
        it: the four mana have to come from somewhere else, which is what makes
        three Plains the honest boundary.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["castle_ardenvale", *[PLAINS] * plains])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "castle_ardenvale", 0)

    def test_the_token_costs_four_other_mana(self, builder):
        game, castle = self.board(builder, 3)
        assert not acts(game, castle), "{2}{W}{W} off three Plains"

    def test_four_other_mana_and_it_is_offered(self, builder):
        """The control, so the row above measures the price and not the wiring."""
        game, castle = self.board(builder, 4)
        assert [a.ability_index for a in acts(game, castle)] == [1]

    def test_the_token_is_a_one_one_white_human(self, builder):
        game, castle = self.board(builder, 4)
        game.apply(acts(game, castle, 1)[0])
        resolve(game)

        [token] = tokens(game)
        c = chars(game.state, token.oid)
        assert (c.power, c.toughness) == (1, 1)
        assert c.colors == frozenset({"W"})
        assert "Human" in c.subtypes

    def test_the_token_is_not_a_soldier(self, builder):
        """The near miss that matters in *this* deck and nowhere else.

        Myrel counts Soldiers, Valiant Veteran and Daru Warchief pump Soldiers,
        and the Castle prints Human. A token typed Soldier by mistake is a
        strictly better card here and would look right on any other board.
        """
        game, castle = self.board(builder, 4)
        game.apply(acts(game, castle, 1)[0])
        resolve(game)

        [token] = tokens(game)
        assert "Soldier" not in chars(game.state, token.oid).subtypes

    def test_making_the_token_taps_the_land(self, builder):
        """The `{T}` in the cost. Without it the Castle makes a token *and* a
        white mana every turn."""
        game, castle = self.board(builder, 4)
        game.apply(acts(game, castle, 1)[0])
        resolve(game)

        assert game.state.objects[castle].tapped


class TestWindbriskHeights:
    """ "Hideaway 4" / "This land enters tapped." / "{T}: Add {W}." / "{W}, {T}: You
    may play the exiled card without paying its mana cost if you attacked with
    three or more creatures this turn."

    The recorded expectation is `{"zone": "battlefield"}`, and that is the whole
    of what the gates saw: the hideaway is an enters-trigger whose result lives in
    exile rather than on the board, and the unlock is an activated ability behind
    a combat condition the sandbox never meets.
    """

    def position(self, builder, *, attackers: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, *[BEAR] * attackers])
            .battlefield(1, [PLAINS])
            .hand(0, ["windbrisk_heights", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, [HIDDEN, *[PLAINS] * 30])
            .library(1, ["island"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        heights = play_land(game, "windbrisk_heights")
        # The hideaway choice is asked from inside the enters-trigger's
        # resolution; how many priority windows that takes is not the test's
        # business, so it is driven as a scan for the exile appearing.
        for _ in range(120):
            if game.state.players[0].exile:
                break
            decision = game.pending()
            if decision is None:
                break
            if decision.context.get("purpose") == "hideaway":
                chooses = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
                if chooses:
                    game.apply(chooses[0])
                    continue
            game.apply(_default_answer(game, decision))
        [exiled] = game.state.players[0].exile
        return game, heights, exiled

    def test_it_enters_tapped(self, builder):
        game, heights, _ = self.position(builder)
        assert game.state.objects[heights].tapped

    def test_hideaway_exiles_exactly_one_of_the_four(self, builder):
        """Four looked at, one exiled, three to the bottom -- so the library is
        one card shorter and not four. A hideaway that exiled the lot, or that
        drew instead of bottoming, passes any assertion about the exile alone."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .hand(0, ["windbrisk_heights", ANCHOR])
            .library(0, [HIDDEN, *[PLAINS] * 30])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = library(game)
        heights = play_land(game, "windbrisk_heights")
        for _ in range(120):
            if game.state.players[0].exile:
                break
            decision = game.pending()
            if decision is None:
                break
            if decision.context.get("purpose") == "hideaway":
                chooses = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
                if chooses:
                    game.apply(chooses[0])
                    continue
            game.apply(_default_answer(game, decision))

        assert len(game.state.players[0].exile) == 1
        assert before - library(game) == 1
        assert game.state.objects[game.state.players[0].exile[0]].exiled_by == heights

    def test_the_exiled_card_is_face_down(self, builder):
        """ "…exile one **face down**", which is `revealed_to` and not a 2/2
        shell: only its controller may look."""
        game, _heights, exiled = self.position(builder)
        assert game.state.objects[exiled].revealed_to == {0}

    def test_it_taps_for_white(self, builder):
        game, heights, _ = self.position(builder)
        assert offered_symbols(game, heights) == {"W"}

    def to_my_next_main(self, game) -> None:
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn + 1 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        assert game.state.active_player == 0

    def test_the_unlock_is_offered_before_any_attack(self, builder):
        """The condition is on the *resolution*, not on the activation (the
        printed card lets you waste the mana), so this is the premise for the two
        rows below rather than a claim about the card."""
        game, heights, _ = self.position(builder, attackers=3)
        self.to_my_next_main(game)
        assert not game.state.objects[heights].tapped, "it untapped"
        assert [a.ability_index for a in acts(game, heights)] == [2]

    def test_without_three_attackers_the_card_stays_in_exile(self, builder):
        """The condition, and the near miss is dropping it altogether: a
        Windbrisk Heights that always unlocks is a free eight-drop on turn four.
        """
        game, heights, exiled = self.position(builder, attackers=3)
        self.to_my_next_main(game)
        game.apply(acts(game, heights, 2)[0])
        resolve(game)

        assert game.state.objects[exiled].zone is Zone.EXILE

    def test_three_attackers_play_it_without_paying_its_mana_cost(self, builder):
        """The card. Moonshaker Cavalry is {5}{W}{W}{W} and the board is one
        Plains and the land itself, so nothing here could have *paid* for it --
        which is how "without paying its mana cost" is pinned at the same time.
        """
        game, heights, exiled = self.position(builder, attackers=3)
        turn = game.state.turn
        pass_until(
            game,
            lambda g: (
                g.state.turn > turn
                and g.state.active_player == 0
                and g.pending() is not None
                and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
            ),
        )
        attack_with(game, *oids_of(game, BEAR, 0))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert len(game.state.turn_ledger.creatures_attacked[0]) == 3, "the premise"

        game.apply(acts(game, heights, 2)[0])
        resolve(game)

        assert game.state.objects[exiled].zone is Zone.BATTLEFIELD
        assert game.state.objects[exiled].def_id == HIDDEN


class TestIdyllicGrange:
    """ "({T}: Add {W}.)" / "This land enters tapped unless you control three or
    more other Plains." / "When this land enters untapped, put a +1/+1 counter on
    target creature you control."

    Gate 5 recorded `{"battlefield_count": 33, "hand_size": {"0": 1}, "zone":
    "battlefield"}` -- no tapped state, and no counter anywhere, so whether the
    trigger fired at all is not in the record.
    """

    def played(self, builder, board, *, creature: str | None = BEAR, theirs=()):
        game = (
            builder(players=2)
            .battlefield(0, [*board, *([creature] if creature else [])])
            .battlefield(1, list(theirs))
            .hand(0, ["idyllic_grange"])
            .build()
        )
        oid = play_land(game, "idyllic_grange")
        resolve(game)
        return game, oid

    def test_two_other_plains_is_not_enough(self, builder):
        game, grange = self.played(builder, [PLAINS] * 2)
        assert game.state.objects[grange].tapped

    def test_three_other_plains_is_the_boundary(self, builder):
        game, grange = self.played(builder, [PLAINS] * 3)
        assert not game.state.objects[grange].tapped

    def test_it_does_not_count_itself(self, builder):
        """The Grange **is** a Plains, so `exclude_self` is the whole difference
        between "three other" and "three": without it two Plains plus itself
        reads as three and the land is untapped a turn early, every game."""
        game, grange = self.played(builder, [PLAINS] * 2)
        assert game.state.objects[grange].tapped, "two others and itself is not three others"

    def test_three_other_nonbasic_plains_count_too(self, builder):
        """The count is of the subtype, not of the basic land."""
        game, grange = self.played(builder, ["idyllic_grange"] * 3)
        assert not game.state.objects[grange].tapped

    def test_entering_untapped_puts_a_counter_on_your_creature(self, builder):
        game, _grange = self.played(builder, [PLAINS] * 3)
        assert game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1") == 1

    def test_entering_tapped_puts_none(self, builder):
        """The rider is conditioned on the same clause the tapped state is, and
        the two are read separately. A trigger written on a bare `self_enters`
        fires on the tapped half too and hands the deck a counter it never had.
        """
        game, grange = self.played(builder, [PLAINS] * 2)
        assert game.state.objects[grange].tapped, "the premise"
        assert not game.state.objects[only_oid(game, BEAR, 0)].counters.get("+1/+1")

    def test_it_cannot_reach_an_opponents_creature(self, builder):
        """ "…target creature **you control**"."""
        game, _grange = self.played(builder, [PLAINS] * 3, creature=None, theirs=[BEAR])
        assert not game.state.objects[only_oid(game, BEAR, 1)].counters.get("+1/+1")

    def test_it_taps_for_white(self, builder):
        game = builder(players=2).battlefield(0, ["idyllic_grange"]).build(advance=False)
        assert offered_symbols(game, only_oid(game, "idyllic_grange", 0)) == {"W"}


class TestSecludedSteppe:
    """ "This land enters tapped." / "{T}: Add {W}." / "Cycling {W}"

    The recorded expectation is `{"zone": "battlefield"}`. Cycling is an activated
    ability of a card **in hand**, which is a zone the behaviour gate never
    activates anything from -- so the second half of this card was entirely
    unobserved.
    """

    def test_it_enters_tapped(self, builder):
        game = builder(players=2).hand(0, ["secluded_steppe"]).build()
        assert game.state.objects[play_land(game, "secluded_steppe")].tapped

    def test_it_taps_for_white(self, builder):
        game = builder(players=2).battlefield(0, ["secluded_steppe"]).build(advance=False)
        assert offered_symbols(game, only_oid(game, "secluded_steppe", 0)) == {"W"}

    def hand_position(self, builder, board):
        game = (
            builder(players=2)
            .battlefield(0, list(board))
            .hand(0, ["secluded_steppe"])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        steppe = game.state.players[0].hand[0]
        return (
            game,
            steppe,
            [
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == steppe
            ],
        )

    def test_cycling_draws_one_and_bins_the_land(self, builder):
        game, steppe, offered = self.hand_position(builder, [PLAINS])
        assert offered, "cycling is offered from hand"
        before = library(game)
        game.apply(offered[0])
        resolve(game)

        assert before - library(game) == 1, "draw a card -- one, not two"
        assert game.state.objects[steppe].zone is Zone.GRAVEYARD, "Discard this card"

    def test_cycling_needs_a_white_source(self, builder):
        """ "Cycling **{W}**". A Sol Ring is two mana and pays none of it, which
        is the difference between the printed cost and a generic one."""
        _game, _steppe, offered = self.hand_position(builder, ["sol_ring"])
        assert offered == []

    def test_and_with_no_mana_at_all_it_is_not_offered(self, builder):
        _game, _steppe, offered = self.hand_position(builder, [])
        assert offered == []

    def test_cycling_is_not_offered_from_the_battlefield(self, builder):
        """`active_zones: ["hand"]`. A land on the table cannot be discarded, and
        an ability offered there would let the Steppe cycle itself off the
        board."""
        game = (
            builder(players=2)
            .battlefield(0, ["secluded_steppe", PLAINS])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        assert acts(game, only_oid(game, "secluded_steppe", 0)) == []


class TestMyriadLandscape:
    """ "This land enters tapped." / "{T}: Add {C}." / "{2}, {T}, Sacrifice this
    land: Search your library for up to two basic land cards that share a land
    type, put them onto the battlefield tapped, then shuffle."

    Gate 5 got as far as `{"library_size": {"0": 40}, ...}` -- an untouched
    library, which is a statement that the card did not *misfire* on entry. The
    fetch itself was never run.
    """

    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["myriad_landscape", PLAINS, PLAINS])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "myriad_landscape", 0)

    def test_it_enters_tapped(self, builder):
        game = builder(players=2).hand(0, ["myriad_landscape"]).build()
        assert game.state.objects[play_land(game, "myriad_landscape")].tapped

    def test_it_taps_for_colourless_and_not_white(self, builder):
        """A colourless land in a mono-white deck, and the deck notices: this
        mana cannot pay a {W} pip. Written as `{W}` it is a better card."""
        game, land = self.position(builder)
        assert offered_symbols(game, land) == {"C"}

    def fetched(self, builder):
        game, land = self.position(builder)
        before = library(game)
        standing = {obj.oid for obj in game.state.battlefield_objects(0)}
        game.apply(acts(game, land, 1)[0])
        resolve(game, take=2)
        arrived = [obj for obj in game.state.battlefield_objects(0) if obj.oid not in standing]
        return game, land, before, arrived

    def test_it_fetches_two_lands(self, builder):
        game, _land, _before, arrived = self.fetched(builder)
        assert [obj.def_id for obj in arrived] == [PLAINS, PLAINS]
        assert len(oids_of(game, PLAINS, 0)) == 4, "the two already down, plus two"

    def test_they_come_out_of_the_library(self, builder):
        """Two off the top of the library and not two out of nowhere. Without
        this the identical board is reached by a fetch that conjures lands, and
        a 99-card deck quietly becomes a 101-card one."""
        game, _land, before, _arrived = self.fetched(builder)
        assert before - library(game) == 2

    def test_they_arrive_tapped(self, builder):
        _game, _land, _before, arrived = self.fetched(builder)
        assert [obj.tapped for obj in arrived] == [True, True]

    def test_it_sacrifices_itself(self, builder):
        game, land, _before, _arrived = self.fetched(builder)
        assert game.state.objects[land].zone is Zone.GRAVEYARD


class TestTerrainGenerator:
    """ "{T}: Add {C}." / "{2}, {T}: You may put a basic land card from your hand
    onto the battlefield tapped."

    The one land in this deck's utility cycle that does **not** enter tapped, and
    the gate's `{"battlefield_count": 33, "zone": "battlefield"}` does not say so.
    Its ability is the near miss of Myriad Landscape's: same shape, different
    zone, and it does not sacrifice itself.
    """

    def test_it_enters_untapped(self, builder):
        """Asserted rather than assumed: a spurious `self_enters_tapped` is
        invisible on a card whose neighbours all carry one, and this branch
        already found ten of them."""
        game = builder(players=2).hand(0, ["terrain_generator"]).build()
        assert not game.state.objects[play_land(game, "terrain_generator")].tapped

    def test_it_taps_for_colourless(self, builder):
        game = builder(players=2).battlefield(0, ["terrain_generator"]).build(advance=False)
        assert offered_symbols(game, only_oid(game, "terrain_generator", 0)) == {"C"}

    def position(self, builder, hand):
        game = (
            builder(players=2)
            .battlefield(0, ["terrain_generator", *[PLAINS] * 3])
            .hand(0, [*hand, ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "terrain_generator", 0)

    def put(self, builder, hand):
        game, generator = self.position(builder, hand)
        before = {obj.oid for obj in game.state.battlefield_objects(0)}
        lands = library(game)
        game.apply(acts(game, generator, 1)[0])
        resolve(game, take=1)
        arrived = [obj for obj in game.state.battlefield_objects(0) if obj.oid not in before]
        return game, arrived, lands

    def test_the_land_comes_out_of_your_hand(self, builder):
        game, arrived, lands = self.put(builder, [PLAINS])
        assert [obj.def_id for obj in arrived] == [PLAINS]
        assert library(game) == lands, "out of hand -- the library is untouched"
        assert hand_ids(game) == [ANCHOR], "and the Plains left the hand"

    def test_it_arrives_tapped(self, builder):
        _game, arrived, _lands = self.put(builder, [PLAINS])
        assert arrived[0].tapped

    def test_it_does_not_use_your_land_drop(self, builder):
        """ "**Put**", not "play". A version that spent the land drop is the same
        card as playing the Plains, and the Generator would do nothing at all."""
        game, _arrived, _lands = self.put(builder, [PLAINS])
        assert game.state.players[0].lands_played == 0

    def test_a_nonbasic_land_in_hand_is_not_eligible(self, builder):
        """ "a **basic** land card". Rogue's Passage is a land in hand and stays
        there -- which is also why the ability asks nothing on this board."""
        game, arrived, _lands = self.put(builder, ["rogue_s_passage"])
        assert arrived == []
        assert "rogue_s_passage" in hand_ids(game)


class TestPathOfAncestry:
    """ "This land enters tapped." / "{T}: Add one mana of any color in your
    commander's color identity. When that mana is spent to cast a creature spell
    that shares a creature type with your commander, scry 1."

    Two different sentences and the gate reached neither: the expectation is
    `{"zone": "battlefield"}`, the sandbox has no commander to narrow the colour
    against, and it never spends a particular land's mana on a particular spell.
    """

    def position(self, builder, hand, *, tapped: bool = False, lands=()):
        game = (
            builder(players=2)
            .battlefield(0, ["path_of_ancestry", *lands])
            .battlefield(1, [BEAR])
            .hand(0, list(hand))
            .library(0, [PLAINS] * 20)
            .commander(0, [MYREL])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        path = only_oid(game, "path_of_ancestry", 0)
        if tapped:
            game.state.objects[path].tapped = True
            game.state.bump_chars()
        return game, path

    def test_it_enters_tapped(self, builder):
        game = builder(players=2).commander(0, [MYREL]).hand(0, ["path_of_ancestry"]).build()
        assert game.state.objects[play_land(game, "path_of_ancestry")].tapped

    def test_it_taps_for_the_commanders_colour_only(self, builder):
        """Myrel is mono-white, so this land makes {W} and nothing else. Five
        fixed modes -- the obvious spelling -- is a strictly better card: it pays
        for spells the printed land cannot."""
        game, path = self.position(builder, [])
        assert offered_symbols(game, path) == {"W"}

    def test_it_is_not_five_colours(self, builder):
        game, path = self.position(builder, [])
        assert len(offered_symbols(game, path)) == 1

    def scried(self, builder, spell: str, **kwargs) -> list[int]:
        """How many cards each scry this cast produced looked at.

        `looked` rather than `bottomed`: whether the card goes to the bottom is
        the player's choice, and "scry 1" is the depth.
        """
        game, _path = self.position(builder, [spell], **kwargs)
        mark = len(game.state.events)
        cast(game, spell)
        return [e["looked"] for e in scries(game, mark)]

    def test_a_soldier_spell_off_its_mana_scries(self, builder):
        """The card. Recruitment Officer is a Human **Soldier** and Myrel is a
        Human Soldier, so both halves of the clause hold."""
        assert self.scried(builder, SOLDIER) == [1], "scry 1, once"

    def test_a_creature_sharing_no_type_does_not(self, builder):
        """ "…that **shares a creature type** with your commander." Ocelot Pride
        is a Cat, is in this deck, and is the witness that the clause is read: a
        trigger written on `types: ["Creature"]` alone scries off every creature
        in the deck."""
        assert self.scried(builder, CAT) == []

    def test_a_white_noncreature_spell_does_not(self, builder):
        """ "…to cast a **creature** spell". Swords to Plowshares is {W} and is
        cast off the same land."""
        assert self.scried(builder, REMOVAL) == []

    def test_a_soldier_paid_for_elsewhere_does_not(self, builder):
        """ "When **that mana** is spent." A bare `spell_cast` trigger is a
        strictly better card -- it would scry off Soldiers cast entirely off
        Plains, which in a deck with 27 of them is every Soldier."""
        assert self.scried(builder, SOLDIER, tapped=True, lands=[PLAINS]) == []


class TestRoguesPassage:
    """ "{T}: Add {C}." / "{4}, {T}: Target creature can't be blocked this turn."

    The expectation is `{"zone": "battlefield"}`. `tests/unit/combat/test_unblockable.py`
    pins the capability on a test-only land called `t_passage`; the shipped card's
    price, its targeting and its colourless mana are new here.
    """

    def board(self, builder, plains: int, *, theirs=(WALL,)):
        game = (
            builder(players=2)
            .battlefield(0, ["rogue_s_passage", *[PLAINS] * plains, BEAR])
            .battlefield(1, [*theirs, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "rogue_s_passage", 0)

    def test_it_enters_untapped(self, builder):
        game = builder(players=2).hand(0, ["rogue_s_passage"]).build()
        assert not game.state.objects[play_land(game, "rogue_s_passage")].tapped

    def test_it_taps_for_colourless(self, builder):
        game, passage = self.board(builder, 4)
        assert offered_symbols(game, passage) == {"C"}
        assert offered_amount(game, passage) == 1

    def test_three_other_mana_is_not_enough(self, builder):
        """ "{4}". The land taps itself, so it cannot contribute -- which makes
        three Plains the boundary and not four."""
        game, passage = self.board(builder, 3)
        assert acts(game, passage, 1) == []

    def test_four_other_mana_and_it_is_offered(self, builder):
        game, passage = self.board(builder, 4)
        assert len(acts(game, passage, 1)) == 2, "one row per legal target"

    def test_it_may_target_any_creature(self, builder):
        """ "**Target creature**", unqualified: a controller clause would be a
        different card, and in this deck the interesting target is sometimes the
        blocker you are about to make useless."""
        game, passage = self.board(builder, 4)
        offered = {t.id for a in acts(game, passage, 1) for t in a.targets}
        assert offered == {only_oid(game, BEAR, 0), only_oid(game, WALL, 1)}

    def combat(self, builder, *, use: bool):
        """Five Plains, not four: the {4} leaves one untapped so `t_plain_instant`
        is still castable, and the seat keeps getting priority instead of the
        engine auto-passing whole turns and taking the `this_turn` effect with
        them."""
        game, passage = self.board(builder, 5)
        bear = only_oid(game, BEAR, 0)
        if use:
            game.apply(next(a for a in acts(game, passage, 1) if a.targets[0].id == bear))
            resolve(game)
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, bear)
        to_declaration(game, DecisionKind.DECLARE_BLOCKERS)
        return game, bear

    def test_the_named_attacker_cannot_be_blocked(self, builder):
        game, _bear = self.combat(builder, use=True)
        assert blocks_offered(game) == []

    def test_and_without_the_ability_the_wall_blocks_it(self, builder):
        """The control. Without it the row above is "a 0/4 declined to block"."""
        game, bear = self.combat(builder, use=False)
        assert blocks_offered(game) == [(only_oid(game, WALL, 1), bear)]


# ----------------------------------------------------------------------
# the rocks
# ----------------------------------------------------------------------


class TestSolRing:
    """ "{T}: Add {C}{C}."

    A hand-written card with **no** expectation entry at all, so no gate ever
    watched it do anything. What `tests/` had was `test_the_ur_dragon_mana.py`
    asserting `{"C": 3}` off a Sol Ring *under Kinnan* -- a test about the
    doubler, which would read the same if the Ring itself made `{W}{W}`.
    """

    def test_it_adds_two(self, builder):
        game = builder(players=2).battlefield(0, ["sol_ring"]).build(advance=False)
        assert offered_amount(game, only_oid(game, "sol_ring", 0)) == 2

    def test_and_both_are_colourless(self, builder):
        """ "{C}{C}", not "{W}{W}". In a mono-white deck those two readings look
        alike on a mana count and are different cards at the payment."""
        game = builder(players=2).battlefield(0, ["sol_ring"]).build(advance=False)
        assert offered_symbols(game, only_oid(game, "sol_ring", 0)) == {"C"}

    def test_its_two_mana_cannot_pay_a_white_pip(self, builder):
        """The payment, read off the action list rather than off the pool. Mind
        Stone is {2} and castable; Soul Warden is {W} and is not."""
        game = (
            builder(players=2)
            .battlefield(0, ["sol_ring"])
            .hand(0, [WHITE_ONE, COLOURLESS_TWO])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        assert castable(game) == {COLOURLESS_TWO}

    def test_it_enters_untapped(self, builder):
        """The contrast with Marble Diamond and Worn Powerstone below, and the
        reason a turn-one Sol Ring is a turn-one Sol Ring."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .hand(0, ["sol_ring"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, "sol_ring")
        assert not game.state.objects[only_oid(game, "sol_ring", 0)].tapped
        assert available_mana(game.state, 0) == 2, "and it is usable the turn it lands"


class TestArcaneSignet:
    """ "{T}: Add one mana of any color in your commander's color identity."

    Another hand-written card with no expectation entry, and -- unlike Sol Ring --
    with no test anywhere in `tests/` that so much as names it.
    """

    def test_it_taps_for_the_commanders_colour_only(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["arcane_signet"])
            .commander(0, [MYREL])
            .build(advance=False)
        )
        signet = only_oid(game, "arcane_signet", 0)
        assert offered_symbols(game, signet) == {"W"}


class TestCommandersSphere:
    """ "{T}: Add one mana of any color in your commander's color identity." /
    "Sacrifice this artifact: Draw a card."

    The mana half is pinned to the commander's identity, as Arcane Signet's is,
    and the sacrifice half beside it.
    """

    def board(self, builder, *, lands=()):
        game = (
            builder(players=2)
            .battlefield(0, ["commanders_sphere", *lands])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .commander(0, [MYREL])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "commanders_sphere", 0)

    def test_it_taps_for_the_commanders_colour_only(self, builder):
        game, sphere = self.board(builder)
        assert offered_symbols(game, sphere) == {"W"}

    def test_the_sacrifice_costs_no_mana_and_no_tap(self, builder):
        """Not "{1}, {T}, Sacrifice" -- that is Mind Stone next door. On a board
        with no other permanent at all the Sphere still offers it, which is the
        only way to tell the two costs apart."""
        game, sphere = self.board(builder)
        assert [a.ability_index for a in acts(game, sphere)] == [1]

    def test_sacrificing_it_draws_a_card(self, builder):
        game, sphere = self.board(builder)
        before = library(game)
        game.apply(acts(game, sphere, 1)[0])
        resolve(game)

        assert before - library(game) == 1
        assert game.state.objects[sphere].zone is Zone.GRAVEYARD


class TestMindStone:
    """ "{T}: Add {C}." / "{1}, {T}, Sacrifice this artifact: Draw a card."

    A hand-written card with no expectation entry. `test_manual_mana.py` asserts
    the *shape* of its action list -- that both abilities appear for a human seat
    -- and never fires either of them.
    """

    def test_it_adds_one_and_not_two(self, builder):
        """The whole difference from Sol Ring, which costs one mana less and
        makes one mana more. Two rocks, one shape, and the quantity is the card.
        """
        game = builder(players=2).battlefield(0, ["mind_stone"]).build(advance=False)
        assert offered_amount(game, only_oid(game, "mind_stone", 0)) == 1
        assert offered_symbols(game, only_oid(game, "mind_stone", 0)) == {"C"}

    def board(self, builder, *, lands=()):
        game = (
            builder(players=2)
            .battlefield(0, ["mind_stone", *lands])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "mind_stone", 0)

    def test_the_draw_needs_a_mana_from_somewhere_else(self, builder):
        """ "{1}, {T}, Sacrifice". The Stone's own `{T}` is spent by the cost, so
        it cannot tap for the `{1}` -- the boundary that tells this cost from
        Commander's Sphere's bare sacrifice."""
        game, stone = self.board(builder)
        assert acts(game, stone) == []

    def test_with_one_other_source_it_is_offered(self, builder):
        game, stone = self.board(builder, lands=[PLAINS])
        assert [a.ability_index for a in acts(game, stone)] == [1]

    def test_sacrificing_it_draws_a_card(self, builder):
        game, stone = self.board(builder, lands=[PLAINS])
        before = library(game)
        game.apply(acts(game, stone, 1)[0])
        resolve(game)

        assert before - library(game) == 1
        assert game.state.objects[stone].zone is Zone.GRAVEYARD


class TestMarbleDiamond:
    """ "This artifact enters tapped." / "{T}: Add {W}."

    The expectation is `{"zone": "battlefield"}` -- which is true of a Marble
    Diamond that enters untapped, and that card is a Mox.
    """

    def played(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, PLAINS])
            .hand(0, ["marble_diamond"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, "marble_diamond")
        return game, only_oid(game, "marble_diamond", 0)

    def test_it_enters_tapped(self, builder):
        game, diamond = self.played(builder)
        assert game.state.objects[diamond].tapped

    def test_so_it_makes_no_mana_the_turn_it_lands(self, builder):
        """What "enters tapped" costs, stated as the thing a player would
        notice. Both Plains paid the {2} and the Diamond is tapped, so the board
        makes nothing -- where an untapped Diamond would read one."""
        game, _diamond = self.played(builder)
        assert available_mana(game.state, 0) == 0

    def test_it_taps_for_white_and_not_colourless(self, builder):
        """A Diamond is a colourless artifact that makes *coloured* mana, which
        is the only reason it is in a deck that also runs Worn Powerstone."""
        game = builder(players=2).battlefield(0, ["marble_diamond"]).build(advance=False)
        diamond = only_oid(game, "marble_diamond", 0)
        assert offered_symbols(game, diamond) == {"W"}
        assert offered_amount(game, diamond) == 1


class TestWornPowerstone:
    """ "This artifact enters tapped." / "{T}: Add {C}{C}."

    The expectation is `{"zone": "battlefield"}`. Both printed sentences are
    unrecorded, and dropping the first one makes this a three-mana rock that
    ramps the turn it lands.
    """

    def test_it_adds_two_colourless(self, builder):
        game = builder(players=2).battlefield(0, ["worn_powerstone"]).build(advance=False)
        stone = only_oid(game, "worn_powerstone", 0)
        assert offered_amount(game, stone) == 2
        assert offered_symbols(game, stone) == {"C"}

    def test_it_enters_tapped(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 3)
            .hand(0, ["worn_powerstone"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, "worn_powerstone")
        assert game.state.objects[only_oid(game, "worn_powerstone", 0)].tapped
        assert available_mana(game.state, 0) == 0, "three Plains spent, and nothing back"


class TestPearlMedallion:
    """ "White spells you cast cost {1} less to cast."

    A static that changes the price of a *later* spell, in a sandbox that casts
    one card and stops: gate 5's `{"battlefield_count": 33, "zone":
    "battlefield"}` cannot see any of it.
    """

    def board(self, builder, *, medallion: bool, lands: int = 1, hand=()):
        return (
            builder(players=2)
            .battlefield(0, (["pearl_medallion"] if medallion else []) + [PLAINS] * lands)
            .hand(0, list(hand))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_a_white_spell_costs_one_less(self, builder):
        game = self.board(builder, medallion=True)
        assert cost_reduction(game.state, 0, game.state.registry.get(WHITE_TWO)) == 1

    def test_a_colourless_spell_costs_the_same(self, builder):
        """ "**White** spells", not "spells". This deck runs nine colourless
        artifacts, so a Medallion written without the colour clause discounts a
        third of the list."""
        game = self.board(builder, medallion=True)
        assert cost_reduction(game.state, 0, game.state.registry.get(COLOURLESS_TWO)) == 0
        assert cost_reduction(game.state, 0, game.state.registry.get("worn_powerstone")) == 0

    def test_the_discount_makes_a_two_drop_castable_off_one_plains(self, builder):
        """Measured at the boundary. Ballyrush Banneret is {1}{W}; one Plains
        pays it only if the {1} is gone."""
        game = self.board(builder, medallion=True, hand=[WHITE_TWO])
        assert WHITE_TWO in castable(game)

    def test_and_without_it_the_same_board_cannot(self, builder):
        game = self.board(builder, medallion=False, hand=[WHITE_TWO])
        assert WHITE_TWO not in castable(game)

    def test_it_cannot_reduce_below_the_coloured_pip(self, builder):
        """The clamp (601.2f). Soul Warden is `{W}` -- no generic part at all --
        so a Medallion with no land behind it still cannot cast it. A reduction
        applied to the mana *value* instead makes every one-drop in the deck
        free."""
        game = self.board(builder, medallion=True, lands=0, hand=[WHITE_ONE])
        assert cost_reduction(game.state, 0, game.state.registry.get(WHITE_ONE)) == 1
        assert castable(game) == set(), "{W} is still owed, and nothing can pay it"


class TestWayfarersBauble:
    """ "{2}, {T}, Sacrifice this artifact: Search your library for a basic land
    card, put that card onto the battlefield tapped, then shuffle."

    A hand-written card with no expectation entry and no test anywhere in
    `tests/` that names it: until now nothing had ever run its only sentence.
    """

    def board(self, builder, plains: int):
        game = (
            builder(players=2)
            .battlefield(0, ["wayfarers_bauble", *[PLAINS] * plains])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "wayfarers_bauble", 0)

    def test_one_other_mana_is_not_enough(self, builder):
        """ "{2}" beside the `{T}`, and the Bauble makes no mana of its own."""
        game, bauble = self.board(builder, 1)
        assert acts(game, bauble) == []

    def test_two_other_mana_and_it_is_offered(self, builder):
        game, bauble = self.board(builder, 2)
        assert [a.ability_index for a in acts(game, bauble)] == [0]

    def fetched(self, builder):
        game, bauble = self.board(builder, 2)
        before = library(game)
        standing = {obj.oid for obj in game.state.battlefield_objects(0)}
        game.apply(acts(game, bauble, 0)[0])
        resolve(game, take=1)
        arrived = [obj for obj in game.state.battlefield_objects(0) if obj.oid not in standing]
        return game, bauble, before, arrived

    def test_it_fetches_exactly_one_land(self, builder):
        """ "a basic land card" -- one. Myriad Landscape next door fetches two off
        a cost one mana cheaper, so the quantity is the card and not the shape.
        """
        game, _bauble, _before, arrived = self.fetched(builder)
        assert [obj.def_id for obj in arrived] == [PLAINS]
        assert len(oids_of(game, PLAINS, 0)) == 3, "the two already down, plus one"

    def test_it_comes_out_of_the_library(self, builder):
        game, _bauble, before, _arrived = self.fetched(builder)
        assert before - library(game) == 1

    def test_it_arrives_tapped(self, builder):
        _game, _bauble, _before, arrived = self.fetched(builder)
        assert [obj.tapped for obj in arrived] == [True]

    def test_it_sacrifices_itself(self, builder):
        game, bauble, _before, _arrived = self.fetched(builder)
        assert game.state.objects[bauble].zone is Zone.GRAVEYARD


class TestArchaeomancersMap:
    """ "When this artifact enters, search your library for up to two basic Plains
    cards, reveal them, put them into your hand, then shuffle."

    Gate 5 got this one nearly right -- `{"hand_size": {"0": 3}, "library_size":
    {"0": 38}}` -- because the trigger fires on entry, which is the one thing its
    sandbox does. What the counts cannot say is *which* zone the cards landed in
    or *what* they were, and both are the card: two basic Plains into **hand**.

    The Map's second sentence (the land-drop catch-up) is already pinned in
    `tests/cards/test_bard_king_of_dale_deck.py::TestArchaeomancersMap`, so it is
    deliberately not repeated here.
    """

    def played(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 3)
            .hand(0, ["archaeomancer_s_map"])
            .library(0, [PLAINS, PLAINS, "idyllic_grange", *[BEAR] * 10])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        before = library(game)
        cast(game, "archaeomancer_s_map", take=2)
        return game, before

    def test_the_two_plains_go_to_your_hand(self, builder):
        """ "…put them into your **hand**", which is the whole difference between
        this card and a Sakura-Tribe Elder: nothing is ramped, the land drop is
        still owed."""
        game, _before = self.played(builder)
        assert hand_ids(game) == [PLAINS, PLAINS]

    def test_and_not_onto_the_battlefield(self, builder):
        game, _before = self.played(builder)
        assert len(oids_of(game, PLAINS, 0)) == 3, "the three already down, and no more"

    def test_they_come_out_of_the_library(self, builder):
        game, before = self.played(builder)
        assert before - library(game) == 2

    def test_a_nonbasic_plains_is_not_fetched(self, builder):
        """ "**basic** Plains cards". Idyllic Grange is a Plains in this very
        deck and is sitting in the searched zone; a selector without the
        supertype takes it."""
        game, _before = self.played(builder)
        assert "idyllic_grange" not in hand_ids(game)


# ----------------------------------------------------------------------
# the gear
# ----------------------------------------------------------------------


class TestSkullclamp:
    """ "Equipped creature gets +1/-1." / "Whenever equipped creature dies, draw
    two cards." / "Equip {1}"

    The expectation is `{"battlefield_count": 33, "hand_size": {"0": 1}, "zone":
    "battlefield"}`. Equip is an activated ability, so the gate never attached
    the Clamp to anything and neither the buff, the drawback nor the draw was
    ever observed.
    """

    def board(self, builder, creature: str, *, plains: int = 3):
        game = (
            builder(players=2)
            .battlefield(0, ["skullclamp", creature, *[PLAINS] * plains])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "skullclamp", 0), only_oid(game, creature, 0)

    def equip(self, game, clamp: int, target: int) -> int:
        before = library(game)
        game.apply(next(a for a in acts(game, clamp) if a.targets and a.targets[0].id == target))
        resolve(game)
        return before - library(game)

    def test_it_gives_plus_one_minus_one(self, builder):
        """Read on a 2/2, where both halves show and nothing dies."""
        game, clamp, bear = self.board(builder, BEAR)
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (2, 2)
        drawn = self.equip(game, clamp, bear)

        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (3, 1)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert drawn == 0, "nothing died, so nothing was drawn"

    def test_a_one_toughness_creature_dies_and_draws_two(self, builder):
        """The card, and the reason it is banned in Commander's smaller cousins.
        Recruitment Officer is a 2/1 Soldier out of this very deck: the `-1`
        kills it and the trigger pays for it twice over.

        A Clamp written `+1/+0`, or one whose trigger drew **one**, leaves a
        board that looks identical the moment anything else kills the creature.
        """
        game, clamp, officer = self.board(builder, SOLDIER)
        assert chars(game.state, officer).toughness == 1, "the premise"
        drawn = self.equip(game, clamp, officer)

        assert game.state.objects[officer].zone is Zone.GRAVEYARD
        assert drawn == 2

    def test_equip_is_sorcery_speed_only(self, builder):
        """702.6b. Offered on your own main phase and nowhere else -- so the
        Clamp cannot be moved onto a creature mid-combat in response to
        anything."""
        game = (
            builder(players=2)
            .battlefield(0, ["skullclamp", BEAR, *[PLAINS] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        clamp = only_oid(game, "skullclamp", 0)
        assert acts(game, clamp), "your own main phase"
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1 and g.pending() is not None and g.pending().player == 0
            ),
        )
        assert acts(game, clamp) == [], "the opponent's turn"


class TestLightningGreaves:
    """ "Equipped creature has haste and shroud." / "Equip {0}"

    The expectation is `{"zone": "battlefield"}`, and both printed clauses are
    behind an Equip the gate never activates. Shroud is the half that is easy to
    lose: it is the card's **drawback**, and a Greaves that granted only haste --
    or that granted hexproof, which stops opponents and not you -- is a strictly
    better card that nothing on the board would look wrong about.
    """

    def board(self, builder, *, lands: int = 2, second_attacker: bool = False):
        b = builder(players=2).battlefield(
            0, ["lightning_greaves", *[PLAINS] * lands] + ([SOLDIER] if second_attacker else [])
        )
        game = (
            b.battlefield(0, [BEAR], sick=True)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "lightning_greaves", 0), only_oid(game, BEAR, 0)

    def test_equip_costs_nothing(self, builder):
        """ "Equip **{0}**", which is why the Greaves go on the commander the turn
        it lands. Offered on a board with no untapped mana at all."""
        game, greaves, bear = self.board(builder, lands=0)
        assert [t.id for a in acts(game, greaves) for t in a.targets] == [bear]

    def test_it_grants_haste_and_shroud(self, builder):
        game, greaves, bear = self.board(builder)
        assert keywords_of(game, bear) == set(), "a vanilla 2/2 before the Greaves"
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert keywords_of(game, bear) == {"haste", "shroud"}

    def test_a_summoning_sick_creature_attacks_that_turn(self, builder):
        """The assertion every wrong haste implementation fails silently: on the
        battlefield, this turn, in the declaration."""
        game, greaves, bear = self.board(builder, second_attacker=True)
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)

        assert any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == bear for a in game.legal_actions()
        )

    def test_and_without_the_greaves_it_cannot(self, builder):
        """The control, on the same turn. Recruitment Officer is the second
        attacker and is load bearing: without a creature that *can* attack there
        is no declaration this turn at all, and the engine walks two turns
        forward to find one -- by which time the sickness has gone and both
        halves of this pair look alike."""
        game, _greaves, bear = self.board(builder, second_attacker=True)
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)

        assert not any(
            a.kind is ActionKind.ADD_ATTACKER and a.source == bear for a in game.legal_actions()
        )

    def test_the_shroud_stops_your_own_spells_too(self, builder):
        """702.18a, and the difference from hexproof. `can_be_targeted` asked as
        **player 0**, who controls the creature."""
        game, greaves, bear = self.board(builder)
        assert can_be_targeted(game.state, 0, bear), "before"
        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert not can_be_targeted(game.state, 0, bear)

    def test_no_other_equipment_can_be_moved_onto_it(self, builder):
        """The drawback, played out of this deck's own two Equipment. Equip
        targets, so once the Greaves are on, Skullclamp has no legal target --
        which is a real cost in a deck that wants the Clamp on the same body."""
        game = (
            builder(players=2)
            .battlefield(0, ["lightning_greaves", "skullclamp", BEAR, *[PLAINS] * 3])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        greaves = only_oid(game, "lightning_greaves", 0)
        clamp = only_oid(game, "skullclamp", 0)
        bear = only_oid(game, BEAR, 0)
        assert acts(game, clamp), "the Clamp could be equipped before"

        game.apply(next(a for a in acts(game, greaves) if a.targets[0].id == bear))
        resolve(game)

        assert acts(game, clamp) == []


class TestSentinelTotem:
    """ "When this artifact enters, scry 1." / "{T}, Exile this artifact: Exile all
    graveyards."

    Gate 5 recorded `{"library_size": {"0": 40}, ...}` for the scry -- which is
    correct and says nothing, since a scry that bottoms nothing moves no cards.
    The ability is the card and was never activated.
    """

    def test_it_scries_one_on_entering(self, builder):
        """Read off the event, because the board cannot show it: a scry that
        keeps the card on top is indistinguishable from no scry at all."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .hand(0, ["sentinel_totem"])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        mark = len(game.state.events)
        cast(game, "sentinel_totem")

        assert [e["looked"] for e in scries(game, mark)] == [1], "scry 1, not scry 2"

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["sentinel_totem", PLAINS])
            .graveyard(0, [PLAINS, BEAR])
            .graveyard(1, [PLAINS])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "sentinel_totem", 0)

    def test_it_exiles_every_graveyard_including_your_own(self, builder):
        """ "**all** graveyards". The near miss is "each opponent's", which in a
        deck running Rest in Peace and Approach of the Second Sun is a different
        and much better card -- and on a board where only the opponent has a
        graveyard the two readings are the same."""
        game, totem = self.board(builder)
        game.apply(acts(game, totem, 1)[0])
        resolve(game)

        assert game.state.players[0].graveyard == []
        assert game.state.players[1].graveyard == []

    def test_it_exiles_itself_rather_than_dying(self, builder):
        """ "**Exile** this artifact" is the cost, not a sacrifice: the Totem does
        not end up in the graveyard it just emptied, and nothing that watches for
        an artifact dying sees anything."""
        game, totem = self.board(builder)
        game.apply(acts(game, totem, 1)[0])
        resolve(game)

        assert game.state.objects[totem].zone is Zone.EXILE


class TestPeterParkersCamera:
    """ "This artifact enters with three film counters on it." / "{2}, {T}, Remove a
    film counter from this artifact: Copy target activated or triggered ability
    you control. You may choose new targets for the copy."

    The entry counters are the one thing gate 5 did pin
    (`{"counters": {"amount": 3, "kind": "film"}}`), so they are not re-asserted.
    Everything past them needs an ability already on the stack, which the gate
    never puts there. `tests/unit/copies/test_copy_ability.py` pins the capability on a
    test-only card called `t_camera`.
    """

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["peter_parker_s_camera"], counters={"film": 3})
            .battlefield(0, ["castle_ardenvale", *[PLAINS] * 6])
            .hand(0, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return (
            game,
            only_oid(game, "peter_parker_s_camera", 0),
            only_oid(game, "castle_ardenvale", 0),
        )

    def test_it_is_not_offered_with_an_empty_stack(self, builder):
        """ "Copy **target** activated or triggered ability": with nothing on the
        stack there is no legal target, so the film counters cannot be burned for
        nothing."""
        game, camera, _castle = self.board(builder)
        assert acts(game, camera) == []

    def copied(self, builder):
        game, camera, castle = self.board(builder)
        game.apply(acts(game, castle, 1)[0])
        assert game.state.stack, "the Castle's ability is waiting to resolve"
        game.apply(acts(game, camera, 0)[0])
        resolve(game)
        return game, camera

    def test_it_copies_an_activated_ability_and_both_resolve(self, builder):
        """The Castle's token ability, copied: two 1/1 Humans off one {2}{W}{W}.
        A copy that replaced the original, or one that never resolved, leaves one
        token and looks like a card that did nothing."""
        game, _camera = self.copied(builder)
        assert len(tokens(game)) == 2

    def test_a_film_counter_is_spent(self, builder):
        """ "**Remove a film counter**" is part of the cost, and it is what makes
        the Camera a three-shot rather than an engine."""
        game, camera = self.copied(builder)
        assert game.state.objects[camera].counters.get("film") == 2


class TestGleamingSplendor:
    """ "Whenever an opponent draws their second card each turn, you create a
    Treasure token." / "{2}{W}: Two target players each draw a card."

    Gate 5's expectation is `{"battlefield_count": 33, "hand_size": {"0": 1},
    "zone": "battlefield"}`: nothing in its sandbox draws a second card after the
    card under test, and it never activates the ability.
    """

    def their_turn(self, builder, spell: str):
        return (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", PLAINS])
            .battlefield(1, ["island"] * 3)
            .hand(0, [ANCHOR])
            .hand(1, [spell])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_an_opponents_second_draw_makes_a_treasure(self, builder):
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert len(tokens(game, 0)) == 1
        assert tokens(game, 0)[0].def_id == "treasure_token"

    def test_the_treasure_is_yours_and_not_theirs(self, builder):
        """ "**you** create". The Splendor is a group-hug enchantment whose whole
        payoff is which side of the table the Treasure lands on."""
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert tokens(game, 1) == []

    def test_two_draws_make_one_treasure_and_not_two(self, builder):
        """ "their **second** card", and only it. Divination draws two, so a
        trigger written on every draw makes two Treasures off this one spell."""
        game = self.their_turn(builder, DRAW_TWO)
        cast(game, DRAW_TWO, pid=1)

        assert len(tokens(game, 0)) == 1

    def from_their_upkeep(self, builder):
        """Seat 1's whole turn, from before the draw step.

        The draw-step draw is their **first** card, which is the half a trigger
        on "an opponent draws" gets wrong every single turn of the game.
        """
        return (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", PLAINS])
            .battlefield(1, ["island"] * 3)
            .hand(0, [ANCHOR])
            .hand(1, [DRAW_TWO])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .active(1)
            .step(Step.UNTAP)
            .build()
        )

    def test_their_draw_step_draw_makes_none(self, builder):
        game = self.from_their_upkeep(builder)
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == 1,
        )
        assert library(game, 1) == 19, "the premise: they drew exactly one card"
        assert tokens(game, 0) == []

    def test_and_the_next_card_after_it_does(self, builder):
        """The boundary read across a step. One card drawn in the draw step, two
        more off Divination, and exactly one of the three is a second card."""
        game = self.from_their_upkeep(builder)
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.active_player == 1,
        )
        cast(game, DRAW_TWO, pid=1)

        assert library(game, 1) == 17, "three cards drawn this turn"
        assert len(tokens(game, 0)) == 1

    def test_your_own_draws_make_none(self, builder):
        """ "…an **opponent** draws"."""
        game = (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", *["island"] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [DRAW_TWO])
            .hand(1, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast(game, DRAW_TWO)

        assert tokens(game, 0) == []

    def test_the_activated_ability_draws_for_two_players(self, builder):
        """ "**Two** target players each draw a card" -- one card each, two seats,
        and one of them is you. A single-target version is a different card and
        would read as the same draw."""
        game = (
            builder(players=2)
            .battlefield(0, ["gleaming_splendor", *[PLAINS] * 4])
            .hand(0, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .library(1, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        splendor = only_oid(game, "gleaming_splendor", 0)
        [action] = acts(game, splendor, 1)
        assert sorted(t.id for t in action.targets) == [0, 1], "both seats, in one activation"
        before = [library(game, 0), library(game, 1)]

        game.apply(action)
        resolve(game)

        assert [before[0] - library(game, 0), before[1] - library(game, 1)] == [1, 1]


class TestRescueRetriever:
    """ "Flash" / "When this creature enters, put a +1/+1 counter on each other
    Soldier you control." / "Prevent all damage that would be dealt to other
    attacking Soldiers you control."

    Gate 5's expectation is `{"battlefield_count": 33, "hand_size": {"0": 1},
    "zone": "battlefield"}` -- no counters recorded, because its sandbox has no
    other Soldier for them to go on, and no combat for the prevention to reach.
    `tests/unit/damage/test_prevent_all_damage.py` pins the capability on a test-only
    card called `t_retriever`; this is the shipped card, in a declared combat.
    """

    def test_it_has_flash(self, builder):
        """A {3}{W}{W} creature this deck holds up, so the timing is the card."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 5)
            .battlefield(1, [PLAINS])
            .hand(0, ["rescue_retriever"])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        pass_until(
            game,
            lambda g: (
                g.state.active_player == 1 and g.pending() is not None and g.pending().player == 0
            ),
        )
        assert "rescue_retriever" in castable(game)

    def test_the_counters_go_on_other_soldiers_you_control(self, builder):
        """One board, four answers, and each is a clause of the sentence.

        Recruitment Officer is a Soldier of mine and gets one; the Bear is mine
        and is not a Soldier; Ballyrush Banneret is a Soldier and is not mine;
        and the Retriever is a Soldier of mine that the word "other" excludes.
        """
        game = (
            builder(players=2)
            .battlefield(0, [SOLDIER, BEAR, *[PLAINS] * 5])
            .battlefield(1, [WHITE_TWO])
            .hand(0, ["rescue_retriever"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        officer, bear = only_oid(game, SOLDIER, 0), only_oid(game, BEAR, 0)
        theirs = only_oid(game, WHITE_TWO, 1)
        dog = cast(game, "rescue_retriever")

        assert game.state.objects[officer].counters.get("+1/+1") == 1
        assert not game.state.objects[bear].counters.get("+1/+1"), "a Bear is not a Soldier"
        assert not game.state.objects[theirs].counters.get("+1/+1"), "not yours"
        assert not game.state.objects[dog].counters.get("+1/+1"), "'each OTHER Soldier'"

    def combat(self, builder, *, retriever: bool):
        """Attack with the Officer into a 2/2, with or without the Retriever.

        Recruitment Officer is a 2/1: one point of combat damage kills it, so the
        shield is the only thing between it and the graveyard.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["rescue_retriever" if retriever else WALL, SOLDIER])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        officer, bear = only_oid(game, SOLDIER, 0), only_oid(game, BEAR, 1)
        attackers = [officer]
        if retriever:
            attackers.append(only_oid(game, "rescue_retriever", 0))
        to_declaration(game, DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, *attackers)
        to_declaration(game, DecisionKind.DECLARE_BLOCKERS)
        return game, officer, bear

    def test_a_blocked_soldier_takes_no_damage(self, builder):
        game, officer, bear = self.combat(builder, retriever=True)
        assert prevents_all_damage(game.state, officer) is True
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER
                and a.source == bear
                and a.targets[0].id == officer
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)

        assert game.state.objects[officer].damage == 0
        assert game.state.objects[officer].zone is Zone.BATTLEFIELD
        assert game.state.objects[bear].zone is Zone.GRAVEYARD, "and it still dealt its own 2"

    def test_and_without_the_retriever_the_same_soldier_dies(self, builder):
        """The control, so the row above is about the static and not about the
        arithmetic of a 2/1 against a 2/2."""
        game, officer, bear = self.combat(builder, retriever=False)
        assert prevents_all_damage(game.state, officer) is False
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER
                and a.source == bear
                and a.targets[0].id == officer
            )
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)

        assert game.state.objects[officer].zone is Zone.GRAVEYARD

    def test_it_does_not_shield_itself(self, builder):
        """ "…**other** attacking Soldiers". The Retriever is an attacking Soldier
        its controller controls, so without the clause it is immune to everything
        while attacking -- and on a board where every Soldier is attacking, the
        narrowed and unnarrowed readings agree about all of them but this one."""
        game, _officer, _bear = self.combat(builder, retriever=True)
        dog = only_oid(game, "rescue_retriever", 0)
        assert prevents_all_damage(game.state, dog) is False
