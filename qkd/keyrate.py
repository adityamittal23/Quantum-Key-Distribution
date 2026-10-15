"""Secret key rate (Member C).

Asymptotic one-way BB84 secret fraction, from the plan:

    r(Q) = 1 - h(Q) - f h(Q),   h(x) = -x log2 x - (1 - x) log2 (1 - x)

The first h(Q) is what Eve may know about the key, given the disturbance Q.
The f h(Q) term is what error correction reveals; f >= 1 is the
error-correction inefficiency, and f = 1 is the Shannon limit. r reaches zero at
Q of about 11% for f = 1, which is where the protocol must abort.

For a finished run, ``final_key_length`` uses the bits Cascade actually leaked
rather than the f h(Q) estimate.
"""

from __future__ import annotations

import math

import numpy as np

DEFAULT_EC_EFFICIENCY = 1.16  # middle of the plan's 1.1 to 1.2 range for Cascade
DEFAULT_PA_EPSILON = 1e-10  # failure probability allowed for privacy amplification


def binary_entropy(x: float | np.ndarray) -> float | np.ndarray:
    """h(x) in bits, with h(0) = h(1) = 0. Accepts scalars or arrays."""
    arr = np.asarray(x, dtype=float)
    if np.any((arr < 0) | (arr > 1)):
        raise ValueError("binary entropy is defined on [0, 1]")
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -arr * np.log2(arr) - (1 - arr) * np.log2(1 - arr)
    h = np.where((arr == 0) | (arr == 1), 0.0, h)
    return float(h) if h.ndim == 0 else h


def secret_fraction(qber: float | np.ndarray, f: float = DEFAULT_EC_EFFICIENCY) -> float | np.ndarray:
    """Asymptotic secret bits per sifted bit, r = max(0, 1 - h(Q) - f h(Q))."""
    if f < 1:
        raise ValueError(f"error-correction efficiency f must be >= 1, got {f}")
    q = np.minimum(np.asarray(qber, dtype=float), 0.5)  # Q above 1/2 carries no extra meaning
    r = np.maximum(0.0, 1 - (1 + f) * binary_entropy(q))
    return float(r) if np.ndim(r) == 0 else r


def qber_threshold(f: float = DEFAULT_EC_EFFICIENCY, tol: float = 1e-12) -> float:
    """The QBER where r(Q) = 0, by bisection (about 0.110 for f = 1)."""
    lo, hi = 0.0, 0.5
    while hi - lo > tol:
        mid = (lo + hi) / 2
        if 1 - (1 + f) * binary_entropy(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def privacy_amplification_margin(epsilon: float = DEFAULT_PA_EPSILON) -> int:
    """Leftover-hash-lemma cost 2 log2(1/epsilon) bits for an epsilon-secure output."""
    if not 0 < epsilon < 1:
        raise ValueError(f"epsilon must be in (0, 1), got {epsilon}")
    return math.ceil(2 * math.log2(1 / epsilon))


def final_key_length(
    corrected_length: int,
    qber: float,
    leaked_bits: int,
    epsilon: float = DEFAULT_PA_EPSILON,
) -> int:
    """Secret bits that survive privacy amplification:

    m = floor(n (1 - h(Q)) - leak_EC - 2 log2(1/epsilon)), clipped at 0.

    The QBER is the sampled estimate, used without finite-size corrections
    (finite-key analysis is a stretch goal in the plan).
    """
    if corrected_length < 0 or leaked_bits < 0:
        raise ValueError("lengths must be non-negative")
    if not np.isfinite(qber):
        return 0
    eve_information = corrected_length * binary_entropy(min(qber, 0.5))
    m = corrected_length - eve_information - leaked_bits - privacy_amplification_margin(epsilon)
    return max(0, math.floor(m))
