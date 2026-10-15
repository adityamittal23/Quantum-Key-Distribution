"""Experiment 2: channel noise.

Sweeps the depolarizing parameter lam from 0 to 30% (Qiskit's convention:
rho -> (1 - lam) rho + lam I/2, so the expected QBER is lam / 2) and runs the
full pipeline, with Cascade and privacy amplification. Measures:

* the QBER, against lam / 2 and the 11% threshold;
* the sifted key length, against n / 2;
* the secret key rate in final bits per photon sent, against the asymptotic
  1/2 (1 - s) r(lam / 2) with r = 1 - h(Q) - f h(Q).

The range goes up to 30% so the QBER passes the threshold (lam of about 22%);
see the phase-1 note in the README.

    python -m experiments.exp2_channel_noise [--quick] [--seed N]
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from experiments.common import (
    INK_MUTED,
    SERIES,
    analytic_trace,
    cli,
    mean_and_interval,
    qiskit_trace,
    run_seed,
    simulated_trace,
    style_figure,
)
from qkd.channel import Channel
from qkd.core import DEFAULT_QBER_THRESHOLD, DEFAULT_SAMPLE_FRACTION
from qkd.keyrate import DEFAULT_EC_EFFICIENCY, secret_fraction
from qkd.noise import Depolarizing
from qkd.pipeline import run_qkd

NAME = "exp2_channel_noise"


@dataclass(frozen=True)
class Config:
    n: int = 100_000
    lambdas: tuple[float, ...] = tuple(np.round(np.linspace(0, 0.30, 21), 4))
    trials: int = 10
    qiskit_n: int = 3_000
    qiskit_lambdas: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3)
    qiskit_trials: int = 3
    sample_fraction: float = DEFAULT_SAMPLE_FRACTION
    threshold: float = DEFAULT_QBER_THRESHOLD


FULL = Config()
QUICK = Config(n=4_000, lambdas=(0.0, 0.1, 0.3), trials=2, qiskit_n=400, qiskit_lambdas=(0.1,), qiskit_trials=1)


def analytic_key_rate(lam: float | np.ndarray, sample_fraction: float, f: float = DEFAULT_EC_EFFICIENCY):
    """Asymptotic secret bits per photon sent: 1/2 sifting x (1 - s) kept after sampling x r(Q)."""
    return 0.5 * (1 - sample_fraction) * secret_fraction(np.asarray(lam) / 2, f)


def _row(mode: str, n: int, lam: float, seed: int, config: Config) -> dict:
    result = run_qkd(n, Channel((Depolarizing(lam),)), mode, seed, config.sample_fraction, config.threshold)
    s = result.summary()
    return {
        "mode": mode,
        "n": n,
        "depolarizing": lam,
        "seed": seed,
        "status": s["status"],
        "qber_estimate": s["qber_estimate"],
        "qber_true": s["qber_true"],
        "sifted_length": s["sifted_length"],
        "ec_leaked_bits": s["ec_leaked_bits"],
        "ec_efficiency": s["ec_efficiency"],
        "final_key_length": s["final_key_length"],
        "keys_match": s["keys_match"],
        "final_bits_per_photon": s["final_bits_per_photon"],
        "qber_analytic": lam / 2,
        "key_rate_analytic": float(analytic_key_rate(lam, config.sample_fraction)),
    }


def run(config: Config, seed: int) -> pd.DataFrame:
    rows, index = [], 0
    for lam in config.lambdas:
        for _ in range(config.trials):
            rows.append(_row("numpy", config.n, float(lam), run_seed(seed, index), config))
            index += 1
    for lam in config.qiskit_lambdas:
        for _ in range(config.qiskit_trials):
            rows.append(_row("qiskit", config.qiskit_n, float(lam), run_seed(seed, index), config))
            index += 1
    return pd.DataFrame(rows)


def plot(table: pd.DataFrame) -> go.Figure:
    table = table.assign(sifted_fraction=table["sifted_length"] / table["n"])
    fast = table[table["mode"] == "numpy"]
    circuit = table[table["mode"] == "qiskit"]
    n = int(fast["n"].iloc[0])
    lam_line = np.linspace(0, fast["depolarizing"].max(), 121)
    fig = make_subplots(rows=1, cols=3, horizontal_spacing=0.07, subplot_titles=(
        "QBER", "Sifted fraction of photons", "Secret key rate"))

    def measured(column: str, panel: int, fmt: str) -> None:
        hover = "λ = %{x:.3f}<br>%{y:" + fmt + "}"
        stats = mean_and_interval(fast, ["depolarizing"], column)
        fig.add_trace(simulated_trace(stats, "depolarizing", f"Fast mode, n = {n:,}", SERIES[0], hover,
                                      showlegend=panel == 1, legendgroup="fast"), 1, panel)
        if not circuit.empty:
            cq = mean_and_interval(circuit, ["depolarizing"], column)
            fig.add_trace(qiskit_trace(cq, "depolarizing", f"Qiskit mode, n = {int(circuit['n'].iloc[0]):,}", hover,
                                       showlegend=panel == 1, legendgroup="qiskit"), 1, panel)

    fig.add_trace(analytic_trace(lam_line, lam_line / 2, "Analytic Q = λ/2"), 1, 1)
    measured("qber_true", 1, ".4f")
    fig.add_hline(y=DEFAULT_QBER_THRESHOLD, line={"color": INK_MUTED, "width": 1}, row=1, col=1,
                  annotation_text="11% abort threshold", annotation_position="top left")

    fig.add_trace(analytic_trace(lam_line, np.full_like(lam_line, 0.5), "Expected 1/2 (bases match)"), 1, 2)
    measured("sifted_fraction", 2, ".4f")

    fig.add_trace(analytic_trace(lam_line, analytic_key_rate(lam_line, DEFAULT_SAMPLE_FRACTION),
                                 f"Asymptotic ½ (1 − s) r(Q), f = {DEFAULT_EC_EFFICIENCY}"), 1, 3)
    measured("final_bits_per_photon", 3, ".4f")

    fig.update_xaxes(title_text="Depolarizing parameter λ", tickformat=".0%")
    fig.update_yaxes(title_text="QBER", tickformat=".0%", row=1, col=1)
    fig.update_yaxes(title_text="Sifted bits / photons sent", range=[0.4, 0.6], row=1, col=2)
    fig.update_yaxes(title_text="Secret bits per photon sent", rangemode="tozero", row=1, col=3)
    style_figure(fig, f"Experiment 2: depolarizing noise raises the QBER until no secret key is left (n = {n:,})")
    fig.update_layout(height=560)
    return fig


def main(argv: list[str] | None = None) -> None:
    cli(NAME, run, plot, FULL, QUICK, argv)


if __name__ == "__main__":
    main()
