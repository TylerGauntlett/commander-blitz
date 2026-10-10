"""Attaching a permanent that is not the ability's own source (rule 701.3).

Every attach the engine had ever done was an Equipment or an Aura attaching
**itself**: Equip and Reconfigure are printed on the Equipment, so "attach to
target creature you control" can only mean *me*, and `op_attach` hardcoded the
mover as ``ctx.source_oid``. ``objects`` was, and still is, the **host** -- the
creature it lands on.

Vault 101: Birthday Party is the witness, and it is the card where the source is
somebody else:

    II, III — You may put an Aura or Equipment card from your hand or graveyard
    onto the battlefield. If an Equipment is put onto the battlefield this way,
    you may attach it to a creature you control.

The source of that ability is a **Saga** -- an Enchantment that is neither Aura
nor Equipment. Written with a plain `attach`, the engine would attach the Saga
itself to a creature and leave the Equipment that had just arrived lying on the
battlefield equipping nobody.

**That failure passes every gate the card pipeline has.** The card loads, the
chapter resolves, the Equipment really is on the battlefield, and a zone
expectation sees exactly what it expected. The only evidence is a `+2/+0` that
never appears, so the claims below are about `attached_to` and about
`chars(...).power` rather than about where anything ended up.

Two more things are pinned here because they are the two ways this can be
half-built:

- **"If an Equipment is put onto the battlefield this way"** is not an `if` op.
  It is the ``attachment`` pool coming back empty when an *Aura* was taken
  instead, which must skip the host question entirely rather than ask it and
  then attach nothing.
- **An Aura put onto the battlefield without being cast enchants nothing.**
  `stack._attach_aura` reads the *spell's* targets and there was no spell, so
  `sba` bins it (704.5m) unless something attaches it. That is the same op with
  a wider ``attachment``, and it is asserted in both directions.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sagas, turn
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import find_action, oids_of

#: "{T}: …put an Aura or Equipment card … onto the battlefield. If an
#: **Equipment** is put onto the battlefield this way, you may attach it…" --
#: Vault 101's second sentence with the Saga's timing taken off, so a test can
#: drive it at a chosen moment.
RITE = "t_gear_rite"
#: The same ability with the ``attachment`` selector left wide open: whatever was
#: put onto the battlefield gets attached, Aura included.
AURA_RITE = "t_aura_rite"
SAGA = "t_gear_saga"
BLADE = "t_gear_blade"  # Equipment. Equipped creature gets +2/+0. Equip {1}
WINGS = "t_gear_wings"  # Aura. Enchanted creature gets +1/+1
SHIELD = "t_gear_shield"  # a second Equipment, already on the battlefield
BEAR = "t_gear_bear"  # vanilla 2/2


def board(builder, *, rite: str = RITE, hand=(), graveyard=(), creatures: int = 1):
    """``rite`` and ``creatures`` bears on player 0's battlefield, and the rite's oid.

    The rite is an Artifact and not a creature, so it is never itself a candidate
    host -- which keeps every "Attach to" pool below exactly the bears.
    """
    b = builder(players=2).battlefield(0, [rite]).battlefield(0, [BEAR] * creatures)
    if hand:
        b = b.hand(0, list(hand))
    if graveyard:
        b = b.graveyard(0, list(graveyard))
    game = b.build()
    return game, oids_of(game, rite, 0)[0]


def saga_board(builder, *, hand=(), graveyard=()):
    """A Saga one lore counter short of chapter II, and its oid.

    ``advance=False`` and a placed lore counter, exactly as `tests/unit/
    test_saga.py` stands a Saga part-way through its story: placing a Saga is not
    the same as one entering, so no chapter has fired yet and :func:`tick` runs
    precisely one.
    """
    b = (
        builder(players=2)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .battlefield(0, [SAGA], counters={sagas.LORE: 1})
        .battlefield(0, [BEAR])
    )
    if hand:
        b = b.hand(0, list(hand))
    if graveyard:
        b = b.graveyard(0, list(graveyard))
    game = b.build(advance=False)
    return game, oids_of(game, SAGA, 0)[0]


def tick(game) -> None:
    """Run the precombat main phase's turn-based actions: 714.2d, and nothing after."""
    game.state.step_started = False
    gen = turn.begin_step(game.state)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def resolve(game, *, take: bool = True, host: bool = True, limit: int = 80) -> list[str]:
    """Play the ability out, returning the prompts it asked for, in order.

    ``take`` answers the search ("You may put … onto the battlefield") and
    ``host`` answers the attach ("you may attach it to a creature you control").
    The returned list is itself an assertion target: a question that was never
    asked is not the same card as one that was asked and declined.
    """
    prompts: list[str] = []
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            prompts.append(decision.prompt)
            want = take if decision.prompt == "Search" else host
            choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            if want and choices:
                game.apply(choices[0])
            else:
                game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        if decision.kind is DecisionKind.PRIORITY:
            if not game.state.stack and not game.state.pending_triggers:
                return prompts
            game.apply(find_action(game, ActionKind.PASS))
            continue
        return prompts
    raise AssertionError(f"the ability never finished; prompts so far: {prompts}")


def activate(game, oid: int) -> None:
    game.apply(find_action(game, ActionKind.ACTIVATE, source=oid))


def attached_to(game, card_id: str, pid: int = 0) -> int | None:
    return game.state.objects[oids_of(game, card_id, pid)[0]].attached_to


def power(game, oid: int) -> int:
    return chars(game.state, oid).power


def card(model: dict):
    """Compile one card definition, so a load-time refusal can be asserted."""
    base = {"id": "x", "name": "X", "types": ["Artifact"], "mana_cost": "{1}"}
    return compile_card(CardModel.model_validate({**base, **model}))


ATTACH = {
    "op": "attach",
    "attachment": {"binding": "gear", "zone": "battlefield"},
    "objects": {"zone": "battlefield", "controller": "you", "types": ["Creature"]},
}


def ability(*effects):
    return {"abilities": [{"kind": "activated", "text": "x", "cost": {"tap": True},
                           "effects": list(effects)}]}


class TestWhatIsAttached:
    """The bug the key exists for: the mover is the Equipment, not the source."""

    def test_the_equipment_that_arrived_is_the_thing_attached(self, builder):
        game, rite = board(builder, hand=[BLADE])
        bear = oids_of(game, BEAR, 0)[0]

        activate(game, rite)
        resolve(game)

        assert attached_to(game, BLADE) == bear

    def test_the_ability_s_own_source_is_left_where_it_is(self, builder):
        """The whole failure in one assertion.

        With the attacher hardcoded to `ctx.source_oid` this is the *bear's* oid:
        the rite -- an Artifact that is neither Aura nor Equipment -- would be
        hanging off a creature, and the Equipment would be attached to nothing.
        """
        game, rite = board(builder, hand=[BLADE])

        activate(game, rite)
        resolve(game)

        assert game.state.objects[rite].attached_to is None

    def test_the_static_buff_applies(self, builder):
        """`attached_to` is bookkeeping; this is what a player would see.

        The characteristic layer reads `{"attached": true}` off the Equipment, so
        an Equipment that arrived unattached grants nothing and says nothing --
        which is exactly why a zone expectation cannot catch the bug.
        """
        game, rite = board(builder, hand=[BLADE])
        bear = oids_of(game, BEAR, 0)[0]
        assert power(game, bear) == 2

        activate(game, rite)
        resolve(game)

        assert power(game, bear) == 4, "equipped creature gets +2/+0"

    def test_it_reaches_the_graveyard_too(self, builder):
        """"from your hand **or graveyard**" -- one search over the union."""
        game, rite = board(builder, graveyard=[BLADE])
        bear = oids_of(game, BEAR, 0)[0]

        activate(game, rite)
        resolve(game)

        assert attached_to(game, BLADE) == bear
        assert power(game, bear) == 4

    def test_only_the_card_put_onto_the_battlefield_this_way_moves(self, builder):
        """"attach **it**" names one card, and a filter cannot say which.

        A second Equipment is already on the battlefield and unattached. A
        selector for "an Equipment you control" would be a legal reading of the
        pool and the wrong reading of the card -- it could pick up the blade that
        has been sitting there since turn three. The binding is what makes "it"
        mean the card this very ability just put down.
        """
        game = (
            builder(players=2)
            .battlefield(0, [RITE])
            .battlefield(0, [BEAR])
            .battlefield(0, [SHIELD])
            .hand(0, [BLADE])
            .build()
        )
        rite = oids_of(game, RITE, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]

        activate(game, rite)
        resolve(game)

        assert attached_to(game, BLADE) == bear, "the one that just arrived"
        assert attached_to(game, SHIELD) is None, "the one already there is untouched"
        assert power(game, bear) == 4, "+2/+0 only -- the shield grants nothing"


class TestTheConditionalIsAnEmptyPool:
    """"If an **Equipment** is put onto the battlefield this way" -- no `if` op."""

    def test_an_aura_asks_no_host_question(self, builder):
        """The rite's ``attachment`` filters the binding to Equipment.

        Taking the Aura leaves that pool empty, and an empty pool must mean *no
        decision*, not a decision that does nothing. A player shown "attach it to
        a creature you control" for a card the sentence does not cover has been
        told the game will do something it will not.
        """
        game, rite = board(builder, hand=[WINGS])

        activate(game, rite)
        prompts = resolve(game)

        assert prompts == ["Search"], "the attach half never came up"

    def test_and_that_aura_is_binned_by_state_based_actions(self, builder):
        """704.5m, and the reason the Aura half needs the same op.

        An Aura put onto the battlefield without being cast targeted nothing, so
        `stack._attach_aura` -- which reads the spell's targets -- never runs.
        Nothing is enchanted, and state-based actions put it in the graveyard.
        """
        game, rite = board(builder, hand=[WINGS])

        activate(game, rite)
        resolve(game)

        aura = game.state.objects[game.state.players[0].graveyard[-1]]
        assert aura.def_id == WINGS
        assert aura.zone is Zone.GRAVEYARD

    def test_a_wider_attachment_saves_it(self, builder):
        """The same op, the same key, the ``subtypes`` filter dropped."""
        game, rite = board(builder, rite=AURA_RITE, hand=[WINGS])
        bear = oids_of(game, BEAR, 0)[0]

        activate(game, rite)
        resolve(game)

        assert attached_to(game, WINGS) == bear, "it survived the state-based check"
        assert power(game, bear) == 3, "enchanted creature gets +1/+1"


class TestYouMay:
    """"you **may** attach it" -- ``optional`` on the host selector."""

    def test_declining_leaves_it_unattached(self, builder):
        game, rite = board(builder, hand=[BLADE])
        bear = oids_of(game, BEAR, 0)[0]

        activate(game, rite)
        prompts = resolve(game, host=False)

        assert prompts == ["Search", "Attach to"], "it was asked, and declined"
        assert attached_to(game, BLADE) is None
        assert power(game, bear) == 2, "no buff from an Equipment on nobody"

    def test_a_declined_equipment_stays_on_the_battlefield(self, builder):
        """The boundary between the two halves of the state-based check.

        `sba` bins an **Aura** attached to nothing and leaves an **Equipment**
        alone, which is why declining is a real choice here and is a slow suicide
        for the Aura above.
        """
        game, rite = board(builder, hand=[BLADE])

        activate(game, rite)
        resolve(game, host=False)

        assert oids_of(game, BLADE, 0), "the Equipment is still on the battlefield"

    def test_declining_the_search_asks_nothing_further(self, builder):
        """"**You may** put an Aura or Equipment card … onto the battlefield."

        Nothing arrived, so the binding is empty and the second half is skipped
        for the same reason the Aura skips it.
        """
        game, rite = board(builder, hand=[BLADE])

        activate(game, rite)
        prompts = resolve(game, take=False)

        assert prompts == ["Search"]
        assert not oids_of(game, BLADE, 0)
        assert len(game.state.players[0].hand) == 1, "it stayed in hand"


class TestTheSourceIsStillTheDefault:
    """No ``attachment`` key, no change -- Equip and Reconfigure are untouched."""

    def test_equip_attaches_the_equipment_it_is_printed_on(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BLADE])
            .battlefield(0, [BEAR])
            .battlefield(0, ["plains"] * 2)
            .build()
        )
        blade = oids_of(game, BLADE, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]

        game.apply(find_action(game, ActionKind.ACTIVATE, source=blade))
        resolve(game)

        assert game.state.objects[blade].attached_to == bear
        assert power(game, bear) == 4


class TestTheSaga:
    """Vault 101's actual shape: the chapter, not a stand-in ability."""

    def test_chapter_two_puts_it_down_and_equips_a_creature(self, builder):
        game, saga = saga_board(builder, hand=[BLADE])
        bear = oids_of(game, BEAR, 0)[0]

        tick(game)
        assert game.state.objects[saga].counter(sagas.LORE) == 2
        resolve(game)

        assert attached_to(game, BLADE) == bear
        assert power(game, bear) == 4

    def test_the_saga_itself_never_becomes_an_attachment(self, builder):
        """A Saga is an Enchantment and not an Aura, so nothing may attach it.

        The old op would have tried, and `primitives.attach` would have let it:
        it refuses self-attachment and protection, and asks no question about
        what kind of permanent the mover is.
        """
        game, saga = saga_board(builder, hand=[BLADE])

        tick(game)
        resolve(game)

        assert game.state.objects[saga].attached_to is None
        assert game.state.objects[saga].zone is Zone.BATTLEFIELD


class TestTheLoaderRefusesItElsewhere:
    """The guard, because every way of getting this wrong is silent."""

    def test_attachment_on_put_onto_battlefield_is_refused(self):
        """The first place anybody will try it -- the op that just put it down.

        Accepted and ignored, the Equipment arrives equipping nobody and the card
        reads exactly as printed. There is no observable difference except the
        buff that never happens, which is the failure the whole validator exists
        to turn into a load error.
        """
        with pytest.raises(DslError, match="only attach reads it"):
            card(ability({"op": "put_onto_battlefield",
                          "objects": {"binding": "gear"},
                          "attachment": {"binding": "gear"}}))

    def test_a_misspelled_key_inside_attachment_is_refused(self):
        with pytest.raises(DslError, match="attachment"):
            card(ability({"op": "attach", "attachment": {"subtype": ["Equipment"]}}))

    def test_attachment_may_not_name_an_undeclared_target(self):
        with pytest.raises(DslError, match="which the card does not declare"):
            card(ability({"op": "attach", "attachment": {"target": "t9"}}))

    def test_a_well_formed_attachment_loads(self):
        assert card(ability(ATTACH)) is not None
