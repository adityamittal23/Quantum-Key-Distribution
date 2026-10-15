import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit_aer.noise import ReadoutError, pauli_error

from qkd.channel import Channel, ChannelEffect, NoiseTerm
from qkd.key import AlicePrep, Photons


class FlipAll(ChannelEffect):
    """Test double: flips every photon value and drops photons marked in its plan."""

    name = "flip_all"

    def sample(self, n, rng):
        return rng.random(n) < 0.5

    def transmit_numpy(self, photons, plan, rng):
        return photons.replace(values=1 - photons.values, lost=photons.lost | plan)

    def append_to_circuit(self, qc, index, plan):
        qc.x(0)

    def lost_mask(self, plan, n):
        return plan


class FiberNoise(ChannelEffect):
    name = "fiber_noise"

    def __init__(self, p):
        self.p = p

    def transmit_numpy(self, photons, plan, rng):
        return photons

    def noise_terms(self):
        return (NoiseTerm(pauli_error([("X", self.p), ("I", 1 - self.p)]), ("id",)),)


def _photons(n=8):
    return Photons.from_alice(AlicePrep(bits=np.zeros(n, dtype=np.uint8), bases=np.zeros(n, dtype=np.uint8)))


def test_empty_channel_is_identity_and_noiseless():
    channel = Channel()
    rng = np.random.default_rng(0)
    photons = _photons()
    plans = channel.sample(len(photons), rng)
    assert channel.transmit_numpy(photons, plans, rng) is photons
    assert channel.build_noise_model() is None
    assert not channel.lost_mask(plans, len(photons)).any()


def test_effects_apply_in_order_and_plans_are_reproducible():
    channel = Channel().then(FlipAll()).then(FlipAll())
    photons = _photons()
    plans_a = channel.sample(len(photons), np.random.default_rng(3))
    plans_b = channel.sample(len(photons), np.random.default_rng(3))
    for a, b in zip(plans_a, plans_b):
        np.testing.assert_array_equal(a, b)
    out = channel.transmit_numpy(photons, plans_a, np.random.default_rng(0))
    assert out.values.tolist() == photons.values.tolist()  # two flips cancel
    np.testing.assert_array_equal(out.lost, plans_a[0] | plans_a[1])
    np.testing.assert_array_equal(channel.lost_mask(plans_a, len(photons)), out.lost)


def test_append_to_circuit_adds_each_effect():
    channel = Channel((FlipAll(), FlipAll()))
    qc = QuantumCircuit(1)
    channel.append_to_circuit(qc, 0, channel.sample(1, np.random.default_rng(0)))
    assert [inst.operation.name for inst in qc.data] == ["x", "x"]


def test_noise_term_is_attached_to_its_instruction():
    model = Channel((FiberNoise(0.1),)).build_noise_model()
    assert model is not None
    assert "id" in model.noise_instructions


def test_two_effects_on_the_same_instruction_are_rejected():
    with pytest.raises(ValueError, match="same|instruction"):
        Channel((FiberNoise(0.1), FiberNoise(0.2))).build_noise_model()


def test_readout_errors_are_combined():
    class Readout(FiberNoise):
        def noise_terms(self):
            return (NoiseTerm(ReadoutError([[1 - self.p, self.p], [self.p, 1 - self.p]])),)

    model = Channel((Readout(0.1), Readout(0.1))).build_noise_model()
    assert "measure" in model.noise_instructions


def test_channel_rejects_non_effects():
    with pytest.raises(TypeError):
        Channel(("not an effect",))
