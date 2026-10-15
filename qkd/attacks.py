"""Eavesdropper attacks and their detection (Member B).

Intercept-resend is the simplest attack that the no-cloning theorem forces on
Eve. She cannot copy an unknown qubit, so to learn anything she must measure
it, and she then has to send Bob a replacement. She picks her basis at random:

* right basis (probability 1/2): she reads Alice's bit and resends the same
  state, so no error is introduced;
* wrong basis (probability 1/2): her outcome is random, she resends a state in
  the wrong basis, and Bob, measuring in Alice's basis, gets a random bit, wrong
  with probability 1/2.

The errors on the sifted key are therefore 1/2 x 1/2 = 25% when she intercepts
everything, and 25% x p when she intercepts a fraction p.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit

from qkd.channel import ChannelEffect
from qkd.key import X_BASIS, Photons, as_bit_array, as_mask

EVE_REGISTER = "eve"
FULL_ATTACK_QBER = 0.25


def expected_qber_intercept_resend(fraction: float) -> float:
    """Analytic sifted-key QBER for intercept-resend on a fraction of photons."""
    return FULL_ATTACK_QBER * fraction


def detection_probability(qber: float, sample_size: int, threshold: float) -> float:
    """Probability that the sampled QBER exceeds ``threshold``, so the protocol aborts.

    The number of errors in a sample of ``m`` bits is Binomial(m, qber); the
    protocol aborts when errors / m > threshold. Computed in log space so it
    stays accurate for samples of many thousands of bits.
    """
    if sample_size <= 0:
        raise ValueError(f"sample_size must be positive, got {sample_size}")
    if not 0.0 <= qber <= 1.0:
        raise ValueError(f"qber must be in [0, 1], got {qber}")
    first_abort = math.floor(threshold * sample_size) + 1  # smallest error count with k/m > threshold
    if first_abort > sample_size:
        return 0.0
    if qber == 0.0:
        return 0.0
    if qber == 1.0:
        return 1.0
    log_q, log_not_q = math.log(qber), math.log1p(-qber)
    log_terms = [
        math.lgamma(sample_size + 1) - math.lgamma(k + 1) - math.lgamma(sample_size - k + 1)
        + k * log_q + (sample_size - k) * log_not_q
        for k in range(first_abort, sample_size + 1)
    ]
    peak = max(log_terms)
    return min(1.0, math.exp(peak) * math.fsum(math.exp(t - peak) for t in log_terms))


@dataclass(frozen=True, eq=False)
class EvePlan:
    """Which photons Eve intercepts and the basis she measures each one in."""

    intercepted: np.ndarray
    bases: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "intercepted", as_mask(self.intercepted, "intercepted"))
        object.__setattr__(self, "bases", as_bit_array(self.bases, "bases"))


class InterceptResend(ChannelEffect):
    """Eve measures each photon with probability ``fraction`` in a random basis and resends it."""

    name = "intercept_resend"

    def __init__(self, fraction: float = 1.0) -> None:
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"intercept fraction must be in [0, 1], got {fraction}")
        self.fraction = float(fraction)

    def sample(self, n: int, rng: np.random.Generator) -> EvePlan:
        intercepted = rng.random(n) < self.fraction
        bases = rng.integers(0, 2, size=n, dtype=np.uint8)
        return EvePlan(intercepted=intercepted, bases=bases)

    def transmit_numpy(self, photons: Photons, plan: EvePlan, rng: np.random.Generator) -> Photons:
        same_basis = plan.bases == photons.bases
        random_outcomes = rng.integers(0, 2, size=len(photons), dtype=np.uint8)
        eve_bits = np.where(same_basis, photons.values, random_outcomes)
        # Measurement collapses the photon to Eve's outcome in Eve's basis; that is what she resends.
        values = np.where(plan.intercepted, eve_bits, photons.values)
        bases = np.where(plan.intercepted, plan.bases, photons.bases)
        return photons.replace(values=values, bases=bases)

    def append_to_circuit(self, qc: QuantumCircuit, index: int, plan: EvePlan) -> None:
        if not plan.intercepted[index]:
            return
        register = ClassicalRegister(1, EVE_REGISTER)
        qc.add_register(register)
        eve_basis = int(plan.bases[index])
        if eve_basis == X_BASIS:
            qc.h(0)
        # A real mid-circuit measurement: the qubit collapses and the collapsed
        # state is what continues to Bob, which is the resend.
        qc.measure(0, register[0])
        if eve_basis == X_BASIS:
            qc.h(0)

    def describe(self) -> dict[str, Any]:
        return {"effect": self.name, "fraction": self.fraction}
