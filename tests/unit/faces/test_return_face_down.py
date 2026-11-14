"""`face_down` on `return_from_graveyard` -- a card returned to the battlefield
face down (708.2).

    Ashcloud Phoenix -- "When this creature dies, return it to the battlefield
    face down under your control."
    Deathmist Raptor -- "... you may return this card from your graveyard to
    the battlefield face up or face down."

Until this key the only face-down arrivals were a morph cast and a manifest,
and neither can take a card out of a graveyard: the Phoenix came back face up,
a 4/1 flier every time, which is a far stronger card than the printed one. The
rules argument here:

* **It arrives as the shell.** The card is a 2/2 colourless creature with no
  name and no abilities from the moment it enters (708.2), so "whenever a
  face-down creature enters" hears it and its own printed abilities do not.
* **It turns up for its morph cost** (702.37e), and megamorph's counter comes
  with paying it (702.37b).
* **Without morph it never turns up by itself.** Only a *manifested* creature
  card turns up for its mana cost (701.34c); a card an effect returned face
  down was not manifested, so the special action is not offered at all.
* **Dying face down is dying with no abilities.** The face-down Phoenix has no
  "when this dies" while it is down (707.2), so a second death leaves it in
  the graveyard -- the loop guard the printed card relies on.
* **"Face up or face down" is a choice**, made by the returning player.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid, pass_until, plus_one_counters, settle

FOREST = "forest"
MOUNTAIN = "mountain"
SWAMP = "swamp"
KILL = "t_afg_kill"  # {B} instant, "destroy target creature"
PHOENIX = "t_rfd_phoenix"  # 4/1 flier, morph {R}, dies -> return face down
HUSK = "t_rfd_husk"  # 3/3, no morph, dies -> return face down
RAPTOR = "t_rfd_raptor"  # 3/3 deathtouch, megamorph {G}, the graveyard return
WATCHER = "t_rfd_watcher"  # "whenever a face-down creature you control enters, draw"
BEAST = "t_morpher"  # {4}{G} 5/5 flier, morph {2}{G}


def board(builder, mine=(), *, graveyard=(), kills=1):
    """Player 0 with Swamps, Mountains, Forests and ``mine``, ``kills`` copies
    of a kill spell in hand and ``graveyard`` in the graveyard. Returns
    ``(game, oid)`` with the oid of the first card in ``mine``."""
    game = (
        builder(players=2)
        .battlefield(0, [SWAMP] * 2 + [MOUNTAIN] * 2 + [FOREST] * 4 + list(mine))
        .battlefield(1, [FOREST] * 2)
        .graveyard(0, list(graveyard))
        .hand(0, [KILL] * kills)
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )
    oid = only_oid(game, mine[0], 0) if mine else None
    return game, oid


def kill(game, oid: int) -> None:
    """Cast the kill spell at ``oid`` and let everything resolve."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == KILL
            and any(ref.id == oid for ref in a.targets)
        )
    )
    settle(game)


def turn_up(game, oid: int) -> None:
    game.apply(activations(game, oid, 0)[0])


def answer_raptor(game, *, take: bool, face_down: bool = False) -> None:
    """Resolve the Raptor's trigger: say yes or no to the "may", then pick the
    face. The face question is asked only after a yes."""
    asked: list[DecisionKind] = []

    def at_question(g) -> bool:
        d = g.pending()
        return d is not None and d.kind in (DecisionKind.MAY, DecisionKind.CHOOSE_MODE)

    pass_until(game, lambda g: at_question(g) or (not g.state.stack and not g.state.pending_triggers))
    while at_question(game):
        decision = game.pending()
        asked.append(decision.kind)
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if take else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
        else:
            assert decision.player == 0
            assert [o.label for o in decision.options] == ["Face up", "Face down"]
            index = 1 if face_down else 0
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
            )
        pass_until(game, lambda g: at_question(g) or (not g.state.stack and not g.state.pending_triggers))
    game.asked = asked  # type: ignore[attr-defined]


def entered_face_down(game, oid: int) -> bool:
    obj = game.state.objects[oid]
    return obj.zone is Zone.BATTLEFIELD and obj.face_down


class TestItComesBackAsTheShell:
    def test_the_phoenix_returns_face_down_as_a_2_2(self, builder):
        game, phoenix = board(builder, [PHOENIX])

        kill(game, phoenix)

        assert entered_face_down(game, phoenix)
        c = chars(game.state, phoenix)
        assert (c.power, c.toughness) == (2, 2)
        assert c.types == frozenset({"Creature"})
        assert not c.keywords and not c.colors
        assert game.state.objects[phoenix].controller == 0
        assert 0 in game.state.objects[phoenix].revealed_to

    def test_a_face_down_watcher_hears_it_enter(self, builder):
        """Marked before its enters event, so the arrival is the shell's."""
        game, phoenix = board(builder, [PHOENIX, WATCHER])
        before = len(game.state.players[0].hand)

        kill(game, phoenix)

        # The kill spell left the hand; the watcher drew one.
        assert len(game.state.players[0].hand) == before

    def test_dying_face_down_leaves_it_in_the_graveyard(self, builder):
        """707.2: the shell has no "when this dies", so the loop ends."""
        game, phoenix = board(builder, [PHOENIX], kills=2)
        kill(game, phoenix)
        assert entered_face_down(game, phoenix)

        kill(game, phoenix)

        assert game.state.objects[phoenix].zone is Zone.GRAVEYARD


class TestTurningItUp:
    def test_the_phoenix_turns_up_for_its_morph_cost(self, builder):
        game, phoenix = board(builder, [PHOENIX])
        kill(game, phoenix)

        turn_up(game, phoenix)
        settle(game)

        assert not game.state.objects[phoenix].face_down
        assert chars(game.state, phoenix).power == 4

    def test_without_morph_it_is_never_offered_the_turn(self, builder):
        """701.34c is manifest's rule, and this card was not manifested."""
        game, husk = board(builder, [HUSK])
        kill(game, husk)
        assert entered_face_down(game, husk)

        assert not activations(game, husk), "no morph cost, so nothing to turn it up for"


class TestFaceUpOrFaceDown:
    def position(self, builder):
        game, beast = board(builder, [BEAST], graveyard=[RAPTOR])
        obj = game.state.objects[beast]
        obj.face_down = True
        obj.revealed_to.add(0)
        game.state.bump_chars()
        raptor = next(o for o in game.state.players[0].graveyard if game.state.objects[o].def_id == RAPTOR)
        return game, beast, raptor

    def test_face_down_turns_up_for_megamorph_with_its_counter(self, builder):
        game, beast, raptor = self.position(builder)
        turn_up(game, beast)

        answer_raptor(game, take=True, face_down=True)

        assert game.asked == [DecisionKind.MAY, DecisionKind.CHOOSE_MODE]  # type: ignore[attr-defined]
        assert entered_face_down(game, raptor)
        assert chars(game.state, raptor).power == 2
        assert "deathtouch" not in chars(game.state, raptor).keywords

        turn_up(game, raptor)
        settle(game)

        assert not game.state.objects[raptor].face_down
        assert plus_one_counters(game, raptor) == 1
        assert "deathtouch" in chars(game.state, raptor).keywords

    def test_face_up_is_the_printed_card(self, builder):
        game, beast, raptor = self.position(builder)
        turn_up(game, beast)

        answer_raptor(game, take=True, face_down=False)

        obj = game.state.objects[raptor]
        assert obj.zone is Zone.BATTLEFIELD and not obj.face_down
        assert chars(game.state, raptor).power == 3

    def test_declining_asks_no_face(self, builder):
        game, beast, raptor = self.position(builder)
        turn_up(game, beast)

        answer_raptor(game, take=False)

        assert game.asked == [DecisionKind.MAY]  # type: ignore[attr-defined]
        assert game.state.objects[raptor].zone is Zone.GRAVEYARD


def _card(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_rfd_bad",
            "name": "Bad",
            "oracle_text": "Return it.",
            "mana_cost": "{G}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }
    )


class TestLoader:
    def test_face_down_needs_the_battlefield(self):
        model = _card(
            {"op": "return_from_graveyard", "face_down": True,
             "objects": {"zone": "graveyard", "player": "you", "count": 1}}
        )
        with pytest.raises(DslError, match="needs destination 'battlefield'"):
            compile_card(model)

    def test_face_down_is_true_or_choose(self):
        model = _card(
            {"op": "return_from_graveyard", "face_down": "yes", "destination": "battlefield",
             "objects": {"zone": "graveyard", "player": "you", "count": 1}}
        )
        with pytest.raises(DslError, match="'face_down' is true or 'choose'"):
            compile_card(model)

    def test_face_down_refuses_a_named_host(self):
        model = _card(
            {"op": "return_from_graveyard", "face_down": True, "destination": "battlefield",
             "host_named": {"zone": "battlefield", "controller": "you", "count": 1},
             "objects": {"zone": "graveyard", "player": "you", "count": 1}}
        )
        with pytest.raises(DslError, match="not an Aura"):
            compile_card(model)
