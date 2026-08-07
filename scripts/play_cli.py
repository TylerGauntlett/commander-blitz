"""Play a game in the terminal.  The fastest way to poke at the engine.

    python scripts/play_cli.py                    # you vs the heuristic AI
    python scripts/play_cli.py --players 4        # a four-player pod
    python scripts/play_cli.py --auto heuristic   # watch two bots play
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from automtg.ai.agents.base import agent_by_name
from automtg.engine.characteristics import chars
from automtg.engine.game import Game, create_game

BAR = "-" * 78


def render(game: Game, seat: int) -> str:
    state = game.state
    lines = [BAR, f"Turn {state.turn}  {state.step.name}  active=p{state.active_player}"]
    for player in state.players:
        tag = "OUT" if player.has_lost else f"{player.life} life"
        marker = ">" if player.pid == seat else " "
        lines.append(
            f"{marker} p{player.pid} {player.name:<10} {tag:<9} "
            f"hand={len(player.hand):<2} library={len(player.library):<2} "
            f"gy={len(player.graveyard):<2} cmd={len(player.command)}"
        )
        board = state.battlefield_objects(player.pid)
        if board:
            lines.append("    " + ", ".join(_permanent(state, o) for o in board))
    if state.stack:
        lines.append("  stack: " + " | ".join(item.description for item in reversed(state.stack)))
    hand = state.players[seat].hand
    if hand:
        lines.append("  your hand: " + ", ".join(state.card(oid).name for oid in hand))
    return "\n".join(lines)


def _permanent(state, obj) -> str:
    card = state.card_of(obj)
    text = card.name
    if "Creature" in card.types:
        derived = chars(state, obj.oid)
        text += f" {derived.power}/{derived.toughness - obj.damage}"
    if obj.tapped:
        text += "(T)"
    if obj.is_commander:
        text += "*"
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players", type=int, default=2, choices=(2, 3, 4))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seat", type=int, default=0, help="which seat you play")
    parser.add_argument("--opponent", default="heuristic", choices=("random", "heuristic"))
    parser.add_argument(
        "--auto", default=None, help="play every seat with this agent and just watch"
    )
    parser.add_argument("--quiet", action="store_true", help="only print the result")
    args = parser.parse_args()

    decks = ["aesi", "edgar"] * 2
    game = create_game(decks[: args.players], seed=args.seed)

    agents = {
        pid: agent_by_name(args.auto or args.opponent, seed=args.seed + pid)
        for pid in range(args.players)
    }
    human = None if args.auto else args.seat

    while not game.over:
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break

        if decision.player != human:
            game.apply(agents[decision.player].act(game, decision.player, actions))
            continue

        print(render(game, human))
        print(f"\n{decision.prompt or decision.kind.value}:")
        for i, action in enumerate(actions):
            print(f"  [{i}] {action.label or action.kind.value}")
        raw = input("> ").strip()
        if raw in ("q", "quit"):
            return 0
        try:
            choice = int(raw)
            action = actions[choice]
        except (ValueError, IndexError):
            print("  (not a valid choice)")
            continue
        game.apply(action)

    if not args.quiet:
        print(render(game, human or 0))
    winners = ", ".join(f"p{w}" for w in game.winners) or "nobody"
    print(f"\n{BAR}\nGame over after {game.state.turn} turns: {winners} wins ({game.state.result})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
