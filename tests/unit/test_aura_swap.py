"""Aura swap — an exchange, not a bounce beside a put-onto-the-battlefield.

    "Aura swap {2} ({2}: Exchange this Aura with an Aura card in your hand.)"

Written as two effects it loads and looks right, and two things go wrong that no
board would show:

- **The new Aura would arrive enchanting nothing.** It is not cast, so it has no
  targeting clause to carry a creature, and `_attach_aura` -- which reads a
  spell's first target -- never runs. A state-based action then bins it, so the
  ability reads "exchange" and is a slow Naturalize on your own card.
- **The exchange would not be atomic.** Between the bounce and the arrival the
  enchanted creature is unenchanted, which matters on exactly the cards this is
  printed alongside.

So it is one op, and the attach happens *after* the move -- `reset_permanent_
state` clears `attached_to` on the way onto the battlefield, the same trap an
Aura attaching itself during `spell_effects` falls into.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.primitives import attach
from tests.conftest import only_oid

PLAINS = "plains"
SWAPPER = "t_swap_aura"    # +1/+0, aura swap {2}
HEAVY = "t_big_aura"       # +5/+0
BEAR = "t_bear"


def position(builder, hand: list[str]):
    """A Bear wearing the light Aura.

    `advance=False`, because an Aura placed by the builder starts attached to
    nothing and a state-based action would bin it before the test could attach
    it -- which is the engine behaving correctly and the position being built
    in the wrong order.
    """
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 3)
        .battlefield(0, [BEAR, SWAPPER])
        .hand(0, hand)
        .build(advance=False)
    )
    bear, aura = only_oid(game, BEAR), only_oid(game, SWAPPER)
    attach(game.state, aura, bear)
    return game, bear, aura


def do_swap(game, aura: int):
    ctx = EffectContext(state=game.state, controller=0, source_oid=aura)
    gen = OPS["aura_swap"](ctx, {"op": "aura_swap"})
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = [0]
        assert decision is not None


class TestTheExchange:
    def test_the_old_aura_goes_to_hand(self, builder):
        game, _, aura = position(builder, [HEAVY])
        do_swap(game, aura)
        assert game.state.objects[aura].zone is Zone.HAND

    def test_the_new_aura_arrives(self, builder):
        game, _, aura = position(builder, [HEAVY])
        do_swap(game, aura)
        assert only_oid(game, HEAVY) is not None

    def test_it_arrives_enchanting_the_same_creature(self, builder):
        """The half two composed effects lose -- and the Aura would be binned."""
        game, bear, aura = position(builder, [HEAVY])
        do_swap(game, aura)

        heavy = only_oid(game, HEAVY)
        assert game.state.objects[heavy].attached_to == bear
        assert game.state.objects[heavy].zone is Zone.BATTLEFIELD

    def test_the_new_static_applies(self, builder):
        game, bear, aura = position(builder, [HEAVY])
        assert chars(game.state, bear).power == 3, "2/2 plus the light Aura"

        do_swap(game, aura)

        assert chars(game.state, bear).power == 7, "2/2 plus the heavy one"


class TestWhenItDoesNothing:
    def test_an_empty_hand_leaves_it_alone(self, builder):
        """It must not bounce the Aura on the battlefield for free."""
        game, bear, aura = position(builder, [])
        do_swap(game, aura)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD
        assert game.state.objects[aura].attached_to == bear

    def test_a_hand_of_non_auras_leaves_it_alone(self, builder):
        game, _, aura = position(builder, [BEAR])
        do_swap(game, aura)

        assert game.state.objects[aura].zone is Zone.BATTLEFIELD
