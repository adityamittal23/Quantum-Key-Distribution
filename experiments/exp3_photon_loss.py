"""Experiment 3: photon loss and distance.

Sweeps the photon-loss probability from 0 to 90% and runs the full pipeline,
on a noiseless channel and on a channel with a small background noise
(depolarizing 4%, QBER of about 2%). Loss is converted to fibre distance at
0.2 dB/km for the hover and the CSV. Measures:

* the raw key rate, detections per photon sent, against the ideal lossless
  channel scaled by (1 - loss);
* the final secret key rate, against the lossless rate x (1 - loss), which
  is what loss alone would predict.

At high loss the final rate falls faster than (1 - loss), because the
fixed-size QBER sample, the Cascade overhead and the privacy-amplification
margin take a larger share of a smaller key.

    python -m experiments.exp3_photon_loss [--quick] [--seed N]
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from experiments.common import (
    SERIES,
    analytic_trace,
    cli,
    mean_and_interval,
    run_seed,
    simulated_trace,
    style_figure,
)
from qkd.channel import Channel
from qkd.core import DEFAULT_QBER_THRESHOLD, DEFAULT_SAMPLE_FRACTION
from qkd.noise import FIBRE_LOSS_DB_PER_KM, Depolarizing, PhotonLoss
from qkd.pipeline import run_qkd

NAME = "exp3_photon_loss"


@dataclass(frozen=True)
class Config:
    n: int = 100_000
    losses: tuple[float, ...] = tuple(np.round(np.linspace(0, 0.9, 19), 3))
    background_noise: tuple[float, ...] = (0.0, 0.04)  # depolarizing parameter
    trials: int = 10
    sample_fraction: float = DEFAULT_SAMPLE_FRACTION
    threshold: float = DEFAULT_QBER_THRESHOLD


FULL = Config()
QUICK = Config(n=4_000, losses=(0.0, 0.5, 0.9), background_noise=(0.0, 0.04), trials=2)


def distance_km(loss: float | np.ndarray, db_per_km: float = FIBRE_LOSS_DB_PER_KM):
    """Fibre length with the given loss probability: L = -10 log10(1 - loss) / alpha."""
    return -10 * np.log10(1 - np.asarray(loss, dtype=float)) / db_per_km + 0.0  # + 0.0 turns -0.0 into 0.0


def run(config: Config, seed: int) -> pd.DataFrame:
    rows, index = [], 0
    for lam in config.background_noise:
        for loss in config.losses:
            channel = Channel((PhotonLoss(float(loss)), Depolarizing(float(lam))))
            for _ in range(config.trials):
                row_seed = run_seed(seed, index)
                index += 1
                s = run_qkd(config.n, channel, "numpy", row_seed, config.sample_fraction, config.threshold).summary()
                rows.append({
                    "n": config.n,
                    "loss": float(loss),
                    "distance_km": float(distance_km(loss)),
                    "depolarizing": float(lam),
                    "seed": row_seed,
                    "status": s["status"],
                    "detected": s["detected"],
                    "raw_bits_per_photon": s["detected"] / config.n,
                    "sifted_length": s["sifted_length"],
                    "qber_estimate": s["qber_estimate"],
                    "final_key_length": s["final_key_length"],
                    "final_bits_per_photon": s["final_bits_per_photon"],
                    "keys_match": s["keys_match"],
                })
    return pd.DataFrame(rows)


def plot(table: pd.DataFrame) -> go.Figure:
    n = int(table["n"].iloc[0])
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.1, subplot_titles=(
        "Raw key rate (detections)", "Final secret key rate"))
    loss_line = np.linspace(0, table["loss"].max(), 91)
    hover = "loss = %{x:.0%} (%{customdata:.0f} km of fibre)<br>%{y:.4f} bits/photon"

    noiseless = table[table["depolarizing"] == table["depolarizing"].min()]
    raw = mean_and_interval(noiseless, ["loss"], "raw_bits_per_photon")
    fig.add_trace(analytic_trace(loss_line, 1 - loss_line, "Ideal lossless channel x (1 − loss)"), 1, 1)
    fig.add_trace(simulated_trace(raw, "loss", "Simulated detections", SERIES[0], hover,
                                  customdata=distance_km(raw["loss"]), showlegend=False), 1, 1)

    for slot, lam in enumerate(sorted(table["depolarizing"].unique())):
        stats = mean_and_interval(table[table["depolarizing"] == lam], ["loss"], "final_bits_per_photon")
        lossless = float(stats.loc[stats["loss"] == stats["loss"].min(), "mean"].iloc[0])
        color = SERIES[slot % len(SERIES)]
        label = "noiseless channel" if lam == 0 else f"depolarizing {lam:.0%} (QBER about {lam / 2:.0%})"
        fig.add_trace(analytic_trace(loss_line, lossless * (1 - loss_line), f"Lossless rate x (1 − loss), {label}",
                                     color=color, legendgroup=label), 1, 2)
        fig.add_trace(simulated_trace(stats, "loss", f"Simulated, {label}", color, hover,
                                      customdata=distance_km(stats["loss"]), legendgroup=label), 1, 2)

    fig.update_xaxes(title_text="Photon loss probability (0.2 dB/km fibre: 90% = 50 km)", tickformat=".0%")
    fig.update_yaxes(title_text="Detections per photon sent", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Secret bits per photon sent", rangemode="tozero", row=1, col=2)
    style_figure(fig, f"Experiment 3: loss scales the key rate down, noise lowers it further (n = {n:,})")
    fig.update_layout(height=580)
    return fig


def main(argv: list[str] | None = None) -> None:
    cli(NAME, run, plot, FULL, QUICK, argv)


if __name__ == "__main__":
    main()
