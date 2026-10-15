import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from qkd.channel import Channel, ChannelEffect
from qkd.core import (
    NumpySimulator,
    QiskitSimulator,
    encode_qubit,
    photon_circuit,
    prepare_alice,
    run_bb84,
)
from qkd.key import X_BASIS, Z_BASIS, AlicePrep

SQRT_HALF = 1 / np.sqrt(2)


class XGateOnEveryPhoton(ChannelEffect):
    """Test double: a deterministic X (bit-flip) gate on every photon.

    X flips |0> <-> |1> but leaves |+> and |-> unchanged up to a global phase,
    so only Z-basis sifted bits become errors and the QBER is about 50%.
    """

    name = "x_gate"

    def transmit_numpy(self, photons, plan, rng):
        flipped = np.where(photons.bases == Z_BASIS, 1 - photons.values, photons.values)
        return photons.replace(values=flipped)

    def append_to_circuit(self, qc, index, plan):
        qc.x(0)


@pytest.mark.parametrize(
    ("bit", "basis", "amplitudes"),
    [
        (0, Z_BASIS, [1, 0]),
        (1, Z_BASIS, [0, 1]),
        (0, X_BASIS, [SQRT_HALF, SQRT_HALF]),
        (1, X_BASIS, [SQRT_HALF, -SQRT_HALF]),
    ],
)
def test_alice_encodes_the_four_bb84_states(bit, basis, amplitudes):
    qc = QuantumCircuit(1)
    encode_qubit(qc, bit, basis)
    assert Statevector(qc).equiv(Statevector(amplitudes))


def test_photon_circuit_measures_matching_basis_deterministically():
    for bit in (0, 1):
        for basis in (Z_BASIS, X_BASIS):
            alice = AlicePrep(bits=[bit] * 50, bases=[basis] * 50)
            bob = QiskitSimulator().transmit_and_measure(
                alice, alice.bases, Channel(), (), np.random.default_rng(1)
            )
            assert bob.bits.tolist() == [bit] * 50


def test_wrong_basis_measurement_is_random_in_both_modes():
    n = 2000
    alice = AlicePrep(bits=np.zeros(n, dtype=np.uint8), bases=np.zeros(n, dtype=np.uint8))
    bob_bases = np.ones(n, dtype=np.uint8)  # Bob always measures |0> in X
    for sim in (NumpySimulator(), QiskitSimulator()):
        bob = sim.transmit_and_measure(alice, bob_bases, Channel(), (), np.random.default_rng(2))
        assert bob.bits.mean() == pytest.approx(0.5, abs=5 * 0.5 / np.sqrt(n))


def test_photon_circuit_requires_plans_with_effects():
    with pytest.raises(ValueError):
        photon_circuit(0, Z_BASIS, Z_BASIS, Channel((XGateOnEveryPhoton(),)))


def test_prepare_alice_is_seeded():
    a = prepare_alice(100, np.random.default_rng(9))
    b = prepare_alice(100, np.random.default_rng(9))
    assert a.bits.tolist() == b.bits.tolist() and a.bases.tolist() == b.bases.tolist()


@pytest.mark.parametrize(("mode", "n"), [("numpy", 20_000), ("qiskit", 1_000)])
def test_no_eve_no_noise_gives_zero_qber_and_half_sifted(mode, n):
    result = run_bb84(n, mode=mode, seed=11)
    assert result.qber.qber == 0.0
    assert result.sifted.true_qber == 0.0
    assert len(result.sifted) == pytest.approx(n / 2, abs=5 * np.sqrt(n) / 2)
    assert not result.aborted
    assert result.alice_key == result.bob_key


def test_same_seed_reproduces_the_run():
    a = run_bb84(5000, channel=Channel((XGateOnEveryPhoton(),)), seed=3)
    b = run_bb84(5000, channel=Channel((XGateOnEveryPhoton(),)), seed=3)
    assert a.summary() == b.summary()
    assert a.bob.bits.tolist() == b.bob.bits.tolist()


def test_protocol_aborts_when_qber_exceeds_threshold():
    result = run_bb84(5000, channel=Channel((XGateOnEveryPhoton(),)), seed=4)
    assert result.qber.qber == pytest.approx(0.5, abs=0.06)
    assert result.aborted


def test_threshold_is_compared_against_the_estimate():
    result = run_bb84(5000, channel=Channel((XGateOnEveryPhoton(),)), seed=4, threshold=0.5)
    assert result.aborted == (result.qber.qber > 0.5)


@pytest.mark.parametrize("bad", [{"n": 0}, {"n": 10, "mode": "gpu"}, {"n": 10, "threshold": 0.7}])
def test_run_bb84_validates_arguments(bad):
    with pytest.raises(ValueError):
        run_bb84(**bad)


# --- Fast mode vs Qiskit mode --------------------------------------------


def test_modes_share_classical_choices_and_agree_without_noise():
    fast = run_bb84(600, mode="numpy", seed=21)
    circuit = run_bb84(600, mode="qiskit", seed=21)
    assert fast.alice.bits.tolist() == circuit.alice.bits.tolist()
    assert fast.bob.bases.tolist() == circuit.bob.bases.tolist()
    np.testing.assert_array_equal(fast.sifted.indices, circuit.sifted.indices)
    # Matching-basis outcomes are deterministic, so the sifted keys are identical.
    assert fast.sifted.bob_key == circuit.sifted.bob_key


def test_modes_agree_on_qber_with_a_channel_effect():
    channel = Channel((XGateOnEveryPhoton(),))
    fast = run_bb84(800, channel=channel, mode="numpy", seed=5)
    circuit = run_bb84(800, channel=channel, mode="qiskit", seed=5)
    # The X gate's effect is deterministic, so both modes give the same sifted keys.
    assert fast.sifted.bob_key == circuit.sifted.bob_key
    assert fast.sifted.true_qber == pytest.approx(circuit.sifted.true_qber)
