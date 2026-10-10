# Agent skills

`skills/` holds the project's agent skills in the Agent Skills layout, one
`SKILL.md` per directory, so that Cursor and Claude Code share one copy:

- `/import-moxfield` makes every card in a Moxfield deck fully playable, end to
  end, and opens the pull request.
- `/author-cards` implements cards the DSL can already express, in bulk or by
  name, through the six gates.
- `/extend-dsl` builds the one engine capability that unblocks a gap record.
- `/create-pr` opens a pull request the way CI expects: a conventional-commit
  title, whose type decides whether the merge deploys and releases, and the
  what/why/how body from `.github/pull_request_template.md`.

Cursor reads `.agents/skills/` directly. Claude Code reads `.claude/skills/`, so
each entry there is a symlink to its twin here. On Windows that needs
`core.symlinks` and the right to create symlinks; [AGENTS.md](../AGENTS.md)
has the setup. [CONTRIBUTING.md](../CONTRIBUTING.md) explains what each skill
does and how to do the same by hand.
