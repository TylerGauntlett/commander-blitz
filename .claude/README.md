# Claude Code skills

The skills in `skills/` are the project's card-authoring workflow, packaged for
[Claude Code](https://claude.com/claude-code): `/import-moxfield`, `/author-cards`
and `/extend-dsl`. [CONTRIBUTING.md](../CONTRIBUTING.md) explains what each does
and how to do the same by hand.

`/create-pr` opens a pull request the way CI expects: a conventional-commit
title (its type decides whether the merge deploys and releases) and the
what/why/how body from `.github/pull_request_template.md`.
