The core loop is finished: a human, a CPU and a training policy all play the
same engine through one seam, every shipped deck is implemented card for card,
the client runs on a desktop, a Steam Deck and a phone, and the site and the
Deck release themselves from every merge that ships. This page is what comes
after. It is the one page under `docs/` about things that do not exist yet,
and it breaks the house rule against numbers exactly where a target *is* a
number.

It is generated. Each item is a file under `docs/roadmap/` with a small front
matter and three sections, written by `/plan-feature` and worked by
`/extend-roadmap`; `scripts/roadmap.py` validates the files, derives the
grid and the queue, and writes this page. Edit the item, not the page.

How to read it:

- Each item says what is true today, what would change and how it would be
  built, and what gate would hold it. Where an item turns on a decision with
  consequences, it is marked **ADR first** and the decision gets an ADR before
  the code.
- Every item opens with three properties. **Effort** uses the sizes
  [TECH_DEBT.md](../../TECH_DEBT.md) uses: **S** an afternoon, **M** a focused
  pull request, **L** a multi-PR effort; a *continuous* item is never done,
  only advanced one batch at a time. **Impact** is who it reaches and how
  often: **high** touches every game or every player of the site, **medium**
  touches a class of players or removes a weekly annoyance, **low** is polish
  somebody would notice and nobody would miss. An item may also carry a
  **rank**, which puts it ahead of the unranked items of its impact; the
  precon items are ranked set by set, newest first. **Depends on** names the items
  that have to land first; "nothing" means it can start today.
- An item may close with **Decisions**, the owner's answers to the questions
  its plan leaves open, and **Open questions**, the ones still waiting. An item
  with the first and not the second is decided, and only a decided item is
  built unattended ([ADR 0026](../adr/0026-the-roadmap-autopilot-merges-on-green.md));
  the rest say **Awaiting decisions**.
- An item leaves this page the way a debt item leaves
  [TECH_DEBT.md](../../TECH_DEBT.md): when the work lands, retire the item in the
  same pull request (`scripts/roadmap.py --done <id>`), which also unblocks
  whatever depended on it, and let the docs it touched carry the result.
  Nothing here is a changelog.
