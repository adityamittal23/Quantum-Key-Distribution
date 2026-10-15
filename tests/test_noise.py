import numpy as np
import pytest

from qkd.channel import Channel
from qkd.core import run_bb84
from qkd.noise import BitFlip, Depolarizing, PhotonLoss, ReadoutNoise, loss_from_distance
from tests.stats import binomial_tolerance

N_FAST = 100_000


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        (Depolarizing(0.3), 0.15),
        (Depolarizing(0.1), 0.05),
        (BitFlip(0.2), 0.10),
        (ReadoutNoise(0.08), 0.08),
        (PhotonLoss(0.5), 0.0),
    ],
    ids=["depolarizing_0.3", "depolarizing_0.1", "bit_flip_0.2", "readout_0.08", "loss_0.5"],
)
def test_fast_mode_noise_qber_matches_analytic(effect, expected):
    result = run_bb84(N_FAST, channel=Channel((effect,)), seed=31)
    tolerance = binomial_tolerance(expected, len(result.sifted))
    assert result.sifted.true_qber == pytest.approx(expected, abs=tolerance)


def test_photon_loss_shrinks_the_sifted_key():
    p = 0.7
    result = run_bb84(N_FAST, channel=Channel((PhotonLoss(p),)), seed=32)
    expected = N_FAST * (1 - p) / 2
    assert len(result.sifted) == pytest.approx(expected, abs=5 * np.sqrt(expected))
    assert result.bob.detected.mean() == pytest.approx(1 - p, abs=0.01)


def test_loss_from_distance():
    assert loss_from_distance(0) == 0.0
    assert loss_from_distance(50) == pytest.approx(0.9)  # 10 dB
    assert PhotonLoss.from_distance(100).p == pytest.approx(0.99)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
@pytest.mark.parametrize("cls", [Depolarizing, BitFlip, ReadoutNoise, PhotonLoss])
def test_noise_probabilities_are_validated(cls, bad):
    with pytest.raises(ValueError):
        cls(bad)


def test_noise_model_uses_labelled_fibre_gates():
    model = Channel((Depolarizing(0.1), BitFlip(0.1), ReadoutNoise(0.05))).build_noise_model()
    assert {"depolarizing", "bit_flip", "measure"} <= set(model.noise_instructions)


def test_duplicate_noise_effects_are_rejected():
    with pytest.raises(ValueError):
        Channel((Depolarizing(0.1), Depolarizing(0.2))).build_noise_model()
