"""The tokens a card names, and why a near-miss is not a substitute.

Rule 111.4: a token's characteristics are exactly the ones the effect creating
it specifies. There is no "close enough" — a 2/2 white Knight with vigilance is
a different card from a 2/2 white Knight, and Summon: Knights of Round makes
twelve of them across its first four chapters. Handing it the vigilance token
would quietly grant twelve creatures an ability the Saga never prints.

`loader` already refuses a `create_token` that names an id the pool does not
have, which is the tripwire that catches a *missing* token. Nothing catches a
token that exists but drifts, and drift is the worse failure: the card keeps
loading, keeps passing its gates, and is simply a better card than the one on
the paper. So the tokens whose exact stats are load-bearing are pinned here.

The witnesses:

- `knight_2_2_w` — Summon: Knights of Round. Filed as an unimplementable card
  purely because the pool's only 2/2 white Knight carried vigilance.
- `moogle_1_2_w_lifelink` — Mog, Moogle Warrior, whose last clause puts a
  counter on "each Moogle you control", so the *subtype* is as load-bearing as
  the power and toughness.
"""

from __future__ import annotations

import json

import pytest

from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import (
    find_action,
    keywords,
    only_oid,
    pass_until,
    pt,
    settle_completely,
    two_seat_board,
)


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    return CardRegistry.from_dir()


class TestTheKnightIsVanilla:
    """Summon: Knights of Round prints no keyword on its Knights."""

    def test_it_exists(self, pool):
        assert pool.get("knight_2_2_w") is not None

    def test_it_is_a_two_two_white_knight(self, pool):
        knight = pool.get("knight_2_2_w")
        assert (knight.power, knight.toughness) == (2, 2)
        assert sorted(knight.colors) == ["W"]
        assert "Knight" in knight.subtypes
        assert knight.is_creature and knight.is_token

    def test_it_has_no_keywords(self, pool):
        """The whole reason it exists rather than reusing the vigilance one."""
        assert not pool.get("knight_2_2_w").keywords

    def test_the_vigilance_knight_is_still_a_separate_token(self, pool):
        """Nobody may "consolidate" these two: the difference is the point."""
        other = pool.get("knight_2_2_w_vigilance")
        assert other is not None
        assert "vigilance" in other.keywords


class TestTheMoogleCarriesItsSubtype:
    """Mog counts Moogles, so a Vampire of the right size is not a stand-in."""

    def test_it_exists(self, pool):
        assert pool.get("moogle_1_2_w_lifelink") is not None

    def test_it_is_a_one_two_white_moogle_with_lifelink(self, pool):
        moogle = pool.get("moogle_1_2_w_lifelink")
        assert (moogle.power, moogle.toughness) == (1, 2)
        assert sorted(moogle.colors) == ["W"]
        assert "Moogle" in moogle.subtypes
        assert "lifelink" in moogle.keywords
        assert moogle.is_creature and moogle.is_token

    def test_it_is_the_only_moogle_token(self, pool):
        """"Put a +1/+1 counter on each Moogle you control" reads the subtype.

        Only the *token* pool is pinned. Mog itself is a Moogle — correctly, and
        that is the point: its last clause counts Moogles on the battlefield,
        so it puts a counter on itself as well as on what it just made. A second
        Moogle *token* would silently change which permanents that clause
        reaches, so if one ever arrives this test should be updated
        deliberately rather than deleted.
        """
        tokens = [c.id for c in pool if "Moogle" in c.subtypes and c.is_token]
        assert tokens == ["moogle_1_2_w_lifelink"]

    def test_the_card_that_makes_them_is_one_too(self, pool):
        """Guards the half above from being read as "nothing else is a Moogle"."""
        mog = pool.get("mog_moogle_warrior")
        assert mog is not None and "Moogle" in mog.subtypes


class TestEveryNamedTokenResolves:
    """The tripwire that turned both of these into gap records rather than bugs.

    `loader._check_token_ids` enforces this at load time; asserting it here is
    what makes the enforcement visible as a *claim* rather than an incident, and
    it fails loudly if that check is ever loosened.
    """

    def test_the_pool_loads(self, pool):
        assert len(pool) > 0

    def test_every_token_id_a_card_names_is_in_the_pool(self, pool):
        """Read from the card JSON, not the compiled `CardDef`.

        The compiled form drops the op dicts, so walking it would collect
        nothing and the assertion would pass without ever looking at a card --
        a green test guarding an empty set. The shipped JSON is the artifact
        that actually has to be right.
        """
        named: set[str] = set()

        def walk(node) -> None:
            if isinstance(node, dict):
                if node.get("op") == "create_token" and isinstance(node.get("token"), str):
                    named.add(node["token"])
                # `replace_token_creation` names ids the same way.
                instead = node.get("create_instead")
                if isinstance(instead, str):
                    named.add(instead)
                elif isinstance(instead, list):
                    named.update(t for t in instead if isinstance(t, str))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for path in authored_card_paths():
            payload = json.loads(path.read_text(encoding="utf-8"))
            walk(payload["cards"] if isinstance(payload, dict) else payload)

        assert named, "walked every card file and found no create_token at all"
        missing = sorted(t for t in named if pool.get(t) is None)
        assert not missing, f"cards name tokens the pool does not define: {missing}"


class TestMyrelsSoldiersAreColorlessArtifacts:
    """Myrel, Shield of Argive: *"create X 1/1 colorless Soldier **artifact**
    creature tokens, where X is the number of Soldiers you control."*

    The near miss is the worst kind, because it is wrong twice over and the
    second way is self-inflicted: `soldier_1_1_w` is a **white non-artifact**
    Soldier, so handing it to Myrel would make tokens of the wrong colour and
    the wrong card type -- and Myrel's own X counts Soldiers, so the tokens feed
    the count that makes the next batch. A commander whose whole deck is built
    on colorless artifact Soldiers would be quietly making something else.
    """

    def test_it_exists(self, pool):
        assert pool.get("soldier_1_1_c") is not None

    def test_it_is_a_colorless_artifact_creature(self, pool):
        soldier = pool.get("soldier_1_1_c")
        assert (soldier.power, soldier.toughness) == (1, 1)
        assert not soldier.colors, "colorless -- the printed word"
        assert "Artifact" in soldier.types and "Creature" in soldier.types
        assert "Soldier" in soldier.subtypes
        assert soldier.is_token

    def test_the_white_soldier_is_still_a_separate_token(self, pool):
        """The two differ in colour and in card type; neither may absorb the
        other, and the white one is what several other cards print."""
        white = pool.get("soldier_1_1_w")
        assert white is not None
        assert sorted(white.colors) == ["W"]
        assert "Artifact" not in white.types


class TestAnafenzasSpiritIsATwoTwoWhite:
    """Anafenza, Unyielding Lineage endures 2: *"put two +1/+1 counters on it or
    create a **2/2 white** Spirit creature token."*

    The pool's only Spirit was `spirit_1_1_c` -- a 1/1 **colorless** one, half
    the body and the wrong colour. Endure is modal, so substituting it would not
    merely make a smaller token: it would make the counters half of the mode
    strictly better than the token half on every board.
    """

    def test_it_exists(self, pool):
        assert pool.get("spirit_2_2_w") is not None

    def test_it_is_a_two_two_white_spirit(self, pool):
        spirit = pool.get("spirit_2_2_w")
        assert (spirit.power, spirit.toughness) == (2, 2)
        assert sorted(spirit.colors) == ["W"]
        assert "Spirit" in spirit.subtypes
        assert spirit.is_creature and spirit.is_token

    def test_the_colorless_spirit_is_still_a_separate_token(self, pool):
        other = pool.get("spirit_1_1_c")
        assert other is not None
        assert (other.power, other.toughness) == (1, 1)
        assert not other.colors


class TestTheAberrationsAngelsAreColorlessEldrazi:
    """Angelic Aberration: *"Create that many **4/4 colorless Eldrazi Angel**
    creature tokens with flying and vigilance."*

    `angel_4_4_w_flying_vigilance` is the right body with the right keywords and
    is still the wrong token: it is **white**, and it is an Angel rather than an
    Eldrazi Angel. The colour is load-bearing twice -- the card itself is Devoid,
    so a white token would contradict the card printing it, and colorless- and
    Eldrazi-typal cards read both characteristics.
    """

    def test_it_exists(self, pool):
        assert pool.get("eldrazi_angel_4_4_c_flying_vigilance") is not None

    def test_it_is_a_colorless_eldrazi_angel_with_both_keywords(self, pool):
        token = pool.get("eldrazi_angel_4_4_c_flying_vigilance")
        assert (token.power, token.toughness) == (4, 4)
        assert not token.colors, "Devoid's token is colorless"
        assert {"Eldrazi", "Angel"} <= set(token.subtypes)
        assert {"flying", "vigilance"} <= set(token.keywords)

    def test_the_white_angel_is_still_a_separate_token(self, pool):
        other = pool.get("angel_4_4_w_flying_vigilance")
        assert other is not None
        assert sorted(other.colors) == ["W"]
        assert "Eldrazi" not in other.subtypes


class TestLinvalasAngelIsAThreeThree:
    """Linvala, the Preserver: *"create a **3/3** white Angel creature token
    with flying."*

    `angel_4_4_w_flying` is the right colour, type and keyword on the wrong
    body: a 4/4 survives the blocks and trades the 3/3 printed one cannot.
    """

    def test_it_exists(self, pool):
        assert pool.get("angel_3_3_w_flying") is not None

    def test_it_is_a_three_three_white_angel_with_flying(self, pool):
        token = pool.get("angel_3_3_w_flying")
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["W"]
        assert list(token.subtypes) == ["Angel"]
        assert list(token.keywords) == ["flying"]

    def test_the_four_four_angel_is_still_a_separate_token(self, pool):
        other = pool.get("angel_4_4_w_flying")
        assert other is not None
        assert (other.power, other.toughness) == (4, 4)


class TestTheEaglesAreBirdSoldiers:
    """The Eagles Are Coming!: *"create a **4/4 white Bird Soldier** creature
    token with flying for each creature returned to your hand this way."*

    Two near misses, each wrong in its own direction. `bird_1_1_w_flying` is a
    quarter of the body. `angel_4_4_w_flying` is the right body and the wrong
    creature types -- and in *this* deck that is the expensive error, because
    Myrel, Daru Warchief, Ballyrush Banneret and Valiant Veteran all count or
    pump Soldiers.
    """

    def test_it_exists(self, pool):
        assert pool.get("bird_soldier_4_4_w_flying") is not None

    def test_it_is_a_four_four_white_bird_soldier_with_flying(self, pool):
        token = pool.get("bird_soldier_4_4_w_flying")
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["W"]
        assert {"Bird", "Soldier"} <= set(token.subtypes)
        assert "flying" in token.keywords

    def test_the_small_bird_is_still_a_separate_token(self, pool):
        other = pool.get("bird_1_1_w_flying")
        assert other is not None
        assert (other.power, other.toughness) == (1, 1)
        assert "Soldier" not in other.subtypes


class TestOcelotPridesCatIsAOneOneWhite:
    """Ocelot Pride: *"create a **1/1 white Cat** creature token."*

    `cat_beast_2_2_w` is the pool's only Cat and is a 2/2 Cat **Beast**. The
    substitution is worse on this card than on most, because its next sentence
    copies *every token you control that entered this turn* -- so a wrong token
    is not made once, it is made and then doubled.
    """

    def test_it_exists(self, pool):
        assert pool.get("cat_1_1_w") is not None

    def test_it_is_a_one_one_white_cat(self, pool):
        cat = pool.get("cat_1_1_w")
        assert (cat.power, cat.toughness) == (1, 1)
        assert sorted(cat.colors) == ["W"]
        assert "Cat" in cat.subtypes
        assert cat.is_creature and cat.is_token

    def test_it_is_not_a_beast(self, pool):
        """The whole reason it exists rather than reusing the Cat Beast."""
        assert "Beast" not in pool.get("cat_1_1_w").subtypes

    def test_the_cat_beast_is_still_a_separate_token(self, pool):
        other = pool.get("cat_beast_2_2_w")
        assert other is not None
        assert (other.power, other.toughness) == (2, 2)
        assert "Beast" in other.subtypes


class TestAngelOfInventionsServosAreColorlessArtifacts:
    """Angel of Invention, Fabricate 2: *"create two **1/1 colorless Servo
    artifact** creature tokens."*

    The pool had three 1/1 colorless artifact creatures -- a Gnome, a Soldier
    and a flying Thopter -- and no Servo. The subtype is load-bearing: Servo and
    artifact-typal cards read it, and the Thopter's flying would make the token
    half of Fabricate strictly better than printed.
    """

    def test_it_exists(self, pool):
        assert pool.get("servo_1_1_c") is not None

    def test_it_is_a_one_one_colorless_artifact_servo(self, pool):
        servo = pool.get("servo_1_1_c")
        assert (servo.power, servo.toughness) == (1, 1)
        assert not servo.colors, "colorless -- the printed word"
        assert "Artifact" in servo.types and "Creature" in servo.types
        assert list(servo.subtypes) == ["Servo"]
        assert not servo.keywords
        assert servo.is_token


class TestThePhyrexianMiteHasToxicAndCantBlock:
    """Skrelv's Hive and White Sun's Twilight: *"create a 1/1 colorless
    **Phyrexian Mite** artifact creature token with **toxic 1** and "This token
    can't block.""*

    The nearest bodies are the Servo above, the Myr and the Gnome: the right
    size and colour with neither the toxic nor the restriction. Toxic is the
    load-bearing half -- Skrelv's Hive gives lifelink to "creatures you control
    with toxic", so a Servo would gain nothing and poison nobody -- and the
    restriction is a drawback a near miss would quietly drop.
    """

    def test_it_exists(self, pool):
        assert pool.get("phyrexian_mite_1_1_c_toxic") is not None

    def test_it_is_a_one_one_colorless_artifact_phyrexian_mite(self, pool):
        mite = pool.get("phyrexian_mite_1_1_c_toxic")
        assert (mite.power, mite.toughness) == (1, 1)
        assert not mite.colors, "colorless -- the printed word"
        assert "Artifact" in mite.types and "Creature" in mite.types
        assert set(mite.subtypes) == {"Phyrexian", "Mite"}
        assert mite.is_token

    def test_it_has_toxic_1(self, pool):
        mite = pool.get("phyrexian_mite_1_1_c_toxic")
        assert set(mite.keywords) == {"toxic"}
        assert mite.toxic == 1

    def test_it_cannot_block(self, pool):
        mite = pool.get("phyrexian_mite_1_1_c_toxic")
        assert [a.static.get("effect") for a in mite.abilities] == ["cant_block"]

    def test_the_servo_is_still_a_separate_token(self, pool):
        servo = pool.get("servo_1_1_c")
        assert not servo.keywords and servo.toxic == 0


class TestDawnOfHopesSoldiersHaveLifelink:
    """Dawn of Hope: *"{3}{W}: Create a 1/1 white Soldier creature token with
    **lifelink**."*

    `soldier_1_1_w` is the right body without the keyword, and lifelink is the
    engine of the card: each Soldier's combat damage gains life, which is what
    feeds Dawn of Hope's own "whenever you gain life" draw. The vanilla Soldier
    would sever the loop the card is built around.
    """

    def test_it_exists(self, pool):
        assert pool.get("soldier_1_1_w_lifelink") is not None

    def test_it_is_a_one_one_white_soldier_with_lifelink(self, pool):
        soldier = pool.get("soldier_1_1_w_lifelink")
        assert (soldier.power, soldier.toughness) == (1, 1)
        assert sorted(soldier.colors) == ["W"]
        assert list(soldier.subtypes) == ["Soldier"]
        assert "lifelink" in soldier.keywords
        assert soldier.is_creature and soldier.is_token
        assert "Artifact" not in soldier.types

    def test_the_vanilla_white_soldier_is_still_a_separate_token(self, pool):
        other = pool.get("soldier_1_1_w")
        assert other is not None
        assert "lifelink" not in other.keywords


class TestChasmSkulkersSquidsHaveIslandwalk:
    """Chasm Skulker: *"create X 1/1 blue Squid creature tokens with
    **islandwalk**."*

    `fish_1_1_u` is the nearest body: one-one and blue, but a Fish with no
    keyword. Islandwalk is what lets a swarm of one-ones matter against a blue
    opponent, so the vanilla Fish would be a weaker card than the printed one.
    """

    TOKEN = "squid_1_1_u_islandwalk"

    def test_it_exists(self, pool):
        assert pool.get(self.TOKEN) is not None

    def test_it_is_a_one_one_blue_squid_with_islandwalk(self, pool):
        squid = pool.get(self.TOKEN)
        assert (squid.power, squid.toughness) == (1, 1)
        assert sorted(squid.colors) == ["U"]
        assert list(squid.subtypes) == ["Squid"]
        assert list(squid.keywords) == ["islandwalk"]
        assert squid.is_creature and squid.is_token

    def test_the_vanilla_blue_fish_is_still_a_separate_token(self, pool):
        other = pool.get("fish_1_1_u")
        assert other is not None
        assert list(other.subtypes) == ["Fish"]
        assert not other.keywords


class TestEmeriasCallsAngelsAreWarriorsToo:
    """Emeria's Call: *"Create two 4/4 white **Angel Warrior** creature tokens
    with flying."*

    `angel_4_4_w_flying` is the right body and keyword with one creature type
    missing. Warrior-typal cards count the second type, so the plain Angel is a
    near miss rather than a stand-in.
    """

    def test_it_exists(self, pool):
        assert pool.get("angel_warrior_4_4_w_flying") is not None

    def test_it_is_a_four_four_white_angel_warrior_with_flying(self, pool):
        token = pool.get("angel_warrior_4_4_w_flying")
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["W"]
        assert set(token.subtypes) == {"Angel", "Warrior"}
        assert "flying" in token.keywords
        assert token.is_creature and token.is_token

    def test_the_plain_angel_is_still_a_separate_token(self, pool):
        other = pool.get("angel_4_4_w_flying")
        assert other is not None
        assert "Warrior" not in other.subtypes


class TestTheWanderingEmperorsSamurai:
    """The Wandering Emperor, -1: *"Create a **2/2 white Samurai** creature
    token with vigilance."*

    `knight_2_2_w_vigilance` matches every characteristic but the creature
    type, and Samurai- and Knight-typal cards read exactly that one.
    """

    def test_it_exists(self, pool):
        assert pool.get("samurai_2_2_w_vigilance") is not None

    def test_it_is_a_two_two_white_samurai_with_vigilance(self, pool):
        token = pool.get("samurai_2_2_w_vigilance")
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["W"]
        assert list(token.subtypes) == ["Samurai"]
        assert "vigilance" in token.keywords
        assert token.is_creature and token.is_token

    def test_the_vigilance_knight_is_still_a_separate_token(self, pool):
        other = pool.get("knight_2_2_w_vigilance")
        assert other is not None
        assert "Samurai" not in other.subtypes


class TestVerdantKrakensTentacleIsALand:
    """Verdant Kraken: *"you create a **3/3 green Forest Tentacle land creature**
    token. (It has "{T}: Add {G}." ...)"*

    Two near misses, each with half the card. `forest_dryad_1_1_g_land` is the
    right shape -- a green Forest land creature that taps for {G} -- at a third
    of the body. `tentacle_1_1_u` has the right creature type and is a blue
    non-land 1/1 with no mana ability. The land type is the load-bearing part:
    the Kraken makes one on *every* player's upkeep, and each is a land that
    landfall, land-count and Forest-typal cards (Aesi's own deck is full of
    them) are meant to see.
    """

    def test_it_exists(self, pool):
        assert pool.get("forest_tentacle_3_3_g_land") is not None

    def test_it_is_a_three_three_green_forest_tentacle_land_creature(self, pool):
        token = pool.get("forest_tentacle_3_3_g_land")
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["G"]
        assert set(token.types) == {"Land", "Creature"}
        assert set(token.subtypes) == {"Forest", "Tentacle"}
        assert not token.keywords
        assert token.is_token

    def test_it_taps_for_green(self, pool):
        """The reminder text is the Forest's intrinsic ability (305.6), written
        out as an ability the way the Dryad token carries it."""
        mana = [a for a in pool.get("forest_tentacle_3_3_g_land").abilities if a.is_mana_ability]
        assert len(mana) == 1

    def test_the_dryad_and_the_blue_tentacle_are_still_separate_tokens(self, pool):
        dryad = pool.get("forest_dryad_1_1_g_land")
        assert dryad is not None and (dryad.power, dryad.toughness) == (1, 1)
        tentacle = pool.get("tentacle_1_1_u")
        assert tentacle is not None and "Land" not in tentacle.types


class TestJosuVesssKnightsAreZombieKnightsWithMenace:
    """Josu Vess, Lich Knight, kicked: *"create eight 2/2 black **Zombie Knight**
    creature tokens with **menace**."*

    The pool had `zombie_2_2_b` (no menace, no Knight) and `pirate_2_2_b_menace`
    (the wrong creature type). Eight of either is a different card: a Zombie
    deck's lords count the subtype, and menace is most of what the kicker buys.
    """

    def test_it_exists(self, pool):
        assert pool.get("zombie_knight_2_2_b_menace") is not None

    def test_it_is_a_two_two_black_zombie_knight_with_menace(self, pool):
        knight = pool.get("zombie_knight_2_2_b_menace")
        assert (knight.power, knight.toughness) == (2, 2)
        assert sorted(knight.colors) == ["B"]
        assert {"Zombie", "Knight"} <= set(knight.subtypes)
        assert "menace" in knight.keywords
        assert knight.is_creature and knight.is_token

    def test_the_plain_zombie_is_still_a_separate_token(self, pool):
        other = pool.get("zombie_2_2_b")
        assert other is not None
        assert "menace" not in other.keywords
        assert "Knight" not in other.subtypes


class TestJadarsZombiesHaveDecayed:
    """Jadar, Ghoulcaller of Nephalia: *"if you control no creatures with
    decayed, create a 2/2 black Zombie creature token **with decayed**."*

    `zombie_2_2_b` is the right body without the keyword, and on this card the
    keyword is the whole engine: the plain Zombie can block, is never
    sacrificed, and never satisfies the intervening-if, so Jadar would make one
    every end step instead of one at a time.
    """

    def test_it_is_a_two_two_black_zombie_with_decayed(self, pool):
        token = pool.get("zombie_2_2_b_decayed")
        assert token is not None
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Zombie"]
        assert list(token.keywords) == ["decayed"]
        assert token.is_creature and token.is_token

    def test_the_plain_zombie_is_still_a_separate_token(self, pool):
        other = pool.get("zombie_2_2_b")
        assert other is not None
        assert "decayed" not in other.keywords


class TestCurrencyConvertersRogueIsATwoTwoBlack:
    """Currency Converter: *"If it's a nonland card, create a **2/2 black
    Rogue** creature token."*

    Two near misses, each wrong on one axis. `vampire_rogue_1_1_b_lifelink` is
    the pool's other black Rogue, on half the body with a keyword the card never
    prints; `zombie_2_2_b` is the right body with the wrong creature type, and
    Rogue- and Zombie-typal cards each read exactly that.
    """

    def test_it_is_a_vanilla_two_two_black_rogue(self, pool):
        token = pool.get("rogue_2_2_b")
        assert token is not None
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Rogue"]
        assert not token.keywords
        assert token.is_creature and token.is_token

    def test_the_vampire_rogue_is_still_a_separate_token(self, pool):
        other = pool.get("vampire_rogue_1_1_b_lifelink")
        assert other is not None
        assert (other.power, other.toughness) == (1, 1)
        assert "lifelink" in other.keywords


class TestBarretsRebelIsATwoTwoRed:
    """Barret, Avalanche Leader: *"Whenever an Equipment you control enters,
    create a **2/2 red Rebel** creature token."*

    `human_knight_2_2_r_trample_haste` is the pool's other 2/2 red token: the
    right body with two keywords the card never prints and the wrong creature
    types, and Barret's own combat trigger attaches only to a Rebel (111.4).
    """

    def test_it_is_a_vanilla_two_two_red_rebel(self, pool):
        token = pool.get("rebel_2_2_r")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["R"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Rebel"]
        assert not token.keywords
        assert not token.abilities

    def test_the_human_knight_is_still_a_separate_token(self, pool):
        other = pool.get("human_knight_2_2_r_trample_haste")
        assert other is not None
        assert (other.power, other.toughness) == (2, 2)
        assert sorted(other.keywords) == ["haste", "trample"]
        assert "Rebel" not in other.subtypes

    def test_an_equipment_entering_makes_one_and_combat_can_equip_it(self, builder):
        """Accorder's Shield costs nothing, so the Rebel is the trigger's alone;
        the beginning-of-combat trigger then hangs the Shield on that token."""
        game = (
            builder(players=2)
            .battlefield(0, ["barret_avalanche_leader", "mountain"])
            .hand(0, ["accorder_s_shield"])
            .build()
        )
        cast = next(
            a for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "accorder_s_shield"
        )
        game.apply(cast)
        settle_completely(game)
        rebel = only_oid(game, "rebel_2_2_r", 0)
        shield = only_oid(game, "accorder_s_shield", 0)

        pass_until(game, lambda g: g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
        # The trigger's declaration offers each legal (Equipment, Rebel) pair,
        # and the bare Rebels for "up to one" Equipment chosen as none.
        (index,) = [
            i for i, option in enumerate(game.pending().options)
            if option.label == "Accorder's Shield, Rebel Token"
        ]
        game.apply(find_action(game, ActionKind.CHOOSE, choice=index))
        settle_completely(game)
        assert game.state.objects[shield].attached_to == rebel


class TestMyrBattlespheresMyrAreColorlessArtifactMyr:
    """Myr Battlesphere: *"create four **1/1 colorless Myr artifact** creature
    tokens"*, and then *"you may tap X untapped **Myr** you control"*.

    The pool had 1/1 colorless artifact creatures -- Servo, Gnome, Soldier --
    and no Myr. The subtype is the card: its own attack trigger counts untapped
    Myr, so a Servo in its place would leave the Battlesphere's four tokens
    unable to feed it.
    """

    def test_it_exists(self, pool):
        assert pool.get("myr_1_1_c") is not None

    def test_it_is_a_one_one_colorless_artifact_myr(self, pool):
        myr = pool.get("myr_1_1_c")
        assert (myr.power, myr.toughness) == (1, 1)
        assert not myr.colors, "colorless -- the printed word"
        assert "Artifact" in myr.types and "Creature" in myr.types
        assert list(myr.subtypes) == ["Myr"]
        assert not myr.keywords
        assert myr.is_token

    def test_the_servo_is_still_a_separate_token(self, pool):
        servo = pool.get("servo_1_1_c")
        assert servo is not None
        assert list(servo.subtypes) == ["Servo"]


class TestUtvaraHellkitesDragonIsASixSix:
    """Utvara Hellkite: *"Whenever a Dragon you control attacks, create a
    **6/6** red Dragon creature token with flying."*

    `dragon_5_5_r_flying` is the right colour, type and keyword on the wrong
    body. The Hellkite's tokens are Dragons that attack and make more of
    themselves, so a smaller token is not made once but compounds every turn.
    """

    def test_it_exists(self, pool):
        assert pool.get("dragon_6_6_r_flying") is not None

    def test_it_is_a_six_six_red_dragon_with_flying(self, pool):
        token = pool.get("dragon_6_6_r_flying")
        assert (token.power, token.toughness) == (6, 6)
        assert sorted(token.colors) == ["R"]
        assert list(token.subtypes) == ["Dragon"]
        assert list(token.keywords) == ["flying"]
        assert token.is_creature and token.is_token

    def test_the_five_five_dragon_is_still_a_separate_token(self, pool):
        other = pool.get("dragon_5_5_r_flying")
        assert other is not None
        assert (other.power, other.toughness) == (5, 5)


class TestTheElderDragonWarsDragonIsAFourFour:
    """The Elder Dragon War, chapter III: *"Create a **4/4** red Dragon creature
    token with flying."*

    `dragon_5_5_r_flying` is the same near miss one size the other way: the
    printed chapter makes a smaller Dragon than the 5/5, and a Saga that read
    ahead straight to chapter III would hand over the bigger one on turn three.
    """

    def test_it_is_a_four_four_red_dragon_with_flying(self, pool):
        token = pool.get("dragon_4_4_r_flying")
        assert token is not None
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["R"]
        assert list(token.subtypes) == ["Dragon"]
        assert list(token.keywords) == ["flying"]
        assert token.is_creature and token.is_token

    def test_the_five_five_dragon_is_still_a_separate_token(self, pool):
        other = pool.get("dragon_5_5_r_flying")
        assert other is not None
        assert (other.power, other.toughness) == (5, 5)


class TestTheSpiderIsAOneTwoWithReach:
    """Arasta of the Endless Web and Arachnogenesis: *"create a 1/2 green
    Spider creature token with reach."*

    `insect_1_1_g` and `plant_0_1_g` are the nearest green bodies, and both
    are the wrong type, size and keyword. Arachnogenesis prevents combat
    damage from every non-Spider, so a token that is not a Spider would turn
    its own blockers off.
    """

    def test_it_is_a_one_two_green_spider_with_reach(self, pool):
        token = pool.get("spider_1_2_g_reach")
        assert token is not None
        assert (token.power, token.toughness) == (1, 2)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Spider"]
        assert list(token.keywords) == ["reach"]
        assert token.is_creature and token.is_token

    def test_the_insect_is_still_a_separate_token(self, pool):
        insect = pool.get("insect_1_1_g")
        assert insect is not None
        assert list(insect.subtypes) == ["Insect"]


class TestKherKeepsKoboldsCarryTheirName:
    """Kher Keep: *"Create a 0/1 red Kobold creature token **named Kobolds of
    Kher Keep**."*

    `plant_0_1_g` is the pool's other 0/1 and is the wrong colour and type.
    The name is a characteristic too (111.4), and it is the one a vanilla
    "Kobold Token" would get wrong: it is the name of a real {0} 0/1 card, which
    is also why `CardRegistry.by_name` must never answer it with the token.
    """

    def test_it_is_a_zero_one_red_kobold_named_for_the_keep(self, pool):
        token = pool.get("kobolds_of_kher_keep_0_1_r")
        assert token is not None
        assert token.name == "Kobolds of Kher Keep"
        assert (token.power, token.toughness) == (0, 1)
        assert sorted(token.colors) == ["R"]
        assert list(token.subtypes) == ["Kobold"]
        assert not token.keywords
        assert token.is_creature and token.is_token

    def test_the_card_of_the_same_name_is_still_a_separate_card(self, pool):
        card = pool.get("kobolds_of_kher_keep")
        assert card is not None and not card.is_token
        assert pool.by_name("Kobolds of Kher Keep").id == "kobolds_of_kher_keep"

    def test_the_plant_is_still_a_separate_token(self, pool):
        plant = pool.get("plant_0_1_g")
        assert plant is not None
        assert sorted(plant.colors) == ["G"]


class TestSetzersBlackjackIsALegendaryFlyingVehicle:
    """Setzer, Wandering Gambler: *"create **The Blackjack, a legendary 3/3
    colorless Vehicle artifact token with flying and crew 2**."*

    Every part is a characteristic a card reads. The name and the supertype put
    it under the legend rule; the Vehicle subtype is what Setzer's second
    ability watches; and it is an artifact, not a creature, until it is crewed.
    `pilot_1_1_c_crew2` is the pool's only other crew-related token and is the
    creature that does the crewing, not a Vehicle; `komas_coil_3_3_u` is the
    other named 3/3 and is a blue Serpent creature.
    """

    TOKEN = "the_blackjack_3_3_c_flying_crew2"

    def test_it_is_a_legendary_three_three_colorless_flying_vehicle(self, pool):
        token = pool.get(self.TOKEN)
        assert token is not None and token.is_token
        assert token.name == "The Blackjack"
        assert sorted(token.supertypes) == ["Legendary"]
        assert list(token.types) == ["Artifact"]
        assert list(token.subtypes) == ["Vehicle"]
        assert (token.power, token.toughness) == (3, 3)
        assert not token.colors and not token.color_identity
        assert list(token.keywords) == ["flying"]
        assert not token.is_creature

    def test_its_one_ability_is_crew_two(self, pool):
        (crew,) = pool.get(self.TOKEN).abilities
        assert crew.text == "Crew 2"
        assert crew.cost.tap_permanents["total_power"] == 2

    def test_a_two_power_creature_crews_it_into_a_three_three_flier(self, builder):
        game = two_seat_board(builder, mine=[self.TOKEN, "grizzly_bears"])
        vehicle = only_oid(game, self.TOKEN, 0)
        assert "Creature" not in chars(game.state, vehicle).types
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == vehicle
            )
        )
        settle_completely(game)
        assert {"Artifact", "Creature"} <= chars(game.state, vehicle).types
        assert pt(game, vehicle) == (3, 3)
        assert "flying" in keywords(game, vehicle)

    @staticmethod
    def _can_crew(game, vehicle: int) -> bool:
        return any(
            a.kind is ActionKind.ACTIVATE and a.source == vehicle
            for a in game.legal_actions()
        )

    def test_a_one_power_creature_cannot_crew_it(self, builder):
        game = two_seat_board(builder, mine=[self.TOKEN, "llanowar_elves"])
        assert not self._can_crew(game, only_oid(game, self.TOKEN, 0))

    def test_a_pilot_crews_it_as_a_three(self, builder):
        game = two_seat_board(builder, mine=[self.TOKEN, "pilot_1_1_c_crew2"])
        assert self._can_crew(game, only_oid(game, self.TOKEN, 0))

    def test_the_pilot_is_still_a_separate_token(self, pool):
        pilot = pool.get("pilot_1_1_c_crew2")
        assert pilot.is_creature and list(pilot.subtypes) == ["Pilot"]
        assert "Vehicle" not in pilot.subtypes


class TestPiasAetherjetIsAnXXFlyingVehicle:
    """Pia Nalaar, Chief Mechanic: *"create an **X/X colorless Vehicle artifact
    token named Nalaar Aetherjet with flying and crew 2**, where X is the amount
    of {E} paid this way."*

    The Blackjack is the near miss: the same flying crew-2 Vehicle, but a fixed
    3/3, legendary, and named something else. The Aetherjet's size is the
    creating effect's (111.4), so it is written 0/0 with `variable_pt`, and its
    crew keeps that size (`keep_pt`) instead of naming one -- crewing it twice,
    or with a counter on it, must not move the base the token was made at.
    """

    TOKEN = "nalaar_aetherjet_x_x_c_flying_crew2"

    def test_it_is_a_nonlegendary_colorless_flying_vehicle_sized_by_its_maker(self, pool):
        token = pool.get(self.TOKEN)
        assert token is not None and token.is_token
        assert token.name == "Nalaar Aetherjet"
        assert not token.supertypes
        assert list(token.types) == ["Artifact"]
        assert list(token.subtypes) == ["Vehicle"]
        assert (token.power, token.toughness) == (0, 0) and token.variable_pt
        assert not token.colors and not token.color_identity
        assert list(token.keywords) == ["flying"]
        assert not token.is_creature

    def test_the_blackjack_is_still_a_separate_fixed_size_token(self, pool):
        blackjack = pool.get("the_blackjack_3_3_c_flying_crew2")
        assert (blackjack.power, blackjack.toughness) == (3, 3)
        assert not blackjack.variable_pt

    def _jet(self, builder, x: int, counters: int = 0):
        """The token as `create_token` leaves an X/X: its base size in
        `copy_overrides`, which is where the creating effect's values live."""
        b = builder(players=2).battlefield(0, [self.TOKEN, "grizzly_bears", "grizzly_bears"])
        (jet,) = [o.oid for o in b.state.objects.values() if o.def_id == self.TOKEN]
        b.state.objects[jet].copy_overrides = {"power": x, "toughness": x}
        if counters:
            b.state.objects[jet].counters["+1/+1"] = counters
        return b.build(), jet

    def _crew(self, game, jet: int) -> None:
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == jet
            )
        )
        settle_completely(game)

    def test_crewed_it_is_the_size_it_was_made_at(self, builder):
        game, jet = self._jet(builder, 4)
        assert "Creature" not in chars(game.state, jet).types
        self._crew(game, jet)
        assert {"Artifact", "Creature"} <= chars(game.state, jet).types
        assert pt(game, jet) == (4, 4)
        assert "flying" in keywords(game, jet)

    def test_crewing_it_again_does_not_move_the_base(self, builder):
        game, jet = self._jet(builder, 4, counters=1)
        self._crew(game, jet)
        assert pt(game, jet) == (5, 5)
        self._crew(game, jet)
        assert pt(game, jet) == (5, 5)

    @staticmethod
    def _crew_with(animate: dict) -> None:
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.cards.schema import CardModel

        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_bad_jet", "name": "Bad Jet", "oracle_text": "Crew 2",
                    "mana_cost": "{2}", "types": ["Artifact"], "subtypes": ["Vehicle"],
                    "power": 3, "toughness": 3,
                    "abilities": [{
                        "kind": "activated", "text": "Crew 2",
                        "cost": {"tap_permanents": {"controller": "you", "total_power": 2,
                                                    "types": ["Creature"]}},
                        "effects": [{"op": "animate", "types": ["Creature"], **animate}],
                    }],
                }
            )
        )

    def test_keep_pt_with_a_size_is_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="keep_pt"):
            self._crew_with({"objects": {"self_only": True, "zone": "battlefield"},
                             "keep_pt": True, "power": {"const": 3},
                             "toughness": {"const": 3}})

    def test_keep_pt_on_anything_but_itself_is_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="self_only"):
            self._crew_with({"objects": {"zone": "battlefield", "subtypes": ["Vehicle"]},
                             "keep_pt": True})

    def test_a_creature_animation_with_no_size_is_still_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="power"):
            self._crew_with({"objects": {"self_only": True, "zone": "battlefield"}})


class TestEzurisPredationMakesPhyrexianBeasts:
    """Ezuri's Predation: *"create a 4/4 green **Phyrexian** Beast creature
    token."*

    `beast_4_4_g` is the same body without the Phyrexian subtype, and the
    pool does read it (`germ_0_0_b` is a Phyrexian Germ), so the plain Beast
    would miss every Phyrexian-matters card.
    """

    def test_it_is_a_four_four_green_phyrexian_beast(self, pool):
        token = pool.get("phyrexian_beast_4_4_g")
        assert token is not None
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["G"]
        assert sorted(token.subtypes) == ["Beast", "Phyrexian"]
        assert not token.keywords
        assert token.is_creature and token.is_token

    def test_the_plain_beast_is_still_a_separate_token(self, pool):
        beast = pool.get("beast_4_4_g")
        assert beast is not None
        assert list(beast.subtypes) == ["Beast"]


class TestArchitectOfTheUntamedsBeastIsAColorlessArtifact:
    """Architect of the Untamed: *"Pay eight {E}: Create a 6/6 **colorless**
    Beast **artifact** creature token."*

    Every other Beast in the pool is green or white and none is an artifact,
    so `beast_4_4_g` is wrong in body, colour and card type; `golem_9_9_c_artifact`
    is the right colour and type on the wrong body and creature type. An
    artifact deck counts this Beast and a green one would not be counted.
    """

    def test_it_is_a_six_six_colorless_beast_artifact_with_nothing_else(self, pool):
        token = pool.get("beast_6_6_c_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (6, 6)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Beast"]
        assert not token.keywords
        assert not token.abilities

    def test_the_green_beast_is_still_a_separate_token(self, pool):
        beast = pool.get("beast_4_4_g")
        assert beast is not None
        assert sorted(beast.colors) == ["G"]
        assert "Artifact" not in beast.types


class TestEmpowersJaceIsABlueZeroLoyaltyPlaneswalker:
    """Empower Jace N: *"…first create a **blue Jace planeswalker** token with
    "[-1]: Surveil 1" and "[-3]: Draw a card."*" (Plan for All Outcomes).
    The catalog's tfra token row prints no loyalty, so it starts at 0 and
    lives on the counters empower puts on it.

    The pool's only planeswalker token, and nothing may stand in for it: a
    printed starting loyalty would make every empower worth that much more,
    and `op_empower` finds it by its Jace subtype.
    """

    def test_it_is_a_blue_jace_planeswalker_with_no_loyalty(self, pool):
        jace = pool.get("jace_planeswalker_u")
        assert jace is not None and jace.is_token
        assert jace.name == "Jace"
        assert list(jace.types) == ["Planeswalker"]
        assert list(jace.subtypes) == ["Jace"]
        assert not jace.supertypes, "not legendary: two may coexist"
        assert sorted(jace.colors) == ["U"]
        assert jace.loyalty == 0

    def test_it_has_exactly_the_two_printed_abilities(self, pool):
        jace = pool.get("jace_planeswalker_u")
        assert [a.cost.loyalty for a in jace.abilities] == [-1, -3]
        assert [a.effects[0]["op"] for a in jace.abilities] == ["surveil", "draw"]

    def test_it_is_the_only_planeswalker_token(self, pool):
        tokens = [c.id for c in pool if c.is_token and "Planeswalker" in c.types]
        assert tokens == ["jace_planeswalker_u"]


class TestAmassArmiesAreZeroZeroBlackArmies:
    """Amass [subtype] N (701.47a): *"…create a 0/0 black [subtype] Army
    creature token"* (Dreadhorde Invasion amasses Zombies; the catalog's tfrc,
    tltr, thob and tcmm rows are the Zombie, Orc, Goblin and Sliver Armies).

    The pool's other 0/0 black creature token is the Phyrexian Germ, and the
    other black Zombies are 2/2s. Neither stands in: a printed size would make
    every amass worth that much more, and `op_amass` finds the Army it grows by
    its Army subtype.
    """

    ARMIES = {
        "Zombie": "zombie_army_0_0_b",
        "Orc": "orc_army_0_0_b",
        "Goblin": "goblin_army_0_0_b",
        "Sliver": "sliver_army_0_0_b",
    }

    @pytest.mark.parametrize("subtype", sorted(ARMIES))
    def test_each_is_a_zero_zero_black_army_of_its_subtype(self, pool, subtype):
        army = pool.get(self.ARMIES[subtype])
        assert army is not None and army.is_token
        assert (army.power, army.toughness) == (0, 0)
        assert sorted(army.colors) == ["B"]
        assert list(army.types) == ["Creature"]
        assert sorted(army.subtypes) == sorted([subtype, "Army"])
        assert not army.keywords and not army.abilities

    def test_the_op_names_exactly_these(self):
        from commanderblitz.engine.effects.ops_counters import AMASS_TOKENS

        assert AMASS_TOKENS == self.ARMIES

    def test_the_germ_is_still_a_separate_token(self, pool):
        germ = pool.get("germ_0_0_b")
        assert germ is not None
        assert "Army" not in germ.subtypes


class TestIncubatesIncubatorIsADoubleFacedToken:
    """Incubate N (701.53a): *"Create an Incubator token with N +1/+1 counters
    on it and '{2}: Transform this artifact.' It transforms into a 0/0
    Phyrexian artifact creature."* (Sunfall; the catalog's tfrc Incubator //
    Phyrexian row.)

    The pool's other colorless Phyrexian artifact creature is the 1/1 Mite with
    toxic, and its other 0/0 Phyrexian is the black Germ. Neither stands in for
    the back face: a printed size or colour would make every incubate a
    different card, and the back is only ever reached by transforming the
    front, which is why linking refuses a `create_token` that names it.
    """

    def test_the_front_is_a_colorless_incubator_artifact(self, pool):
        front = pool.get("incubator_token")
        assert front is not None and front.is_token
        assert list(front.types) == ["Artifact"]
        assert list(front.subtypes) == ["Incubator"]
        assert not front.colors
        assert (front.power, front.toughness) == (None, None)
        [ability] = front.abilities
        assert ability.text == "{2}: Transform this artifact."
        assert ability.cost.mana.text == "{2}"
        assert ability.effects == ({"op": "transform"},)

    def test_the_back_is_a_zero_zero_colorless_phyrexian_artifact_creature(self, pool):
        back = pool.get("phyrexian_0_0_c_artifact")
        assert back is not None and back.is_token
        assert sorted(back.types) == ["Artifact", "Creature"]
        assert list(back.subtypes) == ["Phyrexian"]
        assert (back.power, back.toughness) == (0, 0)
        assert not back.colors
        assert not back.keywords and not back.abilities

    def test_the_faces_are_linked(self, pool):
        assert pool.get("incubator_token").back_face == "phyrexian_0_0_c_artifact"
        assert pool.get("phyrexian_0_0_c_artifact").front_face == "incubator_token"

    def test_the_op_names_the_front(self):
        from commanderblitz.engine.effects.ops_counters import INCUBATOR_TOKEN

        assert INCUBATOR_TOKEN == "incubator_token"

    def test_the_mite_and_the_germ_are_still_separate_tokens(self, pool):
        mite = pool.get("phyrexian_mite_1_1_c_toxic")
        germ = pool.get("germ_0_0_b")
        assert (mite.power, mite.toughness) == (1, 1) and mite.keywords
        assert sorted(germ.colors) == ["B"]


class TestSharkTyphoonsSharkIsAnXXBlueFlier:
    """Shark Typhoon: *"…create an **X/X blue Shark** creature token **with
    flying**"* (the catalog's Shark token row prints `*/*`, blue, Flying).

    Written 0/0 with `variable_pt`, because its size is the creating effect's
    (see `tests/unit/tokens/test_variable_pt_token.py`). The pool's other 0/0
    blue creature token is the green-and-blue Fractal, and its blue fliers are
    printed sizes; none stands in. A Fractal is a 0/0 that is *given* counters,
    so it carries no flag.
    """

    def test_it_is_an_x_x_blue_shark_with_flying(self, pool):
        shark = pool.get("shark_x_x_u_flying")
        assert shark is not None and shark.is_token and shark.is_creature
        assert shark.variable_pt
        assert (shark.power, shark.toughness) == (0, 0)
        assert sorted(shark.colors) == ["U"]
        assert list(shark.types) == ["Creature"]
        assert list(shark.subtypes) == ["Shark"]
        assert list(shark.keywords) == ["flying"]
        assert not shark.abilities

    def test_the_fractal_is_still_a_printed_zero_zero(self, pool):
        fractal = pool.get("fractal_0_0_gu")
        assert not fractal.variable_pt
        assert sorted(fractal.colors) == ["G", "U"]


class TestTheMistmoorsInsectsAreTwoOneWhiteFliers:
    """Overlord of the Mistmoors: *"create two **2/1 white Insect** creature
    tokens **with flying**"* (the catalog's Insect token row prints 2/1, white,
    Flying).

    `insect_1_1_g` is the pool's only other Insect, and it is wrong three ways
    at once: half the power, the wrong colour and no evasion. Two of them on
    every enter and every attack is a strictly weaker card than the printed one.
    """

    def test_it_is_a_two_one_white_insect_with_flying(self, pool):
        token = pool.get("insect_2_1_w_flying")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 1)
        assert sorted(token.colors) == ["W"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Insect"]
        assert list(token.keywords) == ["flying"]
        assert not token.abilities

    def test_the_green_insect_is_still_a_separate_token(self, pool):
        other = pool.get("insect_1_1_g")
        assert (other.power, other.toughness) == (1, 1)
        assert sorted(other.colors) == ["G"]
        assert not other.keywords


class TestGingersGingerbruteIsAHastyFoodGolem:
    """Ginger, Queen of Sweets: *"create a **Gingerbrute** token. (It's a {1}
    1/1 Food Golem artifact creature with haste, "{1}: This token can't be
    blocked this turn except by creatures with haste," and "{2}, {T}, Sacrifice
    this token: You gain 3 life.")"*

    The near misses are `gnome_1_1_c`, the pool's other colorless 1/1 artifact
    creature (vanilla, no haste, no Food to sacrifice), and `food_token`, which
    has the life line but is no creature. The evasion line is `unblockable`
    with `except_blockers`, never the plain op: without the exemption the token
    would be blockable by nothing. Stored, like every token, with no mana cost.
    """

    def test_it_is_a_one_one_colorless_food_golem_with_haste(self, pool):
        token = pool.get("gingerbrute_1_1_c")
        assert token is not None and token.is_token and token.is_creature
        assert token.name == "Gingerbrute"
        assert (token.power, token.toughness) == (1, 1)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert sorted(token.subtypes) == ["Food", "Golem"]
        assert list(token.keywords) == ["haste"]

    def test_it_has_exactly_the_two_printed_abilities(self, pool):
        token = pool.get("gingerbrute_1_1_c")
        evade, food = token.abilities
        assert [e["op"] for e in evade.effects] == ["unblockable"]
        assert evade.effects[0]["except_blockers"] == {"keywords": ["haste"]}
        assert evade.effects[0]["duration"] == "this_turn"
        assert [e["op"] for e in food.effects] == ["gain_life"]
        assert food.cost.tap and food.cost.sacrifice

    def test_the_gnome_and_the_food_are_still_separate_tokens(self, pool):
        gnome, food = pool.get("gnome_1_1_c"), pool.get("food_token")
        assert not gnome.keywords and not gnome.abilities
        assert not food.is_creature

    def test_the_name_does_not_answer_for_a_card(self, pool):
        card = pool.by_name("Gingerbrute")
        assert card is None or not card.is_token


class TestVibraniumIsAnIndestructibleArtifactWithRestrictedMana:
    """T'Challa, the Black Panther; Dora Milaje Elite; The Great Mound; Vibranium
    Mining Mech; Shuri's Fabricator: *"create a tapped Vibranium token. (It's an
    artifact with indestructible and "{T}: Add {C}. This mana can't be spent to
    cast a nonartifact spell.")"*

    `treasure_token` is the near miss: the pool's other colorless mana-making
    artifact, but it sacrifices itself, makes any colour, carries no restriction
    and is not indestructible. Every one of those differences is a different
    card. The restriction is a prohibition, so its `other` half is the wildcard
    -- see `tests/unit/mana/test_mana_restriction_other.py`.
    """

    def test_it_is_an_indestructible_colorless_vibranium_artifact(self, pool):
        token = pool.get("vibranium_token")
        assert token is not None and token.is_token
        assert token.name == "Vibranium"
        assert list(token.types) == ["Artifact"]
        assert list(token.subtypes) == ["Vibranium"]
        assert not token.colors
        assert (token.power, token.toughness) == (None, None)
        assert list(token.keywords) == ["indestructible"]

    def test_it_taps_for_one_colorless_its_mana_barred_from_nonartifact_spells(self, pool):
        [ability] = pool.get("vibranium_token").abilities
        assert ability.is_mana_ability
        assert ability.cost.tap and not ability.cost.sacrifice
        assert ability.effects == ({"op": "add_mana", "mana": "{C}"},)
        restriction = ability.mana_restriction
        assert [g.required for g in restriction.cast] == [frozenset({"artifact"})]
        assert [g.required for g in restriction.activate] == [frozenset()]
        assert [g.required for g in restriction.other] == [frozenset()]

    def test_the_treasure_is_still_a_separate_token(self, pool):
        treasure = pool.get("treasure_token")
        assert not treasure.keywords
        assert treasure.abilities[0].cost.sacrifice
        assert treasure.abilities[0].mana_restriction is None


class TestTradingPostsGoatIsAZeroOneWhite:
    """Trading Post: *"{1}, {T}, Pay 1 life: Create a 0/1 white Goat creature
    token."*

    The pool's other 0/1 tokens are `plant_0_1_g` and
    `kobolds_of_kher_keep_0_1_r`: the right size, the wrong colour and the wrong
    creature type, both of which a card can read.
    """

    def test_it_is_a_zero_one_white_goat(self, pool):
        token = pool.get("goat_0_1_w")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (0, 1)
        assert sorted(token.colors) == ["W"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Goat"]
        assert not token.keywords and not token.abilities

    def test_the_plant_is_still_a_separate_token(self, pool):
        plant = pool.get("plant_0_1_g")
        assert (plant.power, plant.toughness) == (0, 1)
        assert sorted(plant.colors) == ["G"]
        assert "Goat" not in plant.subtypes


class TestWKabisRhinoIsAFourFourGreenTrampler:
    """W'Kabi, Shield of the Nation: *"…create a 4/4 green Rhino creature token
    with trample."*

    `beast_4_4_g` and `phyrexian_beast_4_4_g` are the pool's other 4/4 green
    tokens: the wrong creature type, and neither tramples.
    """

    def test_it_is_a_four_four_green_rhino_with_trample(self, pool):
        token = pool.get("rhino_4_4_g_trample")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["G"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Rhino"]
        assert list(token.keywords) == ["trample"]
        assert not token.abilities

    def test_the_beast_is_still_a_separate_token(self, pool):
        beast = pool.get("beast_4_4_g")
        assert (beast.power, beast.toughness) == (4, 4)
        assert not beast.keywords
        assert "Rhino" not in beast.subtypes


class TestAgeOfUltronsRobotIsATwoTwoColorlessVillain:
    """Age of Ultron, chapter II: *"For each opponent, you create a 2/2
    colorless Robot Villain artifact creature token."*

    `gnome_1_1_c` is the pool's nearest colorless artifact creature: half the
    body, and not a Villain, which the Doom Prevails deck counts.
    """

    def test_it_is_a_two_two_colorless_robot_villain_artifact(self, pool):
        token = pool.get("robot_villain_2_2_c")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert sorted(token.subtypes) == ["Robot", "Villain"]
        assert not token.keywords and not token.abilities

    def test_the_gnome_is_still_a_separate_token(self, pool):
        gnome = pool.get("gnome_1_1_c")
        assert (gnome.power, gnome.toughness) == (1, 1)
        assert "Villain" not in gnome.subtypes


class TestEndlessRanksVillainIsATwoOneBlackMenace:
    """Endless Ranks of HYDRA: *"For each opponent, you create a 2/1 black
    Villain creature token with menace."*

    `pirate_2_2_b_menace` is the pool's nearest: a point of toughness bigger,
    and a Pirate rather than the Villain the Doom Prevails deck counts.
    """

    def test_it_is_a_two_one_black_villain_with_menace(self, pool):
        token = pool.get("villain_2_1_b_menace")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 1)
        assert sorted(token.colors) == ["B"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Villain"]
        assert list(token.keywords) == ["menace"]
        assert not token.abilities

    def test_the_pirate_is_still_a_separate_token(self, pool):
        pirate = pool.get("pirate_2_2_b_menace")
        assert (pirate.power, pirate.toughness) == (2, 2)
        assert "Villain" not in pirate.subtypes


class TestRedGhostsApeIsAThreeThreeRedVillainWithHaste:
    """Red Ghost, Intangible Genius: *"…create a 3/3 red Ape Villain creature
    token with haste."*

    `ape_3_3_g` is the pool's other 3/3 Ape: green, no haste, and not a
    Villain.
    """

    def test_it_is_a_three_three_red_ape_villain_with_haste(self, pool):
        token = pool.get("ape_villain_3_3_r_haste")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["R"]
        assert list(token.types) == ["Creature"]
        assert sorted(token.subtypes) == ["Ape", "Villain"]
        assert list(token.keywords) == ["haste"]
        assert not token.abilities

    def test_the_green_ape_is_still_a_separate_token(self, pool):
        ape = pool.get("ape_3_3_g")
        assert sorted(ape.colors) == ["G"]
        assert not ape.keywords
        assert "Villain" not in ape.subtypes


class TestInvisibleWomansWallIsAZeroThreeColorlessWall:
    """Invisible Woman: *"…create a 0/3 colorless Wall creature token with
    defender and reach."*

    `spider_1_2_g_reach` is the pool's nearest reach blocker: green, a point
    of power that can deal damage, a toughness short, a Spider, and free to
    attack.
    """

    def test_it_is_a_zero_three_colorless_wall_with_defender_and_reach(self, pool):
        token = pool.get("wall_0_3_c_defender_reach")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (0, 3)
        assert not token.colors
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Wall"]
        assert sorted(token.keywords) == ["defender", "reach"]
        assert not token.abilities

    def test_the_spider_is_still_a_separate_token(self, pool):
        spider = pool.get("spider_1_2_g_reach")
        assert (spider.power, spider.toughness) == (1, 2)
        assert "defender" not in spider.keywords


class TestNamorsMerfolkIsAOneOneBlueMerfolk:
    """Namor, Atlantean King: *"Whenever you cast a noncreature spell, create
    a 1/1 blue Merfolk creature token."*

    `fish_1_1_u` and `tentacle_1_1_u` are the same blue 1/1 body with the wrong
    creature type, which a Merfolk lord or a Merfolk count would not see.
    """

    def test_it_is_a_vanilla_one_one_blue_merfolk(self, pool):
        token = pool.get("merfolk_1_1_u")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["U"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Merfolk"]
        assert not token.keywords and not token.abilities

    def test_the_fish_and_the_tentacle_are_still_separate_tokens(self, pool):
        for near_miss in ("fish_1_1_u", "tentacle_1_1_u"):
            assert "Merfolk" not in pool.get(near_miss).subtypes


class TestTheFantasticarsConstructsAreFourFourHastyFliers:
    """The Fantasticar: *"…create four 4/4 colorless Construct artifact
    creature tokens with flying and haste."*

    `construct_0_0_c_artifact_buff` is the pool's other Construct: a 0/0 that
    grows with artifacts and has no keywords. `dragon_4_4_r_flying` has the
    body but is red, not an artifact, and cannot attack the turn it arrives.
    """

    def test_it_is_a_four_four_colorless_construct_artifact_with_flying_and_haste(self, pool):
        token = pool.get("construct_4_4_c_artifact_flying_haste")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (4, 4)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Construct"]
        assert sorted(token.keywords) == ["flying", "haste"]
        assert not token.abilities

    def test_the_growing_construct_is_still_a_separate_token(self, pool):
        construct = pool.get("construct_0_0_c_artifact_buff")
        assert (construct.power, construct.toughness) == (0, 0)
        assert not construct.keywords


class TestRetrofitterFoundrysConstructIsAPlainFourFour:
    """Retrofitter Foundry: *"{T}, Sacrifice a Thopter: Create a 4/4 colorless
    Construct artifact creature token."*

    `construct_4_4_c_artifact_flying_haste` is the same body with two keywords
    the Foundry never prints, and `construct_0_0_c_artifact_buff` carries a
    static that grows it with every artifact; neither is the vanilla 4/4.
    """

    def test_it_is_a_four_four_colorless_construct_artifact_with_nothing_else(self, pool):
        token = pool.get("construct_4_4_c_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (4, 4)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Construct"]
        assert not token.keywords
        assert not token.abilities

    def test_the_hasty_flier_is_still_a_separate_token(self, pool):
        other = pool.get("construct_4_4_c_artifact_flying_haste")
        assert other is not None
        assert sorted(other.keywords) == ["flying", "haste"]


class TestGolemFoundrysGolemIsAPlainThreeThree:
    """Golem Foundry: *"Create a 3/3 colorless Golem artifact creature token."*

    `gingerbrute_1_1_c` is the pool's other Golem: a 1/1 Food with haste and
    an evasion clause. `construct_4_4_c_artifact_flying_haste` is the nearest
    colorless artifact body, a different creature type with two keywords.
    """

    def test_it_is_a_three_three_colorless_golem_artifact_with_nothing_else(self, pool):
        token = pool.get("golem_3_3_c_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Golem"]
        assert not token.keywords
        assert not token.abilities

    def test_titan_forges_golem_is_the_same_shape_at_nine_nine(self, pool):
        """Titan Forge: *"Create a 9/9 colorless Golem artifact creature token."*"""
        token = pool.get("golem_9_9_c_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (9, 9)
        assert not token.colors
        assert list(token.subtypes) == ["Golem"]
        assert not token.keywords and not token.abilities

    def test_gingerbrute_is_still_a_separate_golem(self, pool):
        gingerbrute = pool.get("gingerbrute_1_1_c")
        assert (gingerbrute.power, gingerbrute.toughness) == (1, 1)


class TestTriplicateTitansGolemsEachCarryOneKeyword:
    """Triplicate Titan: *"create a 3/3 colorless Golem artifact creature token
    with flying, a 3/3 … with vigilance, and a 3/3 … with trample."*

    `golem_3_3_c_artifact` is the body with no keyword, and granting one to it
    with `grant_keyword` would leave the keyword off the token's copiable
    values, so a copy of it would lose it. Each Golem prints exactly one of the
    Titan's three keywords, so none of the three may stand in for another.
    """

    @pytest.mark.parametrize("keyword", ["flying", "vigilance", "trample"])
    def test_it_is_a_three_three_colorless_golem_artifact_with_one_keyword(self, pool, keyword):
        token = pool.get(f"golem_3_3_c_artifact_{keyword}")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Golem"]
        assert list(token.keywords) == [keyword]
        assert not token.abilities

    def test_the_vanilla_golem_is_still_a_separate_token(self, pool):
        assert not pool.get("golem_3_3_c_artifact").keywords


class TestPrismariElementalsAreBlueAndRed:
    """Prismari Pianist, Furygale Flocking, Magma Opus and Resculpt: *"a 1/1
    blue and red Elemental"*, *"two 3/3 blue and red Elemental creature tokens
    with flying"*, *"a 4/4 blue and red Elemental creature token."*

    `elemental_2_2_g` is the pool's other Elemental: green, so a count of blue
    or red permanents would not see it, and the wrong size for all three.
    """

    @pytest.mark.parametrize(
        ("token_id", "size", "keywords"),
        [
            ("elemental_1_1_ur", (1, 1), []),
            ("elemental_3_3_ur_flying", (3, 3), ["flying"]),
            ("elemental_4_4_ur", (4, 4), []),
        ],
    )
    def test_each_is_a_blue_and_red_elemental_of_its_size(self, pool, token_id, size, keywords):
        token = pool.get(token_id)
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == size
        assert sorted(token.colors) == ["R", "U"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Elemental"]
        assert sorted(token.keywords) == keywords
        assert not token.abilities

    def test_the_green_elemental_is_still_a_separate_token(self, pool):
        elemental = pool.get("elemental_2_2_g")
        assert sorted(elemental.colors) == ["G"]


class TestBrudicladsMyrIsATwoOneBluePhyrexianArtifact:
    """Brudiclad, Telchor Engineer: *"create a 2/1 blue Phyrexian Myr artifact
    creature token."*

    `myr_1_1_c` is a colorless 1/1 Myr with no Phyrexian type, so it is the
    wrong body and colour for every token Brudiclad then turns into its copy.
    """

    def test_it_is_a_two_one_blue_phyrexian_myr_artifact(self, pool):
        token = pool.get("phyrexian_myr_2_1_u_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 1)
        assert sorted(token.colors) == ["U"]
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert sorted(token.subtypes) == ["Myr", "Phyrexian"]
        assert not token.keywords and not token.abilities

    def test_the_colorless_myr_is_still_a_separate_token(self, pool):
        myr = pool.get("myr_1_1_c")
        assert (myr.power, myr.toughness) == (1, 1)
        assert not myr.colors


class TestManaformHellkitesDragonIsAnXXHastyFlier:
    """Manaform Hellkite: *"create an X/X red Dragon Illusion creature token
    with flying and haste, where X is the amount of mana spent."*

    `dragon_4_4_r_flying` is a fixed 4/4 with no haste and no Illusion type;
    `shark_x_x_u_flying` is the pool's other X/X flier, blue and a Shark.
    """

    def test_it_is_a_variable_red_dragon_illusion_with_flying_and_haste(self, pool):
        token = pool.get("dragon_illusion_x_x_r_flying_haste")
        assert token is not None and token.is_token and token.is_creature
        assert token.variable_pt
        assert (token.power, token.toughness) == (0, 0)
        assert sorted(token.colors) == ["R"]
        assert list(token.types) == ["Creature"]
        assert sorted(token.subtypes) == ["Dragon", "Illusion"]
        assert sorted(token.keywords) == ["flying", "haste"]
        assert not token.abilities

    def test_the_fixed_dragon_is_still_a_separate_token(self, pool):
        dragon = pool.get("dragon_4_4_r_flying")
        assert not dragon.variable_pt
        assert "haste" not in dragon.keywords


class TestLoreholdsSpiritIsAThreeTwoRedAndWhite:
    """Quintorius, Field Historian, Ceaseless Conflict and the other Lorehold
    cards: *"create a **3/2 red and white** Spirit creature token."*

    `spirit_2_2_w` is the nearest Spirit: a 2/2 and white only. Sizing it up
    with `create_token`'s power and toughness would still leave it mono-white,
    which a "red creature" or "multicolored" count would miss.
    """

    def test_it_is_a_three_two_red_and_white_spirit(self, pool):
        spirit = pool.get("spirit_3_2_rw")
        assert spirit is not None and spirit.is_token and spirit.is_creature
        assert (spirit.power, spirit.toughness) == (3, 2)
        assert sorted(spirit.colors) == ["R", "W"]
        assert list(spirit.types) == ["Creature"]
        assert list(spirit.subtypes) == ["Spirit"]
        assert not spirit.keywords and not spirit.abilities

    def test_the_white_spirit_is_still_a_separate_token(self, pool):
        other = pool.get("spirit_2_2_w")
        assert (other.power, other.toughness) == (2, 2)
        assert sorted(other.colors) == ["W"]


class TestSkyclaveApparitionsIllusionIsAPlainXXBlue:
    """Skyclave Apparition: *"its owner creates an **X/X blue Illusion**
    creature token, where X is the mana value of the exiled card."*

    Written 0/0 with `variable_pt`, like the Shark. `illusion_1_1_u` is a
    printed 1/1, and the pool's X/X Illusion is the red Dragon Illusion with
    flying and haste; neither stands in.
    """

    def test_it_is_a_variable_blue_illusion_with_no_abilities(self, pool):
        token = pool.get("illusion_x_x_u")
        assert token is not None and token.is_token and token.is_creature
        assert token.variable_pt
        assert (token.power, token.toughness) == (0, 0)
        assert sorted(token.colors) == ["U"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Illusion"]
        assert not token.keywords and not token.abilities

    def test_the_printed_illusion_is_still_a_separate_token(self, pool):
        other = pool.get("illusion_1_1_u")
        assert not other.variable_pt
        assert (other.power, other.toughness) == (1, 1)


class TestConvertToSlimesOozeIsAPlainXXGreen:
    """Convert to Slime: *"create an **X/X green Ooze** creature token, where X
    is the total mana value of the permanents destroyed this way."*

    Written 0/0 with `variable_pt`, like the Illusion beside it. The pool's
    only green 0/0 is the green-blue Fractal, which is the wrong colour and
    creature type; it does not stand in.
    """

    def test_it_is_a_variable_green_ooze_with_no_abilities(self, pool):
        token = pool.get("ooze_x_x_g")
        assert token is not None and token.is_token and token.is_creature
        assert token.variable_pt
        assert (token.power, token.toughness) == (0, 0)
        assert sorted(token.colors) == ["G"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Ooze"]
        assert not token.keywords and not token.abilities

    def test_the_fractal_is_still_a_separate_green_blue_token(self, pool):
        other = pool.get("fractal_0_0_gu")
        assert sorted(other.colors) == ["G", "U"]
        assert list(other.subtypes) == ["Fractal"]


class TestAetherRefinerysAetherbornIsAPlainXXBlack:
    """Aether Refinery: *"create an **X/X black Aetherborn** creature token,
    where X is the amount of {E} paid this way."*

    Written 0/0 with `variable_pt`, like the Ooze beside it. The pool's other
    X/X tokens are the wrong colour and creature type; the green Ooze does not
    stand in.
    """

    def test_it_is_a_variable_black_aetherborn_with_no_abilities(self, pool):
        token = pool.get("aetherborn_x_x_b")
        assert token is not None and token.is_token and token.is_creature
        assert token.variable_pt
        assert (token.power, token.toughness) == (0, 0)
        assert sorted(token.colors) == ["B"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Aetherborn"]
        assert not token.keywords and not token.abilities

    def test_the_ooze_is_still_a_separate_green_token(self, pool):
        other = pool.get("ooze_x_x_g")
        assert sorted(other.colors) == ["G"]
        assert list(other.subtypes) == ["Ooze"]


class TestScurryOfGremlinsGremlinIsAPlainOneOneRed:
    """Scurry of Gremlins: *"create two **1/1 red Gremlin** creature tokens."*

    The pool's 1/1 reds are the Goblin, the Hamster and the Warrior; each is
    the wrong creature type, and a Goblin is a different token under 111.4.
    """

    def test_it_is_a_one_one_red_gremlin_with_no_abilities(self, pool):
        token = pool.get("gremlin_1_1_r")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["R"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Gremlin"]
        assert not token.keywords and not token.abilities

    def test_the_hamster_is_still_a_separate_red_token(self, pool):
        other = pool.get("hamster_1_1_r")
        assert list(other.subtypes) == ["Hamster"]


class TestStoneIdolGeneratorsConstructIsASixTwelveTrampler:
    """Stone Idol Generator: *"create a **6/12 colorless Construct artifact**
    creature token with **trample**."*

    The pool's other colourless Constructs are 4/4s and the 0/0 that counts
    artifacts; none is the 6/12, and none has trample alone.
    """

    def test_it_is_a_six_twelve_colourless_artifact_construct_with_trample(self, pool):
        token = pool.get("construct_6_12_c_artifact_trample")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (6, 12)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert list(token.subtypes) == ["Construct"]
        assert "trample" in token.keywords and len(token.keywords) == 1

    def test_the_four_four_construct_is_still_a_separate_token(self, pool):
        other = pool.get("construct_4_4_c_artifact")
        assert (other.power, other.toughness) == (4, 4)
        assert not other.keywords


class TestWitherbloomsPestGainsLifeWhenItDies:
    """Beledros Witherbloom, Blight Mound and the Witherbloom precon: *"create a
    **1/1 black and green Pest** creature token with 'When this token dies, you
    gain 1 life.'"*

    The pool's nearest 1/1 is the green Insect, which has neither the black nor
    the death trigger; a Pest that gains nothing is a weaker card everywhere.
    """

    def test_it_is_a_one_one_black_and_green_pest(self, pool):
        pest = pool.get("pest_1_1_bg")
        assert pest is not None and pest.is_token and pest.is_creature
        assert (pest.power, pest.toughness) == (1, 1)
        assert sorted(pest.colors) == ["B", "G"]
        assert list(pest.types) == ["Creature"]
        assert list(pest.subtypes) == ["Pest"]
        assert not pest.keywords

    def test_it_gains_one_life_when_it_dies(self, pool):
        (ability,) = pool.get("pest_1_1_bg").abilities
        assert ability.kind == "triggered"
        assert ability.trigger.event == "dies" and ability.trigger.source == "self"
        (effect,) = ability.effects
        assert effect["op"] == "gain_life" and effect["player"] == "you"

    def test_the_green_insect_is_still_a_separate_token(self, pool):
        other = pool.get("insect_1_1_g")
        assert (other.power, other.toughness) == (1, 1)
        assert sorted(other.colors) == ["G"]


class TestCreakwoodLiegesWormIsAPlainBlackAndGreen:
    """Creakwood Liege: *"you may create a **1/1 black and green Worm**
    creature token."*

    The Pest is the same body in the same colours and still the wrong token:
    it gains its controller life when it dies, and the Worm does nothing.
    """

    def test_it_is_a_plain_one_one_black_and_green_worm(self, pool):
        worm = pool.get("worm_1_1_bg")
        assert worm is not None and worm.is_token and worm.is_creature
        assert (worm.power, worm.toughness) == (1, 1)
        assert sorted(worm.colors) == ["B", "G"]
        assert list(worm.types) == ["Creature"]
        assert list(worm.subtypes) == ["Worm"]
        assert not worm.keywords and not worm.abilities

    def test_the_pest_is_still_a_separate_token(self, pool):
        other = pool.get("pest_1_1_bg")
        assert list(other.subtypes) == ["Pest"]
        assert other.abilities


class TestOphiomancersSnakeHasDeathtouch:
    """Ophiomancer: *"create a **1/1 black Snake** creature token with
    **deathtouch**."*

    The pool had no Snake at all; the deathtouch is the whole point of the
    card, which turns a 1/1 into a blocker nothing wants to attack into.
    """

    def test_it_is_a_one_one_black_snake_with_deathtouch(self, pool):
        snake = pool.get("snake_1_1_b_deathtouch")
        assert snake is not None and snake.is_token and snake.is_creature
        assert (snake.power, snake.toughness) == (1, 1)
        assert sorted(snake.colors) == ["B"]
        assert list(snake.types) == ["Creature"]
        assert list(snake.subtypes) == ["Snake"]
        assert "deathtouch" in snake.keywords and len(snake.keywords) == 1
        assert not snake.abilities


class TestTrudgeGardensFungusBeastHasTrample:
    """Trudge Garden: *"create a **4/4 green Fungus Beast** creature token with
    **trample**."*

    Two near misses, neither of them it: `beast_4_4_g` is the body without
    trample, and `rhino_4_4_g_trample` is the body and keyword on a Rhino.
    """

    def test_it_is_a_four_four_green_fungus_beast_with_trample(self, pool):
        token = pool.get("fungus_beast_4_4_g_trample")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["G"]
        assert list(token.types) == ["Creature"]
        assert sorted(token.subtypes) == ["Beast", "Fungus"]
        assert "trample" in token.keywords and len(token.keywords) == 1
        assert not token.abilities

    def test_the_plain_beast_is_still_a_separate_token(self, pool):
        other = pool.get("beast_4_4_g")
        assert (other.power, other.toughness) == (4, 4)
        assert "trample" not in other.keywords


class TestAjanisChosensCatIsATwoTwo:
    """Ajani's Chosen: *"create a **2/2 white Cat** creature token."*

    Two near misses, neither of them it: `cat_1_1_w` is the right creature
    type at the wrong size, and `cat_beast_2_2_w` is the right body that is
    also a Beast.
    """

    def test_it_is_a_two_two_white_cat(self, pool):
        cat = pool.get("cat_2_2_w")
        assert cat is not None and cat.is_token and cat.is_creature
        assert (cat.power, cat.toughness) == (2, 2)
        assert sorted(cat.colors) == ["W"]
        assert list(cat.types) == ["Creature"]
        assert list(cat.subtypes) == ["Cat"]
        assert not cat.keywords and not cat.abilities

    def test_the_near_misses_are_still_separate_tokens(self, pool):
        assert (pool.get("cat_1_1_w").power, pool.get("cat_1_1_w").toughness) == (1, 1)
        assert sorted(pool.get("cat_beast_2_2_w").subtypes) == ["Beast", "Cat"]


class TestArchonOfSunsGracesPegasusFlies:
    """Archon of Sun's Grace: *"create a **2/2 white Pegasus** creature token
    with **flying**."*

    The pool had no Pegasus; flying is the point of the body.
    """

    def test_it_is_a_two_two_white_pegasus_with_flying(self, pool):
        token = pool.get("pegasus_2_2_w_flying")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["W"]
        assert list(token.types) == ["Creature"]
        assert list(token.subtypes) == ["Pegasus"]
        assert "flying" in token.keywords and len(token.keywords) == 1
        assert not token.abilities


class TestScrivsContractIsAWhiteAura:
    """Scriv, the Obligator: *"create a **white Aura** enchantment token named
    **Contract** attached to target creature an opponent controls."*

    The near miss is `wicked_role`, the pool's other Aura token: colorless, a
    Role (so 704.5y would bin one Contract for the next Role its controller
    put on the same creature), and a +1/+1 static where the Contract has only
    its attack trigger. Its behaviour is `test_contract_token.py`.
    """

    def test_it_is_a_white_aura_with_one_triggered_ability(self, pool):
        token = pool.get("contract")
        assert token is not None and token.is_token and token.is_aura
        assert token.name == "Contract"
        assert sorted(token.colors) == ["W"]
        assert list(token.types) == ["Enchantment"]
        assert list(token.subtypes) == ["Aura"]
        assert [a.kind for a in token.abilities] == ["triggered"]

    def test_the_wicked_role_is_still_a_separate_token(self, pool):
        role = pool.get("wicked_role")
        assert "Role" in role.subtypes and not role.colors


class TestCurseOfTheSwinesBoar:
    """Curse of the Swine: *"its controller creates a **2/2 green Boar**
    creature token."*

    `elemental_2_2_g` is the same body and colour with the wrong creature
    type, and Boar-typal cards read exactly that one.
    """

    def test_it_is_a_two_two_green_boar(self, pool):
        token = pool.get("boar_2_2_g")
        assert token is not None and token.is_creature and token.is_token
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Boar"]
        assert not token.keywords

    def test_the_green_elemental_is_still_a_separate_token(self, pool):
        other = pool.get("elemental_2_2_g")
        assert other is not None
        assert "Boar" not in other.subtypes


class TestBlightCursesTokens:
    """Three tokens the Blight Curse precon prints, each beside its near miss.

    Flourishing Defenses makes a *1/1 green Elf Warrior*, where the pool's
    other 1/1 Warrior is white and no Elf; Hapatra, Vizier of Poisons makes a
    *1/1 green Snake with deathtouch*, where the pool's Snake is black; and
    Wickersmith's Tools makes a *2/2 colorless Scarecrow artifact creature*.
    Rule 111.4: a token is exactly what its creating effect says.
    """

    def test_the_elf_warrior_is_green_and_both_types(self, pool):
        token = pool.get("elf_warrior_1_1_g")
        assert token is not None and token.is_creature and token.is_token
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["G"]
        assert sorted(token.subtypes) == ["Elf", "Warrior"]
        assert not token.keywords

    def test_the_white_warrior_is_still_a_separate_token(self, pool):
        white = pool.get("warrior_1_1_w")
        assert white is not None and "Elf" not in white.subtypes

    def test_the_green_snake_has_deathtouch(self, pool):
        token = pool.get("snake_1_1_g_deathtouch")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["G"]
        assert "deathtouch" in token.keywords

    def test_the_black_snake_is_still_a_separate_token(self, pool):
        black = pool.get("snake_1_1_b_deathtouch")
        assert black is not None and sorted(black.colors) == ["B"]

    def test_the_scarecrow_is_a_colorless_artifact_creature(self, pool):
        token = pool.get("scarecrow_2_2_c")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (2, 2)
        assert not token.colors
        assert "Artifact" in token.types and "Creature" in token.types
        assert list(token.subtypes) == ["Scarecrow"]


class TestTheDanceOfTheElementsTokens:
    """Dance of the Elements names five tokens the pool lacked, each next to a
    near miss that would have made its card a different card.

    - Crib Swap, Belonging, Springleaf Parade and Abundant Countryside make a
      **1/1** changeling Shapeshifter; the pool's only Shapeshifter was a 3/2.
    - Elemental Spectacle and Omnath, Locus of Rage make a **5/5 red and
      green** Elemental; the nearest was the 4/4 blue and red one.
    - Hoofprints of the Stag makes a **4/4 white** Elemental with flying.
    - Titan of Industry makes a 4/4 green **Rhino Warrior** with no
      keywords; `rhino_4_4_g_trample` is a Rhino alone, with trample.
    - Vernal Sovereign makes a green and white Elemental whose power and
      toughness *are* the number of creatures you control -- a
      characteristic-defining static, not a number fixed when it is made.
    """

    def test_the_small_shapeshifter_is_a_colorless_changeling(self, pool):
        token = pool.get("shapeshifter_1_1_c_changeling")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (1, 1)
        assert not token.colors
        assert "Shapeshifter" in token.subtypes
        assert any(a.text.startswith("Changeling") for a in token.abilities)

    def test_the_large_shapeshifter_is_still_a_separate_token(self, pool):
        other = pool.get("shapeshifter_3_2_c_changeling")
        assert (other.power, other.toughness) == (3, 2)

    def test_the_red_green_elemental_is_a_five_five(self, pool):
        token = pool.get("elemental_5_5_rg")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (5, 5)
        assert sorted(token.colors) == ["G", "R"]
        assert list(token.subtypes) == ["Elemental"]
        assert not token.keywords

    def test_the_white_elemental_flies(self, pool):
        token = pool.get("elemental_4_4_w_flying")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["W"]
        assert list(token.keywords) == ["flying"]

    def test_the_blue_red_elemental_is_still_a_separate_token(self, pool):
        other = pool.get("elemental_4_4_ur")
        assert sorted(other.colors) == ["R", "U"] and not other.keywords

    def test_the_rhino_warrior_has_both_types_and_no_keywords(self, pool):
        token = pool.get("rhino_warrior_4_4_g")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (4, 4)
        assert sorted(token.colors) == ["G"]
        assert sorted(token.subtypes) == ["Rhino", "Warrior"]
        assert not token.keywords

    def test_the_trampling_rhino_is_still_a_separate_token(self, pool):
        other = pool.get("rhino_4_4_g_trample")
        assert "Warrior" not in other.subtypes and "trample" in other.keywords

    def test_the_sovereigns_elemental_counts_your_creatures(self, pool):
        token = pool.get("elemental_x_x_gw_creature_count")
        assert token is not None and token.is_token
        assert sorted(token.colors) == ["G", "W"]
        assert list(token.subtypes) == ["Elemental"]
        assert (token.power, token.toughness) == (0, 0)

    def test_the_sovereigns_elemental_grows_with_your_board(self, builder):
        game = two_seat_board(
            builder,
            mine=["elemental_x_x_gw_creature_count", "grizzly_bears"],
            theirs=["grizzly_bears"],
        )
        token = only_oid(game, "elemental_x_x_gw_creature_count", 0)
        assert pt(game, token) == (2, 2)


class TestTheWorldShaperTokens:
    """Eumidian Hatchery and Scouring Swarm: *"a 1/1 black Insect creature token
    with flying"*; Hammer of Purphoros: *"a 3/3 colorless Golem enchantment
    artifact creature token"*; Titania, Protector of Argoth: *"a 5/3 green
    Elemental creature token"*; Formless Genesis: *"an X/X colorless
    Shapeshifter creature token with changeling and deathtouch"*. Each sits
    beside a near miss that is not it."""

    def test_the_black_insect_is_a_one_one_flier(self, pool):
        token = pool.get("insect_1_1_b_flying")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Insect"]
        assert list(token.keywords) == ["flying"]

    def test_the_green_and_white_insects_are_still_separate_tokens(self, pool):
        assert sorted(pool.get("insect_1_1_g").colors) == ["G"]
        assert not pool.get("insect_1_1_g").keywords
        assert (pool.get("insect_2_1_w_flying").power, pool.get("insect_2_1_w_flying").toughness) == (2, 1)

    def test_the_hammers_golem_is_an_enchantment_too(self, pool):
        token = pool.get("golem_3_3_c_enchantment_artifact")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (3, 3)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature", "Enchantment"]
        assert list(token.subtypes) == ["Golem"]

    def test_the_plain_golem_is_not_an_enchantment(self, pool):
        assert "Enchantment" not in pool.get("golem_3_3_c_artifact").types

    def test_titanias_elemental_is_a_green_five_three(self, pool):
        token = pool.get("elemental_5_3_g")
        assert token is not None and token.is_token
        assert (token.power, token.toughness) == (5, 3)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Elemental"]
        assert not token.keywords

    def test_the_red_green_five_five_is_still_a_separate_token(self, pool):
        other = pool.get("elemental_5_5_rg")
        assert (other.power, other.toughness) == (5, 5)

    def test_the_formless_shapeshifter_has_deathtouch_and_variable_size(self, pool):
        token = pool.get("shapeshifter_x_x_c_changeling_deathtouch")
        assert token is not None and token.is_token
        assert not token.colors
        assert list(token.keywords) == ["deathtouch"]
        assert token.variable_pt
        assert any(a.text.startswith("Changeling") for a in token.abilities)

    def test_the_small_changeling_has_no_deathtouch(self, pool):
        assert "deathtouch" not in pool.get("shapeshifter_1_1_c_changeling").keywords


class TestTheScionsWizardPings:
    """Circle of Power and Transpose: *"a 0/1 black Wizard creature token with
    'Whenever you cast a noncreature spell, this token deals 1 damage to each
    opponent.'"* The pool's other Wizard is a vanilla 2/2 blue, two power and a
    colour away, with no trigger at all."""

    TOKEN = "wizard_0_1_b_noncreature_ping"

    def test_it_is_a_zero_one_black_wizard(self, pool):
        token = pool.get(self.TOKEN)
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (0, 1)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Wizard"]
        assert not token.keywords

    def test_it_carries_the_noncreature_spell_trigger(self, pool):
        (ability,) = pool.get(self.TOKEN).abilities
        assert ability.text.startswith("Whenever you cast a noncreature spell")

    def test_the_blue_wizard_is_still_a_separate_vanilla_token(self, pool):
        other = pool.get("wizard_2_2_u")
        assert (other.power, other.toughness) == (2, 2)
        assert sorted(other.colors) == ["U"]
        assert not other.abilities

    def test_a_noncreature_spell_pings_each_opponent(self, builder):
        """Brainstorm deals no damage of its own, so the point lost is the token's."""
        game = (
            builder(players=2)
            .battlefield(0, [self.TOKEN, "island"])
            .hand(0, ["brainstorm"])
            .build()
        )
        before = game.state.players[1].life
        cast = next(
            a for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "brainstorm"
        )
        game.apply(cast)
        settle_completely(game)
        assert game.state.players[1].life == before - 1


class TestTheMarduSurgeTokens:
    """Four tokens Mardu Surge prints that the pool had only near misses for.

    - Chittering Witch: *"create a 1/1 **black Rat** creature token"* -- the
      pool's 1/1 black is a Vampire, which Vampire-typal cards would count.
    - Release the Dogs: *"Create four 1/1 **white Dog** creature tokens"* --
      `cat_1_1_w` is the right body under the wrong creature type.
    - Tempt with Vengeance: *"1/1 **red** Elemental creature tokens **with
      haste**"* -- `elemental_1_1_ur` is blue and red, and has no haste.
    - Idol of Oblivion: *"Create a **10/10 colorless Eldrazi** creature
      token"* -- the pool's other Eldrazi are a Spawn with a mana ability and a
      flying, vigilant Angel.
    """

    @pytest.mark.parametrize(
        ("token_id", "size", "colors", "subtypes", "kws"),
        [
            ("rat_1_1_b", (1, 1), ["B"], ["Rat"], []),
            ("dog_1_1_w", (1, 1), ["W"], ["Dog"], []),
            ("elemental_1_1_r_haste", (1, 1), ["R"], ["Elemental"], ["haste"]),
            ("eldrazi_10_10_c", (10, 10), [], ["Eldrazi"], []),
        ],
    )
    def test_it_is_exactly_the_printed_token(self, pool, token_id, size, colors, subtypes, kws):
        token = pool.get(token_id)
        assert token is not None
        assert (token.power, token.toughness) == size
        assert sorted(token.colors) == colors
        assert list(token.subtypes) == subtypes
        assert list(token.keywords) == kws
        assert not token.abilities

    @pytest.mark.parametrize(
        ("near_miss", "differs"),
        [
            ("vampire_1_1_b", lambda t: "Rat" not in t.subtypes),
            ("cat_1_1_w", lambda t: "Dog" not in t.subtypes),
            ("elemental_1_1_ur", lambda t: "haste" not in t.keywords and "U" in t.colors),
            ("eldrazi_spawn_0_1_c", lambda t: (t.power, t.toughness) == (0, 1)),
        ],
    )
    def test_the_near_miss_is_still_a_separate_token(self, pool, near_miss, differs):
        other = pool.get(near_miss)
        assert other is not None
        assert differs(other)


class TestTheAbzanArmorTokens:
    """Hornet Nest: *"create that many 1/1 green Insect creature tokens with
    flying and deathtouch"*; Rampart Architect: *"create a 1/3 white Wall
    creature token with defender."* Each sits beside the near miss a card
    would otherwise reach for."""

    def test_the_hornet_is_a_green_one_one_with_flying_and_deathtouch(self, pool):
        token = pool.get("insect_1_1_g_flying_deathtouch")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Insect"]
        assert sorted(token.keywords) == ["deathtouch", "flying"]
        assert not token.abilities

    def test_the_plain_green_insect_has_neither_keyword(self, pool):
        assert not pool.get("insect_1_1_g").keywords

    def test_the_rampart_wall_is_a_white_one_three_defender(self, pool):
        token = pool.get("wall_1_3_w_defender")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 3)
        assert sorted(token.colors) == ["W"]
        assert list(token.subtypes) == ["Wall"]
        assert list(token.keywords) == ["defender"]
        assert not token.abilities

    def test_the_colorless_wall_is_still_zero_power_with_reach(self, pool):
        wall = pool.get("wall_0_3_c_defender_reach")
        assert wall.power == 0 and not wall.colors and "reach" in wall.keywords


class TestTheJumpScareTokens:
    """Sandwurm Convergence: *"create a 5/5 green Wurm creature token."* No
    keyword, which is what separates it from the near miss beside it: the
    red-green Elemental is the pool's other vanilla 5/5."""

    def test_the_wurm_is_a_green_five_five_with_no_keywords(self, pool):
        token = pool.get("wurm_5_5_g")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (5, 5)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Wurm"]
        assert not token.keywords
        assert not token.abilities

    def test_the_red_green_five_five_is_still_an_elemental(self, pool):
        other = pool.get("elemental_5_5_rg")
        assert list(other.subtypes) == ["Elemental"]
        assert sorted(other.colors) == ["G", "R"]


class TestTheMiracleWorkerTokens:
    """Phenomenon Investigators' Believe mode: *"create a 2/2 black Horror
    enchantment creature token."* The enchantment type is the load-bearing
    part: the precon counts and returns enchantments, so the pool's 2/2 black
    Zombie of the same size is not a stand-in."""

    def test_the_horror_is_a_black_two_two_enchantment_creature(self, pool):
        token = pool.get("horror_2_2_b_enchantment")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Horror"]
        assert "Enchantment" in token.types
        assert not token.keywords
        assert not token.abilities

    def test_the_glimmer_is_a_white_one_one_enchantment_creature(self, pool):
        """Soaring Lightbringer: *"Whenever you attack a player, create a 1/1
        white Glimmer enchantment creature token that's tapped and attacking
        that player."* Its flying comes from the Lightbringer's own static
        ("other enchantment creatures you control have flying"), so the token
        itself prints no keyword."""
        token = pool.get("glimmer_1_1_w_enchantment")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["W"]
        assert list(token.subtypes) == ["Glimmer"]
        assert "Enchantment" in token.types
        assert not token.keywords
        assert not token.abilities

    def test_the_black_two_two_zombie_is_still_not_an_enchantment(self, pool):
        other = pool.get("zombie_2_2_b")
        assert list(other.subtypes) == ["Zombie"]
        assert "Enchantment" not in other.types


class TestTheAnimatedArmyTokens:
    """Esika's Chariot: *"When Esika's Chariot enters, create two 2/2 green Cat
    creature tokens."* The pool's 2/2 Cat is white, and a deck that counts
    green permanents or green creatures sees the difference (111.4)."""

    def test_the_cat_is_a_green_two_two(self, pool):
        token = pool.get("cat_2_2_g")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Cat"]
        assert not token.keywords
        assert not token.abilities

    def test_the_white_cat_is_still_white(self, pool):
        other = pool.get("cat_2_2_w")
        assert sorted(other.colors) == ["W"]
        assert list(other.subtypes) == ["Cat"]

    def test_the_hamster_is_a_red_one_one(self, pool):
        """Rolling Hamsphere: *"create three 1/1 red Hamster creature tokens,
        then it deals X damage ... where X is the number of Hamsters you
        control."* The subtype is the load-bearing part: the Vehicle counts
        Hamsters, so the pool's 1/1 red Goblin is not a stand-in."""
        token = pool.get("hamster_1_1_r")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["R"]
        assert list(token.subtypes) == ["Hamster"]
        assert not token.keywords
        assert not token.abilities


class TestTheFamilyMattersTokens:
    """Three tokens the Family Matters precon names that the pool had only as
    near misses (111.4)."""

    def test_the_phyrexian_golem_is_a_colorless_three_three_artifact(self, pool):
        """Blade Splicer: *"create a 3/3 colorless Phyrexian Golem artifact
        creature token."* The Phyrexian type is the load-bearing part: a card
        that counts Phyrexians sees it, and the plain Golem is not one."""
        token = pool.get("phyrexian_golem_3_3_c_artifact")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert not token.colors
        assert sorted(token.types) == ["Artifact", "Creature"]
        assert sorted(token.subtypes) == ["Golem", "Phyrexian"]
        assert not token.keywords
        assert not token.abilities

    def test_the_plain_golem_is_still_not_phyrexian(self, pool):
        other = pool.get("golem_3_3_c_artifact")
        assert list(other.subtypes) == ["Golem"]

    def test_the_rabbit_is_a_white_one_one(self, pool):
        """Jacked Rabbit: *"create a number of 1/1 white Rabbit creature
        tokens."* Bloomburrow counts Rabbits, so the pool's 1/1 white Cat
        and Dog are not stand-ins."""
        token = pool.get("rabbit_1_1_w")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["W"]
        assert list(token.subtypes) == ["Rabbit"]
        assert not token.keywords
        assert not token.abilities

    def test_the_storm_crow_is_a_blue_one_two_flier(self, pool):
        """Murmuration: *"create a 1/2 blue Bird creature token with flying
        named Storm Crow."* Its toughness and name are what the pool's 2/2
        blue Bird and 1/1 vigilant Bird lack."""
        token = pool.get("storm_crow_1_2_u_flying")
        assert token is not None and token.is_token and token.is_creature
        assert token.name == "Storm Crow"
        assert (token.power, token.toughness) == (1, 2)
        assert sorted(token.colors) == ["U"]
        assert list(token.subtypes) == ["Bird"]
        assert list(token.keywords) == ["flying"]
        assert not token.abilities

    def test_the_two_two_blue_bird_is_still_a_separate_token(self, pool):
        other = pool.get("bird_2_2_u_flying")
        assert (other.power, other.toughness) == (2, 2)


class TestFishersTalentsSharkIsAPlainThreeThree:
    """Fisher's Talent, level 2: *"If you would create a Fish token, create a
    **3/3 blue Shark creature token** instead."*

    `shark_x_x_u_flying` is the near miss: a blue Shark, but X/X with flying.
    The level-3 line replaces this Shark with the 8/8 Octopus, so the subtype
    is as load-bearing as the body.
    """

    TOKEN = "shark_3_3_u"

    def test_it_is_a_vanilla_three_three_blue_shark(self, pool):
        token = pool.get(self.TOKEN)
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["U"]
        assert list(token.subtypes) == ["Shark"]
        assert not token.keywords
        assert not token.abilities

    def test_the_flying_x_x_shark_is_still_a_separate_token(self, pool):
        other = pool.get("shark_x_x_u_flying")
        assert other is not None
        assert list(other.keywords) == ["flying"]


class TestSquirreledAwayTokens:
    """Squirreled Away's tokens, each pinned beside its nearest near miss
    (111.4: a token is exactly what its creating effect says).

    - *"Create a 1/1 green Squirrel creature token."* (Chatterstorm,
      Chitterspitter, Squirrel Nest and most of the deck). The pool's 1/1
      green tokens are other creature types, and Squirrel lords count them.
    - *"create a 3/3 green Raccoon creature token"* (Gourmand's Talent, level
      2); the pool's 3/3 green Badger and Beast are the near misses.
    - *"Create a 2/2 blue Shapeshifter creature token with changeling."*
      (Maskwood Nexus); the 1/1 colorless changeling is the near miss.
    """

    def test_the_squirrel_is_a_green_one_one(self, pool):
        token = pool.get("squirrel_1_1_g")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Squirrel"]
        assert not token.keywords
        assert not token.abilities

    def test_the_raccoon_is_a_vanilla_green_three_three(self, pool):
        token = pool.get("raccoon_3_3_g")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Raccoon"]
        assert not token.abilities

    def test_the_badger_is_still_a_separate_three_three(self, pool):
        other = pool.get("badger_3_3_g")
        assert list(other.subtypes) == ["Badger"]

    def test_the_blue_shapeshifter_is_a_two_two_changeling(self, pool):
        token = pool.get("shapeshifter_2_2_u_changeling")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["U"]
        assert "Shapeshifter" in token.subtypes
        near = pool.get("shapeshifter_1_1_c_changeling")
        assert [a.text for a in token.abilities] == [a.text for a in near.abilities]

    def test_the_colorless_changeling_is_still_a_one_one(self, pool):
        other = pool.get("shapeshifter_1_1_c_changeling")
        assert (other.power, other.toughness) == (1, 1)
        assert not other.colors


class TestGarruksWolfLoadsAGarrukOnDeath:
    """Garruk, Cursed Huntsman, 0: *"Create two 2/2 black and green Wolf
    creature tokens with 'When this token dies, put a loyalty counter on each
    Garruk you control.'"* The pool had no Wolf; the 2/2 black Zombie and
    green Boar are the near misses, each the wrong colour pair and with no
    dies trigger."""

    TOKEN = "wolf_2_2_bg_garruk_loyalty"

    def test_it_is_a_black_and_green_two_two_wolf(self, pool):
        token = pool.get(self.TOKEN)
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["B", "G"]
        assert list(token.subtypes) == ["Wolf"]

    def test_its_death_puts_loyalty_on_each_garruk(self, pool):
        (ability,) = pool.get(self.TOKEN).abilities
        assert ability.text == "When this token dies, put a loyalty counter on each Garruk you control."
        (effect,) = ability.effects
        assert effect["op"] == "add_counters"
        assert effect["counter"] == "loyalty"
        assert effect["objects"]["subtypes"] == ["Garruk"]
        assert effect["objects"]["count"] == "all"

    def test_the_two_two_black_zombie_is_still_a_separate_token(self, pool):
        other = pool.get("zombie_2_2_b")
        assert list(other.subtypes) == ["Zombie"]

    def test_the_plain_green_wolf_is_a_vanilla_two_two(self, pool):
        """Wolfwillow Haven: *"Create a 2/2 green Wolf creature token."* The
        Garruk Wolf is the near miss: black and green, with a dies trigger."""
        token = pool.get("wolf_2_2_g")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Wolf"]
        assert not token.abilities


class TestTheGraveyardOverdriveTokens:
    """Izoni and Grist make a 1/1 black and green Insect, Garruk, Apex Predator
    a 3/3 black Beast with deathtouch, and Disa and Tarmogoyf Nest a Tarmogoyf.
    The near misses are the green Insect, the green Beast and, for the
    Tarmogoyf, nothing: no other token counts card types in graveyards."""

    def test_the_insect_is_a_black_and_green_one_one(self, pool):
        token = pool.get("insect_1_1_bg")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["B", "G"]
        assert list(token.subtypes) == ["Insect"]
        assert not token.keywords and not token.abilities

    def test_the_green_insect_is_still_mono_green(self, pool):
        assert sorted(pool.get("insect_1_1_g").colors) == ["G"]

    def test_the_beast_is_a_black_three_three_with_deathtouch(self, pool):
        token = pool.get("beast_3_3_b_deathtouch")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (3, 3)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Beast"]
        assert set(token.keywords) == {"deathtouch"}

    def test_the_green_beast_is_still_vanilla(self, pool):
        token = pool.get("beast_3_3_g")
        assert sorted(token.colors) == ["G"] and not token.keywords

    def test_the_tarmogoyf_is_a_named_green_lhurgoyf_costing_two(self, pool):
        token = pool.get("tarmogoyf_0_1_g")
        assert token is not None and token.is_token and token.is_creature
        assert token.name == "Tarmogoyf"
        assert token.mana_value == 2
        assert (token.power, token.toughness) == (0, 1)
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Lhurgoyf"]

    def test_the_tarmogoyf_counts_card_types_in_all_graveyards(self, pool):
        (ability,) = pool.get("tarmogoyf_0_1_g").abilities
        types_in_graveyards = {
            "distinct": {"objects": {"controller": "any", "zone": "graveyard"}, "of": "card_type"}
        }
        assert ability.static["effect"] == "set_pt"
        assert ability.static["affects"] == {"self_only": True}
        assert ability.static["power"] == types_in_graveyards
        assert ability.static["toughness"] == {"sum": [types_in_graveyards, {"const": 1}]}


class TestTheTrickyTerrainTokens:
    """Dark Depths makes Marit Lage, Hydra Broodmaster X/X green Hydras and
    Desert Warfare 1/1 red, green and white Sand Warriors, each pinned beside
    its nearest near miss (111.4: a token is exactly what its creating effect
    says). The near misses are the colorless indestructible Vibranium, the
    green X/X Ooze and the one-colour 1/1 Warriors."""

    def test_marit_lage_is_a_legendary_black_twenty_twenty(self, pool):
        token = pool.get("marit_lage_20_20_b_flying_indestructible")
        assert token is not None and token.is_token and token.is_creature
        assert token.name == "Marit Lage"
        assert sorted(token.supertypes) == ["Legendary"]
        assert (token.power, token.toughness) == (20, 20)
        assert sorted(token.colors) == ["B"]
        assert list(token.subtypes) == ["Avatar"]
        assert set(token.keywords) == {"flying", "indestructible"}

    def test_the_hydra_is_a_green_x_x(self, pool):
        token = pool.get("hydra_x_x_g")
        assert token is not None and token.is_token and token.is_creature
        assert sorted(token.colors) == ["G"]
        assert list(token.subtypes) == ["Hydra"]
        assert not token.keywords and not token.abilities

    def test_the_ooze_is_still_a_separate_x_x(self, pool):
        assert list(pool.get("ooze_x_x_g").subtypes) == ["Ooze"]

    def test_the_sand_warrior_is_a_three_colour_one_one(self, pool):
        token = pool.get("sand_warrior_1_1_rgw")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert sorted(token.colors) == ["G", "R", "W"]
        assert sorted(token.subtypes) == ["Sand", "Warrior"]
        assert not token.keywords and not token.abilities

    def test_the_red_warrior_is_still_mono_red(self, pool):
        assert sorted(pool.get("warrior_1_1_r").colors) == ["R"]


class TestTheEldraziIncursionTokens:
    """Spawnbed Protector, Sifter of Skulls, Warping Wail and the rest of
    Eldrazi Incursion: *"create a **1/1** colorless Eldrazi **Scion** creature
    token with 'Sacrifice this token: Add {C}.'"*; Ugin, the Ineffable: *"create
    a **2/2 colorless** Spirit creature token."*

    The Scion's near miss is the Spawn: the same mana ability on a 0/1, so it
    has no power and is not a Scion. Ugin's near misses are the 1/1 colorless
    Spirit and the 2/2 white one, each right in one of the two ways.
    """

    def test_the_scion_is_a_colorless_one_one_that_makes_colorless_mana(self, pool):
        token = pool.get("eldrazi_scion_1_1_c")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert not token.colors
        assert sorted(token.subtypes) == ["Eldrazi", "Scion"]
        (ability,) = token.abilities
        assert ability.is_mana_ability
        assert list(ability.effects) == [{"op": "add_mana", "mana": "{C}"}]

    def test_the_spawn_is_still_a_separate_zero_one(self, pool):
        spawn = pool.get("eldrazi_spawn_0_1_c")
        assert (spawn.power, spawn.toughness) == (0, 1)
        assert sorted(spawn.subtypes) == ["Eldrazi", "Spawn"]

    def test_ugins_spirit_is_a_colorless_two_two(self, pool):
        token = pool.get("spirit_2_2_c")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (2, 2)
        assert not token.colors
        assert list(token.subtypes) == ["Spirit"]
        assert not token.keywords and not token.abilities

    def test_the_other_spirits_are_still_separate(self, pool):
        small = pool.get("spirit_1_1_c")
        assert (small.power, small.toughness) == (1, 1) and not small.colors
        assert sorted(pool.get("spirit_2_2_w").colors) == ["W"]


class TestYoungPyromancersElementalIsMonoRed:
    """Young Pyromancer: *"create a 1/1 **red** Elemental creature token."*

    Its near misses are `elemental_1_1_ur`, the same body in blue and red, and
    `elemental_1_1_r_haste`, the same body and colour with haste.
    """

    def test_it_is_a_vanilla_red_one_one_elemental(self, pool):
        token = pool.get("elemental_1_1_r")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert list(token.colors) == ["R"]
        assert list(token.subtypes) == ["Elemental"]
        assert not token.keywords and not token.abilities

    def test_the_near_misses_are_still_separate(self, pool):
        assert sorted(pool.get("elemental_1_1_ur").colors) == ["R", "U"]
        assert list(pool.get("elemental_1_1_r_haste").keywords) == ["haste"]


class TestTheThunderJunctionDragonElementalHasProwess:
    """Elemental Eruption and Eris, Roar of the Storm: *"create a 4/4 red
    **Dragon Elemental** creature token with flying and **prowess**."*

    Its near miss is `dragon_4_4_r_flying`: the same body and colour, but no
    Elemental type and no prowess trigger.
    """

    def test_it_is_a_flying_red_dragon_elemental_with_prowess(self, pool):
        token = pool.get("dragon_elemental_4_4_r_flying_prowess")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (4, 4)
        assert list(token.colors) == ["R"]
        assert sorted(token.subtypes) == ["Dragon", "Elemental"]
        assert list(token.keywords) == ["flying"]
        (prowess,) = token.abilities
        assert prowess.text == "Prowess"

    def test_the_plain_dragon_is_still_separate(self, pool):
        dragon = pool.get("dragon_4_4_r_flying")
        assert list(dragon.subtypes) == ["Dragon"] and not dragon.abilities


class TestMurmuringMysticsBirdIllusion:
    """Murmuring Mystic: *"create a 1/1 blue **Bird Illusion** creature token
    with flying."*

    Its near misses are `illusion_1_1_u_flying`, with no Bird type, and
    `bird_1_1_u_flying_vigilance`, with no Illusion type and vigilance.
    """

    def test_it_is_a_flying_blue_bird_illusion(self, pool):
        token = pool.get("bird_illusion_1_1_u_flying")
        assert token is not None and token.is_token and token.is_creature
        assert (token.power, token.toughness) == (1, 1)
        assert list(token.colors) == ["U"]
        assert sorted(token.subtypes) == ["Bird", "Illusion"]
        assert list(token.keywords) == ["flying"]
        assert not token.abilities

    def test_the_near_misses_are_still_separate(self, pool):
        assert list(pool.get("illusion_1_1_u_flying").subtypes) == ["Illusion"]
        assert "vigilance" in pool.get("bird_1_1_u_flying_vigilance").keywords
