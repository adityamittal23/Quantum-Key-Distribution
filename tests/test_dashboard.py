from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.dashboard_logic import (
    QISKIT_MAX_PHOTONS,
    DashboardParams,
    attack_figure,
    build_channel,
    circuit_text,
    key_rate_figure,
    photon_table,
    simulate,
    stage_lengths,
)
from qkd.attacks import InterceptResend
from qkd.noise import Depolarizing, PhotonLoss, ReadoutNoise

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


# --- logic ---------------------------------------------------------------


def test_build_channel_keeps_only_active_effects_in_physical_order():
    assert build_channel(DashboardParams()).effects == ()
    params = DashboardParams(eve_fraction=0.5, depolarizing=0.1, loss=0.3, readout=0.02)
    kinds = [type(e) for e in build_channel(params).effects]
    assert kinds == [InterceptResend, Depolarizing, PhotonLoss, ReadoutNoise]


def test_qiskit_mode_photon_limit():
    with pytest.raises(ValueError):
        DashboardParams(mode="qiskit", n=QISKIT_MAX_PHOTONS + 1)


def test_photon_table_shows_eve_and_sifting():
    params = DashboardParams(n=2000, eve_fraction=1.0, seed=3)
    result = simulate(params)
    table = photon_table(result, build_channel(params), 16)
    assert len(table) == 16
    assert table["Eve"].str.startswith("measures in").all()
    kept = table["kept after sifting"] == "yes"
    assert (table.loc[kept, "Alice basis"] == table.loc[kept, "Bob basis"]).all()
    assert set(table["state sent"]) <= {"|0>", "|1>", "|+>", "|->"}


def test_circuit_text_shows_eve_register_and_noise_gate():
    params = DashboardParams(n=500, eve_fraction=1.0, depolarizing=0.1, seed=1)
    result = simulate(params)
    drawing = circuit_text(result, build_channel(params), 0)
    assert "eve" in drawing and "bob" in drawing and "depolarizing" in drawing
    with pytest.raises(ValueError):
        circuit_text(result, build_channel(params), 500)


def test_stage_lengths_shrink_monotonically():
    result = simulate(DashboardParams(n=20_000, depolarizing=0.06, loss=0.3))
    bits = stage_lengths(result)["bits"].tolist()
    assert bits == sorted(bits, reverse=True)
    assert bits[0] == 20_000 and bits[-1] == len(result.final_alice_key) > 0


def test_stage_lengths_after_abort():
    result = simulate(DashboardParams(n=5_000, eve_fraction=1.0))
    stages = stage_lengths(result).set_index("stage")["bits"]
    assert stages["After error correction"] == 0 and stages["Final secret key"] == 0


def test_figures_handle_nan_qber():
    assert len(key_rate_figure(float("nan")).data) == 2  # no "this run" marker
    assert len(attack_figure(0.0, float("nan"), 0.11).data) == 1


# --- the app itself, rendered headless ----------------------------------


def _slider(at: AppTest, label: str):
    return next(s for s in at.slider if s.label == label)


def test_app_renders_clean_run():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("Secure key established" in s.value for s in at.success)
    assert [t.label for t in at.tabs] == ["Photons and circuits", "QBER and security", "Key pipeline", "Experiment results"]
    assert at.code and "bob" in at.code[0].value  # circuit drawing present


def test_app_aborts_under_full_attack():
    at = AppTest.from_file(APP, default_timeout=120).run()
    _slider(at, "Intercept fraction p").set_value(1.0).run()
    assert not at.exception
    assert any("Aborted" in e.value for e in at.error)


def test_app_qiskit_mode_with_noise_and_loss():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.radio[0].set_value("qiskit").run()
    _slider(at, "Depolarizing λ").set_value(0.08).run()
    _slider(at, "Loss probability").set_value(0.3).run()
    assert not at.exception
    assert "depolarizing" in at.code[0].value or "lost" in at.dataframe[0].value.to_string()


def test_app_loss_by_distance():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.toggle[0].set_value(True).run()
    _slider(at, "Distance (km)").set_value(50).run()
    assert not at.exception
    assert any("50 km of fibre loses 90.0%" in c.value for c in at.caption)
