""""…create a token that's tapped and attacking **that player**."

    Ainok Strike Leader — "Whenever you attack with this creature and/or your
    commander, for each opponent, create a 1/1 red Goblin creature token that's
    tapped and attacking that player."

    Combat Calligrapher — "Whenever a player attacks one of your opponents, that
    attacking player creates a tapped 2/1 white and black Inkling creature token
    with flying that's attacking that opponent."

`attacking` was a bare boolean, resolved as "whoever the **source** is already
attacking" (`board_helpers._attack_target`). That is the right answer for the cards
it was written for and it is silently wrong for both of these:

- Inside `for_each_player` the boolean has no idea the loop moved. At a pod
  Ainok's three tokens would all be declared against the one seat the Ainok
  itself is swinging at — "for each opponent" would degenerate into "three
  tokens at one player", which is a *different and better* card.
- Combat Calligrapher never attacks at all. Its trigger fires off somebody
  else's declaration, so the lookup returns `None`, and the token arrives tapped
  and attacking nobody while the card still looks implemented.

So `attacking` now also takes a **player spec** — the seat a `for_each_player`
loop is on (`{"binding": "each_player"}`), a trigger's `defender` binding, or a
target. The boolean is untouched, because every shipped card uses it.

Two rules bound the feature, and both are asserted below:

- **508.4** — a permanent put onto the battlefield attacking was never
  *declared* as an attacker, so it triggers nothing that fires on attacking.
  That contract predates this change and is what keeps "whenever this attacks,
  make a token attacking" finite; naming the player must not quietly break it.
- **509.1** — the defending player declares blockers. `finish_attackers` fills
  `pending_blockers` from the declaration, so a token pointed at a seat nobody
  declared against (Ainok's third opponent) would otherwise be attacking a
  player who is never asked to block it. That seat is now inserted into the
  queue, in APNAP order — and only while blocks are still being declared, since
  a permanent arriving after that is simply unblocked.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, oids_of, only_oid, pass_until

BEAR = "t_bear"
WALL = "t_defensive_wall"
GOBLIN = "goblin_1_1_r"
INKLING = "inkling_2_1_wb_flying"
#: "Whenever you attack, for each opponent, create a 1/1 red Goblin creature
#: token that's tapped and attacking that player." Ainok Strike Leader's line.
MARSHAL = "t_pod_marshal"
#: "Whenever a player attacks one of your opponents, that attacking player
#: creates a tapped 2/1 … Inkling … that's attacking that opponent."
SCRIBE = "t_ink_scribe"


def position(builder, *, bears: int = 1, players: int = 4, defenders: int = 0, p0=(), p3=()):
    """Player 0 with ``bears`` to swing, in a pod.

    Four seats by default, because every claim here is about *which* player a
    token was pointed at, and a two-player game answers that by accident: there
    is only one opponent to be wrong about.
    """
    b = builder(players=players)
    b.battlefield(0, [*([BEAR] * bears), *p0])
    for pid in range(1, players):
        extra = list(p3) if pid == players - 1 else []
        if defenders or extra:
            b.battlefield(pid, [WALL] * defenders + extra)
        b.library(pid, ["swamp"] * 20)
    b.library(0, ["swamp"] * 20)
    return b.active(0).step(Step.UNTAP).max_turns(2).build()


def to_declare_attackers(game, limit: int = 120):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def declare(game, plan: dict[int, int]) -> dict[int, list[int]]:
    """Send player 0's bears at the seats in ``plan`` -- ``{defender: how many}``.

    Stops **inside** the declare attackers step, with the declaration closed:
    that is the window an attack trigger resolves in, which is where every card
    under test creates its token.
    """
    to_declare_attackers(game)
    bears = list(oids_of(game, BEAR, 0))
    sent: dict[int, list[int]] = {}
    for defender, count in plan.items():
        for _ in range(count):
            oid = bears.pop(0)
            action = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any(t.kind == "player" and t.id == defender for t in a.targets)
            )
            game.apply(action)
            sent.setdefault(defender, []).append(oid)
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    return sent


def run_effect(game, effects, *, source=None, controller=0, bindings=None, targets=None):
    """Resolve ``effects`` as an attack trigger would, and return the new tokens."""
    before = set(game.state.objects)
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        source_oid=source,
        bindings=dict(bindings or {}),
        targets=dict(targets or {}),
    )
    list(execute(ctx, effects))
    return [oid for oid in game.state.objects if oid not in before]


def token(spec: dict) -> dict:
    return {"op": "create_token", "token": GOBLIN, "tapped": True, **spec}


def attacking_map(game) -> dict[int, int]:
    return dict(game.state.combat.attackers)


def blockers_asked(game, limit: int = 200) -> set[int]:
    """Which seats the engine actually stops and asks for blocks, run to damage."""
    asked: set[int] = set()
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.state.step is Step.END_OF_COMBAT:
            break
        if decision.kind is DecisionKind.DECLARE_BLOCKERS:
            asked.add(decision.player)
        game.apply(_default_answer(game, decision))
    return asked


class TestNamingThePlayer:
    """The clause the boolean cannot say: *that* player, not mine."""

    def test_a_binding_points_the_token_at_the_named_seat(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})],
                          bindings={"each_player": 3})

        assert len(made) == 1
        assert attacking_map(game)[made[0]] == 3, "the named seat, not the one I am attacking"

    def test_for_each_opponent_gives_every_seat_its_own_token(self, builder):
        """Ainok Strike Leader's whole line, written the way the card reads."""
        game = position(builder)
        declare(game, {1: 1})
        made = run_effect(
            game,
            [
                {
                    "op": "for_each_player",
                    "players": "each_opponent",
                    "effects": [token({"attacking": {"binding": "each_player"}})],
                }
            ],
        )

        assert len(made) == 3, "one per opponent"
        assert sorted(attacking_map(game)[oid] for oid in made) == [1, 2, 3]

    def test_the_source_need_not_be_attacking_anything(self, builder):
        """Combat Calligrapher: the trigger fires off somebody *else's* attack.

        Under the boolean this token attacked nobody, which is the whole clause
        dropped on the floor with nothing to show for it.
        """
        game = position(builder, players=4)
        declare(game, {1: 1})
        watcher = oids_of(game, BEAR, 0)[0]
        made = run_effect(
            game,
            [{"op": "create_token", "token": INKLING, "tapped": True,
              "attacking": {"binding": "defender"}}],
            source=watcher,
            controller=2,
            bindings={"defender": 1},
        )

        assert attacking_map(game)[made[0]] == 1
        assert game.state.objects[made[0]].controller == 2, "*that attacking player* creates it"

    def test_a_target_can_name_the_seat(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        made = run_effect(
            game,
            [token({"attacking": {"target": "t1"}})],
            targets={"t1": (TargetRef.player(2),)},
        )

        assert attacking_map(game)[made[0]] == 2

    def test_the_token_is_still_tapped(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})],
                          bindings={"each_player": 2})

        assert game.state.objects[made[0]].tapped


class TestTheBooleanIsUnchanged:
    """Every shipped card uses `attacking: true` and none of them may move."""

    def test_true_still_means_where_the_source_is_pointed(self, builder):
        game = position(builder)
        sent = declare(game, {2: 1})
        made = run_effect(game, [token({"attacking": True})], source=sent[2][0])

        assert attacking_map(game)[made[0]] == 2

    def test_true_from_a_non_attacking_source_joins_nobody(self, builder):
        """The documented contract: there is nobody to join, so it just arrives."""
        game = position(builder, bears=2)
        declare(game, {1: 1})
        bystander = oids_of(game, BEAR, 0)[1]
        made = run_effect(game, [token({"attacking": True})], source=bystander)

        assert made[0] not in attacking_map(game)
        assert game.state.objects[made[0]].tapped, "tapped was asked for; attacking was not possible"

    def test_false_and_absent_both_mean_no_combat(self, builder):
        game = position(builder)
        sent = declare(game, {1: 1})
        made = run_effect(
            game,
            [token({"attacking": False}), token({})],
            source=sent[1][0],
        )

        assert all(oid not in attacking_map(game) for oid in made)


class TestNamingNobody:
    """A spec that resolves to no seat is the boolean's "nobody to join"."""

    def test_an_unbound_binding_leaves_the_token_out_of_combat(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})])

        assert made[0] not in attacking_map(game)

    def test_a_player_who_has_left_is_not_attacked(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        game.state.players[3].has_lost = True
        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})],
                          bindings={"each_player": 3})

        assert made[0] not in attacking_map(game)

    def test_naming_several_seats_at_once_is_refused(self, builder):
        """A creature attacks exactly one player, so there is nothing to pick.

        The plural *names* are refused at load time; this is the one shape load
        time cannot see -- a target that chose two players.
        """
        game = position(builder)
        declare(game, {1: 1})
        with pytest.raises(DslError, match="attacks exactly one"):
            run_effect(
                game,
                [token({"attacking": {"target": "t1"}})],
                targets={"t1": (TargetRef.player(1), TargetRef.player(2))},
            )


class TestItWasNeverDeclaredAnAttacker:
    """508.4 -- and the reason "make a token attacking" does not loop forever."""

    def test_no_attacks_event_is_fired_for_the_token(self, builder):
        game = position(builder)
        declare(game, {1: 1})
        before = len([e for e in game.state.events if e.type is EventType.ATTACKS])
        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})],
                          bindings={"each_player": 2})

        after = [e for e in game.state.events if e.type is EventType.ATTACKS]
        assert len(after) == before
        assert all(e.data.get("attacker") != made[0] for e in after)


class TestTheCardsThisUnblocks:
    """Both witnesses, as printed cards, through a real combat.

    Their triggers resolve in the declare attackers step, which is the window
    the boolean got wrong: neither source is attacking the seat its token is
    aimed at, and the Scribe is not attacking at all.
    """

    def test_the_marshal_makes_one_token_per_opponent_each_at_its_own_seat(self, builder):
        """"For each opponent, create a token that's tapped and attacking *that player*.\""""
        game = position(builder, p0=[MARSHAL])
        declare(game, {1: 1})

        goblins = oids_of(game, GOBLIN, 0)
        assert len(goblins) == 3, "one per opponent"
        assert sorted(attacking_map(game)[g] for g in goblins) == [1, 2, 3]
        assert all(game.state.objects[g].tapped for g in goblins)

    def test_the_marshal_need_not_be_attacking_itself(self, builder):
        """It stayed home and the bear swung, which is the "and/or your
        commander" half of the printed trigger. Under the boolean all three
        tokens would have joined whatever the Marshal was attacking -- nothing."""
        game = position(builder, p0=[MARSHAL])
        declare(game, {1: 1})

        assert only_oid(game, MARSHAL, 0) not in attacking_map(game)
        assert all(g in attacking_map(game) for g in oids_of(game, GOBLIN, 0))

    def test_every_newly_attacked_seat_declares_blockers(self, builder):
        game = position(builder, p0=[MARSHAL], defenders=1)
        declare(game, {1: 1})
        assert game.state.combat.pending_blockers == [1, 2, 3]

        assert {1, 2, 3} <= blockers_asked(game)

    def test_the_damage_lands_on_the_seats_that_were_named(self, builder):
        """The whole clause, measured where a player would notice it."""
        game = position(builder, p0=[MARSHAL])
        declare(game, {1: 1})
        before = [p.life for p in game.state.players]

        pass_until(game, lambda g: g.state.step is Step.END_OF_COMBAT)

        after = [p.life for p in game.state.players]
        assert after[1] == before[1] - 3, "the bear and one goblin"
        assert after[2] == before[2] - 1, "a goblin, at a seat nobody declared against"
        assert after[3] == before[3] - 1

    def test_the_scribe_points_its_token_at_the_defender(self, builder):
        """"Whenever a player attacks one of your opponents, that attacking
        player creates a … token that's attacking that opponent." The source is
        not an attacker at all, so the boolean had nothing to read."""
        game = position(builder, p3=[SCRIBE])
        declare(game, {1: 1})

        inklings = oids_of(game, INKLING)
        assert len(inklings) == 1
        assert game.state.objects[inklings[0]].controller == 0, "*that attacking player* makes it"
        assert attacking_map(game)[inklings[0]] == 1, "at the seat that was attacked"


class TestTheQueueOfBlockers:
    """509.1 -- a player being attacked is a player who declares blockers."""

    def test_a_seat_nobody_declared_against_is_inserted_in_apnap_order(self, builder):
        """Seat 3 was the declared defender; seats 1 and 2 arrive with the
        tokens and have to be asked *before* it, not appended after."""
        game = position(builder, p0=[MARSHAL])
        declare(game, {3: 1})

        assert game.state.combat.pending_blockers == [1, 2, 3]

    def test_a_seat_already_being_attacked_is_not_queued_twice(self, builder):
        game = position(builder, bears=2, p0=[MARSHAL])
        declare(game, {1: 1, 2: 1})

        assert game.state.combat.pending_blockers == [1, 2, 3]

    def test_a_token_arriving_after_the_declaration_is_simply_unblocked(self, builder):
        """The other half of 509.1, and the guard that stops this becoming a
        second block declaration: once the step is walking its queue, a token
        still joins combat but nobody is called back to block it."""
        game = position(builder)
        declare(game, {1: 1})
        assert game.state.step is Step.DECLARE_BLOCKERS, "the step is under way"

        made = run_effect(game, [token({"attacking": {"binding": "each_player"}})],
                          bindings={"each_player": 3})

        assert attacking_map(game)[made[0]] == 3, "it is still attacking that player"
        assert 3 not in game.state.combat.pending_blockers


class TestTheLoaderRefusesWhatCannotWork:
    def compile(self, attacking):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe",
                    "name": "Probe",
                    "mana_cost": "{R}",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "abilities": [
                        {
                            "kind": "triggered",
                            "trigger": {"event": "you_attack"},
                            "effects": [
                                {"op": "create_token", "token": GOBLIN, "attacking": attacking}
                            ],
                        }
                    ],
                }
            )
        )

    def test_the_boolean_still_loads(self):
        assert self.compile(True) is not None

    @pytest.mark.parametrize("spec", ["opponent", "each_opponent", "each_player", "all"])
    def test_a_plural_spec_is_refused(self, spec):
        """"Each opponent" has no single answer, and picking one silently would
        make a card that reads like a pod sweep and hits one seat."""
        with pytest.raises(DslError, match="a creature attacks one"):
            self.compile(spec)

    def test_a_bare_seat_number_is_refused(self):
        """No printed card names a seat, and `0` is indistinguishable from false."""
        with pytest.raises(DslError, match="true/false or a player spec"):
            self.compile(2)

    def test_a_misspelled_name_is_refused(self):
        with pytest.raises(DslError, match="unknown player spec"):
            self.compile("each_oponent")

    def test_a_target_the_card_never_declared_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            self.compile({"target": "t1"})

    def test_a_singular_name_loads(self):
        assert self.compile("active_player") is not None

    def test_copy_permanent_and_put_onto_battlefield_are_checked_too(self):
        """They take the same key through the same helper."""
        for op, extra in (
            ("copy_permanent", {"objects": {"self_only": True}}),
            ("put_onto_battlefield", {"objects": {"self_only": True}}),
        ):
            with pytest.raises(DslError, match="a creature attacks one"):
                compile_card(
                    CardModel.model_validate(
                        {
                            "id": "t_probe",
                            "name": "Probe",
                            "mana_cost": "{R}",
                            "types": ["Creature"],
                            "power": 1,
                            "toughness": 1,
                            "abilities": [
                                {
                                    "kind": "triggered",
                                    "trigger": {"event": "you_attack"},
                                    "effects": [
                                        {"op": op, "attacking": "each_opponent", **extra}
                                    ],
                                }
                            ],
                        }
                    )
                )
