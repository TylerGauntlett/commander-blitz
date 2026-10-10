---
name: create-pr
description: Open a pull request the way this repository expects. It gives the PR a conventional-commit title, whose type decides whether the merge deploys the site and cuts a Steam Deck release, and a short reviewable body in the what/why/how template with one diagram (old path dotted, new path solid). Use when asked to open, create, raise or submit a PR or pull request, and from any skill that ends by opening one.
---

# Opening a pull request

The PR title becomes the squash merge's subject on `main`. Its type decides what the merge
does. CI (`.github/workflows/pr.yml`) rejects a title or body that breaks the rules below,
so get them right before opening the PR.

Write for a reviewer who has five minutes. Use short, plain bullets. Prefer the short
form over the complete one.

## 1 · Read the whole branch

```bash
git branch --show-current          # never main: stop and branch if it is
git fetch -q origin
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

The PR describes every commit on the branch, not only the last one.

## 2 · Pick the title

`type(scope): summary`. The scope is optional, lowercase and names one area (`engine`,
`frontend`, `desktop`, `cards`, `dsl`, `ci`, `deps`, `art`). The summary is no longer
than 72 characters in total and has no trailing period. A `!` after the scope marks a
breaking change.

| type | use it for | on merge |
|---|---|---|
| `feat` | something a player or developer can now do (new cards, mechanics, art) | deploys + Deck release |
| `fix` | something that was wrong now isn't, including runtime dependency bumps | deploys + Deck release |
| `perf` | faster or lighter, same behaviour | deploys + Deck release |
| `refactor` | same behaviour, different code | deploys + Deck release |
| `build` | packaging, Docker, the desktop bundle | deploys + Deck release |
| `revert` | undoing an earlier merge | deploys + Deck release |
| `docs` | prose only | nothing ships |
| `test` | tests only | nothing ships |
| `ci` | workflows, CI scripts | nothing ships |
| `chore` | tooling, skills, housekeeping that doesn't reach a player | nothing ships |
| `style` | formatting only | nothing ships |

If the branch mixes types, pick the one that ships. Shipping is the safe failure: a
`docs:` title over a code change would leave that code undeployed. When the user needs
to know whether the merge ships, tell them which way it goes.

## 3 · Write the body

Copy `.github/pull_request_template.md` to a scratch file and fill it in. Follow this
structure exactly:

1. **Summary.** One short paragraph that someone who hasn't seen the work can follow.
2. **Risks.** Two bullets: the blast radius (what could break, and for whom) and the
   rollback (how to undo it).
3. **What.** **One** mermaid diagram, the only one in the PR, followed by three bullets.
   - It is one `flowchart LR` with no subgraphs. Old and new paths share nodes, so the
     change shows up as a fork. Draw the old path dotted (`-.->`) and the new path solid
     (`-->`). Anything that stays the same is part of the new path, so it is solid too.
   - Keep it to about six nodes, and only draw what changes. For a change that has no
     old path (a brand-new file), draw the one flow it adds, all solid.
   - Keep node labels to a few words, in quotes if they contain punctuation.
4. **Why.** Three bullets.
5. **How.** Three bullets on the approach, not a file list.
6. **Details** (`<details>`, collapsed). This holds everything else: the verification
   commands and their results, coverage tables, follow-ups and caveats.

End the body with the attribution line from the session's instructions, if there is one.

## 4 · Check, push, open

```bash
bash .github/scripts/conventional.sh title "<title>"
bash .github/scripts/conventional.sh body <scratch>/pr.md
git push -u origin HEAD
gh pr create --base main --title "<title>" --body-file <scratch>/pr.md
```

Both checks must pass before `gh pr create`. They are the same script CI runs. Report
the PR URL.

To fix a PR that is already open, use `gh pr edit <n> --title … --body-file …`. The
title check re-runs on the edit by itself.
