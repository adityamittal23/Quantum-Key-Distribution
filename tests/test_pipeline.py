import pytest

from qkd.attacks import InterceptResend
from qkd.channel import Channel
from qkd.core import run_bb84
from qkd.keyrate import binary_entropy
from qkd.noise import Depolarizing, PhotonLoss
from qkd.pipeline import run_qkd


def test_clean_channel_gives_identical_secret_keys():
    result = run_qkd(20_000, seed=1)
    assert result.status == "ok" and result.keys_match
    # Q = 0: only the Cascade parities and the PA margin are removed.
    assert len(result.final_alice_key) > 0.9 * len(result.protocol.alice_key)


@pytest.mark.parametrize(
    "channel",
    [
        Channel((Depolarizing(0.10),)),  # Q of about 5%
        Channel((InterceptResend(0.3),)),  # Q of about 7.5%
        Channel((PhotonLoss(0.5), Depolarizing(0.06))),
    ],
    ids=["depolarizing", "partial_eve", "loss_and_noise"],
)
def test_error_correction_succeeds_below_threshold(channel):
    result = run_qkd(40_000, channel=channel, seed=2)
    summary = result.summary()
    assert summary["qber_estimate"] < 0.11
    assert result.status == "ok"
    assert summary["ec_residual_errors"] == 0
    assert result.keys_match and summary["final_key_length"] > 0


def test_final_key_length_follows_the_secret_fraction():
    result = run_qkd(100_000, channel=Channel((Depolarizing(0.10),)), seed=3)
    n_ec = len(result.protocol.alice_key)
    q = result.protocol.qber.qber
    f = result.cascade.efficiency(q)
    # m is about n (1 - h(Q) - f h(Q)), up to the PA margin.
    predicted = n_ec * (1 - (1 + f) * binary_entropy(q))
    assert len(result.final_alice_key) == pytest.approx(predicted, abs=100)


def test_protocol_aborts_above_threshold_without_post_processing():
    result = run_qkd(20_000, channel=Channel((InterceptResend(1.0),)), seed=4)
    assert result.status == "aborted_qber"
    assert result.cascade is None and len(result.final_alice_key) == 0
    assert not result.keys_match


def test_failed_verification_aborts():
    result = run_qkd(20_000, channel=Channel((Depolarizing(0.15),)), seed=5, ec_passes=1)
    assert result.status == "aborted_verification"
    assert len(result.final_alice_key) == 0


def test_high_qber_that_passes_a_loose_threshold_leaves_no_secret_key():
    # Q of about 10.5% passes a 12% check, but with real Cascade leakage (f of about 1.2)
    # 1 - h(Q) - f h(Q) < 0, so privacy amplification leaves nothing.
    result = run_qkd(40_000, channel=Channel((Depolarizing(0.21),)), seed=6, threshold=0.12)
    assert result.status == "ok"
    assert result.cascade.alice_key == result.cascade.bob_key
    assert len(result.final_alice_key) == 0


def test_short_runs_rarely_fail_verification():
    # Found in phase 5: with n of about 1300 and Cascade blocks sized from the point
    # estimate, 59 of 300 runs failed verification. Sizing from the upper bound fixes that.
    channel = Channel((Depolarizing(0.04),))
    statuses = [run_qkd(1300, channel=channel, seed=s).status for s in range(100)]
    assert statuses.count("aborted_verification") <= 2
    assert statuses.count("ok") >= 95


def test_qiskit_mode_end_to_end():
    result = run_qkd(4000, channel=Channel((Depolarizing(0.08),)), mode="qiskit", seed=7)
    assert result.status == "ok" and result.keys_match


def test_pipeline_matches_run_bb84_and_is_reproducible():
    a = run_qkd(10_000, channel=Channel((InterceptResend(0.2),)), seed=8)
    b = run_qkd(10_000, channel=Channel((InterceptResend(0.2),)), seed=8)
    assert a.summary() == b.summary()
    assert a.final_alice_key == b.final_alice_key
    bb84 = run_bb84(10_000, channel=Channel((InterceptResend(0.2),)), seed=8)
    assert a.protocol.summary() == bb84.summary()
