"""Buyback (702.27): a kicker with a rider on where the card goes.

The census routes it as "an additional cost like `kicker`, plus a return-to-hand
instead of the graveyard", which is exactly right and describes two halves that
were one-and-a-bit away from existing. `kicker` is the additional cost and
`cast_kicked` already outlives the spell; the rider is new, and it is four
lines beside the flashback rider it mirrors.

Three things worth holding down:

**It only ever replaces the graveyard.** The rider sits where flashback's exile
rider sits, and both are written as "instead of the graveyard" rather than as
an unconditional destination — a buyback *permanent* spell still enters the
battlefield, and a buyback spell that was countered never resolved at all.

**Unkicked is unchanged.** Buyback is optional, and a card that returned to
hand whether or not you paid would be a strictly better one.

**The label is the card's own word.** `kicker_label` exists for the same reason
`evoke_label` does: the engine's name for the mechanism is "kicker", but an
action reading "Cast Whim of Volrath (kicked)" is wrong on screen about what
the player is buying.

The loader guard needed widening rather than bypassing. It refuses a kicker
cost that nothing reads, which is right — half a kicker is a spell that charges
more and does the same thing. A buyback card has no `kicked` clause in its
effects because the *rider* is what the extra mana buys, so `buyback` now
counts as a reader.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import _default_answer

BUYBACK = "t_buyback"  # {1}{R} instant, buyback {3}, 2 damage to any target


def cast(builder, *, pay_buyback: bool, lands: int = 6):
    game = (
        builder(players=2).hand(0, [BUYBACK]).battlefield(0, ["mountain"] * lands).build()
    )
    lines = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and a.kicked is pay_buyback
    ]
    assert lines, f"no {'buyback' if pay_buyback else 'plain'} line offered"
    game.apply(lines[0])
    for _ in range(20):
        if not game.state.stack and not game.state.pending_triggers:
            break
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    (obj,) = [o for o in game.state.objects.values() if o.def_id == BUYBACK]
    return game, obj


class TestWhereTheCardGoes:
    def test_paying_returns_it_to_hand(self, builder):
        _game, obj = cast(builder, pay_buyback=True)
        assert obj.zone is Zone.HAND

    def test_not_paying_leaves_it_in_the_graveyard(self, builder):
        """Buyback is optional, and a card that came back either way would be
        a strictly better one."""
        _game, obj = cast(builder, pay_buyback=False)
        assert obj.zone is Zone.GRAVEYARD


class TestTheSpellStillWorks:
    def test_it_deals_its_damage_either_way(self, builder):
        for pay in (False, True):
            game, _obj = cast(builder, pay_buyback=pay)
            assert sum(p.life for p in game.state.players) == 78, (
                "two damage, whichever way it was cast"
            )

    def test_the_buyback_line_costs_more(self, builder):
        game = (
            builder(players=2).hand(0, [BUYBACK]).battlefield(0, ["mountain"] * 2).build()
        )
        lines = [a for a in game.legal_actions() if a.kind is ActionKind.CAST]
        assert lines, "{1}{R} is affordable on two lands"
        assert all(not a.kicked for a in lines), "but {1}{R} plus {3} is not"


class TestTheLabel:
    def test_it_says_buyback_not_kicked(self, builder):
        game = (
            builder(players=2).hand(0, [BUYBACK]).battlefield(0, ["mountain"] * 6).build()
        )
        # One line per legal target, so check them all rather than unpacking.
        lines = [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.kicked]
        assert lines
        assert all("(buyback)" in a.label for a in lines)
        assert not any("kicked" in a.label for a in lines)

    def test_an_ordinary_kicker_card_still_says_kicked(self, builder):
        """`kicker_label` defaults, so nothing shipped moved."""
        game = (
            builder(players=2)
            .hand(0, ["t_kicker_creature"])
            .battlefield(0, ["island"] * 8)
            .build()
        )
        kicked = [
            a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.kicked
        ]
        assert kicked and "(kicked)" in kicked[0].label


class TestTheLoaderGuard:
    def base(self, **extra) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Draw a card.",
            "mana_cost": "{1}{U}",
            "types": ["Sorcery"],
            "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            **extra,
        }

    def test_buyback_without_a_kicker_is_refused(self):
        """Nothing to pay means the rider never fires, and the card reads
        buyback while going to the graveyard like anything else."""
        with pytest.raises(DslError, match="needs a 'kicker' cost"):
            compile_card(CardModel.model_validate(self.base(buyback=True)))

    def test_a_kicker_nothing_reads_is_still_refused(self):
        """The guard was widened, not removed: half a kicker is a spell that
        charges more and does the same thing."""
        with pytest.raises(DslError, match="no effect reads via 'kicked'"):
            compile_card(CardModel.model_validate(self.base(kicker="{2}")))

    def test_buyback_counts_as_a_reader(self):
        compile_card(CardModel.model_validate(self.base(kicker="{2}", buyback=True)))
