# ADR 0010 — Every shipping merge to main is a Steam Deck release

**Status:** accepted

Supersedes the "desktop catches up when a release is tagged" cadence in
[ADR 0009](0009-offline-first-desktop.md).

## Context

The desktop build used to release only when someone pushed a `vX.Y.Z` tag matching
`desktop/package.json`. That was for two reasons, and neither holds any more:

- **The source was private.** A private repository's release assets need a token to
  download, so releases had to be copied to a separate public repository,
  `commander-blitz-releases`, with a cross-repo token. The project went public on
  2026-10-10, and releases now live in this repository and publish with the
  workflow's own `GITHUB_TOKEN`.
- **Actions minutes were the binding limit.** On the Free plan for a private
  repository, ~25 runner-minutes per release was worth rationing. Standard runners
  are free for public repositories.

The cost of the tag-only cadence showed in practice. #64 redrew the Steam library art
and merged, then sat unreleased until #65, a pull request that existed only to bump the
version so a tag could be pushed. The site deployed on every merge, while the Deck
stayed behind until someone remembered.

## Decision

**A push to main that passes the gate and ships is released.** `deploy.yml` calls
`release.yml` as a reusable workflow next to the site deploy. It uses the same guard as
`build` (green `gate`, a push, `main`) and runs in parallel, because a Deck doesn't
depend on the droplet.

**"Ships" is the commit type.** A squash merge's subject is its pull request's title,
and `pr.yml` requires that title to be a conventional commit. `feat`, `fix`, `perf`,
`refactor`, `build` and `revert` ship: they deploy the site and cut a release. `docs`,
`chore`, `ci`, `test` and `style` do neither. The rules live in one script,
`.github/scripts/conventional.sh`, which the pull request gate, the ship decision and
the `/create-pr` skill all call. A push ships if any commit in it ships, or if it
contains a non-conventional subject, or if its commit list can't be read in full. Doubt
resolves to shipping, because a quiet type over a real change would leave that code
unreleased.

**The version is `X.Y.<commits on main>`.** Major and minor come from
`desktop/package.json` and change only through a deliberate pull request. The patch is
the commit count, which CI stamps into `package.json` before anything reads it, so the
AppImage, `latest-linux.yml`, `app.getVersion()` and the content manifest all agree.
Squash merges keep main linear, so the count only grows. Both updaters move only to a
strictly higher version, so that growth is the update mechanism. The same commit always
gets the same version, which makes a re-run a no-op.

**A release can't go backwards or appear half-finished.** The `version` job stops if
the release already exists or isn't newer than `latest`. `publish` uploads into a
draft and makes it the latest release only as its last step. A newer push cancels an
in-flight run (`cancel-in-progress`), and a draft is invisible to
`releases/latest/download/…`.

**`deployed` covers the Deck too.** A green gate on a push that ships must leave both
the deploy and the release green. A push that doesn't ship must leave both skipped.

## Consequences

- The site and the Deck move together. Offline play is as current as the last merge
  that shipped.
- Every shipping merge is a full AppImage download on every Deck. No blockmap is
  published, so updates aren't differential. They download in the background and
  install on quit.
- There is no pre-release channel. `install.sh` and both updaters read only
  `releases/latest`. To hold a change back, merge it under a non-shipping type and
  release later with `workflow_dispatch` on `release.yml`. To undo one, revert it: the
  revert ships a higher version.
- Pull request titles are now a gate. A title that isn't a conventional commit can't
  merge (once "pull request title" is a required check). Dependabot gets `fix(deps)` for
  runtime ecosystems and `ci(deps)` for Actions.
- `min_shell_version` still defaults to the content's own version. That's harmless
  because the shell and the content always release together.

### Amended 2026-10-10: content-only releases, and what a push owes

Two of the consequences above turned out to cost more than expected, and are changed:

- **The AppImage is rebuilt only when the shell changed** since the latest release:
  what electron-builder packs, what builds it, or `release.yml`. Otherwise the
  release carries the previous AppImage and `latest-linux.yml` unchanged, and the
  content's `min_shell_version` names that shell. A Deck downloads only the content
  tarball, through the content updater that was already there. A fresh install
  between shell releases boots the older bundled content for one update check.
- **What ships is measured from the last deploy and the last release that
  finished**, not from the commits in the push. `cancel-in-progress` on main had made
  the push-only verdict lose work: a `feat:` merge cancelled by a quick `chore:`
  merge was never deployed or released (#73 behind #77). The site and the Deck are
  judged separately, because a cancel or a failure can leave them on different
  commits. `workflow_dispatch` of `deploy.yml` on main now ships both, as the
  recovery path.

## Rejected

- **Release on every push regardless of type.** Deck players would download the
  whole app again for a typo fix in a README.
- **Skip by changed paths, the way `changes` skips tests.** A path list is the wrong
  question for a release. It tells you whether the gate can see a file, not whether a
  player would notice the change. The author knows the answer, and the title records it
  where a reviewer can check it.
- **`X.Y.<run number>`.** A re-run of the same commit would get a new number and ship
  a duplicate release.
- **A bot commits the version bump to main.** That adds a commit per release, needs a
  token that can push past branch protection, and re-triggers the pipeline it came from.
- **Pre-release identifiers (`1.0.1-build.7`).** `releases/latest` ignores
  pre-releases. Also, `desktop/src/version.ts` compares pre-release tags as strings,
  so `build.10` would sort below `build.9`.
