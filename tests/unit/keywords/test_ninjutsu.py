"""Ninjutsu, as rule 702.49 defines it.

    "Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand:
    Put this card onto the battlefield from your hand tapped and attacking.)"

Two words in the reminder text decide when and where the ninja fights, and both
are pinned here because each has a plausible wrong reading.

- **"unblocked"** (509.1h). An attacking creature becomes *blocked* or
  *unblocked* as blockers are declared, and not before. In the declare
  attackers step no attacker is unblocked yet, so ninjutsu is not offered
  there: swapping a ninja in before blocks would let it be blocked, which the
  printed card never allows. A blocked attacker stays blocked after its blocker
  leaves combat, so it can never be swapped out either. `blocked` is a
  selector key that answers neither `true` nor `false` before blockers are
  declared, or for a creature that is not attacking.
- **"attacking"** (702.49c). The ninja enters attacking *the same player,
  planeswalker or battle the returned creature was attacking*. At a pod that
  is not the first declared attacker's defender, and against a planeswalker it
  is the walker, not its controller. The cost's ``as`` records the returned
  creature's attack as it is paid, before the bounce takes it out of combat,
  and ``attacking: {"same_as": …}`` reads that record back.

The ability is offered from **hand**, and passes the outside-the-battlefield
guard because the effect moves `self_only` out. The ninja was never *declared*
as an attacker (508.4), so it triggers nothing that fires on attacking. Yuffie,
Materia Hunter is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, oids_of, only_oid

ISLAND = "island"
NINJA = "t_ninja"  # 3/2, Ninjutsu {1}{U}
BEAR = "t_bear"
WALKER = "t_walker"  # loyalty 4
#: The shipped witness: Ninjutsu {1}{R}, paid from the position's Mountain.
YUFFIE = "yuffie_materia_hunter"


def position(
    builder, *, players: int = 2, bears: int = 1, blockers=(), walker_at=None, ninja=NINJA
):
    """Player 0 with ``bears`` to swing, three Islands and the ninja in hand.

    Plus two Mountains and an instant, so player 0 has something to do in every
    priority window and the engine stops to ask -- which is what makes "ninjutsu
    was not offered then" an observation rather than an auto-pass.
    """
    b = builder(players=players)
    b.battlefield(0, [ISLAND] * 3 + ["mountain"] * 2 + [BEAR] * bears)
    b.hand(0, [ninja, "t_bolt"])
    b.library(0, [ISLAND] * 20)
    for pid in range(1, players):
        mine = list(blockers) if pid == 1 else []
        if pid == walker_at:
            mine.append(WALKER)
        b.battlefield(pid, mine)
        b.library(pid, [ISLAND] * 20)
    return b.build()


def ninjutsu_action(game, card: str = NINJA):
    ninja = next(
        (o for o in game.state.players[0].hand if game.state.objects[o].def_id == card),
        None,
    )
    if ninja is None:
        return None
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == ninja
        ),
        None,
    )


def declare_attacks(game, attacks: dict[int, TargetRef]) -> None:
    """Pass to player 0's attack declaration and swing each bear at its target."""
    for _ in range(200):
        decision = game.pending()
        assert decision is not None
        if decision.kind is DecisionKind.DECLARE_ATTACKERS and decision.player == 0:
            break
        game.apply(_default_answer(game, decision))
    for bear, target in attacks.items():
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER and a.source == bear and target in a.targets
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def run_to_blocks(game, blocks: dict[int, int] | None = None, card: str = NINJA):
    """Run the combat on from declared attackers to player 0's first priority
    after blockers are declared.

    ``blocks`` maps each blocker to the attacker it blocks; every other
    declaration is finished empty. Returns ``(offer, early)``: the ninjutsu
    action then (or ``None``), and how many times player 0 held priority before
    blockers were declared -- the window in which the offer must not appear.
    """
    blocks = dict(blocks or {})
    early = 0
    for _ in range(400):
        decision = game.pending()
        combat = game.state.combat
        assert decision is not None and combat is not None, "combat ended"
        mine = decision.kind is DecisionKind.PRIORITY and decision.player == 0
        if mine and combat.blockers_declared:
            return ninjutsu_action(game, card), early
        if mine:
            early += 1
            assert ninjutsu_action(game, card) is None, "offered before blockers were declared"
        if decision.kind is DecisionKind.DECLARE_BLOCKERS:
            add = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ADD_BLOCKER
                    and a.source in blocks
                    and any(t.id == blocks[a.source] for t in a.targets)
                ),
                None,
            )
            if add is not None:
                blocks.pop(add.source)
                game.apply(add)
                continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("blockers were never declared")


def activate(game, offer, returned: int, card: str = NINJA) -> None:
    """Activate ninjutsu, returning ``returned``, and let it resolve."""
    game.apply(offer)
    for _ in range(200):
        decision = game.pending()
        if decision is None or game.state.objects[returned].zone is Zone.HAND:
            break
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choice = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and returned in [t.id for t in a.targets]
            )
            game.apply(choice)
            continue
        game.apply(_default_answer(game, decision))
    for _ in range(200):
        decision = game.pending()
        if decision is None or oids_of(game, card):
            break
        game.apply(_default_answer(game, decision))


def pool(game, selector) -> set[int]:
    ctx = EffectContext(state=game.state, controller=0)
    return set(resolve_pool(ctx, {"zone": "battlefield", **selector}))


class TestWhenItIsOffered:
    def test_it_is_not_offered_before_combat(self, builder):
        """Nothing is attacking, so the cost has nothing to return."""
        game = position(builder)
        assert ninjutsu_action(game) is None

    def test_it_is_not_offered_before_blockers_are_declared(self, builder):
        """509.1h: in the declare attackers step no attacker is unblocked yet.

        Corrects an earlier pin that offered it here, which let the ninja be
        swapped in before blocks and then be blocked.
        """
        game = position(builder)
        bear = only_oid(game, BEAR)
        declare_attacks(game, {bear: TargetRef.player(1)})
        offer, early = run_to_blocks(game)
        assert early, "player 0 never held priority in the declare attackers step"
        assert offer is not None

    def test_it_is_offered_once_blockers_are_declared_and_nobody_blocked(self, builder):
        """The window the keyword is played in."""
        game = position(builder, blockers=[BEAR])
        bear = only_oid(game, BEAR, 0)
        declare_attacks(game, {bear: TargetRef.player(1)})
        offer, _ = run_to_blocks(game)
        assert offer is not None
        assert game.state.combat.blockers_declared

    def test_it_is_not_offered_when_the_attacker_is_blocked(self, builder):
        """The whole of "unblocked", and the reason it is not `not blocking`."""
        game = position(builder, blockers=[BEAR])
        bear = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        declare_attacks(game, {bear: TargetRef.player(1)})
        offer, _ = run_to_blocks(game, {blocker: bear})
        assert offer is None, "a blocked attacker cannot be swapped out"


class TestTheBlockedKey:
    """`blocked` read straight off the selector, at each moment of combat."""

    def test_an_attacker_is_neither_before_blockers_are_declared(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        declare_attacks(game, {bear: TargetRef.player(1)})
        assert game.state.combat.attacking(bear)
        assert not game.state.combat.blockers_declared
        assert bear not in pool(game, {"blocked": False})
        assert bear not in pool(game, {"blocked": True})

    def test_a_blocked_attacker_stays_blocked_when_its_blocker_leaves_combat(self, builder):
        game = position(builder, blockers=[BEAR])
        bear = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        declare_attacks(game, {bear: TargetRef.player(1)})
        run_to_blocks(game, {blocker: bear})
        game.state.combat.remove(blocker)
        assert bear in pool(game, {"blocked": True})
        assert bear not in pool(game, {"blocked": False})

    def test_a_creature_that_is_not_attacking_is_neither(self, builder):
        game = position(builder, bears=2)
        attacker, idle = oids_of(game, BEAR, 0)
        declare_attacks(game, {attacker: TargetRef.player(1)})
        run_to_blocks(game)
        assert attacker in pool(game, {"blocked": False})
        assert idle not in pool(game, {"blocked": False})
        assert idle not in pool(game, {"blocked": True})


class TestWhatItDoes:
    def _swap(self, builder):
        game = position(builder)
        bear = only_oid(game, BEAR)
        declare_attacks(game, {bear: TargetRef.player(1)})
        offer, _ = run_to_blocks(game)
        assert offer is not None
        activate(game, offer, bear)
        return game, bear

    def test_the_attacker_goes_back_to_hand(self, builder):
        game, bear = self._swap(builder)
        assert game.state.objects[bear].zone is Zone.HAND

    def test_the_ninja_arrives_tapped_and_attacking(self, builder):
        game, _ = self._swap(builder)
        ninja = only_oid(game, NINJA)
        assert game.state.objects[ninja].on_battlefield
        assert game.state.objects[ninja].tapped
        assert game.state.combat.attacking(ninja)

    def test_it_connects_for_its_own_power(self, builder):
        """The observable consequence: a 3/2 ninja, not the 2/2 that was bounced."""
        game, _ = self._swap(builder)
        life = game.state.players[1].life
        for _ in range(200):
            decision = game.pending()
            if decision is None or game.state.players[1].life != life:
                break
            game.apply(_default_answer(game, decision))
        assert game.state.players[1].life == life - 3


class TestWhomTheNinjaAttacks:
    """702.49c: the same player, planeswalker or battle as the returned creature."""

    @pytest.mark.parametrize("card", [NINJA, YUFFIE])
    def test_it_attacks_the_returned_creatures_player_not_the_first_attackers(
        self, builder, card
    ):
        game = position(builder, players=3, bears=2, ninja=card)
        first, second = oids_of(game, BEAR, 0)
        declare_attacks(game, {first: TargetRef.player(1), second: TargetRef.player(2)})
        offer, _ = run_to_blocks(game, card=card)
        assert offer is not None
        activate(game, offer, second, card)
        ninja = only_oid(game, card)
        assert game.state.objects[second].zone is Zone.HAND
        assert game.state.combat.attackers[ninja] == 2
        assert game.state.combat.attackers[first] == 1

    def test_it_attacks_the_planeswalker_the_returned_creature_was_attacking(
        self, builder
    ):
        game = position(builder, walker_at=1)
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER)
        declare_attacks(game, {bear: TargetRef.obj(walker)})
        offer, _ = run_to_blocks(game)
        activate(game, offer, bear)
        ninja = only_oid(game, NINJA)
        assert game.state.combat.attackers[ninja] == 1
        assert game.state.combat.attacking_permanent.get(ninja) == walker

    def test_the_walker_takes_the_damage_and_the_player_does_not(self, builder):
        game = position(builder, walker_at=1)
        bear = only_oid(game, BEAR, 0)
        walker = only_oid(game, WALKER)
        declare_attacks(game, {bear: TargetRef.obj(walker)})
        offer, _ = run_to_blocks(game)
        activate(game, offer, bear)
        life = game.state.players[1].life
        loyalty = game.state.objects[walker].counters["loyalty"]
        for _ in range(200):
            decision = game.pending()
            if decision is None or game.state.objects[walker].counters["loyalty"] != loyalty:
                break
            game.apply(_default_answer(game, decision))
        assert game.state.objects[walker].counters["loyalty"] == loyalty - 3
        assert game.state.players[1].life == life


def ninja_card(cost_extra=None, effect_extra=None, *, kind="activated") -> CardModel:
    cost = {
        "mana": "{1}{U}",
        "return_to_hand": {
            "controller": "you",
            "types": ["Creature"],
            "attacking": True,
            "blocked": False,
            "as": "returned",
        },
    }
    cost["return_to_hand"].update(cost_extra or {})
    effect = {
        "op": "put_onto_battlefield",
        "objects": {"zone": "hand", "self_only": True},
        "controller": "you",
        "tapped": True,
        "attacking": {"same_as": "returned"},
    }
    effect.update(effect_extra or {})
    return CardModel.model_validate(
        {
            "id": "probe_ninja",
            "name": "Probe Ninja",
            "oracle_text": "Ninjutsu",
            "mana_cost": "{2}{U}",
            "types": ["Creature"],
            "power": 3,
            "toughness": 2,
            "abilities": [
                {
                    "kind": kind,
                    "text": "Ninjutsu",
                    "active_zones": ["hand"],
                    "cost": cost,
                    "effects": [effect],
                }
            ],
        }
    )


class TestTheLoaderRefuses:
    def test_the_shape_loads(self):
        compile_card(ninja_card())

    def test_same_as_naming_nothing_the_cost_binds(self):
        with pytest.raises(DslError, match="same_as"):
            compile_card(ninja_card(effect_extra={"attacking": {"same_as": "other"}}))

    def test_a_returned_name_with_a_count_above_one(self):
        with pytest.raises(DslError, match="exactly one"):
            compile_card(ninja_card(cost_extra={"count": 2}))

    def test_same_as_widened_to_a_planeswalker(self):
        with pytest.raises(DslError, match="or_planeswalker"):
            compile_card(ninja_card(effect_extra={"or_planeswalker": True}))

    def test_same_as_with_extra_keys(self):
        with pytest.raises(DslError, match="same_as"):
            compile_card(
                ninja_card(effect_extra={"attacking": {"same_as": "returned", "player": 1}})
            )
