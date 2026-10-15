import numpy as np
import pytest

from qkd.key import AlicePrep, BobMeasurement, Key, Photons, X_BASIS, Z_BASIS


def test_key_rejects_non_binary_values():
    with pytest.raises(ValueError):
        Key(np.array([0, 1, 2]))


def test_key_bits_are_read_only_copies():
    source = np.array([0, 1, 1], dtype=np.uint8)
    key = Key(source)
    source[0] = 1
    assert str(key) == "011"
    with pytest.raises(ValueError):
        key.bits[0] = 1


def test_key_error_rate_counts_mismatches():
    a = Key.from_string("0101")
    b = Key.from_string("0111")
    assert a.mismatches(b) == 1
    assert a.error_rate(b) == pytest.approx(0.25)
    assert Key([]).error_rate(Key([])) == 0.0


def test_key_error_rate_requires_equal_length():
    with pytest.raises(ValueError):
        Key.from_string("01").error_rate(Key.from_string("011"))


def test_key_select_and_without_return_new_keys():
    key = Key.from_string("10110")
    assert str(key.select(np.array([0, 2]))) == "11"
    assert str(key.without(np.array([0, 2]))) == "010"
    assert str(key) == "10110"


def test_alice_prep_requires_matching_lengths():
    with pytest.raises(ValueError):
        AlicePrep(bits=[0, 1], bases=[Z_BASIS])


def test_photons_replace_keeps_original():
    alice = AlicePrep(bits=[0, 1], bases=[Z_BASIS, X_BASIS])
    photons = Photons.from_alice(alice)
    flipped = photons.replace(values=1 - photons.values)
    assert photons.values.tolist() == [0, 1]
    assert flipped.values.tolist() == [1, 0]
    assert not photons.lost.any()


def test_bob_measurement_validates_detected_mask():
    with pytest.raises(ValueError):
        BobMeasurement(bases=[0, 1], bits=[0, 1], detected=[True])
