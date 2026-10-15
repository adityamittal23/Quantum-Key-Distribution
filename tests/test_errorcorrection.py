import numpy as np
import pytest

from qkd.errorcorrection import cascade, first_block_size
from qkd.key import Key
from qkd.keyrate import binary_entropy


def _noisy_pair(n, q, seed):
    rng = np.random.default_rng(seed)
    alice = rng.integers(0, 2, n, dtype=np.uint8)
    errors = rng.random(n) < q
    return Key(alice), Key(alice ^ errors), int(errors.sum())


@pytest.mark.parametrize("q", [0.01, 0.03, 0.05, 0.08, 0.10])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_cascade_makes_keys_identical_below_threshold(q, seed):
    alice, bob, _ = _noisy_pair(20_000, q, seed)
    result = cascade(alice, bob, q, np.random.default_rng(seed + 50))
    assert result.bob_key == alice
    assert result.verified
    assert result.alice_key is alice  # Alice's key is never modified


@pytest.mark.parametrize("q", [0.02, 0.05, 0.10])
def test_cascade_leaks_at_least_the_shannon_limit(q):
    alice, bob, errors = _noisy_pair(20_000, q, 3)
    result = cascade(alice, bob, q, np.random.default_rng(4))
    true_q = errors / len(alice)
    # No reconciliation can reveal less than n h(Q); Cascade is typically 1.1 to 1.25 times that.
    assert result.leaked_bits >= len(alice) * binary_entropy(true_q)
    assert 1.0 <= result.efficiency(true_q) <= 1.35
    assert result.corrections >= errors  # every error flipped, possibly some twice


def test_identical_keys_need_no_corrections():
    alice, _, _ = _noisy_pair(5000, 0.0, 5)
    result = cascade(alice, alice, 0.0, np.random.default_rng(6))
    assert result.corrections == 0 and result.verified and result.bob_key == alice


def test_verification_catches_a_failed_correction():
    # One pass with blocks far too large for the real error rate leaves errors behind.
    alice, bob, _ = _noisy_pair(20_000, 0.10, 7)
    result = cascade(alice, bob, qber_estimate=0.001, rng=np.random.default_rng(8), passes=1)
    assert result.bob_key != alice
    assert not result.verified


def test_cascade_is_reproducible_for_a_seed():
    alice, bob, _ = _noisy_pair(5000, 0.05, 9)
    a = cascade(alice, bob, 0.05, np.random.default_rng(10))
    b = cascade(alice, bob, 0.05, np.random.default_rng(10))
    assert a.leaked_bits == b.leaked_bits and a.bob_key == b.bob_key


def test_empty_keys():
    result = cascade(Key([]), Key([]), 0.05, np.random.default_rng(0))
    assert len(result.bob_key) == 0 and result.verified


def test_first_block_size():
    assert first_block_size(0.05, 10_000) == 15  # ceil(0.73 / 0.05)
    assert first_block_size(0.0, 10_000) == 730  # floored QBER
    assert first_block_size(0.0, 100) == 100  # never larger than the key
    assert first_block_size(0.5, 10_000) == 4  # minimum block


@pytest.mark.parametrize("kwargs", [{"passes": 0}, {"verify_bits": -1}])
def test_cascade_validates_arguments(kwargs):
    alice, bob, _ = _noisy_pair(100, 0.05, 0)
    with pytest.raises(ValueError):
        cascade(alice, bob, 0.05, np.random.default_rng(0), **kwargs)


def test_cascade_requires_equal_lengths():
    with pytest.raises(ValueError):
        cascade(Key([0, 1]), Key([0]), 0.05, np.random.default_rng(0))
