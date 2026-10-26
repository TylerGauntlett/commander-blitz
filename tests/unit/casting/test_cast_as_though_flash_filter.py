""""You may cast artifact spells as though they had flash." -- Shimmer Myr.

The spell filter on the player-wide `cast_as_though_flash` static. 702.8a's
flash is a permission about *a spell*; Shimmer Myr grants it to the artifact
spells its controller casts and to nothing else, and Yeva, Nature's Herald
narrows it twice ("green creature spells"). Without the filter the only
`cast_as_though_flash` there was is Vedalken Orrery's, which reaches every spell
-- a strictly better card than the printed Myr, and the reason the loader
refused a filter on it until one was read.

The filter is `affects_spells`, matched by `player_casts_as_though_flash`
against the face being cast with `_matches_printed`, exactly as Oath of Nissa's
`spend_mana_as_any_color` filter is. `casting._timing_ok` is the one seat that
asks it, so every zone a spell is cast from is covered by the same read. Asked
without a card the filtered permission does not answer: "this player may cast
spells at instant speed" is false while a sorcery still waits for its window.

The near miss is `grant_flash_permission`, which carries `types` but is a
one-shot permission with a duration; this one lasts exactly as long as its
source is on the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_casts_as_though_flash

MYR = "t_myr_permission"  # you may cast artifact spells as though they had flash
HERALD = "t_green_herald"  # you may cast green creature spells ...
TRINKET = "t_filter_trinket"  # {1} artifact
GOLEM = "t_filter_golem"  # {1} artifact creature
BEAR = "t_filter_bear"  # {G} green creature
GROWTH = "t_filter_growth"  # {G} green sorcery
SORCERY = "t_sorcery"  # {R} red sorcery
BOAR = "t_flash_sorcery_target"  # {R} red creature


def position(builder, *source: str, active: int = 1, hand0=(TRINKET,), hand1=(TRINKET,)):
    """Player 0 controls the permission; by default it is player 1's turn.

    Off-turn is the only place a timing permission can show: on its own turn
    in a main phase, player 0 could cast everything anyway.
    """
    lands = ["mountain", "mountain", "forest", "forest"]
    return (
        builder(players=2)
        .battlefield(0, lands + list(source))
        .battlefield(1, lands)
        .hand(0, list(hand0))
        .hand(1, list(hand1))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(active)
        .build(advance=False)
    )


def can_cast(game, pid: int, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in legality._priority_actions(game.state, pid)
    )


class TestTheBaseline:
    def test_without_the_permission_an_artifact_waits_for_its_window(self, builder):
        game = position(builder)
        assert not can_cast(game, 0, TRINKET)


class TestTheArtifactFilter:
    """Shimmer Myr: the permission reaches artifact spells and nothing else."""

    @pytest.mark.parametrize("card", [TRINKET, GOLEM])
    def test_an_artifact_spell_is_castable_off_turn(self, builder, card):
        """An artifact creature is an artifact spell too -- `types` is a subset test."""
        game = position(builder, MYR, hand0=(card,))
        assert can_cast(game, 0, card)

    @pytest.mark.parametrize("card", [SORCERY, BOAR])
    def test_a_non_artifact_spell_is_not(self, builder, card):
        game = position(builder, MYR, hand0=(card,))
        assert not can_cast(game, 0, card)

    def test_it_is_scoped_to_its_controller(self, builder):
        game = position(builder, MYR, active=0)
        assert not can_cast(game, 1, TRINKET)

    def test_without_the_source_the_window_returns(self, builder):
        game = position(builder, MYR)
        myr = next(o for o in game.state.battlefield if game.state.objects[o].def_id == MYR)
        game.state.battlefield.remove(myr)
        game.state.bump_chars()
        assert not can_cast(game, 0, TRINKET)


class TestATwoKeyFilter:
    """Yeva's shape: "green creature spells" is a conjunction of both keys."""

    def test_a_green_creature_is_castable(self, builder):
        game = position(builder, HERALD, hand0=(BEAR,))
        assert can_cast(game, 0, BEAR)

    def test_a_green_sorcery_is_not(self, builder):
        game = position(builder, HERALD, hand0=(GROWTH,))
        assert not can_cast(game, 0, GROWTH)

    def test_a_red_creature_is_not(self, builder):
        game = position(builder, HERALD, hand0=(BOAR,))
        assert not can_cast(game, 0, BOAR)


class TestTheReader:
    def test_it_answers_for_a_matching_face(self, builder, registry):
        game = position(builder, MYR)
        assert player_casts_as_though_flash(game.state, 0, registry.get(TRINKET))
        assert not player_casts_as_though_flash(game.state, 0, registry.get(SORCERY))

    def test_without_a_card_a_filtered_permission_does_not_answer(self, builder):
        game = position(builder, MYR)
        assert not player_casts_as_though_flash(game.state, 0)


class TestTheLoader:
    def card(self, **extra):
        return {
            "id": "t_probe_myr",
            "name": "Probe Myr",
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "You may cast artifact spells as though they had flash.",
                    "effect": "cast_as_though_flash",
                    "affects_player": "you",
                    **extra,
                }
            ],
        }

    def test_a_spell_filter_loads(self):
        compiled = compile_card(
            CardModel.model_validate(self.card(affects_spells={"types": ["Artifact"]}))
        )
        assert compiled.abilities[0].static["affects_spells"] == {"types": ["Artifact"]}

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError, match="empty filter"):
            compile_card(CardModel.model_validate(self.card(affects_spells={})))

    @pytest.mark.parametrize("key", ["controller", "tapped"])
    def test_a_key_a_spell_cannot_answer_is_refused(self, key):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(CardModel.model_validate(self.card(affects_spells={key: "you"})))

    def test_affects_is_still_refused(self):
        """`affects` picks out permanents; a spell in hand is not one."""
        with pytest.raises(DslError, match="cast_as_though_flash"):
            compile_card(CardModel.model_validate(self.card(affects={"types": ["Artifact"]})))
