"""The Atraxa, Praetors' Voice deck's counter engine, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. This deck is a superfriends list, and almost
every one of its support cards lives in that gate's blind spots:

- **It never activates an ability.** Karn's Bastion, Viral Drake, Tekuthal's
  indestructible counter and The Chain Veil's extra activation are activated
  abilities, and so is every loyalty ability the deck's payoffs exist to grow.
- **A trigger that never fires cannot be asserted.** Atraxa, Brokers Ascendancy
  and The Chain Veil all wait for an end step; Innkeeper's Talent waits for
  combat; Flux Channeler and Inexorable Tide wait for a *second* spell.
- **A choice the sandbox answers passively is invisible.** Proliferate is
  "choose any number", and the passive answer is "none" -- so a proliferate the
  gate saw resolve is one that chose nothing. What this deck does with the
  choice (grow its own walkers and an opponent's poison, never the opponent's
  walkers) is the card.
- **A replacement on a later event is invisible.** Tekuthal's "proliferate
  twice", Doubling Season's "twice that many", Oath of Gideon's extra loyalty
  and Innkeeper's Talent's level 3 each change something that happens after
  the card itself has resolved.

So the authored expectations are floors, and these are the observations. Each
class is one card, and each pins the **near miss** as well: the reading that
would be wrong if the card had been written the other way. The deck has some
famous ones -- Doubling Season doubles an effect's counters and *not* a +1
loyalty cost, Oath of Gideon adds loyalty on entry and *not* to a +N, and
Innkeeper's Talent's "if you would put" reaches both.

**Why every position holds an `ANCHOR`.** With no play available to anybody the
engine's auto-pass runs whole turns inside a single `apply`, and an end-step
trigger is overshot. A castable instant in each seat's hand, and an untapped
Plains to cast it with, is a reason for priority to stop.
"""

from __future__ import annotations

from automtg.engine import legality
from automtg.engine.characteristics import chars
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import (
    _default_answer,
    find_action,
    hand_ids,
    library_ids,
    oids_of,
    only_oid,
    pass_until,
)

PLAINS = "plains"
ISLAND = "island"
SWAMP = "swamp"
FOREST = "forest"
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- a reason for priority to stop
BEAR = "t_bear"  # {1}{G} 2/2 vanilla creature
WIZARD = "fugitive_wizard"  # a creature that carries no counters, for "only what has one"
WALKER = "t_walker"  # {2}{B} loyalty 4; "+1: You gain 2 life." / "-3: Draw a card."
OTHER_WALKER = "t_taunting_walker"  # loyalty 6, a second legendary name
THIRD_WALKER = "kasmina_enigma_sage"  # the deck's own, a third legendary name
ARTIFACT = "sol_ring"
ENCHANTMENT = "t_anthem"
KOR_ALLY = "kor_ally_1_1_w"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def obj_key(oid: int) -> tuple[str, int]:
    return ("object", oid)


def player_key(pid: int) -> tuple[str, int]:
    return ("player", pid)


def _key(ref) -> tuple[str, int]:
    return (ref.kind, ref.id)


def resolve(game, picks=(), *, targets=(), yes: bool = False, limit: int = 300) -> list[set]:
    """Let the stack empty, answering every proliferate with ``picks``.

    ``picks`` is one set of keys (`obj_key` / `player_key`) used for every
    proliferate, or a list of sets, one per proliferate in order -- Tekuthal's
    two are separate choices. ``targets`` are oids chosen in any other
    CHOOSE_OBJECTS decision. Returns the keys each proliferate *offered*, one set
    per proliferate decision, which is itself a measurement: an empty list means
    nothing proliferated.
    """
    per = list(picks) if isinstance(picks, list) else None
    offered: list[set] = []
    wanted: set = set()
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return offered
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            if decision.context.get("purpose") == "proliferate":
                if not decision.selected:
                    offered.append({_key(o.ref) for o in decision.options})
                    if per is not None:
                        wanted = set(per[len(offered) - 1]) if len(offered) <= len(per) else set()
                    else:
                        wanted = set(picks)
                choice = next(
                    (
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE and _key(a.targets[0]) in wanted
                    ),
                    None,
                )
            else:
                choice = next(
                    (
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE
                        and a.targets
                        and a.targets[0].kind == "object"
                        and a.targets[0].id in set(targets)
                    ),
                    None,
                )
            if choice is None:
                choice = find_action(game, ActionKind.FINISH_DECLARATION)
            game.apply(choice)
            continue
        if yes and decision.kind is DecisionKind.MAY:
            game.apply(find_action(game, ActionKind.YES))
            continue
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return offered
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack did not empty")


def cast_only(game, card_id: str, pid: int = 0) -> int:
    """Put ``card_id`` on the stack and stop, leaving its questions unanswered."""
    pass_until(
        game,
        lambda g: (
            g.pending() is not None
            and g.pending().player == pid
            and any(
                a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
                for a in g.legal_actions()
            )
        ),
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    return action.source


def cast_at(game, card_id: str, target: int, pid: int = 0) -> int:
    """Cast a single-target spell at ``target`` and stop."""
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().player == pid,
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and [t.id for t in a.targets] == [target]
    )
    game.apply(action)
    return action.source


def spell_targets(game, card_id: str) -> set[int]:
    """Every oid some cast action for ``card_id`` targets."""
    return {
        t.id
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for t in a.targets
        if t.kind == "object"
    }


def offers(game, pid: int, kind: ActionKind) -> set[str]:
    """The def_ids ``pid`` is offered ``kind`` for, read from legality directly."""
    return {
        game.state.objects[a.source].def_id
        for a in legality._priority_actions(game.state, pid)
        if a.kind is kind and a.source is not None
    }


def activations(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def plus_one(game, walker: int):
    return next(a for a in activations(game, walker) if "+1" in (a.label or ""))


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counter("loyalty")


def counters(game, oid: int) -> dict[str, int]:
    return {k: v for k, v in game.state.objects[oid].counters.items() if v}


def poison(game, pid: int) -> int:
    return game.state.players[pid].poison


def tokens(game, def_id: str, pid: int = 0) -> list:
    return [o for o in game.state.battlefield_objects(pid) if o.def_id == def_id and o.is_token]


def to_end_step(game, ender: int) -> None:
    pass_until(game, lambda g: g.state.step is Step.END_STEP and g.state.active_player == ender)


def attack_with(game, oids, defender: int = 1) -> None:
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )
    for oid in oids:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == "player" and t.id == defender for t in a.targets)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def proliferate_board(
    builder,
    *,
    extra=(),
    lands=(),
    hand=(),
    their_lands=(),
    their_hand=(),
    active: int = 0,
    step=None,
    talent_level=None,
):
    """The shared table every proliferate card is measured on.

    Player 0: a walker at 4, a Bear with one +1/+1 counter, a Wizard with no
    counters, one poison counter, ``extra`` and ``lands``. Player 1: a walker at
    4, a Bear with one -1/-1 counter, and three poison counters. Every kind of
    thing proliferate can grow is on it on both sides, so "it grew what it was
    told to and nothing else" has something to be wrong about.
    """
    b = (
        builder(players=2)
        .battlefield(0, [WALKER, WIZARD, PLAINS, *extra, *lands])
        .battlefield(0, [BEAR], counters={"+1/+1": 1})
        .battlefield(1, [WALKER, PLAINS, *their_lands])
        .battlefield(1, [BEAR], counters={"-1/-1": 1})
        .hand(0, [*hand, ANCHOR])
        .hand(1, [*their_hand, ANCHOR])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .active(active)
        .max_turns(6)
    )
    if step is not None:
        b = b.step(step)
    if talent_level is not None:
        b = b.battlefield(0, ["innkeeper_s_talent"], level=talent_level)
    game = b.build()
    game.state.players[0].poison = 1
    game.state.players[1].poison = 3
    return game


class Table:
    """The oids on `proliferate_board`, by role."""

    def __init__(self, game):
        self.my_walker = only_oid(game, WALKER, 0)
        self.my_bear = only_oid(game, BEAR, 0)
        self.wizard = only_oid(game, WIZARD, 0)
        self.their_walker = only_oid(game, WALKER, 1)
        self.their_bear = only_oid(game, BEAR, 1)


# ----------------------------------------------------------------------
# proliferate
# ----------------------------------------------------------------------


class TestAtraxaPraetorsVoice:
    """ "At the beginning of your end step, proliferate."

    The gate never reaches an end step, so the commander's only line of text was
    unobserved. And proliferate is a *choice*: the authored card has to offer
    every permanent and player with a counter, take exactly what is chosen, and
    leave the rest alone.
    """

    def end_step(self, builder, *, ender: int = 0, picks=()):
        game = proliferate_board(
            builder,
            extra=["atraxa_praetors_voice"],
            active=ender,
            step=Step.POSTCOMBAT_MAIN,
        )
        t = Table(game)
        to_end_step(game, ender)
        offered = resolve(game, picks(t) if callable(picks) else picks)
        return game, t, offered

    def test_it_offers_everything_with_a_counter_and_nothing_without(self, builder):
        game, t, offered = self.end_step(builder)

        assert len(offered) == 1, "one proliferate"
        assert offered[0] == {
            obj_key(t.my_walker),
            obj_key(t.my_bear),
            obj_key(t.their_walker),
            obj_key(t.their_bear),
            player_key(0),
            player_key(1),
        }
        assert obj_key(t.wizard) not in offered[0], "no counter, nothing to grow"
        assert obj_key(only_oid(game, "atraxa_praetors_voice")) not in offered[0]

    def test_it_grows_what_you_choose_and_only_that(self, builder):
        """The superfriends choice: your walker, your creature, their poison and
        their -1/-1 counters -- and *not* their walker or your own poison."""
        game, t, _ = self.end_step(
            builder,
            picks=lambda t: {
                obj_key(t.my_walker),
                obj_key(t.my_bear),
                obj_key(t.their_bear),
                player_key(1),
            },
        )

        assert loyalty(game, t.my_walker) == 5
        assert counters(game, t.my_bear) == {"+1/+1": 2}
        assert game.state.objects[t.their_bear].zone is Zone.GRAVEYARD, "a 2/2 with two -1/-1"
        assert poison(game, 1) == 4
        assert loyalty(game, t.their_walker) == 4, "declined"
        assert poison(game, 0) == 1, "declined"

    def test_declining_everything_changes_nothing(self, builder):
        game, t, offered = self.end_step(builder, picks=set())

        assert offered, "the premise: it did proliferate"
        assert loyalty(game, t.my_walker) == 4
        assert poison(game, 1) == 3

    def test_nothing_at_an_opponents_end_step(self, builder):
        """ "your end step"."""
        game, t, offered = self.end_step(builder, ender=1, picks=lambda t: {obj_key(t.my_walker)})

        assert offered == []
        assert loyalty(game, t.my_walker) == 4


class TestContentiousPlan:
    """ "Proliferate. Draw a card." The gate saw the draw and a proliferate that chose nothing."""

    def board(self, builder):
        return proliferate_board(builder, lands=[ISLAND, ISLAND], hand=["contentious_plan"])

    def test_it_proliferates_what_you_choose_and_draws(self, builder):
        game = self.board(builder)
        t = Table(game)
        hand = len(game.state.players[0].hand)
        cast_only(game, "contentious_plan")
        offered = resolve(game, {obj_key(t.my_walker), player_key(1)})

        assert len(offered) == 1
        assert loyalty(game, t.my_walker) == 5
        assert poison(game, 1) == 4
        assert loyalty(game, t.their_walker) == 4
        assert len(game.state.players[0].hand) == hand, "cast one, drew one"

    def test_choosing_nothing_still_draws(self, builder):
        game = self.board(builder)
        t = Table(game)
        library = len(game.state.players[0].library)
        cast_only(game, "contentious_plan")
        resolve(game, set())

        assert loyalty(game, t.my_walker) == 4
        assert len(game.state.players[0].library) == library - 1


class TestFluxChanneler:
    """ "Whenever you cast a noncreature spell, proliferate."

    A cast trigger, and the gate casts the card under test and nothing after it.
    """

    def board(self, builder, *, active: int = 0):
        return proliferate_board(
            builder,
            extra=["flux_channeler"],
            lands=[FOREST, FOREST],
            hand=[BEAR],
            active=active,
            step=Step.PRECOMBAT_MAIN,
        )

    def test_a_noncreature_spell_proliferates(self, builder):
        game = self.board(builder)
        t = Table(game)
        cast_only(game, ANCHOR)
        offered = resolve(game, {obj_key(t.my_walker)})

        assert len(offered) == 1
        assert loyalty(game, t.my_walker) == 5

    def test_a_creature_spell_does_not(self, builder):
        """ "**noncreature** spell"."""
        game = self.board(builder)
        t = Table(game)
        cast_only(game, BEAR)
        offered = resolve(game, {obj_key(t.my_walker)})

        assert offered == []
        assert loyalty(game, t.my_walker) == 4

    def test_an_opponents_spell_does_not(self, builder):
        """ "you cast"."""
        game = self.board(builder, active=1)
        t = Table(game)
        cast_only(game, ANCHOR, pid=1)
        offered = resolve(game, {obj_key(t.my_walker)})

        assert offered == []
        assert loyalty(game, t.my_walker) == 4


class TestInexorableTide:
    """ "Whenever you cast a spell, proliferate." -- any spell, unlike Flux Channeler."""

    def board(self, builder, *, active: int = 0):
        return proliferate_board(
            builder,
            extra=["inexorable_tide"],
            lands=[FOREST, FOREST],
            hand=[BEAR],
            active=active,
            step=Step.PRECOMBAT_MAIN,
        )

    def test_a_creature_spell_proliferates_too(self, builder):
        """The near miss is Flux Channeler's "noncreature"."""
        game = self.board(builder)
        t = Table(game)
        cast_only(game, BEAR)
        offered = resolve(game, {obj_key(t.my_walker), player_key(1)})

        assert len(offered) == 1
        assert loyalty(game, t.my_walker) == 5
        assert poison(game, 1) == 4

    def test_an_opponents_spell_does_not(self, builder):
        game = self.board(builder, active=1)
        t = Table(game)
        cast_only(game, ANCHOR, pid=1)
        offered = resolve(game, {obj_key(t.my_walker)})

        assert offered == []
        assert loyalty(game, t.my_walker) == 4


class TestKarnsBastion:
    """ "{4}, {T}: Proliferate." A land, so the gate counted permanents and stopped."""

    def board(self, builder, *, others: int = 4, tapped: bool = False):
        game = (
            builder(players=2)
            .battlefield(0, [WALKER, PLAINS, *[ISLAND] * others])
            .battlefield(0, ["karn_s_bastion"], tapped=tapped)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, "karn_s_bastion"), only_oid(game, WALKER, 0)

    def test_it_proliferates_and_taps(self, builder):
        game, bastion, walker = self.board(builder)
        actions = activations(game, bastion)
        assert len(actions) == 1, "the {C} ability is the solver's, not the action list's"
        game.apply(actions[0])
        offered = resolve(game, {obj_key(walker)})

        assert len(offered) == 1
        assert loyalty(game, walker) == 5
        assert game.state.objects[bastion].tapped

    def test_tapped_it_cannot(self, builder):
        """{T} is in the cost."""
        game, bastion, _walker = self.board(builder, tapped=True)

        assert activations(game, bastion) == []

    def test_the_four_cannot_come_from_itself(self, builder):
        """Four other mana sources plus the Plains is five; take two away and
        the Bastion's own {C} cannot make up the difference, because it taps
        for the cost."""
        game, bastion, _walker = self.board(builder, others=2)

        assert activations(game, bastion) == []


class TestViralDrake:
    """ "Infect" / "{3}{U}: Proliferate." -- repeatable, with no {T} in the cost."""

    def board(self, builder, lands: int = 8):
        game = proliferate_board(builder, extra=["viral_drake"], lands=[ISLAND] * lands)
        return game, Table(game), only_oid(game, "viral_drake")

    def test_it_proliferates(self, builder):
        game, t, drake = self.board(builder)
        game.apply(activations(game, drake)[0])
        offered = resolve(game, {player_key(1)})

        assert len(offered) == 1
        assert poison(game, 1) == 4
        assert loyalty(game, t.their_walker) == 4

    def test_it_can_be_activated_again_in_the_same_turn(self, builder):
        """No {T} and no once-each-turn: eight lands, two proliferates."""
        game, _t, drake = self.board(builder)
        game.apply(activations(game, drake)[0])
        resolve(game, {player_key(1)})
        again = activations(game, drake)
        assert again, "a second activation was not offered"
        game.apply(again[0])
        resolve(game, {player_key(1)})

        assert poison(game, 1) == 5

    def test_its_combat_damage_to_a_player_is_poison(self, builder):
        """Infect: one poison counter and no life lost."""
        game = (
            builder(players=2)
            .battlefield(0, ["viral_drake", PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(0)
            .step(Step.UPKEEP)
            .max_turns(2)
            .build()
        )
        life = game.state.players[1].life
        attack_with(game, [only_oid(game, "viral_drake")])
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert poison(game, 1) == 1
        assert game.state.players[1].life == life


class TestTekuthalInquiryDominus:
    """ "If you would proliferate, proliferate twice instead." / "{1}{U/P}{U/P},
    Remove three counters from among other artifacts, creatures, and planeswalkers
    you control: Put an indestructible counter on Tekuthal."

    A replacement on a later proliferate and an activated ability: the gate
    could see neither.
    """

    def board(self, builder, *, active: int = 0, caster: int = 0):
        game = proliferate_board(
            builder,
            extra=["tekuthal_inquiry_dominus"],
            lands=[ISLAND, ISLAND],
            hand=["contentious_plan"] if caster == 0 else [],
            their_lands=[ISLAND, ISLAND] if caster == 1 else [],
            their_hand=["contentious_plan"] if caster == 1 else [],
            active=active,
            step=Step.PRECOMBAT_MAIN,
        )
        return game, Table(game)

    def test_one_proliferate_becomes_two_separate_choices(self, builder):
        """Each repetition is its own choice: the walker the first time, only the
        poison the second -- not one choice applied twice."""
        game, t = self.board(builder)
        cast_only(game, "contentious_plan")
        offered = resolve(game, [{obj_key(t.my_walker)}, {player_key(1)}])

        assert len(offered) == 2
        assert loyalty(game, t.my_walker) == 5
        assert poison(game, 1) == 4

    def test_choosing_the_same_thing_twice_grows_it_by_two(self, builder):
        game, t = self.board(builder)
        cast_only(game, "contentious_plan")
        resolve(game, {obj_key(t.my_walker), player_key(1)})

        assert loyalty(game, t.my_walker) == 6
        assert poison(game, 1) == 5

    def test_an_opponents_proliferate_is_not_doubled(self, builder):
        """ "If **you** would proliferate"."""
        game, t = self.board(builder, active=1, caster=1)
        cast_only(game, "contentious_plan", pid=1)
        offered = resolve(game, {obj_key(t.their_walker)})

        assert len(offered) == 1
        assert loyalty(game, t.their_walker) == 5

    def ability_board(self, builder, *, mine=None, on_self=None, theirs=None):
        b = (
            builder(players=2)
            .battlefield(0, [PLAINS, *[ISLAND] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
        )
        b = b.battlefield(0, ["tekuthal_inquiry_dominus"], counters=on_self)
        if mine:
            b = b.battlefield(0, [BEAR], counters=mine)
        if theirs:
            b = b.battlefield(1, [BEAR], counters=theirs)
        game = b.build()
        return game, only_oid(game, "tekuthal_inquiry_dominus")

    def test_three_counters_buy_an_indestructible_counter(self, builder):
        game, tek = self.ability_board(builder, mine={"+1/+1": 3})
        bear = only_oid(game, BEAR, 0)
        actions = activations(game, tek)
        assert actions, "the ability was not offered"
        game.apply(actions[0])
        resolve(game, targets=[bear])

        assert counters(game, tek) == {"indestructible": 1}
        assert counters(game, bear) == {}
        assert "indestructible" in {str(k) for k in chars(game.state, tek).keywords}

    def test_two_counters_are_not_enough(self, builder):
        game, tek = self.ability_board(builder, mine={"+1/+1": 2})

        assert activations(game, tek) == []

    def test_counters_on_tekuthal_itself_do_not_pay(self, builder):
        """ "from among **other** artifacts, creatures, and planeswalkers"."""
        game, tek = self.ability_board(builder, on_self={"+1/+1": 3})

        assert activations(game, tek) == []

    def test_counters_on_an_opponents_creature_do_not_pay(self, builder):
        """ "…you control"."""
        game, tek = self.ability_board(builder, theirs={"+1/+1": 3})

        assert activations(game, tek) == []


# ----------------------------------------------------------------------
# counter doubling
# ----------------------------------------------------------------------


class TestDoublingSeason:
    """ "If an effect would create one or more tokens under your control, it
    creates twice that many of those tokens instead." / "If an effect would put
    one or more counters on a permanent you control, it puts twice that many of
    those counters on that permanent instead."

    Two replacements on later events, and the famous ruling the second carries:
    a planeswalker's +1 is a **cost**, not an effect, so it is not doubled.
    """

    def test_a_proliferate_on_your_walker_is_doubled(self, builder):
        game = proliferate_board(
            builder,
            extra=["doubling_season"],
            lands=[ISLAND, ISLAND],
            hand=["contentious_plan"],
        )
        t = Table(game)
        cast_only(game, "contentious_plan")
        resolve(game, {obj_key(t.my_walker), obj_key(t.their_walker), player_key(1)})

        assert loyalty(game, t.my_walker) == 6

    def test_an_opponents_walker_and_poison_are_not(self, builder):
        """ "on a permanent **you control**" -- and a player is not a permanent."""
        game = proliferate_board(
            builder,
            extra=["doubling_season"],
            lands=[ISLAND, ISLAND],
            hand=["contentious_plan"],
        )
        t = Table(game)
        cast_only(game, "contentious_plan")
        resolve(game, {obj_key(t.my_walker), obj_key(t.their_walker), player_key(1)})

        assert loyalty(game, t.their_walker) == 5
        assert poison(game, 1) == 4

    def test_a_plus_one_loyalty_cost_is_not_doubled(self, builder):
        """ "If **an effect** would put" -- a loyalty cost is a cost (118.1).

        The near miss is the most common Doubling Season misreading there is,
        and it would make every +1 in this deck a +2.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["doubling_season", WALKER, PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        walker = only_oid(game, WALKER, 0)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert loyalty(game, walker) == 5

    def test_a_walker_entering_has_its_loyalty_doubled(self, builder):
        """Starting loyalty is counters an effect puts on as it enters (the
        card's own ruling): a printed 4 arrives as 8."""
        game = (
            builder(players=2)
            .battlefield(0, ["doubling_season", PLAINS, *[SWAMP] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, [WALKER, ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, WALKER)
        resolve(game)

        assert loyalty(game, only_oid(game, WALKER, 0)) == 8

    def test_tokens_are_doubled(self, builder):
        """Oath of Gideon's two Kor Allies become four."""
        game = (
            builder(players=2)
            .battlefield(0, ["doubling_season", *[PLAINS] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, ["oath_of_gideon", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_gideon")
        resolve(game)

        assert len(tokens(game, KOR_ALLY)) == 4


class TestDeepglowSkate:
    """ "When this creature enters, double the number of each kind of counter on
    any number of target permanents."

    The gate's sandbox had nothing with counters on it to double.
    """

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WALKER, PLAINS, *[ISLAND] * 5])
            .battlefield(0, [BEAR], counters={"+1/+1": 2, "charge": 1})
            .battlefield(1, [WALKER, PLAINS])
            .hand(0, ["deepglow_skate", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        return game, only_oid(game, WALKER, 0), only_oid(game, BEAR, 0), only_oid(game, WALKER, 1)

    def target_decision(self, game):
        cast_only(game, "deepglow_skate")
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_OBJECTS,
        )
        return game.pending()

    def pick(self, game, *oids):
        """Answer the targeting one permanent at a time, then stop -- "any
        number" is asked as a pick-then-done, so any subset can be chosen."""
        self.target_decision(game)
        for oid in oids:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.targets and a.targets[0].id == oid
                )
            )
        done = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION), None
        )
        if done is not None:
            game.apply(done)

    def test_every_permanent_is_offered_one_at_a_time(self, builder):
        """Each legal permanent is its own option, so the choice is the player's
        rather than a list of pre-built subsets cut at the option limit."""
        game, walker, bear, theirs = self.board(builder)
        decision = self.target_decision(game)
        offered = {o.ref.id for o in decision.options if o.ref is not None}
        assert {walker, bear, theirs} <= offered
        assert decision.min_count == 0

    def test_it_doubles_each_kind_on_each_chosen_permanent(self, builder):
        """Every permanent chosen -- the option the engine offers first."""
        game, walker, bear, theirs = self.board(builder)
        self.pick(game, walker, bear, theirs)
        resolve(game)

        assert loyalty(game, walker) == 8
        assert counters(game, bear) == {"+1/+1": 4, "charge": 2}, "each kind"
        assert loyalty(game, theirs) == 8
        assert counters(game, only_oid(game, PLAINS, 1)) == {}, (
            "nothing to double stays nothing"
        )

    def test_it_can_double_just_your_own_two(self, builder):
        """ "any number of **target** permanents" -- the superfriends pick is your
        walker and your creature, and never the opponent's walker."""
        game, walker, bear, theirs = self.board(builder)
        self.pick(game, walker, bear)
        resolve(game)

        assert loyalty(game, walker) == 8
        assert counters(game, bear) == {"+1/+1": 4, "charge": 2}
        assert loyalty(game, theirs) == 4


class TestInnkeepersTalent:
    """ "At the beginning of combat on your turn, put a +1/+1 counter on target
    creature you control." / Level 2: "Permanents you control with counters on
    them have ward {1}." / Level 3: "If you would put one or more counters on a
    permanent or player, put twice that many of each of those kinds of counters
    on that permanent or player instead."

    A combat trigger, two level abilities the gate never buys, and a level-3
    replacement whose wording is the opposite of Doubling Season's on both of
    its axes: "if **you** would put", so a loyalty cost counts, and "permanent
    **or player**", so an opponent's permanent and poison count too.
    """

    def combat(self, builder, *, active: int = 0, level: int = 1):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, BEAR])
            .battlefield(0, ["innkeeper_s_talent"], level=level)
            .battlefield(1, [PLAINS, BEAR])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(active)
            .step(Step.UPKEEP)
            .max_turns(3)
            .build()
        )
        pass_until(game, lambda g: g.state.step is Step.BEGIN_COMBAT)
        resolve(game)
        return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

    def test_beginning_of_combat_counters_your_creature(self, builder):
        game, mine, theirs = self.combat(builder)

        assert counters(game, mine) == {"+1/+1": 1}
        assert counters(game, theirs) == {}, "target creature **you** control"

    def test_not_on_an_opponents_turn(self, builder):
        """ "on **your** turn"."""
        game, mine, _theirs = self.combat(builder, active=1)

        assert counters(game, mine) == {}

    def test_level_three_doubles_the_combat_counter(self, builder):
        game, mine, _theirs = self.combat(builder, level=3)

        assert counters(game, mine) == {"+1/+1": 2}

    def ward(self, builder, *, level: int, with_counter: bool):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS])
            .battlefield(0, ["innkeeper_s_talent"], level=level)
            .battlefield(0, [BEAR], counters={"+1/+1": 1} if with_counter else None)
            .battlefield(1, [SWAMP, FOREST, FOREST])
            .hand(0, [ANCHOR])
            .hand(1, ["putrefy"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        cast_at(game, "putrefy", bear, pid=1)
        resolve(game)
        return game, bear

    def test_level_two_wards_a_permanent_with_a_counter(self, builder):
        """The opponent spent all three lands on Putrefy and cannot pay {1}."""
        game, bear = self.ward(builder, level=2, with_counter=True)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_level_two_does_not_ward_one_without(self, builder):
        """ "with counters on them"."""
        game, bear = self.ward(builder, level=2, with_counter=False)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_level_one_wards_nothing(self, builder):
        game, bear = self.ward(builder, level=1, with_counter=True)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_level_three_doubles_a_plus_one_loyalty_cost(self, builder):
        """ "If **you** would put" -- unlike Doubling Season, a cost counts."""
        game = (
            builder(players=2)
            .battlefield(0, [WALKER, PLAINS])
            .battlefield(0, ["innkeeper_s_talent"], level=3)
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        walker = only_oid(game, WALKER, 0)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert loyalty(game, walker) == 6

    def level_three_proliferate(self, builder):
        game = proliferate_board(
            builder, lands=[ISLAND, ISLAND], hand=["contentious_plan"], talent_level=3
        )
        t = Table(game)
        cast_only(game, "contentious_plan")
        resolve(game, {obj_key(t.my_walker), obj_key(t.their_walker), player_key(1)})
        return game, t

    def test_level_three_doubles_your_proliferate_on_any_permanent(self, builder):
        """ "on a permanent" -- not only one you control, which Doubling Season says."""
        game, t = self.level_three_proliferate(builder)

        assert loyalty(game, t.my_walker) == 6
        assert loyalty(game, t.their_walker) == 6

    def test_level_three_doubles_your_proliferate_on_a_player(self, builder):
        """ "…on a permanent **or player**": their three poison become five."""
        game, _t = self.level_three_proliferate(builder)

        assert poison(game, 1) == 5


class TestBrokersAscendancy:
    """ "At the beginning of your end step, put a +1/+1 counter on each creature
    you control and a loyalty counter on each planeswalker you control." """

    def end_step(self, builder, *, ender: int = 0):
        game = (
            builder(players=2)
            .battlefield(0, ["brokers_ascendancy", WALKER, BEAR, PLAINS])
            .battlefield(1, [WALKER, BEAR, PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(ender)
            .step(Step.POSTCOMBAT_MAIN)
            .max_turns(6)
            .build()
        )
        to_end_step(game, ender)
        resolve(game)
        return game

    def test_your_creatures_and_walkers_grow(self, builder):
        game = self.end_step(builder)

        assert counters(game, only_oid(game, BEAR, 0)) == {"+1/+1": 1}
        assert loyalty(game, only_oid(game, WALKER, 0)) == 5

    def test_an_opponents_do_not(self, builder):
        """ "…you control", on both halves."""
        game = self.end_step(builder)

        assert counters(game, only_oid(game, BEAR, 1)) == {}
        assert loyalty(game, only_oid(game, WALKER, 1)) == 4

    def test_nothing_at_an_opponents_end_step(self, builder):
        game = self.end_step(builder, ender=1)

        assert counters(game, only_oid(game, BEAR, 0)) == {}
        assert loyalty(game, only_oid(game, WALKER, 0)) == 4


# ----------------------------------------------------------------------
# the Oaths
# ----------------------------------------------------------------------


class TestOathOfGideon:
    """ "When Oath of Gideon enters, create two 1/1 white Kor Ally creature
    tokens." / "Each planeswalker you control enters with an additional loyalty
    counter on it."

    The static changes a *later* walker's arrival, and the near miss is the
    tempting implementation -- a counter replacement with an addend -- which
    would also add one to every +N loyalty cost. The printed card never does.
    """

    def oath_board(self, builder, *, active: int = 0):
        return (
            builder(players=2)
            .battlefield(0, ["oath_of_gideon", PLAINS, *[SWAMP] * 3])
            .battlefield(1, [PLAINS, *[SWAMP] * 3])
            .hand(0, [WALKER, ANCHOR])
            .hand(1, [WALKER, ANCHOR])
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )

    def test_it_makes_two_kor_allies(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, ["oath_of_gideon", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_gideon")
        resolve(game)
        made = tokens(game, KOR_ALLY)

        assert len(made) == 2
        c = chars(game.state, made[0].oid)
        assert (c.power, c.toughness) == (1, 1)
        assert {"Kor", "Ally"} <= set(c.subtypes)

    def test_a_walker_you_cast_enters_with_one_more(self, builder):
        game = self.oath_board(builder)
        cast_only(game, WALKER)
        resolve(game)

        assert loyalty(game, only_oid(game, WALKER, 0)) == 5

    def test_but_its_plus_one_is_still_plus_one(self, builder):
        """5 -> 6, not 5 -> 7."""
        game = self.oath_board(builder)
        cast_only(game, WALKER)
        resolve(game)
        walker = only_oid(game, WALKER, 0)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert loyalty(game, walker) == 6

    def test_an_opponents_walker_enters_with_its_printed_loyalty(self, builder):
        """ "Each planeswalker **you control**"."""
        game = self.oath_board(builder, active=1)
        cast_only(game, WALKER, pid=1)
        resolve(game)

        assert loyalty(game, only_oid(game, WALKER, 1)) == 4


class TestOathOfAjani:
    """ "When Oath of Ajani enters, put a +1/+1 counter on each creature you
    control." / "Planeswalker spells you cast cost {1} less to cast." """

    def test_it_counters_each_creature_you_control(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, WIZARD, PLAINS, FOREST])
            .battlefield(1, [BEAR, PLAINS])
            .hand(0, ["oath_of_ajani", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_ajani")
        resolve(game)

        assert counters(game, only_oid(game, BEAR, 0)) == {"+1/+1": 1}
        assert counters(game, only_oid(game, WIZARD, 0)) == {"+1/+1": 1}, "each, not one"
        assert counters(game, only_oid(game, BEAR, 1)) == {}, "…you control"

    def discount_board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["oath_of_ajani", PLAINS])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .build()
        )

    def discount(self, game, card_id: str, pid: int = 0) -> int:
        return cost_reduction(game.state, pid, game.state.registry.get(card_id))

    def test_a_planeswalker_spell_costs_one_less(self, builder):
        assert self.discount(self.discount_board(builder), WALKER) == 1

    def test_a_creature_spell_does_not(self, builder):
        """ "**Planeswalker** spells"."""
        assert self.discount(self.discount_board(builder), BEAR) == 0

    def test_an_opponents_walker_does_not(self, builder):
        """ "…you cast"."""
        assert self.discount(self.discount_board(builder), WALKER, pid=1) == 0

    def priced(self, builder, *, oath: bool):
        return (
            builder(players=2)
            .battlefield(0, [SWAMP, SWAMP] + (["oath_of_ajani"] if oath else []))
            .hand(0, [WALKER])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_the_discount_is_charged_at_the_boundary(self, builder):
        """{2}{B} less {1} is {1}{B}: two Swamps."""
        assert WALKER in offers(self.priced(builder, oath=True), 0, ActionKind.CAST)

    def test_and_without_it_two_swamps_are_a_land_short(self, builder):
        assert WALKER not in offers(self.priced(builder, oath=False), 0, ActionKind.CAST)


class TestOathOfNissa:
    """ "When Oath of Nissa enters, look at the top three cards of your library.
    You may reveal a creature, land, or planeswalker card from among them and put
    it into your hand. Put the rest on the bottom of your library in any order."
    / "You may spend mana as though it were mana of any color to cast
    planeswalker spells." """

    def dig(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS, FOREST])
            .battlefield(1, [PLAINS])
            .hand(0, ["oath_of_nissa", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "oath_of_nissa")
        top = game.state.players[0].library[:3]
        resolve(game, targets=top)
        return game

    def test_it_takes_a_planeswalker(self, builder):
        game = self.dig(builder, [ANCHOR, WALKER, ANCHOR, *[PLAINS] * 6])

        assert WALKER in hand_ids(game)
        assert library_ids(game)[-2:] == [ANCHOR, ANCHOR], "the rest to the bottom"

    def test_it_takes_a_creature(self, builder):
        game = self.dig(builder, [BEAR, ANCHOR, ANCHOR, *[PLAINS] * 6])

        assert BEAR in hand_ids(game)

    def test_an_instant_is_not_offered(self, builder):
        """ "a creature, land, or planeswalker card"."""
        game = self.dig(builder, [ANCHOR, ANCHOR, ANCHOR, *[ISLAND] * 6])

        assert hand_ids(game).count(ANCHOR) == 1, "only the anchor it started with"
        assert library_ids(game)[-3:] == [ANCHOR] * 3

    def test_it_looks_at_three_and_no_further(self, builder):
        game = self.dig(builder, [ANCHOR, ANCHOR, ANCHOR, WALKER, *[PLAINS] * 5])

        assert WALKER not in hand_ids(game)
        assert library_ids(game)[0] == WALKER

    def priced(self, builder, *, oath: bool, card: str):
        return (
            builder(players=2)
            .battlefield(0, [FOREST] * 3 + (["oath_of_nissa"] if oath else []))
            .hand(0, [card])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_green_mana_casts_a_black_planeswalker(self, builder):
        assert WALKER in offers(self.priced(builder, oath=True, card=WALKER), 0, ActionKind.CAST)

    def test_and_without_it_it_cannot(self, builder):
        assert WALKER not in offers(self.priced(builder, oath=False, card=WALKER), 0, ActionKind.CAST)

    def test_the_any_color_mana_is_only_for_planeswalkers(self, builder):
        """ "…to cast **planeswalker** spells" -- a {W} instant still needs white."""
        assert ANCHOR not in offers(self.priced(builder, oath=True, card=ANCHOR), 0, ActionKind.CAST)


# ----------------------------------------------------------------------
# lands and removal
# ----------------------------------------------------------------------


class TestRuptureSpire:
    """ "This land enters tapped." / "When this land enters, sacrifice it unless
    you pay {1}." / "{T}: Add one mana of any color." """

    def play(self, builder, *, lands=(PLAINS,), pay: bool):
        game = (
            builder(players=2)
            .battlefield(0, list(lands))
            .battlefield(1, [PLAINS])
            .hand(0, ["rupture_spire", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.PLAY_LAND
                and game.state.objects[a.source].def_id == "rupture_spire"
            )
        )
        resolve(game, yes=pay)
        return game

    def test_paying_keeps_it_and_it_entered_tapped(self, builder):
        game = self.play(builder, pay=True)
        spire = only_oid(game, "rupture_spire", 0)

        assert game.state.objects[spire].tapped
        assert game.state.objects[only_oid(game, PLAINS, 0)].tapped, "the {1} was paid"

    def test_declining_sacrifices_it(self, builder):
        game = self.play(builder, pay=False)

        assert oids_of(game, "rupture_spire", 0) == []
        assert "rupture_spire" in [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ]

    def test_with_nothing_to_pay_with_it_is_sacrificed(self, builder):
        game = self.play(builder, lands=(), pay=True)

        assert oids_of(game, "rupture_spire", 0) == []

    def priced(self, builder, card: str):
        return (
            builder(players=2)
            .battlefield(0, ["rupture_spire"])
            .hand(0, [card])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_it_taps_for_white(self, builder):
        assert ANCHOR in offers(self.priced(builder, ANCHOR), 0, ActionKind.CAST)

    def test_and_for_blue(self, builder):
        """A second colour, so "any color" is not one hard-coded colour."""
        game = (
            builder(players=2)
            .battlefield(0, ["rupture_spire", PLAINS])
            .hand(0, ["contentious_plan"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

        assert "contentious_plan" in offers(game, 0, ActionKind.CAST)


class TestPutrefy:
    """ "Destroy target artifact or creature. It can't be regenerated." """

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS, SWAMP, FOREST, FOREST])
            .battlefield(1, [BEAR, ARTIFACT, ENCHANTMENT, WALKER, "t_regenerator", FOREST])
            .hand(0, ["putrefy", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .max_turns(3)
            .build()
        )

    def test_it_targets_artifacts_and_creatures_only(self, builder):
        game = self.board(builder)
        legal = spell_targets(game, "putrefy")

        assert only_oid(game, BEAR, 1) in legal
        assert only_oid(game, ARTIFACT, 1) in legal
        assert only_oid(game, ENCHANTMENT, 1) not in legal
        assert only_oid(game, WALKER, 1) not in legal

    def test_it_destroys_an_artifact(self, builder):
        game = self.board(builder)
        ring = only_oid(game, ARTIFACT, 1)
        cast_at(game, "putrefy", ring)
        resolve(game)

        assert game.state.objects[ring].zone is Zone.GRAVEYARD

    def test_a_regeneration_shield_does_not_save_it(self, builder):
        """The opponent regenerates in response, and the troll dies anyway."""
        game = self.board(builder)
        troll = only_oid(game, "t_regenerator", 1)
        cast_at(game, "putrefy", troll)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 1)
        regen = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == troll
        )
        game.apply(regen)
        pass_until(
            game,
            lambda g: g.state.objects[troll].regeneration_shields > 0
            or g.state.objects[troll].zone is not Zone.BATTLEFIELD,
        )
        assert game.state.objects[troll].regeneration_shields == 1, "the premise: a shield"
        resolve(game)

        assert game.state.objects[troll].zone is Zone.GRAVEYARD


class TestFracture:
    """ "Destroy target artifact, enchantment, or planeswalker." """

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [PLAINS, PLAINS, SWAMP])
            .battlefield(1, [BEAR, ARTIFACT, ENCHANTMENT, WALKER, PLAINS])
            .hand(0, ["fracture", ANCHOR])
            .hand(1, [ANCHOR])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_it_targets_all_three_and_not_a_creature(self, builder):
        game = self.board(builder)
        legal = spell_targets(game, "fracture")

        assert {
            only_oid(game, ARTIFACT, 1),
            only_oid(game, ENCHANTMENT, 1),
            only_oid(game, WALKER, 1),
        } <= legal
        assert only_oid(game, BEAR, 1) not in legal

    def test_it_destroys_a_planeswalker(self, builder):
        game = self.board(builder)
        walker = only_oid(game, WALKER, 1)
        cast_at(game, "fracture", walker)
        resolve(game)

        assert game.state.objects[walker].zone is Zone.GRAVEYARD


# ----------------------------------------------------------------------
# finding planeswalkers
# ----------------------------------------------------------------------


class TestCallTheGatewatch:
    """ "Search your library for a planeswalker card, reveal it, put it into your
    hand, then shuffle." """

    def search(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 3])
            .battlefield(1, [PLAINS])
            .hand(0, ["call_the_gatewatch", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "call_the_gatewatch")
        resolve(game, targets=list(game.state.players[0].library))
        return game

    def test_it_finds_a_planeswalker(self, builder):
        game = self.search(builder, [BEAR, ARTIFACT, WALKER, *[PLAINS] * 5])

        assert WALKER in hand_ids(game)
        assert WALKER not in library_ids(game)

    def test_it_finds_nothing_else(self, builder):
        """ "a **planeswalker** card"."""
        game = self.search(builder, [BEAR, ARTIFACT, *[PLAINS] * 5])

        assert BEAR not in hand_ids(game)
        assert ARTIFACT not in hand_ids(game)
        assert len(game.state.players[0].library) == 7


class TestDeployTheGatewatch:
    """ "Look at the top seven cards of your library. Put up to two planeswalker
    cards from among them onto the battlefield. Put the rest on the bottom of
    your library in a random order." """

    def deploy(self, builder, library):
        game = (
            builder(players=2)
            .battlefield(0, [*[PLAINS] * 6])
            .battlefield(1, [PLAINS])
            .hand(0, ["deploy_the_gatewatch", ANCHOR])
            .hand(1, [ANCHOR])
            .library(0, list(library))
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        cast_only(game, "deploy_the_gatewatch")
        top = game.state.players[0].library[:7]
        resolve(game, targets=top)
        return game

    def test_up_to_two_walkers_enter_with_their_loyalty(self, builder):
        game = self.deploy(
            builder,
            [WALKER, BEAR, OTHER_WALKER, THIRD_WALKER, PLAINS, PLAINS, PLAINS, ISLAND, ISLAND],
        )
        arrived = [
            o for o in game.state.battlefield_objects(0)
            if o.def_id in (WALKER, OTHER_WALKER, THIRD_WALKER)
        ]

        assert len(arrived) == 2, "up to **two**, with three on offer"
        assert all(o.counter("loyalty") > 0 for o in arrived)
        left = [d for d in library_ids(game) if d in (WALKER, OTHER_WALKER, THIRD_WALKER)]
        assert len(left) == 1, "the third went to the bottom"

    def test_the_rest_go_to_the_bottom(self, builder):
        game = self.deploy(
            builder,
            [WALKER, BEAR, PLAINS, PLAINS, PLAINS, PLAINS, PLAINS, ISLAND, ISLAND],
        )

        assert oids_of(game, WALKER, 0), "the walker came in"
        assert oids_of(game, BEAR, 0) == [], "a creature is not a planeswalker"
        assert library_ids(game)[:2] == [ISLAND, ISLAND], "the six seen are under the unseen two"

    def test_it_looks_at_seven_and_no_further(self, builder):
        game = self.deploy(builder, [*[PLAINS] * 7, WALKER, ISLAND])

        assert oids_of(game, WALKER, 0) == []
        assert library_ids(game)[0] == WALKER


# ----------------------------------------------------------------------
# The Chain Veil
# ----------------------------------------------------------------------


class TestTheChainVeil:
    """ "At the beginning of your end step, if you didn't activate a loyalty
    ability of a planeswalker this turn, you lose 2 life." / "{4}, {T}: For each
    planeswalker you control, you may activate one of its loyalty abilities once
    this turn as though none of its loyalty abilities have been activated this
    turn."

    An end-step trigger with an intervening if, and an activated ability that
    changes what is offered *afterwards*: both invisible to the gate.
    """

    def board(self, builder, *, ender: int = 0, step=Step.PRECOMBAT_MAIN):
        game = (
            builder(players=2)
            .battlefield(0, ["the_chain_veil", WALKER, PLAINS, *[SWAMP] * 4])
            .battlefield(1, [PLAINS])
            .hand(0, [ANCHOR])
            .hand(1, [ANCHOR])
            .active(ender)
            .step(step)
            .max_turns(6)
            .build()
        )
        return game, only_oid(game, "the_chain_veil", 0), only_oid(game, WALKER, 0)

    def test_no_loyalty_activation_costs_two_life(self, builder):
        game, _veil, _walker = self.board(builder, step=Step.POSTCOMBAT_MAIN)
        life = game.state.players[0].life
        to_end_step(game, 0)
        resolve(game)

        assert game.state.players[0].life == life - 2

    def test_a_loyalty_activation_avoids_it(self, builder):
        """+1 gains 2, and the Veil takes nothing back."""
        game, _veil, walker = self.board(builder)
        life = game.state.players[0].life
        game.apply(plus_one(game, walker))
        resolve(game)
        to_end_step(game, 0)
        resolve(game)

        assert game.state.players[0].life == life + 2

    def test_nothing_at_an_opponents_end_step(self, builder):
        """ "your end step"."""
        game, _veil, _walker = self.board(builder, ender=1, step=Step.POSTCOMBAT_MAIN)
        life = game.state.players[0].life
        to_end_step(game, 1)
        resolve(game)

        assert game.state.players[0].life == life

    def test_a_second_activation_is_not_offered_without_it(self, builder):
        """606.3, the control for the next test."""
        game, _veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert activations(game, walker) == []

    def test_the_veil_grants_one_more_loyalty_activation(self, builder):
        game, veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)
        game.apply(activations(game, veil)[0])
        resolve(game)

        assert game.state.objects[veil].tapped
        game.apply(plus_one(game, walker))
        resolve(game)
        assert loyalty(game, walker) == 6

    def test_and_only_one(self, builder):
        """ "once this turn" -- the third is not offered."""
        game, veil, walker = self.board(builder)
        game.apply(plus_one(game, walker))
        resolve(game)
        game.apply(activations(game, veil)[0])
        resolve(game)
        game.apply(plus_one(game, walker))
        resolve(game)

        assert activations(game, walker) == []
