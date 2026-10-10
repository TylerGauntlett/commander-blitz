""""…create a token that's tapped and attacking that player **or a planeswalker
they control**."

    Adeline, Resplendent Cathar — "Whenever you attack, for each opponent,
    create a 1/1 white Human creature token that's tapped and attacking that
    player or a planeswalker they control."

`create_token`'s `attacking` could name a *seat* (Ainok Strike Leader, see
`test_token_attacking_player.py`) and nothing else. The token joined
`combat.attackers` against the player and there was no way to aim it at a
permanent, although a declared attacker has been able to attack a planeswalker
since planeswalkers shipped (`combat.add_attacker(permanent=...)`).

That is a narrower card, not a rougher one. Rule 506.2 makes a planeswalker a
third kind of thing to attack, and attacking somebody's planeswalker is not
attacking them — the line this engine draws for Ghostly Prison and goad. Rule
508.4 says who picks for a creature that enters attacking: its **controller**,
as it enters, among what the effect allows. Adeline's sentence allows the named
opponent or any planeswalker that opponent controls; an Adeline that could only
ever hit the seat drops a choice its controller makes every combat, on exactly
the boards where the walker is the reason to attack.

So `or_planeswalker: true` beside `attacking`. The choice is an existing
`ask_targets` question (a player ref and object refs in one list, purpose
``"attack"``) — no new decision kind — and the answer is written where a
declared attack at a walker is written: `attackers[oid]` stays the defending
player and `attacking_permanent[oid]` names the walker, so combat damage
(508.1, 506.4c) needs nothing new.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.authoring.packet import reference
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import _default_answer, oids_of, only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"  # loyalty 4, legendary
HUMAN = "human_1_1_w"
#: Adeline's whole card: vigilance, power equal to the number of creatures you
#: control, and the attack trigger this file is about.
CATHAR = "t_resplendent_marshal"


def position(builder, *, players: int = 2, walkers=(), p0=(), bears: int = 1, hand=()):
    """Player 0 with ``bears`` to swing; a planeswalker at each seat in ``walkers``."""
    b = builder(players=players)
    b.battlefield(0, [*([BEAR] * bears), *p0])
    b.hand(0, list(hand))
    b.library(0, ["swamp"] * 20)
    for pid in range(1, players):
        if pid in walkers:
            b.battlefield(pid, [WALKER])
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def declare(game, defender: int = 1) -> int:
    """Swing player 0's first bear at ``defender``'s face and close the declaration."""
    for _ in range(120):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    bear = oids_of(game, BEAR, 0)[0]
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == bear
            and any(t.kind == "player" and t.id == defender for t in a.targets)
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    return bear


def token(**spec) -> dict:
    return {"op": "create_token", "token": HUMAN, "tapped": True, **spec}


def drive(game, effects, answers=(), *, controller: int = 0, bindings=None):
    """Resolve ``effects`` directly, answering each decision from ``answers``.

    ``answers`` is a list of callables, each handed the pending decision and
    returning the option ordinal. Returns ``(new oids, decisions asked)``; a
    decision beyond the answers supplied fails the test, which is how "nothing
    is asked" is asserted.
    """
    before = set(game.state.objects)
    ctx = EffectContext(
        state=game.state, controller=controller, bindings=dict(bindings or {})
    )
    gen = execute(ctx, effects)
    asked = []
    pending = list(answers)
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            assert pending, f"asked a question nobody expected: {decision.prompt}"
            decision = gen.send([pending.pop(0)(decision)])
    except StopIteration:
        pass
    return [oid for oid in game.state.objects if oid not in before], asked


def pick_object(decision) -> int:
    return next(i for i, o in enumerate(decision.options) if o.ref.kind == "object")


def pick_player(decision) -> int:
    return next(i for i, o in enumerate(decision.options) if o.ref.kind == "player")


class TestNoPlaneswalkerNothingIsAsked:
    """With nothing but the seat to attack, the sentence is Ainok's sentence."""

    def test_the_token_attacks_the_player_without_a_question(self, builder):
        game = position(builder)
        declare(game)
        made, asked = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            bindings={"each_player": 1},
        )

        assert asked == []
        assert game.state.combat.attackers[made[0]] == 1
        assert made[0] not in game.state.combat.attacking_permanent

    def test_a_walker_at_another_seat_is_not_offered(self, builder):
        """"A planeswalker **they** control" -- the named seat's, nobody else's."""
        game = position(builder, players=3, walkers=(2,))
        declare(game)
        made, asked = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            bindings={"each_player": 1},
        )

        assert asked == []
        assert game.state.combat.attackers[made[0]] == 1

    def test_my_own_walker_is_not_offered(self, builder):
        game = position(builder, p0=[WALKER])
        declare(game)
        _, asked = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            bindings={"each_player": 1},
        )

        assert asked == []

    def test_without_the_key_a_walker_is_never_offered(self, builder):
        """Ainok's cards keep reading the way they were written."""
        game = position(builder, walkers=(1,))
        declare(game)
        made, asked = drive(
            game, [token(attacking={"binding": "each_player"})], bindings={"each_player": 1}
        )

        assert asked == []
        assert made[0] not in game.state.combat.attacking_permanent


class TestTheControllerChooses:
    """508.4: the token's controller picks, among the seat and its walkers."""

    def test_the_seat_and_its_walker_are_both_offered(self, builder):
        game = position(builder, walkers=(1,))
        declare(game)
        walker = only_oid(game, WALKER, 1)
        _, asked = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            [pick_player], bindings={"each_player": 1},
        )

        (decision,) = asked
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "attack", "not a target: nothing is targeted"
        assert {(o.ref.kind, o.ref.id) for o in decision.options} == {
            ("player", 1),
            ("object", walker),
        }
        assert (decision.min_count, decision.max_count) == (1, 1)

    def test_choosing_the_walker_records_the_token_against_it(self, builder):
        game = position(builder, walkers=(1,))
        declare(game)
        walker = only_oid(game, WALKER, 1)
        made, _ = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            [pick_object], bindings={"each_player": 1},
        )

        assert game.state.combat.attacking_permanent[made[0]] == walker
        assert game.state.combat.attackers[made[0]] == 1, "506.2: its controller is still the defender"

    def test_choosing_the_player_records_no_walker(self, builder):
        game = position(builder, walkers=(1,))
        declare(game)
        made, _ = drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            [pick_player], bindings={"each_player": 1},
        )

        assert game.state.combat.attackers[made[0]] == 1
        assert made[0] not in game.state.combat.attacking_permanent

    def test_the_tokens_controller_is_who_is_asked(self, builder):
        """Not the effect's controller: a token another player creates is
        theirs to aim."""
        game = position(builder, players=3, walkers=(1,))
        declare(game)
        _, asked = drive(
            game,
            [token(attacking={"binding": "each_player"}, or_planeswalker=True,
                   controller={"binding": "maker"})],
            [pick_player],
            bindings={"each_player": 1, "maker": 2},
        )

        assert asked[0].player == 2

    def test_each_token_chooses_for_itself(self, builder):
        """508.4 is per creature: two tokens may split between face and walker."""
        game = position(builder, walkers=(1,))
        declare(game)
        walker = only_oid(game, WALKER, 1)
        made, asked = drive(
            game,
            [token(attacking={"binding": "each_player"}, or_planeswalker=True,
                   amount={"const": 2})],
            [pick_object, pick_player],
            bindings={"each_player": 1},
        )

        assert len(asked) == 2
        assert [game.state.combat.attacking_permanent.get(oid) for oid in made] == [walker, None]
        assert all(game.state.combat.attackers[oid] == 1 for oid in made)

    def test_the_boolean_form_widens_the_same_way(self, builder):
        """`attacking: true` names the seat the source is pointed at; the key
        offers that seat's walkers."""
        game = position(builder, walkers=(1,))
        bear = declare(game)
        walker = only_oid(game, WALKER, 1)
        before = set(game.state.objects)
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        gen = execute(ctx, [token(attacking=True, or_planeswalker=True)])
        decision = next(gen)
        with pytest.raises(StopIteration):
            gen.send([pick_object(decision)])
        (made,) = [oid for oid in game.state.objects if oid not in before]

        assert game.state.combat.attacking_permanent[made] == walker

    def test_it_is_still_never_declared(self, builder):
        """508.4's other half: choosing a walker is not declaring an attack."""
        game = position(builder, walkers=(1,))
        declare(game)
        attacks = len([e for e in game.state.events if e.type is EventType.ATTACKS])
        drive(
            game, [token(attacking={"binding": "each_player"}, or_planeswalker=True)],
            [pick_object], bindings={"each_player": 1},
        )

        assert len([e for e in game.state.events if e.type is EventType.ATTACKS]) == attacks


class TestTheSiblingOpsTakeTheKey:
    def test_put_onto_battlefield(self, builder):
        """Ninjutsu's op, with the ninja aimed at a walker."""
        game = position(builder, walkers=(1,), hand=[BEAR])
        declare(game)
        walker = only_oid(game, WALKER, 1)
        (in_hand,) = [
            oid for oid in game.state.players[0].hand if game.state.objects[oid].def_id == BEAR
        ]
        drive(
            game,
            [{"op": "put_onto_battlefield", "objects": {"binding": "it"}, "tapped": True,
              "attacking": {"binding": "each_player"}, "or_planeswalker": True}],
            [pick_object],
            bindings={"each_player": 1, "it": [in_hand]},
        )

        assert game.state.objects[in_hand].zone is Zone.BATTLEFIELD
        assert game.state.combat.attacking_permanent[in_hand] == walker

    def test_copy_permanent(self, builder):
        game = position(builder, walkers=(1,))
        bear = declare(game)
        walker = only_oid(game, WALKER, 1)
        made, asked = drive(
            game,
            [{"op": "copy_permanent", "objects": {"binding": "it"}, "tapped": True,
              "attacking": {"binding": "each_player"}, "or_planeswalker": True}],
            [pick_object],
            bindings={"each_player": 1, "it": [bear]},
        )

        assert len(asked) == 1
        assert game.state.combat.attacking_permanent[made[0]] == walker


def resolve_to_attack_choice(game, limit: int = 200):
    """Pass along until an ``attack`` choice is pending; ``None`` if none came."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.state.step >= Step.DECLARE_BLOCKERS:
            return None
        if decision.context.get("purpose") == "attack":
            return decision
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached an attack choice")


def choose(game, kind: str, ident: int) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE
            and any(t.kind == kind and t.id == ident for t in a.targets)
        )
    )


class TestTheCard:
    """The witness as a printed card, through a real combat."""

    def test_the_damage_lands_on_the_walker(self, builder):
        game = position(builder, walkers=(1,), p0=[CATHAR])
        declare(game)
        walker = only_oid(game, WALKER, 1)
        life = game.state.players[1].life

        decision = resolve_to_attack_choice(game)
        assert decision is not None and decision.player == 0
        choose(game, "object", walker)
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert game.state.objects[walker].counter("loyalty") == 3, "the Human hit the walker"
        assert game.state.players[1].life == life - 2, "only the bear hit the player"

    def test_a_walker_gone_before_damage_takes_nothing_from_the_player(self, builder):
        """506.4c: the token attacked the walker, not the seat, and does not
        fall through to the player when the walker leaves."""
        game = position(builder, walkers=(1,), p0=[CATHAR])
        declare(game)
        walker = only_oid(game, WALKER, 1)
        life = game.state.players[1].life
        resolve_to_attack_choice(game)
        choose(game, "object", walker)
        game.state.objects[walker].counters["loyalty"] = 0

        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        assert game.state.players[1].life == life - 2, "the bear only"

    def test_for_each_opponent_asks_only_where_there_is_a_walker(self, builder):
        """A pod: walkers at seats 1 and 3, none at seat 2. Two questions, each
        offering only its own seat's walker; seat 2's token goes to the face."""
        game = position(builder, players=4, walkers=(1, 3), p0=[CATHAR])
        declare(game, defender=2)
        seat_walkers = {1: only_oid(game, WALKER, 1), 3: only_oid(game, WALKER, 3)}

        offered = []
        while (decision := resolve_to_attack_choice(game)) is not None:
            (seat,) = [o.ref.id for o in decision.options if o.ref.kind == "player"]
            walkers = [o.ref.id for o in decision.options if o.ref.kind == "object"]
            offered.append((seat, walkers))
            choose(game, "object", seat_walkers[seat])

        assert sorted(offered) == [(1, [seat_walkers[1]]), (3, [seat_walkers[3]])]
        humans = oids_of(game, HUMAN, 0)
        combat = game.state.combat
        assert sorted(combat.attackers[h] for h in humans) == [1, 2, 3]
        assert sorted(combat.attacking_permanent.get(h, 0) for h in humans) == sorted(
            [0, seat_walkers[1], seat_walkers[3]]
        )

    def test_the_passive_answer_is_the_player_and_does_not_hang(self, builder):
        """Every automated seat answers a `CHOOSE_OBJECTS` already; the default
        answer is the first option, the seat."""
        game = position(builder, walkers=(1,), p0=[CATHAR])
        declare(game)
        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        (human,) = oids_of(game, HUMAN, 0)
        assert human not in (game.state.combat.attacking_permanent if game.state.combat else {})

    def test_power_is_the_number_of_creatures_i_control(self, builder):
        """604.3: the characteristic-defining line, a `set_pt` with a count."""
        game = position(builder, p0=[CATHAR], bears=2)
        cathar = only_oid(game, CATHAR, 0)
        assert (chars(game.state, cathar).power, chars(game.state, cathar).toughness) == (3, 4)


class TestTheLoader:
    def compile(self, **effect):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe",
                    "name": "Probe",
                    "mana_cost": "{W}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "abilities": [
                        {
                            "kind": "triggered",
                            "trigger": {"event": "you_attack"},
                            "effects": [
                                {
                                    "op": "for_each_player",
                                    "players": "each_opponent",
                                    "effects": [{"op": "create_token", "token": HUMAN, **effect}],
                                }
                            ],
                        }
                    ],
                }
            )
        )

    def test_it_loads_beside_a_player_spec(self):
        assert self.compile(attacking={"binding": "each_player"}, or_planeswalker=True)

    def test_it_loads_beside_the_boolean(self):
        assert self.compile(attacking=True, or_planeswalker=True)

    @pytest.mark.parametrize("attacking", [None, False])
    def test_it_needs_an_attacking_to_widen(self, attacking):
        """Otherwise the token attacks nobody while the card reads as printed."""
        effect = {"or_planeswalker": True}
        if attacking is not None:
            effect["attacking"] = attacking
        with pytest.raises(DslError, match="needs an `attacking`"):
            self.compile(**effect)

    def test_it_must_be_a_boolean(self):
        with pytest.raises(DslError, match="must be true or false"):
            self.compile(attacking={"binding": "each_player"}, or_planeswalker="true")

    def test_the_packet_advertises_it(self):
        options = reference()["op_options"]
        for op in ("create_token", "copy_permanent", "put_onto_battlefield"):
            assert "or_planeswalker" in options[op], op
