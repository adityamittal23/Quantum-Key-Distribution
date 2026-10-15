"""BB84 QKD dashboard (Member C).

    streamlit run app/streamlit_app.py

The sidebar sets the channel: Eve, noise and loss. The main page runs the
whole protocol and shows each stage: photons and circuits, QBER and security,
the key-length pipeline, and the saved experiment results.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `streamlit run` puts only app/ on the path
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.dashboard_logic import (  # noqa: E402
    PHOTON_COUNTS,
    QISKIT_MAX_PHOTONS,
    DashboardParams,
    attack_figure,
    build_channel,
    circuit_text,
    key_preview,
    key_rate_figure,
    photon_table,
    simulate,
    stage_figure,
    stage_lengths,
)
from qkd.noise import loss_from_distance  # noqa: E402
from qkd.results_io import RESULTS_DIR, read_results_csv  # noqa: E402

EXPERIMENTS = {
    "1. Eavesdropping detection": "exp1_eavesdropping",
    "2. Channel noise": "exp2_channel_noise",
    "3. Photon loss and distance": "exp3_photon_loss",
    "4. Classical baseline (RSA)": "exp4_classical_baseline",
}

PHOTON_ROWS = 16
ROW_PX = 35  # Streamlit dataframe row height, so all PHOTON_ROWS rows show without scrolling
LEGEND_ROOM_PX = 110
KEY_PREVIEW_BITS = 48

st.set_page_config(page_title="BB84 QKD Simulator", page_icon=":material/key:", layout="wide")


@st.cache_data(show_spinner="Running BB84...", max_entries=32)
def cached_run(params: DashboardParams):
    return simulate(params)


def sidebar() -> DashboardParams:
    sb = st.sidebar
    sb.header("Simulator")
    mode = sb.radio("Mode", ["numpy", "qiskit"], horizontal=True,
                    format_func=lambda m: "Fast (NumPy)" if m == "numpy" else "Qiskit circuits (Aer)",
                    help="Both modes share every random choice for a given seed; Qiskit mode runs one circuit per photon.")
    counts = [c for c in PHOTON_COUNTS if mode == "numpy" or c <= QISKIT_MAX_PHOTONS]
    n = sb.select_slider("Photons sent", options=counts, value=min(5_000, counts[-1]))
    seed = int(sb.number_input("Seed", min_value=0, max_value=2**31 - 1, value=2026, step=1))

    sb.header("Eavesdropper")
    eve = sb.slider("Intercept fraction p", 0.0, 1.0, 0.0, 0.05,
                    help="Eve measures this fraction of photons in a random basis and resends them. Expected QBER: 25% x p.")

    sb.header("Channel noise")
    dep = sb.slider("Depolarizing λ", 0.0, 0.30, 0.0, 0.01, help="QBER contribution λ/2.")
    flip = sb.slider("Bit flip", 0.0, 0.30, 0.0, 0.01, help="Pauli X; affects only Z-basis photons, so QBER is p/2.")
    readout = sb.slider("Detector readout error", 0.0, 0.20, 0.0, 0.01, help="Bob's detector reports the wrong bit.")

    sb.header("Photon loss")
    by_distance = sb.toggle("Set loss by fibre distance (0.2 dB/km)")
    if by_distance:
        km = sb.slider("Distance (km)", 0, 100, 0, 5)
        loss = loss_from_distance(km)
        sb.caption(f"{km} km of fibre loses {loss:.1%} of photons.")
    else:
        loss = sb.slider("Loss probability", 0.0, 0.95, 0.0, 0.05)

    sb.header("Protocol")
    threshold = sb.slider("Abort threshold", 0.05, 0.20, 0.11, 0.005, format="%.3f")
    sample = sb.slider("QBER sample fraction", 0.05, 0.5, 0.2, 0.05)
    return DashboardParams(mode, int(n), seed, eve, dep, flip, readout, float(loss), threshold, sample)


def status_banner(summary: dict) -> None:
    status = summary["status"]
    if status == "ok" and summary["final_key_length"] > 0:
        st.success(f"Secure key established: {summary['final_key_length']:,} identical secret bits.",
                   icon=":material/check_circle:")
    elif status == "ok":
        st.warning("Keys agree after error correction, but privacy amplification leaves no secret bits: "
                   "the QBER is too high for the error-correction leakage.", icon=":material/warning:")
    elif status == "aborted_qber":
        st.error(f"Aborted: estimated QBER {summary['qber_estimate']:.2%} is above the "
                 f"{summary['threshold']:.1%} threshold, so an eavesdropper or a bad channel is assumed.",
                 icon=":material/gpp_bad:")
    else:
        st.warning("Aborted: the verification hashes differ after error correction.", icon=":material/warning:")


def metrics(summary: dict, result) -> None:
    cols = st.columns(5)
    q = summary["qber_estimate"]
    se = result.protocol.qber.standard_error
    cols[0].metric("QBER (sampled)", "n/a" if q != q else f"{q:.2%}",
                   help=f"From {summary['sample_size']:,} sacrificed bits; standard error {se:.2%}. "
                        f"Whole-key value seen only by the simulator: {summary['qber_true']:.2%}.")
    cols[1].metric("Sifted key", f"{summary['sifted_length']:,} bits",
                   help="Positions where Bob detected the photon and the bases matched (about half).")
    cols[2].metric("Final secret key", f"{summary['final_key_length']:,} bits")
    cols[3].metric("Key rate", f"{summary['final_bits_per_photon']:.4f}", help="Secret bits per photon sent.")
    eff = summary["ec_efficiency"]
    cols[4].metric("Cascade leakage", f"{summary['ec_leaked_bits']:,} bits",
                   help="Parities revealed in public; f = leaked / (n h(Q)).",
                   delta=None if eff != eff else f"f = {eff:.2f}", delta_color="off")


def photons_tab(result, channel, params: DashboardParams) -> None:
    st.markdown(
        "Alice encodes each bit in a random basis: **Z** gives |0>/|1>, and **X** gives |+>/|->. "
        "Bob measures in his own random basis. A wrong basis gives a random result, because the bases are "
        "mutually unbiased. Eve cannot copy a qubit (no-cloning), so she must measure it, and a wrong guess "
        "disturbs it.")
    table = photon_table(result, channel, PHOTON_ROWS)
    st.dataframe(table, hide_index=True, width="stretch", height=ROW_PX * (len(table) + 1) + 3)
    left, right = st.columns([1, 3])
    index = left.number_input("Draw the circuit for photon", 0, params.n - 1, 0, 1)
    left.caption("This is the circuit Qiskit mode runs for this photon: Alice's preparation | channel | "
                 "Bob's measurement. Eve's intercept is a mid-circuit measurement into the `eve` register; "
                 "noise appears as labelled identity gates that carry the Aer error.")
    right.code(circuit_text(result, channel, int(index)), language=None)


def security_tab(result, params: DashboardParams) -> None:
    q = result.protocol.qber.qber
    left, right = st.columns(2)
    left.subheader("Disturbance reveals Eve")
    left.plotly_chart(attack_figure(params.eve_fraction, q, params.threshold), width="stretch", theme="streamlit")
    left.caption("Eve picks the wrong basis half the time, and then Bob's bit is wrong half the time: Q = 25% x p. "
                 "Noise adds to the QBER too, because the protocol cannot tell noise from Eve.")
    right.subheader("Secret fraction r(Q)")
    right.plotly_chart(key_rate_figure(q), width="stretch", theme="streamlit")
    right.caption("r = 1 - h(Q) - f h(Q): Eve's possible knowledge, h(Q), plus the bits revealed by error "
                  "correction, f h(Q), are removed. The bound r = 0 at 11% is why the protocol aborts there.")


def pipeline_tab(result) -> None:
    left, right = st.columns([3, 2])
    left.subheader("Key length after each stage")
    left.plotly_chart(stage_figure(stage_lengths(result)), width="stretch", theme="streamlit")
    right.subheader("Final keys")
    if result.status == "ok" and len(result.final_alice_key):
        right.dataframe(key_preview(result, KEY_PREVIEW_BITS), hide_index=True, width="stretch")
        right.write("Identical: **yes**" if result.keys_match else "Identical: **no**")
    else:
        right.info("No final key in this run.")
    if result.cascade:
        c = result.cascade
        right.markdown(
            f"- Cascade: {c.passes} passes, first block {c.first_block_size} bits, {c.corrections:,} bits corrected\n"
            f"- Verification hash: {'match' if c.verified else 'mismatch'}\n"
            f"- Privacy amplification: Toeplitz hash, {len(c.alice_key):,} to {len(result.final_alice_key):,} bits")


def experiments_tab() -> None:
    choice = st.selectbox("Saved experiment", list(EXPERIMENTS))
    name = EXPERIMENTS[choice]
    path = RESULTS_DIR / f"{name}.csv"
    if not path.exists():
        st.info(f"No results yet. Run `python -m experiments.{name}`.")
        return
    meta, table = read_results_csv(path)
    module = importlib.import_module(f"experiments.{name}")
    figure = module.plot(table)
    # The page is narrower than the report PNG, so the legend wraps onto more rows: give it room.
    figure.update_layout(height=(figure.layout.height or 560) + LEGEND_ROOM_PX,
                         margin={"b": 90 + LEGEND_ROOM_PX}, legend={"y": 0.01, "yanchor": "bottom", "yref": "container"})
    st.plotly_chart(figure, width="stretch", theme=None)
    st.caption(f"From results/{name}.csv: master seed {meta['seed']}, {len(table):,} runs, "
               f"created {meta['created_utc']}. Every point is the mean of rows in that file.")
    with st.expander("Raw rows"):
        st.dataframe(table, hide_index=True)


def main() -> None:
    st.title("BB84 Quantum Key Distribution")
    st.caption("Alice and Bob grow a shared secret key from single qubits. Any eavesdropping shows up as errors.")
    params = sidebar()
    channel = build_channel(params)
    result = cached_run(params)
    summary = result.summary()
    status_banner(summary)
    metrics(summary, result)
    tabs = st.tabs(["Photons and circuits", "QBER and security", "Key pipeline", "Experiment results"])
    with tabs[0]:
        photons_tab(result, channel, params)
    with tabs[1]:
        security_tab(result, params)
    with tabs[2]:
        pipeline_tab(result)
    with tabs[3]:
        experiments_tab()


main()
