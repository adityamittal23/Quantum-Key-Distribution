from math import comb

import numpy as np
import pytest

from qkd.attacks import (
    EVE_REGISTER,
    EvePlan,
    InterceptResend,
    detection_probability,
    expected_qber_intercept_resend,
)
from qkd.channel import Channel
from qkd.core import QiskitSimulator, photon_circuit, run_bb84
from qkd.key import X_BASIS, Z_BASIS, AlicePrep
from tests.stats import binomial_tolerance

N_FAST = 100_000


def test_full_intercept_resend_gives_25_percent_qber():
    result = run_bb84(N_FAST, channel=Channel((InterceptResend(1.0),)), seed=101)
    sifted = len(result.sifted)
    assert result.sifted.true_qber == pytest.approx(0.25, abs=binomial_tolerance(0.25, sifted))
    assert result.qber.qber == pytest.approx(0.25, abs=binomial_tolerance(0.25, result.qber.sample_size))
    assert result.aborted


@pytest.mark.parametrize("p", [0.0, 0.1, 0.3, 0.5, 0.8, 1.0])
def test_partial_intercept_gives_quarter_p_qber(p):
    result = run_bb84(N_FAST, channel=Channel((InterceptResend(p),)), seed=200 + int(p * 10))
    expected = expected_qber_intercept_resend(p)
    tolerance = binomial_tolerance(expected, len(result.sifted))
    assert result.sifted.true_qber == pytest.approx(expected, abs=tolerance)


def test_eve_does_not_change_sifted_length():
    result = run_bb84(N_FAST, channel=Channel((InterceptResend(1.0),)), seed=7)
    assert len(result.sifted) == pytest.approx(N_FAST / 2, abs=5 * np.sqrt(N_FAST) / 2)


def test_protocol_aborts_under_full_attack_and_passes_without_eve():
    attacked = run_bb84(20_000, channel=Channel((InterceptResend(1.0),)), seed=8)
    clean = run_bb84(20_000, seed=8)
    assert attacked.aborted and not clean.aborted


def test_eve_measures_mid_circuit_in_her_basis():
    eve = InterceptResend(1.0)
    plans = (EvePlan(intercepted=[True], bases=[X_BASIS]),)
    qc = photon_circuit(0, Z_BASIS, Z_BASIS, Channel((eve,)), 0, plans)
    ops = [inst.operation.name for inst in qc.data]
    assert [reg.name for reg in qc.cregs] == ["bob", EVE_REGISTER]
    assert ops.count("measure") == 2
    eve_measure = ops.index("measure")
    assert ops[eve_measure - 1] == "h" and ops[eve_measure + 1] == "h"


def test_photon_eve_skips_has_no_eve_register():
    plans = (EvePlan(intercepted=[False], bases=[X_BASIS]),)
    qc = photon_circuit(0, Z_BASIS, Z_BASIS, Channel((InterceptResend(1.0),)), 0, plans)
    assert [reg.name for reg in qc.cregs] == ["bob"]


def test_eve_in_matching_basis_introduces_no_error_in_qiskit():
    n = 200
    plans = (EvePlan(intercepted=[True] * n, bases=[X_BASIS] * n),)
    alice = AlicePrep(bits=[1] * n, bases=[X_BASIS] * n)
    bob = QiskitSimulator().transmit_and_measure(
        alice, alice.bases, Channel((InterceptResend(1.0),)), plans, np.random.default_rng(3)
    )
    assert bob.bits.tolist() == [1] * n


def test_intercept_fraction_is_validated():
    with pytest.raises(ValueError):
        InterceptResend(1.5)


# --- detection probability ---------------------------------------------


def _brute_force_detection(q, m, threshold):
    return sum(comb(m, k) * q**k * (1 - q) ** (m - k) for k in range(m + 1) if k / m > threshold)


@pytest.mark.parametrize(("q", "m"), [(0.05, 20), (0.11, 50), (0.25, 40), (0.2, 7)])
def test_detection_probability_matches_brute_force(q, m):
    expected = _brute_force_detection(q, m, 0.11)
    assert detection_probability(q, m, 0.11) == pytest.approx(expected, rel=1e-9)


def test_detection_probability_edges_and_monotonicity():
    assert detection_probability(0.0, 100, 0.11) == 0.0
    assert detection_probability(1.0, 100, 0.11) == 1.0
    assert detection_probability(0.25, 5000, 0.11) == pytest.approx(1.0)
    values = [detection_probability(0.25 * p, 200, 0.11) for p in np.linspace(0, 1, 11)]
    assert values == sorted(values)


def test_detection_probability_validates_input():
    with pytest.raises(ValueError):
        detection_probability(0.1, 0, 0.11)
