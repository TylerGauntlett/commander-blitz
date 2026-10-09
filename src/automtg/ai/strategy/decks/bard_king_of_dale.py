"""Bard, King of Dale: draw two, make twice the tokens, then turn the crowd sideways.

Bard doubles every token the deck makes and turns every draw past the first
into two, which makes each cantrip a "second card this turn" trigger for the
deck's payoffs (Prince Imrahil, Mischievous Mystic, Detective of the Month).
The plan is rocks into a turn-four or -five Bard, cheap draw spells to turn
those payoffs into bodies, then an anthem or Moonshaker Cavalry to make the
crowd lethal. Skullclamp on a 1/1 token is four cards under Bard.

See docs/cpus/bard_king_of_dale.md for how the deck plays and what this plan encodes.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import Step

from ..archetypes import GoWide, activated_ability, cast_card, target_objects
from ..base import DeckPlan
from ..board import classify, commander_oids, ready_attackers

#: Permanents that turn a second draw in a turn into a body or a counter --
#: with any of them out, a cantrip is a creature spell too.
DRAW_PAYOFFS = frozenset(
    {
        "bard_king_of_dale",
        "prince_imrahil_the_fair",
        "mischievous_mystic",
        "emrakul_s_messenger",
        "detective_of_the_month",
        "alandra_sky_dreamer",
        "thopter_fabricator",
        "nadir_kraken",
        "the_council_of_four",
    }
)


class BardGoWide(GoWide):
    #: With a payoff out, a one-mana cantrip is a card *and* a body (two under
    #: Bard): worth more than a vanilla one-drop, so it lifts draw (200) past
    #: a cheap creature (~340).
    draw_bonus = 150.0
    greaves_bonus = 100.0
    clamp_bonus = 60.0
    #: Makindi Stampede is a finisher, not a turn-two play: it waits for this
    #: many creatures ready to swing.
    stampede_attackers = 3

    def priority_value(self, state, seat, action, base):
        value = super().priority_value(state, seat, action, base)
        card = cast_card(state, action)
        if card is not None:
            if getattr(action, "gift_to", None) is not None:
                # Perch Protection's gift hands an opponent an extra turn for a
                # fog this agent cannot time; the four Birds alone are the play.
                return 0.0
            if value > 0 and classify(card) == "draw" and self._payoff_out(state, seat):
                value += self.draw_bonus
            if card.id == "makindi_stampede_makindi_mesas" and value > 0:
                wide = len(ready_attackers(state, seat)) >= self.stampede_attackers
                if state.step is not Step.PRECOMBAT_MAIN or not wide:
                    return 0.0
                value += 80.0
            return value
        ability = activated_ability(state, action)
        if ability is not None and ability.is_equip and value > 0:
            value = self._equip_value(state, seat, action, value)
        return value

    def _payoff_out(self, state, seat) -> bool:
        return any(o.def_id in DRAW_PAYOFFS for o in state.battlefield_objects(seat))

    def _equip_value(self, state, seat, action, value):
        equipment = state.objects.get(action.source)
        targets = target_objects(state, action)
        if equipment is None or not targets:
            return value
        target = targets[0]
        bards = set(commander_oids(state, seat))
        if equipment.def_id == "lightning_greaves":
            # Shroud on the engine; never peel it off Bard for anything else.
            if equipment.attached_to in bards:
                return 0.0
            return value + self.greaves_bonus if target in bards else value
        if equipment.def_id == "skullclamp":
            obj = state.objects[target]
            # +1/-1 kills an X/1 on the spot: two cards, four under Bard, for
            # a token that was only ever a chump blocker.
            if obj.is_token and chars(state, target).toughness <= 1:
                return value + self.clamp_bonus
        return value


STRATEGY = BardGoWide(
    DeckPlan(
        deck_id="bard_king_of_dale",
        archetype="go_wide",
        commanders=frozenset({"bard_king_of_dale"}),
        key_cards={
            "bard_king_of_dale": 100.0,
            # Six mana is a lot: the rocks come first.
            "sol_ring": 80.0,
            "arcane_signet": 40.0,
            "azorius_signet": 40.0,
            "talisman_of_progress": 30.0,
            "mind_stone": 30.0,
            "thran_dynamo": 30.0,
            "smothering_tithe": 60.0,
            # Engines and anthems that make a pile of 1/1s a clock.
            "skullclamp": 50.0,
            "caretaker_s_talent": 50.0,
            "cathars_crusade": 60.0,
            "adeline_resplendent_cathar": 60.0,
            "prince_imrahil_the_fair": 40.0,
            "monastery_mentor": 40.0,
            "elesh_norn_grand_cenobite": 60.0,
            "moonshaker_cavalry": 60.0,
        },
        win_cons=frozenset(
            {"moonshaker_cavalry", "elesh_norn_grand_cenobite", "cathars_crusade"}
        ),
        protect=frozenset({"smothering_tithe", "skullclamp", "lightning_greaves"}),
        keep_lands=(2, 5),
        aggression=0.5,
    )
)
