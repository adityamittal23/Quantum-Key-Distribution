"""Core BB84 protocol (Member A): Alice, Bob and the two simulators.

Both simulators implement ``transmit_and_measure`` with the same signature, so
``run_bb84`` switches between them with one argument:

* ``QiskitSimulator`` builds one circuit per photon: Alice's preparation, the
  channel's gates, then Bob's measurement in his basis, run on Aer.
* ``NumpySimulator`` applies the same physics to arrays and handles 10^5+
  photons in milliseconds. ``tests/test_core.py`` checks it against the
  Qiskit mode.

Randomness comes from three independent streams split off one master seed:

* the protocol stream (Alice's bits and bases, Bob's bases, channel plans);
* the measurement stream (quantum outcomes);
* the post-processing stream (the QBER sample).

The two modes therefore share every classical choice, and they differ only
in the measurement outcomes, which are quantum-random.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit_aer import AerSimulator

from qkd.channel import Channel
from qkd.key import X_BASIS, AlicePrep, BobMeasurement, Key, Photons, as_bit_array
from qkd.qber import QberEstimate, estimate_qber
from qkd.sifting import SiftResult, sift

Mode = Literal["qiskit", "numpy"]

DEFAULT_SAMPLE_FRACTION = 0.2
DEFAULT_QBER_THRESHOLD = 0.11  # asymptotic one-way BB84 bound used by the plan
BOB_REGISTER = "bob"
_SEED_LIMIT = 2**31 - 1


class Simulator(Protocol):
    name: str

    def transmit_and_measure(
        self,
        alice: AlicePrep,
        bob_bases: np.ndarray,
        channel: Channel,
        plans: tuple,
        rng: np.random.Generator,
    ) -> BobMeasurement: ...


def random_bits(n: int, rng: np.random.Generator) -> np.ndarray:
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    return rng.integers(0, 2, size=n, dtype=np.uint8)


def prepare_alice(n: int, rng: np.random.Generator) -> AlicePrep:
    """Alice draws ``n`` random bits and ``n`` random bases (Z or X)."""
    return AlicePrep(bits=random_bits(n, rng), bases=random_bits(n, rng))


def choose_bases(n: int, rng: np.random.Generator) -> np.ndarray:
    """Bob's random measurement bases."""
    return as_bit_array(random_bits(n, rng), "bases")


# --- Qiskit circuits -------------------------------------------------------


def encode_qubit(qc: QuantumCircuit, bit: int, basis: int) -> None:
    """Alice prepares |0>, |1>, |+> or |->: X for bit 1, then H for the X basis."""
    if bit:
        qc.x(0)
    if basis == X_BASIS:
        qc.h(0)


def measure_qubit(qc: QuantumCircuit, basis: int, clbit) -> None:
    """Bob measures in Z, or rotates X to Z with H first."""
    if basis == X_BASIS:
        qc.h(0)
    qc.measure(0, clbit)


def photon_circuit(
    alice_bit: int,
    alice_basis: int,
    bob_basis: int,
    channel: Channel = Channel(),
    index: int = 0,
    plans: tuple | None = None,
) -> QuantumCircuit:
    """One photon's journey: Alice's preparation | channel | Bob's measurement.

    Bob's result is always classical bit 0 (register ``bob``). Effects such as
    Eve may add their own registers.
    """
    qc = QuantumCircuit(QuantumRegister(1, "q"), ClassicalRegister(1, BOB_REGISTER), name=f"photon_{index}")
    encode_qubit(qc, alice_bit, alice_basis)
    qc.barrier(label="send")
    if channel.effects:
        if plans is None:
            raise ValueError("plans are required when the channel has effects (use Channel.sample)")
        channel.append_to_circuit(qc, index, plans)
        qc.barrier(label="receive")
    measure_qubit(qc, bob_basis, qc.cregs[0][0])
    return qc


def _bob_bit(memory: str) -> int:
    # Aer prints clbits high-to-low with spaces between registers; clbit 0 is last.
    return int(memory.replace(" ", "")[-1])


@dataclass(frozen=True)
class QiskitSimulator:
    """Circuit-per-photon simulation on Aer (demonstrable, slower)."""

    name: str = "qiskit"

    def transmit_and_measure(
        self,
        alice: AlicePrep,
        bob_bases: np.ndarray,
        channel: Channel,
        plans: tuple,
        rng: np.random.Generator,
    ) -> BobMeasurement:
        n = len(alice)
        lost = channel.lost_mask(plans, n)
        sent = np.flatnonzero(~lost)
        bits = np.zeros(n, dtype=np.uint8)
        if sent.size:
            circuits = [
                photon_circuit(int(alice.bits[i]), int(alice.bases[i]), int(bob_bases[i]), channel, int(i), plans)
                for i in sent
            ]
            backend = AerSimulator(
                noise_model=channel.build_noise_model(),
                seed_simulator=int(rng.integers(0, _SEED_LIMIT)),
            )
            result = backend.run(circuits, shots=1, memory=True).result()
            bits[sent] = [_bob_bit(result.get_memory(k)[0]) for k in range(sent.size)]
        return BobMeasurement(bases=bob_bases, bits=bits, detected=~lost)


# --- NumPy fast mode -------------------------------------------------------


def measure_photons(photons: Photons, bob_bases: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Projective measurement of BB84 eigenstates in Bob's bases.

    Same basis: Bob reads the encoded value. Other basis: the two bases are
    mutually unbiased, so the outcome is uniformly random.
    """
    random_outcomes = random_bits(len(photons), rng)
    return np.where(photons.bases == bob_bases, photons.values, random_outcomes).astype(np.uint8)


@dataclass(frozen=True)
class NumpySimulator:
    """Array-based simulation of the same physics (fast, for large sweeps)."""

    name: str = "numpy"

    def transmit_and_measure(
        self,
        alice: AlicePrep,
        bob_bases: np.ndarray,
        channel: Channel,
        plans: tuple,
        rng: np.random.Generator,
    ) -> BobMeasurement:
        photons = channel.transmit_numpy(Photons.from_alice(alice), plans, rng)
        bits = channel.detect_numpy(measure_photons(photons, bob_bases, rng), rng)
        return BobMeasurement(bases=bob_bases, bits=bits, detected=~photons.lost)


SIMULATORS: dict[str, Simulator] = {"qiskit": QiskitSimulator(), "numpy": NumpySimulator()}


# --- Protocol run ----------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ProtocolResult:
    """Everything one BB84 run produced, up to the abort decision."""

    n: int
    mode: str
    seed: int
    alice: AlicePrep
    bob: BobMeasurement
    sifted: SiftResult
    qber: QberEstimate
    threshold: float
    aborted: bool
    plans: tuple

    @property
    def alice_key(self) -> Key:
        """Alice's sifted key with the QBER sample removed (input to error correction)."""
        return self.qber.alice_remaining

    @property
    def bob_key(self) -> Key:
        return self.qber.bob_remaining

    def summary(self) -> dict[str, float | int | bool | str]:
        """Flat numbers for tables and CSV rows."""
        return {
            "mode": self.mode,
            "seed": self.seed,
            "n": self.n,
            "detected": int(self.bob.detected.sum()),
            "sifted_length": len(self.sifted),
            "sample_size": self.qber.sample_size,
            "sample_errors": self.qber.errors,
            "qber_estimate": self.qber.qber,
            "qber_true": self.sifted.true_qber,
            "threshold": self.threshold,
            "aborted": self.aborted,
            "remaining_length": len(self.alice_key),
        }


PROTOCOL_STREAM, MEASUREMENT_STREAM, SAMPLING_STREAM, RECONCILIATION_STREAM = range(4)


def stream(seed: int, index: int) -> np.random.Generator:
    """Independent generator number ``index`` derived from the master ``seed``."""
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(index,)))


def split_streams(seed: int) -> tuple[np.random.Generator, np.random.Generator, np.random.Generator]:
    """Protocol, measurement and QBER-sampling generators for one master seed."""
    return stream(seed, PROTOCOL_STREAM), stream(seed, MEASUREMENT_STREAM), stream(seed, SAMPLING_STREAM)


def run_bb84(
    n: int,
    channel: Channel = Channel(),
    mode: Mode = "numpy",
    seed: int = 0,
    sample_fraction: float = DEFAULT_SAMPLE_FRACTION,
    threshold: float = DEFAULT_QBER_THRESHOLD,
) -> ProtocolResult:
    """Run BB84 steps 1-5: prepare, transmit, measure, sift, estimate QBER, decide.

    Aborts when the estimated QBER exceeds ``threshold``, or when the sifted
    key is too short to estimate it.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if mode not in SIMULATORS:
        raise ValueError(f"mode must be one of {sorted(SIMULATORS)}, got {mode!r}")
    if not 0.0 <= threshold <= 0.5:
        raise ValueError(f"threshold must be in [0, 0.5], got {threshold}")

    protocol_rng, measurement_rng, post_rng = split_streams(seed)
    alice = prepare_alice(n, protocol_rng)
    bob_bases = choose_bases(n, protocol_rng)
    plans = channel.sample(n, protocol_rng)

    bob = SIMULATORS[mode].transmit_and_measure(alice, bob_bases, channel, plans, measurement_rng)
    sifted = sift(alice, bob)
    estimate = estimate_qber(sifted.alice_key, sifted.bob_key, sample_fraction, post_rng)
    aborted = bool(np.isnan(estimate.qber) or estimate.qber > threshold)
    return ProtocolResult(
        n=n,
        mode=mode,
        seed=seed,
        alice=alice,
        bob=bob,
        sifted=sifted,
        qber=estimate,
        threshold=threshold,
        aborted=aborted,
        plans=plans,
    )
