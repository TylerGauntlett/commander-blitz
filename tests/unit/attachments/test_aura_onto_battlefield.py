"""An Aura put onto the battlefield without being cast chooses its host (303.4f).

    303.4f If an Aura is entering the battlefield under a player's control by
    any means other than by resolving as an Aura spell, and the effect putting
    it onto the battlefield doesn't specify the object or player the Aura will
    enchant, that player chooses what it will enchant as the Aura enters the
    battlefield. The player must choose a legal object or player according to
    the Aura's enchant ability and any other applicable effects.

    303.4g If an Aura is entering the battlefield and there is no legal object
    or player for it to enchant, the Aura remains in its current zone, unless
    that zone is the stack.

Without this, `stack._attach_aura` -- which reads a cast Aura's target -- was
the only road onto a host, so an Aura returned from a graveyard, found off the
top of a library or revealed entered enchanting nothing, every enters trigger
saw it, and the state-based action put it into a graveyard (704.5m). Armored
Skyhunter's "you may put an Aura … onto the battlefield" put Auras straight in
the bin, and an Aura with nothing to enchant left its library or graveyard when
it should have stayed.

`zones.offer_aura_host` asks the question on every arrival path that can stop
to ask, and the answer is attached in `_enter_battlefield`, before
ENTERS_BATTLEFIELD goes out. The enchant clause is the Aura's first target spec,
read for the player it enters under. It is **not targeting**: hexproof and
shroud do not narrow the choice; protection does, because a permanent with
protection can't be *enchanted* by an Aura with that quality (702.16c).
``host_named`` on the arrival op is an effect that names the host itself, with
a following `attach` ("…attached to that token", Forum Filibuster).

The witnesses are Songbirds' Blessing (reveal_until), Armored Skyhunter
(look_at_top), Ghoulish Impetus and Screams from Within (return_from_graveyard).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TempEffect
from tests.conftest import library_ids, oids_of, only_oid, settle

AURA = "t_eb_aura"  # white, "Enchant creature" and nothing else
LAND_AURA = "t_wild_growth"  # "Enchant land"
CURSE = "t_encumber"  # "Enchant opponent"
BEAR = "t_bear"
HEXPROOF = "t_hexproof"
SHROUD = "t_shrouded"
ISLAND = "island"

REANIMATE_AURA = [
    {
        "op": "return_from_graveyard",
        "destination": "battlefield",
        "objects": {"zone": "graveyard", "subtypes": ["Aura"], "count": 1},
    }
]
#: Armored Skyhunter's look, with the Equipment half taken off.
LOOK = [
    {
        "op": "look_at_top",
        "amount": {"const": 3},
        "objects": {"count": 1, "optional": True, "subtypes": ["Aura"]},
        "destination": "battlefield",
        "rest_to_bottom": True,
    }
]


def position(builder, *, mine=(), theirs=(), graveyard=(), hand=(), library=None):
    """Player 0's ``mine`` facing player 1's ``theirs``, in a main phase.

    ``library`` is player 0's exact library, top first.
    """
    b = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    if graveyard:
        b.graveyard(0, list(graveyard))
    if hand:
        b.hand(0, list(hand))
    if library is not None:
        b.library(0, list(library))
    return b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)


def run(game, effects, *, pick=None, source=None):
    """Resolve ``effects`` for player 0, then the state-based actions.

    Every question is answered with its first option, except one that offers
    ``pick`` (an oid, or a seat for a player question), which takes it. Returns
    the decisions asked, so a test can read what was offered.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = execute(ctx, effects)
    asked = []
    answer = None
    while True:
        try:
            decision = gen.send(answer)
        except StopIteration:
            break
        asked.append(decision)
        chosen = [
            i
            for i, option in enumerate(decision.options)
            if pick is not None and option.ref is not None and option.ref.id == pick
        ]
        answer = chosen[:1] or [0]
    sba.run(game.state)
    return asked


def card_oid(game, card_id: str) -> int:
    """The one ``card_id`` in any zone -- `only_oid` reads the battlefield alone."""
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def offered(decision) -> set[int]:
    return {option.ref.id for option in decision.options if option.ref is not None}


def host_questions(asked):
    return [d for d in asked if "enchant" in d.prompt]


class TestAHostIsChosen:
    def test_the_controller_picks_any_creature_the_clause_allows(self, builder):
        """Two Bears, one each side, and an Island. "Enchant creature" offers
        the two Bears and not the land; the opponent's is chosen and kept."""
        game = position(builder, mine=[BEAR, ISLAND], theirs=[BEAR], graveyard=[AURA])
        aura = card_oid(game, AURA)
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)

        asked = run(game, REANIMATE_AURA, pick=theirs)

        (question,) = host_questions(asked)
        assert question.kind is DecisionKind.CHOOSE_OBJECTS
        assert question.player == 0
        assert offered(question) == {mine, theirs}
        obj = game.state.objects[aura]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.attached_to == theirs
        assert obj.controller == 0

    def test_it_enters_attached(self, builder):
        """Attached before ENTERS_BATTLEFIELD: no enters trigger sees an Aura
        enchanting nothing, and the ATTACHED event comes first."""
        game = position(builder, mine=[BEAR], graveyard=[AURA])
        aura = card_oid(game, AURA)

        run(game, REANIMATE_AURA)

        kinds = [
            e.type
            for e in game.state.events
            if e.source == aura and e.type in (EventType.ATTACHED, EventType.ENTERS_BATTLEFIELD)
        ]
        assert kinds[:2] == [EventType.ATTACHED, EventType.ENTERS_BATTLEFIELD]

    def test_an_enchant_land_aura_is_offered_only_lands(self, builder):
        game = position(builder, mine=[BEAR, ISLAND], graveyard=[LAND_AURA])
        island = only_oid(game, ISLAND, 0)

        asked = run(game, REANIMATE_AURA)

        assert all(offered(q) == {island} for q in host_questions(asked))
        assert game.state.objects[card_oid(game, LAND_AURA)].attached_to == island

    def test_enchant_opponent_lands_on_an_opponent(self, builder):
        """A player clause chooses a seat, never the Aura's own controller."""
        game = position(builder, hand=[CURSE])
        curse = card_oid(game, CURSE)

        run(game, [{"op": "put_onto_battlefield", "objects": {"zone": "hand", "subtypes": ["Aura"]}}])

        obj = game.state.objects[curse]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.attached_to_player == 1


class TestItDoesNotTarget:
    @pytest.mark.parametrize("warded", [HEXPROOF, SHROUD])
    def test_hexproof_and_shroud_do_not_stop_it(self, builder, warded):
        """Nothing is targeted (115.1), so an opponent's hexproof or shrouded
        creature is a legal host."""
        game = position(builder, theirs=[warded], graveyard=[AURA])
        host = only_oid(game, warded, 1)

        run(game, REANIMATE_AURA, pick=host)

        assert game.state.objects[card_oid(game, AURA)].attached_to == host

    def test_protection_does(self, builder):
        """702.16c: protection from white can't be enchanted by a white Aura.
        The protected Bear is not offered; the other one is all there is."""
        game = position(builder, mine=[BEAR, BEAR], graveyard=[AURA])
        shielded, plain = oids_of(game, BEAR, 0)
        game.state.objects[shielded].until_eot.append(
            TempEffect(kind="protection", keyword="W", timestamp=game.state.alloc_timestamp())
        )
        game.state.bump_chars()

        asked = run(game, REANIMATE_AURA, pick=shielded)

        assert host_questions(asked) == [], "one legal host is no question"
        assert game.state.objects[card_oid(game, AURA)].attached_to == plain


class TestNoLegalHostNoArrival:
    def test_it_stays_in_the_graveyard(self, builder):
        """Only lands: "enchant creature" has nothing, so the Aura never moves --
        no ENTERS_BATTLEFIELD, no trip through the battlefield to the bin."""
        game = position(builder, mine=[ISLAND], graveyard=[AURA])
        aura = card_oid(game, AURA)
        before = len(game.state.events)

        asked = run(game, REANIMATE_AURA)

        assert host_questions(asked) == []
        assert game.state.objects[aura].zone is Zone.GRAVEYARD
        assert game.state.players[0].graveyard == [aura]
        assert not [
            e for e in game.state.events[before:] if e.type == EventType.ENTERS_BATTLEFIELD
        ]

    def test_it_stays_in_the_library_and_goes_with_the_rest(self, builder):
        """Armored Skyhunter's shape: the Aura is taken, cannot enter, and is
        one of "the rest", bottomed with the cards not taken."""
        game = position(builder, mine=[ISLAND], library=[AURA, ISLAND, ISLAND, BEAR])

        run(game, LOOK)

        assert game.state.objects[card_oid(game, AURA)].zone is Zone.LIBRARY
        assert library_ids(game)[0] == BEAR, "the three looked at went under"

    def test_an_enchant_opponent_aura_stays_with_no_opponent_to_take_it(self, builder):
        """The seat side of 303.4g: the only opponent has protection from
        everything, so the curse stays in hand."""
        game = position(builder, hand=[CURSE])
        curse = card_oid(game, CURSE)
        run(game, [{"op": "grant_protection", "player": "opponent", "from_everything": True}])

        run(game, [{"op": "put_onto_battlefield", "objects": {"zone": "hand", "subtypes": ["Aura"]}}])

        assert game.state.objects[curse].zone is Zone.HAND


class TestEveryArrivalPath:
    def test_look_at_top(self, builder):
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA, ISLAND, ISLAND])
        bear = only_oid(game, BEAR, 0)

        run(game, LOOK)

        assert game.state.objects[card_oid(game, AURA)].attached_to == bear

    def test_reveal_until(self, builder):
        """Songbirds' Blessing's walk: reveal until an Aura, onto the battlefield."""
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA, ISLAND])
        bear = only_oid(game, BEAR, 0)

        run(
            game,
            [
                {
                    "op": "reveal_until",
                    "objects": {"subtypes": ["Aura"]},
                    "destination": "battlefield",
                }
            ],
        )

        assert game.state.objects[card_oid(game, AURA)].attached_to == bear

    def test_search_library(self, builder):
        game = position(builder, mine=[BEAR], library=[ISLAND, AURA])
        bear = only_oid(game, BEAR, 0)

        run(
            game,
            [
                {
                    "op": "search_library",
                    "selector": {"subtypes": ["Aura"]},
                    "destination": "battlefield",
                }
            ],
        )

        assert game.state.objects[card_oid(game, AURA)].attached_to == bear


class TestTheHostNamedByTheEffect:
    FILIBUSTER = [
        {
            "op": "return_from_graveyard",
            "destination": "battlefield",
            "host_named": True,
            "objects": {"zone": "graveyard", "subtypes": ["Aura"], "count": 1},
        },
        {
            "op": "attach",
            "attachment": {"zone": "battlefield", "subtypes": ["Aura"]},
            "objects": {"zone": "battlefield", "types": ["Creature"], "controller": "opponent"},
        },
    ]

    def test_host_named_asks_nothing_and_the_attach_decides(self, builder):
        """"…to the battlefield attached to that token": 303.4f does not apply,
        so the only host question is the `attach` op's."""
        game = position(builder, mine=[BEAR], theirs=[BEAR], graveyard=[AURA])
        theirs = only_oid(game, BEAR, 1)

        asked = run(game, self.FILIBUSTER)

        assert host_questions(asked) == []
        assert game.state.objects[card_oid(game, AURA)].attached_to == theirs

    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "return_to_hand", "host_named": True, "objects": {"self_only": True}},
            {
                "op": "return_from_graveyard",
                "destination": "hand",
                "host_named": True,
                "objects": {"zone": "graveyard"},
            },
            {
                "op": "put_onto_battlefield",
                "host_named": "yes",
                "objects": {"zone": "hand"},
            },
        ],
    )
    def test_the_loader_refuses_it_where_it_says_nothing(self, effect):
        model = CardModel.model_validate(
            {
                "id": "t_bad_host_named",
                "name": "Bad Host Named",
                "types": ["Sorcery"],
                "mana_cost": "{1}",
                "spell_effects": [effect],
            }
        )
        with pytest.raises(DslError, match="host_named"):
            compile_card(model)


class TestTheCastPathIsUnchanged:
    def test_a_cast_aura_enchants_its_target_and_asks_nothing_more(self, builder):
        """The spell's target is the host (`stack._attach_aura`); 303.4f is for
        an Aura that was not cast, so no second question is asked."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR, "plains"])
            .hand(0, [AURA])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        _, second = oids_of(game, BEAR, 0)
        aura = card_oid(game, AURA)
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source == aura
            and any(getattr(ref, "id", None) == second for ref in a.targets)
        )
        game.apply(cast)
        prompts = []
        for _ in range(40):
            decision = game.pending()
            if decision is None or (not game.state.stack and decision.kind is DecisionKind.PRIORITY):
                break
            if decision.kind is not DecisionKind.PRIORITY:
                prompts.append(decision.prompt)
            settle(game)
        assert host_questions_by_prompt(prompts) == []
        assert game.state.objects[aura].attached_to == second


def host_questions_by_prompt(prompts):
    return [p for p in prompts if "enchant" in p]


class TestTheWitnesses:
    def _effects(self, game, card_id, index):
        return list(game.state.registry.get(card_id).abilities[index].effects)

    def test_armored_skyhunter_puts_an_aura_on_a_creature(self, builder):
        game = position(builder, mine=["armored_skyhunter", BEAR], library=[AURA, ISLAND])
        bear = only_oid(game, BEAR, 0)
        skyhunter = only_oid(game, "armored_skyhunter", 0)

        run(game, self._effects(game, "armored_skyhunter", 0), pick=bear, source=skyhunter)

        assert game.state.objects[card_oid(game, AURA)].attached_to == bear
        assert game.state.objects[card_oid(game, AURA)].zone is Zone.BATTLEFIELD

    @pytest.mark.parametrize("card_id", ["screams_from_within", "ghoulish_impetus"])
    def test_a_returning_aura_chooses_its_host_or_stays(self, builder, card_id):
        """"Return this card to the battlefield": the host is chosen as it
        returns, with no `attach` after it; with no creature left it never
        leaves the graveyard. Ghoulish Impetus's return is the delayed half."""
        effects = self._effects(game := position(builder, graveyard=[card_id]), card_id, -1)
        if effects[0]["op"] == "delay":
            effects = list(effects[0]["effects"])
        assert [e["op"] for e in effects] == ["return_from_graveyard"]
        aura = card_oid(game, card_id)

        run(game, effects, source=aura)
        assert game.state.objects[aura].zone is Zone.GRAVEYARD

        game = position(builder, theirs=[BEAR], graveyard=[card_id])
        aura, bear = card_oid(game, card_id), only_oid(game, BEAR, 1)
        asked = run(game, effects, source=aura)
        assert game.state.objects[aura].attached_to == bear
        assert len([d for d in asked if d.kind is DecisionKind.CHOOSE_OBJECTS]) <= 1
