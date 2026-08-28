"""A triggered ability chooses its modes as it goes on the stack -- 603.3d.

    Oltec Matterweaver -- "Whenever you cast a creature spell, choose one --
    * Create a 1/1 colorless Gnome artifact creature token.
    * Create a token that's a copy of **target** artifact token you control."

Rule 603.3d puts a trigger's modes *and* its targets at the one moment the
ability is put on the stack, applying 601.2b then 601.2c in that order. The
engine had only half of it: targets were declared there, but `op_choose_mode`
asked which mode as the ability **resolved**, which is after the only moment a
target could have been named. So a mode could not own a target, and the loader
said so outright -- "an ability's modes are chosen as it resolves, which is
after the moment its targets were declared".

Every way of writing this card without a mode-owned target is a *different
card*, and the second bullet is not the half that breaks:

* a plain ability-level target for the copy fizzles the **whole trigger**
  whenever you control no artifact token (`filter_legal` reports `any_legal`
  False), so the first creature you cast makes no Gnome at all -- and the Gnome
  is itself the first artifact token, so that is the normal case, not an edge;
* `optional: true` survives that, but lets the copy mode be taken with nothing
  targeted, which is a mode that silently does nothing;
* a `chooser: "controller"` selector inside the mode resolves at the right time
  and is not targeting: no `became_target` event, no ward or shroud check, and
  no fizzle when the chosen token is gone.

So the claims worth pinning, each of which is one of those wrong cards if it
breaks:

* **601.2b: a mode with no legal target is not offered.** With no artifact
  token on the battlefield the Gnome bullet is still available and still makes
  its Gnome -- the case all three workarounds get wrong;
* the target a mode declares is **its own**, chosen as the ability goes on the
  stack, and `became_target` fires there (603.2d);
* choosing the other mode declares **no** target at all, so removing the token
  in response cannot fizzle it;
* 608.2b's re-check on resolution knows **which mode was chosen** -- it splits
  the stored refs by `Ability.specs_for_modes`, the ability-level twin of what
  a modal spell already had.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from automtg.engine.stack import push_triggered_ability, resolve_top
from automtg.engine.structs import TriggerInstance
from automtg.engine.zones import move_object

WEAVER = "t_matterweaver"
GNOME = "gnome_1_1_c"
GNOME_MODE = "Create a 1/1 colorless Gnome artifact creature token."
COPY_MODE = "Create a token that's a copy of target artifact token you control."


def board(builder, tokens: tuple[str, ...] = ()) -> tuple:
    """The Matterweaver on the battlefield, and whatever tokens the test wants.

    Returns ``(game, source_oid, token_oids)``. The tokens are made with the
    `create_token` primitive rather than placed by the builder because
    ``is_token`` is the whole of the second mode's selector -- a card of the
    same name placed on the battlefield is not a token and must not be offered.
    """
    game = (
        builder(players=2)
        .battlefield(0, [WEAVER] + ["forest"] * 6)
        .library(0, ["forest"] * 20)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    made: list[int] = []
    for token in tokens:
        made.extend(create_token(game.state, token, 0))
    source = next(
        obj.oid for obj in game.state.battlefield_objects(0) if obj.def_id == WEAVER
    )
    return game, source, made


def push(game, source: int, answers: tuple[str, ...] = (), *, asked: list | None = None):
    """Put the trigger on the stack, answering its questions by label.

    Driven by hand rather than through a cast, for the reason
    `test_orphaned_trigger` does the same: the questions are asked *inside*
    `push_triggered_ability`, and a full game with nothing to respond with
    auto-passes straight through the resolution afterwards, leaving no moment
    to look at the stack item in.

    ``asked`` collects each decision, so a test can claim what was *not* asked.
    """
    trig = TriggerInstance(
        source_oid=source, ability_index=0, controller=0, def_id=WEAVER
    )
    generator = push_triggered_ability(game.state, trig)
    remaining = list(answers)
    send: list[int] | None = None
    while True:
        try:
            decision = generator.send(send)
        except StopIteration as stop:
            assert not remaining, f"never asked about {remaining}"
            return stop.value
        if asked is not None:
            asked.append(decision)
        labels = [option.label for option in decision.options]
        assert remaining, f"unexpected question: {labels}"
        want = remaining.pop(0)
        assert want in labels, f"{want!r} not offered; got {labels}"
        send = [labels.index(want)]


def resolve(game) -> None:
    """Resolve the top of the stack, taking the first answer to anything."""
    generator = resolve_top(game.state)
    send: list[int] | None = None
    while True:
        try:
            generator.send(send)
        except StopIteration:
            return
        send = [0]


def permanents(game, pid: int = 0) -> list[str]:
    """What is on the battlefield, minus the lands that paid for none of it."""
    return sorted(
        obj.def_id for obj in game.state.battlefield_objects(pid) if obj.def_id != "forest"
    )


class TestAModeWithNoLegalTargetIsNotOffered:
    """601.2b, and the whole reason the capability exists.

    The Gnome is itself the first artifact token, so "you control no artifact
    token" is the state of the board on the *first* creature you cast in every
    game this card is played in.
    """

    def test_the_gnome_mode_is_still_taken_with_no_artifact_token(self, builder):
        game, source, _ = board(builder)
        asked: list = []
        item = push(game, source, asked=asked)
        assert item.modes == (0,), "the only mode with a legal target"
        assert asked == [], "one legal mode is not a question worth asking"

    def test_and_it_still_makes_its_gnome(self, builder):
        """An unconditional ability-level target loses this: `filter_legal`
        answers `any_legal` False and the whole trigger fizzles."""
        game, source, _ = board(builder)
        push(game, source)
        resolve(game)
        assert permanents(game) == [GNOME, WEAVER]

    def test_both_modes_are_offered_once_a_token_is_there(self, builder):
        """The boundary the test above sits on: one artifact token is the
        difference between a forced mode and a real choice."""
        game, source, _ = board(builder, ("treasure_token",))
        asked: list = []
        push(game, source, (GNOME_MODE,), asked=asked)
        assert [option.label for option in asked[0].options] == [GNOME_MODE, COPY_MODE]
        assert asked[0].kind is DecisionKind.CHOOSE_MODE
        assert asked[0].player == 0, "the trigger's controller chooses"

    def test_a_token_an_opponent_controls_does_not_open_the_mode(self, builder):
        """"…artifact token **you control**". The selector is half of 601.2b's
        "no legal target", so a Treasure across the table offers nothing."""
        game, source, _ = board(builder)
        create_token(game.state, "treasure_token", 1)
        item = push(game, source)
        assert item.modes == (0,)


class TestTheTargetIsDeclaredWithTheMode:
    def test_the_chosen_mode_declares_its_own_target(self, builder):
        game, source, made = board(builder, ("treasure_token",))
        item = push(game, source, (COPY_MODE,))
        assert item.modes == (1,)
        assert item.modes_answered, "or `op_choose_mode` asks again on resolution"
        assert [ref.id for ref in item.targets] == made

    def test_the_other_mode_declares_no_target_at_all(self, builder):
        """Not "declines an optional one" -- there is nothing to decline. The
        `optional: true` spelling stores an empty ref for a target that was
        offered; this stores none, because the spec was never in the list."""
        game, source, _ = board(builder, ("treasure_token",))
        item = push(game, source, (GNOME_MODE,))
        assert item.modes == (0,)
        assert item.targets == ()

    def test_two_tokens_make_the_target_a_real_question(self, builder):
        game, source, made = board(builder, ("treasure_token", "clue_token"))
        asked: list = []
        item = push(game, source, (COPY_MODE, "Clue"), asked=asked)
        assert [d.kind for d in asked] == [
            DecisionKind.CHOOSE_MODE,
            DecisionKind.CHOOSE_OBJECTS,
        ], "modes first, then the targets they own -- 601.2b, then 601.2c"
        assert [ref.id for ref in item.targets] == [made[1]]

    def test_it_becomes_a_target_as_the_ability_goes_on_the_stack(self, builder):
        """603.2d. A `chooser` selector inside the mode fires nothing here, so
        no ward and no "whenever this becomes the target" would ever see it."""
        game, source, made = board(builder, ("treasure_token",))
        push(game, source, (COPY_MODE,))
        became = [e for e in game.state.events if e.type == "became_target"]
        assert [e.data.get("oid") for e in became] == made

    def test_the_copy_is_of_what_was_targeted(self, builder):
        game, source, _ = board(builder, ("treasure_token",))
        push(game, source, (COPY_MODE,))
        resolve(game)
        assert permanents(game) == [WEAVER, "treasure_token", "treasure_token"]

    def test_the_gnome_mode_makes_a_gnome_and_not_a_copy(self, builder):
        game, source, _ = board(builder, ("treasure_token",))
        push(game, source, (GNOME_MODE,))
        resolve(game)
        assert permanents(game) == [GNOME, WEAVER, "treasure_token"]


class TestTheRecheckKnowsWhichModeWasChosen:
    """608.2b, and the reason `Ability.specs_for_modes` exists.

    `filter_legal` splits the stored refs **by position** against a spec list,
    so resolution has to rebuild the list the push built. Rebuilding the
    printed list instead would ask the Gnome mode to account for a ref it never
    declared.
    """

    def test_the_copy_mode_fizzles_when_its_token_leaves(self, builder):
        game, source, made = board(builder, ("treasure_token",))
        push(game, source, (COPY_MODE,))
        move_object(game.state, made[0], Zone.EXILE, to_player=0)
        resolve(game)
        assert permanents(game) == [WEAVER], "nothing was created"
        assert game.state.events[-1].type == "spell_fizzled"

    def test_the_gnome_mode_does_not(self, builder):
        """The same board, the same removal, the other mode -- and the Gnome
        still arrives. An unconditional ability-level target cannot tell these
        two apart, because it declared the target either way."""
        game, source, made = board(builder, ("treasure_token",))
        push(game, source, (GNOME_MODE,))
        move_object(game.state, made[0], Zone.EXILE, to_player=0)
        resolve(game)
        assert permanents(game) == [GNOME, WEAVER]

    def test_the_specs_resolution_splits_by_are_the_ones_the_push_declared(
        self, builder
    ):
        game, source, made = board(builder, ("treasure_token", "clue_token"))
        item = push(game, source, (COPY_MODE, "Clue"))
        ability = game.state.registry.get(WEAVER).abilities[0]
        assert [spec.id for spec in ability.specs_for_modes(item.modes)] == ["tok"]
        assert [spec.id for spec in ability.specs_for_modes((0,))] == []
        assert len(item.targets) == 1 and item.targets[0].id == made[1]


class TestTheLoaderRefusals:
    """Each one is a card that would otherwise load and read wrong."""

    def ability(self, **over):
        ability = {
            "kind": "triggered",
            "text": "Whenever you cast a creature spell, choose one.",
            "trigger": {"event": "spell_cast", "controller": "you"},
            "targets": [
                {
                    "id": "tok",
                    "kind": "permanent",
                    "mode": 1,
                    "selector": {"zone": "battlefield", "controller": "you"},
                }
            ],
            "effects": [
                {
                    "op": "choose_mode",
                    "count": 1,
                    "modes": [
                        {"label": "Draw a card.", "effects": [{"op": "draw"}]},
                        {
                            "label": "Copy it.",
                            "effects": [
                                {"op": "copy_permanent", "objects": {"target": "tok"}}
                            ],
                        },
                    ],
                }
            ],
        }
        ability.update(over)
        return ability

    def compile(self, ability):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "x_modal_trigger",
                    "name": "X Modal Trigger",
                    "mana_cost": "{2}",
                    "types": ["Artifact"],
                    "abilities": [ability],
                }
            )
        )

    def test_the_shape_it_is_meant_to_allow_still_loads(self):
        self.compile(self.ability())

    def test_an_activated_ability_may_own_one_now(self):
        """It could not, and Phoenix Down is what changed it.

        `legality` used to enumerate one activation per legal target tuple, so
        the targets were fixed before `Game._activate` asked which mode -- the
        reverse of the printed order, and no moment to declare a mode's target
        in. `_ability_aims` now offers one activation *per mode*, each carrying
        only the targets that mode owns, so the bullet is part of the action the
        way `kicked` is part of a cast. See tests/unit/test_modal_activated.py.
        """
        self.compile(self.ability(kind="activated", cost={"mana": "{1}"}, trigger=None))

    def test_a_mode_owned_target_needs_a_single_top_level_choose_mode(self):
        with pytest.raises(DslError, match="top-level 'choose_mode'"):
            self.compile(self.ability(effects=[{"op": "draw"}]))

    def test_a_mode_that_does_not_exist(self):
        ability = self.ability()
        ability["targets"][0]["mode"] = 7
        with pytest.raises(DslError, match="mode 7 does not exist"):
            self.compile(ability)

    def test_an_optional_mode_owned_target(self):
        """Declining it is declining the mode, and 601.2b already says a mode
        with no legal target cannot be chosen."""
        ability = self.ability()
        ability["targets"][0]["optional"] = True
        with pytest.raises(DslError, match="cannot be 'optional'"):
            self.compile(ability)

    def test_a_caster_chosen_size_inside_a_mode(self):
        ability = self.ability()
        ability["targets"][0]["count"] = "any"
        with pytest.raises(DslError, match="fixed number"):
            self.compile(ability)
