# QKD Simulator Project Plan

Oct 14, 2026 · @Pratham

We will build a BB84 quantum key distribution simulator in Python and Qiskit, with eavesdropper attacks, channel noise and a dashboard, split across three members and finished in six weeks.

## Quantum principles covered

Six core syllabus ideas carry the security argument, and each one has a concrete place in the code.

| Principle | Role in QKD | Where it appears in the project |
| --- | --- | --- |
| Qubit and superposition | Alice encodes each bit in one of two bases | Qiskit circuit per photon: X for bit 1, H for the diagonal basis |
| Measurement and collapse | Wrong-basis measurement gives a random result | Bob's basis choice and measurement step |
| Complementary bases | Z and X bases are mutually unbiased, so one measurement erases the other | Basis sifting and the 50% mismatch discard |
| No-cloning theorem | Eve cannot copy a qubit and keep it intact | Intercept-resend attack module |
| Disturbance implies detection | Eve's guesses add errors on the sifted key | QBER estimate on a sampled subset |
| Entanglement (stretch goal) | Shared Bell pairs give correlated outcomes | E91 variant with a CHSH test |

Dirac notation ties these together: states are written as |0>, |1>, |+>, |->, and the project can reuse the course's Dirac-to-vector conversion idea (sample project 1) for the state display.

## Architecture

&#91;embedded content: QKD simulator architecture · 3 stages, 4 post-processing steps\]

Qubits travel through the channel that Member B's attack and noise modules control, and everything after measurement runs on the public classical channel. The highlighted box is where the security argument lives. Member A owns Alice, Bob, sifting and the QBER check; Member C owns error correction, amplification and the dashboard.

## Tech stack

Python end to end keeps the three members on one language; Qiskit with the Aer simulator does the quantum work, and Streamlit gives the dashboard without a separate frontend.

| Layer | Choice | Why |
| --- | --- | --- |
| Quantum circuits | Qiskit + Qiskit Aer | Syllabus-standard, supports noise models, fast statevector and shot-based runs |
| Noise modelling | Qiskit Aer NoiseModel (depolarizing, bit-flip, readout error) | Gives realistic channel loss and error for QBER studies |
| Numerics and data | NumPy, pandas | Bulk bit-string handling and result tables |
| Classical post-processing | Python: error correction (Cascade), privacy amplification (universal hashing) | Turns the sifted key into a usable secret key |
| Visualisation | Streamlit + Plotly, Qiskit circuit drawer, Bloch sphere plots | Interactive sliders for noise and attack strength |
| Fast mode | NumPy-only BB84 simulator | Runs 100,000+ qubits for statistics, while Qiskit handles the demonstrable circuits |
| Testing | pytest | Checks known results: QBER near 0 without Eve, near 25% with full intercept-resend |
| Repository | Git + GitHub | Three contributors, visible commit history for the viva |
| Optional demo | IBM Quantum free tier | One small real-hardware run of 8 to 16 qubits, if queue time allows |

A separate NumPy fast mode matters: Qiskit circuits per photon are slow at scale, so the large statistical sweeps use the NumPy version, validated against Qiskit on small runs.

## Team split

Each member owns a separable module with its own tests and its own slide section, which meets the syllabus rule that members present their contributions in detail. The assignment of names is open.

| Member | Module | Deliverables | What they present |
| --- | --- | --- | --- |
| A | Core protocol | BB84 circuits in Qiskit, basis sifting, QBER estimation, NumPy fast simulator, validation against Qiskit | Qubit encoding, measurement and basis mismatch, with live circuit demo |
| B | Attacks and noise | Intercept-resend and partial-intercept Eve, Aer noise models, photon-loss model, attack detection threshold | No-cloning, disturbance and detection, QBER versus attack strength |
| C | Post-processing and dashboard | Cascade error correction, privacy amplification, key-rate computation, Streamlit dashboard, final report plots | Secret key rate, security threshold, and the full end-to-end demo |

Shared work: the repository layout, a common `Channel` and `Key` interface agreed in week 1, and the final report.

## Protocol and maths

BB84 runs in six steps, and the numbers below are what the tests check against.

1. Alice draws random bits and random bases (Z or X) and prepares |0>, |1>, |+> or |-> accordingly.
2. The qubits cross the channel, where Eve and noise may act on them.
3. Bob picks random bases and measures.
4. Alice and Bob announce bases publicly and keep only matching positions, about half of the qubits (the sifted key).
5. They sacrifice a random sample of the sifted key to estimate the error rate Q (QBER). If Q exceeds the threshold, they abort.
6. They run error correction and privacy amplification on the rest to get the final secret key.

Expected results to verify:

- With no Eve and no noise, Q = 0 and the sifted key length is about n/2.
- With Eve intercepting every qubit in a random basis, Q = 25%, because she guesses the basis wrongly half the time and a wrong guess flips Bob's result half the time.
- If Eve intercepts a fraction p of qubits, Q = 25% x p.
- Aborting above roughly 11% QBER matches the known asymptotic security bound for one-way BB84.

The asymptotic secret fraction, with h the binary entropy and f the error-correction inefficiency (about 1.1 to 1.2 for Cascade):

```latex
r = 1 - h(Q) - f\,h(Q), \qquad h(x) = -x\log_2 x - (1-x)\log_2(1-x)
```

The dashboard will plot r against Q to show the key rate falling to zero near the threshold.

## Experiments

Four experiments turn the simulator into an evaluation, and each has a classical baseline or an analytic prediction to compare against.

| Experiment | Variable swept | Metric | Compared against |
| --- | --- | --- | --- |
| 1. Eavesdropping detection | Eve intercept fraction, 0 to 100% | QBER, detection probability | Analytic Q = 25% x p |
| 2. Channel noise | Depolarizing error, 0 to 15% | QBER, sifted key length, secret key rate | Threshold near 11% |
| 3. Photon loss and distance | Loss probability, 0 to 90% | Raw key rate, final key rate | Ideal lossless channel |
| 4. Classical baseline | Key size, 128 to 2048 bits | Time to exchange a key, security basis | RSA key exchange and the Shor attack cost from the course |

Experiment 4 connects back to the syllabus: classical key exchange relies on factoring being hard, while QKD relies on physics, and the plan's report should state that comparison plainly.

Each run is seeded and logged to CSV so every plotted number can be traced to its run.

## Schedule

The plan assumes a start on Oct 15, 2026 and a final demo in the week of Nov 23; shift the weeks once the real submission date is known.

| Week | Dates | Milestone | Owner |
| --- | --- | --- | --- |
| 1 | Oct 15 to 21 | Topic approved, repo and interfaces fixed, basic BB84 circuit for one qubit running | All, A leads |
| 2 | Oct 22 to 28 | Full BB84 with sifting and QBER, NumPy fast mode, first tests passing | A |
| 3 | Oct 29 to Nov 4 | Intercept-resend Eve, noise models, loss model, experiments 1 and 2 | B |
| 4 | Nov 5 to 11 | Cascade and privacy amplification, key-rate computation, experiment 3 | C |
| 5 | Nov 12 to 18 | Streamlit dashboard, experiment 4 baseline, optional IBM hardware run | C, then all |
| 6 | Nov 19 to 25 | Report, slides, rehearsal of each member's section, demo freeze | All |

## Risks and open questions

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Qiskit circuit-per-qubit runs are too slow for large sweeps | High | NumPy fast mode, validated against Qiskit on small runs |
| Cascade error correction is fiddly to implement | Medium | Start with a simple parity-block version, upgrade only if time allows |
| IBM hardware queue delays the optional demo | Medium | Treat it as a bonus and keep the Aer noise model as the main result |
| One member's module blocks the others | Medium | Agree the `Channel` and `Key` interfaces in week 1 and stub them |
| Scope creep into E91 or finite-key analysis | Medium | Keep both as stretch goals after experiments 1 to 4 are done |
