"""Channel noise and photon loss (Member B).

Each effect works in both simulators:

* Qiskit mode puts an identity unitary labelled with the effect's name in the
  circuit and attaches the Aer error to that label, so the noise acts at the
  effect's position in the channel, separate effects never stack, and the
  circuit drawing names the noise;
* fast mode applies the same channel to BB84 eigenstates.

Expected sifted-key QBER for each effect on its own:

* depolarizing with parameter lam, rho -> (1 - lam) rho + lam I/2 (Qiskit's
  convention): QBER = lam / 2, because a fully mixed qubit gives a random bit;
* bit flip (X with probability p): QBER = p / 2, because X changes |0>/|1>
  but leaves |+>/|-> unchanged up to a global phase;
* readout error (Bob's detector reports the wrong bit with probability p):
  QBER = p;
* photon loss: no errors, it only shortens the key.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import UnitaryGate
from qiskit_aer.noise import ReadoutError, depolarizing_error, pauli_error

from qkd.channel import ChannelEffect, NoiseTerm
from qkd.key import Z_BASIS, Photons

FIBRE_LOSS_DB_PER_KM = 0.2  # typical telecom fibre at 1550 nm
_IDENTITY = np.eye(2)


def _check_probability(name: str, value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
    return float(value)


def loss_from_distance(km: float, db_per_km: float = FIBRE_LOSS_DB_PER_KM) -> float:
    """Photon-loss probability of ``km`` of fibre: 1 - 10^(-alpha L / 10)."""
    if km < 0 or db_per_km < 0:
        raise ValueError("distance and attenuation must be non-negative")
    return 1.0 - 10 ** (-db_per_km * km / 10)


class _FibreNoise(ChannelEffect):
    """Shared mechanics for noise that acts on the photon inside the fibre."""

    probability_name = "p"

    def __init__(self, p: float) -> None:
        self.p = _check_probability(self.probability_name, p)

    def append_to_circuit(self, qc: QuantumCircuit, index: int, plan: Any) -> None:
        # A labelled identity unitary: it does nothing itself, Aer attaches the error to its
        # label, and circuit drawings show the effect's name (a plain IGate draws as "I").
        qc.append(UnitaryGate(_IDENTITY, label=self.name), [0])

    def describe(self) -> dict[str, Any]:
        return {"effect": self.name, self.probability_name: self.p}


class Depolarizing(_FibreNoise):
    """With probability ``lam`` the photon is replaced by the maximally mixed state."""

    name = "depolarizing"
    probability_name = "lam"

    def transmit_numpy(self, photons: Photons, plan: Any, rng: np.random.Generator) -> Photons:
        # I/2 is an equal mixture of |0> and |1>, i.e. a Z eigenstate with a random value.
        hit = rng.random(len(photons)) < self.p
        random_values = rng.integers(0, 2, size=len(photons), dtype=np.uint8)
        return photons.replace(
            values=np.where(hit, random_values, photons.values),
            bases=np.where(hit, Z_BASIS, photons.bases),
        )

    def noise_terms(self) -> tuple[NoiseTerm, ...]:
        return (NoiseTerm(depolarizing_error(self.p, 1), (self.name,)),)


class BitFlip(_FibreNoise):
    """Pauli X with probability ``p``: flips Z-basis states and leaves X-basis states alone."""

    name = "bit_flip"

    def transmit_numpy(self, photons: Photons, plan: Any, rng: np.random.Generator) -> Photons:
        flip = (rng.random(len(photons)) < self.p) & (photons.bases == Z_BASIS)
        return photons.replace(values=np.where(flip, 1 - photons.values, photons.values))

    def noise_terms(self) -> tuple[NoiseTerm, ...]:
        return (NoiseTerm(pauli_error([("X", self.p), ("I", 1 - self.p)]), (self.name,)),)


class ReadoutNoise(ChannelEffect):
    """Bob's detector reports the wrong bit with probability ``p``.

    In Qiskit mode this is an Aer ``ReadoutError``. Aer applies it to every
    measurement, so it also affects Eve's recorded bits, but it changes only the
    recorded classical value and not the collapsed state, so the photon Eve
    resends to Bob is unaffected.
    """

    name = "readout"

    def __init__(self, p: float) -> None:
        self.p = _check_probability("p", p)

    def transmit_numpy(self, photons: Photons, plan: Any, rng: np.random.Generator) -> Photons:
        return photons

    def detect_numpy(self, bits: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        flip = rng.random(len(bits)) < self.p
        return np.where(flip, 1 - bits, bits).astype(np.uint8)

    def noise_terms(self) -> tuple[NoiseTerm, ...]:
        return (NoiseTerm(ReadoutError([[1 - self.p, self.p], [self.p, 1 - self.p]])),)

    def describe(self) -> dict[str, Any]:
        return {"effect": self.name, "p": self.p}


class PhotonLoss(ChannelEffect):
    """Each photon is lost with probability ``p`` and never reaches Bob's detector.

    Loss is a classical erasure: Bob sees no click and both parties drop that
    position during sifting. The lost photons are drawn in ``sample``, so both
    simulators lose exactly the same photons.
    """

    name = "photon_loss"

    def __init__(self, p: float) -> None:
        self.p = _check_probability("p", p)

    @classmethod
    def from_distance(cls, km: float, db_per_km: float = FIBRE_LOSS_DB_PER_KM) -> PhotonLoss:
        return cls(loss_from_distance(km, db_per_km))

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.random(n) < self.p

    def transmit_numpy(self, photons: Photons, plan: np.ndarray, rng: np.random.Generator) -> Photons:
        return photons.replace(lost=photons.lost | plan)

    def lost_mask(self, plan: np.ndarray, n: int) -> np.ndarray:
        return plan

    def describe(self) -> dict[str, Any]:
        return {"effect": self.name, "p": self.p}
