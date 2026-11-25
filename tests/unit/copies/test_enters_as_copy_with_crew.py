"""The as-enters copy that is a Vehicle with crew.

    "You may have this Vehicle enter as a copy of a creature an opponent
    controls, **except it's a Vehicle artifact with crew 3** and it loses all
    other card types."                                    -- Imposter Mech

707.9b: the exception is a copiable value. It is the shapes the Effigy
already uses (`test_enters_as_copy_add_abilities.py`): ``set_types`` for
"loses all other card types", ``add_subtypes`` for the Vehicle, and the crew
written once under ``grantable_abilities`` and named in
``except_.add_abilities``. The copied creature's creature types go with the
Creature type it no longer has (205.1b), and its size stays, because a
Vehicle's printed size is the one it has when crewed (301.7).

The new part is the verifier's: the keyword is printed unquoted, so the
residual gate counts each "with crew N" as one more `add_abilities` position,
and that position must be a crew ability (known by its cost, ADR 0032)
whose text is "Crew N". A copy that grants a different crew, or none,
cannot claim the sentence.
"""

from __future__ import annotations

import dataclasses

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.engine.characteristics import chars
from tests.conftest import only_oid
from tests.unit.copies.test_enters_as_copy import cast, name_of
from tests.unit.copies.test_enters_as_copy_set_types import position, types_of

MECH = "t_eaxc_mech"
BEAR = "t_bear"  # 2/2 Creature - Bear, no abilities

LINE = (
    "You may have this Vehicle enter as a copy of a creature an opponent "
    "controls, except it's a Vehicle artifact with crew 3 and it loses all "
    "other card types"
)


def face(game, oid: int):
    return game.state.card_of(game.state.objects[oid])


class TestTheCopyIsAVehicleWithCrew:
    def test_it_is_the_creature_as_a_vehicle_artifact(self, builder):
        game = position(builder, MECH, mine=("island",))
        cast(game, MECH)
        oid = only_oid(game, MECH, 0)
        assert name_of(game, oid) == "Test Bear"
        assert types_of(game, oid) == {"Artifact"}
        assert "Vehicle" in chars(game.state, oid).subtypes
        assert "Bear" not in chars(game.state, oid).subtypes

    def test_it_has_crew_3(self, builder):
        game = position(builder, MECH, mine=("island",))
        cast(game, MECH)
        oid = only_oid(game, MECH, 0)
        crews = [a for a in face(game, oid).abilities if a.is_crew]
        assert [a.text for a in crews] == ["Crew 3"]

    def test_declining_the_copy_leaves_the_printed_vehicle(self, builder):
        game = position(builder, MECH, mine=("island",))
        cast(game, MECH, say_yes=False)
        oid = only_oid(game, MECH, 0)
        assert name_of(game, oid) == "Test Imposter Mech"
        assert [a.text for a in face(game, oid).abilities] == ["Crew 3"]


class TestTheVerifierWantsThatCrew:
    def _with_crew(self, registry, text: str, power: int):
        card = registry.get(MECH)
        ability = card.grantable_abilities[0]
        cost = dataclasses.replace(
            ability.cost,
            tap_permanents={**ability.cost.tap_permanents, "total_power": power},
        )
        crew = dataclasses.replace(ability, text=text, cost=cost)
        return dataclasses.replace(card, grantable_abilities=(crew,))

    def test_the_sentence_is_claimed_with_crew_3(self, registry):
        assert _covered(registry.get(MECH), LINE)

    def test_a_copy_granting_another_crew_cannot_claim_it(self, registry):
        assert not _covered(self._with_crew(registry, "Crew 2", 2), LINE)

    def test_a_copy_granting_nothing_cannot_claim_it(self, registry):
        card = registry.get(MECH)
        replacement = {**card.replacements[0]}
        replacement["except_"] = {
            k: v for k, v in replacement["except_"].items() if k != "add_abilities"
        }
        assert not _covered(dataclasses.replace(card, replacements=(replacement,)), LINE)
