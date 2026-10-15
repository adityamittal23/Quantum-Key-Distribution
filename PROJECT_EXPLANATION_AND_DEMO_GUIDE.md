# Complete Project Explanation, Viva Guide & Live Demo Manual
## BB84 Quantum Key Distribution (QKD) Simulator

> **Purpose of this Document:**  
> This file is written specifically for you so that you can understand every single concept, line of thought, and component of this project from absolute basics. It also gives you a **verbatim script** and **click-by-click demo walkthrough** to present confidently to your project guide/professor.

---

# Table of Contents
1. [The 60-Second "Elevator Pitch" (Start with This)](#1-the-60-second-elevator-pitch)
2. [Why Does This Project Matter? (The Problem It Solves)](#2-why-does-this-project-matter)
3. [The Core Quantum Physics (Explained Simply)](#3-the-core-quantum-physics-explained-simply)
4. [Step-by-Step Protocol Walkthrough (The 6 Stages)](#4-step-by-step-protocol-walkthrough)
5. [The Dual-Simulator Architecture (Why Both Qiskit & NumPy?)](#5-the-dual-simulator-architecture)
6. [Team Division (Who Did What for 3 Members)](#6-team-division-who-did-what-for-3-members)
7. [Step-by-Step Live Demo Script for Your Guide](#7-step-by-step-live-demo-script-for-your-guide)
8. [Professor Viva Q&A Cheat Sheet (Tough Questions & Exact Answers)](#8-professor-viva-qa-cheat-sheet)
9. [Project Codebase Map (Quick Reference)](#9-project-codebase-map)

---

# 1. The 60-Second "Elevator Pitch"

If your guide asks: *"Tell me in 1 minute what your project does"*, speak this:

> *"Sir/Ma'am, in modern cybersecurity, all secure communication (like HTTPS, online banking, and RSA) relies on classical math problems—like factoring large numbers—being too hard for computers to solve. But with Shor's algorithm running on a quantum computer, RSA can be broken in polynomial time.*
>
> *Our project implements **Quantum Key Distribution (BB84)**. Instead of relying on math, QKD relies on the **fundamental laws of quantum physics**—specifically the **No-Cloning Theorem** and **Heisenberg's Uncertainty Principle**. Alice sends single photons in quantum superposition to Bob. If an eavesdropper (Eve) attempts to intercept or measure the photons, quantum mechanics dictates that the wave function collapses, introducing an unavoidable error rate (QBER).
>
> *We have built a full end-to-end simulator in Python and Qiskit with an interactive dashboard: from single-qubit quantum circuits, eavesdropper attacks, and optical fiber noise, to classical error correction (Cascade) and privacy amplification (Toeplitz hashing) that produce a guaranteed identical, secret cryptographic key."*

---

# 2. Why Does This Project Matter?

### The Crisis: The "Quantum Threat" to Classical Encryption
* **Today's standard**: When you connect to a server, you use **RSA-2048** or Elliptic Curve Cryptography (ECC) to exchange a secret key.
* **The flaw**: RSA's security is **computational**. It assumes that factoring a 2048-bit number takes classical supercomputers thousands of years using the General Number Field Sieve (GNFS).
* **The quantum reality**: In 1994, Peter Shor proved that a quantum computer can factor numbers in seconds ($O(L^3)$ operations using $2L+3 \approx 4,099$ logical qubits). Once large-scale quantum computers arrive, all historical encrypted traffic stored today ("Harvest Now, Decrypt Later") will be broken.

### The Solution: Quantum Key Distribution (QKD)
* QKD does **not** transmit secret messages directly. It safely creates and shares a **random secret key** between two parties (Alice and Bob).
* Once Alice and Bob have an identical secret key that no eavesdropper knows, they can use it with the **One-Time Pad (Vernam Cipher)** or AES-256. The One-Time Pad is mathematically proven by Claude Shannon to be **100% unbreakable** (Information-Theoretic Security).

---

# 3. The Core Quantum Physics (Explained Simply)

There are four basic quantum principles that make BB84 impossible to hack:

```
        Z Basis (Computational)                  X Basis (Diagonal / Hadamard)
             |0> (0°)                                    |+> (45°)
                |                                           /
                |                                          /
    <---|--------------|--->                     <---|--------------|--->
                |                                          /
                |                                         /
             |1> (180°)                                  |-> (135°)
```

1. **Mutually Unbiased Bases ($Z$ and $X$)**:
   - Alice has two rulers (bases) to encode bits:
     - The **$Z$ basis** (computational): Bit `0` is $|0\rangle$, Bit `1` is $|1\rangle$.
     - The **$X$ basis** (diagonal): Bit `0` is $|+\rangle = \frac{|0\rangle + |1\rangle}{\sqrt{2}}$, Bit `1` is $|-\rangle = \frac{|0\rangle - |1\rangle}{\sqrt{2}}$.
   - If Alice prepares a photon in the $Z$ basis and Bob measures in the $Z$ basis, Bob gets Alice's exact bit with 100% certainty.
   - But if Alice prepares in $Z$ and Bob measures in $X$, Bob gets a **completely random result** ($50\%$ chance of 0, $50\%$ chance of 1). The two bases are conjugate (orthogonal in measurement space).

2. **The Measurement Collapse Postulate**:
   - A quantum state remains in superposition until measured. Measurement forces the state to collapse into an eigenstate of the measurement operator.

3. **The No-Cloning Theorem (Wootters & Zurek, 1982)**:
   - An eavesdropper (Eve) cannot make a copy of an unknown quantum state without altering the original. Therefore, Eve cannot clone Alice's photon, keep a copy, and send the original to Bob.

4. **Disturbance Implies Detection**:
   - Because Eve cannot clone the photon, the only way she can learn anything is to **measure it herself and resend a new photon to Bob** (Intercept-Resend attack).
   - Because Eve does not know which basis Alice used, she has to guess ($Z$ or $X$).
   - 50% of the time, Eve guesses the wrong basis. When she sends her wrong-basis photon to Bob, Bob (measuring in Alice's basis) gets a wrong answer 50% of the time.
   - Result: $50\% \times 50\% = \mathbf{25\%}$ **error rate (QBER)** introduced on the bits they both measured in the same basis!
   - Eve's presence is announced by the laws of quantum mechanics!

---

# 4. Step-by-Step Protocol Walkthrough

Here is the exact journey of the protocol from start to finish:

```
[ Alice ]                                                             [ Bob ]
   |                                                                     |
   |--- 1. Send Qubits (|0>, |1>, |+>, |->) over Quantum Channel ------->|
   |                                                                     |
   |        (Channel: Eve may intercept, Fiber may add noise or loss)    |
   |                                                                     |
   |<=== 2. Public Classical Discussion: Announce Bases ("Z, X, X...") ==>|
   |    ==> Sifting: Keep only matching bases (Discard ~50%)             |
   |                                                                     |
   |<=== 3. Public Classical Discussion: Compare 20% Random Sample ======>|
   |    ==> Estimate QBER: If QBER > 11% ---> ABORT (Eve detected!)      |
   |                                                                     |
   |<=== 4. Public Classical Discussion: Cascade Parity Checks ==========>|
   |    ==> Error Correction: Correct any channel noise discrepancies    |
   |                                                                     |
   |--- 5. Independent Toeplitz Hash Multiplication -------------------->|
   |    ==> Privacy Amplification: Compress key to remove leaked info    |
   |                                                                     |
[ Final Key ] <================== 100% Identical ==================> [ Final Key ]
```

### Stage 1: Alice's Preparation
- Alice generates $N$ random classical bits (`0` or `1`) and $N$ random bases ($Z$ or $X$).
- For each bit, Alice creates a quantum circuit with 1 qubit:
  - Bit 0 in $Z$ basis $\to |0\rangle$ (Do nothing)
  - Bit 1 in $Z$ basis $\to |1\rangle$ (Apply $X$ gate)
  - Bit 0 in $X$ basis $\to |+\rangle$ (Apply $H$ gate)
  - Bit 1 in $X$ basis $\to |-\rangle$ (Apply $X$ then $H$ gate)

### Stage 2: Quantum Channel Transmission
- Photons travel down an optical fiber channel.
- Three things can happen:
  1. **Eavesdropper (Eve)**: Intercepts a fraction $p$ of photons, measures them in a random basis, and resends.
  2. **Channel Noise**: Depolarizing noise or stray magnetic fields cause bit-flips.
  3. **Photon Loss**: Fiber attenuation absorbs photons ($0.2\text{ dB/km}$ in telecom fiber).

### Stage 3: Bob's Measurement
- Bob does not know Alice's bases. He picks his own random basis ($Z$ or $X$) for each incoming photon.
- If measuring in $Z$, Bob measures directly. If measuring in $X$, Bob applies an $H$ gate first, then measures.
- Photons lost in the fiber result in no detection ("no click").

### Stage 4: Basis Sifting
- Alice and Bob communicate over a public classical channel (phone, internet).
- **They DO NOT reveal their bits!** They only announce their **bases**:
  - Alice: *"For photon 1, I used Z. For photon 2, I used X..."*
  - Bob: *"I used Z for photon 1, and Z for photon 2..."*
- Whenever their bases match, they keep the bit. When their bases disagree, they throw it away.
- Result: About **50% of detected photons survive** (the "Sifted Key").

### Stage 5: QBER Estimation & Abort
- Some bits might still disagree due to noise or Eve.
- Alice and Bob sacrifice a random subset (typically 20%) of the sifted key and publicly compare them.
- They calculate the **Quantum Bit Error Rate (QBER)**:
  $$\text{QBER} = \frac{\text{Number of Errors in Sample}}{\text{Sample Size}}$$
- **Security Check**:
  - If $\text{QBER} > 11\%$: An eavesdropper is present! The secret key cannot be guaranteed. They **ABORT** the protocol and discard everything.
  - If $\text{QBER} \le 11\%$: Errors are small enough to be corrected. The sacrificed bits are permanently discarded so Eve cannot use them.

### Stage 6: Classical Post-Processing
Even below 11%, Bob's remaining key might have a few flipped bits, and Eve might have learned a few bits.
1. **Cascade Error Correction (`errorcorrection.py`)**:
   - Alice and Bob divide the key into blocks and compare block parities (sum modulo 2).
   - If parities differ, binary search pinpoints and flips Bob's erroneous bit.
   - They verify their keys match with a 32-bit random parity hash.
2. **Privacy Amplification (`privacy.py`)**:
   - Because Eve heard the public parity announcements during error correction, she has partial information.
   - Alice and Bob multiply their key by a public random **Toeplitz matrix** over $\text{GF}(2)$.
   - By the Leftover Hash Lemma, this compresses the key down to $m$ bits:
     $$m \approx n(1 - h(Q)) - \text{Leaked Bits} - \text{Security Margin}$$
   - Eve's mutual information about the final compressed key is mathematically reduced to less than $10^{-10}$ bits (practically zero!).
   - **Result: Alice and Bob now hold 100% identical, purely secret keys.**

---

# 5. The Dual-Simulator Architecture

A major innovation of our project is having **two simulator engines with the exact same interface**:

```
                       ┌────────────────────────┐
                       │  User / Dashboard UI   │
                       └───────────┬────────────┘
                                   │
                                   ▼
                       ┌────────────────────────┐
                       │   run_qkd(n, channel)  │
                       └───────────┬────────────┘
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
      ┌─────────────────────┐             ┌─────────────────────┐
      │ Qiskit Mode (Aer)   │             │  NumPy Fast Mode    │
      ├─────────────────────┤             ├─────────────────────┤
      │ Builds real quantum │             │ Vectorized arrays   │
      │ circuits per photon │             │ exact BB84 physics  │
      │ Slower, demonstrable│             │ Millions of photons │
      │ (up to 5,000 qubits)│             │ in milliseconds     │
      └─────────────────────┘             └─────────────────────┘
                 ▲                                   ▲
                 └───────────────┬───────────────────┘
                                 │
                     Validated in test suite:
               test_mode_agreement.py (38 tests)
```

* **Why Qiskit Mode?** It uses actual quantum computing objects (`QuantumCircuit`, `HGate`, `XGate`, `AerSimulator`) so you can inspect the circuit of any photon and prove to your teacher that it runs on a real quantum simulator.
* **Why NumPy Fast Mode?** Simulating individual Qiskit circuits for 100,000 photons takes minutes. NumPy fast mode simulates the exact same projective measurement probabilities in milliseconds, allowing us to generate huge statistical sweeps and error bars.
* In [`tests/test_mode_agreement.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/tests/test_mode_agreement.py), we prove that with the same seed, both modes yield statistically identical results.

---

# 6. Team Division (For a 3-Member Team)

If your guide asks how the project was divided among team members, use this official split:

| Member | Assigned Role | Modules & Files Built | Key Concepts Presented |
| :--- | :--- | :--- | :--- |
| **Member A** | **Core Quantum Protocol** | `qkd/core.py`, `qkd/sifting.py`, `qkd/qber.py`, `tests/test_core.py`, `tests/test_sifting_qber.py` | Qubit preparation in $Z$ and $X$ bases, quantum measurement collapse, basis sifting, QBER Wilson score confidence bounds, Qiskit vs. NumPy dual engine. |
| **Member B** | **Attacks & Channel Noise** | `qkd/attacks.py`, `qkd/noise.py`, `tests/test_attacks.py`, `tests/test_noise.py` | No-Cloning theorem, Intercept-Resend attack proof ($Q = 25\% \times p$), Aer noise models (depolarizing, bit-flip, readout error), optical fiber attenuation ($0.2\text{ dB/km}$). |
| **Member C** | **Post-Processing & Dashboard** | `qkd/errorcorrection.py`, `qkd/privacy.py`, `qkd/keyrate.py`, `qkd/pipeline.py`, `app/` | Cascade error correction algorithm, Toeplitz hashing for privacy amplification, Shannon binary entropy $h(Q)$, Streamlit web dashboard, RSA vs QKD benchmarks. |

---

# 7. Step-by-Step Live Demo Script for Your Guide

Follow this script step-by-step when demonstrating to your guide or professor:

### Step 1: Start the Dashboard
In your terminal, run:
```powershell
streamlit run app/streamlit_app.py
```
Open `http://localhost:8501` in your browser.

---

### Step 2: Scenario 1 — The Ideal Secure Transmission (Clean Channel)
* **What to set in Sidebar**:
  - Mode: `Fast (NumPy)`
  - Photons sent: `5,000`
  - Intercept fraction $p$: `0.0`
  - Depolarizing $\lambda$: `0.0`
  - Loss: `0.0`
* **What to show your guide**:
  - Point to the green banner: **"Secure key established"**.
  - Show the top metrics:
    - **QBER (sampled)**: `0.00%` (No errors!).
    - **Sifted key**: ~`2,500 bits` (~50% of the 5,000 photons sent).
    - **Final secret key**: ~`1,930 bits`.
  - Click on the **Key pipeline** tab: Show the horizontal bar chart showing how 5,000 photons reduce to ~2,500 sifted bits, and after the 20% QBER sample and privacy amplification, yield ~1,930 identical secret bits.
  - Show the table at the right: Alice's and Bob's final key bits match 100%!

---

### Step 3: Scenario 2 — Caught in the Act! (Full Eavesdropping Attack)
* **What to say to your guide**:
  > *"Now let's see what happens if an eavesdropper, Eve, intercepts every single photon crossing the fiber."*
* **What to set in Sidebar**:
  - Drag the **Intercept fraction $p$** slider to `1.0`.
* **What happens on screen**:
  - The banner instantly turns red: **"Aborted: estimated QBER ~25% is above the 11.0% threshold, so an eavesdropper or bad channel is assumed."**
  - Point to the **QBER and security** tab:
    - In the left graph, show that the measured QBER dot sits precisely on the theoretical line:
      $$\text{QBER} = 0.25 \times p = 25\%$$
    - Point to the dashed horizontal line at 11%: the QBER of 25% crossed the abort threshold.
  - Explain: *"Eve tried to listen, but the collapse of the quantum state introduced 25% errors. Alice and Bob detected Eve and aborted without leaking any data."*

---

### Step 4: Scenario 3 — Partial Eavesdropping & Privacy Amplification
* **What to say to your guide**:
  > *"What if Eve is clever and only taps 20% of the photons to stay below the 11% threshold?"*
* **What to set in Sidebar**:
  - Set **Intercept fraction $p$** to `0.20`.
* **What happens on screen**:
  - Banner is green: **"Secure key established"**.
  - QBER is around $\approx 5\%$ ($0.25 \times 0.20 = 5\%$).
  - Show your guide the **Key pipeline** tab:
    - Notice that the **Final secret key** is smaller than in Scenario 1.
    - Explain: *"Even though Eve stayed under the 11% threshold, our Toeplitz privacy amplification automatically shrunk the key by $n \cdot h(Q)$ bits, completely wiping out the information Eve gained!"*

---

### Step 5: Scenario 5 — Inspecting a Real Quantum Circuit
* **What to say to your guide**:
  > *"Let's look under the hood at the actual Qiskit quantum circuit for a single photon."*
* **What to click**:
  - Click on the **Photons and circuits** tab.
  - Scroll down to the circuit drawing box.
  - Enter photon index `0`, `1`, `2` to show different photons.
  - Show the guide:
    - The `X` gate (if Alice sent bit 1).
    - The `H` gate (if Alice chose the diagonal basis).
    - The `barrier` labelled `send`.
    - The `eve` mid-circuit measurement register (if Eve attacked).
    - The `barrier` labelled `receive`.
    - Bob's measurement into classical register `bob`.
  - Explain: *"This is a genuine Qiskit circuit simulated with AerSimulator."*

---

### Step 6: Scenario 6 — Real-World Fiber Attenuation
* **What to say to your guide**:
  > *"In real optical fibers, photons get absorbed over distance at 0.2 dB per kilometer."*
* **What to set in Sidebar**:
  - Toggle **"Set loss by fibre distance (0.2 dB/km)"**.
  - Slide distance to `50 km`.
  - The caption shows: *"50 km of fibre loses 90% of photons."*
* **What to show**:
  - Sifted key drops from 2,500 bits down to ~250 bits because 90% of photons never reached Bob.
  - But the remaining key still has QBER = 0% and keys still match!

---

# 8. Professor Viva Q&A Cheat Sheet

Here are the exact questions professors love to ask, with simple, punchy answers:

### Q1: "Why do Alice and Bob discard 50% of their photons during sifting?"
> **Answer**:  
> *"Because Bob has to choose his measurement basis at random without knowing Alice's choice. Since there are two orthogonal bases ($Z$ and $X$), Bob matches Alice's basis 50% of the time. When his basis disagrees, the outcomes are completely uncorrelated quantum random noise, so those photons must be discarded."*

---

### Q2: "Why is the abort threshold chosen as 11%? Why not 5% or 20%?"
> **Answer**:  
> *"11.0% is the famous **Shor-Preskill asymptotic security bound** for one-way BB84. At QBER $Q$, the secret key rate formula is:
> $$r(Q) = 1 - 2h(Q)$$
> where $h(Q) = -Q \log_2 Q - (1-Q)\log_2(1-Q)$ is the binary Shannon entropy. When $Q \approx 0.1104$ (11%), $2h(Q) = 1$, which means the secret fraction $r(Q)$ drops to zero. Above 11%, error correction and privacy amplification would consume more bits than the key has, leaving zero secret bits."*

---

### Q3: "What is the difference between Error Correction and Privacy Amplification?"
> **Answer**:  
> *"They solve opposite problems:
> - **Error Correction (Cascade)** makes Bob's key match Alice's key by finding and correcting channel errors through public parity checks.
> - **Privacy Amplification (Toeplitz Hashing)** destroys Eve's knowledge. Because error correction announced block parities in public, Eve learned partial information. Privacy amplification compresses the key using a universal hash function so that Eve's mutual information drops to zero."*

---

### Q4: "Why did you build both a NumPy mode and a Qiskit mode?"
> **Answer**:  
> *"In Qiskit, creating and simulating individual quantum circuits for 100,000 photons takes significant CPU time and memory. Therefore, we built a NumPy fast mode that applies exact projective measurement physics to large arrays in milliseconds for big statistical sweeps. We then wrote comprehensive tests in `test_mode_agreement.py` to prove both simulators produce statistically identical QBER and sifted keys."*

---

### Q5: "How does QKD compare to RSA?"
> **Answer**:  
> *"RSA is based on computational complexity—specifically, that factoring $N = p \cdot q$ is hard classically ($O(\exp((\ln N)^{1/3}))$ using GNFS). But Shor's algorithm on a quantum computer factors it in polynomial time ($O(L^3)$), rendering RSA obsolete. In contrast, QKD relies on the laws of quantum physics (No-Cloning and Heisenberg Uncertainty). No computer—classical or quantum—can break QKD because you cannot violate quantum mechanics."*

---

### Q6: "Can Eve hide her presence by only intercepting a tiny fraction of photons?"
> **Answer**:  
> *"If Eve intercepts a small fraction $p$, she introduces an error rate $Q = 0.25p$. If $p=0.10$, QBER is only 2.5%, which is under the 11% threshold. While she avoids an abort, she only intercepted 10% of the photons, so her mutual information is small. When Alice and Bob perform privacy amplification, the key length is compressed by the measured QBER, which mathematically eliminates that partial information."*

---

# 9. Project Codebase Map

When your teacher asks you to show the code, use this map:

| File | What to Open it For |
| :--- | :--- |
| [`qkd/core.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/core.py) | **Member A**: Contains `encode_qubit()`, `measure_qubit()`, `photon_circuit()`, and `run_bb84()`. |
| [`qkd/sifting.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/sifting.py) | **Member A**: Contains `sift()` which discards non-matching bases. |
| [`qkd/qber.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/qber.py) | **Member A**: Contains `estimate_qber()` and Wilson confidence intervals. |
| [`qkd/attacks.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/attacks.py) | **Member B**: Contains `InterceptResend` and `detection_probability()`. |
| [`qkd/noise.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/noise.py) | **Member B**: Contains `Depolarizing`, `BitFlip`, `ReadoutNoise`, and `PhotonLoss`. |
| [`qkd/errorcorrection.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/errorcorrection.py) | **Member C**: Contains the Cascade algorithm and binary search error locator. |
| [`qkd/privacy.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/qkd/privacy.py) | **Member C**: Contains `ToeplitzHash` and FFT-based matrix compression. |
| [`app/streamlit_app.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/app/streamlit_app.py) | **Member C**: The Streamlit user interface code. |
| [`experiments/summarize.py`](file:///C:/Users/ADMIN/OneDrive/Desktop/VIT/7th%20Semester/Quantum%20Computing/Project/experiments/summarize.py) | Prints the master benchmark numbers from disk. |

---

### Summary Checklist for Demo Day:
1. Open PowerShell and run: `streamlit run app/streamlit_app.py`.
2. Have this file (`PROJECT_EXPLANATION_AND_DEMO_GUIDE.md`) open on your screen as your speaking notes.
3. Follow the 6 demo scenarios in Section 7.
4. Keep Section 8 ready for any viva questions!
