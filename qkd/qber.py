"""QBER estimation (Member A).

Alice and Bob publicly compare a random sample of the sifted key. The sampled
bits are revealed to Eve, so both parties discard them. The fraction of
disagreements in the sample estimates the quantum bit error rate Q.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qkd.key import Key

DEFAULT_UPPER_BOUND_Z = 2.0  # about a 97.7% one-sided confidence level


@dataclass(frozen=True, eq=False)
class QberEstimate:
    sample_indices: np.ndarray  # positions within the sifted key
    errors: int
    alice_remaining: Key
    bob_remaining: Key

    @property
    def sample_size(self) -> int:
        return int(self.sample_indices.size)

    @property
    def qber(self) -> float:
        """Estimated QBER; NaN when nothing could be sampled."""
        return self.errors / self.sample_size if self.sample_size else float("nan")

    def upper_bound(self, z: float = DEFAULT_UPPER_BOUND_Z) -> float:
        """Wilson score upper confidence bound on the QBER; NaN when nothing was sampled.

        Unlike Q + z SE, it stays above zero when the sample has no errors, so a
        lucky sample cannot make error correction trust a perfect channel.
        """
        m = self.sample_size
        if not m:
            return float("nan")
        q = self.qber
        centre = q + z * z / (2 * m)
        spread = z * np.sqrt(q * (1 - q) / m + z * z / (4 * m * m))
        return float(min(1.0, (centre + spread) / (1 + z * z / m)))

    @property
    def standard_error(self) -> float:
        """Binomial standard error of the estimate, sqrt(Q(1 - Q) / m)."""
        if not self.sample_size:
            return float("nan")
        q = self.qber
        return float(np.sqrt(q * (1 - q) / self.sample_size))


def sample_size_for(length: int, fraction: float) -> int:
    """Number of bits to sacrifice: round(fraction * length), at least 1 when possible."""
    if not 0.0 < fraction < 1.0:
        raise ValueError(f"sample fraction must be in (0, 1), got {fraction}")
    if length == 0:
        return 0
    return min(length, max(1, round(fraction * length)))


def estimate_qber(
    alice_key: Key, bob_key: Key, fraction: float, rng: np.random.Generator
) -> QberEstimate:
    """Sacrifice a random ``fraction`` of the sifted key to estimate the QBER."""
    if len(alice_key) != len(bob_key):
        raise ValueError(f"sifted keys differ in length: {len(alice_key)} vs {len(bob_key)}")
    m = sample_size_for(len(alice_key), fraction)
    sample = np.sort(rng.choice(len(alice_key), size=m, replace=False)) if m else np.array([], dtype=np.int64)
    sample.setflags(write=False)
    errors = alice_key.select(sample).mismatches(bob_key.select(sample))
    return QberEstimate(
        sample_indices=sample,
        errors=errors,
        alice_remaining=alice_key.without(sample),
        bob_remaining=bob_key.without(sample),
    )
