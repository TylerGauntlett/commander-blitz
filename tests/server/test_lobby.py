"""The pod object, without HTTP.

Everything here talks to :class:`PodRegistry` directly.  The HTTP surface gets
its own file; this one is about the rules -- who may sit where, what each seat
is allowed to know about the others, and what happens when somebody walks away.
"""

from __future__ import annotations

import pytest

from automtg.cards.registry import default_registry
from automtg.server import lobby as L
from automtg.server.lobby import Pod, PodError, PodRegistry, PodSeat
from automtg.server.sessions import SessionRegistry


@pytest.fixture(scope="module")
def data():
    return default_registry()


@pytest.fixture
def pods(data) -> PodRegistry:
    return PodRegistry(SessionRegistry(data))


def seated(pods: PodRegistry, *, guests: int = 1) -> tuple[Pod, list]:
    """A pod with a host in seat 0 and ``guests`` guests after them."""
    pod, host = pods.create(host_name="Host", deck_id="aesi")
    players = [host]
    for i in range(guests):
        _, guest = pods.join(pod.code, name=f"Guest {i}")
        players.append(guest)
    return pod, players


class TestPodCodes:
    def test_the_format_is_word_then_four_digits(self):
        for _ in range(50):
            assert L._CODE_RE.match(L.make_code()), L.make_code()
            word, _, digits = L.make_code().partition("-")
            assert word.isupper() and len(digits) == 4

    def test_every_word_is_distinct(self):
        """A duplicate would halve that word's share of the code space."""
        assert len(set(L.POD_WORDS)) == len(L.POD_WORDS) == 128

    @pytest.mark.parametrize(
        "typed",
        ["gyre-8412", "GYRE8412", " gyre 8412 ", "Gyre-8412", "GYRE_8412"],
    )
    def test_a_code_read_aloud_still_finds_the_pod(self, typed):
        """Case, whitespace and a missing hyphen are not a different pod."""
        assert L.normalise_code(typed) == "GYRE-8412"

    def test_a_collision_is_retried(self, monkeypatch):
        """Pre-seed every word the generator will pick, bar the last."""
        picks = iter(["GYRE", "GYRE", "LOTUS"])
        monkeypatch.setattr(L.secrets, "choice", lambda seq: next(picks))
        monkeypatch.setattr(L.secrets, "randbelow", lambda n: 0)
        assert L.make_code({"GYRE-1000"}) == "LOTUS-1000"

    def test_lookup_normalises(self, pods):
        pod, _ = pods.create()
        assert pods.get(pod.code.lower().replace("-", "")) is pod

    def test_an_unknown_code_is_not_found(self, pods):
        with pytest.raises(PodError) as exc:
            pods.get("GYRE-0000")
        assert exc.value.code == "not_found"


class TestSeatModel:
    def test_a_cpu_is_ready_the_moment_it_is_seated(self):
        assert PodSeat(kind="cpu", deck_id="aesi").ready

    def test_a_human_is_ready_only_once_locked(self):
        seat = PodSeat(kind="human", deck_id="aesi")
        assert not seat.ready
        seat.locked = True
        assert seat.ready

    def test_a_locked_human_with_no_deck_is_not_ready(self):
        assert not PodSeat(kind="human", locked=True).ready

    def test_an_open_chair_is_never_ready(self):
        """It is a chair somebody was invited to and has not taken."""
        assert not PodSeat(kind="open").ready
        assert not PodSeat().ready

    def test_only_cpu_and_human_seats_become_players(self):
        assert PodSeat(kind="cpu").filled and PodSeat(kind="human").filled
        assert not PodSeat(kind="open").filled and not PodSeat().filled


class TestDeckSecrecy:
    """The lobby's hidden-information contract, mirroring ``player_view``."""

    def test_an_unlocked_deck_is_invisible_to_everybody_else(self, pods):
        pod, (host, guest) = seated(pods)
        pods.update_seat(pod, guest.player_id, deck_id="edgar")

        assert pod.view_for(host.player_id).seats[1].deck is None
        assert pod.view_for(None).seats[1].deck is None
        assert pod.view_for(guest.player_id).seats[1].deck.id == "edgar"

    def test_locking_in_reveals_it_to_everybody(self, pods):
        pod, (host, guest) = seated(pods)
        pods.update_seat(pod, guest.player_id, deck_id="edgar", locked=True)
        assert pod.view_for(host.player_id).seats[1].deck.id == "edgar"
        assert pod.view_for(None).seats[1].deck.id == "edgar"

    def test_unlocking_hides_it_again(self, pods):
        pod, (host, guest) = seated(pods)
        pods.update_seat(pod, guest.player_id, deck_id="edgar", locked=True)
        pods.update_seat(pod, guest.player_id, locked=False)
        assert pod.view_for(host.player_id).seats[1].deck is None

    def test_a_cpu_deck_is_always_visible(self, pods):
        """The host chose it, so there is nothing to hide."""
        pod, (host, guest) = seated(pods)
        pods.admin_seat(pod, host.player_id, 2, action="add_cpu", deck_id="zurgo")
        assert pod.view_for(guest.player_id).seats[2].deck.id == "zurgo"

    def test_no_view_ever_carries_a_token(self, pods):
        pod, players = seated(pods, guests=2)
        for viewer in [None, *[p.player_id for p in players]]:
            blob = pod.view_for(viewer).model_dump_json()
            for player in players:
                assert player.token not in blob

    def test_no_view_carries_another_players_id(self, pods):
        """The client needs a name and a state, never an identity it could use."""
        pod, (host, guest) = seated(pods)
        blob = pod.view_for(host.player_id).model_dump_json()
        assert guest.player_id not in blob

    def test_your_own_seat_is_marked(self, pods):
        pod, (_host, guest) = seated(pods)
        view = pod.view_for(guest.player_id)
        assert view.your_seat == 1
        assert [s.is_you for s in view.seats] == [False, True, False, False]
        assert [s.is_host for s in view.seats] == [True, False, False, False]
        assert not view.you_are_host


class TestJoining:
    def test_the_host_takes_seat_zero(self, pods):
        pod, host = pods.create(host_name="Host")
        assert pod.seat_of(host.player_id) == 0
        assert pod.is_host(host.player_id)
        assert pod.view_for(host.player_id).you_are_host

    def test_guests_fill_the_chairs_in_order(self, pods):
        _pod, players = seated(pods, guests=3)
        assert [p.seat for p in players] == [0, 1, 2, 3]

    def test_a_full_pod_is_refused(self, pods):
        pod, _ = seated(pods, guests=3)
        with pytest.raises(PodError) as exc:
            pods.join(pod.code, name="Fifth")
        assert exc.value.code == "pod_full"

    def test_an_open_chair_is_taken_before_an_empty_one(self, pods):
        """An open chair was deliberately held for somebody."""
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 3, action="open_chair")
        _, guest = pods.join(pod.code, name="Guest")
        assert guest.seat == 3

    def test_rejoining_with_your_token_is_idempotent(self, pods):
        pod, (_host, guest) = seated(pods)
        pods.update_seat(pod, guest.player_id, deck_id="edgar")
        _, again = pods.join(pod.code, name="Somebody Else", token=guest.token)
        assert again.player_id == guest.player_id
        assert again.seat == guest.seat
        assert pod.seats[1].deck_id == "edgar"
        assert len(pod.players) == 2

    def test_joining_a_dealt_pod_is_routed_to_the_table(self, pods):
        pod, (host, guest) = seated(pods)
        for player in (host, guest):
            pods.update_seat(pod, player.player_id, deck_id="aesi", locked=True)
        session = pods.start(pod, host.player_id)

        with pytest.raises(PodError) as exc:
            pods.join(pod.code, name="Latecomer")
        assert exc.value.code == "already_started"
        assert exc.value.detail["game_id"] == session.game_id


class TestSeatAdmin:
    def test_only_the_host_may_touch_another_seat(self, pods):
        pod, (_host, guest) = seated(pods)
        with pytest.raises(PodError) as exc:
            pods.admin_seat(pod, guest.player_id, 2, action="add_cpu")
        assert exc.value.code == "not_host"

    def test_not_even_the_host_reaches_into_a_players_chair(self, pods):
        """They chose that deck privately and may not have locked it in."""
        pod, (host, _guest) = seated(pods)
        with pytest.raises(PodError) as exc:
            pods.admin_seat(pod, host.player_id, 1, action="clear")
        assert exc.value.code == "not_your_seat"

    def test_add_cpu_seats_a_ready_opponent(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu", deck_id="edgar")
        seat = pod.seats[1]
        assert (seat.kind, seat.deck_id, seat.ready) == ("cpu", "edgar", True)

    def test_add_cpu_without_a_deck_still_picks_one(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")
        assert pod.seats[1].deck_id in pods.sessions.data.decks

    def test_cpus_never_mirror_each_other(self, pods):
        """Four seats playing the same commander is not a pod."""
        pod, (host,) = seated(pods, guests=0)
        for index in (1, 2, 3):
            pods.admin_seat(pod, host.player_id, index, action="add_cpu")
        decks = [seat.deck_id for seat in pod.seats]
        assert len(set(decks)) == 4, decks

    def test_distinctness_is_measured_by_commander_not_deck_id(self, pods, data):
        """Two lists can share a commander, and usually do once you import.

        A machine with a Moxfield import of a deck the engine also ships as a
        precon has two ids for one commander.  Seating both is still a mirror
        match and still draws two identical cards on the table.
        """
        from dataclasses import replace

        from automtg.cards.registry import GameData

        # Three decks, two of which are the same commander under different ids.
        aesi = data.decks["aesi"]
        pods.sessions.data = GameData(
            registry=data.registry,
            decks={
                "aesi": aesi,
                "aesi_copy": replace(aesi, id="aesi_copy", name="Aesi (imported)"),
                "edgar": data.decks["edgar"],
            },
        )
        pod, (host,) = seated(pods, guests=0)
        pods.update_seat(pod, host.player_id, deck_id="aesi")
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")

        commanders = [
            pods.sessions.data.decks[seat.deck_id].commanders
            for seat in pod.seats
            if seat.deck_id
        ]
        assert len(set(commanders)) == len(commanders), commanders

    def test_the_same_pod_twice_seats_the_same_decks(self, pods, data):
        """A seeded pod has to deal the same game twice.

        A deck chosen at random would be a source of variation the seed does
        not cover, which is what ``e2e/full-game.spec.ts`` would notice first.
        """

        def build():
            pod, (host,) = seated(pods, guests=0)
            for index in (1, 2, 3):
                pods.admin_seat(pod, host.player_id, index, action="add_cpu")
            return [seat.deck_id for seat in pod.seats]

        assert build() == build()

    def test_a_cpu_moves_off_a_deck_a_person_takes(self, pods):
        """The CPU's deck was assigned; the human's was chosen."""
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu", deck_id="zurgo")
        pods.update_seat(pod, host.player_id, deck_id="zurgo")
        assert pod.seats[0].deck_id == "zurgo"
        assert pod.seats[1].deck_id != "zurgo"

    def test_a_cpu_the_host_pinned_is_left_alone_by_another_cpu(self, pods):
        """Dedupe only fires against a *person's* choice, not a CPU's."""
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu", deck_id="edgar")
        pods.admin_seat(pod, host.player_id, 2, action="add_cpu", deck_id="edgar")
        pods.update_seat(pod, host.player_id, deck_id="aesi")
        assert pod.seats[1].deck_id == "edgar"
        assert pod.seats[2].deck_id == "edgar"

    def test_set_deck_and_set_agent_land_on_the_seat(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")
        pods.admin_seat(pod, host.player_id, 1, action="set_deck", deck_id="zurgo")
        pods.admin_seat(pod, host.player_id, 1, action="set_agent", agent="random")
        assert (pod.seats[1].deck_id, pod.seats[1].agent) == ("zurgo", "random")

    def test_an_unknown_deck_is_refused(self, pods):
        pod, (host,) = seated(pods, guests=0)
        with pytest.raises(PodError) as exc:
            pods.admin_seat(pod, host.player_id, 1, action="add_cpu", deck_id="nope")
        assert exc.value.code == "unknown_deck"

    def test_clear_empties_a_chair_and_open_chair_holds_it(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")
        pods.admin_seat(pod, host.player_id, 1, action="clear")
        assert pod.seats[1].kind == "empty"
        pods.admin_seat(pod, host.player_id, 1, action="open_chair")
        assert pod.seats[1].kind == "open"

    def test_every_admin_action_moves_the_version(self, pods):
        pod, (host,) = seated(pods, guests=0)
        before = pod.version
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")
        assert pod.version > before


class TestLockIn:
    def test_locking_with_no_deck_is_refused(self, pods):
        pod, (_host, guest) = seated(pods)
        with pytest.raises(PodError) as exc:
            pods.update_seat(pod, guest.player_id, locked=True)
        assert exc.value.code == "not_ready"
        assert not pod.seats[1].locked

    def test_a_stranger_has_no_seat_to_update(self, pods):
        pod, _ = seated(pods)
        with pytest.raises(PodError) as exc:
            pods.update_seat(pod, "nobody", deck_id="aesi")
        assert exc.value.code == "not_your_seat"

    def test_an_unknown_deck_is_refused(self, pods):
        pod, (_host, guest) = seated(pods)
        with pytest.raises(PodError) as exc:
            pods.update_seat(pod, guest.player_id, deck_id="black_lotus")
        assert exc.value.code == "unknown_deck"


class TestStart:
    def _ready_pod(self, pods, guests=1):
        pod, players = seated(pods, guests=guests)
        for player in players:
            pods.update_seat(pod, player.player_id, deck_id="aesi", locked=True)
        return pod, players

    def test_a_solo_pod_cannot_deal(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.update_seat(pod, host.player_id, deck_id="aesi", locked=True)
        with pytest.raises(PodError) as exc:
            pods.start(pod, host.player_id)
        assert exc.value.code == "not_ready"

    def test_an_unready_seat_blocks_the_deal(self, pods):
        pod, (host, guest) = seated(pods)
        pods.update_seat(pod, host.player_id, deck_id="aesi", locked=True)
        pods.update_seat(pod, guest.player_id, deck_id="edgar")
        with pytest.raises(PodError) as exc:
            pods.start(pod, host.player_id)
        assert exc.value.code == "not_ready"

    def test_only_the_host_deals(self, pods):
        pod, (_host, guest) = self._ready_pod(pods)
        with pytest.raises(PodError) as exc:
            pods.start(pod, guest.player_id)
        assert exc.value.code == "not_host"

    def test_dealing_moves_the_pod_to_the_table(self, pods):
        pod, (host, guest) = self._ready_pod(pods)
        session = pods.start(pod, host.player_id)
        assert pod.status == "in_game"
        assert pod.game_id == session.game_id
        assert pod.view_for(guest.player_id).game_id == session.game_id

    def test_seats_are_compacted_not_padded(self, pods):
        """[you, guest, empty, empty] is a two-player game, not a four-seat one."""
        pod, players = self._ready_pod(pods)
        session = pods.start(pod, players[0].player_id)
        assert len(session.seats) == 2
        assert [s.kind for s in session.seats] == ["human", "human"]

    def test_open_chairs_become_cpus(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.update_seat(pod, host.player_id, deck_id="aesi", locked=True)
        pods.admin_seat(pod, host.player_id, 1, action="open_chair")
        session = pods.start(pod, host.player_id)
        assert [s.kind for s in session.seats] == ["human", "ai"]

    def test_every_human_gets_a_token_mapped_to_their_table_seat(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.update_seat(pod, host.player_id, deck_id="aesi", locked=True)
        pods.admin_seat(pod, host.player_id, 1, action="add_cpu")
        _, guest = pods.join(pod.code, name="Guest")  # lands in seat 2
        pods.update_seat(pod, guest.player_id, deck_id="edgar", locked=True)

        session = pods.start(pod, host.player_id)
        # Lobby seats 0, 1, 2 compact to table seats 0, 1, 2 -- but the guest was
        # in lobby chair 2 and is at table seat 2 only because the CPU filled 1.
        assert session.tokens == {host.token: 0, guest.token: 2}
        assert session.seat_for_token(guest.token) == 2

    def test_the_seed_is_honoured(self, pods):
        pod, players = self._ready_pod(pods)
        pod.seed = 12345
        assert pods.start(pod, players[0].player_id).seed == 12345

    def test_dealing_twice_is_refused(self, pods):
        pod, players = self._ready_pod(pods)
        pods.start(pod, players[0].player_id)
        with pytest.raises(PodError) as exc:
            pods.start(pod, players[0].player_id)
        assert exc.value.code == "already_started"


class TestLifecycle:
    def test_a_guest_leaving_reopens_their_chair(self, pods):
        """The pod stays joinable at the same code."""
        pod, (_host, guest) = seated(pods)
        pods.leave(pod, guest.player_id)
        assert pod.seats[1].kind == "open"
        assert pod.status == "open"
        _, replacement = pods.join(pod.code, name="Replacement")
        assert replacement.seat == 1

    def test_the_host_leaving_transfers_the_pod(self, pods):
        pod, (host, guest) = seated(pods)
        pods.leave(pod, host.player_id)
        assert pod.host_id == guest.player_id
        assert pod.view_for(guest.player_id).you_are_host

    def test_the_host_leaving_transfers_by_seat_order(self, pods):
        pod, (host, first, _second) = seated(pods, guests=2)
        pods.leave(pod, host.player_id)
        assert pod.host_id == first.player_id

    def test_the_last_human_leaving_closes_the_pod(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.leave(pod, host.player_id)
        assert pod.status == "closed"
        assert pod.view_for(None).status == "closed"

    def test_leaving_twice_is_harmless(self, pods):
        pod, (_host, guest) = seated(pods)
        pods.leave(pod, guest.player_id)
        pods.leave(pod, guest.player_id)
        assert len(pod.players) == 1


class TestSweep:
    def test_an_idle_player_loses_their_chair(self, pods):
        pod, (host, guest) = seated(pods)
        later = max(p.last_seen for p in pod.players.values()) + L.PLAYER_TTL_SECONDS + 1
        # The host is kept alive; only the guest has gone quiet.
        pod.players[host.player_id].last_seen = later
        pods.sweep(now=later)
        assert guest.player_id not in pod.players
        assert pod.seats[1].kind == "open"

    def test_a_live_pod_is_left_alone(self, pods):
        pod, _players = seated(pods)
        pods.sweep()
        assert len(pod.players) == 2
        assert len(pods) == 1

    def test_an_abandoned_pod_is_evicted(self, pods):
        pod, _ = seated(pods)
        assert pods.sweep(now=pod.created + L.POD_TTL_SECONDS + 1) == 1
        assert len(pods) == 0

    def test_a_closed_pod_lingers_long_enough_to_say_so(self, pods):
        """"That pod closed" and "no such pod" are different things to read."""
        pod, (host,) = seated(pods, guests=0)
        pods.leave(pod, host.player_id)
        pods.sweep()
        assert pods.get(pod.code).status == "closed"

    def test_a_closed_pod_is_eventually_recycled(self, pods):
        pod, (host,) = seated(pods, guests=0)
        pods.leave(pod, host.player_id)
        assert pods.sweep(now=pod.closed_at + L.CLOSED_LINGER_SECONDS + 1) == 1
        assert len(pods) == 0

    def test_a_dealt_pod_survives_its_players_going_quiet(self, pods):
        """Everybody is at the table; nobody is polling the lobby any more."""
        pod, players = seated(pods)
        for player in players:
            pods.update_seat(pod, player.player_id, deck_id="aesi", locked=True)
        pods.start(pod, players[0].player_id)
        pods.sweep(now=players[0].last_seen + L.PLAYER_TTL_SECONDS + 1)
        assert pod.status == "in_game"
        assert len(pod.players) == 2


class TestDeckLookupIsLive:
    def test_a_pod_reads_decks_through_the_session_registry(self, pods, data):
        """``app.state.reload()`` rebinds ``sessions.data`` after an import.

        A pod that cached its own reference would leave the deck somebody just
        imported invisible in the lobby.
        """
        from dataclasses import replace

        from automtg.cards.registry import GameData

        pod, (host,) = seated(pods, guests=0)
        seat = pod.view_for(host.player_id).seats[0]
        assert seat.deck.name == "Aesi, Tyrant of Gyre Strait"

        # Stand in for what `reload()` does: build a fresh GameData and rebind it
        # onto the session registry, leaving the pod object untouched.
        fresh = GameData(
            registry=data.registry,
            decks={**data.decks, "aesi": replace(data.decks["aesi"], name="Aesi, Reloaded")},
        )
        pods.sessions.data = fresh
        assert pod.view_for(host.player_id).seats[0].deck.name == "Aesi, Reloaded"

    def test_a_deck_added_after_the_pod_opened_is_selectable(self, pods, data):
        from dataclasses import replace

        from automtg.cards.registry import GameData

        pod, (host,) = seated(pods, guests=0)
        with pytest.raises(PodError):
            pods.update_seat(pod, host.player_id, deck_id="imported")

        pods.sessions.data = GameData(
            registry=data.registry,
            decks={**data.decks, "imported": replace(data.decks["edgar"], id="imported")},
        )
        pods.update_seat(pod, host.player_id, deck_id="imported")
        assert pod.seats[0].deck_id == "imported"
