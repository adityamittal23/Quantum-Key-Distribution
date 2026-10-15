"""Print the headline numbers of every experiment, read straight from results/*.csv.

Use these numbers in the report and slides, so every quoted figure comes from
a run on disk:

    python -m experiments.summarize
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from qkd.results_io import RESULTS_DIR, read_results_csv


def _load(name: str, results_dir: Path) -> tuple[dict, pd.DataFrame] | None:
    path = results_dir / f"{name}.csv"
    if not path.exists():
        print(f"{name}: no results yet (run python -m experiments.{name})")
        return None
    meta, table = read_results_csv(path)
    print(f"\n== {name}  (seed {meta['seed']}, {len(table)} runs, {meta['created_utc']})")
    return meta, table


def summarize(results_dir: Path = RESULTS_DIR) -> None:
    if loaded := _load("exp1_eavesdropping", results_dir):
        _, t = loaded
        fast = t[(t["mode"] == "numpy") & (t["n"] == t["n"].max())]
        q = fast.groupby("intercept_fraction")[["qber_true", "qber_analytic"]].mean()
        print(f"QBER at p = 1 (n = {fast['n'].iloc[0]:,}): {q.loc[1.0, 'qber_true']:.4f} (analytic 0.25)")
        print(f"max |simulated - 0.25 p| over p: {(q['qber_true'] - q['qber_analytic']).abs().max():.4f}")
        detect = t[t["mode"] == "numpy"].groupby(["n", "intercept_fraction"])["aborted"].mean().unstack(0)
        print("detection probability (rows p, columns n):")
        print(detect.loc[[0.0, 0.2, 0.4, 0.5, 0.6, 1.0]].round(3).to_string())
        circuit = t[t["mode"] == "qiskit"].groupby("intercept_fraction")["qber_true"].mean()
        print("Qiskit-mode QBER by p:", circuit.round(4).to_dict())

    if loaded := _load("exp2_channel_noise", results_dir):
        _, t = loaded
        fast = t[t["mode"] == "numpy"]
        g = fast.groupby("depolarizing").agg(
            qber=("qber_true", "mean"), rate=("final_bits_per_photon", "mean"),
            aborted=("status", lambda s: (s != "ok").mean()), f=("ec_efficiency", "mean"))
        print(g.round(4).to_string())
        positive = g[g["rate"] > 0]
        print(f"largest lam with a secret key: {positive.index.max():.3f} (QBER {positive['qber'].iloc[-1]:.4f})")

    if loaded := _load("exp3_photon_loss", results_dir):
        _, t = loaded
        g = t.groupby(["depolarizing", "loss"]).agg(
            km=("distance_km", "first"), raw=("raw_bits_per_photon", "mean"), final=("final_bits_per_photon", "mean"))
        print(g.round(4).to_string())

    if loaded := _load("exp4_classical_baseline", results_dir):
        _, t = loaded
        g = t.groupby(["method", "key_bits"]).agg(
            time_s=("time_s", "mean"), photons=("photons_needed", "mean"),
            gnfs_log2=("classical_attack_log2_ops", "first"), shor_qubits=("shor_logical_qubits", "first"))
        print(g.round(4).to_string())


if __name__ == "__main__":
    summarize()
