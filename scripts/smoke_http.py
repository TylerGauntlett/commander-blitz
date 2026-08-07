"""Play a whole game against a running server, exactly as the browser client does.

    python scripts/smoke_http.py --url http://127.0.0.1:8000 --players 2

This is the closest thing to the manual browser gate that a script can do: it
uses the same endpoints, the same opaque action ids, and the same
"select all, confirm" combat submission the React client uses.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

#: Preference order for the crude client policy: act rather than pass.
PREFERRED = (
    "play_land",
    "cast",
    "activate",
    "choose",
    "yes",
    "keep",
    "finish_declaration",
    "pass",
)


def call(url: str, path: str, body: dict | None = None, method: str | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{url}{path}",
        data=data,
        method=method or ("POST" if data else "GET"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} -> {exc.code}: {exc.read().decode()[:300]}") from None


def pick(actions: list[dict]) -> dict:
    for kind in PREFERRED:
        for action in actions:
            if action["kind"] == kind:
                return action
    return actions[0]


def play(url: str, players: int, seed: int, verbose: bool) -> int:
    seats = [{"deck_id": "aesi", "kind": "human", "name": "You"}]
    for i in range(1, players):
        seats.append(
            {
                "deck_id": "edgar" if i % 2 else "aesi",
                "kind": "ai",
                "agent": "heuristic",
                "name": f"AI {i}",
            }
        )

    created = call(url, "/api/games", {"seats": seats, "seed": seed})
    game_id = created["game_id"]
    state, actions = created["state"], created["actions"]
    print(f"game {game_id}: {players} players, seed {seed}")

    hidden_ok = state["players"][1]["hand"] is None
    combat_used = False
    steps = 0

    while steps < 6000:
        if state["game_over"]:
            break
        if not actions:
            raise RuntimeError(f"no actions offered at turn {state['turn']} {state['step']}")

        pending = state.get("pending") or {}
        attacks = [a for a in actions if a["kind"] == "add_attacker"]
        if pending.get("kind") == "declare_attackers" and attacks:
            # One defender per attacker: in a pod, legality offers the same
            # creature against every opponent, but it can only attack one.
            chosen_defender: dict[int, int] = {}
            for a in attacks:
                chosen_defender.setdefault(a["source_oid"], a["targets"][0]["id"])
            pairs = [[oid, defender] for oid, defender in chosen_defender.items()]
            payload = call(
                url,
                f"/api/games/{game_id}/declare",
                {"seat": 0, "kind": "attackers", "pairs": pairs},
            )
            combat_used = True
        else:
            chosen = pick(actions)
            if verbose:
                print(f"  T{state['turn']} {state['step']}: {chosen['label']}")
            payload = call(
                url,
                f"/api/games/{game_id}/actions",
                {"seat": 0, "action_id": chosen["id"]},
            )
        state, actions = payload["state"], payload["actions"]
        hidden_ok = hidden_ok and state["players"][1]["hand"] is None
        steps += 1

    call(url, f"/api/games/{game_id}", method="DELETE")

    if not state["game_over"]:
        print(f"FAIL game did not finish in {steps} client actions")
        return 1
    if not hidden_ok:
        print("FAIL opponent hand contents leaked through the player view")
        return 1
    if not combat_used:
        print("WARN never reached a combat declaration")

    winners = ", ".join(f"p{w}" for w in state["winners"]) or "nobody"
    print(
        f"OK   finished on turn {state['turn']} after {steps} client actions: "
        f"{winners} ({state['result']}); hidden information held"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--players", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    health = call(args.url, "/health")
    print(f"server ok: {health['cards']} cards, decks {health['decks']}")
    return play(args.url, args.players, args.seed, args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
