"""The effect-op registry: ``OPS``, the ``@register`` decorator, ``RECORDING_OPS``.

A leaf the ``ops_*`` modules can import without running the package, which
imports them. See `commanderblitz.engine.effects.load_ops`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..errors import DslError

#: op name -> implementation.  Populated by the ``@register`` decorator.
OPS: dict[str, Callable[..., Any]] = {}

#: The ops that write ``ctx.bindings`` when given an ``as`` name -- "the cards
#: revealed this way", "the number of creature cards exiled this way", "exile
#: **the token**".  Every other op ignores an ``as`` entirely, and an `as` that
#: nothing writes reads back as 0 rather than as an error, so the loader refuses
#: it (see `loader.effects._validate_effect`).  Listed here, beside `OPS`, so the guard
#: and the implementations cannot drift apart.
RECORDING_OPS = frozenset(
    {
        #: The one recorder whose binding is a **player**: `choose_player`
        #: writes the seat that was chosen, read back by the `{"binding": …}`
        #: player spec rather than as a pool of objects. It is also the only
        #: one for which `as` is *required* -- the answer is unreachable
        #: otherwise. See `ops_control.op_choose_player`.
        #: Airbend's pool, recorded for `exile`'s reason and with `exile`'s
        #: accumulating semantics -- "airbend all other creatures" is one pool
        #: a later line may need to name.
        "airbend",
        #: The amassed Army, a list of zero or one oids -- "the
        #: amassed Army's power". See `ops_counters.op_amass`.
        "amass",
        #: What was beheld -- the chosen permanent or the revealed hand card.
        #: See `ops_cards.op_behold`.
        "behold",
        #: The cards actually **cast** -- Conduit of Worlds' "if you do". Not
        #: the cards offered: a declined offer and a card with no payable line
        #: are not in it. See `ops_cards.op_cast_card`.
        "cast_card",
        #: The one recorder whose binding is a **card name** -- a string, read
        #: back only by a selector's ``{"name": {"binding": …}}``. Tamiyo,
        #: Collector of Tales. See `ops_control.op_choose_card_name`.
        "choose_card_name",
        "choose_player",
        #: The one recorder that does **nothing** to what it picked. Tragic
        #: Arrogance marks the survivors before the mass sacrifice; every other
        #: recorder acts on its pick, and marking-without-acting had no
        #: spelling. Accumulates, so four per-type choices share one name and a
        #: single `exclude_binding` spares them all.
        "choose_permanents",
        "copy_permanent",
        "create_token",
        #: The permanents actually **destroyed** -- Avenge's "for each creature
        #: destroyed this way". Not the ones chosen: indestructible,
        #: regeneration, a shield counter and totem armor each leave a chosen
        #: permanent out of it. Accumulates. See `ops_removal.op_destroy`.
        "destroy",
        #: "…then draw that many cards" -- Joshua; "draw that many cards **plus
        #: one**" -- Celes; "if a **creature card** was discarded this way" --
        #: Mog. The binding **accumulates** across the players a single discard
        #: touches, because Mog asks one card of each player in one resolution
        #: and then asks what was discarded at all, not what the last player
        #: pitched. See `ops_cards.op_discard`.
        "discard",
        #: The **discovered card** (701.57c), a list of zero or one oids,
        #: whether it was cast or put into hand -- Hit the Mother Lode's "if
        #: the discovered card's mana value is less than 10". Empty when the
        #: scan ran the library out. See `ops_cards.op_discover`.
        "discover",
        #: The second recorder whose binding is a **set of seats**, beside
        #: `may`: the players who actually drew at least one card. Cut a Deal's
        #: "each opponent who drew a card this way" -- an opponent with an empty
        #: library, or whose draw dredge replaced, drew nothing and is not one.
        #: Read with the `{"binding": …}` player spec; the loader refuses it as
        #: a pool of objects. See `ops_cards.op_draw`.
        "draw",
        "exile",
        #: The card the walk stopped at, a list of zero or one oids, cast or
        #: not. See `ops_cards.op_exile_until`.
        "exile_until",
        "gain_control",
        #: The Incubators made, `create_token`'s record. See
        #: `ops_counters.op_incubate`.
        "incubate",
        "join_forces",
        #: The cards a bounded look off the top actually **took** -- "exile the
        #: top card of your library face down. Put **that card** into your hand
        #: at the beginning of your next end step" (Necropotence). Nothing else
        #: can name that card afterwards: `_move_found` deliberately writes no
        #: `exiled_by`, so `exiled_with: "self"` matches nothing, and even with
        #: the link written it would be source-wide where the printed "that
        #: card" is per-activation. Accumulates across seats like `discard` and
        #: `mill`, so a `player: "each_player"` look binds every seat's cards
        #: rather than the last one's. See `ops_cards.op_look_at_top`.
        "look_at_top",
        #: A recorder whose binding is a plain **int**: the life actually
        #: lost, after replacements, summed over every player the op hit --
        #: "you gain life equal to the life lost this way" (Gray Merchant of
        #: Asphodel) and extort's "that much life". See `ops_life.op_lose_life`.
        "lose_life",
        #: The only recorder whose binding is a **set of seats**: `may` writes
        #: the players who said yes, read back with the `{"binding": …}` player
        #: spec. Snort's "each opponent who discarded their hand this way" is
        #: the acceptance and not anything the effects moved -- a player with an
        #: empty hand who takes the free draw-five has discarded their hand, of
        #: nothing, and is still burned.
        "may",
        #: The cards actually milled, across every player one op touched --
        #: Locke, Treasure Hunter's "if a land card was milled **this way**".
        #: An `exists` over a graveyard is a different card: it matches a land
        #: that was already lying there.
        "mill",
        #: The cards actually **cast**, which is neither the cards offered nor
        #: the cards exiled -- one with no legal target is never cast at all.
        #: Kefka turns on that distinction: "each player who owns a spell you
        #: cast this way loses life equal to its mana value".
        "play_exiled",
        #: The cards actually put into a library -- Teferi's Puzzle Box, "puts
        #: the cards in their hand on the bottom of their library in any order,
        #: then draws **that many** cards". Read after the tuck, the hand is
        #: empty; the binding is the only place the number survives. What
        #: arrived, not what was chosen: a commander redirected to the command
        #: zone was not put there. See `ops_cards.op_put_on_top`.
        "put_on_top",
        #: A plain **int**, like `lose_life`'s: the counters actually removed --
        #: Eventide's Shadow's "equal to the number of counters removed this
        #: way", which nothing on the board still shows once they are gone.
        #: See `ops_counters.op_remove_counters_from_among`.
        "remove_counters_from_among",
        #: "…for each creature returned to your hand **this way**" -- The Eagles
        #: Are Coming!. Beside `exile` and `sacrifice`, whose bindings it copies
        #: in both shape and accumulating semantics, and it matters here for a
        #: reason the other two rarely meet: the sentence that counts the return
        #: lives inside a `delay`, and a `{"target": …}` there is refused by name
        #: because `_run_delayed` rebuilds its context with no targets. A binding
        #: is carried forward where a target is not.
        "return_to_hand",
        "reveal",
        #: The matches a reveal-until walk moved, every seat's -- "put those
        #: creature cards onto the battlefield … they're goaded". See
        #: `ops_cards.op_reveal_until`.
        "reveal_until",
        #: The one recorder whose binding is not a set of objects: `roll_dice`
        #: writes the faces it threw, read back by `{"rolled": …}` rather than
        #: by `{"count": {"binding": …}}`. See `ops_cards.op_roll_dice`.
        "roll_dice",
        "sacrifice",
        "search_library",
        "search_zones",
        "snapshot",
    }
)


def register(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an effect op under ``name``."""

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in OPS:
            raise DslError(f"duplicate effect op {name!r}")
        OPS[name] = fn
        return fn

    return decorate
