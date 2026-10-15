"""Testable logic behind the Streamlit dashboard (Member C).

The UI in ``streamlit_app.py`` only lays out widgets. Everything that turns
slider values into a simulation, a table or a figure lives here, so pytest
can check it without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from qkd.attacks import EvePlan, InterceptResend, expected_qber_intercept_resend
from qkd.channel import Channel, ChannelEffect
from qkd.core import photon_circuit
from qkd.key import BASIS_NAMES, STATE_LABELS
from qkd.keyrate import DEFAULT_EC_EFFICIENCY, qber_threshold, secret_fraction
from qkd.noise import BitFlip, Depolarizing, PhotonLoss, ReadoutNoise
from qkd.pipeline import QKDResult, run_qkd

QISKIT_MAX_PHOTONS = 5_000  # keeps a Qiskit-mode run to a couple of seconds
PHOTON_COUNTS = (500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000)

# Reference palette, by role (dataviz skill). Backgrounds come from the Streamlit theme.
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
MUTED = "#898781"


@dataclass(frozen=True)
class DashboardParams:
    mode: str = "numpy"
    n: int = 5_000
    seed: int = 2026
    eve_fraction: float = 0.0
    depolarizing: float = 0.0
    bit_flip: float = 0.0
    readout: float = 0.0
    loss: float = 0.0
    threshold: float = 0.11
    sample_fraction: float = 0.2

    def __post_init__(self) -> None:
        if self.mode not in ("numpy", "qiskit"):
            raise ValueError(f"unknown mode {self.mode!r}")
        if self.mode == "qiskit" and self.n > QISKIT_MAX_PHOTONS:
            raise ValueError(f"Qiskit mode is limited to {QISKIT_MAX_PHOTONS:,} photons")


def build_channel(params: DashboardParams) -> Channel:
    """Effects in physical order: Eve taps the fibre, then fibre noise, loss, then Bob's detector.

    Effects with a zero setting are left out, so the circuits show only what acts.
    """
    effects: list[ChannelEffect] = []
    if params.eve_fraction > 0:
        effects.append(InterceptResend(params.eve_fraction))
    if params.depolarizing > 0:
        effects.append(Depolarizing(params.depolarizing))
    if params.bit_flip > 0:
        effects.append(BitFlip(params.bit_flip))
    if params.loss > 0:
        effects.append(PhotonLoss(params.loss))
    if params.readout > 0:
        effects.append(ReadoutNoise(params.readout))
    return Channel(tuple(effects))


def simulate(params: DashboardParams) -> QKDResult:
    return run_qkd(params.n, build_channel(params), params.mode, params.seed,
                   params.sample_fraction, params.threshold)


def eve_plan(result: QKDResult, channel: Channel) -> EvePlan | None:
    for effect, plan in zip(channel.effects, result.protocol.plans):
        if isinstance(effect, InterceptResend):
            return plan
    return None


def photon_table(result: QKDResult, channel: Channel, count: int = 16) -> pd.DataFrame:
    """The first ``count`` photons, step by step, as the protocol sees them."""
    protocol = result.protocol
    alice, bob = protocol.alice, protocol.bob
    plan = eve_plan(result, channel)
    rows = []
    for i in range(min(count, protocol.n)):
        a_basis, b_basis = int(alice.bases[i]), int(bob.bases[i])
        detected = bool(bob.detected[i])
        kept = detected and a_basis == b_basis
        eve = "-"
        if plan is not None and plan.intercepted[i]:
            eve = f"measures in {BASIS_NAMES[int(plan.bases[i])]}"
        rows.append({
            "photon": i,
            "Alice bit": int(alice.bits[i]),
            "Alice basis": BASIS_NAMES[a_basis],
            "state sent": STATE_LABELS[(a_basis, int(alice.bits[i]))],
            "Eve": eve,
            "Bob basis": BASIS_NAMES[b_basis],
            "Bob bit": int(bob.bits[i]) if detected else "lost",
            "kept after sifting": "yes" if kept else "no",
            "error": ("yes" if alice.bits[i] != bob.bits[i] else "no") if kept else "",
        })
    return pd.DataFrame(rows)


def circuit_text(result: QKDResult, channel: Channel, index: int) -> str:
    """Text drawing of photon ``index``'s circuit, exactly as Qiskit mode would build it."""
    protocol = result.protocol
    if not 0 <= index < protocol.n:
        raise ValueError(f"photon index must be in [0, {protocol.n})")
    qc = photon_circuit(int(protocol.alice.bits[index]), int(protocol.alice.bases[index]),
                        int(protocol.bob.bases[index]), channel, index, protocol.plans)
    return str(qc.draw(output="text", fold=-1))


def stage_lengths(result: QKDResult) -> pd.DataFrame:
    """Key length after each protocol stage, from the run itself."""
    summary = result.summary()
    stages = [
        ("Photons sent", summary["n"]),
        ("Detected by Bob", summary["detected"]),
        ("Sifted (bases match)", summary["sifted_length"]),
        ("After QBER sample", summary["remaining_length"]),
        ("After error correction", summary["remaining_length"] if result.cascade else 0),
        ("Final secret key", summary["final_key_length"]),
    ]
    return pd.DataFrame(stages, columns=["stage", "bits"])


def _style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(height=height, margin={"l": 60, "r": 20, "t": 40, "b": 50},
                      legend={"orientation": "h", "y": -0.25, "x": 0}, hovermode="closest")
    return fig


def stage_figure(stages: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=stages["bits"], y=stages["stage"], orientation="h", marker={"color": SERIES_1, "cornerradius": 4},
        text=[f"{b:,}" for b in stages["bits"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:,} bits<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="bits", rangemode="tozero")
    return _style(fig, 340)


def key_rate_figure(qber: float, f: float = DEFAULT_EC_EFFICIENCY) -> go.Figure:
    """r(Q) = 1 - h(Q) - f h(Q) with this run's QBER marked."""
    q = np.linspace(0, 0.15, 301)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=q, y=secret_fraction(q, 1.0), mode="lines", name="r(Q), ideal f = 1",
                             line={"color": MUTED, "width": 2, "dash": "dash"}, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=q, y=secret_fraction(q, f), mode="lines", name=f"r(Q), Cascade f = {f}",
                             line={"color": SERIES_1, "width": 2},
                             hovertemplate="Q = %{x:.3f}<br>r = %{y:.3f}<extra></extra>"))
    if np.isfinite(qber):
        fig.add_trace(go.Scatter(x=[qber], y=[secret_fraction(min(qber, 0.5), f)], mode="markers",
                                 name="this run", marker={"color": SERIES_2, "size": 12, "line": {"width": 2}},
                                 hovertemplate="this run: Q = %{x:.4f}<br>r = %{y:.3f}<extra></extra>"))
    fig.add_vline(x=qber_threshold(1.0), line={"color": MUTED, "width": 1},
                  annotation_text="r = 0 at 11.0% (f = 1)", annotation_position="top right")
    fig.update_xaxes(title_text="QBER Q", tickformat=".0%")
    fig.update_yaxes(title_text="Secret bits per sifted bit", range=[0, 1.02])
    return _style(fig)


def attack_figure(eve_fraction: float, qber: float, threshold: float) -> go.Figure:
    """Analytic Q = 0.25 p, with this run's measured QBER at its intercept fraction."""
    p = np.linspace(0, 1, 101)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p, y=expected_qber_intercept_resend(p), mode="lines", name="Analytic Q = 0.25 p",
                             line={"color": MUTED, "width": 2, "dash": "dash"}, hoverinfo="skip"))
    if np.isfinite(qber):
        fig.add_trace(go.Scatter(x=[eve_fraction], y=[qber], mode="markers", name="this run (all channel effects)",
                                 marker={"color": SERIES_2, "size": 12},
                                 hovertemplate="p = %{x:.2f}<br>measured Q = %{y:.4f}<extra></extra>"))
    fig.add_hline(y=threshold, line={"color": MUTED, "width": 1},
                  annotation_text=f"abort threshold {threshold:.0%}", annotation_position="top left")
    fig.update_xaxes(title_text="Eve's intercept fraction p", range=[-0.02, 1.02])
    fig.update_yaxes(title_text="QBER", tickformat=".0%", rangemode="tozero")
    return _style(fig)


def key_preview(result: QKDResult, bits: int = 64) -> pd.DataFrame:
    """First bits of each party's final key, for a visual check that they match."""
    return pd.DataFrame({
        "party": ["Alice", "Bob"],
        "final key (first bits)": [str(result.final_alice_key)[:bits], str(result.final_bob_key)[:bits]],
    })
