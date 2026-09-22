"""A static that makes *somebody else's* spell cost more, and charges it in life.

"Spells your opponents cast that target this creature cost an additional 3 life
to cast." — Terror of the Peaks, the witness.

It is an **additional cost** (601.2f), and the whole card is in that word. A
cost is paid as the spell is cast (601.2h), so it is charged before the spell is
on the stack and is not refunded when the spell is countered. A cost is not
optional: there is no "unless", and no moment at which the caster could decline
it. And a cost that cannot be paid makes the spell **uncastable** — so legality
must never offer a target the caster cannot afford to announce, which is the
half `TestTheOfferAndTheCharge` is about. Rule 118.4 fixes the boundary: life
may be paid down to exactly 0, so a 3-life tax is payable at 3 life and not at
2.

**Three near misses, all of them different cards.**

`spell_cost_reduction` already had the two hard clauses — `affects_spells` says
whose spells, and `targeting` reads the refs the cast actually chose (Strong
Back's "Aura spells you cast that target enchanted creature"). It points the
wrong way twice: `costs.cost_reduction` subtracts its total and clamps at zero,
so a negative amount rounds away to "costs the printed price" — a card that
loads clean and taxes nobody, which `TestTheLoader` now refuses by name — and it
is mana arithmetic end to end, so it could never charge life.

`ward` is the loud one, and taxing with it would hand the Dragon a much stronger
and differently-shaped card: ward is a triggered counter-unless-paid, so it
fires on *abilities* too, it prices the spell after it is already cast, the
opponent decides whether to pay once they are committed, and declining kills the
spell rather than merely costing life. `TestItIsACostAndNotAWard` plays out the
difference that matters most — the tax is collected from a spell that never
resolves.

`becomes_target` is a trigger, so it cannot price a cast at all: it would still
fire on a countered spell, and losing 3 life *after the fact* is something the
caster cannot decline by simply not casting.

The resource is the last design point. Life, and the loader refuses anything
else: mana would have to reach the payment solver, where a surcharge changes
which lands tap and which tuples are affordable, and every one of those seams is
a place the offer and the charge could disagree. Life is checked beside the mana
and touches none of it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.player_statics import spell_life_tax
from automtg.engine.structs import LifeLock
from tests.conftest import only_oid, pass_until

DRAKE = "t_life_toll_drake"  # spells opponents cast that target it cost 3 life more
COLLECTOR = "t_toll_collector"  # every spell opponents cast costs 2 life more
BEAR = "t_bear"  # a plain 2/2, so a second thing for the removal to aim at
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
COUNTER = "t_counterspell"  # {U}{U} instant, counter target spell


def board(builder, mine=(DRAKE,), *, life=20, hand=(BOLT,), theirs=()):
    """P0 holds the taxing permanent; P1 holds the spells and the mana."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4 + list(mine))
        .battlefield(1, ["mountain"] * 6 + list(theirs))
        .hand(1, list(hand))
        .life(1, life)
        .active(0)
        .build()
    )


def casts(game, def_id: str = BOLT) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == def_id
    ]


def offered(game, def_id: str = BOLT) -> list[str]:
    """Every way P1 is allowed to aim ``def_id`` right now, by label."""
    pass_until(game, lambda g: bool(casts(g, def_id)) or not g.legal_actions())
    return sorted(a.label or "" for a in casts(game, def_id))


def cast_at(game, oid: int, def_id: str = BOLT) -> None:
    pass_until(game, lambda g: bool(casts(g, def_id)))
    game.apply(next(a for a in casts(game, def_id) if any(r.id == oid for r in a.targets)))


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def tax(game, targets, *, pid: int = 1, spell: str = BOLT) -> int:
    return spell_life_tax(game.state, pid, game.state.registry.get(spell), targets)


def ref_to(game, oid: int):
    """The target tuple a cast aimed at ``oid`` would carry."""
    pass_until(game, lambda g: bool(casts(g)))
    return next(a for a in casts(game) if any(r.id == oid for r in a.targets)).targets


class TestWhatItTaxes:
    def test_a_spell_aimed_at_the_taxing_creature(self, builder):
        game = board(builder)
        assert tax(game, ref_to(game, only_oid(game, DRAKE, 0))) == 3

    def test_the_same_spell_aimed_elsewhere_is_free(self, builder):
        """"…that target **this creature**". The clause is the card."""
        game = board(builder, theirs=(BEAR,))
        assert tax(game, ref_to(game, only_oid(game, BEAR, 1))) == 0

    def test_nothing_with_no_taxing_permanent(self, builder):
        """The control: the same spell, the same aim, nobody collecting."""
        game = board(builder, mine=(), theirs=(BEAR,))
        assert tax(game, ref_to(game, only_oid(game, BEAR, 1))) == 0

    def test_its_own_controller_is_not_taxed(self, builder):
        """"Spells your **opponents** cast." The Dragon does not tax its owner."""
        game = board(builder)
        drake = only_oid(game, DRAKE, 0)
        assert tax(game, ref_to(game, drake), pid=0) == 0

    def test_two_of_them_stack(self, builder):
        game = board(builder, mine=(DRAKE, COLLECTOR))
        assert tax(game, ref_to(game, only_oid(game, DRAKE, 0))) == 5, (
            "3 for aiming at the Drake, 2 for casting a spell at all"
        )

    def test_a_tax_with_no_targeting_clause_reaches_every_spell(self, builder):
        game = board(builder, mine=(COLLECTOR,), theirs=(BEAR,))
        assert tax(game, ref_to(game, only_oid(game, BEAR, 1))) == 2


class TestTheGateReadsItMeanly:
    """`targets=None` is the price asked before any target exists.

    The two reductions read a `targeting` clause **generously** there, because
    refusing would drop a spell that is affordable once discounted. A tax is
    generous to the caster by doing the opposite: charging speculatively would
    refuse a spell the player can afford to aim somewhere else.
    """

    def test_a_targeting_tax_is_left_out(self, builder):
        game = board(builder)
        assert tax(game, None) == 0

    def test_an_unconditional_one_is_not(self, builder):
        game = board(builder, mine=(COLLECTOR,))
        assert tax(game, None) == 2


class TestTheOfferAndTheCharge:
    """A cost that cannot be paid makes the spell uncastable (601.2h)."""

    def test_the_target_is_offered_while_the_life_is_there(self, builder):
        game = board(builder, life=20)
        assert any("Drake" in label for label in offered(game))

    def test_life_may_be_paid_down_to_exactly_zero(self, builder):
        """118.4. At 3 life the 3-life tax is payable, and the offer stands."""
        game = board(builder, life=3)
        assert any("Drake" in label for label in offered(game))

    def test_and_no_further(self, builder):
        game = board(builder, life=2)
        assert not any("Drake" in label for label in offered(game)), (
            "an opponent at 2 cannot pay 3, so the Drake is not a legal target at all"
        )

    def test_the_other_targets_survive(self, builder):
        """Only the taxed aim goes. The spell itself is still castable."""
        game = board(builder, life=2, theirs=(BEAR,))
        labels = offered(game)
        assert labels, "the line is still on offer"
        assert any("Test Bear" in label for label in labels)

    def test_an_unconditional_tax_withdraws_the_whole_line(self, builder):
        """Nothing to aim it at cheaply, so there is no cast to offer."""
        assert offered(board(builder, mine=(COLLECTOR,), life=1)) == []

    def test_the_two_stack_at_the_boundary(self, builder):
        """3 + 2 at 3 life: the Drake goes, the Collector stays."""
        labels = offered(board(builder, mine=(DRAKE, COLLECTOR), life=3))
        assert not any("Drake" in label for label in labels)
        assert any("Collector" in label for label in labels)

    def test_a_frozen_life_total_cannot_pay_at_all(self, builder):
        """"Your life total can't change" makes paying life impossible rather
        than free — 118.4 makes it a loss of life, and 601.2h then makes the
        cast illegal. The same refusal `costs.can_pay` makes about "pay 3 life"."""
        game = board(builder, theirs=(BEAR,))
        game.state.life_locks.append(LifeLock(player=1))
        labels = offered(game)
        assert not any("Drake" in label for label in labels)
        assert any("Test Bear" in label for label in labels), "an untaxed aim is untouched"

    def test_the_life_is_actually_taken(self, builder):
        game = board(builder, life=20)
        cast_at(game, only_oid(game, DRAKE, 0))
        assert game.state.players[1].life == 17

    def test_and_nothing_is_taken_for_an_untaxed_aim(self, builder):
        game = board(builder, life=20, theirs=(BEAR,))
        cast_at(game, only_oid(game, BEAR, 1))
        assert game.state.players[1].life == 20


class TestItIsACostAndNotAWard:
    """Ward prices the spell after it is cast and kills it unpaid. This does not."""

    def test_the_tax_is_paid_before_the_spell_resolves(self, builder):
        game = board(builder, life=20)
        cast_at(game, only_oid(game, DRAKE, 0))
        types = [e.type for e in game.state.events]
        assert "life_lost" in types
        assert types.index("life_lost") < types.index("spell_resolved"), (
            "a cost is paid as the spell is cast, not when it resolves"
        )

    def test_a_countered_spell_has_still_been_paid_for(self, builder):
        """The difference that matters: ward refunds nothing because ward was
        never paid, and this was paid before there was anything to counter."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 4 + [DRAKE])
            .battlefield(1, ["mountain"] * 6)
            .hand(0, [COUNTER])
            .hand(1, [BOLT])
            .life(1, 20)
            .active(0)
            .build()
        )
        drake = only_oid(game, DRAKE, 0)
        cast_at(game, drake)
        assert game.state.players[1].life == 17

        item = game.state.stack[-1]
        bolt = item.oid
        pass_until(game, lambda g: bool(casts(g, COUNTER)))
        game.apply(
            next(a for a in casts(game, COUNTER) if any(r.id == item.sid for r in a.targets))
        )
        settle(game)

        assert game.state.objects[bolt].zone is Zone.GRAVEYARD, "the Bolt was countered"
        assert game.state.objects[only_oid(game, DRAKE, 0)].damage == 0
        assert game.state.players[1].life == 17, "and the 3 life stays spent"

    def test_nobody_is_asked_anything(self, builder):
        """A cost is not a `may`. Ward's whole shape is the prompt it raises."""
        game = board(builder, life=20)
        cast_at(game, only_oid(game, DRAKE, 0))
        assert "ability_triggered" not in [e.type for e in game.state.events]


class TestItWearsOffWithItsSource:
    def test_killing_the_taxing_permanent_ends_the_tax(self, builder):
        """A static, so it lasts exactly as long as the permanent does."""
        game = board(builder, life=20, hand=(BOLT, BOLT, BOLT), theirs=(BEAR,))
        drake = only_oid(game, DRAKE, 0)
        cast_at(game, drake)
        settle(game)
        cast_at(game, drake)
        settle(game)
        assert game.state.objects[drake].zone is Zone.GRAVEYARD

        assert tax(game, ref_to(game, only_oid(game, BEAR, 1))) == 0
        life = game.state.players[1].life
        cast_at(game, only_oid(game, BEAR, 1))
        assert game.state.players[1].life == life


def probe(**static) -> dict:
    text = "Spells your opponents cast cost an additional 3 life to cast."
    base = {
        "kind": "static",
        "text": text,
        "effect": "spell_cost_increase",
        "affects_spells": {"controller": "opponent"},
        "cost": {"pay_life": 3},
    }
    base.update(static)
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": text,
        "mana_cost": "{R}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [base],
    }


class TestTheLoader:
    def test_the_shipped_shape_loads(self):
        compile_card(CardModel.model_validate(probe()))

    def test_with_a_targeting_clause_too(self):
        compile_card(CardModel.model_validate(probe(targeting={"self_only": True})))

    def test_a_filter_is_required(self):
        """Without one it taxes every cast in the game, and loads clean."""
        payload = probe()
        del payload["abilities"][0]["affects_spells"]
        with pytest.raises(DslError, match="needs 'affects_spells'"):
            compile_card(CardModel.model_validate(payload))

    def test_a_price_is_required(self):
        payload = probe()
        del payload["abilities"][0]["cost"]
        with pytest.raises(DslError, match="needs a 'cost'"):
            compile_card(CardModel.model_validate(payload))

    def test_a_tax_of_zero_is_refused(self):
        with pytest.raises(DslError, match="1 or more"):
            compile_card(CardModel.model_validate(probe(cost={"pay_life": 0})))

    def test_an_empty_cost_is_refused_the_same_way(self):
        """`prune_cost` drops a zero, so "pay 0 life" and "pay nothing" are one
        card: the line prints and charges nobody."""
        with pytest.raises(DslError, match="1 or more"):
            compile_card(CardModel.model_validate(probe(cost={})))

    def test_mana_is_refused(self):
        """It would have to reach the payment solver, where the offer and the
        charge have four more chances to disagree. No printed card asks for it."""
        with pytest.raises(DslError, match="paid in life only"):
            compile_card(CardModel.model_validate(probe(cost={"mana": "{1}"})))

    def test_a_sacrifice_is_refused(self):
        """`attack_tax`'s reason: it would ask a question inside the cast."""
        with pytest.raises(DslError, match="paid in life only"):
            compile_card(
                CardModel.model_validate(
                    probe(cost={"pay_life": 3, "sacrifice": {"types": ["Creature"]}})
                )
            )

    def test_affects_is_the_wrong_key(self):
        with pytest.raises(DslError, match="not 'affects'"):
            compile_card(
                CardModel.model_validate(probe(affects={"types": ["Creature"]}))
            )

    def test_board_state_keys_are_refused(self):
        with pytest.raises(DslError, match="no board state"):
            compile_card(
                CardModel.model_validate(
                    probe(affects_spells={"controller": "opponent", "tapped": False})
                )
            )

    def test_an_amount_is_refused(self):
        """The size is the `cost`. An `amount` here is read by nothing and looks,
        on the card, exactly like the number being charged."""
        with pytest.raises(DslError, match="priced by its 'cost'"):
            compile_card(CardModel.model_validate(probe(amount={"const": 3})))


class TestTheReductionCannotBeWrittenBackwards:
    """The silent-wrong-card this effect exists to make unnecessary.

    `costs.cost_reduction` subtracts the reduction total and clamps it at zero,
    so `amount: -3` on a `spell_cost_reduction` would load clean, print "costs 3
    more" and charge the printed price. Refused by name, pointing at the effect
    that means it.
    """

    def test_a_negative_reduction_is_a_load_error(self):
        payload = probe(
            effect="spell_cost_reduction",
            affects_spells={"controller": "opponent"},
            amount=-3,
        )
        del payload["abilities"][0]["cost"]
        with pytest.raises(DslError, match="spell_cost_increase"):
            compile_card(CardModel.model_validate(payload))

    def test_the_wrapped_spelling_is_refused_too(self):
        """`{"const": -3}` is the spelling a card would actually use — every
        shipped reduction writes its amount that way."""
        payload = probe(
            effect="spell_cost_reduction",
            affects_spells={"controller": "opponent"},
            amount={"const": -3},
        )
        del payload["abilities"][0]["cost"]
        with pytest.raises(DslError, match="spell_cost_increase"):
            compile_card(CardModel.model_validate(payload))

    def test_a_reduction_of_zero_still_loads(self):
        """Only the sign is refused: `{"const": 0}` is a conditional discount
        that happens not to apply, which is an ordinary thing for one to be."""
        payload = probe(
            effect="spell_cost_reduction",
            affects_spells={"controller": "you"},
            amount=0,
        )
        del payload["abilities"][0]["cost"]
        compile_card(CardModel.model_validate(payload))
