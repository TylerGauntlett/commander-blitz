# Commander Blitz

[commanderblitz.com](https://commanderblitz.com)

A Magic: The Gathering **Commander** rules engine, a self-play training layer, and the
client that plays it — built so the rules live in exactly one place and everything
else is a driver on top of them.

The Python package is still `automtg`: the project was named that first, and the
name is an import path rather than something anybody reads. The rename stopped at
the surfaces a player sees.

```
automtg.engine   pure, deterministic rules engine (no I/O, no ML, no HTTP)
automtg.cards    JSON card definitions, validated and compiled at load time
automtg.ai       Gymnasium environment, agents, headless arena, PPO trainer
automtg.server   FastAPI application exposing the engine
frontend/        React + Vite playtest client
```

The engine is a state machine that advances until it needs a decision from a player.
A human clicking in the browser and a policy sampling an action index both end up
calling the same `Game.apply(action)`, so there is one code path for "a player did
something" and no way for the UI and the AI to disagree about the rules.

## Quickstart

```bash
py -3.13 -m venv .venv                      # 3.13: what CI and the image run
.venv/Scripts/pip install -c constraints.txt -e ".[dev]"   # add ",train" for the PPO trainer

python scripts/validate_decks.py            # card files and deck legality
pytest                                      # the full suite
python scripts/play_cli.py                  # play in the terminal
python scripts/run_arena.py --games 100     # headless duels, with a report
```

To play in the browser, run the API and the client in two terminals:

```bash
.venv/Scripts/uvicorn automtg.server.app:get_app --factory --reload
cd frontend && bun install && bun run dev     # or: npm install && npm run dev
```

Then open <http://localhost:5173>. The Vite dev server proxies `/api` to the engine.

To browse the components on their own — every state of every panel, no engine needed:

```bash
cd frontend && npm run storybook            # port 6006
npx playwright install chromium             # one time, to run the stories as tests
npm run test:stories
```

### Playing over a LAN

Two to four people on the same network share one engine process. Bind both servers to
the network rather than to loopback — the dev server pins `127.0.0.1` by default:

```bash
.venv/Scripts/uvicorn automtg.server.app:get_app --factory --host 0.0.0.0
cd frontend && npm run dev -- --host
```

Then everybody opens `http://<your-lan-ip>:5173`. One person creates a pod and reads
out the code (`GYRE-8412`); the rest join with it, pick a deck, and lock in. CORS is
open to private-network origins only, so this stays reachable from a network you are
already on and nowhere else.

## What is in the box

| | |
|---|---|
| **Decks** | Two Commander-legal 100-card decks: *Aesi, Tyrant of Gyre Strait* (Simic ramp/landfall) and *Edgar Markov* (Mardu vampire aggro). Every card in both decks is implemented and tested. |
| **Rules** | Full turn structure, the stack, priority, triggered and static abilities, combat with ten keyword abilities, state-based actions, commander tax and commander damage, and N-player pods. |
| **Multiplayer** | Two to four people, each in their own browser against one process. Create a pod, share the code, pick decks privately, lock in, play. See [docs/api.md](docs/api.md). |
| **Card data** | Plain JSON in `data/cards/`. Card art is downloaded once at build time and served by this app -- no runtime network calls. See [docs/card-catalog.md](docs/card-catalog.md). |
| **AI** | A random agent, a reflexive heuristic agent that beats it ~85% of the time, and a masked-PPO self-play trainer. |
| **Verification** | `python scripts/verify.py` runs every gate end to end. |

## Documentation

Start with [docs/architecture.md](docs/architecture.md) for the shape of the system,
then:

- [docs/engine-rules.md](docs/engine-rules.md) — turn structure, the stack, combat, with diagrams
- [docs/rules-coverage.md](docs/rules-coverage.md) — **what is implemented, what is simplified, and what is not** 
- [docs/card-dsl.md](docs/card-dsl.md) — how to write a card
- [docs/decks.md](docs/decks.md) — the two decks and every substitution made
- [docs/ai-training.md](docs/ai-training.md) — the environment, the action space, self-play
- [docs/api.md](docs/api.md) — the HTTP surface
- [docs/frontend.md](docs/frontend.md) — the client
- [docs/testing.md](docs/testing.md) — how the whole thing is verified
- [docs/deployment.md](docs/deployment.md) — CI/CD: every commit to `main` ships to <https://commanderblitz.com>

`docs/rules-coverage.md` is the one to read if you want to know what this engine can
and cannot do. It is deliberately honest: this is an MVP with real simplifications,
and they are all written down.
