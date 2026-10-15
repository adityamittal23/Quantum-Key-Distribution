"""Shared data types passed between the BB84 stages.

This module and ``channel.py`` are the contract between the three team modules:
core protocol (Member A), attacks and noise (Member B), and post-processing
(Member C). Every type is a frozen dataclass whose arrays are read-only, so a
stage returns new objects instead of changing the ones it was given.

Bit and basis conventions used everywhere:

* bits are ``np.uint8`` arrays holding 0 or 1;
* ``Z_BASIS`` (0) is the computational basis {|0>, |1>};
* ``X_BASIS`` (1) is the diagonal basis {|+>, |->}, where |+> encodes 0 and |-> encodes 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

Z_BASIS = 0
X_BASIS = 1
BASIS_NAMES = {Z_BASIS: "Z", X_BASIS: "X"}

# Dirac labels for the four BB84 states, indexed by (basis, bit).
STATE_LABELS = {
    (Z_BASIS, 0): "|0>",
    (Z_BASIS, 1): "|1>",
    (X_BASIS, 0): "|+>",
    (X_BASIS, 1): "|->",
}


def as_bit_array(values: Iterable[int] | np.ndarray, name: str = "bits") -> np.ndarray:
    """Return a read-only 1-D uint8 copy of ``values``, rejecting anything but 0/1."""
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    if arr.size and not np.isin(arr, (0, 1)).all():
        raise ValueError(f"{name} must contain only 0 and 1")
    out = arr.astype(np.uint8, copy=True)
    out.setflags(write=False)
    return out


def as_mask(values: Iterable[bool] | np.ndarray, name: str = "mask") -> np.ndarray:
    """Return a read-only 1-D boolean copy of ``values``."""
    arr = np.asarray(values, dtype=bool)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got shape {arr.shape}")
    out = arr.copy()
    out.setflags(write=False)
    return out


def _require_same_length(**arrays: np.ndarray) -> None:
    lengths = {name: len(arr) for name, arr in arrays.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"length mismatch: {lengths}")


@dataclass(frozen=True, eq=False)
class Key:
    """A bit string held by one party (raw, sifted, corrected or final key)."""

    bits: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "bits", as_bit_array(self.bits, "bits"))

    @classmethod
    def from_string(cls, text: str) -> Key:
        return cls(np.array([int(ch) for ch in text], dtype=np.uint8))

    def __len__(self) -> int:
        return int(self.bits.size)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Key):
            return NotImplemented
        return bool(np.array_equal(self.bits, other.bits))

    __hash__ = None  # type: ignore[assignment]  # mutable-looking value type; not hashable

    def __str__(self) -> str:
        return "".join(map(str, self.bits.tolist()))

    def mismatches(self, other: Key) -> int:
        """Number of positions where the two keys differ."""
        if len(self) != len(other):
            raise ValueError(f"keys differ in length: {len(self)} vs {len(other)}")
        return int(np.count_nonzero(self.bits != other.bits))

    def error_rate(self, other: Key) -> float:
        """Fraction of differing positions; 0.0 for two empty keys."""
        if len(self) == 0 and len(other) == 0:
            return 0.0
        return self.mismatches(other) / len(self)

    def select(self, indices: np.ndarray) -> Key:
        """New key made of the bits at ``indices`` (an index array or boolean mask)."""
        return Key(self.bits[indices])

    def without(self, indices: np.ndarray) -> Key:
        """New key with the bits at the integer ``indices`` removed."""
        return Key(np.delete(self.bits, indices))


@dataclass(frozen=True, eq=False)
class AlicePrep:
    """Alice's random choices: the bit and the basis for each photon she sends."""

    bits: np.ndarray
    bases: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "bits", as_bit_array(self.bits, "bits"))
        object.__setattr__(self, "bases", as_bit_array(self.bases, "bases"))
        _require_same_length(bits=self.bits, bases=self.bases)

    def __len__(self) -> int:
        return int(self.bits.size)


@dataclass(frozen=True, eq=False)
class Photons:
    """Qubits in flight, in the fast-mode representation.

    Each photon is a BB84 eigenstate described by ``(bases[i], values[i])``: for
    example basis X with value 1 is |->. Intercept-resend, Pauli errors and
    depolarizing noise all keep a photon inside this set of four states (or a
    uniform mixture of them), so this representation is exact for the effects
    the project models. ``lost`` marks photons that never reach Bob's detector.
    """

    values: np.ndarray
    bases: np.ndarray
    lost: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", as_bit_array(self.values, "values"))
        object.__setattr__(self, "bases", as_bit_array(self.bases, "bases"))
        object.__setattr__(self, "lost", as_mask(self.lost, "lost"))
        _require_same_length(values=self.values, bases=self.bases, lost=self.lost)

    @classmethod
    def from_alice(cls, alice: AlicePrep) -> Photons:
        return cls(alice.bits, alice.bases, np.zeros(len(alice), dtype=bool))

    def __len__(self) -> int:
        return int(self.values.size)

    def replace(self, **changes: np.ndarray) -> Photons:
        """Copy with some fields replaced (the arrays are validated again)."""
        fields = {"values": self.values, "bases": self.bases, "lost": self.lost}
        fields.update(changes)
        return Photons(**fields)


@dataclass(frozen=True, eq=False)
class BobMeasurement:
    """Bob's basis choices, his measured bits and which photons he detected.

    ``bits[i]`` is meaningless where ``detected[i]`` is False; sifting drops those.
    """

    bases: np.ndarray
    bits: np.ndarray
    detected: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "bases", as_bit_array(self.bases, "bases"))
        object.__setattr__(self, "bits", as_bit_array(self.bits, "bits"))
        object.__setattr__(self, "detected", as_mask(self.detected, "detected"))
        _require_same_length(bases=self.bases, bits=self.bits, detected=self.detected)

    def __len__(self) -> int:
        return int(self.bits.size)
