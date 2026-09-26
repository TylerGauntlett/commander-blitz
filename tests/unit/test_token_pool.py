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

from automtg.cards.registry import CardRegistry, authored_card_paths


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
