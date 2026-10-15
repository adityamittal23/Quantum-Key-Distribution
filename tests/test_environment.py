"""Checks that the pinned Qiskit stack exposes the APIs the simulator relies on."""

import qiskit
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator


def test_removed_execute_api_is_not_used():
    assert not hasattr(qiskit, "execute")


def test_single_qubit_bb84_round_trip_on_aer():
    # Alice sends |-> (bit 1, X basis); Bob measures in X and must read 1.
    qc = QuantumCircuit(1, 1)
    qc.x(0)
    qc.h(0)
    qc.h(0)
    qc.measure(0, 0)
    result = AerSimulator(seed_simulator=1).run(qc, shots=20, memory=True).result()
    assert set(result.get_memory()) == {"1"}
