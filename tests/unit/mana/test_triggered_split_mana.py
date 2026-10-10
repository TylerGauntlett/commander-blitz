"""An attack trigger that rituals X mana the player divides, spendable only on spells.

    "Whenever Klauth attacks, add X mana in **any combination of colors**, where
    X is **the total power of attacking creatures**. **Spend this mana only to
    cast spells.** Until end of turn, you don't lose this mana as steps and
    phases end."                                 -- Klauth, Unrivaled Ancient

Two things the engine had only in the one place that could not have them, and
each of them, omitted, ships a card stronger or weaker than the printed one.

**The combination, off a trigger.** `split`/`amount` were compiled only under
`is_mana_ability`, which the loader allows on activated abilities alone, and a
mana ability may never stop to ask (605.1a) -- so `costs._split_options` answers
the combination by *offering every composition to the payment solver*. A
triggered ability has no payment to fold a choice into and every right to ask,
so `ops_mana._add_split_mana` asks: one mana at a time, over the named colours.
The near miss is Tanuki Transplanter's shape -- a `repeat` of an `add_mana` of
one *fixed* colour -- which spells the size and the persistence exactly and
still fixes the colour on the card. For a five-colour Dragon that is a strictly
worse card, and "any combination" is the whole of why anybody plays it.

**The restriction, on mana an effect made.** `mana.ManaSource` carries a
restriction and `costs.mana_sources` enforces it by *withholding the untapped
source* -- which works only because a mana ability's mana is tapped at the
instant it is spent. Klauth's mana is already floating, so the pool is the only
thing left that can remember what it may pay for: `Pip` grows a `restriction`,
`ManaPool.spendable` reports the pool as one purpose may spend it, and
`ManaPool.spend` takes only pips that permit that purpose. Without it the ritual
would fund activated abilities the printed card refuses to fund -- an infinite
combo enabler rather than a big-mana payoff.

**X is a total power, read at resolution.** Not the *count* of attackers, which
is the same number on a board of 1/1s and wildly wrong on a board of Dragons;
and read when the trigger resolves rather than when it was put on the stack,
because that is when the effect happens.

The persistence clause needed nothing: `persists_until_end_of_turn` already
rides on the pip (see `test_mana_doesnt_empty.py`), and it is asserted here
anyway, because a ritual that evaporated at the end of the declare-attackers
step never reaches the main phase the card is for.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import (
    CAST,
    SYMBOL_INDEX,
    ManaCost,
    ManaPool,
    ManaRestriction,
    RestrictionGroup,
    SpendPurpose,
)
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

WYRM = "t_tsm_wyrm"  # the Klauth line in full
RITUAL = "t_tsm_ritual"  # the same trigger with no spend restriction
RELIC = "t_tsm_relic"  # "{1}: You gain 1 life." -- what the mana may not pay for
SPARK = "t_tsm_bolt"  # a {1} instant -- what it may

#: The order `split` names the colours in, which is the order the prompt offers.
SPLIT = ["W", "U", "B", "R", "G"]

CAST_ANYTHING = ManaRestriction(cast=(RestrictionGroup(),))


def position(builder, dragon: str = WYRM, *, friends: list[str] | None = None):
    """Seat 0 in their precombat main with a Dragon, a relic and a spell in hand.

    No lands anywhere: every assertion below is about what the *pool* can pay
    for, and an untapped land would fund the relic whatever the pool said.
    """
    return (
        builder(players=2)
        .battlefield(0, [dragon, RELIC, *(friends or [])])
        .hand(0, [SPARK])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def attack_with(game, *card_ids: str) -> None:
    """Declare the named creatures as attackers on seat 1, and finish."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for card_id in card_ids:
        game.apply(
            find_action(
                game,
                ActionKind.ADD_ATTACKER,
                source=only_oid(game, card_id, 0),
                targets=(TargetRef.player(1),),
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def divide(game, colors: str) -> None:
    """Answer the trigger's one-mana-at-a-time colour choice, in order.

    ``"RRGG"`` is the player dividing four mana as two red and two green --
    the thing a fixed-colour `repeat` cannot say. Priority is passed between
    answers because the trigger resolves off the stack.
    """
    for color in colors:
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.CHOOSE_MODE,
        )
        game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index(color)))


def pool(game, pid: int = 0) -> dict[str, int]:
    return game.state.players[pid].mana_pool.to_dict()


def can_activate(game, card_id: str, pid: int = 0) -> bool:
    oid = only_oid(game, card_id, pid)
    return any(
        a.kind is ActionKind.ACTIVATE and a.source == oid for a in game.legal_actions()
    )


def can_cast(game, card_id: str, pid: int = 0) -> bool:
    return any(
        a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestHowMuchManaItMakes:
    def test_x_is_the_total_power_of_the_attackers(self, builder):
        """Five power attacking, five mana. Not one, which is the count."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        assert sum(pool(game).values()) == 5

    def test_a_second_attacker_adds_its_power_and_not_one(self, builder):
        """A 2/2 joining a 5/5 is +2, not +1.

        The whole difference between "total power" and "number of attacking
        creatures", and the two numbers coincide on any board of 1/1s -- which
        is why the witness here is a bear.
        """
        game = position(builder, friends=["t_bear"])
        attack_with(game, WYRM, "t_bear")
        divide(game, "RRRRRRR")
        assert sum(pool(game).values()) == 7

    def test_a_creature_left_at_home_is_not_counted(self, builder):
        """"Attacking", not "you control": the relic's neighbour stays back."""
        game = position(builder, friends=["t_bear"])
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        assert sum(pool(game).values()) == 5


class TestTheCombinationIsTheirs:
    def test_the_player_divides_x_among_the_colours(self, builder):
        """The claim the card is played for, and the one a fixed-colour
        `repeat` cannot make: five mana, four different colours."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "WUBRR")
        assert pool(game) == {"W": 1, "U": 1, "B": 1, "R": 2}

    def test_it_is_not_x_of_one_chosen_colour(self, builder):
        """The near miss stated as an assertion: a `choose_mode` over five
        `add_mana`s picks a colour once and makes X of it, so a mixed pool is
        the only thing that tells the two cards apart."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "WWUUB")
        assert len(pool(game)) > 1

    def test_all_of_one_colour_is_still_a_legal_division(self, builder):
        """"Any combination" includes the degenerate one."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "GGGGG")
        assert pool(game) == {"G": 5}

    def test_it_asks_once_per_mana(self, builder):
        """Five questions for five mana. Asked once for the whole ritual, the
        division could only ever be X of one colour."""
        game = position(builder)
        attack_with(game, WYRM)
        asked = 0
        for _ in range(5):
            pass_until(
                game,
                lambda g: g.pending() and g.pending().kind is DecisionKind.CHOOSE_MODE,
            )
            asked += 1
            game.apply(find_action(game, ActionKind.CHOOSE, choice=SPLIT.index("R")))
        assert asked == 5


class TestTheRestrictionBinds:
    def test_the_mana_pays_for_a_spell(self, builder):
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        assert can_cast(game, SPARK)

    def test_the_mana_does_not_pay_for_an_activated_ability(self, builder):
        """"Spend this mana only to cast spells." Five mana floating and the
        relic's {1} is still unaffordable -- which is the printed card, and the
        line the engine could not say at all before `Pip.restriction`."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        assert not can_activate(game, RELIC)

    def test_the_same_mana_without_the_clause_does_pay_for_it(self, builder):
        """The control. The serpent's ritual is the identical trigger with the
        restriction left off, so this is the assertion above measuring the
        clause rather than measuring effect-made mana."""
        game = position(builder, RITUAL)
        attack_with(game, RITUAL)
        divide(game, "RRRRR")
        assert can_activate(game, RELIC)

    def test_casting_really_spends_it(self, builder):
        """Offered *and* payable: an offer the payment then could not meet would
        strand the cast mid-resolution."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source is not None
            and game.state.objects[a.source].def_id == SPARK
        )
        game.apply(action)
        assert sum(pool(game).values()) == 4


class TestTheManaLastsTheTurn:
    def test_it_survives_the_end_of_the_declare_attackers_step(self, builder):
        """500.4 empties the pool at every boundary, and a ritual that did not
        say otherwise would never reach the main phase it is made for."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert sum(pool(game).values()) == 5

    def test_it_does_not_survive_the_turn(self, builder):
        """"Until end of turn". The cleanup step's `advance` is where the
        promise runs out; floating into the untap step would hand seat 0 mana
        on somebody else's turn."""
        game = position(builder)
        attack_with(game, WYRM)
        divide(game, "RRRRR")
        pass_until(game, lambda g: g.state.turn > 1)
        assert pool(game) == {}


class TestThePoolCarriesTheRestriction:
    """`ManaPool` in isolation, where the rule is easiest to read."""

    def _pool(self) -> ManaPool:
        pool = ManaPool()
        pool.add("R", 2, restriction=CAST_ANYTHING)
        pool.add("R", 1)
        return pool

    def test_a_restricted_pip_is_not_spendable_for_an_ability(self):
        purpose = SpendPurpose(kind="activate", names=frozenset({"artifact"}))
        assert self._pool().spendable(purpose)[SYMBOL_INDEX["R"]] == 1

    def test_it_is_spendable_for_a_spell(self):
        purpose = SpendPurpose(kind=CAST, names=frozenset({"instant"}))
        assert self._pool().spendable(purpose)[SYMBOL_INDEX["R"]] == 3

    def test_no_purpose_at_all_withholds_it(self):
        """The same under-count `ManaSource.permits` makes for the same reason:
        the safe direction for a number the AI reads."""
        assert self._pool().spendable()[SYMBOL_INDEX["R"]] == 1

    def test_an_unrestricted_pool_is_reported_untouched(self):
        pool = ManaPool()
        pool.add("R", 3)
        assert pool.spendable() == tuple(pool.amounts)

    def test_spending_skips_the_pips_it_may_not_take(self):
        """The take and the offer must agree. `_take` is newest-first, and the
        restricted pips here are the older two -- so a take that ignored the
        purpose would reach straight past the one legal pip."""
        pool = self._pool()
        purpose = SpendPurpose(kind="activate", names=frozenset({"artifact"}))
        pool.spend(ManaCost.parse("{R}").with_x(0), purpose)
        assert pool.amounts[SYMBOL_INDEX["R"]] == 2
        assert all(pip.restriction is not None for pip in pool.tags[SYMBOL_INDEX["R"]])

    def test_spending_more_than_it_permits_is_refused(self):
        """Rather than silently taking a forbidden pip: `spendable` promised
        there would be enough, and a take that reached past it would make the
        two disagree."""
        pool = self._pool()
        purpose = SpendPurpose(kind="activate", names=frozenset({"artifact"}))
        with pytest.raises(ValueError):
            pool.spend(ManaCost.parse("{R}{R}").with_x(0), purpose)


class TestTheLoaderPlacesIt:
    def _card(self, effects):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Add mana.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": effects,
            }
        )

    def test_a_well_formed_split_loads(self):
        compile_card(
            self._card(
                [
                    {
                        "op": "add_mana",
                        "split": ["U", "R"],
                        "amount": {"const": 2},
                        "mana_restriction": {"cast": "any"},
                    }
                ]
            )
        )

    def test_a_split_without_an_amount_is_refused(self):
        """It would load clean and add nothing -- a card printing "add X mana"
        that adds none."""
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(self._card([{"op": "add_mana", "split": ["U", "R"]}]))

    def test_a_one_colour_split_is_refused(self):
        with pytest.raises(DslError, match="two or more colours"):
            compile_card(
                self._card([{"op": "add_mana", "split": ["U"], "amount": {"const": 2}}])
            )

    def test_an_unknown_symbol_is_refused(self):
        with pytest.raises(DslError, match="unknown mana symbols"):
            compile_card(
                self._card(
                    [{"op": "add_mana", "split": ["U", "Q"], "amount": {"const": 2}}]
                )
            )

    def test_a_malformed_restriction_fails_at_load(self):
        """Compiled twice on purpose -- here and again as the effect resolves --
        so a typo is a test failure rather than a game that stops."""
        with pytest.raises(DslError, match="unparsable mana restriction"):
            compile_card(
                self._card(
                    [{"op": "add_mana", "mana": "{G}", "mana_restriction": ["7"]}]
                )
            )

    def test_the_restriction_is_refused_on_any_other_op(self):
        """Read by nobody elsewhere, so the printed clause would vanish."""
        with pytest.raises(DslError, match="read by nobody"):
            compile_card(
                self._card(
                    [
                        {
                            "op": "draw",
                            "amount": {"const": 1},
                            "mana_restriction": {"cast": "any"},
                        }
                    ]
                )
            )

    def test_it_is_refused_on_a_mana_ability_s_add_mana(self):
        """A mana ability's restriction belongs to the *ability*, where
        `costs.mana_sources` reads it. The effect is never run, so a restriction
        written on it would be silently dropped."""
        with pytest.raises(DslError, match="belongs on the ability"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "x",
                        "name": "X",
                        "oracle_text": "{T}: Add {G}.",
                        "types": ["Land"],
                        "abilities": [
                            {
                                "kind": "activated",
                                "text": "{T}: Add {G}.",
                                "is_mana_ability": True,
                                "cost": {"tap": True},
                                "effects": [
                                    {
                                        "op": "add_mana",
                                        "mana": "{G}",
                                        "mana_restriction": "creature",
                                    }
                                ],
                            }
                        ],
                    }
                )
            )
