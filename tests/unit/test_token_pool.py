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

    def test_no_other_token_answers_to_moogle(self, pool):
        """"Put a +1/+1 counter on each Moogle you control" must count one.

        If a second Moogle token ever enters the pool this test should be
        updated deliberately rather than deleted — the card's last clause reads
        the subtype off the battlefield, so the set of things that answer to it
        is part of the card's behaviour.
        """
        moogles = [c.id for c in pool if "Moogle" in c.subtypes]
        assert moogles == ["moogle_1_2_w_lifelink"]


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
