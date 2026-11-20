"""Every activated ability of another card: the `gain_activated_abilities` op.

    "{1}: You may cast target creature card in a graveyard this turn. When you
    cast it this turn, this creature **gains all activated abilities of that
    card until end of turn**."                          -- Havengul Lich

A layer-6 ability-adding effect (613.1f) lasting until end of turn (514.2).
Four rules make the card:

* **113.6, 602.1: the abilities are the Lich's.** Its controller activates
  them, a ``{T}`` in their cost taps the Lich, and "this creature" in their
  text is the Lich -- not the creature that printed them.
* **"All activated abilities" (602.1, 605.1a).** Mana abilities are activated
  abilities and come along; static and triggered abilities do not.
* **The card as it was cast.** The delayed trigger resolves while the creature
  spell is still on the stack, so the abilities are read off the spell then --
  its characteristics on the stack, which are its printed ones -- and kept.
  What becomes of the card afterwards (it resolves, dies, is exiled) takes
  nothing away; the card's rulings say the same.
* **400.7.** The gain is on the Lich object: cleanup ends it, and so does the
  Lich leaving the battlefield -- the object that comes back is a new one.

Without the op the near misses were all wrong: `grant_ability` hands over one
fixed entry of the granting card's own ``grantable_abilities``; `become_copy`
takes the name and every characteristic; the `grant_exiled_abilities` static
lends only off cards linked to its source in exile, for as long as they stay.

`t_ga_lich` in `tests/data/gain_activated_abilities.cards.json` is Havengul
Lich's ability on a vanilla body, and Havengul Lich itself is the shipped
witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.characteristics import abilities_of
from commanderblitz.engine.costs import mana_sources
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import clear_until_eot, lose_all_abilities_timed
from commanderblitz.engine.stack import ability_of
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, activations, only_oid, settle

LICH = "t_ga_lich"
TINKERER = "t_gx_tinkerer"  # {1}{G}: "{1}, {T}: Put a +1/+1 counter on this creature."
ELVES = "llanowar_elves"  # {G}: "{T}: Add {G}."
BREWMASTER = "t_gx_brewmaster"  # a creature card with only a static ability
TINKER_TEXT = "{1}, {T}: Put a +1/+1 counter on this creature."
ANCHOR = "lightning_bolt"  # keeps player 0 holding priority in the main phase
OWN = 1  # the Lich's one printed ability

LANDS = ["forest", "forest", "forest", "forest", "swamp", "mountain"]


def card(game, card_id: str) -> int:
    """The one object of ``card_id``, in whatever zone it is."""
    [oid] = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def position(builder, graveyard=(TINKERER,), *, theirs: bool = True):
    """Player 0 with the Lich and lands; ``graveyard`` in player 1's graveyard
    (or player 0's). Returns ``(game, lich)``."""
    b = builder(players=2).battlefield(0, [LICH, *LANDS]).hand(0, [ANCHOR])
    b = b.graveyard(1 if theirs else 0, list(graveyard))
    game = b.build()
    return game, only_oid(game, LICH, 0)


def permit(game, lich: int, card_id: str) -> None:
    """Activate the Lich targeting ``card_id`` in a graveyard, and resolve it."""
    target = card(game, card_id)
    [action] = [a for a in activations(game, lich, 0) if a.targets[0].id == target]
    game.apply(action)
    settle(game)


def cast(game, card_id: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))


def lent(game, lich: int) -> list[str]:
    return [a.text for a in abilities_of(game.state, lich)[OWN:]]


def borrowed(builder, card_id: str = TINKERER, **kw):
    """The Lich, having cast ``card_id`` under its own permission; the spell
    still on the stack."""
    game, lich = position(builder, (card_id,), **kw)
    permit(game, lich, card_id)
    cast(game, card_id)
    return game, lich


class TestTheLichGainsTheAbilities:
    def test_casting_the_card_lends_its_activated_ability(self, builder):
        game, lich = borrowed(builder)

        assert game.state.objects[card(game, TINKERER)].zone is Zone.STACK
        assert lent(game, lich) == [TINKER_TEXT]
        assert abilities_of(game.state, lich)[OWN].index == OWN

    def test_its_controller_may_activate_it(self, builder):
        game, lich = borrowed(builder)
        settle(game)

        assert activations(game, lich, OWN)

    def test_it_taps_the_lich_and_this_creature_is_the_lich(self, builder):
        """113.6 / 602.1: the ability is the Lich's, so its ``{T}`` taps the
        Lich and its "this creature" is the Lich."""
        game, lich = borrowed(builder)
        settle(game)
        tinkerer = card(game, TINKERER)
        game.apply(activations(game, lich, OWN)[0])

        item = game.state.stack[-1]
        assert item.source_oid == lich
        assert item.granted_ability is not None
        assert ability_of(game.state, item).text == TINKER_TEXT
        assert game.state.objects[lich].tapped
        settle(game)

        assert game.state.objects[lich].counter(PLUS_ONE) == 1
        assert game.state.objects[tinkerer].counter(PLUS_ONE) == 0

    def test_the_creature_keeps_its_own_ability(self, builder):
        """Lent, not taken: the creature that resolves has exactly its own."""
        game, _ = borrowed(builder)
        settle(game)
        tinkerer = card(game, TINKERER)

        assert game.state.objects[tinkerer].zone is Zone.BATTLEFIELD
        assert [a.text for a in abilities_of(game.state, tinkerer)] == [TINKER_TEXT]

    def test_a_card_in_its_controllers_own_graveyard_works_too(self, builder):
        game, lich = borrowed(builder, theirs=False)

        assert lent(game, lich) == [TINKER_TEXT]


class TestWhatIsLent:
    def test_a_mana_ability_is_lent(self, builder):
        """605.1a: a mana ability is an activated ability."""
        game, lich = borrowed(builder, ELVES)
        settle(game)

        assert lent(game, lich) == ["{T}: Add {G}."]
        assert abilities_of(game.state, lich)[OWN].is_mana_ability
        assert any(s.oid == lich for s in mana_sources(game.state, 0))

    def test_a_static_ability_is_not(self, builder):
        game, lich = borrowed(builder, BREWMASTER)

        assert lent(game, lich) == []


class TestTheSnapshot:
    def test_it_outlives_the_creature_dying(self, builder):
        """Read off the spell as it was cast; the creature leaving takes
        nothing from the Lich."""
        game, lich = borrowed(builder)
        settle(game)
        move_object(game.state, card(game, TINKERER), Zone.GRAVEYARD, to_player=1)

        assert lent(game, lich) == [TINKER_TEXT]
        assert activations(game, lich, OWN)

    def test_it_outlives_the_card_being_exiled_off_the_stack(self, builder):
        """A spell that never resolves -- countered and exiled -- lent all the
        same: the trigger resolved before it could."""
        game, lich = borrowed(builder)
        move_object(game.state, card(game, TINKERER), Zone.EXILE, to_player=1)
        game.state.stack.clear()

        assert lent(game, lich) == [TINKER_TEXT]


class TestOnlyWhenYouCastThatCard:
    def test_the_permission_alone_lends_nothing(self, builder):
        game, lich = position(builder)
        permit(game, lich, TINKERER)

        assert lent(game, lich) == []

    def test_another_creature_cast_lends_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [LICH, *LANDS])
            .hand(0, [ANCHOR, ELVES])
            .graveyard(1, [TINKERER])
            .build()
        )
        lich = only_oid(game, LICH, 0)
        permit(game, lich, TINKERER)
        cast(game, ELVES)
        settle(game)

        assert lent(game, lich) == []

    def test_it_fires_once(self, builder):
        """One subscription, one gain: the delayed trigger is spent."""
        game, lich = borrowed(builder)
        settle(game)

        assert lent(game, lich) == [TINKER_TEXT]
        assert not any(d.source_oid == lich for d in game.state.delayed_triggers)


class TestItWearsOff:
    def test_cleanup_ends_it(self, builder):
        game, lich = borrowed(builder)
        settle(game)
        clear_until_eot(game.state)

        assert lent(game, lich) == []
        assert not activations(game, lich, OWN)

    def test_a_lich_that_returns_is_a_new_object(self, builder):
        """400.7: the gain was the old object's."""
        game, lich = borrowed(builder)
        settle(game)
        move_object(game.state, lich, Zone.GRAVEYARD, to_player=0)
        move_object(game.state, lich, Zone.BATTLEFIELD, to_player=0)

        assert lent(game, lich) == []

    def test_a_later_loss_of_all_abilities_hides_it(self, builder):
        """613.7: a timed "loses all abilities" that began later wins."""
        game, lich = borrowed(builder)
        settle(game)
        lose_all_abilities_timed(game.state, lich, cutoff=game.state.alloc_timestamp())

        assert abilities_of(game.state, lich) == ()


class TestTheLoader:
    SHAPE = {
        "op": "gain_activated_abilities",
        "from": {"binding": "subject"},
        "objects": {"self_only": True},
    }

    def validate(self, **change) -> None:
        effect = {**self.SHAPE, **change}
        _validate_effect({k: v for k, v in effect.items() if v is not None}, "probe", {})

    def test_the_printed_shape_loads(self):
        self.validate()

    def test_from_is_required(self):
        with pytest.raises(DslError, match="needs 'from'"):
            self.validate(**{"from": None})

    def test_objects_is_required(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            self.validate(objects=None)

    def test_another_duration_is_refused(self):
        with pytest.raises(DslError, match="until end of turn"):
            self.validate(duration="permanent")

    def test_a_grantable_index_is_refused(self):
        with pytest.raises(DslError, match="takes no"):
            self.validate(ability=0)
