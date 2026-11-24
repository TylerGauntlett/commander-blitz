"""A card put onto the battlefield under another player's control -- 110.2a.

    The Beamtown Bullies -- "{T}: Target opponent whose turn it is puts target
    nonlegendary creature card from your graveyard onto the battlefield under
    their control. It gains haste. Goad it. At the beginning of the next end
    step, exile it."

110.2a: an effect that puts a permanent onto the battlefield may say it enters
under some other player's control. The nearest spelling the DSL had --
return the card under your control, then `gain_control` it to the opponent --
is a different card: the creature would *enter* under you, so its enters
triggers would be yours (603.3a, a triggered ability's controller is its
source's controller when it triggered), its "as this enters" questions and
"would enter" replacements yours to answer, and for a moment you would control
a creature the printed card never lets you have.

So `put_onto_battlefield` and `return_from_graveyard` read ``controller`` as a
player spec (`selectors.arrival_controller`) beside the words ``"you"`` and
``"owner"``. What is pinned below:

1. The card enters under the named player, still owned by you, and its enters
   trigger is theirs -- they draw, you do not.
2. Goaded by the Bullies' controller and hasty, it must attack, and not you.
3. The delayed trigger exiles it into its owner's exile.
4. "Target opponent whose turn it is": on your own turn nobody is a legal
   target, and on an opponent's turn only that opponent is, spelled with the
   existing player-spec forms.
5. A player spec naming nobody puts nothing anywhere.
6. The loader refuses a plural spec, a player spec on a return to a hand, and
   a target the card does not declare.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import goaders
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import activations, pass_until, settle
from tests.unit.combat.test_goad import can_finish, defenders_offered, to_declare_attackers

BULLIES = "t_pupc_bullies"  # return_from_graveyard with controller {"target": "t1"}
PUTTER = "t_pupc_putter"  # the same ability through put_onto_battlefield
DRAWER = "t_etb_draw"  # "When Test ETB Draw enters, draw a card."

BOTH = pytest.mark.parametrize("source", [BULLIES, PUTTER])


def position(builder, source: str = BULLIES, *, active: int = 1):
    """Player 0's Bullies and a drawer in their graveyard, at a three-seat table.

    Player 0 holds priority in ``active``'s precombat main phase, the only
    window the printed ability is ever activated in.
    """
    game = (
        builder(players=3)
        .battlefield(0, [source])
        .graveyard(0, [DRAWER])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None
        and d.kind is DecisionKind.PRIORITY
        and d.player == 0,
    )
    src = next(o.oid for o in game.state.objects.values() if o.def_id == source)
    card = next(o.oid for o in game.state.objects.values() if o.def_id == DRAWER)
    return game, src, card


def bully(builder, source: str = BULLIES):
    game, src, card = position(builder, source)
    hands = [len(p.hand) for p in game.state.players]
    (activation,) = activations(game, src)
    game.apply(activation)
    settle(game)
    return game, card, hands


class TestItEntersUnderThem:
    @BOTH
    def test_they_control_it_and_you_still_own_it(self, builder, source):
        game, card, _ = bully(builder, source)
        obj = game.state.objects[card]
        assert obj.zone is Zone.BATTLEFIELD
        assert (obj.controller, obj.owner) == (1, 0)

    @BOTH
    def test_its_enters_trigger_is_theirs(self, builder, source):
        """603.3a: the trigger's controller is the permanent's as it entered.
        Returned under you and then handed over, you would draw."""
        game, _, hands = bully(builder, source)
        assert len(game.state.players[1].hand) == hands[1] + 1
        assert len(game.state.players[0].hand) == hands[0]


class TestItAttacksSomebodyElse:
    @BOTH
    def test_it_is_goaded_by_you_and_hasty(self, builder, source):
        game, card, _ = bully(builder, source)
        assert goaders(game.state, card) == {0}
        to_declare_attackers(game)
        assert not can_finish(game), "goaded and hasty, it must attack"
        assert defenders_offered(game, card) == [2], "and not the player who goaded it"


class TestItIsExiled:
    @BOTH
    def test_at_the_next_end_step_into_its_owners_exile(self, builder, source):
        game, card, _ = bully(builder, source)
        pass_until(game, lambda g: g.state.objects[card].zone is not Zone.BATTLEFIELD)
        assert game.state.objects[card].zone is Zone.EXILE
        assert card in game.state.players[0].exile


class TestOpponentWhoseTurnItIs:
    def offered(self, builder, active: int) -> set[int]:
        """The players the target line offers player 0 on ``active``'s turn."""
        game = (
            builder(players=3)
            .battlefield(0, [BULLIES])
            .graveyard(0, [DRAWER])
            .active(active)
            .build(advance=False)
        )
        src = next(o.oid for o in game.state.objects.values() if o.def_id == BULLIES)
        specs = game.state.registry.get(BULLIES).abilities[0].targets
        combos = enumerate_target_tuples(game.state, 0, specs, src, limit=100)
        return {ref.id for combo in combos for ref in combo if ref.kind == "player"}

    def test_on_your_turn_nobody_is_a_legal_target(self, builder):
        assert self.offered(builder, 0) == set()

    @pytest.mark.parametrize("active", [1, 2])
    def test_on_an_opponents_turn_only_that_opponent_is(self, builder, active):
        assert self.offered(builder, active) == {active}


class TestNobodyToPutIt:
    @pytest.mark.parametrize("op", ["put_onto_battlefield", "return_from_graveyard"])
    def test_a_player_spec_naming_nobody_puts_nothing(self, builder, op):
        """The target player became illegal (608.2b) while the creature card
        did not: the ability resolves, and nobody is there to put the card
        onto the battlefield, so it stays where it is rather than falling back
        to its owner or to you."""
        game, _, card = position(builder)
        put(game, op, card, {"target": "t1"}, targets={})
        assert game.state.objects[card].zone is Zone.GRAVEYARD

    @pytest.mark.parametrize("op", ["put_onto_battlefield", "return_from_graveyard"])
    def test_the_same_spec_naming_a_seat_puts_it_under_them(self, builder, op):
        """The control for the test above: the same op and card, a live target."""
        game, _, card = position(builder)
        put(game, op, card, {"target": "t1"}, targets={"t1": (TargetRef.player(2),)})
        obj = game.state.objects[card]
        assert (obj.zone, obj.controller) == (Zone.BATTLEFIELD, 2)


def put(game, op: str, card: int, controller, *, targets) -> None:
    """Run ``op`` alone over ``card`` for player 0, with ``targets`` as chosen."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None, targets=targets)
    ctx.bindings["it"] = [card]
    spec = {"op": op, "controller": controller, "objects": {"binding": "it", "zone": "graveyard"}}
    if op == "return_from_graveyard":
        spec["destination"] = "battlefield"
    for _ in execute(ctx, [spec]):
        pass


def probe(effect: dict, targets: list | None = None) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{B}",
                "types": ["Sorcery"],
                "targets": targets or [],
                "spell_effects": [effect],
            }
        )
    )


PLAYER_TARGET = [{"id": "t1", "kind": "player", "count": 1, "selector": {"controller": "opponent"}}]


class TestTheLoaderGuardsIt:
    @pytest.mark.parametrize("op", ["put_onto_battlefield", "return_from_graveyard"])
    def test_a_target_player_loads(self, op):
        probe(
            {
                "op": op,
                "destination": "battlefield",
                "controller": {"target": "t1"},
                "objects": {"zone": "graveyard", "types": ["Creature"]},
            }
            if op == "return_from_graveyard"
            else {
                "op": op,
                "controller": {"target": "t1"},
                "objects": {"zone": "graveyard", "types": ["Creature"]},
            },
            PLAYER_TARGET,
        )

    def test_a_plural_spec_is_refused(self):
        """One seat puts the card down; 'each_opponent' would hand it to the
        first of them and say nothing."""
        with pytest.raises(DslError, match="names one player"):
            probe(
                {
                    "op": "put_onto_battlefield",
                    "controller": "each_opponent",
                    "objects": {"zone": "graveyard", "types": ["Creature"]},
                }
            )

    def test_a_misspelled_word_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            probe(
                {
                    "op": "put_onto_battlefield",
                    "controller": "yuo",
                    "objects": {"zone": "graveyard", "types": ["Creature"]},
                }
            )

    def test_an_undeclared_target_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            probe(
                {
                    "op": "put_onto_battlefield",
                    "controller": {"target": "t1"},
                    "objects": {"zone": "graveyard", "types": ["Creature"]},
                }
            )

    def test_a_player_on_a_return_to_hand_is_refused(self):
        """A card goes to its owner's hand (400.3); nobody else's control
        reaches it there."""
        with pytest.raises(DslError, match="only a return to the battlefield"):
            probe(
                {
                    "op": "return_from_graveyard",
                    "destination": "hand",
                    "controller": {"target": "t1"},
                    "objects": {"zone": "graveyard", "types": ["Creature"]},
                },
                PLAYER_TARGET,
            )
