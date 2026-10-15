import numpy as np
import pytest

from qkd.key import AlicePrep, BobMeasurement, Key
from qkd.qber import estimate_qber, sample_size_for
from qkd.sifting import sift


def test_sift_keeps_detected_matching_bases_only():
    alice = AlicePrep(bits=[1, 0, 1, 1, 0], bases=[0, 1, 1, 0, 0])
    bob = BobMeasurement(
        bases=[0, 0, 1, 0, 0], bits=[1, 1, 1, 0, 0], detected=[True, True, True, False, True]
    )
    result = sift(alice, bob)
    assert result.indices.tolist() == [0, 2, 4]
    assert str(result.alice_key) == "110"
    assert str(result.bob_key) == "110"
    assert result.true_qber == 0.0


def test_sift_rejects_length_mismatch():
    with pytest.raises(ValueError):
        sift(AlicePrep([0], [0]), BobMeasurement([0, 0], [0, 0], [True, True]))


def test_empty_sift_has_nan_true_qber():
    result = sift(AlicePrep([0], [0]), BobMeasurement([1], [0], [True]))
    assert len(result) == 0 and np.isnan(result.true_qber)


def test_qber_sample_is_removed_from_both_keys():
    alice = Key(np.zeros(100, dtype=np.uint8))
    bob = Key(np.r_[np.ones(10), np.zeros(90)].astype(np.uint8))
    est = estimate_qber(alice, bob, 0.2, np.random.default_rng(0))
    assert est.sample_size == 20
    assert len(est.alice_remaining) == len(est.bob_remaining) == 80
    # Every error is either in the sample or left in the remaining key.
    assert est.errors + est.alice_remaining.mismatches(est.bob_remaining) == 10
    assert est.qber == est.errors / 20


def test_wilson_upper_bound():
    zero_errors = estimate_qber(Key(np.zeros(100, dtype=np.uint8)), Key(np.zeros(100, dtype=np.uint8)),
                                0.5, np.random.default_rng(0))
    assert zero_errors.qber == 0.0
    assert zero_errors.upper_bound(2.0) == pytest.approx(4 / 54, rel=1e-9)  # z^2 / (m + z^2) when Q = 0
    alice = Key(np.zeros(1000, dtype=np.uint8))
    bob = Key(np.r_[np.ones(100), np.zeros(900)].astype(np.uint8))
    est = estimate_qber(alice, bob, 0.5, np.random.default_rng(1))
    assert est.qber < est.upper_bound(2.0) < est.upper_bound(3.0) < est.qber + 4 * est.standard_error + 0.01


def test_qber_on_empty_key_is_nan():
    est = estimate_qber(Key([]), Key([]), 0.2, np.random.default_rng(0))
    assert est.sample_size == 0 and np.isnan(est.qber) and np.isnan(est.standard_error)


@pytest.mark.parametrize(("length", "fraction", "expected"), [(0, 0.2, 0), (3, 0.1, 1), (100, 0.25, 25)])
def test_sample_size(length, fraction, expected):
    assert sample_size_for(length, fraction) == expected


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1])
def test_sample_fraction_must_be_proper(fraction):
    with pytest.raises(ValueError):
        sample_size_for(10, fraction)
