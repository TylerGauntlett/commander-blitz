"""An arrival may narrow the host an uncast Aura chooses (303.4f, 303.4g).

    303.4f ... that player chooses what it will enchant as the Aura enters the
    battlefield. The player must choose a legal object or player according to
    the Aura's enchant ability **and any other applicable effects**.

    303.4g If an Aura is entering the battlefield and there is no legal object
    or player for it to enchant, the Aura remains in its current zone.

Retether: "Return each Aura card from your graveyard to the battlefield. Only
creatures can be enchanted this way. (Aura cards that can't enchant a creature
on the battlefield remain in your graveyard.)" The second sentence is one of
303.4f's "other applicable effects". Without ``aura_host`` the choice
`zones.offer_aura_host` offers is the enchant clause alone, so an "Enchant
permanent" Aura could come back on a land, an "Enchant land" one would come
back at all, and a Curse would come back on an opponent -- each a card the
printed parenthetical says stays in the graveyard.

What would be wrong without each claim below:

- **Only hosts matching both are offered**: the filter is intersected with the
  enchant clause, never substituted for it, so it neither widens "Enchant
  creature you control" nor lets "Enchant permanent" reach a land.
- **An Aura with no such host stays in its zone**, and never enters: "Enchant
  land", "Enchant opponent" (a seat is not a permanent), "Enchant creature card
  in a graveyard" (Animate Dead), and any Aura when no creature is there.
- **Without the key nothing changes**, which is the boundary: the same Aura on
  the same board is offered the land again.
- **The loader refuses** the key where no Aura chooses a host -- another op, a
  return to the hand, beside ``host_named`` or ``face_down`` -- and any filter
  key outside `AURA_HOST_KEYS`.

The witness is Retether (``t_ah_retether``, written as the shipped card is).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.vocabulary import AURA_HOST_KEYS
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import only_oid, settle

RETETHER = "t_ah_retether"
ANY_AURA = "t_ah_any_aura"  # "Enchant permanent"
AURA = "t_eb_aura"  # "Enchant creature"
LAND_AURA = "t_wild_growth"  # "Enchant land"
CURSE = "t_encumber"  # "Enchant opponent"
ANIMATE_DEAD = "t_animate_dead"  # "Enchant creature card in a graveyard"
BEAR = "t_bear"
ISLAND = "island"
SOL_RING = "sol_ring"


def returning(aura_host=None, *, op="return_from_graveyard", zone="graveyard"):
    """Every Aura card in player 0's ``zone`` onto the battlefield, with
    ``aura_host`` on the arrival when given."""
    spec = {
        "op": op,
        "objects": {"zone": zone, "subtypes": ["Aura"], "count": "all"},
    }
    if op == "return_from_graveyard":
        spec["destination"] = "battlefield"
    if aura_host is not None:
        spec["aura_host"] = aura_host
    return [spec]


CREATURES_ONLY = {"types": ["Creature"]}


def position(builder, *, mine=(), theirs=(), graveyard=(), hand=()):
    b = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    if graveyard:
        b.graveyard(0, list(graveyard))
    if hand:
        b.hand(0, list(hand))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)


def run(game, effects):
    """Resolve ``effects`` for player 0, answering every question with its
    first option, then the state-based actions. Returns the decisions asked."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, effects)
    asked, answer = [], None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        asked.append(decision)
        answer = [0]
    sba.run(game.state)
    return asked


def card(game, card_id: str):
    (obj,) = [o for o in game.state.objects.values() if o.def_id == card_id]
    return obj


def offered(asked) -> list[set[int]]:
    return [
        {o.ref.id for o in d.options if o.ref is not None} for d in asked if "enchant" in d.prompt
    ]


def entered(game, card_id: str) -> bool:
    oid = card(game, card_id).oid
    return any(
        e.type == EventType.ENTERS_BATTLEFIELD and e.source == oid for e in game.state.events
    )


class TestOnlyHostsMatchingBothAreOffered:
    def test_enchant_permanent_is_offered_only_the_creatures(self, builder):
        """A Bear each side, an Island and a Sol Ring: "Enchant permanent"
        allows all four, "only creatures" leaves the two Bears."""
        game = position(builder, mine=[BEAR, ISLAND, SOL_RING], theirs=[BEAR], graveyard=[ANY_AURA])
        bears = {only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)}

        asked = run(game, returning(CREATURES_ONLY))

        assert offered(asked) == [bears]
        assert card(game, ANY_AURA).attached_to in bears

    def test_the_filter_never_widens_the_clause(self, builder):
        """"Enchant creature" under a creature-or-land filter is still offered
        creatures only; the filter is intersected, not substituted."""
        game = position(builder, mine=[BEAR, ISLAND], graveyard=[AURA])

        asked = run(game, returning({"any_types": ["Creature", "Land"]}))

        assert offered(asked) == []  # one legal host is enchanted unasked
        assert card(game, AURA).attached_to == only_oid(game, BEAR, 0)

    def test_controller_is_read_for_the_player_it_enters_under(self, builder):
        game = position(builder, mine=[BEAR], theirs=[BEAR], graveyard=[AURA])

        asked = run(game, returning({"types": ["Creature"], "controller": "opponent"}))

        assert offered(asked) == []
        assert card(game, AURA).attached_to == only_oid(game, BEAR, 1)

    def test_put_onto_battlefield_reads_it_too(self, builder):
        game = position(builder, mine=[BEAR, ISLAND], hand=[ANY_AURA])

        asked = run(game, returning(CREATURES_ONLY, op="put_onto_battlefield", zone="hand"))

        assert offered(asked) == []
        assert card(game, ANY_AURA).attached_to == only_oid(game, BEAR, 0)


class TestAnAuraWithNoSuchHostStaysWhereItWas:
    @pytest.mark.parametrize("aura", [LAND_AURA, CURSE, ANIMATE_DEAD], ids=["land", "player", "graveyard_card"])
    def test_a_clause_no_creature_satisfies(self, builder, aura):
        """A creature card waits in the graveyard too, so Animate Dead's own
        clause has a card to enchant -- and still none that is a creature on
        the battlefield."""
        game = position(builder, mine=[BEAR, ISLAND], theirs=[BEAR], graveyard=[aura, "t_bear"])

        asked = run(game, returning(CREATURES_ONLY))

        assert offered(asked) == []
        assert card(game, aura).zone is Zone.GRAVEYARD
        assert not entered(game, aura)

    def test_no_creature_on_the_battlefield(self, builder):
        game = position(builder, mine=[ISLAND, SOL_RING], graveyard=[ANY_AURA])

        run(game, returning(CREATURES_ONLY))

        assert card(game, ANY_AURA).zone is Zone.GRAVEYARD
        assert not entered(game, ANY_AURA)


class TestWithoutTheKey:
    def test_the_enchant_clause_alone_is_offered(self, builder):
        """The boundary: the same Aura on the same board, with no filter, is
        offered the Island and the Sol Ring again."""
        game = position(builder, mine=[BEAR, ISLAND, SOL_RING], graveyard=[ANY_AURA])

        asked = run(game, returning())

        assert offered(asked) == [
            {only_oid(game, BEAR, 0), only_oid(game, ISLAND, 0), only_oid(game, SOL_RING, 0)}
        ]

    def test_an_enchant_land_aura_returns(self, builder):
        game = position(builder, mine=[BEAR, ISLAND], graveyard=[LAND_AURA])

        run(game, returning())

        assert card(game, LAND_AURA).attached_to == only_oid(game, ISLAND, 0)


class TestRetether:
    def test_the_creature_auras_return_and_the_rest_stay(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, ISLAND] + ["plains"] * 4)
            .hand(0, [RETETHER])
            .graveyard(0, [ANY_AURA, LAND_AURA, CURSE])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        cast = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
        game.apply(cast)
        settle(game)

        assert card(game, RETETHER).zone is Zone.GRAVEYARD
        assert card(game, ANY_AURA).attached_to == bear
        assert card(game, LAND_AURA).zone is Zone.GRAVEYARD
        assert card(game, CURSE).zone is Zone.GRAVEYARD


class TestTheLoader:
    @pytest.mark.parametrize(
        ("effect", "match"),
        [
            (
                {"op": "return_to_hand", "aura_host": CREATURES_ONLY, "objects": {"self_only": True}},
                "filter on the host",
            ),
            (
                {
                    "op": "return_from_graveyard",
                    "destination": "hand",
                    "aura_host": CREATURES_ONLY,
                    "objects": {"zone": "graveyard"},
                },
                "needs destination 'battlefield'",
            ),
            (
                {"op": "put_onto_battlefield", "aura_host": True, "objects": {"zone": "hand"}},
                "filter on the host",
            ),
            (
                {"op": "put_onto_battlefield", "aura_host": {}, "objects": {"zone": "hand"}},
                "filter on the host",
            ),
            (
                {
                    "op": "return_from_graveyard",
                    "destination": "battlefield",
                    "aura_host": CREATURES_ONLY,
                    "host_named": {"zone": "battlefield", "types": ["Creature"]},
                    "objects": {"zone": "graveyard"},
                },
                "host_named",
            ),
            (
                {
                    "op": "return_from_graveyard",
                    "destination": "battlefield",
                    "aura_host": CREATURES_ONLY,
                    "face_down": True,
                    "objects": {"zone": "graveyard"},
                },
                "face_down",
            ),
            (
                {
                    "op": "put_onto_battlefield",
                    "aura_host": {"types": ["Creature"], "binding": "host"},
                    "objects": {"zone": "hand"},
                },
                "not a description of a host",
            ),
            (
                {
                    "op": "put_onto_battlefield",
                    "aura_host": {"types": ["Creature"], "zone": "graveyard"},
                    "objects": {"zone": "hand"},
                },
                "not a description of a host",
            ),
        ],
        ids=[
            "other_op",
            "to_hand",
            "boolean",
            "empty",
            "with_host_named",
            "face_down",
            "binding",
            "zone",
        ],
    )
    def test_refuses(self, effect, match):
        model = CardModel.model_validate(
            {
                "id": "t_bad_aura_host",
                "name": "Bad Aura Host",
                "types": ["Sorcery"],
                "mana_cost": "{1}",
                "spell_effects": [effect],
            }
        )
        with pytest.raises(DslError, match=match):
            compile_card(model)

    def test_every_allowed_key_is_a_selector_key(self):
        from commanderblitz.engine.effects.selectors import SELECTOR_KEYS

        assert AURA_HOST_KEYS <= SELECTOR_KEYS
