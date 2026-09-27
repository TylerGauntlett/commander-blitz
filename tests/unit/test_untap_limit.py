"""``untap_limit`` — a cap on how many permanents untap, and who chooses.

    Winter Orb — "As long as this artifact is untapped, players can't untap more
    than one land during their untap steps."

`untap_held`'s own docstring already said what this is not. `skip_untap_step`
marks every permanent its filter describes and `untap_all` skips all of them: an
all-or-nothing hold, with no number and nobody choosing. Written with it, Winter
Orb becomes **Rising Waters** — every land held down — which is a strictly harsher
card, and exactly the approximation the gap record refused rather than shipped.
`TestItIsNotAHold` asserts that difference on one board instead of describing it.

Three things this had to get right.

**A count, not a flag.** The cap is a number, and a missing one reads as zero,
which is the harsher card again — so the loader refuses it.

**The untapping player chooses.** 502.2 untaps; it does not choose, so this is the
first question the untap step has ever put to anybody. It is asked in
`turn._untap_step`, which became a generator for it, rather than inside
`primitives.untap_all`, which is not one and whose every other caller wants no
decision. An engine that picked for the player would be deciding whether Winter
Orb locks out the Sol Ring or the Island, which is a different card every game.

**It composes with what was already there.** The capped-out set is consulted
beside the `untap_held` check and *before* `skip_next_untap`, so a permanent the
cap stopped does not also burn a one-shot skip that was waiting for a later untap
step — the same argument `untap_all` already makes for `held`.

The "as long as this artifact is untapped" half of the printed card needed
**nothing**: the gap record flagged `exists` over `{"self_only": true, "tapped":
false}` as a plausible but unproven near miss and recorded it rather than guessing,
and it turns out to work. `TestTheSelfUntappedGate` is the proof, and it is the
whole of how the card is beaten in play — you tap the Orb on the opponent's end
step.

Witness: Winter Orb (`data/authoring/answers/winter_orb.json`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.player_statics import untap_caps
from automtg.engine.primitives import untap_all
from tests.conftest import oids_of, only_oid

ORB = "t_winter_orb"  # Winter Orb as printed, gated on its own untapped state
UNGATED = "t_winter_orb_ungated"  # the same cap with no self-untapped condition
STASIS = "t_stasis_like"  # skip_untap_step over lands -- the harsher card
PLAINS = "plains"
BEAR = "t_bear"


def board(builder, mine=(UNGATED,), lands=3, tapped=True):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands + list(mine))
        .battlefield(1, [PLAINS])
        .hand(0, [PLAINS])
        .build(advance=False)
    )
    if tapped:
        for oid in oids_of(game, PLAINS, 0):
            game.state.objects[oid].tapped = True
        game.state.bump_chars()
    return game


class TestTheCapIsSeen:
    def test_it_reports_the_maximum_and_the_candidates(self, builder):
        game = board(builder)
        caps = untap_caps(game.state, 0)

        assert len(caps) == 1
        maximum, candidates = caps[0]
        assert maximum == 1
        assert set(candidates) == set(oids_of(game, PLAINS, 0))

    def test_nothing_is_capped_without_the_static(self, builder):
        game = board(builder, mine=())
        assert untap_caps(game.state, 0) == []

    def test_only_the_named_types_are_capped(self, builder):
        """Winter Orb says lands. A creature is not one, so it is not a
        candidate -- which is most of what stops the cap being a Stasis."""
        game = board(builder, mine=(UNGATED, BEAR))
        game.state.objects[only_oid(game, BEAR, 0)].tapped = True
        game.state.bump_chars()
        _, candidates = untap_caps(game.state, 0)[0]

        assert only_oid(game, BEAR, 0) not in candidates

    def test_it_reaches_the_opponent_too(self, builder):
        """"**Players** can't untap" -- `affects_player: "any"`, so the Orb's own
        controller is capped as well as everyone else. The drawback is the card."""
        game = board(builder)
        game.state.objects[only_oid(game, PLAINS, 1)].tapped = True
        game.state.bump_chars()
        assert untap_caps(game.state, 1)


class TestUntapAllHonoursTheChoice:
    def test_only_the_chosen_land_untaps(self, builder):
        game = board(builder)
        lands = oids_of(game, PLAINS, 0)
        keep, rest = lands[0], set(lands[1:])

        untapped = untap_all(game.state, 0, capped_out=rest)

        assert keep in untapped
        assert all(game.state.objects[o].tapped for o in rest)

    def test_without_a_cap_every_land_untaps(self, builder):
        """Pins that the holding-down is the cap's and not the position's."""
        game = board(builder)
        untapped = untap_all(game.state, 0)
        assert set(oids_of(game, PLAINS, 0)) <= set(untapped)

    def test_a_capped_permanent_does_not_burn_a_skip(self, builder):
        """`untap_all` already argues this for `untap_held`: a permanent stopped
        by something else must not also spend a one-shot skip that was waiting
        for a later untap step."""
        game = board(builder)
        lands = oids_of(game, PLAINS, 0)
        game.state.objects[lands[1]].skip_next_untap = True

        untap_all(game.state, 0, capped_out={lands[1], lands[2]})

        assert game.state.objects[lands[1]].skip_next_untap is True, "still waiting"


class TestItIsNotAHold:
    """The difference between a cap and `skip_untap_step`, measured.

    Winter Orb lets one land through; Rising Waters lets none. A version written
    with the hold would look identical in every test that only asks "did
    everything untap".
    """

    def test_the_cap_lets_one_through(self, builder):
        game = board(builder)
        lands = oids_of(game, PLAINS, 0)
        untapped = untap_all(game.state, 0, capped_out=set(lands[1:]))
        assert len(untapped) >= 1

    def test_the_hold_lets_none_through(self, builder):
        game = board(builder, mine=(STASIS,))
        untapped = untap_all(game.state, 0)
        assert not set(oids_of(game, PLAINS, 0)) & set(untapped)


class TestTheSelfUntappedGate:
    """"As long as this artifact is untapped" -- the clause the gap record listed
    as plausible but unproven, and which needed no new work at all.

    It is also the whole of how the card is beaten in play: tap the Orb on the
    opponent's end step and your own untap step is free.
    """

    def test_the_cap_applies_while_the_orb_is_untapped(self, builder):
        game = board(builder, mine=(ORB,))
        assert untap_caps(game.state, 0)

    def test_and_lifts_once_the_orb_is_tapped(self, builder):
        game = board(builder, mine=(ORB,))
        game.state.objects[only_oid(game, ORB, 0)].tapped = True
        game.state.bump_chars()
        assert untap_caps(game.state, 0) == []


class TestTheLoaderRefusals:
    def _card(self, **static) -> CardModel:
        base = {
            "kind": "static",
            "text": "Players can't untap more than one land during their untap steps.",
            "effect": "untap_limit",
            "affects_player": "any",
            "affects": {"controller": "any", "types": ["Land"]},
            "amount": {"const": 1},
        }
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_orb_probe",
                "name": "Orb Probe",
                "mana_cost": "{2}",
                "oracle_text": "Players can't untap more than one land during their "
                "untap steps.",
                "types": ["Artifact"],
                "abilities": [base],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_no_amount_is_refused(self):
        """A cap with no number reads as zero, which is the harsher card."""
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(self._card(amount=None))

    def test_no_filter_is_refused(self):
        """Winter Orb says lands; filterless it holds down the whole board."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(affects=None))
