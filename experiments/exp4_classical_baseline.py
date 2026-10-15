"""Experiment 4: QKD against a classical RSA key exchange.

For each key size L from 128 to 2048 bits:

* RSA, measured: time to generate an L-bit-modulus key pair, then encrypt and
  decrypt a random session key (key transport). Security rests on factoring
  being hard. The GNFS work and Shor's qubit count are analytic models from
  ``rsa_baseline``.
* QKD, measured: the fewest photons, on a geometric grid of n, that give at
  least L final secret bits over a channel with depolarizing 4% (QBER of about
  2%), and the simulator's wall time for that run in fast mode and Qiskit
  mode. Security rests on physics: no-cloning, and disturbance revealing Eve.

Times are measured on the machine named in the CSV header, so they are
machine-dependent. They compare cost in this simulator; they are not the speed
of real QKD hardware, which depends on the photon source rate and the fibre.

    python -m experiments.exp4_classical_baseline [--quick] [--seed N]
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from experiments.common import INK_MUTED, SERIES, cli, mean_and_interval, run_seed, style_figure
from experiments.rsa_baseline import generate_keypair, gnfs_log2_operations, shor_logical_qubits
from qkd.channel import Channel
from qkd.noise import Depolarizing
from qkd.pipeline import run_qkd

NAME = "exp4_classical_baseline"
QKD_SECURITY = "physics: no-cloning and disturbance detection"
RSA_SECURITY = "computational: hardness of factoring (broken by Shor)"


@dataclass(frozen=True)
class Config:
    key_bits: tuple[int, ...] = (128, 256, 512, 1024, 2048)
    rsa_trials: int = 5
    qkd_trials: int = 5
    qiskit_trials: int = 1
    depolarizing: float = 0.04
    n_start: int = 500
    n_growth: float = 1.1  # photon-count grid: n_start x 1.1^k
    n_max: int = 2_000_000


FULL = Config()
QUICK = Config(key_bits=(128, 256), rsa_trials=1, qkd_trials=1, qiskit_trials=1)


def _rsa_row(bits: int, seed: int) -> dict:
    rng = random.Random(seed)
    start = time.perf_counter()
    keys = generate_keypair(bits, rng)
    keygen = time.perf_counter() - start
    session_key = rng.randrange(1, keys.n)
    start = time.perf_counter()
    ciphertext = keys.encrypt(session_key)
    encrypt = time.perf_counter() - start
    start = time.perf_counter()
    recovered = keys.decrypt(ciphertext)
    decrypt = time.perf_counter() - start
    if recovered != session_key:
        raise RuntimeError("RSA round trip failed")
    return {
        "method": "rsa",
        "key_bits": bits,
        "seed": seed,
        "time_s": keygen + encrypt + decrypt,
        "rsa_keygen_s": keygen,
        "rsa_encrypt_s": encrypt,
        "rsa_decrypt_s": decrypt,
        "security_basis": RSA_SECURITY,
        "classical_attack_log2_ops": gnfs_log2_operations(bits),
        "shor_logical_qubits": shor_logical_qubits(bits),
    }


def photons_for_key(bits: int, config: Config, seed: int) -> tuple[int, dict]:
    """Smallest n on the grid whose run yields at least ``bits`` secret bits."""
    channel = Channel((Depolarizing(config.depolarizing),))
    k = 0
    while True:
        n = math.ceil(config.n_start * config.n_growth**k)
        if n > config.n_max:
            raise RuntimeError(f"no {bits}-bit key within {config.n_max} photons")
        summary = run_qkd(n, channel, "numpy", seed).summary()
        if summary["status"] == "ok" and summary["final_key_length"] >= bits:
            return n, summary
        k += 1


def _qkd_row(bits: int, mode: str, n: int, config: Config, seed: int) -> dict:
    channel = Channel((Depolarizing(config.depolarizing),))
    start = time.perf_counter()
    summary = run_qkd(n, channel, mode, seed).summary()
    elapsed = time.perf_counter() - start
    return {
        "method": f"qkd_{mode}",
        "key_bits": bits,
        "seed": seed,
        "time_s": elapsed,
        "photons_needed": n,
        "final_key_length": summary["final_key_length"],
        "qber_estimate": summary["qber_estimate"],
        "keys_match": summary["keys_match"],
        "security_basis": QKD_SECURITY,
    }


def run(config: Config, seed: int) -> pd.DataFrame:
    rows, index = [], 0
    for bits in config.key_bits:
        for _ in range(config.rsa_trials):
            rows.append(_rsa_row(bits, run_seed(seed, index)))
            index += 1
        for trial in range(config.qkd_trials):
            row_seed = run_seed(seed, index)
            index += 1
            n, _ = photons_for_key(bits, config, row_seed)
            rows.append(_qkd_row(bits, "numpy", n, config, row_seed))
            if trial < config.qiskit_trials:
                rows.append(_qkd_row(bits, "qiskit", n, config, row_seed))
    return pd.DataFrame(rows)


def plot(table: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=2, vertical_spacing=0.2, horizontal_spacing=0.1, subplot_titles=(
        "Measured time to establish a key", "QKD: photons needed for an L-bit secret key",
        "Classical attack on RSA: GNFS work (analytic)", "Quantum attack on RSA: Shor's logical qubits (analytic)"))
    labels = {"rsa": "RSA key pair + transport", "qkd_numpy": "QKD simulation, fast mode",
              "qkd_qiskit": "QKD simulation, Qiskit mode"}
    for slot, method in enumerate(["rsa", "qkd_numpy", "qkd_qiskit"]):
        group = table[table["method"] == method]
        if group.empty:
            continue
        stats = mean_and_interval(group, ["key_bits"], "time_s")
        fig.add_trace(go.Scatter(
            x=stats["key_bits"], y=stats["mean"], mode="markers+lines", name=labels[method],
            marker={"color": SERIES[slot], "size": 8}, line={"color": SERIES[slot], "width": 2},
            hovertemplate="L = %{x} bits<br>%{y:.4f} s<extra>" + labels[method] + "</extra>"), 1, 1)

    qkd = table[table["method"] == "qkd_numpy"]
    photons = mean_and_interval(qkd, ["key_bits"], "photons_needed")
    fig.add_trace(go.Scatter(
        x=photons["key_bits"], y=photons["mean"], mode="markers+lines", name="QKD photons needed",
        showlegend=False, marker={"color": SERIES[1], "size": 8}, line={"color": SERIES[1], "width": 2},
        error_y={"type": "data", "array": photons["half_width"], "color": SERIES[1], "thickness": 1.5},
        hovertemplate="L = %{x} bits<br>%{y:,.0f} photons<extra></extra>"), 1, 2)

    rsa = table[table["method"] == "rsa"].groupby("key_bits").first().reset_index()
    for col, row_col, unit in [("classical_attack_log2_ops", (2, 1), "log2 operations"),
                               ("shor_logical_qubits", (2, 2), "logical qubits")]:
        fig.add_trace(go.Scatter(
            x=rsa["key_bits"], y=rsa[col], mode="markers+lines", showlegend=False,
            marker={"color": INK_MUTED, "size": 8}, line={"color": INK_MUTED, "width": 2, "dash": "dash"},
            hovertemplate="RSA-%{x}<br>%{y:,.1f} " + unit + "<extra>analytic</extra>"), *row_col)

    fig.update_xaxes(title_text="Key size L (bits): RSA modulus, or QKD secret key", type="log",
                     tickvals=sorted(table["key_bits"].unique()))
    fig.update_yaxes(title_text="Seconds (log scale)", type="log", dtick=1, row=1, col=1)
    fig.update_yaxes(title_text="Photons sent", rangemode="tozero", row=1, col=2)
    fig.update_yaxes(title_text="log2 operations", row=2, col=1)
    fig.update_yaxes(title_text="Logical qubits (2L + 3)", rangemode="tozero", row=2, col=2)
    style_figure(fig, "Experiment 4: RSA security is computational; QKD security is physical")
    fig.update_layout(height=820, hovermode="closest", legend={"y": -0.12})
    return fig


def main(argv: list[str] | None = None) -> None:
    cli(NAME, run, plot, FULL, QUICK, argv)


if __name__ == "__main__":
    main()
