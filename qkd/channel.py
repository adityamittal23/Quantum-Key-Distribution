"""The quantum channel between Alice and Bob, shared by both simulators.

A ``Channel`` is an ordered tuple of ``ChannelEffect`` objects (Eve, noise,
loss, ...). Member B writes effects; Member A's simulators consume them. Each
effect describes itself once and works in both modes:

* ``sample`` draws the effect's classical random choices for ``n`` photons
  (for example which photons Eve intercepts and in which basis). The same
  draws feed both simulators, so for a fixed seed the two modes see the same
  attack and the same lost photons.
* ``transmit_numpy`` applies the effect to the fast-mode ``Photons``.
* ``append_to_circuit`` adds the effect's gates to photon ``index``'s circuit
  in Qiskit mode, between Alice's preparation and Bob's measurement.
* ``noise_terms`` returns Aer noise-model entries for Qiskit mode.
* ``detect_numpy`` acts on Bob's measured bits in fast mode, for effects in
  his detector rather than in the fibre (for example readout error).
* ``lost_mask`` reports which photons the effect removed, for Qiskit mode.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer.noise import NoiseModel, QuantumError, ReadoutError

from qkd.key import Photons, as_mask


@dataclass(frozen=True)
class NoiseTerm:
    """One Aer noise-model entry.

    A ``QuantumError`` is attached to every instruction named in
    ``instructions``. A ``ReadoutError`` applies to all measurements, and
    ``instructions`` is ignored for it.
    """

    error: QuantumError | ReadoutError
    instructions: tuple[str, ...] = ()


class ChannelEffect(ABC):
    """One physical process acting on the photons between Alice and Bob."""

    name: str = "effect"

    def sample(self, n: int, rng: np.random.Generator) -> Any:
        """Pre-draw this effect's classical randomness for ``n`` photons."""
        return None

    @abstractmethod
    def transmit_numpy(self, photons: Photons, plan: Any, rng: np.random.Generator) -> Photons:
        """Return the photons after this effect (fast mode)."""

    def append_to_circuit(self, qc: QuantumCircuit, index: int, plan: Any) -> None:
        """Add gates for photon ``index`` to its one-qubit circuit (Qiskit mode)."""

    def noise_terms(self) -> tuple[NoiseTerm, ...]:
        """Aer noise-model entries this effect needs (Qiskit mode)."""
        return ()

    def detect_numpy(self, bits: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Return Bob's measured bits after detector-side effects (fast mode)."""
        return bits

    def lost_mask(self, plan: Any, n: int) -> np.ndarray:
        """Photons this effect removed from the channel (Qiskit mode)."""
        return np.zeros(n, dtype=bool)

    def describe(self) -> dict[str, Any]:
        """Parameters for result logging; override to add the effect's settings."""
        return {"effect": self.name}


@dataclass(frozen=True)
class Channel:
    """An ordered composition of effects. ``Channel()`` is a perfect channel."""

    effects: tuple[ChannelEffect, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", tuple(self.effects))
        for effect in self.effects:
            if not isinstance(effect, ChannelEffect):
                raise TypeError(f"not a ChannelEffect: {effect!r}")

    def then(self, effect: ChannelEffect) -> Channel:
        """New channel with ``effect`` appended after the existing ones."""
        return Channel(self.effects + (effect,))

    def sample(self, n: int, rng: np.random.Generator) -> tuple[Any, ...]:
        """One plan per effect, drawn in channel order from ``rng``."""
        return tuple(effect.sample(n, rng) for effect in self.effects)

    def transmit_numpy(
        self, photons: Photons, plans: tuple[Any, ...], rng: np.random.Generator
    ) -> Photons:
        for effect, plan in zip(self.effects, plans, strict=True):
            photons = effect.transmit_numpy(photons, plan, rng)
        return photons

    def detect_numpy(self, bits: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        for effect in self.effects:
            bits = effect.detect_numpy(bits, rng)
        return bits

    def append_to_circuit(self, qc: QuantumCircuit, index: int, plans: tuple[Any, ...]) -> None:
        for effect, plan in zip(self.effects, plans, strict=True):
            effect.append_to_circuit(qc, index, plan)

    def lost_mask(self, plans: tuple[Any, ...], n: int) -> np.ndarray:
        lost = np.zeros(n, dtype=bool)
        for effect, plan in zip(self.effects, plans, strict=True):
            lost = lost | as_mask(effect.lost_mask(plan, n), effect.name)
        return lost

    def build_noise_model(self) -> NoiseModel | None:
        """Combine every effect's noise terms into one Aer model, or None if noiseless.

        Each quantum error is attached to the instruction label its effect places
        in the circuit. Two effects claiming the same label would make Aer apply
        both errors at both gates, so that is rejected. Readout errors from
        several effects are composed into one.
        """
        quantum: dict[str, QuantumError] = {}
        readout: ReadoutError | None = None
        for effect in self.effects:
            for term in effect.noise_terms():
                if isinstance(term.error, ReadoutError):
                    readout = term.error if readout is None else readout.compose(term.error)
                    continue
                if not term.instructions:
                    raise ValueError(f"{effect.name}: a QuantumError needs instruction names")
                for name in term.instructions:
                    if name in quantum:
                        raise ValueError(
                            f"two effects attach noise to instruction {name!r}; "
                            "combine them into one effect instead"
                        )
                    quantum[name] = term.error
        if not quantum and readout is None:
            return None
        model = NoiseModel()
        for name, error in quantum.items():
            model.add_all_qubit_quantum_error(error, [name])
        if readout is not None:
            model.add_all_qubit_readout_error(readout)
        return model

    def describe(self) -> list[dict[str, Any]]:
        return [effect.describe() for effect in self.effects]
