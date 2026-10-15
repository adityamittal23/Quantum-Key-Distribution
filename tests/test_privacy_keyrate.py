import numpy as np
import pytest

from qkd.key import Key
from qkd.keyrate import (
    binary_entropy,
    final_key_length,
    privacy_amplification_margin,
    qber_threshold,
    secret_fraction,
)
from qkd.privacy import ToeplitzHash, amplify

# --- key rate ------------------------------------------------------------


def test_binary_entropy_known_values():
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0
    assert binary_entropy(0.5) == pytest.approx(1.0)
    assert binary_entropy(0.11) == pytest.approx(0.4999, abs=1e-4)
    np.testing.assert_allclose(binary_entropy(np.array([0.25, 0.75])), [0.811278, 0.811278], atol=1e-6)


def test_binary_entropy_rejects_out_of_range():
    with pytest.raises(ValueError):
        binary_entropy(1.2)


def test_threshold_matches_the_11_percent_bound():
    assert qber_threshold(f=1.0) == pytest.approx(0.1100, abs=5e-4)
    assert qber_threshold(f=1.16) < qber_threshold(f=1.0)
    assert secret_fraction(qber_threshold(f=1.0), f=1.0) == pytest.approx(0.0, abs=1e-9)


def test_secret_fraction_shape():
    assert secret_fraction(0.0) == 1.0
    assert secret_fraction(0.2) == 0.0
    qs = np.linspace(0, 0.12, 25)
    rs = secret_fraction(qs)
    assert np.all(np.diff(rs) <= 0)
    with pytest.raises(ValueError):
        secret_fraction(0.05, f=0.9)


def test_final_key_length_formula():
    margin = privacy_amplification_margin(1e-10)
    assert margin == 67  # ceil(2 log2 1e10)
    n, q, leak = 10_000, 0.05, 3_400
    expected = int(np.floor(n * (1 - binary_entropy(q)) - leak - margin))
    assert final_key_length(n, q, leak) == expected
    assert final_key_length(100, 0.10, 90) == 0  # leakage exceeds secrecy
    assert final_key_length(100, float("nan"), 0) == 0


# --- Toeplitz hashing ----------------------------------------------------


@pytest.mark.parametrize(("n", "m"), [(1, 1), (16, 5), (100, 37), (257, 256)])
def test_fft_toeplitz_matches_explicit_matrix(n, m):
    rng = np.random.default_rng(n * 1000 + m)
    toeplitz = ToeplitzHash.random(n, m, rng)
    key = Key(rng.integers(0, 2, n, dtype=np.uint8))
    T = toeplitz.matrix()
    assert T.shape == (m, n)
    assert T[1:, 1:].tolist() == T[:-1, :-1].tolist()  # constant diagonals
    expected = (T.astype(np.int64) @ key.bits.astype(np.int64)) % 2
    assert toeplitz.apply(key).bits.tolist() == expected.tolist()


def test_fft_toeplitz_is_exact_on_large_keys():
    rng = np.random.default_rng(1)
    n, m = 60_000, 30_000
    toeplitz = ToeplitzHash.random(n, m, rng)
    key = Key(rng.integers(0, 2, n, dtype=np.uint8))
    out = toeplitz.apply(key).bits
    rows = rng.choice(m, size=20, replace=False)
    for i in rows:  # spot-check rows against the definition T[i, j] = t[i - j + n - 1]
        row = toeplitz.seed_bits[i - np.arange(n) + n - 1]
        assert out[i] == int(row.astype(np.int64) @ key.bits.astype(np.int64)) % 2


def test_hash_is_linear_over_gf2():
    rng = np.random.default_rng(2)
    toeplitz = ToeplitzHash.random(64, 20, rng)
    x, y = (Key(rng.integers(0, 2, 64, dtype=np.uint8)) for _ in range(2))
    lhs = toeplitz.apply(Key(x.bits ^ y.bits)).bits
    assert lhs.tolist() == (toeplitz.apply(x).bits ^ toeplitz.apply(y).bits).tolist()


def test_amplify_gives_identical_keys_of_requested_length():
    rng = np.random.default_rng(3)
    key = Key(rng.integers(0, 2, 1000, dtype=np.uint8))
    result = amplify(key, key, 400, np.random.default_rng(4))
    assert len(result.alice_key) == 400 and result.alice_key == result.bob_key


def test_amplified_output_is_balanced():
    rng = np.random.default_rng(5)
    key = Key(rng.integers(0, 2, 20_000, dtype=np.uint8))
    out = amplify(key, key, 10_000, rng).alice_key.bits
    assert out.mean() == pytest.approx(0.5, abs=4.5 * 0.5 / np.sqrt(10_000))


def test_toeplitz_validation():
    with pytest.raises(ValueError):
        ToeplitzHash(np.zeros(5, dtype=np.uint8), 3, 4)  # would lengthen the key
    with pytest.raises(ValueError):
        ToeplitzHash(np.zeros(5, dtype=np.uint8), 3, 2)  # needs exactly 3 + 2 - 1 = 4 seed bits
    with pytest.raises(ValueError):
        ToeplitzHash.random(3, 2, np.random.default_rng(0)).apply(Key([0, 1]))  # wrong input length
