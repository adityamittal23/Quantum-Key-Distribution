"""End-to-end QKD run (Member C): BB84 plus classical post-processing.

``run_qkd`` performs all six steps of the plan:

* steps 1 to 5 run through ``core.run_bb84``: preparation, channel, measurement,
  sifting, and QBER estimation with the abort check;
* step 6 is Cascade error correction, hash verification and Toeplitz privacy
  amplification.

A run ends in one of three outcomes:

* ``aborted_qber``: the estimated QBER is above the threshold, so the parties
  stop before error correction;
* ``aborted_verification``: the hashes differ after Cascade, so the keys may
  still differ and are discarded;
* ``ok``: both parties hold the same final key. That key can still be empty
  if the leaked information used up the whole key.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from qkd.channel import Channel
from qkd.core import (
    DEFAULT_QBER_THRESHOLD,
    DEFAULT_SAMPLE_FRACTION,
    RECONCILIATION_STREAM,
    Mode,
    ProtocolResult,
    run_bb84,
    stream,
)
from qkd.errorcorrection import DEFAULT_PASSES, DEFAULT_VERIFY_BITS, CascadeResult, cascade
from qkd.key import Key
from qkd.keyrate import DEFAULT_PA_EPSILON, final_key_length, secret_fraction
from qkd.privacy import PrivacyResult, amplify


@dataclass(frozen=True, eq=False)
class QKDResult:
    protocol: ProtocolResult
    cascade: CascadeResult | None
    privacy: PrivacyResult | None
    status: str  # "ok", "aborted_qber" or "aborted_verification"

    @property
    def final_alice_key(self) -> Key:
        return self.privacy.alice_key if self.privacy else Key([])

    @property
    def final_bob_key(self) -> Key:
        return self.privacy.bob_key if self.privacy else Key([])

    @property
    def keys_match(self) -> bool:
        return self.status == "ok" and self.final_alice_key == self.final_bob_key

    def summary(self) -> dict[str, float | int | bool | str]:
        row = dict(self.protocol.summary())
        q = self.protocol.qber.qber
        ec = self.cascade
        row.update(
            status=self.status,
            ec_leaked_bits=ec.leaked_bits if ec else 0,
            ec_corrections=ec.corrections if ec else 0,
            ec_efficiency=ec.efficiency(q) if ec else float("nan"),
            ec_residual_errors=ec.alice_key.mismatches(ec.bob_key) if ec else -1,
            final_key_length=len(self.final_alice_key),
            keys_match=self.keys_match,
            secret_fraction_asymptotic=0.0 if math.isnan(q) else secret_fraction(q),
            final_bits_per_photon=len(self.final_alice_key) / self.protocol.n,
        )
        return row


def run_qkd(
    n: int,
    channel: Channel = Channel(),
    mode: Mode = "numpy",
    seed: int = 0,
    sample_fraction: float = DEFAULT_SAMPLE_FRACTION,
    threshold: float = DEFAULT_QBER_THRESHOLD,
    ec_passes: int = DEFAULT_PASSES,
    verify_bits: int = DEFAULT_VERIFY_BITS,
    epsilon: float = DEFAULT_PA_EPSILON,
) -> QKDResult:
    """Run BB84 and, unless it aborts, error correction and privacy amplification."""
    protocol = run_bb84(n, channel, mode, seed, sample_fraction, threshold)
    if protocol.aborted:
        return QKDResult(protocol, None, None, "aborted_qber")

    rng = stream(seed, RECONCILIATION_STREAM)
    # Blocks are sized from an upper bound on Q: a sample that underestimates the error
    # rate would otherwise give blocks too large for Cascade to clear, and verification would fail.
    block_qber = protocol.qber.upper_bound()
    corrected = cascade(protocol.alice_key, protocol.bob_key, block_qber, rng, ec_passes, verify_bits)
    if not corrected.verified:
        return QKDResult(protocol, corrected, None, "aborted_verification")

    m = final_key_length(len(corrected.alice_key), protocol.qber.qber, corrected.leaked_bits, epsilon)
    amplified = amplify(corrected.alice_key, corrected.bob_key, m, rng)
    return QKDResult(protocol, corrected, amplified, "ok")
