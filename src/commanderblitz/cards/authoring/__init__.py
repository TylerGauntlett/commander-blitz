"""Adding cards to the engine systematically, rather than one pair of hands at a time.

The engine plays a few hundred hand-written cards out of ~32,000 in the catalog.
Everything else imports as a *proxy*: right name, art, cost, types and keywords,
with the rules text inert (``commanderblitz.cards.proxy``). That is honest, and it is not
a game -- a real imported deck had 41 of its 100 cards doing nothing.

This package turns "somebody writes a card" into a repeatable batch:

``verify``   the six gates a candidate card must clear before it is written
``queue``    what to work on next, most-played first
``templates`` the sentences common enough to translate deterministically
``packet``   what an agent is handed for everything else

**The verifier is the centre of gravity, not the generator.** ``compile_card``
validates *vocabulary*, not *meaning*: a card can load cleanly and do the wrong
thing, and nothing on screen would say so. Generation is cheap and trust is
expensive, so nothing is written that has not demonstrated its behaviour.
"""
