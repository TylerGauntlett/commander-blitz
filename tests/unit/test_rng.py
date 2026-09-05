"""The engine's one random source, pinned method by method.

Determinism is what makes undo-by-replay and golden replays possible, and every
shuffle and coin flip in the engine goes through this class. The three methods
nothing else reached -- `choice`, `random`, `setstate` -- are what a replay
would need first (TECH_DEBT CG-06's neighbour: `rng.py` was 88%).
"""

from __future__ import annotations

from automtg.engine.rng import Rng


def test_the_same_seed_gives_the_same_sequence_every_way_it_is_drawn():
    a, b = Rng(7), Rng(7)
    assert a.shuffled(range(10)) == b.shuffled(range(10))
    assert [a.randint(1, 6) for _ in range(5)] == [b.randint(1, 6) for _ in range(5)]
    assert a.random() == b.random()
    assert a.choice("abc") == b.choice("abc")


def test_a_missing_seed_is_seed_zero_and_an_explicit_one_is_kept():
    assert Rng().seed == 0
    assert Rng(None).seed == 0
    assert Rng("12").seed == 12


def test_shuffle_is_in_place_and_shuffled_is_a_copy():
    rng = Rng(3)
    seq = list(range(8))
    copy = rng.shuffled(seq)
    assert seq == list(range(8))
    assert sorted(copy) == seq
    rng.shuffle(seq)
    assert sorted(seq) == list(range(8))


def test_choice_draws_from_the_sequence_and_random_stays_in_range():
    rng = Rng(11)
    for _ in range(50):
        assert rng.choice((1, 2, 3)) in (1, 2, 3)
        assert 0.0 <= rng.random() < 1.0


def test_state_round_trips_so_a_replay_can_resume_mid_stream():
    rng = Rng(5)
    rng.random()
    saved = rng.getstate()
    ahead = [rng.randint(0, 99) for _ in range(4)]
    rng.setstate(saved)
    assert [rng.randint(0, 99) for _ in range(4)] == ahead
