""""Whenever one or more creatures attack one of your opponents", and "those creatures".

    Frontier Warmonger — "Whenever one or more creatures attack one of your
    opponents or a planeswalker they control, those creatures gain menace until
    end of turn."

A batch attack trigger that knows **who was attacked**, and a binding that names
the creatures that caused it. Rule 508.1 declares each attacker against one
defending player, so "one or more creatures attack one of your opponents" is one
ability per (declaration, defending player) pair — coarser than a creature and
finer than a combat.

Neither existing attack trigger can say it, and each fails on a different half:

- **`you_attack`** is the right shape — one `ATTACKERS_DECLARED`, once per
  declaration — and carries no defender at all, so `_defender_matches` returns
  False on the absent key and a `defending` clause never matches. The ability is
  inert forever, and silently. Dropping the clause is not a weaker card but a
  different one: plain `you_attack` with `controller: "any"` also fires when an
  opponent swings at *you*, handing menace to the creatures you are about to
  block.
- **`attacks`** carries the defender and is per *creature*. The note on
  `you_attack` in `triggers.py` already refused that substitution in writing —
  it "would fire three times on a three-creature swing" — and each of the three
  copies could speak about one attacker only.

`EventType.CREATURES_ATTACKED_PLAYER` is therefore a new event rather than a
second `ATTACKERS_DECLARED`: that one means "the declaration closed" and there is
exactly one per combat, so firing it per defender would pay Clavileño twice on a
split attack and tell the client the attack was declared twice.

"Those creatures" is `{"binding": "attackers"}`, carried by `EVENT_BINDING_KEYS`
like every other "that much". The list machinery already existed — `resolve_pool`
sends a binding through `_bound_oids`, which has taken a list since devour — so
the set the event always carried was simply being dropped.
`{"zone": "battlefield", "attacking": true}` is the near miss and says something
strictly larger: it is a bare boolean with no notion of *whom*, so on a split
attack it also names the creatures attacking the trigger's own controller.

What is pinned below, and each is a way this could be silently wrong:

1. One firing per declaration per defender — not one per creature, which is the
   whole difference from `attacks`.
2. The defender discrimination in **both** directions: `defending: "opponent"`
   must not fire on an attack at its own controller, and `defending: "you"` must
   not fire on an attack at somebody else. A two-player game hides this.
3. "Those creatures" is exactly the attackers declared against *that* defender —
   not the whole declaration, and not every attacking creature on the board.
4. A planeswalker's controller is the defending player, so "or a planeswalker
   they control" needs no second clause.
5. `you_attack` still fires exactly **once** on a declaration split between two
   seats. The new event is fired beside it, not instead of it.
6. The loader refuses `defending` on `you_attack`, which is the inert card this
   capability exists because nobody could write.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.turn import clear_until_eot
from tests.conftest import _default_answer, oids_of, only_oid, settle

BEAR = "t_bear"
WALKER = "t_walker"
#: "Whenever one or more creatures attack one of your opponents or a
#: planeswalker they control, those creatures gain menace until end of turn."
WARMONGER = "t_warmonger"
#: "Whenever one or more creatures attack you, you gain 1 life." The other half
#: of the `defending` clause, and the counter that shows how *often* it fired.
WATCHER = "t_attacked_watcher"
#: "Whenever you attack, you gain 1 life." The trigger that must not change.
YOU_ATTACK = "t_you_attack"


def position(builder, *, bears: int = 1, p0=(), p1=(), p2=()):
    """Player 0 attacks; the trigger under test sits wherever the claim needs it.

    Three players, because the whole question this capability answers is which
    seat was attacked, and a two-player game answers it by accident: every
    attack is at the only opponent there is.
    """
    b = builder(players=3)
    b.battlefield(0, [*([BEAR] * bears), *p0])
    if p1:
        b.battlefield(1, list(p1))
    if p2:
        b.battlefield(2, list(p2))
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def finish(game) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    settle(game)


def declare(game, plan: dict[int, int]) -> dict[int, list[int]]:
    """Send player 0's bears at the seats in ``plan`` -- ``{defender: how many}``.

    Returns which bear went where, because every claim below is about a
    *subset*, and the test has to be able to name the other subset too.
    """
    to_declare_attackers(game)
    bears = list(oids_of(game, BEAR, 0))
    sent: dict[int, list[int]] = {}
    for defender, count in plan.items():
        for _ in range(count):
            oid = bears.pop(0)
            action = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == "player" and t.id == defender for t in a.targets)
            )
            game.apply(action)
            sent.setdefault(defender, []).append(oid)
    finish(game)
    return sent


def declare_at_planeswalker(game) -> int:
    """One bear at the planeswalker player 2 controls. Returns the attacker."""
    to_declare_attackers(game)
    bear = only_oid(game, BEAR, 0)
    walker = only_oid(game, WALKER, 2)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER
        and a.source == bear
        and any(t.kind == "object" and t.id == walker for t in a.targets)
    )
    game.apply(action)
    finish(game)
    return bear


def has_menace(game, oid: int) -> bool:
    return "menace" in chars(game.state, oid).keywords


def fired(game) -> list:
    """Every `creatures_attacked_player` in the log -- how often, and at whom."""
    return [
        e for e in game.state.events if e.type == EventType.CREATURES_ATTACKED_PLAYER
    ]


class TestOncePerDeclarationPerDefender:
    def test_three_attackers_at_one_seat_fire_it_once(self, builder):
        """The whole difference from `attacks`, which is per creature."""
        game = position(builder, bears=3, p1=(WATCHER,))
        before = game.state.players[1].life
        declare(game, {1: 3})

        assert len(fired(game)) == 1
        assert game.state.players[1].life == before + 1

    def test_a_split_declaration_fires_it_once_per_seat(self, builder):
        """One declaration, two defending players, two abilities -- and player 1
        is paid for the two creatures aimed at them, not for all three."""
        game = position(builder, bears=3, p1=(WATCHER,))
        before = game.state.players[1].life
        declare(game, {1: 2, 2: 1})

        assert sorted(e.data["defender"] for e in fired(game)) == [1, 2]
        assert game.state.players[1].life == before + 1

    def test_no_attackers_fire_nothing(self, builder):
        game = position(builder, bears=0, p1=(WATCHER,))
        before = game.state.players[1].life
        to_declare_attackers(game)
        finish(game)

        assert fired(game) == []
        assert game.state.players[1].life == before

    def test_you_attack_still_fires_once_for_the_whole_declaration(self, builder):
        """The event this one is fired *beside*, and must not disturb.

        Clavileño is one Demon per combat however the swing is split. A batch
        trigger built by firing `ATTACKERS_DECLARED` once per defender would pay
        it twice here, which is why the new fact got its own event type.
        """
        game = position(builder, bears=3, p0=(YOU_ATTACK,))
        before = game.state.players[0].life
        declare(game, {1: 2, 2: 1})

        declared = [
            e for e in game.state.events if e.type == EventType.ATTACKERS_DECLARED
        ]
        assert len(declared) == 1
        assert game.state.players[0].life == before + 1


class TestWhichSeatWasAttacked:
    def test_opponent_fires_on_an_attack_at_another_seat(self, builder):
        game = position(builder, bears=1, p1=(WARMONGER,))
        sent = declare(game, {2: 1})

        assert has_menace(game, sent[2][0])

    def test_opponent_does_not_fire_on_an_attack_at_its_own_controller(self, builder):
        """The half a two-player game cannot show, and the reason dropping the
        `defending` clause is a different card rather than a rougher one: menace
        handed to the creatures its controller is about to block."""
        game = position(builder, bears=1, p1=(WARMONGER,))
        sent = declare(game, {1: 1})

        assert not has_menace(game, sent[1][0])

    def test_you_fires_only_for_the_attacked_seat(self, builder):
        game = position(builder, bears=1, p1=(WATCHER,))
        before = game.state.players[1].life
        declare(game, {2: 1})

        assert game.state.players[1].life == before, "player 2 was attacked, not 1"

    def test_a_planeswalkers_controller_is_the_defending_player(self, builder):
        """"…or a planeswalker they control" is free: `combat.attackers[oid]` is
        the defending *player* even when the attack is aimed at a walker, so one
        `defending: "opponent"` covers both halves of the printed line."""
        game = position(builder, bears=1, p1=(WARMONGER,), p2=(WALKER,))
        bear = declare_at_planeswalker(game)

        assert [e.data["defender"] for e in fired(game)] == [2]
        assert has_menace(game, bear)


class TestThoseCreatures:
    def test_the_binding_names_the_attackers(self, builder):
        game = position(builder, bears=2, p1=(WARMONGER,))
        sent = declare(game, {2: 2})

        assert all(has_menace(game, oid) for oid in sent[2])

    def test_it_is_the_subset_for_that_defender_only(self, builder):
        """A pod attack split between two seats is one declaration and two
        abilities, and each may speak only about its own half. The whole
        `attackers` list would grant menace to the creatures attacking the
        Warmonger's controller."""
        game = position(builder, bears=3, p1=(WARMONGER,))
        sent = declare(game, {1: 2, 2: 1})

        assert has_menace(game, sent[2][0])
        assert not any(has_menace(game, oid) for oid in sent[1])

    def test_a_creature_that_stayed_home_gets_nothing(self, builder):
        """`{"attacking": true}` is the near miss and would still be right here;
        what it cannot do is the test above. This pins the other end: the pool is
        the event's set, not the board."""
        game = position(builder, bears=2, p1=(WARMONGER,))
        sent = declare(game, {2: 1})
        home = next(oid for oid in oids_of(game, BEAR, 0) if oid not in sent[2])

        assert has_menace(game, sent[2][0])
        assert not has_menace(game, home)

    def test_the_menace_wears_off_at_cleanup(self, builder):
        """"until end of turn" -- `grant_keyword`'s default duration."""
        game = position(builder, bears=1, p1=(WARMONGER,))
        sent = declare(game, {2: 1})
        assert has_menace(game, sent[2][0])

        clear_until_eot(game.state)

        assert not has_menace(game, sent[2][0])


class TestTheLoaderRefusesAnInertDefendingClause:
    def compile(self, trigger: dict):
        model = CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "mana_cost": "{R}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": trigger,
                        "effects": [
                            {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                ],
            }
        )
        return compile_card(model)

    def test_defending_on_you_attack_is_refused(self, builder):
        """`ATTACKERS_DECLARED` carries no defender, so this clause matches
        nothing forever. Loading it would ship a card that reads "attacks one of
        your opponents" and never triggers."""
        with pytest.raises(DslError, match="defending"):
            self.compile({"event": "you_attack", "defending": "opponent"})

    def test_defending_on_the_batch_trigger_loads(self, builder):
        card = self.compile(
            {
                "event": "creatures_attack_player",
                "controller": "any",
                "defending": "opponent",
            }
        )
        trigger = card.abilities[0].trigger
        assert trigger is not None
        assert trigger.defending == "opponent"
        assert trigger.controller == "any"
