"""Self-play training and evaluation.

The engine is a decision machine; this package turns it into something an RL
agent can hold.  Three pieces:

* :mod:`commanderblitz.ai.action_space` -- a fixed flat index over actions plus the
  legality mask.  The mask is derived from ``legality.legal_actions()``, the same
  enumeration the HTTP layer serves, so the two can never disagree.
* :mod:`commanderblitz.ai.encoding` -- the observation vector.
* :mod:`commanderblitz.ai.env` -- a Gymnasium environment that drives the other seats.
"""
