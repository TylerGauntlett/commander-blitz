---
id: art-store
title: An art store the servers own
area: cards
effort: M
impact: high
why: removes the one runtime dependency on a third party, and every deck and card expansion sits on top of it
depends_on: []
status: in_progress
adr: true
---

## Today

The repository commits the art for the cards it ships, and the
hosted server lazily fetches anything else from Scryfall the first time a
board shows it ([card-catalog.md](../card-catalog.md#serving)). The browser
never talks to Scryfall, which is the rule
[ADR 0012](../adr/0012-art-fetched-once-served-locally.md) set; the server
still does, at a moment a player is waiting, and so does every Steam Deck
on its own behalf (`ArtStore._fill`, which the sidecar's `eager_art`
prefetch drives). At catalog scale that is a rate limit and an outage
waiting to be met by whoever imports the wrong deck on the wrong evening.

Refreshing the Scryfall bundle is a hand-run `build_card_index.py
--refresh`; nothing schedules it, so there is no refresh for a crawl to
follow.

## The change

Download every illustration once, slowly, into a corpus committed to this
repository, and have every Commander Blitz server serve from it before it
asks anybody else. Committed, not a volume or an object store: a file in
git is permanent, portable, and plays on a fresh clone with nothing running
anywhere, which is the property `data/art/` already has and the reason it
was chosen. The cost is a repository and an image that grow by the size of
the corpus, accepted in the ADR.

- **The store is `data/art_store/`**, keyed by printing:
  `{scryfall_id}.jpg` and `{scryfall_id}_back.jpg`, sharded by the id's
  first two characters. It is the third layer behind the committed
  `data/art/` and ahead of the lazy cache: `ArtStore.path_for` and the
  printing path consult it in that order, `/art/{card_id}.jpg` and `?p=`
  keep their meaning, and the owned-wins rule keeps its order. The lazy
  fill stays as the fallback for a printing the store has not reached, and
  the `_missing` set stays as the answer for one Scryfall does not have.
- **A backfill script**, `scripts/backfill_art.py`, walks what is wanted
  at the pace Scryfall asks for: every printing the index resolves (one per
  name, both faces where the card has two), every pin in
  `art_pins.json`, and every printing a shipped deck chose, less what
  `data/art/` already owns. Resumable and idempotent by construction: a
  file in the store is never fetched again, a download is written whole or
  not at all, and a printing the CDN does not have is recorded once in
  `data/art_store/_unavailable.json` and never retried. `--limit` caps one
  run.
- **A scheduled workflow commits the crawl.** `art-backfill.yml` runs the
  script on a schedule and by hand, commits what it fetched on a branch,
  and opens a `chore(art):` pull request that merges itself once the gate
  passes. `chore` is deliberate: a crawl neither deploys the site nor cuts
  a Deck release on its own, and reaches both with the next merge that
  ships. The gate treats the store as inert, so a crawl costs no test run.
  It needs a token that is not `GITHUB_TOKEN`, since a pull request opened
  with that one starts no workflow and would wait on its checks forever.
- **The image carries the store** in a layer of its own, so a deploy moves
  only the illustrations that are new. **The Deck's content package does
  not**: it carries `data/art/` as today.
- **The Deck fetches from the site first, then Scryfall.** The sidecar's
  lazy fill and eager prefetch ask the hosted origin's
  `/art/{scryfall_id}[_back].jpg` before the CDN, so one throttled crawl
  serves every device; Scryfall stays behind it for a site that is down.
  The desktop's offline story is unchanged: what it has, it has.
- **`/health` reports the backfill**: how much of what is wanted the store
  holds, when the crawl last ran, and how many lookups fell through to the
  lazy fill since boot, which is the number that should go to zero and stay
  there.

**The decision this forces.** `data/art/` is Wizards-owned illustration, and
[card-catalog.md](../card-catalog.md#a-note-on-the-images) asks for a
deliberate decision before the corpus grows. A store holding the whole
catalog is that moment, and the decision belongs in an ADR before the
backfill runs: what is stored (Scryfall's `art_crop`, as served, for every
printing above and no other), where (committed, in the image, not in the
Deck's package), and what the Deck fetches.

Every printing of every card is not in scope: an order of magnitude more
storage for illustrations almost nobody will see, and a later decision.

## Gate

The art API tests gain the third layer: a store file is served ahead of a
cached one and behind a committed one, a deck's printing is served from the
store, and a request for a printing the store lacks still fills lazily. A
desktop store with an upstream asks the site before Scryfall and falls back
when the site fails. The backfill script is resumable under test: interrupt
it, run it again, and no file is fetched twice; a printing the CDN lacks is
recorded and not asked for again. `/health` carries the backfill fields and
`tests/server/test_art_api.py` asserts the payload still names no
`cards.scryfall.io` URL. A test holds the Docker image and the content
package to the placement above: the image copies the store, the package
excludes it.
