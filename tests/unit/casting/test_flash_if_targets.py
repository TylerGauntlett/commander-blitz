""""You may cast this spell as though it had flash if it targets a commander."

Timely Ward is the witness: an Aura whose flash permission is conditioned on
its own target. It is `flash_if_targets`, a filter over the targets the cast
chose, in the language of `cost_reduction.targeting`.

The rules argument. 307.1 lets an Aura be cast only by the active player in a
main phase with an empty stack, and "as though it had flash" lifts that. The
condition reads the spell's targets, which are chosen at 601.2c, and 601.3
checks a permission to cast when the spell is proposed -- once, against those
targets. So outside sorcery timing the cast is legal only aimed at a commander,
and it is not asked again afterwards: a target that stops matching later leaves
a spell that was legally cast. At sorcery timing, or under another flash
permission (Vedalken Orrery), the card is cast as printed and aims at any
creature.

Without this the card has two wrong readings. `as_though_flash: true` lets it
enchant any creature at instant speed, a strictly better card than the printed
one; dropping the sentence makes it sorcery-speed only, strictly worse. And a
cast offered at instant speed with the target chosen freely would let it end
up on a non-commander, which the permission never allowed.

The card is `t_fit_ward`, in tests/data/flash_if_targets.cards.json.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.casting import flash_if_targets_owed
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, settle

WARD = "t_fit_ward"  # {W} Aura: flash if it targets a commander; indestructible
BEAR = "t_ground_bear"  # 2/2, the creature that is (or is not) a commander
ORRERY = "t_orrery"  # you may cast spells as though they had flash
BOLT = "t_bolt"  # {R} instant, something to keep a priority stop open
PLAINS = "plains"

TARGETS = [
    {
        "id": "enchanted",
        "kind": "permanent",
        "selector": {"types": ["Creature"], "zone": "battlefield"},
    }
]


def position(
    builder,
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    commanders: tuple[int, ...] = (0,),
    extra: tuple[str, ...] = (),
    active: int = 0,
):
    """Each player controls one bear; ``commanders`` names whose bear is a
    commander. Player 0 holds the Ward and a bolt at ``step`` on ``active``'s
    turn."""
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS, PLAINS, "mountain", BEAR, *extra])
        .battlefield(1, [PLAINS, BEAR])
        .hand(0, [WARD, BOLT])
        .hand(1, [BOLT])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(step)
        .active(active)
        .build(advance=False)
    )
    for pid in commanders:
        game.state.objects[bear(game, pid)].is_commander = True
    for player in game.state.players:
        player.full_control = True
    game._advance()
    return game


def bear(game, pid: int) -> int:
    (oid,) = oids_of(game, BEAR, pid)
    return oid


def casts(game, card_id: str = WARD) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def aimed_at(lines) -> set[int]:
    return {ref.id for line in lines for ref in line.targets}


def ward_oid(game) -> int:
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == WARD)


def owed(game) -> bool:
    return flash_if_targets_owed(game.state, 0, game.state.card(ward_oid(game)))


def indestructible(game, oid: int) -> bool:
    return "indestructible" in chars(game.state, oid).keywords


def ward_card(**extra):
    base = {
        "id": "x",
        "name": "X",
        "oracle_text": "",
        "mana_cost": "{W}",
        "types": ["Enchantment"],
        "subtypes": ["Aura"],
        "targets": TARGETS,
        "flash_if_targets": {"is_commander": True},
    }
    base.update(extra)
    return CardModel.model_validate(base)


class TestAtSorceryTiming:
    """The card is cast as printed: any creature is a legal target."""

    def test_both_bears_are_offered(self, builder):
        game = position(builder)
        assert not owed(game)
        assert aimed_at(casts(game)) == {bear(game, 0), bear(game, 1)}

    def test_no_commander_is_needed(self, builder):
        game = position(builder, commanders=())
        assert aimed_at(casts(game)) == {bear(game, 0), bear(game, 1)}


class TestAtInstantTiming:
    """Outside 307.1 the cast is offered only at a commander (601.2c, 601.3)."""

    @pytest.mark.parametrize("step", [Step.UPKEEP, Step.BEGIN_COMBAT, Step.END_STEP])
    def test_only_the_commander_is_offered(self, builder, step):
        game = position(builder, step=step)
        assert owed(game)
        assert aimed_at(casts(game)) == {bear(game, 0)}

    def test_an_opponents_commander_counts(self, builder):
        game = position(builder, step=Step.UPKEEP, commanders=(1,))
        assert aimed_at(casts(game)) == {bear(game, 1)}

    def test_every_commander_is_offered(self, builder):
        game = position(builder, step=Step.UPKEEP, commanders=(0, 1))
        assert aimed_at(casts(game)) == {bear(game, 0), bear(game, 1)}

    def test_without_a_commander_it_is_not_castable(self, builder):
        game = position(builder, step=Step.UPKEEP, commanders=())
        assert casts(game, BOLT), "the control: player 0 holds priority here"
        assert casts(game) == []

    def test_on_an_opponents_turn(self, builder):
        """In the opponent's main phase, asked of player 0's priority actions."""
        game = position(builder, active=1)
        lines = [
            a
            for a in legality._priority_actions(game.state, 0)
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == WARD
        ]
        assert aimed_at(lines) == {bear(game, 0)}

    def test_it_resolves_onto_the_commander(self, builder):
        game = position(builder, step=Step.UPKEEP)
        (line,) = casts(game)
        game.apply(line)
        settle(game)
        assert indestructible(game, bear(game, 0))
        assert not indestructible(game, bear(game, 1))


class TestCheckedOnceWhenProposed:
    """601.3 asks the permission when the spell is proposed, and not again."""

    def test_a_target_that_stops_matching_still_gets_the_aura(self, builder):
        game = position(builder, step=Step.UPKEEP)
        (line,) = casts(game)
        game.apply(line)
        game.state.objects[bear(game, 0)].is_commander = False
        settle(game)
        assert indestructible(game, bear(game, 0))


class TestAnotherPermissionIsNotThisOne:
    """Under Vedalken Orrery the cast is legal without the card's permission,
    so its condition does not narrow the targets."""

    def test_the_orrery_lets_it_aim_anywhere(self, builder):
        game = position(builder, step=Step.UPKEEP, extra=(ORRERY,))
        assert not owed(game)
        assert aimed_at(casts(game)) == {bear(game, 0), bear(game, 1)}


class TestTheDiagnosticAgrees:
    """`legality.unplayable_reason` names the gate the action list closed."""

    def test_no_commander_is_timing(self, builder):
        game = position(builder, step=Step.UPKEEP, commanders=())
        assert legality.unplayable_reason(game.state, 0, ward_oid(game)) == "timing"

    def test_a_commander_has_no_reason(self, builder):
        game = position(builder, step=Step.UPKEEP)
        assert legality.unplayable_reason(game.state, 0, ward_oid(game)) is None


class TestTheLoader:
    def test_the_filter_compiles(self):
        card = compile_card(ward_card())
        assert card.flash_if_targets == {"is_commander": True}
        assert not card.as_though_flash

    @pytest.mark.parametrize("extra", [{"as_though_flash": True}, {"flash_cost": {"mana": "{2}"}}])
    def test_it_is_refused_beside_another_own_permission(self, extra):
        with pytest.raises(DslError, match="one of the three"):
            compile_card(ward_card(**extra))

    def test_it_is_refused_on_an_instant(self):
        with pytest.raises(DslError, match="never be asked"):
            compile_card(ward_card(types=["Instant"], subtypes=[]))

    def test_it_is_refused_without_targets(self):
        with pytest.raises(DslError, match="no targets"):
            compile_card(ward_card(targets=[]))

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError, match="non-empty filter"):
            compile_card(ward_card(flash_if_targets={}))

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(ward_card(flash_if_targets={"is_commandr": True}))


class TestTheResidualGateReadsTheLine:
    """The authoring residual gate claims the printed line for
    `flash_if_targets`, and only when the card declares it."""

    LINE = "You may cast this spell as though it had flash if it targets a commander."

    def test_the_condition_claims_the_line(self):
        from commanderblitz.cards.authoring.verify import residual_text

        card = compile_card(ward_card(oracle_text=self.LINE))
        assert residual_text(card, self.LINE) == ""

    def test_without_it_the_line_stays(self):
        from commanderblitz.cards.authoring.verify import residual_text

        card = compile_card(ward_card(oracle_text=self.LINE, flash_if_targets=None))
        assert residual_text(card, self.LINE) != ""
