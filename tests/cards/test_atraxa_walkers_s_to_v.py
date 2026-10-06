"""The Atraxa, Praetors' Voice superfriends deck's planeswalkers, S to V, doing what they print.

Every card here cleared the six authoring gates, and that is why this file
exists. Gate 5 -- the behaviour gate -- casts a card once, in one fixed sandbox,
and reads the board. For a planeswalker that is almost nothing:

- **It never activates an ability.** A planeswalker is its loyalty abilities,
  so for each of these nine cards the gate saw a permanent arrive with its
  printed loyalty and learned nothing about any of the three lines under it.
  Every ability below is activated, and every test reads both the effect and
  the loyalty change -- the cost is half the line.
- **It cannot see a later turn.** Four of these cards print "until your next
  turn" (Sorin's anthem, Tamiyo's delayed draw, Teferi's flash, Vraska's
  deathtouch-on-Vraska), and one prints a "next untap step". Each is walked
  through the opponent's turn and into the controller's next one, because the
  near miss -- "until end of turn" -- is the reading that looks right on the
  turn it was activated.
- **An emblem acts on a later turn, from the command zone.** Sorin's edict,
  Tamiyo's free casting and Teferi's instant-speed loyalty are observed doing
  their job after the planeswalker that made them is gone.
- **A static that changes someone else's options is invisible** to a gate that
  only asks the caster: Tamiyo, Collector of Tales' protection and Teferi, Time
  Raveler's lock are read from the opponent's side.

Each class is one card and pins the near miss too: X removes exactly X, the
emblem frees only spells cast from hand, the lock binds only opponents, the
Assassin's loss lands on the player it hit and nobody else.

**Why every position holds an `ANCHOR`.** With no play available to anybody the
engine's auto-pass runs whole turns inside one `apply`, which overshoots every
"until your next turn" boundary measured here. A castable instant in each
seat's hand is a reason for priority to stop.
"""

from __future__ import annotations

import contextlib

from automtg.cards.registry import DeckList, validate_deck
from automtg.engine import legality
from automtg.engine.costs import cost_reduction
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    activations,
    find_action,
    keywords,
    oids_of,
    only_oid,
    pass_until,
    pt,
    settle_completely,
)

PLAINS = "plains"
ISLAND = "island"
FOREST = "forest"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
BEAR = "t_bear"  # {1}{G} 2/2 vanilla, mana value 2
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
SORCERY = "divination"  # {2}{U} sorcery, draw two
TRINKET = "t_xdt_two"  # {2} vanilla artifact
THREE_DROP = "t_xdt_three"  # {3} vanilla artifact, a mana-value-3 permanent card


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def table(
    builder,
    walker: str,
    *,
    loyalty: int | None = None,
    mine=(),
    theirs=(),
    lands0=(PLAINS,),
    lands1=(PLAINS,),
    hand0=(ANCHOR,),
    hand1=(ANCHOR,),
    library0=None,
    graveyard0=(),
    graveyard1=(),
    players: int = 2,
    life: dict[int, int] | None = None,
    tapped_lands: bool = False,
):
    """Player 0's precombat main with ``walker`` on the battlefield.

    ``loyalty`` overrides the printed starting loyalty, which is how an ultimate
    is reached without three turns of plus abilities in front of it.
    """
    counters = {"loyalty": loyalty} if loyalty is not None else None
    b = builder(players=players).battlefield(0, [walker], counters=counters)
    b = b.battlefield(0, list(mine)).battlefield(0, list(lands0), tapped=tapped_lands)
    b = b.battlefield(1, [*theirs, *lands1])
    b = b.hand(0, list(hand0)).hand(1, list(hand1))
    b = b.library(0, list(library0) if library0 is not None else [PLAINS] * 20)
    b = b.library(1, [PLAINS] * 20)
    b = b.graveyard(0, list(graveyard0)).graveyard(1, list(graveyard1))
    for pid in range(2, players):
        b = b.battlefield(pid, [PLAINS]).hand(pid, [ANCHOR]).library(pid, [PLAINS] * 20)
    for pid, amount in (life or {}).items():
        b = b.life(pid, amount)
    game = b.step(Step.PRECOMBAT_MAIN).active(0).max_turns(12).build()
    return game, only_oid(game, walker, 0)


def activate(game, oid: int, index: int, *, targets=None, x: int | None = None):
    """Activate ability ``index`` of ``oid``, aimed at exactly ``targets``.

    ``targets`` is a collection of oids (or player ids for a player target);
    ``None`` takes the first offer. ``x`` matches an X announced with the offer.
    """
    for action in activations(game, oid, index):
        if targets is not None and sorted(t.id for t in action.targets) != sorted(targets):
            continue
        if x is not None and action.x != x:
            continue
        game.apply(action)
        return action
    raise AssertionError(
        f"no activation {index} of {oid} at {targets} x={x}; "
        f"offered: {[(a.ability_index, [t.id for t in a.targets], a.x) for a in activations(game, oid)]}"
    )


def choose_x(game, x: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counter("loyalty")


def offers(game, pid: int, kind: ActionKind) -> set[str]:
    """The def_ids ``pid`` is offered ``kind`` for, asked of legality directly.

    `game.legal_actions()` answers only for whoever holds the pending decision;
    several claims below are about the seat that does not.
    """
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is kind and a.source is not None
    }


def later(game, pid: int, step: Step, *, turns: int = 1) -> None:
    """Pass forward into ``pid``'s ``step``, at least ``turns`` turns from now."""
    start = game.state.turn
    pass_until(
        game,
        lambda g: (
            g.state.turn >= start + turns
            and g.state.active_player == pid
            and g.state.step is step
        ),
    )


def attack_with(game, attacks: dict[int, int | tuple[str, int]]) -> None:
    """Declare ``{attacker: defending player}`` (or ``("walker", oid)``) and close it."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid, defender in attacks.items():
        if isinstance(defender, tuple):
            want = ("object", defender[1])
        else:
            want = ("player", defender)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any((t.kind, t.id) == want for t in a.targets)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def through_combat(game) -> None:
    pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)


def tokens(game, def_id: str, pid: int = 0) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def zone_ids(game, pid: int, zone: str) -> list[str]:
    return [game.state.objects[o].def_id for o in getattr(game.state.players[pid], zone)]


def lives(game) -> list[int]:
    return [p.life for p in game.state.players]


def run(game, effects, controller: int) -> None:
    """Resolve ``effects`` for ``controller``, taking the first option of every question."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    with contextlib.suppress(StopIteration):
        decision = next(gen)
        while True:
            decision = gen.send(list(range(decision.min_count or 1)))


# ----------------------------------------------------------------------
# Sorin
# ----------------------------------------------------------------------


class TestSorinGrimNemesis:
    """ "+1: Reveal the top card of your library and put that card into your hand.
    Each opponent loses life equal to its mana value." / "-X: Sorin deals X damage
    to target creature or planeswalker and you gain X life." / "-9: Create a number
    of 1/1 black Vampire Knight creature tokens with lifelink equal to the highest
    life total among all players."
    """

    def test_plus_one_draws_the_top_card_and_drains_each_opponent_by_its_mana_value(
        self, builder
    ):
        """Three seats: both opponents lose 2 for a mana-value-2 card, you lose nothing."""
        game, sorin = table(builder, "sorin_grim_nemesis", library0=[BEAR, *[PLAINS] * 10],
                            players=3)
        activate(game, sorin, 0)
        settle_completely(game)

        assert loyalty(game, sorin) == 7
        assert BEAR in zone_ids(game, 0, "hand")
        assert lives(game) == [40, 38, 38]

    def test_plus_one_on_a_land_drains_nothing(self, builder):
        """Mana value 0 is 0 life -- the card still goes to hand."""
        game, sorin = table(builder, "sorin_grim_nemesis", library0=[FOREST, *[PLAINS] * 10])
        activate(game, sorin, 0)
        settle_completely(game)

        assert FOREST in zone_ids(game, 0, "hand")
        assert lives(game) == [40, 40]

    def test_minus_x_offers_x_up_to_the_loyalty(self, builder):
        game, sorin = table(builder, "sorin_grim_nemesis", theirs=[BEAR])
        activate(game, sorin, 1, targets=[only_oid(game, BEAR, 1)])

        assert game.pending().kind is DecisionKind.CHOOSE_X
        assert game.pending().context["max_x"] == 6

    def test_minus_two_kills_a_bear_gains_two_and_costs_two(self, builder):
        game, sorin = table(builder, "sorin_grim_nemesis", theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        activate(game, sorin, 1, targets=[bear])
        choose_x(game, 2)
        settle_completely(game)

        assert loyalty(game, sorin) == 4
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert lives(game)[0] == 42

    def test_minus_one_removes_exactly_one_and_the_bear_lives(self, builder):
        """The near miss: X read as the full loyalty, or as a constant."""
        game, sorin = table(builder, "sorin_grim_nemesis", theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        activate(game, sorin, 1, targets=[bear])
        choose_x(game, 1)
        settle_completely(game)

        assert loyalty(game, sorin) == 5
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert lives(game)[0] == 41

    def test_minus_nine_counts_the_highest_life_total_at_the_table(self, builder):
        """You at 12, the opponent at 15: fifteen Knights, not twelve."""
        game, sorin = table(builder, "sorin_grim_nemesis", loyalty=9, life={0: 12, 1: 15})
        activate(game, sorin, 2)
        settle_completely(game)
        made = tokens(game, "vampire_knight_1_1_b_lifelink")

        assert len(made) == 15
        assert all("lifelink" in keywords(game, t.oid) for t in made)
        assert game.state.objects[sorin].zone is Zone.GRAVEYARD, "nine loyalty, all spent"


class TestSorinSolemnVisitor:
    """ "+1: Until your next turn, creatures you control get +1/+0 and gain
    lifelink." / "-2: Create a 2/2 black Vampire creature token with flying." /
    "-6: You get an emblem with 'At the beginning of each opponent's upkeep, that
    player sacrifices a creature of their choice.'"
    """

    def anthem(self, builder):
        game, sorin = table(builder, "sorin_solemn_visitor", mine=[BEAR], theirs=[BEAR])
        activate(game, sorin, 0)
        settle_completely(game)
        return game, sorin, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

    def test_plus_one_pumps_and_grants_lifelink_to_your_creatures(self, builder):
        game, sorin, mine, _theirs = self.anthem(builder)

        assert loyalty(game, sorin) == 5
        assert pt(game, mine) == (3, 2), "+1/+0, not +1/+1"
        assert "lifelink" in keywords(game, mine)

    def test_an_opponents_creature_gets_nothing(self, builder):
        game, _sorin, _mine, theirs = self.anthem(builder)

        assert pt(game, theirs) == (2, 2)
        assert "lifelink" not in keywords(game, theirs)

    def test_the_lifelink_gains_life_in_combat(self, builder):
        """The keyword doing its job: a 3-power attacker gains you 3."""
        game, sorin = table(builder, "sorin_solemn_visitor", mine=[BEAR])
        activate(game, sorin, 0)
        settle_completely(game)
        attack_with(game, {only_oid(game, BEAR, 0): 1})
        through_combat(game)

        assert lives(game) == [43, 37]

    def test_it_survives_the_opponents_turn(self, builder):
        """ "Until your next turn": the near miss ends it at this turn's cleanup."""
        game, _sorin, mine, _theirs = self.anthem(builder)
        later(game, 1, Step.UPKEEP)

        assert pt(game, mine) == (3, 2)
        assert "lifelink" in keywords(game, mine)

    def test_it_ends_when_your_next_turn_begins(self, builder):
        game, _sorin, mine, _theirs = self.anthem(builder)
        later(game, 0, Step.UPKEEP)

        assert pt(game, mine) == (2, 2)
        assert "lifelink" not in keywords(game, mine)

    def test_minus_two_makes_a_flying_vampire(self, builder):
        game, sorin = table(builder, "sorin_solemn_visitor")
        activate(game, sorin, 1)
        settle_completely(game)
        (vampire,) = tokens(game, "vampire_2_2_b_flying")

        assert loyalty(game, sorin) == 2
        assert pt(game, vampire.oid) == (2, 2)
        assert "flying" in keywords(game, vampire.oid)

    def emblem(self, builder):
        game, sorin = table(
            builder, "sorin_solemn_visitor", loyalty=6, mine=[BEAR], theirs=[BEAR, BEAR]
        )
        activate(game, sorin, 2)
        settle_completely(game)
        return game, sorin

    def test_minus_six_gives_you_the_emblem(self, builder):
        game, sorin = self.emblem(builder)

        assert game.state.objects[sorin].zone is Zone.GRAVEYARD
        assert len(game.state.players[0].command) == 1
        assert game.state.players[1].command == []

    def test_the_emblem_takes_a_creature_at_each_opponents_upkeep(self, builder):
        """One creature, not all of them."""
        game, _sorin = self.emblem(builder)
        later(game, 1, Step.DRAW)

        assert len(oids_of(game, BEAR, 1)) == 1

    def test_the_emblem_spares_you_at_your_own_upkeep(self, builder):
        """ "each **opponent's** upkeep" -- your bear lives through your next one."""
        game, _sorin = self.emblem(builder)
        later(game, 0, Step.DRAW)

        assert len(oids_of(game, BEAR, 0)) == 1
        assert len(oids_of(game, BEAR, 1)) == 1, "and theirs paid once, on their upkeep"


# ----------------------------------------------------------------------
# Tamiyo
# ----------------------------------------------------------------------


DISCARD = {"op": "discard", "player": "each_player", "amount": 1}
EDICT = {"op": "sacrifice", "objects": {"controller": "any", "types": ["Creature"], "count": "all"}}


class TestTamiyoCollectorOfTales:
    """ "Spells and abilities your opponents control can't cause you to discard cards
    or sacrifice permanents." / "+1: Choose a nonland card name, then reveal the top
    four cards of your library. Put all cards with the chosen name from among them
    into your hand and the rest into your graveyard." / "-3: Return target card from
    your graveyard to your hand."
    """

    def shielded(self, builder):
        game, _tamiyo = table(
            builder,
            "tamiyo_collector_of_tales",
            mine=[BEAR],
            theirs=[BEAR],
            hand0=[BEAR, BEAR],
            hand1=[BEAR, BEAR],
        )
        return game

    def test_an_opponents_discard_skips_you(self, builder):
        game = self.shielded(builder)
        run(game, [DISCARD], controller=1)

        assert len(game.state.players[0].hand) == 2
        assert len(game.state.players[1].hand) == 1, "the rest of the spell still resolves"

    def test_an_opponents_edict_skips_your_permanents(self, builder):
        game = self.shielded(builder)
        run(game, [EDICT], controller=1)

        assert len(oids_of(game, BEAR, 0)) == 1
        assert oids_of(game, BEAR, 1) == []

    def test_your_own_discard_and_edict_still_reach_you(self, builder):
        """ "your **opponents** control" -- the near miss is blanket protection."""
        game = self.shielded(builder)
        run(game, [DISCARD, EDICT], controller=0)

        assert len(game.state.players[0].hand) == 1
        assert oids_of(game, BEAR, 0) == []

    def name_it(self, builder, name: str):
        game, tamiyo = table(
            builder,
            "tamiyo_collector_of_tales",
            library0=[BEAR, PLAINS, BEAR, BOLT, BEAR, *[PLAINS] * 6],
        )
        activate(game, tamiyo, 1)
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE,
        )
        game.apply(
            next(a for a in game.legal_actions() if a.label and name in a.label)
        )
        settle_completely(game)
        return game, tamiyo

    def test_plus_one_takes_every_named_card_among_the_top_four(self, builder):
        game, tamiyo = self.name_it(builder, "Test Bear")

        assert loyalty(game, tamiyo) == 6
        assert zone_ids(game, 0, "hand").count(BEAR) == 2

    def test_the_rest_go_to_the_graveyard_and_the_fifth_stays(self, builder):
        """ "the rest into your graveyard", and "four" is four: the bear fifth is untouched."""
        game, _tamiyo = self.name_it(builder, "Test Bear")

        assert sorted(zone_ids(game, 0, "graveyard")) == sorted([PLAINS, BOLT])
        assert zone_ids(game, 0, "library")[0] == BEAR

    def test_minus_three_returns_a_card_from_your_graveyard(self, builder):
        game, tamiyo = table(
            builder, "tamiyo_collector_of_tales", graveyard0=[BOLT], graveyard1=[BEAR]
        )
        bolt = game.state.players[0].graveyard[0]
        theirs = game.state.players[1].graveyard[0]
        offered = {t.id for a in activations(game, tamiyo, 2) for t in a.targets}

        assert theirs not in offered, "'your graveyard'"
        activate(game, tamiyo, 2, targets=[bolt])
        settle_completely(game)
        assert loyalty(game, tamiyo) == 2
        assert BOLT in zone_ids(game, 0, "hand")


class TestTamiyoCompleatedSage:
    """ "Compleated" / "+1: Tap up to one target artifact or creature. It doesn't
    untap during its controller's next untap step." / "-X: Exile target nonland
    permanent card with mana value X from your graveyard. Create a token that's a
    copy of that card." / "-7: Create Tamiyo's Notebook ..."
    """

    def cast(self, builder, phyrexian: int):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 3 + [ISLAND] * 2)
            .battlefield(1, [PLAINS])
            .hand(0, ["tamiyo_compleated_sage"])
            .hand(1, [ANCHOR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "tamiyo_compleated_sage"
            and a.phyrexian == phyrexian
        )
        game.apply(action)
        settle_completely(game)
        return game, action.source

    def test_paid_with_mana_she_enters_with_five(self, builder):
        game, tamiyo = self.cast(builder, 0)

        assert loyalty(game, tamiyo) == 5
        assert lives(game)[0] == 40

    def test_paid_with_life_she_enters_with_three(self, builder):
        game, tamiyo = self.cast(builder, 1)

        assert loyalty(game, tamiyo) == 3
        assert lives(game)[0] == 38

    def frozen(self, builder):
        game, tamiyo = table(builder, "tamiyo_compleated_sage", theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        activate(game, tamiyo, 0, targets=[bear])
        settle_completely(game)
        return game, tamiyo, bear

    def test_plus_one_taps_the_target(self, builder):
        game, tamiyo, bear = self.frozen(builder)

        assert loyalty(game, tamiyo) == 6
        assert game.state.objects[bear].tapped

    def test_it_skips_its_controllers_next_untap(self, builder):
        game, _tamiyo, bear = self.frozen(builder)
        later(game, 1, Step.UPKEEP)

        assert game.state.objects[bear].tapped

    def test_and_only_the_next_one(self, builder):
        """ "**next** untap step": the one after that untaps it."""
        game, _tamiyo, bear = self.frozen(builder)
        later(game, 1, Step.UPKEEP, turns=3)

        assert not game.state.objects[bear].tapped

    def test_minus_x_offers_each_permanent_card_at_its_own_mana_value(self, builder):
        """Nonland, permanent, yours: the land and the opponent's card are not aims."""
        game, tamiyo = table(
            builder,
            "tamiyo_compleated_sage",
            graveyard0=[BEAR, THREE_DROP, FOREST, BOLT],
            graveyard1=[TRINKET],
        )
        offered = {
            (a.x, game.state.objects[a.targets[0].id].def_id)
            for a in activations(game, tamiyo, 1)
        }

        assert offered == {(2, BEAR), (3, THREE_DROP)}

    def test_minus_two_exiles_the_bear_and_copies_it(self, builder):
        game, tamiyo = table(builder, "tamiyo_compleated_sage", graveyard0=[BEAR, THREE_DROP])
        bear = game.state.players[0].graveyard[0]
        activate(game, tamiyo, 1, targets=[bear], x=2)
        settle_completely(game)
        copies = [o for o in game.state.battlefield_objects(0) if o.is_token]

        assert loyalty(game, tamiyo) == 3
        assert game.state.objects[bear].zone is Zone.EXILE
        assert len(copies) == 1
        assert game.state.card_of(copies[0]).name == "Test Bear"
        assert THREE_DROP in zone_ids(game, 0, "graveyard"), "only the one it aimed at"

    def test_minus_seven_makes_the_notebook(self, builder):
        """Spells you cast cost {2} less -- and your opponent's do not."""
        game, tamiyo = table(builder, "tamiyo_compleated_sage", loyalty=7)
        activate(game, tamiyo, 2)
        settle_completely(game)
        divination = game.state.registry.get(SORCERY)

        assert len(tokens(game, "tamiyos_notebook")) == 1
        assert game.state.objects[tamiyo].zone is Zone.GRAVEYARD
        assert cost_reduction(game.state, 0, divination) == 2
        assert cost_reduction(game.state, 1, divination) == 0


class TestTamiyoFieldResearcher:
    """ "+1: Choose up to two target creatures. Until your next turn, whenever either
    of those creatures deals combat damage, you draw a card." / "-2: Tap up to two
    target nonland permanents. They don't untap during their controller's next untap
    step." / "-7: Draw three cards. You get an emblem with 'You may cast spells from
    your hand without paying their mana costs.'"
    """

    def watched(self, builder):
        """Two bears of yours; Tamiyo's +1 picks only the first."""
        game, tamiyo = table(builder, "tamiyo_field_researcher", mine=[BEAR, BEAR])
        watched, unwatched = oids_of(game, BEAR, 0)
        activate(game, tamiyo, 0, targets=[watched])
        settle_completely(game)
        return game, tamiyo, watched, unwatched

    def test_plus_one_draws_when_the_chosen_creature_connects(self, builder):
        """Both bears connect; only the chosen one draws. The near miss draws two."""
        game, tamiyo, watched, unwatched = self.watched(builder)
        library = len(game.state.players[0].library)
        attack_with(game, {watched: 1, unwatched: 1})
        through_combat(game)

        assert loyalty(game, tamiyo) == 5
        assert len(game.state.players[0].library) == library - 1

    def test_the_unchosen_creature_alone_draws_nothing(self, builder):
        game, _tamiyo, _watched, unwatched = self.watched(builder)
        library = len(game.state.players[0].library)
        attack_with(game, {unwatched: 1})
        through_combat(game)

        assert len(game.state.players[0].library) == library

    def test_it_is_gone_by_your_next_turn(self, builder):
        """ "Until your next turn" -- the chosen bear connects on your next turn for nothing."""
        game, _tamiyo, watched, _unwatched = self.watched(builder)
        later(game, 0, Step.PRECOMBAT_MAIN)
        library = len(game.state.players[0].library)
        attack_with(game, {watched: 1})
        through_combat(game)

        assert lives(game)[1] == 38, "the premise: it connected"
        assert len(game.state.players[0].library) == library

    def test_minus_two_taps_two_and_they_skip_their_next_untap(self, builder):
        game, tamiyo = table(builder, "tamiyo_field_researcher", theirs=[BEAR, TRINKET])
        bear, trinket = only_oid(game, BEAR, 1), only_oid(game, TRINKET, 1)
        land = oids_of(game, PLAINS, 1)[0]
        offered = {t.id for a in activations(game, tamiyo, 1) for t in a.targets}
        assert land not in offered, "'nonland'"

        activate(game, tamiyo, 1, targets=[bear, trinket])
        settle_completely(game)
        assert loyalty(game, tamiyo) == 2
        later(game, 1, Step.UPKEEP)
        assert game.state.objects[bear].tapped and game.state.objects[trinket].tapped

    def emblem(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["tamiyo_field_researcher"], counters={"loyalty": 7})
            .battlefield(1, [PLAINS])
            .hand(0, [BEAR])
            .hand(1, [ANCHOR])
            .commander(0, [BEAR])
            .library(0, [PLAINS] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        tamiyo = only_oid(game, "tamiyo_field_researcher", 0)
        activate(game, tamiyo, 2)
        settle_completely(game)
        return game, tamiyo

    def test_minus_seven_draws_three_and_gives_the_emblem(self, builder):
        game, tamiyo = self.emblem(builder)

        assert game.state.objects[tamiyo].zone is Zone.GRAVEYARD
        assert len(game.state.players[0].hand) == 4
        assert len(game.state.players[0].library) == 17
        assert any(game.state.objects[o].def_id != BEAR for o in game.state.players[0].command)

    def test_the_emblem_casts_a_spell_from_hand_for_free(self, builder):
        """No lands at all, and the bear in hand is castable."""
        game, _tamiyo = self.emblem(builder)
        in_hand = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == BEAR)

        assert any(
            a.cast_free
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == in_hand
        )

    def test_the_emblem_does_not_free_the_command_zone(self, builder):
        """ "from your **hand**" -- the commander, same card, stays out of reach."""
        game, _tamiyo = self.emblem(builder)
        commander = game.state.players[0].commanders[0]

        assert not any(
            a.kind is ActionKind.CAST and a.source == commander for a in game.legal_actions()
        )


# ----------------------------------------------------------------------
# Teferi
# ----------------------------------------------------------------------


class TestTeferiTemporalArchmage:
    """ "+1: Look at the top two cards of your library. Put one of them into your
    hand and the other on the bottom of your library." / "-1: Untap up to four
    target permanents." / "-10: You get an emblem with 'You may activate loyalty
    abilities of planeswalkers you control on any player's turn any time you could
    cast an instant.'" / "Teferi, Temporal Archmage can be your commander."
    """

    def test_plus_one_takes_one_of_two_and_bottoms_the_other(self, builder):
        game, teferi = table(
            builder, "teferi_temporal_archmage", library0=[BEAR, BOLT, *[PLAINS] * 10]
        )
        activate(game, teferi, 0)
        settle_completely(game)
        hand = zone_ids(game, 0, "hand")
        library = zone_ids(game, 0, "library")

        assert loyalty(game, teferi) == 6
        assert (BEAR in hand) != (BOLT in hand), "exactly one of the two"
        assert library[-1] in {BEAR, BOLT} and library[-1] not in hand
        assert library[0] == PLAINS and len(library) == 11

    def test_minus_one_untaps_four_and_no_more(self, builder):
        """Every offer aims at four permanents at most; the four aimed at untap."""
        game, teferi = table(
            builder, "teferi_temporal_archmage", lands0=[PLAINS] * 5, tapped_lands=True
        )
        lands = oids_of(game, PLAINS, 0)
        offers_ = activations(game, teferi, 1)
        assert max(len(a.targets) for a in offers_) == 4

        action = next(a for a in offers_ if len(a.targets) == 4)
        aimed = {t.id for t in action.targets}
        game.apply(action)
        settle_completely(game)

        assert loyalty(game, teferi) == 4
        assert all(not game.state.objects[o].tapped for o in lands if o in aimed)
        assert all(game.state.objects[o].tapped for o in lands if o not in aimed)
        assert any(o not in aimed for o in lands), "the premise: a fifth land stayed tapped"

    def test_minus_ten_lets_you_activate_on_an_opponents_turn(self, builder):
        game, teferi = table(builder, "teferi_temporal_archmage", loyalty=11)
        activate(game, teferi, 2)
        settle_completely(game)
        assert loyalty(game, teferi) == 1
        assert len(game.state.players[0].command) == 1

        later(game, 1, Step.UPKEEP)
        assert "teferi_temporal_archmage" in offers(game, 0, ActionKind.ACTIVATE)

    def test_without_the_emblem_not_on_their_turn(self, builder):
        """The control for the above."""
        game, _teferi = table(builder, "teferi_temporal_archmage")
        later(game, 1, Step.UPKEEP)

        assert "teferi_temporal_archmage" not in offers(game, 0, ActionKind.ACTIVATE)

    def test_he_can_lead_a_deck(self, real_registry):
        deck = DeckList(
            id="t",
            name="T",
            commanders=("teferi_temporal_archmage",),
            color_identity=frozenset("U"),
            cards=((ISLAND, 99),),
        )

        assert real_registry.get("teferi_temporal_archmage").can_be_commander
        assert validate_deck(deck, real_registry) == []

    def test_a_planeswalker_without_the_line_cannot(self, real_registry):
        """The near miss is "any legendary planeswalker": Sorin prints no such line."""
        deck = DeckList(
            id="t",
            name="T",
            commanders=("sorin_grim_nemesis",),
            color_identity=frozenset("WB"),
            cards=((PLAINS, 99),),
        )

        assert not real_registry.get("sorin_grim_nemesis").can_be_commander
        assert validate_deck(deck, real_registry) != []


class TestTeferiTimeRaveler:
    """ "Each opponent can cast spells only any time they could cast a sorcery." /
    "+1: Until your next turn, you may cast sorcery spells as though they had
    flash." / "-3: Return up to one target artifact, creature, or enchantment to its
    owner's hand. Draw a card."
    """

    def lock(self, builder):
        return table(
            builder,
            "teferi_time_raveler",
            lands0=[ISLAND] * 3 + ["mountain"],
            lands1=["mountain"] * 2,
            hand0=[BOLT],
            hand1=[BOLT],
        )

    def test_an_opponent_cannot_cast_an_instant_on_your_turn(self, builder):
        game, _teferi = self.lock(builder)

        assert BOLT not in offers(game, 1, ActionKind.CAST)

    def test_you_still_can(self, builder):
        """ "Each **opponent**" -- the near miss locks its controller too."""
        game, _teferi = self.lock(builder)

        assert BOLT in offers(game, 0, ActionKind.CAST)

    def test_on_their_own_turn_they_wait_for_their_main_phase(self, builder):
        game, _teferi = self.lock(builder)
        later(game, 1, Step.UPKEEP)
        assert BOLT not in offers(game, 1, ActionKind.CAST), "not in their upkeep"

        later(game, 1, Step.PRECOMBAT_MAIN, turns=0)
        assert BOLT in offers(game, 1, ActionKind.CAST), "but in their main phase"

    def flashed(self, builder):
        game, teferi = table(
            builder,
            "teferi_time_raveler",
            lands0=[ISLAND] * 3 + [FOREST],
            hand0=[SORCERY, BEAR],
        )
        activate(game, teferi, 1)
        settle_completely(game)
        return game, teferi

    def test_plus_one_lets_you_cast_a_sorcery_on_their_turn(self, builder):
        game, teferi = self.flashed(builder)
        later(game, 1, Step.UPKEEP)

        assert loyalty(game, teferi) == 5
        assert SORCERY in offers(game, 0, ActionKind.CAST)

    def test_but_not_a_creature(self, builder):
        """ "sorcery spells" -- the bear stays at sorcery speed."""
        game, _teferi = self.flashed(builder)
        later(game, 1, Step.UPKEEP)

        assert BEAR not in offers(game, 0, ActionKind.CAST)

    def test_it_ends_when_your_next_turn_begins(self, builder):
        game, _teferi = self.flashed(builder)
        later(game, 0, Step.UPKEEP)

        assert SORCERY not in offers(game, 0, ActionKind.CAST)

    def test_minus_three_bounces_and_draws(self, builder):
        game, teferi = table(builder, "teferi_time_raveler", theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        library = len(game.state.players[0].library)
        activate(game, teferi, 2, targets=[bear])
        settle_completely(game)

        assert loyalty(game, teferi) == 1
        assert game.state.objects[bear].zone is Zone.HAND
        assert bear in game.state.players[1].hand, "its owner's hand"
        assert len(game.state.players[0].library) == library - 1

    def test_minus_three_with_no_target_still_draws(self, builder):
        """ "up to one" -- the draw is not conditional on the bounce."""
        game, teferi = table(builder, "teferi_time_raveler")
        library = len(game.state.players[0].library)
        activate(game, teferi, 2, targets=[])
        settle_completely(game)

        assert len(game.state.players[0].library) == library - 1


# ----------------------------------------------------------------------
# Vraska
# ----------------------------------------------------------------------


class TestVraskaTheUnseen:
    """ "+1: Until your next turn, whenever a creature deals combat damage to Vraska,
    destroy that creature." / "-3: Destroy target nonland permanent." / "-7: Create
    three 1/1 black Assassin creature tokens with 'Whenever this token deals combat
    damage to a player, that player loses the game.'"
    """

    def guarded(self, builder):
        game, vraska = table(builder, "vraska_the_unseen", theirs=[BEAR, BEAR])
        activate(game, vraska, 0)
        settle_completely(game)
        return game, vraska

    def test_plus_one_destroys_a_creature_that_hits_her_on_their_turn(self, builder):
        """Two bears swing: one at Vraska, one at you. Only the first dies."""
        game, vraska = self.guarded(builder)
        assert loyalty(game, vraska) == 6
        at_her, at_you = oids_of(game, BEAR, 1)
        later(game, 1, Step.UPKEEP)
        attack_with(game, {at_her: ("walker", vraska), at_you: 0})
        through_combat(game)

        assert loyalty(game, vraska) == 4
        assert game.state.objects[at_her].zone is Zone.GRAVEYARD
        assert game.state.objects[at_you].zone is Zone.BATTLEFIELD

    def test_it_is_over_by_their_following_turn(self, builder):
        """ "Until your next turn": a bear hitting her a full round later lives."""
        game, vraska = self.guarded(builder)
        bear = oids_of(game, BEAR, 1)[0]
        later(game, 1, Step.UPKEEP, turns=3)
        attack_with(game, {bear: ("walker", vraska)})
        through_combat(game)

        assert loyalty(game, vraska) == 4
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_minus_three_destroys_a_nonland_permanent(self, builder):
        game, vraska = table(builder, "vraska_the_unseen", theirs=[TRINKET])
        trinket = only_oid(game, TRINKET, 1)
        land = oids_of(game, PLAINS, 1)[0]
        offered = {t.id for a in activations(game, vraska, 1) for t in a.targets}
        assert land not in offered, "'nonland'"

        activate(game, vraska, 1, targets=[trinket])
        settle_completely(game)
        assert loyalty(game, vraska) == 2
        assert game.state.objects[trinket].zone is Zone.GRAVEYARD

    def test_minus_seven_assassins_make_the_player_they_hit_lose(self, builder):
        """Three seats: the player hit loses, the other plays on."""
        game, vraska = table(builder, "vraska_the_unseen", loyalty=7, players=3)
        activate(game, vraska, 2)
        settle_completely(game)
        assassins = tokens(game, "assassin_1_1_b_lose_game")
        assert len(assassins) == 3
        assert game.state.objects[vraska].zone is Zone.GRAVEYARD

        later(game, 0, Step.PRECOMBAT_MAIN)
        attack_with(game, {assassins[0].oid: 1})
        through_combat(game)

        assert game.state.players[1].has_lost
        assert not game.state.players[2].has_lost
        assert not game.over


class TestVraskaRelicSeeker:
    """ "+2: Create a 2/2 black Pirate creature token with menace." / "-3: Destroy
    target artifact, creature, or enchantment. Create a Treasure token." / "-10:
    Target player's life total becomes 1."
    """

    def test_plus_two_makes_a_menace_pirate(self, builder):
        game, vraska = table(builder, "vraska_relic_seeker")
        activate(game, vraska, 0)
        settle_completely(game)
        (pirate,) = tokens(game, "pirate_2_2_b_menace")

        assert loyalty(game, vraska) == 8
        assert pt(game, pirate.oid) == (2, 2)
        assert "menace" in keywords(game, pirate.oid)

    def test_minus_three_destroys_and_you_get_the_treasure(self, builder):
        game, vraska = table(builder, "vraska_relic_seeker", theirs=[TRINKET])
        trinket = only_oid(game, TRINKET, 1)
        land = oids_of(game, PLAINS, 1)[0]
        offered = {t.id for a in activations(game, vraska, 1) for t in a.targets}
        assert land not in offered, "artifact, creature or enchantment -- not land"

        activate(game, vraska, 1, targets=[trinket])
        settle_completely(game)
        assert loyalty(game, vraska) == 3
        assert game.state.objects[trinket].zone is Zone.GRAVEYARD
        assert len(tokens(game, "treasure_token", 0)) == 1
        assert tokens(game, "treasure_token", 1) == []

    def test_minus_ten_sets_the_target_to_one(self, builder):
        """35 becomes 1 -- "becomes", not "loses 19" -- and nobody else moves."""
        game, vraska = table(
            builder, "vraska_relic_seeker", loyalty=10, players=3, life={1: 35}
        )
        activate(game, vraska, 2, targets=[1])
        settle_completely(game)

        assert lives(game) == [40, 1, 40]
        assert game.state.objects[vraska].zone is Zone.GRAVEYARD
