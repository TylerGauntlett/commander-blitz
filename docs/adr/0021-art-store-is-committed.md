# ADR 0021 — The art store is committed, crawled by a bot, and asked before Scryfall

**Status:** accepted

[ADR 0012](0012-art-fetched-once-served-locally.md) decided that art is fetched
once and served by this application. It left one fetch at runtime: the lazy fill
in `ArtStore._fill`, which the hosted server and every Steam Deck run against
Scryfall the first time a board shows a card the repository did not ship. This
ADR is where the rest of the catalog's art lives and who fetches it.

## Context

Every card a player can import, and every deck the catalog can build, wants an
illustration. Filling those on demand puts Scryfall's rate limit and uptime in
front of a player who is waiting, once per server and once more per Deck. The
alternative is to download them ahead of time, slowly, once.

That download is Wizards-owned illustration taken from a third-party CDN, and
[card-catalog.md](../card-catalog.md#a-note-on-the-images) asked for a
deliberate decision before the corpus grew past the cards the repository plays.
The corpus this ADR allows is the whole catalog's.

The candidates for where it lives were a Docker volume, an object store, and the
repository. A volume or a bucket keeps git small but is state outside the code:
it does not come with a clone, it is lost with the droplet or needs credentials,
and a local checkout plays without it. The repository is where `data/art/`
already lives, for exactly the reason that a fresh clone then needs nothing
running anywhere.

## Decision

**The crawled art is committed to this repository under `data/art_store/`,
written only by `scripts/backfill_art.py` through a scheduled workflow whose
pull requests merge themselves, and every server asks it before it asks
anybody else.**

- **What is stored.** Scryfall's `art_crop`, byte for byte as served, never
  re-encoded or resized. For every printing the catalog index resolves (one per
  name, and the back face where a card has an illustration there), every pin in
  `data/catalog/art_pins.json`, and every printing a shipped deck chose. Nothing
  `data/art/` already owns is stored twice. Every printing of every card is
  **not** stored; that is a separate decision.
- **How it is keyed.** By printing, `{scryfall_id}.jpg` and
  `{scryfall_id}_back.jpg`, sharded by the id's first two characters
  (`store_path` in `cards/images.py`). A printing is the unit Scryfall serves and
  the unit a deck names, so two cards or two decks sharing an illustration share
  one file.
- **The order of the layers.** Committed `data/art/` (reviewed, and the place a
  pin's answer lands) beats the store, which beats the lazy cache under
  `generated/`. The lazy fill remains, as the fallback for a printing the crawl
  has not reached; how often it is used is on `/health` as `fell_through`.
- **Who writes it.** `art-backfill.yml`, on a schedule and by hand. It caps each
  run, opens one `chore(art):` pull request with what it fetched and sets it to
  merge itself. `chore` keeps a crawl from deploying or releasing on its own;
  the illustrations reach the site with the next merge that ships. The gate's
  `changes` job treats `data/art_store/` as inert, because no test reads an
  illustration.
- **What ships where.** The Docker image carries the store in a layer of its
  own, so a deploy moves only what is new. The Deck's content package does not
  carry it (`assemble-content.mjs` leaves it out) and carries `data/art/` as
  before.
- **What the Deck fetches.** The sidecar's lazy fill asks the hosted origin's
  `/art/{scryfall_id}[_back].jpg` first and Scryfall second. One crawl serves
  every device; a site that is down costs a Deck nothing it had before.

## Consequences

- The repository, every clone and every CI checkout grow by the size of the
  corpus, for good: git keeps what it has been given. Removing the store later
  shrinks the tree, not the history.
- A crawl is a bot writing to `main` on a schedule. It needs a token that is
  not `GITHUB_TOKEN` (a pull request opened with that token starts no workflow,
  so its required checks would never report) and the repository's auto-merge
  setting. Without either, the workflow fails or its pull request waits, and
  the lazy fill keeps covering the gap.
- **Reading `data/art_store/` from a test, or from anything the gate runs,
  reverses the inert rule** and makes every crawl a full gate run. Hold such a
  check in the backfill script instead.
- **Copying `data/` into the image in one layer again reverses the layer
  split** and makes every card edit re-ship the whole corpus.
  `TestTheDeployedShape` holds the Dockerfile and the content assembler to this.
- A wider corpus (every printing, or a second encoding for the Deck) changes
  what is distributed and amends this ADR first.

## Rejected

- **A Docker volume.** State outside the code: it does not come with a clone,
  it is lost with the droplet, and it was the shape that once shadowed committed
  art (`docs/deployment.md`).
- **An object store.** Credentials, an SDK and a terraform apply, for a corpus
  that git holds fine; and still not portable to a local checkout.
- **Git LFS.** The free quota is smaller than the corpus, and every CI checkout
  spends transfer on it.
- **A crawl inside the server process.** It would run on every deploy of every
  server, write nothing durable a clone could use, and put the throttle in
  front of the same process that serves games.
- **The Deck fetching from Scryfall only, or the site only.** The first keeps a
  third party on every device; the second makes a site outage take away art a
  Deck could still have had.
