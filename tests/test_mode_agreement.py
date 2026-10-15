"""Validation of the NumPy fast mode against the Qiskit circuit mode.

For each channel both modes run the same seed, so they share every classical
choice: bits, bases, Eve's choices and lost photons. Measurement and noise
outcomes are independent quantum randomness, so the QBERs are compared
statistically, with each other and with the analytic value.
"""

import pytest

from qkd.attacks import InterceptResend
from qkd.channel import Channel
from qkd.core import run_bb84
from qkd.noise import BitFlip, Depolarizing, PhotonLoss, ReadoutNoise
from tests.stats import agree, binomial_tolerance

N_QISKIT = 3000

CHANNELS = {
    "eve_full": (Channel((InterceptResend(1.0),)), 0.25),
    "eve_half": (Channel((InterceptResend(0.5),)), 0.125),
    "depolarizing": (Channel((Depolarizing(0.2),)), 0.10),
    "bit_flip": (Channel((BitFlip(0.3),)), 0.15),
    "readout": (Channel((ReadoutNoise(0.1),)), 0.10),
    "loss": (Channel((PhotonLoss(0.6),)), 0.0),
    # Eve, then depolarizing: P(error) = 0.25 (1 - lam) + lam / 2.
    "eve_then_depolarizing": (Channel((InterceptResend(1.0), Depolarizing(0.2))), 0.25 * 0.8 + 0.1),
    # Bob's readout error on top of Eve: P(error) = 0.25 (1 - p) + 0.75 p.
    "eve_with_readout": (Channel((InterceptResend(1.0), ReadoutNoise(0.1))), 0.25 * 0.9 + 0.75 * 0.1),
}


@pytest.mark.parametrize("name", CHANNELS)
def test_fast_and_qiskit_modes_agree(name):
    channel, expected = CHANNELS[name]
    fast = run_bb84(N_QISKIT, channel=channel, mode="numpy", seed=77)
    circuit = run_bb84(N_QISKIT, channel=channel, mode="qiskit", seed=77)

    # Shared classical choices give identical sifted positions in both modes.
    assert fast.sifted.indices.tolist() == circuit.sifted.indices.tolist()

    m = len(fast.sifted)
    q_fast, q_circuit = fast.sifted.true_qber, circuit.sifted.true_qber
    assert agree(q_fast, m, q_circuit, m), f"fast {q_fast:.4f} vs qiskit {q_circuit:.4f}"
    assert q_circuit == pytest.approx(expected, abs=binomial_tolerance(expected, m))
    assert q_fast == pytest.approx(expected, abs=binomial_tolerance(expected, m))
