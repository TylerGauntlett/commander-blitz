"""Behold — "choose a Dragon you control or reveal a Dragon card from your hand".

Sarkhan, Dragon Ascendant: "When Sarkhan enters, you may behold a Dragon. If you
do, create a Treasure token." Caustic Exhale: "As an additional cost to cast
this spell, behold a Dragon or pay {1}." Dispelling Exhale: "As an additional
cost to cast this spell, you may behold a Dragon … If a Dragon was beheld, …".

The nearest spelling before this was `may` with an `exists` condition over a
Dragon on the battlefield or in hand, and it is a cheaper card than the printed
one: it never asks *which* Dragon and never reveals the hand card, and the
reveal is the price -- every opponent learns the Dragon you are holding. The
other half that has to hold is 601.2a: a spell is on the stack before its costs
are paid, so a Dragon spell with a behold cost can never behold itself.

The shipped witnesses are Elven Passage (the op: "You may behold an Elf. If
you do, untap that land"), Caustic Exhale and the Lorwyn "behold … or pay {2}"
creatures (the cost as a branch), and Dispelling Exhale (the optional cost).

`t_behold_seer` is Sarkhan's trigger on a plain Human, `t_behold_exhale` the
"or pay {1}" branch, `t_behold_maybe` the optional cost read back with
`additional_paid`, and `t_behold_aspirant` a Dragon whose cost must find a
*different* Dragon.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, hand_ids, settle

WHELP = "t_behold_whelp"
SEER = "t_behold_seer"
EXHALE = "t_behold_exhale"
MAYBE = "t_behold_maybe"
ASPIRANT = "t_behold_aspirant"
BEAR = "t_bear"


def treasure(then=None, **extra) -> dict:
    return {
        "op": "behold",
        "optional": True,
        "objects": {"subtypes": ["Dragon"]},
        "as": "beheld",
        "effects": [{"op": "create_token", "token": "treasure_token"}],
        **({"else": then} if then else {}),
        **extra,
    }


def board(builder, *, mine=(), hand=(), theirs=(), their_hand=()):
    game = (
        builder(players=2)
        .battlefield(0, [SEER, *mine])
        .hand(0, list(hand))
        .battlefield(1, list(theirs))
        .hand(1, list(their_hand))
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == SEER)
    return game, src


def run(game, spec: dict, source: int, *, yes: bool = True, pick: int = 0):
    """Run one op; answer yes/no with ``yes`` and every choice with ``pick``."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS[spec["op"]](ctx, spec)
    asked = []
    if inspect.isgenerator(gen):
        send = None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            asked.append(decision)
            if decision.kind is DecisionKind.MAY:
                send = [0] if yes else [1]
            else:
                send = [pick]
    return ctx, asked


def treasures(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if o.def_id == "treasure_token")


def reveals(game) -> list[list[str]]:
    return [e.data["cards"] for e in game.state.events if e.type == "reveal"]


class TestWhatMayBeBeheld:
    def test_a_dragon_you_control_and_a_dragon_in_hand_are_both_offered(self, builder):
        game, src = board(builder, mine=[WHELP], hand=[WHELP, BEAR])
        _, asked = run(game, treasure(), src)
        choice = next(d for d in asked if d.kind is DecisionKind.CHOOSE_OBJECTS)
        zones = sorted(game.state.objects[o.value].zone.value for o in choice.options)
        assert zones == ["battlefield", "hand"]

    def test_an_opponents_dragon_is_not_yours_to_behold(self, builder):
        """Neither on their battlefield nor in their hidden hand."""
        game, src = board(builder, theirs=[WHELP], their_hand=[WHELP])
        _, asked = run(game, treasure(), src)
        assert asked == []
        assert treasures(game) == 0

    def test_a_creature_of_another_type_does_not_qualify(self, builder):
        game, src = board(builder, mine=[BEAR], hand=[BEAR])
        _, asked = run(game, treasure(), src)
        assert asked == []
        assert treasures(game) == 0


class TestIfYouDo:
    def test_nothing_to_behold_asks_nothing_and_runs_else(self, builder):
        """"Yes" must always mean a behold happened, so it is not offered."""
        game, src = board(builder, hand=[BEAR])
        spec = treasure(then=[{"op": "draw", "player": "you", "amount": {"const": 1}}])
        before = len(game.state.players[0].hand)
        _, asked = run(game, spec, src)
        assert asked == []
        assert treasures(game) == 0
        assert len(game.state.players[0].hand) == before + 1

    def test_declining_creates_nothing_and_reveals_nothing(self, builder):
        game, src = board(builder, hand=[WHELP])
        _, asked = run(game, treasure(), src, yes=False)
        assert [d.kind for d in asked] == [DecisionKind.MAY]
        assert treasures(game) == 0
        assert reveals(game) == []

    def test_beholding_from_hand_reveals_the_card_and_keeps_it(self, builder):
        game, src = board(builder, hand=[WHELP])
        ctx, _ = run(game, treasure(), src)
        assert treasures(game) == 1
        assert reveals(game) == [[WHELP]]
        assert hand_ids(game).count(WHELP) == 1, "beheld, not moved"
        assert game.state.objects[ctx.bindings["beheld"][0]].def_id == WHELP

    def test_choosing_a_permanent_reveals_nothing(self, builder):
        """It is already public; the event would be a reveal of nothing hidden."""
        game, src = board(builder, mine=[WHELP])
        run(game, treasure(), src)
        assert treasures(game) == 1
        assert reveals(game) == []

    def test_a_dragon_source_may_behold_itself(self, builder):
        """"A Dragon you control" includes the permanent asking."""
        game = builder(players=2).battlefield(0, [WHELP]).build(advance=False)
        src = next(o.oid for o in game.state.battlefield_objects(0))
        ctx, _ = run(game, treasure(), src)
        assert ctx.bindings["beheld"] == [src]
        assert treasures(game) == 1

    def test_the_trigger_end_to_end(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 2)
            .hand(0, [SEER, WHELP])
            .build()
        )
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SEER
        )
        game.apply(cast)
        for _ in range(50):
            decision = game.pending()
            if decision is None or (
                decision.kind is DecisionKind.PRIORITY
                and not game.state.stack
                and not game.state.pending_triggers
            ):
                break
            if decision.kind is DecisionKind.MAY:
                game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            else:
                game.apply(_default_answer(game, decision))
        assert treasures(game) == 1
        assert reveals(game) == [[WHELP]]


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def cost_board(builder, card_id: str, *, mine=(), hand=(), lands: int = 4):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * lands + list(mine))
        .hand(0, [card_id, *hand])
        .library(0, ["forest"] * 20)
        .build()
    )


def pay(game, action) -> None:
    game.apply(action)
    for _ in range(50):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.PRIORITY:
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        else:
            game.apply(_default_answer(game, decision))


class TestTheCost:
    def test_with_no_dragon_only_the_pay_branch_is_offered(self, builder):
        game = cost_board(builder, EXHALE, hand=[BEAR])
        assert sorted(a.additional_choice for a in cast_lines(game, EXHALE)) == [1]

    def test_a_dragon_in_hand_opens_the_behold_branch(self, builder):
        game = cost_board(builder, EXHALE, hand=[WHELP])
        assert sorted(a.additional_choice for a in cast_lines(game, EXHALE)) == [0, 1]

    def test_beholding_costs_no_mana_and_reveals_the_card(self, builder):
        game = cost_board(builder, EXHALE, hand=[WHELP], lands=1)
        # One Swamp: {B} alone. The {1} branch is not affordable, beholding is.
        assert sorted(a.additional_choice for a in cast_lines(game, EXHALE)) == [0]
        pay(game, cast_lines(game, EXHALE)[0])
        graveyard = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert graveyard == [EXHALE], "cast and resolved on {B} alone"
        assert reveals(game) == [[WHELP]]
        assert WHELP in hand_ids(game)

    def test_a_dragon_spell_cannot_behold_itself(self, builder):
        """601.2a: it is on the stack, not in hand, when the cost is paid."""
        alone = cost_board(builder, ASPIRANT, lands=0, mine=["mountain"])
        assert cast_lines(alone, ASPIRANT) == []
        paired = cost_board(builder, ASPIRANT, lands=0, mine=["mountain"], hand=[WHELP])
        assert len(cast_lines(paired, ASPIRANT)) == 1


class TestTheOptionalCost:
    def drawn(self, builder, *, hand, behold: bool) -> int:
        game = cost_board(builder, MAYBE, hand=hand, mine=["island"])
        lines = cast_lines(game, MAYBE)
        line = next(a for a in lines if (a.additional_times == 1) is behold)
        before = len(game.state.players[0].library)
        pay(game, line)
        settle(game)
        return before - len(game.state.players[0].library)

    def test_beheld_reads_back_as_paid(self, builder):
        assert self.drawn(builder, hand=[WHELP], behold=True) == 2

    def test_not_beheld_is_the_plain_spell(self, builder):
        assert self.drawn(builder, hand=[WHELP], behold=False) == 1

    def test_no_dragon_offers_only_the_plain_spell(self, builder):
        game = cost_board(builder, MAYBE, hand=[BEAR], mine=["island"])
        assert [a.additional_times for a in cast_lines(game, MAYBE)] == [0]


class TestTheLoaderRefuses:
    def card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_behold",
                "name": "Test Bad Behold",
                "oracle_text": "Draw a card.",
                "mana_cost": "{1}{R}",
                "types": ["Sorcery"],
                **extra,
            }
        )

    @pytest.mark.parametrize(
        "objects",
        [None, {}, {"subtypes": ["Dragon"], "zone": "graveyard"},
         {"subtypes": ["Dragon"], "controller": "opponent"},
         {"subtypes": ["Dragon"], "count": 0}],
    )
    def test_a_malformed_selector_on_the_op(self, objects):
        effect = {"op": "behold", "effects": [{"op": "draw", "player": "you"}]}
        if objects is not None:
            effect["objects"] = objects
        with pytest.raises(DslError):
            compile_card(self.card(spell_effects=[effect]), source="t")

    def test_a_behold_nothing_reads(self):
        effect = {"op": "behold", "objects": {"subtypes": ["Dragon"]}}
        with pytest.raises(DslError, match="if you do"):
            compile_card(self.card(spell_effects=[effect]), source="t")

    def test_a_zone_on_the_cost(self):
        with pytest.raises(DslError, match="implied"):
            compile_card(
                self.card(
                    additional_cost={"behold": {"subtypes": ["Dragon"], "zone": "hand"}},
                    spell_effects=[{"op": "draw", "player": "you"}],
                ),
                source="t",
            )
