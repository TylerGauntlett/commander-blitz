"""The fourteen tokens the Bard, King of Dale deck prints, each proved.

A token definition never goes through the card-authoring gates -- `verify.py`
casts a card and reads the board, and a token is not cast -- so it has exactly
the coverage written here. `test_artifact_tokens.py` makes that argument for the
four artifact tokens whose whole content is an activated ability; these are the
creature tokens, and the failure they are exposed to is a different one.

**A wrong token is silent.** `create_token` names an id, `validate_token_references`
checks only that the id exists and is a token, and nothing anywhere compares the
token that arrives against the words printed on the card that made it. So a
Luminarch Ascension pointed at `angel_4_4_w_flying_vigilance` -- the Angel that
was already in the pool -- loads, plays, and hands out a strictly better
creature than the printed one, forever, with nothing to notice. Two of these ids
differ from a shipped neighbour by exactly one printed word, and both are here
for that reason:

| new | shipped neighbour | the word |
|---|---|---|
| `angel_4_4_w_flying` | `angel_4_4_w_flying_vigilance` | vigilance |
| `illusion_1_1_u` | `illusion_1_1_u_flying` | flying |
| `knight_2_2_wu_vigilance` | `knight_2_2_w_vigilance` | blue |

The rest of the file is the two tokens that carry a printed ability of their own,
because a token's ability is the half a data change can get wrong in a way that
looks right: Emrakul's Spawn sacrificing itself for `{C}`, and Urza's Construct,
whose size is not a number at all.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars
from automtg.engine.enums import COLORLESS, ActionKind, DecisionKind, Step
from automtg.engine.mana import SYMBOL_INDEX
from automtg.engine.primitives import create_token
from tests.conftest import oids_of, pass_until

#: A castable instant in the OPPONENT's hand, so priority has a reason to stop
#: before cleanup. See `TestTheProwessMonk`.
ANCHOR = "t_plain_instant"

#: Every id added for this deck, with the printed words it must match. The list
#: is the point: a token dropped from `tokens.cards.json` fails here rather than
#: in a game, and `create_token` naming a missing id is a load error the whole
#: pool takes.
PRINTED: tuple[tuple[str, int, int, frozenset[str], str, frozenset[str]], ...] = (
    ("drake_2_2_u_flying", 2, 2, frozenset("U"), "Drake", frozenset({"flying"})),
    ("knight_2_2_wu_vigilance", 2, 2, frozenset("WU"), "Knight", frozenset({"vigilance"})),
    ("detective_2_2_wu", 2, 2, frozenset("WU"), "Detective", frozenset()),
    ("eldrazi_spawn_0_1_c", 0, 1, frozenset(), "Spawn", frozenset()),
    ("bird_1_1_u_flying_vigilance", 1, 1, frozenset("U"), "Bird",
     frozenset({"flying", "vigilance"})),
    ("angel_4_4_w_flying", 4, 4, frozenset("W"), "Angel", frozenset({"flying"})),
    ("faerie_1_1_u_flying", 1, 1, frozenset("U"), "Faerie", frozenset({"flying"})),
    ("monk_1_1_w_prowess", 1, 1, frozenset("W"), "Monk", frozenset()),
    ("tentacle_1_1_u", 1, 1, frozenset("U"), "Tentacle", frozenset()),
    ("bird_2_2_u_flying", 2, 2, frozenset("U"), "Bird", frozenset({"flying"})),
    ("spirit_1_1_c", 1, 1, frozenset(), "Spirit", frozenset()),
    ("illusion_1_1_u", 1, 1, frozenset("U"), "Illusion", frozenset()),
    ("thopter_1_1_c_flying", 1, 1, frozenset(), "Thopter", frozenset({"flying"})),
)

#: The one token whose size is not a number. Its printed P/T is 0/0 and it is
#: never that on a board, because its own static counts it -- so it is checked
#: by `TestTheUrzaConstruct` below rather than against a constant here.
VARIABLE = "construct_0_0_c_artifact_buff"


def board(builder, token: str, *, extra=(), count: int = 1):
    """`count` copies of the token on your battlefield, with mana for anything."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + ["island"] * 2 + list(extra))
        .battlefield(1, ["t_bear"])
        .library(0, ["forest"] * 10)
        .build()
    )
    create_token(game.state, token, 0, count)
    pass_until(
        game,
        lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
    )
    game.state.bump_chars()
    return game, oids_of(game, token)


class TestEachTokenIsWhatItsCardPrints:
    """Size, colour, creature type and keywords, read off the characteristics layer.

    `chars` rather than the `CardDef`, because that is what every rule asks: a
    token whose printed fields are right but which the layer reports wrong is
    wrong where it counts.
    """

    @pytest.mark.parametrize(
        "token,power,toughness,colors,subtype,keywords",
        PRINTED,
        ids=[row[0] for row in PRINTED],
    )
    def test_it_matches(self, builder, token, power, toughness, colors, subtype, keywords):
        game, (oid,) = board(builder, token)
        c = chars(game.state, oid)

        assert (c.power, c.toughness) == (power, toughness)
        assert set(c.colors) == set(colors)
        assert subtype in {str(s) for s in c.subtypes}
        assert {str(k) for k in c.keywords} == set(keywords)

    def test_every_one_of_them_is_marked_a_token(self, registry):
        """`validate_token_references` refuses a `create_token` naming a real
        card, and it is the only thing that does -- a definition that forgot the
        flag would be a card players could draw."""
        for tid in [row[0] for row in PRINTED] + [VARIABLE]:
            assert registry.get(tid).is_token, tid


class TestTheOnesThatDifferByOneWord:
    """Each of these was already in the pool wearing one extra printed word.

    Reaching for the neighbour is the cheapest possible mistake here and the
    hardest to see, because the near-miss token is a *better* creature and the
    card still works. Luminarch Ascension is the witness: its printed Angel has
    flying and the shipped one had vigilance too.
    """

    def test_the_new_angel_does_not_have_vigilance(self, builder):
        game, (oid,) = board(builder, "angel_4_4_w_flying")
        keywords = {str(k) for k in chars(game.state, oid).keywords}
        assert keywords == {"flying"}

    def test_the_shipped_angel_still_does(self, builder):
        """The pair, asserted from the other side: if these ever converge, one of
        the two cards that name them is quietly wrong and nothing else says so."""
        game, (oid,) = board(builder, "angel_4_4_w_flying_vigilance")
        assert {str(k) for k in chars(game.state, oid).keywords} == {"flying", "vigilance"}

    def test_the_new_illusion_cannot_fly(self, builder):
        """The Theorist's +1 prints a plain 1/1; the shipped Illusion flies."""
        game, (oid,) = board(builder, "illusion_1_1_u")
        assert not {str(k) for k in chars(game.state, oid).keywords}

    def test_the_new_knight_is_two_colours(self, builder):
        """Chivalric Alliance's Knight is white **and blue**, and colour is not
        cosmetic: it is what a protection or a devotion count reads."""
        game, (oid,) = board(builder, "knight_2_2_wu_vigilance")
        assert set(chars(game.state, oid).colors) == {"W", "U"}


class TestTheEldraziSpawn:
    """"Sacrifice this token: Add {C}." -- Emrakul's Messenger.

    A mana ability with no tap in its cost, which is the shape that would be
    wrong if it were copied from the Treasure without thinking: a Treasure taps
    *and* sacrifices, and a Spawn that also tapped would be unusable the turn it
    arrives on any card that makes it attacking or tapped.
    """

    def test_it_makes_one_colorless_and_ceases_to_exist(self, builder):
        game, (oid,) = board(builder, "eldrazi_spawn_0_1_c")
        pool = game.state.players[0].mana_pool
        before = pool.amounts[SYMBOL_INDEX[COLORLESS]]

        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid
        )
        game.apply(action)

        pool = game.state.players[0].mana_pool
        assert pool.amounts[SYMBOL_INDEX[COLORLESS]] == before + 1
        # 111.7: a token that leaves the battlefield ceases to exist. It is not
        # in the graveyard, so a Spawn written as a nontoken would be visible
        # here as an object that survived.
        assert oid not in game.state.objects

    def test_its_cost_does_not_tap_it(self, builder):
        """The ability is offered on a token that is already tapped.

        Asserted rather than described: a `tap` quietly added to the cost would
        leave every other test in this class passing.
        """
        game, (oid,) = board(builder, "eldrazi_spawn_0_1_c")
        game.state.objects[oid].tapped = True
        game.state.bump_chars()

        assert any(
            a.kind is ActionKind.ACTIVATE and a.source == oid for a in game.legal_actions()
        )


class TestTheUrzaConstruct:
    """"This token gets +1/+1 for each artifact you control."

    A 0/0 whose size is a count, and the one token here that cannot be a row of
    numbers. Three things it has to get right, and each has a wrong version that
    loads:

    - it **counts itself**, so a lone Construct is a 1/1 and not a 0/0 that dies
      to state-based actions the moment it arrives
    - it is a **static**, so an artifact cast later grows it -- `add_counters`
      would freeze it at its arrival size and `pump` would wear off at cleanup
    - it counts *artifacts*, not Constructs, so a second one makes both bigger
    """

    def test_a_lone_construct_is_a_one_one(self, builder):
        game, (oid,) = board(builder, "construct_0_0_c_artifact_buff")
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (1, 1)

    def test_it_survives_state_based_actions(self, builder):
        """The 0/0 written without the self-count dies on arrival (704.5f), which
        is a token that visibly never exists rather than one that is merely
        small."""
        game, (oid,) = board(builder, "construct_0_0_c_artifact_buff")
        pass_until(game, lambda g: g.pending() is not None)
        assert oid in game.state.objects

    def test_two_constructs_are_each_two_two(self, builder):
        """Each counts the other as well as itself -- the clause says artifacts,
        and a Construct token is one."""
        game, oids = board(builder, "construct_0_0_c_artifact_buff", count=2)
        for oid in oids:
            c = chars(game.state, oid)
            assert (c.power, c.toughness) == (2, 2)

    def test_another_artifact_on_the_board_grows_it(self, builder):
        """The static reads the board continuously, so an artifact that was
        never involved in making the token still counts."""
        game, (oid,) = board(builder, "construct_0_0_c_artifact_buff", extra=["sol_ring"])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)


class TestTheProwessMonk:
    """"1/1 white Monk creature token with prowess" -- Monastery Mentor.

    Prowess is not one of the loader's keywords; it is a `spell_cast` trigger
    filtered to noncreature spells, the way the shipped pool has always written
    it. So the assertion cannot be "the token has prowess" -- there is nothing to
    read -- and has to be the behaviour instead, which is the better assertion
    anyway.
    """

    def test_it_starts_as_a_plain_one_one(self, builder):
        game, (oid,) = board(builder, "monk_1_1_w_prowess")
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (1, 1)
        assert not {str(k) for k in c.keywords}

    def test_a_noncreature_spell_pumps_it(self, builder):
        """The anchor in the opponent's hand is load bearing, not scenery.

        With no play available to anybody the engine's auto-pass runs from the
        ritual resolving straight through cleanup, which wipes every
        until-end-of-turn effect -- so the pump would be measured after the
        thing it did had worn off, and this test would pass whatever the token
        did. It is the same failure `drive` had inside the authoring harness.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 4)
            .battlefield(1, ["plains"])
            .hand(0, ["pyretic_ritual"])
            .hand(1, [ANCHOR])
            .build()
        )
        create_token(game.state, "monk_1_1_w_prowess", 0, 1)
        pass_until(
            game,
            lambda g: g.state.active_player == 0 and g.state.step is Step.PRECOMBAT_MAIN,
        )
        game.state.bump_chars()
        (oid,) = oids_of(game, "monk_1_1_w_prowess")
        assert chars(game.state, oid).power == 1

        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "pyretic_ritual"
        )
        game.apply(cast)
        pass_until(
            game,
            lambda g: not g.state.stack
            and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
        )

        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)
