"""Sheoldred, the Apocalypse ("Draw Death"): make the table draw, charge for every card.

Sheoldred turns each card an opponent draws into two life lost, and the deck is
built to hand out cards: Howling Mine, Font of Mythos, Temple Bell, Teferi's
Puzzle Box, and "target player draws" spells pointed across the table. All of
that is a gift without a punisher on the table, so the plan prices every
group-draw effect by how much an opponent's draw currently hurts them -- and
holds the worst of them until it hurts.

See docs/cpus/sheoldred_the_apocalypse.md for how the deck plays and what this
plan encodes.
"""

from __future__ import annotations

from math import ceil

from automtg.engine.costs import available_mana

from ..archetypes import Punisher, activated_ability, cast_card, target_objects
from ..base import Combo, DeckPlan
from ..board import commander_oids

SHEOLDRED = "sheoldred_the_apocalypse"
#: Life an opponent loses for each card they draw, by the permanent charging it.
OPPONENT_DRAW_PAIN = {
    SHEOLDRED: 2,
    "underworld_dreams": 1,
    "fate_unraveler": 1,
    "scrawling_crawler": 1,
    "ob_nixilis_the_hate_twisted": 1,
}
#: Permanents and spells that make opponents draw. Worth more with every point
#: of pain on the table; the ``HELD`` ones are pure gifts without it.
GROUP_DRAW = frozenset(
    {
        "howling_mine",
        "font_of_mythos",
        "teferi_s_puzzle_box",
        "temple_bell",
        "otherworld_atlas",
        "scrawling_crawler",
        "seizan_perverter_of_truth",
        "master_of_the_feast",
        "dark_deal",
    }
)
HELD = frozenset({"font_of_mythos", "teferi_s_puzzle_box", "dark_deal"})
#: Activated abilities, by card, whose effect is "each player draws".
GROUP_DRAW_ABILITIES = {
    "temple_bell": 0,
    "mikokoro_center_of_the_sea": 1,
    "geier_reach_sanitarium": 1,
    "otherworld_atlas": 1,
}
#: "Target player draws N and loses N" -- a card spell at home, a kill spell
#: across the table once Sheoldred is out.
PACTS = frozenset({"sign_in_blood", "blood_pact", "damnable_pact", "peer_into_the_abyss", "eldritch_pact"})
#: The pacts safe to point at ourselves: a fixed two cards for two life.
SELF_PACTS = frozenset({"sign_in_blood", "blood_pact"})
#: Our own life floor for paying life to draw.
SAFE_LIFE = 10


def pain(state, seat: int) -> int:
    """Life an opponent loses per card drawn, from what we have out right now."""
    return sum(OPPONENT_DRAW_PAIN.get(o.def_id, 0) for o in state.battlefield_objects(seat))


class DrawDeath(Punisher):
    """The Punisher archetype, priced in cards an opponent is forced to draw."""

    def priority_value(self, state, seat, action, base):
        card = cast_card(state, action)
        if card is not None and card.id in PACTS:
            return self._pact_value(state, seat, action, card.id, base)
        value = super().priority_value(state, seat, action, base)
        hurt = pain(state, seat)
        if card is not None and value > 0 and card.id in GROUP_DRAW:
            if card.id in HELD and not hurt:
                return 0.0
            value += 40.0 * hurt
        ability = activated_ability(state, action)
        if ability is not None:
            source = state.objects[action.source]
            if GROUP_DRAW_ABILITIES.get(source.def_id) == action.ability_index:
                if not hurt:
                    return 0.0  # a card for everybody is a card for three opponents
                charges = source.counters.get("charge", 1) if source.def_id == "otherworld_atlas" else 1
                return max(value, 5.0) + 30.0 * hurt * max(1, charges)
            if ability.is_equip:
                value = self._equip_value(state, seat, action, value)
        return value

    def _pact_value(self, state, seat, action, card_id, base) -> float:
        players = [ref.id for ref in action.targets if ref.kind == "player"]
        if not players or base <= 0:
            return 0.0
        pid = players[0]
        if pid == seat:
            # Two cards for two life is a fine draw spell -- Sheoldred even pays
            # it back. The X and half-the-library pacts are never aimed home.
            if card_id in SELF_PACTS and state.players[seat].life > SAFE_LIFE:
                return base
            return 0.0
        victim = state.players[pid]
        draws, loss = _pact_size(state, seat, card_id, pid)
        damage = loss + draws * pain(state, seat)
        if damage >= victim.life:
            return base + 400.0  # it kills: cast it now
        if not pain(state, seat) and card_id != "peer_into_the_abyss":
            # Cards for an opponent and a little life: a gift. Peer still
            # halves a life total, which is worth it on its own.
            return 0.0
        return base + 10.0 * damage + self.player_score(state, seat, pid, "damage")

    def _equip_value(self, state, seat, action, value) -> float:
        """Boots and Greaves belong on Sheoldred, never moved off her."""
        commanders = set(commander_oids(state, seat))
        equipment = state.objects.get(action.source)
        targets = target_objects(state, action)
        if not targets or equipment is None:
            return value
        if targets[0] in commanders:
            return 0.0 if equipment.attached_to == targets[0] else value + 60.0
        if equipment.attached_to in commanders:
            return 0.0
        return value


def _pact_size(state, seat: int, card_id: str, pid: int) -> tuple[int, int]:
    """(cards drawn, life lost directly) for one pact aimed at ``pid``."""
    victim = state.players[pid]
    if card_id in SELF_PACTS:
        return 2, 2
    if card_id == "damnable_pact":
        x = max(0, available_mana(state, seat) - 2)
        return x, x
    if card_id == "peer_into_the_abyss":
        return ceil(len(victim.library) / 2), ceil(victim.life / 2)
    if card_id == "eldritch_pact":
        n = len(victim.graveyard)
        return n, n
    return 0, 0


STRATEGY = DrawDeath(
    DeckPlan(
        deck_id="sheoldred_the_apocalypse",
        archetype="punisher",
        commanders=frozenset({SHEOLDRED}),
        key_cards={
            SHEOLDRED: 120.0,
            "underworld_dreams": 60.0,
            "sol_ring": 80.0,
            "arcane_signet": 30.0,
            "jet_medallion": 20.0,
            "crypt_ghast": 40.0,
            "lightning_greaves": 40.0,
            "swiftfoot_boots": 40.0,
            "sanguine_bond": 40.0,
            "vito_thorn_of_the_dusk_rose": 40.0,
            "marauding_blight_priest": 30.0,
            "phyrexian_arena": 40.0,
        },
        combos=(
            # Not loops -- the list has no Exquisite Blood -- but each turns a
            # draw into two drains: Sheoldred's lifegain for our cards is
            # mirrored onto an opponent.
            Combo("Sheoldred + Sanguine Bond", frozenset({SHEOLDRED, "sanguine_bond"}), 120.0),
            Combo("Sheoldred + Vito", frozenset({SHEOLDRED, "vito_thorn_of_the_dusk_rose"}), 120.0),
            Combo("Puzzle Box under Sheoldred", frozenset({SHEOLDRED, "teferi_s_puzzle_box"}), 150.0),
        ),
        win_cons=frozenset(
            {"underworld_dreams", "peer_into_the_abyss", "damnable_pact", "gray_merchant_of_asphodel"}
        ),
        protect=frozenset({"lightning_greaves", "swiftfoot_boots", "font_of_mythos", "howling_mine"}),
        keep_lands=(3, 5),
        aggression=0.4,
    )
)
