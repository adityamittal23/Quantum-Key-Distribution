"""Experiment 1: eavesdropping detection.

Sweeps Eve's intercept fraction p from 0 to 1 and measures:

* the sifted-key QBER, against the analytic Q = 0.25 p;
* the detection probability, the fraction of runs the protocol aborts,
  against the exact binomial prediction for the sample size used.

Three photon counts show how a larger QBER sample detects smaller attacks.
Qiskit-mode runs at a few values of p check the fast mode.

    python -m experiments.exp1_eavesdropping [--quick] [--seed N]
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
from qkd.attacks import InterceptResend, detection_probability, expected_qber_intercept_resend
from qkd.channel import Channel
from qkd.core import DEFAULT_QBER_THRESHOLD, DEFAULT_SAMPLE_FRACTION, run_bb84

NAME = "exp1_eavesdropping"


@dataclass(frozen=True)
class Config:
    photon_counts: tuple[int, ...] = (1_000, 5_000, 20_000)
    fractions: tuple[float, ...] = tuple(np.round(np.linspace(0, 1, 21), 3))
    trials: int = 40
    qiskit_n: int = 2_000
    qiskit_fractions: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    qiskit_trials: int = 3
    sample_fraction: float = DEFAULT_SAMPLE_FRACTION
    threshold: float = DEFAULT_QBER_THRESHOLD


FULL = Config()
QUICK = Config(photon_counts=(1_000,), fractions=(0.0, 0.5, 1.0), trials=3, qiskit_n=300,
               qiskit_fractions=(1.0,), qiskit_trials=1)


def _row(mode: str, n: int, p: float, seed: int, config: Config) -> dict:
    result = run_bb84(n, Channel((InterceptResend(p),)), mode, seed, config.sample_fraction, config.threshold)
    summary = result.summary()
    return {
        "mode": mode,
        "n": n,
        "intercept_fraction": p,
        "seed": seed,
        "sifted_length": summary["sifted_length"],
        "sample_size": summary["sample_size"],
        "qber_estimate": summary["qber_estimate"],
        "qber_true": summary["qber_true"],
        "aborted": summary["aborted"],
        "qber_analytic": expected_qber_intercept_resend(p),
        "detection_analytic": detection_probability(
            expected_qber_intercept_resend(p), max(summary["sample_size"], 1), config.threshold
        ),
    }


def run(config: Config, seed: int) -> pd.DataFrame:
    rows, index = [], 0
    for n in config.photon_counts:
        for p in config.fractions:
            for _ in range(config.trials):
                rows.append(_row("numpy", n, float(p), run_seed(seed, index), config))
                index += 1
    for p in config.qiskit_fractions:
        for _ in range(config.qiskit_trials):
            rows.append(_row("qiskit", config.qiskit_n, float(p), run_seed(seed, index), config))
            index += 1
    return pd.DataFrame(rows)


def plot(table: pd.DataFrame) -> go.Figure:
    fast = table[table["mode"] == "numpy"]
    circuit = table[table["mode"] == "qiskit"]
    photon_counts = sorted((int(n) for n in fast["n"].unique()), reverse=True)  # largest n: slot 1 in both panels
    largest = photon_counts[0]

    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.1, subplot_titles=(
        f"Sifted-key QBER (n = {largest:,} photons)", "Detection probability (protocol aborts)"))

    p_line = np.linspace(0, 1, 101)
    fig.add_trace(analytic_trace(p_line, 0.25 * p_line, "Analytic Q = 0.25 p"), 1, 1)
    qber = mean_and_interval(fast[fast["n"] == largest], ["intercept_fraction"], "qber_true")
    largest_sample = int(round(fast.loc[fast["n"] == largest, "sample_size"].mean()))
    fig.add_trace(simulated_trace(qber, "intercept_fraction",
                                  f"Fast mode, n = {largest:,} (QBER sample of about {largest_sample:,} bits)", SERIES[0],
                                  "p = %{x:.2f}<br>QBER = %{y:.4f}", legendgroup=str(largest)), 1, 1)
    if not circuit.empty:
        cq = mean_and_interval(circuit, ["intercept_fraction"], "qber_true")
        fig.add_trace(qiskit_trace(cq, "intercept_fraction", f"Qiskit mode, n = {int(circuit['n'].iloc[0]):,}",
                                   "p = %{x:.2f}<br>QBER = %{y:.4f}"), 1, 1)
    fig.add_hline(y=DEFAULT_QBER_THRESHOLD, line={"color": INK_MUTED, "width": 1}, row=1, col=1,
                  annotation_text="11% abort threshold", annotation_position="top left")

    for slot, n in enumerate(photon_counts):
        group = fast[fast["n"] == n]
        color = SERIES[slot % len(SERIES)]
        analytic = group.groupby("intercept_fraction")["detection_analytic"].mean()
        fig.add_trace(analytic_trace(analytic.index, analytic.values, "Binomial prediction (dashed, colour matches n)",
                                     color=color, showlegend=slot == 0, legendgroup="prediction"), 1, 2)
        detected = mean_and_interval(group, ["intercept_fraction"], "aborted")
        sample = int(round(group["sample_size"].mean()))
        fig.add_trace(simulated_trace(detected, "intercept_fraction", f"Fast mode, n = {n:,} (QBER sample of about {sample:,} bits)",
                                      color, "p = %{x:.2f}<br>P(abort) = %{y:.3f}",
                                      showlegend=bool(n != largest), legendgroup=str(n)), 1, 2)

    fig.update_xaxes(title_text="Eve's intercept fraction p", range=[-0.02, 1.02])
    fig.update_yaxes(title_text="QBER", tickformat=".0%", row=1, col=1)
    fig.update_yaxes(title_text="Fraction of runs aborted", tickformat=".0%", range=[-0.03, 1.03], row=1, col=2)
    style_figure(fig, "Experiment 1: intercept-resend raises the QBER by 25% x p and is detected")
    fig.update_layout(height=560)
    return fig


def main(argv: list[str] | None = None) -> None:
    cli(NAME, run, plot, FULL, QUICK, argv)


if __name__ == "__main__":
    main()
