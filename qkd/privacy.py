"""Privacy amplification by Toeplitz hashing (Member C).

After error correction Alice and Bob share an n-bit key, but Eve may know part
of it, from her attack and from the public Cascade parities. Both parties
apply the same random m x n Toeplitz matrix T (a universal hash family) to the
key over GF(2). By the leftover hash lemma the m-bit output is almost uniform
and independent of Eve's knowledge, provided m stays below the key's
remaining secrecy; ``keyrate.final_key_length`` gives that m.

T is fixed by its first column and first row (n + m - 1 public random bits),
T[i, j] = t[i - j + n - 1]. T x is then one slice of the convolution t * x,
which is computed with an FFT in O(n log n) instead of forming the matrix.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qkd.key import Key, as_bit_array


@dataclass(frozen=True, eq=False)
class ToeplitzHash:
    """A public Toeplitz matrix mapping ``input_length`` bits to ``output_length`` bits."""

    seed_bits: np.ndarray  # n + m - 1 bits that define T
    input_length: int
    output_length: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "seed_bits", as_bit_array(self.seed_bits, "seed_bits"))
        if self.input_length < 0 or self.output_length < 0:
            raise ValueError("lengths must be non-negative")
        if self.output_length > self.input_length:
            raise ValueError("privacy amplification cannot lengthen the key")
        expected = max(self.input_length + self.output_length - 1, 0)
        if self.seed_bits.size != expected:
            raise ValueError(f"need {expected} seed bits, got {self.seed_bits.size}")

    @classmethod
    def random(cls, input_length: int, output_length: int, rng: np.random.Generator) -> ToeplitzHash:
        size = max(input_length + output_length - 1, 0)
        return cls(rng.integers(0, 2, size=size, dtype=np.uint8), input_length, output_length)

    def matrix(self) -> np.ndarray:
        """The explicit m x n matrix, for small sizes, tests and the dashboard."""
        n, m = self.input_length, self.output_length
        i, j = np.indices((m, n))
        return self.seed_bits[i - j + n - 1]

    def apply(self, key: Key) -> Key:
        n, m = self.input_length, self.output_length
        if len(key) != n:
            raise ValueError(f"hash expects {n} bits, got {len(key)}")
        if m == 0:
            return Key([])
        size = 1 << int(np.ceil(np.log2(self.seed_bits.size + n)))
        spectrum = np.fft.rfft(self.seed_bits.astype(float), size) * np.fft.rfft(key.bits.astype(float), size)
        conv = np.rint(np.fft.irfft(spectrum, size)[n - 1:n - 1 + m]).astype(np.int64)
        return Key(conv % 2)


@dataclass(frozen=True, eq=False)
class PrivacyResult:
    alice_key: Key
    bob_key: Key
    hash: ToeplitzHash


def amplify(alice_key: Key, bob_key: Key, output_length: int, rng: np.random.Generator) -> PrivacyResult:
    """Compress both corrected keys with one shared random Toeplitz hash."""
    if len(alice_key) != len(bob_key):
        raise ValueError(f"keys differ in length: {len(alice_key)} vs {len(bob_key)}")
    toeplitz = ToeplitzHash.random(len(alice_key), output_length, rng)
    return PrivacyResult(alice_key=toeplitz.apply(alice_key), bob_key=toeplitz.apply(bob_key), hash=toeplitz)
