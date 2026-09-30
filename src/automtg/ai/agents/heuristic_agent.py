"""A reflexive, rule-ordered opponent.

No search, no lookahead, no cloning -- it scores each legal action from the
current position and takes the best one.  That is deliberate: undo and env resets
work by replay rather than by copying state, so an agent that wanted to explore
hypotheticals would have to replay whole games to do it.

The point of this agent is twofold: it is the "reasonably competent player" the
app needs on the other side of the table, and it is the benchmark a trained
policy has to beat before it is worth anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from automtg.engine.actions import Action
from automtg.engine.carddef import CardDef
from automtg.engine.characteristics import abilities_of, chars
from automtg.engine.combat import can_block
from automtg.engine.costs import life_cost
from automtg.engine.enums import ActionKind, DecisionKind, Keyword, Step
from automtg.engine.rng import Rng

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.game import Game
    from automtg.engine.state import GameState

#: Life total below which chump blocking becomes worthwhile.
DESPERATE_LIFE = 10
#: Cheapest opposing spell worth spending a counterspell on.
COUNTER_THRESHOLD = 3
#: Effect ops that only make the source bigger or harder to kill this turn.
#: An ability whose whole effect is one of these is a combat trick, and worth
#: nothing at all outside combat.
COMBAT_TRICK_OPS = frozenset({"pump", "grant_keyword"})
#: Counter kinds that hurt the permanent's controller, so proliferate grows
#: them on an opponent's permanent and never on ours.
HARMFUL_COUNTERS = frozenset({"-1/-1", "stun"})


class HeuristicAgent:
    name = "heuristic"

    def __init__(self, seed: int = 0) -> None:
        self.rng = Rng(seed)

    # ------------------------------------------------------------------

    def act(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        decision = game.pending()
        assert decision is not None
        kind = decision.kind

        if kind is DecisionKind.MULLIGAN:
            return self._mulligan(game, seat, actions)
        if kind is DecisionKind.DECLARE_ATTACKERS:
            return self._attack(game, seat, actions)
        if kind is DecisionKind.DECLARE_BLOCKERS:
            return self._block(game, seat, actions)
        if kind is DecisionKind.PRIORITY:
            return self._priority(game, seat, actions)
        return self._choice(game, seat, actions, decision)

    # ------------------------------------------------------------------
    # mulligans
    # ------------------------------------------------------------------

    def _mulligan(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        """Keep on two to five lands; anything else is a mulligan."""
        state = game.state
        player = state.players[seat]
        lands = sum(1 for oid in player.hand if state.card(oid).is_land)
        keep = 2 <= lands <= 5 or player.mulligans_taken >= 2
        want = ActionKind.KEEP if keep else ActionKind.MULLIGAN
        return _first(actions, want) or actions[0]

    # ------------------------------------------------------------------
    # combat
    # ------------------------------------------------------------------

    def _attack(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        state = game.state
        attacks = [a for a in actions if a.kind is ActionKind.ADD_ATTACKER]
        if not attacks:
            return _first(actions, ActionKind.FINISH_DECLARATION) or actions[0]

        target = self._best_defender(state, seat)
        best: tuple[float, Action] | None = None
        for action in attacks:
            if action.targets and action.targets[0].id != target:
                continue
            score = self._attack_value(state, seat, action.source, target)
            if score > 0 and (best is None or score > best[0]):
                best = (score, action)
        if best is not None:
            return best[1]
        return _first(actions, ActionKind.FINISH_DECLARATION) or actions[0]

    def _best_defender(self, state: GameState, seat: int) -> int:
        """Attack whoever is closest to dying, breaking ties on board strength."""
        opponents = state.opponents(seat)
        return min(
            opponents,
            key=lambda pid: (
                state.players[pid].life,
                sum(chars(state, o.oid).toughness for o in _creatures(state, pid)),
                pid,
            ),
        )

    def _attack_value(self, state: GameState, seat: int, oid: int, defender: int) -> float:
        """How good is swinging with this creature?  Non-positive means "hold it back"."""
        mine = chars(state, oid)
        if mine.power <= 0:
            return 0.0

        blockers = [
            o
            for o in _creatures(state, defender)
            if not o.tapped and can_block(state, o.oid, oid, defender)
        ]
        if not blockers:
            # Unblockable damage; commander damage counts double towards a kill.
            bonus = 4.0 if state.objects[oid].is_commander else 0.0
            return mine.power + bonus

        best_blocker = max(blockers, key=lambda o: chars(state, o.oid).power)
        block_power = chars(state, best_blocker.oid).power
        kills_something = any(
            mine.power >= chars(state, o.oid).toughness
            or Keyword.DEATHTOUCH.value in mine.keywords
            for o in blockers
        )
        survives = mine.toughness > block_power or Keyword.INDESTRUCTIBLE.value in mine.keywords

        if survives and kills_something:
            return mine.power + 3.0
        if survives:
            return mine.power * 0.5
        if kills_something:
            # A trade is fine when we have more creatures than they do.
            if len(_creatures(state, seat)) > len(_creatures(state, defender)):
                return 1.0
            return 0.0
        return 0.0

    def _block(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        state = game.state
        blocks = [a for a in actions if a.kind is ActionKind.ADD_BLOCKER]
        done = _first(actions, ActionKind.FINISH_DECLARATION)
        if not blocks:
            return done or actions[0]

        desperate = state.players[seat].life <= DESPERATE_LIFE
        best: tuple[float, Action] | None = None
        for action in blocks:
            score = self._block_value(state, seat, action.source, action.targets[0].id, desperate)
            if score > 0 and (best is None or score > best[0]):
                best = (score, action)
        if best is not None:
            return best[1]
        return done or blocks[0]

    def _block_value(
        self, state: GameState, seat: int, blocker: int, attacker: int, desperate: bool
    ) -> float:
        mine = chars(state, blocker)
        theirs = chars(state, attacker)
        kills = mine.power >= theirs.toughness or Keyword.DEATHTOUCH.value in mine.keywords
        dies = theirs.power >= mine.toughness and (
            Keyword.INDESTRUCTIBLE.value not in mine.keywords
        )

        if kills and not dies:
            return 10.0 + theirs.power
        if kills and dies:
            return 4.0 + theirs.power - mine.power
        if not dies:
            return 2.0
        if desperate:
            return 1.0 + theirs.power * 0.1  # chump to stay alive
        return 0.0

    # ------------------------------------------------------------------
    # priority
    # ------------------------------------------------------------------

    def _priority(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        state = game.state
        best: tuple[float, Action] | None = None
        for action in actions:
            score = self._priority_value(state, seat, action)
            if score > 0 and (best is None or score > best[0]):
                best = (score, action)
        if best is not None:
            return best[1]
        return _first(actions, ActionKind.PASS) or actions[0]

    def _priority_value(self, state: GameState, seat: int, action: Action) -> float:
        if action.kind is ActionKind.PASS:
            return 0.0
        if action.kind is ActionKind.PLAY_LAND:
            return 1000.0  # a missed land drop is the most expensive mistake there is

        if action.kind is ActionKind.ACTIVATE:
            return self._activate_value(state, seat, action)

        if action.kind is not ActionKind.CAST:
            return 0.0

        card = state.card(action.source)
        role = classify(card)
        sorcery_speed = state.active_player == seat and state.step in (
            Step.PRECOMBAT_MAIN,
            Step.POSTCOMBAT_MAIN,
        )

        if role == "counter":
            return self._counter_value(state, seat, action)
        if role == "removal":
            return self._removal_value(state, seat, action, card)
        if role == "pump":
            # Only worth it mid-combat, and only on our own creature.
            if state.step is not Step.DECLARE_BLOCKERS:
                return 0.0
            return 20.0 if self._targets_own(state, seat, action) else 0.0

        # Everything else is a sorcery-speed play.
        if not sorcery_speed or state.stack:
            return 0.0
        if role == "ramp":
            return 400.0 - state.turn * 5
        if role == "draw":
            return 200.0
        if role == "creature":
            return 300.0 + card.mana_value * 8 + (card.power or 0) * 3
        return 100.0 + card.mana_value

    def _activate_value(self, state: GameState, seat: int, action: Action) -> float:
        """How good is activating this ability?  Non-positive means "don't".

        Every activation used to score a flat 5.0, which beat passing at every
        priority window -- so the agent activated the same ability again the
        instant it resolved, and kept going until the cost became unpayable.
        Adanto Vanguard's "Pay 4 life" took it from 40 to 3 for one turn of
        indestructible; Bloodthrone Vampire ate its own board a creature at a
        time.  Three rules fix that, in order of how much damage they undo.

        The first is the important one: **once per ability per turn**.  The
        turn ledger already counts activations for forecast and loyalty, and
        `Game._activate` bumps it before the cost is paid, so the ability
        scores zero even while it is still on the stack.  It does cap a
        genuinely repeatable pump (firebreathing) at one activation a turn --
        a real cost, and much cheaper than the alternative, because this agent
        has no notion of how much power it needs.
        """
        oid, index = action.source, action.ability_index
        if oid is None or index is None:
            return 5.0
        abilities = abilities_of(state, oid)
        if not 0 <= index < len(abilities):
            # Turning a face-down creature up is an ACTIVATE borrowing index 0
            # of a permanent with no abilities at all; see
            # `legality._turn_face_up_actions`.
            return 5.0
        ability = abilities[index]
        if ability.is_mana_ability:
            # By-hand mana (a Signet, a Vivid land) never reaches the ledger,
            # and tapping already stops it repeating.  The mana it floats is
            # what the next pass spends.
            return 5.0
        if state.turn_ledger.activations(oid, index):
            return 0.0

        # Life is a resource this agent otherwise never prices, and an ability
        # that *can* be paid for is not the same as one worth paying for.  The
        # chump-blocking threshold does duty here too.
        cost = ability.cost
        if (
            cost is not None
            and cost.pay_life
            and state.players[seat].life - life_cost(state, seat, cost, oid) <= DESPERATE_LIFE
        ):
            return 0.0

        ops = {effect.get("op") for effect in ability.effects}
        if ops and ops <= COMBAT_TRICK_OPS:
            if cost is not None and cost.sacrifice is not None:
                # A creature on the board is worth more than +2/+2 for a turn.
                return 0.0
            if state.step is not Step.DECLARE_BLOCKERS or not _in_combat(state, oid):
                # The same rule the "pump" spell bucket follows below: a trick
                # spent before blocks are known usually buys nothing.
                return 0.0
            granted = {
                str(keyword).lower()
                for effect in ability.effects
                if effect.get("op") == "grant_keyword"
                for keyword in (
                    effect.get("keywords") or ([effect["keyword"]] if "keyword" in effect else [])
                )
            }
            if granted and granted <= chars(state, oid).keywords:
                return 0.0  # it already has what this would grant
            return 20.0  # the pump-spell weight, so it outranks a plain activation
        return 5.0

    def _counter_value(self, state: GameState, seat: int, action: Action) -> float:
        for ref in action.targets:
            if ref.kind != "stack":
                continue
            item = state.stack_item(ref.id)
            if item is None or item.controller == seat:
                continue
            spell = state.registry.get(item.def_id)
            if spell.mana_value >= COUNTER_THRESHOLD:
                return 500.0 + spell.mana_value * 10
        return 0.0

    def _removal_value(
        self, state: GameState, seat: int, action: Action, card: CardDef
    ) -> float:
        best = 0.0
        for ref in action.targets:
            if ref.kind == "player":
                continue
            obj = state.objects.get(ref.id)
            if obj is None:
                continue
            if obj.controller == seat:
                return 0.0  # never point removal at our own board
            value = chars(state, ref.id).power * 10 + state.card_of(obj).mana_value * 5
            if obj.is_commander:
                value += 40
            best = max(best, value)
        return (350.0 + best) if best > 0 else 0.0

    def _targets_own(self, state: GameState, seat: int, action: Action) -> bool:
        return any(
            ref.kind == "object"
            and state.objects.get(ref.id) is not None
            and state.objects[ref.id].controller == seat
            for ref in action.targets
        )

    # ------------------------------------------------------------------
    # effect choices
    # ------------------------------------------------------------------

    def _choice(self, game: Game, seat: int, actions: Sequence[Action], decision) -> Action:
        """Answer a choice raised by a resolving effect."""
        if decision.kind is DecisionKind.MAY:
            return _first(actions, ActionKind.YES) or actions[0]

        purpose = str(decision.context.get("purpose", "choose"))
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        if not choices:
            return actions[0]

        state = game.state
        # X is not a menu item to pick the first of: `choices[0]` is X = 0,
        # which casts Blue Sun's Zenith for nothing. Spending everything is both
        # the better play in almost every position and exactly what the agent
        # saw before `CHOOSE_X` existed, when legality pinned X to the maximum.
        if purpose == "choose_x":
            return max(choices, key=lambda a: a.choice or 0)
        if purpose == "sacrifice":
            return min(choices, key=lambda a: self._creature_value(state, a))
        if purpose in ("discard", "scry_bottom", "surveil"):
            return max(choices, key=lambda a: self._card_junk_score(state, a))
        if purpose == "search":
            return max(choices, key=lambda a: self._land_search_score(state, seat, a))
        if purpose == "destroy":
            return max(choices, key=lambda a: self._creature_value(state, a))
        if purpose == "remove_counter_cost":
            # Take a counter off whatever misses it least: a harmful one first,
            # then the permanent carrying the most, never the last loyalty on a
            # planeswalker while anything else will do.
            return max(choices, key=lambda a: self._counter_spare(state, a))
        if purpose == "choose_card_name":
            # The first label is alphabetical, not good: name whatever this
            # seat's library holds most copies of, so a Tamiyo look is likeliest
            # to hit.
            return max(choices, key=lambda a: self._name_hits(state, seat, decision, a))
        if purpose == "proliferate":
            # A free multi-select: `choices[0]` would grow whatever came first
            # -- an opponent's planeswalker, the -1/-1 counters on our own
            # creature -- and then the next, until everything had grown.
            wanted = [a for a in choices if self._proliferate_helps(state, seat, a)]
            return wanted[0] if wanted else _first(actions, ActionKind.FINISH_DECLARATION) or choices[0]
        if purpose == "choose_direction":
            # Aminatou's rotation: `choices[0]` is always "left", whatever sits
            # there. Take the richer board -- we lose ours either way.
            seats = list(decision.context.get("takes_from") or [])
            return max(choices, key=lambda a: self._board_worth(state, seats, a))
        return choices[0]

    def _name_hits(self, state: GameState, seat: int, decision, action: Action) -> int:
        """How many cards in this seat's library carry the label this action names."""
        index = action.choice
        if index is None or not 0 <= index < len(decision.options):
            return 0
        label = decision.options[index].label
        return sum(
            1
            for oid in state.players[seat].library
            if state.card_of(state.objects[oid]).name == label
        )

    def _board_worth(self, state: GameState, seats: Sequence[int], action: Action) -> int:
        """Total mana value of the nonland permanents the seat behind this answer controls."""
        index = action.choice if action.choice is not None else -1
        if not 0 <= index < len(seats):
            return 0
        return sum(
            state.card_of(obj).mana_value
            for obj in state.battlefield_objects(seats[index])
            if not state.card_of(obj).is_land
        )

    def _counter_spare(self, state: GameState, action: Action) -> tuple[int, int, int]:
        """How little one counter off this permanent costs us -- higher is better."""
        oid = _target_oid(action)
        obj = state.objects.get(oid) if oid is not None else None
        if obj is None:
            return (0, 0, 0)
        held = {kind: n for kind, n in obj.counters.items() if n > 0}
        harmful = any(kind in HARMFUL_COUNTERS for kind in held)
        last_loyalty = held.get("loyalty", 0) == 1 and len(held) == 1
        return (int(harmful), int(not last_loyalty), sum(held.values()))

    def _proliferate_helps(self, state: GameState, seat: int, action: Action) -> bool:
        """Is one more of every counter already on this permanent or player good for us?

        Ours when none of its counters hurts its controller (loyalty, +1/+1,
        charge, lore); theirs when every one of them does (-1/-1, stun). A
        player's only counter is poison, which is good on anybody but us.
        """
        if not action.targets:
            return False
        ref = action.targets[0]
        if ref.kind == "player":
            return ref.id != seat
        obj = state.objects.get(ref.id)
        if obj is None:
            return False
        kinds = [kind for kind, n in obj.counters.items() if n > 0]
        if not kinds:
            return False
        harmful = [kind in HARMFUL_COUNTERS for kind in kinds]
        return not any(harmful) if obj.controller == seat else all(harmful)

    def _creature_value(self, state: GameState, action: Action) -> float:
        oid = _target_oid(action)
        if oid is None or oid not in state.objects:
            return 0.0
        c = chars(state, oid)
        return c.power + c.toughness + state.card_of(state.objects[oid]).mana_value

    def _card_junk_score(self, state: GameState, action: Action) -> float:
        """Higher means "get rid of this one first"."""
        oid = _target_oid(action)
        if oid is None or oid not in state.objects:
            return 0.0
        card = state.card(oid)
        # Excess lands and the most expensive spells are the first to go.
        return 5.0 if card.is_land else float(card.mana_value)

    def _land_search_score(self, state: GameState, seat: int, action: Action) -> float:
        """Fetch the basic covering the colour we are shortest of."""
        oid = _target_oid(action)
        if oid is None or oid not in state.objects:
            return 0.0
        card = state.card(oid)
        if not card.is_land:
            return 0.0
        produced = set(card.color_identity)
        if not produced:
            return 1.0
        have = {colour: 0 for colour in produced}
        for other in state.battlefield_objects(seat):
            for colour in state.card_of(other).color_identity:
                if colour in have:
                    have[colour] += 1
        return 10.0 - min(have.values())


# ----------------------------------------------------------------------


def classify(card: CardDef) -> str:
    """Bucket a card by what it is for, from the ops it actually uses."""
    ops = {effect.get("op") for effect in _walk(card)}
    if "counter" in ops:
        return "counter"
    if ops & {"destroy", "exile"} and card.targets:
        return "removal"
    if "search_library" in ops:
        return "ramp"
    if ops & {"pump", "grant_keyword"} and card.targets:
        return "pump"
    if "draw" in ops and not card.is_permanent:
        return "draw"
    if card.is_creature:
        return "creature"
    return "other"


def _walk(card: CardDef):
    def walk(effects):
        for effect in effects:
            yield effect
            for key in ("then", "else", "effects"):
                yield from walk(effect.get(key) or [])
            for mode in effect.get("modes", []) or []:
                yield from walk(mode.get("effects") or [])

    yield from walk(card.spell_effects)


def _in_combat(state: GameState, oid: int) -> bool:
    """Is this creature attacking or blocking right now?"""
    combat = state.combat
    return combat is not None and (oid in combat.attackers or oid in combat.blockers)


def _creatures(state: GameState, pid: int):
    return [o for o in state.battlefield_objects(pid) if "Creature" in chars(state, o.oid).types]


def _first(actions: Sequence[Action], kind: ActionKind) -> Action | None:
    for action in actions:
        if action.kind is kind:
            return action
    return None


def _target_oid(action: Action) -> int | None:
    for ref in action.targets:
        if ref.kind == "object":
            return ref.id
    return None
