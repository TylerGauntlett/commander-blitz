"""Demonstrate: "choose an opponent to **also** copy it."

Excavation Technique and Silverquill Lecturer are the witnesses, and the clause
that blocked both of them is the second half of the reminder text. Rule 706.10
puts a copy on the stack, and `op_copy_spell` could already do that -- but it
ended `put_copy_on_stack(state, ctx.controller, …)`, so the copy's controller
was the resolving player and nothing else was sayable. Every copy the engine
could make was yours.

That is not a missing nicety. Demonstrate's downside *is* the opponent's copy:
without it Silverquill Lecturer is a one-sided Cackling Counterpart engine and
Excavation Technique is unconditional removal with no rider, and both would look
entirely normal on the page. The loader has no effect-key whitelist, so a card
written with `"controller": "opponent"` on the op loaded clean and handed the
copy to the wrong seat with nothing to say so.

Two pieces, and neither is a new `DecisionKind`:

* `copy_spell` takes a `controller` **player spec**, read plurally exactly as
  `copy_permanent`'s already is -- one copy per named seat.
* `choose_player` asks one seat and records it under `as`, which the
  `{"binding": …}` player spec then names. `select_players` resolves
  `"opponent"`/`"each_opponent"` to the *whole set*, and every spelling that
  names one player -- `target`, `controller_of_target`, `controller_of`,
  `owner_of` -- reads something a target or a trigger already produced.
  Demonstrate's copy is explicitly untargeted, so at a pod `"each_opponent"`
  would hand a copy to *every* opponent instead of the one chosen.
  `ask_player`/`CHOOSE_PLAYER` have existed since clash; what was missing was
  somewhere to put the answer.

And the clause the redirection drags in with it: "players may choose new
targets for **their** copies" (115.7b). `_choose_new_targets` asked
`ctx.controller`, which for a redirected copy is the wrong seat in both
directions -- it would let you aim an opponent's copy and stop them aiming it
themselves. The chooser now decides the *legal set* as well, because "target
creature you control" means a different pool for each of them, and declining
stays available even when the tuple the original chose is not legal for the new
controller: a copy nobody retargets is countered on resolution (608.2b), which
is the answer an opponent gives to a copy they do not want.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from tests.conftest import _default_answer

DRAW = "t_demo_draw"  # Demonstrate. "You draw a card." -- untargeted
RALLY = "t_demo_pump"  # Demonstrate. "Target creature you control gets +2/+2."
LECTURER = "t_lecturer"  # "Creature spells you cast have demonstrate."
STORMCAT = "t_stormcat"  # copies your instants, and names no controller
ZAP = "t_zap"  # {R} instant, 3 damage to target creature
BEAR = "grizzly_bears"
THEIRS = "t_goblin"


def position(builder, *, players: int = 2, spell: str = DRAW, board: bool = False):
    """You are holding a demonstrate spell with the mana to cast it."""
    mine = ["mountain"] * 4
    make = builder(players=players).hand(0, [spell])
    if board:
        mine = [*mine, BEAR]
        make = make.battlefield(1, [THEIRS])
    return make.battlefield(0, mine).build()


def lecturer_position(builder, *, players: int = 2):
    """The Lecturer is out and you are holding a creature spell."""
    return (
        builder(players=players)
        .battlefield(0, ["forest"] * 4 + [LECTURER])
        .hand(0, [BEAR])
        .build()
    )


def cast(game, card_id: str):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)


def run(game, *, demonstrate=True, opponent=None, retarget_to=None, limit=300):
    """Resolve everything, answering demonstrate's questions deliberately.

    Returns the decisions it saw, so a test can assert *who* was asked rather
    than only what came out the other end.
    """
    seen = []
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        if decision.kind in (
            DecisionKind.DECLARE_ATTACKERS,
            DecisionKind.DECLARE_BLOCKERS,
        ):
            break
        seen.append(decision)
        actions = game.legal_actions()
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if demonstrate else ActionKind.NO
            game.apply(next(a for a in actions if a.kind is want))
            continue
        if decision.kind is DecisionKind.CHOOSE_PLAYER and opponent is not None:
            game.apply(
                next(
                    a
                    for a in actions
                    if a.kind is ActionKind.CHOOSE
                    and decision.options[a.choice].value == opponent
                )
            )
            continue
        if decision.kind is DecisionKind.CHOOSE_MODE and retarget_to is not None:
            game.apply(
                next(
                    a
                    for a in actions
                    if a.kind is ActionKind.CHOOSE
                    and retarget_to in (decision.options[a.choice].label or "")
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    return seen


def copy_controllers(game):
    """Whose each copy was, in the order they were put on the stack.

    Read off `SPELL_COPIED` rather than off the stack: a copy is on the stack
    only until it resolves, and with nothing to respond with the engine walks
    the whole stack off inside a single `apply`.
    """
    return [
        event.player
        for event in game.state.events
        if event.type == EventType.SPELL_COPIED
    ]


def hand_sizes(game):
    return [len(p.hand) for p in game.state.players]


def creatures(game, pid):
    return [
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].controller == pid
        and "Creature" in game.state.card_of(game.state.objects[oid]).types
    ]


class TestTheChosenOpponentGetsTheCopy:
    """The half of demonstrate that was unsayable."""

    def test_the_opponents_copy_resolves_under_their_control(self, builder):
        """"You draw a card" on their copy draws *them* a card.

        The copy is not merely on the stack for them: it resolves as theirs, so
        `"player": "you"` inside it means the opponent. Hard-coded to
        `ctx.controller`, all three draws would have been mine.
        """
        game = position(builder)
        cast(game, DRAW)
        run(game)
        assert hand_sizes(game) == [2, 1], (
            "the original and my copy drew me two; their copy drew them one"
        )

    def test_only_the_chosen_opponent_copies_it(self, builder):
        """The pod boundary: one seat, not `each_opponent`.

        Invisible in a two-player game and wrong everywhere else -- which is
        exactly why `"each_opponent"` was the tempting spelling and is not the
        card.
        """
        game = position(builder, players=3)
        cast(game, DRAW)
        run(game, opponent=2)
        assert copy_controllers(game) == [0, 2], (
            "one copy mine, one the seat I chose -- and none for the other opponent"
        )
        assert hand_sizes(game) == [2, 0, 1], (
            "the seat I chose copied it; the other opponent got nothing"
        )

    def test_declining_makes_no_copies_at_all(self, builder):
        """"You **may** copy it" -- and the opponent's copy is conditional on mine.

        "If you do, choose an opponent to also copy it": saying no is not a
        half-resolution that still hands a copy across the table.
        """
        game = position(builder, players=3)
        cast(game, DRAW)
        seen = run(game, demonstrate=False)
        assert copy_controllers(game) == [], "no copies were made at all"
        assert hand_sizes(game) == [1, 0, 0], "only the original spell resolved"
        assert not [d for d in seen if d.kind is DecisionKind.CHOOSE_PLAYER], (
            "nobody is chosen when the copy was declined"
        )

    def test_a_copy_with_no_controller_clause_is_still_mine(self, builder):
        """The 706.10 default, untouched: storm and replicate gained nothing.

        `t_stormcat` writes no `controller`, so its copy belongs to the
        resolving player -- and a regression here would silently rewrite every
        storm, replicate, conspire, casualty and gravestorm card in the pool.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 4 + [STORMCAT])
            .hand(0, [ZAP])
            .battlefield(1, [THEIRS])
            .build()
        )
        cast(game, ZAP)
        assert copy_controllers(game) == [0], (
            "an unqualified copy is the resolving player's"
        )


class TestEachCopysOwnControllerChoosesItsTargets:
    """115.7b: "players may choose new targets for **their** copies"."""

    def test_the_opponent_is_asked_about_the_opponents_copy(self, builder):
        game = position(builder, spell=RALLY, board=True)
        cast(game, RALLY)
        seen = run(game, retarget_to="Test Goblin")
        retargets = [
            d
            for d in seen
            if d.kind is DecisionKind.CHOOSE_MODE and "New targets" in (d.prompt or "")
        ]
        assert [d.player for d in retargets] == [1], (
            "only the opponent's copy had a question, and it was put to them"
        )

    def test_the_options_are_the_seats_own_creatures(self, builder):
        """The chooser decides the legal set, not only who is asked.

        "Target creature you control" is a different pool for each of them. Read
        off my seat the opponent would have been offered my Grizzly Bears as a
        *new* target -- a copy pointed somewhere its controller could never
        have pointed it.
        """
        game = position(builder, spell=RALLY, board=True)
        cast(game, RALLY)
        seen = run(game, retarget_to="Test Goblin")
        options = [
            label
            for d in seen
            if d.kind is DecisionKind.CHOOSE_MODE
            for label in (o.label for o in d.options)
        ]
        assert "Test Goblin" in options, "their own creature is the legal target"
        assert options.count("Grizzly Bears") == 1, (
            "my bears appear once, as the 'leave it alone' answer -- never as a "
            "creature they may newly choose"
        )

    def test_the_retargeted_copy_pumps_their_creature(self, builder):
        game = position(builder, spell=RALLY, board=True)
        cast(game, RALLY)
        run(game, retarget_to="Test Goblin")
        theirs = creatures(game, 1)[0]
        mine = creatures(game, 0)[0]
        assert (chars(game.state, theirs).power, chars(game.state, theirs).toughness) == (
            3,
            3,
        ), "their copy resolved on their creature"
        assert chars(game.state, mine).power == 6, (
            "and the original and my own copy both landed on mine"
        )

    def test_declining_leaves_the_copy_to_be_countered(self, builder):
        """608.2b, and the reason "leave it alone" has to stay on the menu.

        The tuple the original chose is not legal for the new controller, so
        counting the legal options and skipping the question would have taken
        the choice away in exactly the case where it matters. Keeping it
        counters the copy on resolution -- which is what an opponent handed a
        spell they do not want would choose.
        """
        game = position(builder, spell=RALLY, board=True)
        cast(game, RALLY)
        run(game, retarget_to="Grizzly Bears")
        theirs = creatures(game, 1)[0]
        assert (chars(game.state, theirs).power, chars(game.state, theirs).toughness) == (
            1,
            1,
        ), "the copy kept an illegal target and was countered"
        assert chars(game.state, creatures(game, 0)[0]).power == 6, (
            "and nothing about the copies I do control changed"
        )


class TestGrantedDemonstrate:
    """Silverquill Lecturer: "creature spells you cast have demonstrate"."""

    def test_both_copies_are_tokens_one_each(self, builder):
        """"Each copy becomes a token" is 706.10's own rule, not a rider.

        A copy of a permanent spell is backed by a token object, so it resolves
        onto the battlefield and the token state-based action cleans it up --
        and the printed card is still the only non-token on the board.
        """
        game = lecturer_position(builder)
        cast(game, BEAR)
        run(game)
        bears = [
            game.state.objects[oid]
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == BEAR
        ]
        assert sorted((b.controller, b.is_token) for b in bears) == [
            (0, False),
            (0, True),
            (1, True),
        ], "the cast bear, my token copy, and the chosen opponent's token copy"

    def test_the_copies_do_not_re_trigger_it(self, builder):
        """A copy is put on the stack, not cast, so the grant does not loop."""
        game = lecturer_position(builder)
        cast(game, BEAR)
        seen = run(game)
        assert len([d for d in seen if d.kind is DecisionKind.MAY]) == 1, (
            "the trigger fired once, for the one spell that was cast"
        )


class TestTheLoaderRefusesTheNearMisses:
    def _card(self, effect, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_demo",
                "name": "Bad Demonstration",
                "oracle_text": "Bad.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "colors": ["U"],
                "color_identity": ["U"],
                "spell_effects": [effect],
                **extra,
            }
        )

    def test_choose_player_without_a_binding_is_a_load_error(self):
        """The chosen seat exists only as its `as`; without one it is thrown away."""
        with pytest.raises(DslError, match="needs an 'as'"):
            compile_card(self._card({"op": "choose_player", "players": "each_opponent"}))

    def test_an_unknown_controller_name_is_a_load_error(self):
        """Silent until resolution otherwise, and then only for the cards it reached."""
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(
                self._card({"op": "copy_spell", "controller": "each_oponent"})
            )

    def test_a_controller_naming_a_permanent_target_is_a_load_error(self):
        """`{"target": …}` keeps only player refs, so a permanent resolves to nobody.

        Which `copy_spell` reads as "no copies at all" -- a card that loads,
        resolves and does nothing.
        """
        with pytest.raises(DslError, match="never a player"):
            compile_card(
                self._card(
                    {"op": "copy_spell", "controller": {"target": "t1"}},
                    targets=[
                        {
                            "id": "t1",
                            "kind": "permanent",
                            "count": 1,
                            "selector": {"zone": "battlefield", "types": ["Creature"]},
                        }
                    ],
                )
            )

    def test_choose_players_pool_is_validated_too(self):
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(
                self._card(
                    {"op": "choose_player", "as": "who", "players": "each_oponent"}
                )
            )
