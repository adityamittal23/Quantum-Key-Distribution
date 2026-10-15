"""Smoke tests: every experiment runs its QUICK config and writes a traceable CSV and a plot."""

import random

import pytest

from experiments import exp1_eavesdropping, exp2_channel_noise, exp3_photon_loss, exp4_classical_baseline
from experiments.common import execute
from experiments.rsa_baseline import (
    generate_keypair,
    gnfs_log2_operations,
    is_probable_prime,
    shor_logical_qubits,
)
from qkd.results_io import read_results_csv

EXPERIMENTS = [exp1_eavesdropping, exp2_channel_noise, exp3_photon_loss, exp4_classical_baseline]


@pytest.mark.parametrize("module", EXPERIMENTS, ids=lambda m: m.NAME)
def test_experiment_writes_csv_with_seed_params_and_plot(module, tmp_path):
    csv_path, html_path = execute(module.NAME, module.run, module.plot, module.QUICK, seed=5,
                                  results_dir=tmp_path, write_png=False)
    meta, table = read_results_csv(csv_path)
    assert meta["seed"] == 5 and meta["experiment"] == module.NAME
    assert meta["params"]  # the full config is recorded
    # Each run is individually traceable. Experiment 4 reruns one seed in both simulator modes.
    keys = ["seed", "method"] if "method" in table.columns else ["seed"]
    assert not table.duplicated(keys).any()
    assert html_path.stat().st_size > 1000


@pytest.mark.parametrize("module", EXPERIMENTS[:3], ids=lambda m: m.NAME)
def test_quantum_experiments_are_reproducible(module):
    a = module.run(module.QUICK, seed=9)
    b = module.run(module.QUICK, seed=9)
    assert a.equals(b)


def test_exp1_rows_follow_the_analytic_trend():
    table = exp1_eavesdropping.run(exp1_eavesdropping.QUICK, seed=3)
    full = table[(table["mode"] == "numpy") & (table["intercept_fraction"] == 1.0)]
    assert full["qber_true"].between(0.18, 0.32).all()
    assert table.loc[table["intercept_fraction"] == 0.0, "qber_true"].eq(0).all()


def test_exp2_aborts_at_high_noise():
    table = exp2_channel_noise.run(exp2_channel_noise.QUICK, seed=3)
    assert (table.loc[table["depolarizing"] == 0.3, "status"] == "aborted_qber").all()
    assert (table.loc[table["depolarizing"] == 0.0, "keys_match"]).all()


# --- RSA baseline --------------------------------------------------------


def test_miller_rabin_on_known_numbers():
    rng = random.Random(0)
    assert all(is_probable_prime(p, rng) for p in [2, 3, 97, 7919, 2**61 - 1])
    assert not any(is_probable_prime(c, rng) for c in [1, 91, 561, 2**61 + 1])  # 561 is a Carmichael number


@pytest.mark.parametrize("bits", [128, 256, 512])
def test_rsa_round_trip_and_modulus_size(bits):
    keys = generate_keypair(bits, random.Random(bits))
    assert keys.bits == bits
    message = random.Random(1).randrange(keys.n)
    assert keys.decrypt(keys.encrypt(message)) == message


def test_rsa_cost_models():
    assert shor_logical_qubits(2048) == 4099
    assert gnfs_log2_operations(2048) > gnfs_log2_operations(1024) > 80
    assert gnfs_log2_operations(2048) == pytest.approx(116.9, abs=0.5)  # about 2^117 (o(1) dropped)
