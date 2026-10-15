"""Basis sifting (Member A).

After transmission Alice and Bob announce their bases on the public channel
and keep only the positions where the bases match and Bob detected a photon.
For random bases about half the detected positions survive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from qkd.key import AlicePrep, BobMeasurement, Key


@dataclass(frozen=True, eq=False)
class SiftResult:
    """Positions kept by sifting and the two parties' sifted keys."""

    indices: np.ndarray  # positions in the original photon stream
    alice_key: Key
    bob_key: Key

    def __len__(self) -> int:
        return len(self.alice_key)

    @property
    def true_qber(self) -> float:
        """Error rate over the whole sifted key.

        Only a simulator can know this, because it sees both keys. The protocol
        itself uses the sampled estimate from ``qber.estimate_qber``.
        """
        return self.alice_key.error_rate(self.bob_key) if len(self) else float("nan")


def sift(alice: AlicePrep, bob: BobMeasurement) -> SiftResult:
    """Keep detected positions where Alice's and Bob's bases agree."""
    if len(alice) != len(bob):
        raise ValueError(f"Alice sent {len(alice)} photons but Bob has {len(bob)} records")
    keep = bob.detected & (alice.bases == bob.bases)
    indices = np.flatnonzero(keep)
    indices.setflags(write=False)
    return SiftResult(indices=indices, alice_key=Key(alice.bits[keep]), bob_key=Key(bob.bits[keep]))
