""""This token can't be blocked this turn except by creatures with haste" --
the one-turn `unblockable` with an exemption, aimed at a blocker filter.

Rule 509.1b: a blocker may be declared only if no restriction forbids it. The
Gingerbrute's "{1}:" line is such a restriction, and it forbids *some*
blockers: every one that lacks haste. Two near misses would load clean and be a
different card.

- Plain `unblockable` refuses every blocker, so a Gingerbrute that paid {1}
  would be blockable by nothing at all -- strictly better than printed. The
  exemption lives on the same table entry (`Unblockable.except_blockers`) and
  is asked per blocker in `combat.unblockable`.
- The `block_restriction` static ("can't be blocked except by Walls" on Joven's
  Tools' attacker, the printed form) lasts as long as its permanent and has no
  clock, so an activation cannot switch it on for one turn.

The witness is the **Gingerbrute** token (`gingerbrute_1_1_c`) that Ginger,
Queen of Sweets makes. What is pinned below, each a way this could be silently
wrong rather than broken:

1. A blocker without haste is refused and one with haste is offered -- the
   exemption is not dropped, and it is not the whole board.
2. The filter reads the blocker's **derived** characteristics when blockers
   are declared: a creature that gained haste after the ability resolved may
   block, which a printed-face read would deny.
3. Asked with no blocker, the attacker is *not* "unblockable": nothing reads an
   exemption-carrying entry as total evasion (the AI's board read asks this).
4. Two entries on one attacker are two restrictions, and a plain one beside an
   exempting one still refuses everybody.
5. It wears off at cleanup like the plain form.
6. The loader refuses an empty filter, an unknown key, and a "whose" key.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import grant_keyword
from commanderblitz.engine.temp_effects import make_unblockable
from tests.conftest import _default_answer, activations, only_oid, pass_until

BEAR = "t_bear"
GINGERBRUTE = "gingerbrute_1_1_c"
KNIGHT = "human_knight_2_2_r_trample_haste"
HASTE = {"keywords": ["haste"]}


def position(builder, *, mine=(BEAR,), theirs=(BEAR, KNIGHT), lands=0):
    """Player 0 attacks with ``mine``; player 1 defends with ``theirs``."""
    b = builder(players=2)
    b.battlefield(0, list(mine) + ["island"] * lands)
    b.battlefield(1, list(theirs))
    return b.active(0).step(Step.UNTAP).build()


def to_declare_blockers(game, limit: int = 80):
    """Advance to the declare-blockers decision, attacking with every creature."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_BLOCKERS:
            return game
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            adds = [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]
            game.apply(adds[0] if adds else _default_answer(game, decision))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare blockers")


def blockers_offered(game) -> list[int]:
    return sorted(
        {
            a.source
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source is not None
        }
    )


class TestOnlyTheExemptMayBlock:
    def test_the_hasty_blocker_is_offered_and_the_other_is_not(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        bear, knight = only_oid(game, BEAR, 1), only_oid(game, KNIGHT, 1)
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=HASTE)
        to_declare_blockers(game)
        assert blockers_offered(game) == [knight]
        assert not combat_mod.can_block(game.state, bear, mine, 1)

    def test_without_the_exemption_nobody_blocks(self, builder):
        """The contrast that makes the filter load-bearing."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_haste_granted_after_resolution_is_read(self, builder):
        """Derived, at declaration: the bear that gained haste may block."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        bear = only_oid(game, BEAR, 1)
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=HASTE)
        grant_keyword(game.state, bear, "haste")
        to_declare_blockers(game)
        assert bear in blockers_offered(game)

    def test_a_union_exempts_either_branch(self, builder):
        """"Except by artifact creatures and/or red creatures" (Firefright Mage)."""
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        exempt = {"any_of": [{"types": ["Artifact"]}, {"colors": ["R"]}]}
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=exempt)
        to_declare_blockers(game)
        assert blockers_offered(game) == [only_oid(game, KNIGHT, 1)]


class TestItIsNotTotalEvasion:
    def test_asked_without_a_blocker_it_is_blockable(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=HASTE)
        assert not combat_mod.unblockable(game.state, mine)
        assert combat_mod.unblockable(game.state, mine, only_oid(game, BEAR, 1))
        assert not combat_mod.unblockable(game.state, mine, only_oid(game, KNIGHT, 1))

    def test_a_plain_entry_beside_it_still_refuses_everyone(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=HASTE)
        make_unblockable(game.state, [mine], "this_turn", player=0)
        assert len(game.state.unblockables) == 2, "different entries, both recorded"
        to_declare_blockers(game)
        assert blockers_offered(game) == []

    def test_two_exemptions_must_both_be_met(self, builder):
        game = position(builder)
        mine = only_oid(game, BEAR, 0)
        make_unblockable(game.state, [mine], "this_turn", player=0, except_blockers=HASTE)
        make_unblockable(
            game.state, [mine], "this_turn", player=0, except_blockers={"subtypes": ["Bear"]}
        )
        to_declare_blockers(game)
        assert blockers_offered(game) == [], "the knight is no Bear, the bear has no haste"


class TestTheGingerbrute:
    """The token's own activation, which the authoring verifier never makes."""

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [GINGERBRUTE, "island", "island"])
            .battlefield(1, [BEAR, KNIGHT])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_the_activation_records_an_exempting_entry_on_itself(self, builder):
        game = self.board(builder)
        brute = only_oid(game, GINGERBRUTE, 0)
        game.apply(activations(game, brute, 0)[0])
        pass_until(game, lambda g: not g.state.stack)
        [entry] = game.state.unblockables
        assert entry.objects == (brute,)
        assert entry.except_blockers == HASTE
        to_declare_blockers(game)
        assert blockers_offered(game) == [only_oid(game, KNIGHT, 1)]

    def test_unactivated_it_is_an_ordinary_attacker(self, builder):
        game = self.board(builder)
        to_declare_blockers(game)
        assert blockers_offered(game) == sorted(
            [only_oid(game, BEAR, 1), only_oid(game, KNIGHT, 1)]
        )

    def test_it_wears_off_at_cleanup(self, builder):
        game = self.board(builder)
        brute = only_oid(game, GINGERBRUTE, 0)
        game.apply(activations(game, brute, 0)[0])
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.unblockables == []


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


def spec(exempt) -> dict:
    return {
        "op": "unblockable",
        "objects": {"types": ["Creature"]},
        "duration": "this_turn",
        "except_blockers": exempt,
    }


class TestTheLoaderGuardsIt:
    def test_the_printed_shapes_compile(self):
        probe(spec(HASTE))
        probe(spec({"any_of": [{"types": ["Artifact"]}, {"colors": ["R"]}]}))

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError, match="non-empty static filter"):
            probe(spec({}))

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            probe(spec({"zone": "battlefield"}))

    def test_a_whose_key_is_refused(self):
        with pytest.raises(DslError, match="not whose it is"):
            probe(spec({"controller": "opponent", "keywords": ["haste"]}))

    def test_an_empty_union_is_refused(self):
        with pytest.raises(DslError, match="any_of"):
            probe(spec({"any_of": []}))
