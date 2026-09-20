"""The Blor the Impervious deck, card by card, doing what it prints.

Every card here already cleared the six authoring gates, and that is exactly why
this file exists. Gate 5 -- the behaviour gate -- casts a card **once**, in one
fixed sandbox, and reads the board. Three of its documented limits bite most of
this deck:

- **It never activates an ability.** The Mycosynth Gardens' copy ability,
  Excalibur's equip and The Irencrag's mana ability are the whole point of those
  cards, and the harness stops before any of them.
- **A trigger that never fires cannot be asserted.** Nothing in that position
  attacks, mutates, or plays a second permanent, so Tanuki Transplanter, Gemrazer
  and The Irencrag all have honest expectations of "nothing happened".
- **A static that changes a later spell's price is invisible.** The sandbox casts
  one card and stops, so Excalibur's and Strong Back's discounts are measured
  against a board that never pays them.

So the authoring expectations are floors, and these are the observations. Each
class is one card and asserts the printed sentence the gate could not reach --
including, in each case, the **near miss**: the reading that would be wrong if
the card were mis-written.
"""

from __future__ import annotations

from automtg.cards.registry import default_registry
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.costs import ability_mana, cost_reduction
from automtg.engine.enums import ActionKind, Step
from automtg.engine.mana import SYMBOL_INDEX
from automtg.engine.primitives import attach, damage_permanent
from tests.conftest import only_oid, pass_until

GREEN = SYMBOL_INDEX["G"]


def board(builder, mine=(), theirs=(), lands=6, hand=(), attachments=()):
    """A board, with ``attachments`` hooked up before the first advance.

    An Aura attached to nothing is put into its owner's graveyard by the
    state-based actions, and `build(advance=True)` runs them -- so an Aura this
    file wants on the battlefield has to find its host first. `attach` is the
    same primitive the Aura's own resolution calls.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    for aura, host in attachments:
        assert attach(game.state, only_oid(game, aura), only_oid(game, host))
    game.state.bump_chars()
    game._advance()
    return game


def cast(game, card_id: str):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestInquisitorsFlail:
    """"If equipped creature would deal combat damage, it deals double that
    damage instead." Gate 5 never reaches combat, so the doubling is unobserved
    there -- the card enters and the board looks identical either way."""

    def position(self, builder):
        game = board(
            builder, mine=["inquisitor_s_flail", "grizzly_bears"], theirs=["grizzly_bears"]
        )
        assert attach(
            game.state,
            only_oid(game, "inquisitor_s_flail"),
            only_oid(game, "grizzly_bears", pid=0),
        )
        game.state.bump_chars()
        return game

    def test_the_equipped_creature_hits_for_double(self, builder):
        game = self.position(builder)
        dealt = damage_permanent(
            game.state,
            only_oid(game, "grizzly_bears", pid=1),
            2,
            only_oid(game, "grizzly_bears", pid=0),
            is_combat=True,
        )
        assert dealt == 4

    def test_but_not_outside_combat(self, builder):
        """The near miss. The card says "combat damage" and a Flail that
        doubled a burn spell would be a different card."""
        game = self.position(builder)
        dealt = damage_permanent(
            game.state,
            only_oid(game, "grizzly_bears", pid=1),
            2,
            only_oid(game, "grizzly_bears", pid=0),
            is_combat=False,
        )
        assert dealt == 2


class TestExcaliburSwordOfEden:
    """"This spell costs {X} less to cast, where X is the total mana value of
    historic permanents you control." A price, which the behaviour gate cannot
    see: it casts the card and reads the board."""

    def test_an_empty_board_pays_the_printed_twelve(self, builder):
        game = board(builder, lands=0)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) == 0

    def test_historic_permanents_pay_for_it(self, builder):
        """A Sol Ring is an artifact (2), Urza's Saga a Saga land (0), and the
        commander a legendary creature -- three different halves of "historic",
        which is the disjunction the card needed."""
        game = board(builder, mine=["sol_ring", "urza_s_saga", "blor_the_impervious"], lands=0)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) > 0

    def test_a_forest_pays_nothing(self, builder):
        """The near miss: a Forest is a permanent you control and is not
        historic, so a reduction counting permanents rather than historic ones
        would discount here."""
        game = board(builder, lands=5)
        card = default_registry().registry.get("excalibur_sword_of_eden")
        assert cost_reduction(game.state, 0, card) == 0


class TestStrongBack:
    """"Equip abilities you activate that target enchanted creature cost {3}
    less to activate." Two prices and an aim, none of which gate 5 reaches."""

    def position(self, builder):
        return board(
            builder,
            mine=["strong_back", "commander_s_plate", "grizzly_bears", "llanowar_elves"],
            attachments=[("strong_back", "grizzly_bears")],
        )

    def equip_price(self, game, at: str) -> int:
        oid = only_oid(game, "commander_s_plate")
        ability = next(
            a for a in abilities_of(game.state, oid) if getattr(a, "is_equip", False)
        )
        wanted = only_oid(game, at)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and any(r.id == wanted for r in a.targets)
        )
        return ability_mana(
            game.state, 0, ability.cost, 0, oid, ability=ability, targets=action.targets
        ).generic

    def test_equipping_the_enchanted_creature_is_cheaper(self, builder):
        game = self.position(builder)
        assert self.equip_price(game, "grizzly_bears") < self.equip_price(
            game, "llanowar_elves"
        )

    def test_the_enchanted_creature_grows_with_what_is_on_it(self, builder):
        """"Enchanted creature gets +2/+2 for each Aura and Equipment attached
        to it." Strong Back counts itself, so a 2/2 bear is already a 4/4."""
        game = self.position(builder)
        assert chars(game.state, only_oid(game, "grizzly_bears")).power == 4


class TestNaturalize:
    """A bug this deck's work found in a card it does not contain.

    "Destroy target artifact **or enchantment**" shipped able to target only
    artifacts: the selector said `types: ["Artifact"]`, which is an AND over one
    type rather than the printed or. The card loaded, played, and quietly did
    half of what it says -- the failure mode no gate can see, because targeting
    fewer things is never an error.

    `any_types` is the spelling the disjunction needs, and Loran of the Third
    Path has used it for the same printed words all along.
    """

    def test_it_can_target_an_enchantment(self, builder):
        game = board(builder, theirs=["sylvan_library"], hand=["naturalize"])
        wanted = only_oid(game, "sylvan_library")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert aims, "an enchantment is half of what the card says it destroys"

    def test_it_still_targets_an_artifact(self, builder):
        """The control: widening the filter must not have swapped one half of
        the sentence for the other."""
        game = board(builder, theirs=["sol_ring"], hand=["naturalize"])
        wanted = only_oid(game, "sol_ring")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert aims

    def test_it_does_not_target_a_creature(self, builder):
        """The near miss. `any_types` is an or over the two named types and not
        a licence to hit anything."""
        game = board(builder, theirs=["grizzly_bears"], hand=["naturalize"])
        wanted = only_oid(game, "grizzly_bears")
        aims = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "naturalize"
            and any(r.id == wanted for r in a.targets)
        ]
        assert not aims
