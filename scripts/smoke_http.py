"""Play a whole game against a running server, exactly as the browser client does.

    python scripts/smoke_http.py --url http://127.0.0.1:8000 --players 2
    python scripts/smoke_http.py --pod --players 2

This is the closest thing to the manual browser gate that a script can do: it
uses the same endpoints, the same opaque action ids, and the same
"select all, confirm" combat submission the React client uses.

``--pod`` drives the multiplayer path instead: create a pod, join it as N-1
other people, everybody picks a deck and locks in, the host deals, and the game
is then played with each seat acting only through its own token.  Every request
carries the header a browser would carry, so this exercises the authorisation
boundary as well as the flow.
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


def call(
    url: str,
    path: str,
    body: dict | None = None,
    method: str | None = None,
    *,
    token: str | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Player-Token"] = token
    request = urllib.request.Request(
        f"{url}{path}",
        data=data,
        method=method or ("POST" if data else "GET"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} -> {exc.code}: {exc.read().decode()[:300]}") from None


def expect_status(
    url: str,
    path: str,
    body: dict | None,
    want: int,
    *,
    method: str | None = None,
    token: str | None = None,
) -> None:
    """Assert a request is *refused* with a particular status.

    The point of the pod path is that a seat cannot be driven by somebody who
    does not hold its token, and a smoke test that only exercised the happy path
    would pass just as well with the check deleted.
    """
    try:
        call(url, path, body, method, token=token)
    except RuntimeError as exc:
        if f"-> {want}:" in str(exc):
            return
        raise RuntimeError(f"expected {want} from {path}, got: {exc}") from None
    raise RuntimeError(f"expected {want} from {path}, but it succeeded")


def pick(actions: list[dict]) -> dict:
    for kind in PREFERRED:
        for action in actions:
            if action["kind"] == kind:
                return action
    return actions[0]


def act(
    url: str,
    game_id: str,
    seat: int,
    state: dict,
    actions: list[dict],
    *,
    token: str | None = None,
    verbose: bool = False,
) -> tuple[dict, bool]:
    """Take one decision for ``seat``.  Returns the new payload and whether it
    was a combat declaration."""
    pending = state.get("pending") or {}
    attacks = [a for a in actions if a["kind"] == "add_attacker"]
    if pending.get("kind") == "declare_attackers" and attacks:
        # One defender per attacker: in a pod, legality offers the same creature
        # against every opponent, but it can only attack one.
        chosen_defender: dict[int, int] = {}
        for a in attacks:
            chosen_defender.setdefault(a["source_oid"], a["targets"][0]["id"])
        pairs = [[oid, defender] for oid, defender in chosen_defender.items()]
        payload = call(
            url,
            f"/api/games/{game_id}/declare",
            {"seat": seat, "kind": "attackers", "pairs": pairs},
            token=token,
        )
        return payload, True

    chosen = pick(actions)
    if verbose:
        print(f"  T{state['turn']} {state['step']} p{seat}: {chosen['label']}")
    payload = call(
        url,
        f"/api/games/{game_id}/actions",
        {"seat": seat, "action_id": chosen["id"]},
        token=token,
    )
    return payload, False


def play(
    url: str,
    players: int,
    seed: int,
    verbose: bool,
    deck: str = "aesi",
    opponent_deck: str = "edgar",
) -> int:
    seats = [{"deck_id": deck, "kind": "human", "name": "You"}]
    for i in range(1, players):
        seats.append(
            {
                "deck_id": opponent_deck if i % 2 else deck,
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

        payload, declared = act(url, game_id, 0, state, actions, verbose=verbose)
        combat_used = combat_used or declared
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


DECKS = ("aesi", "edgar", "isperia", "zurgo")


def play_pod(url: str, players: int, seed: int, verbose: bool) -> int:
    """Create a pod, fill it with ``players`` humans, deal it, and play it out.

    Every request from here on carries the player's own token, so this fails if
    the authorisation boundary is wrong in either direction: too tight and the
    rightful seat is refused, too loose and the deliberate cross-seat attempts
    below succeed.
    """
    opened = call(
        url, "/api/pods", {"name": "P0", "deck_id": DECKS[0], "seed": seed}
    )
    code = opened["pod"]["code"]
    tokens = [opened["player_token"]]
    print(f"pod {code}: {players} players, seed {seed}")

    for i in range(1, players):
        joined = call(url, f"/api/pods/{code}/join", {"name": f"P{i}"})
        tokens.append(joined["player_token"])
        call(
            url,
            f"/api/pods/{code}/seat",
            {"deck_id": DECKS[i % len(DECKS)], "locked": True},
            method="PATCH",
            token=tokens[i],
        )

    # A guest's deck must be invisible to the host, and only the host may deal.
    if players > 1:
        call(url, f"/api/pods/{code}/seat", {"locked": False}, method="PATCH", token=tokens[1])
        seen = call(url, f"/api/pods/{code}", token=tokens[0])["seats"][1]["deck"]
        if seen is not None:
            print("FAIL an unlocked guest's deck was visible to the host")
            return 1
        call(url, f"/api/pods/{code}/seat", {"locked": True}, method="PATCH", token=tokens[1])
        expect_status(url, f"/api/pods/{code}/start", None, 403, method="POST", token=tokens[1])

    call(url, f"/api/pods/{code}/seat", {"locked": True}, method="PATCH", token=tokens[0])
    view = call(url, f"/api/pods/{code}/start", None, "POST", token=tokens[0])
    game_id = view["game_id"]
    if view["status"] != "in_game" or not game_id:
        print(f"FAIL the pod did not deal: {view['status']}")
        return 1

    # Everybody learns their table seat from their own token.
    seats: dict[int, str] = {}
    for token in tokens:
        seats[call(url, f"/api/games/{game_id}/state", token=token)["your_seat"]] = token
    if sorted(seats) != list(range(players)):
        print(f"FAIL seats did not compact cleanly: {sorted(seats)}")
        return 1
    print(f"game {game_id}: seats {sorted(seats)} dealt from the pod")

    # One seat must not be drivable by another seat's token.
    if players > 1:
        expect_status(url, f"/api/games/{game_id}/state?seat=0", None, 403, token=seats[1])
        expect_status(url, f"/api/games/{game_id}/state?seat=1", None, 403, token=None)

    hidden_ok = True
    combat_used = False
    steps = 0
    state = call(url, f"/api/games/{game_id}/state", token=seats[0])["state"]

    while steps < 6000:
        if state["game_over"]:
            break
        pending = state.get("pending")
        if pending is None:
            break
        seat = pending["player"]
        view = call(url, f"/api/games/{game_id}/state", token=seats[seat])
        if not view["actions"]:
            raise RuntimeError(f"no actions offered to p{seat} at turn {state['turn']}")

        payload, declared = act(
            url,
            game_id,
            seat,
            view["state"],
            view["actions"],
            token=seats[seat],
            verbose=verbose,
        )
        combat_used = combat_used or declared
        state = payload["state"]
        hidden_ok = hidden_ok and all(
            player["hand"] is None for i, player in enumerate(state["players"]) if i != seat
        )
        steps += 1

    if not state["game_over"]:
        print(f"FAIL game did not finish in {steps} client actions")
        return 1
    if not hidden_ok:
        print("FAIL another seat's hand contents were visible")
        return 1
    if not combat_used:
        print("WARN never reached a combat declaration")

    winners = ", ".join(f"p{w}" for w in state["winners"]) or "nobody"
    print(
        f"OK   finished on turn {state['turn']} after {steps} client actions: "
        f"{winners} ({state['result']}); every seat saw only its own hand"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--players", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--pod",
        action="store_true",
        help="drive the multiplayer lobby: every player is a human with a token",
    )
    parser.add_argument("--verbose", action="store_true")
    # The fixture lists by default, which the test servers serve. A shipped
    # build serves only the precons, so `desktop/sidecar/smoke.sh` names two.
    parser.add_argument("--deck", default="aesi", help="your seat's deck id")
    parser.add_argument("--opponent-deck", default="edgar", help="the odd seats' deck id")
    args = parser.parse_args()

    health = call(args.url, "/health")
    print(f"server ok: {health['cards']} cards, decks {health['decks']}")
    if args.pod:
        return play_pod(args.url, args.players, args.seed, args.verbose)
    return play(
        args.url, args.players, args.seed, args.verbose, args.deck, args.opponent_deck
    )


if __name__ == "__main__":
    raise SystemExit(main())
