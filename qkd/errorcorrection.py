"""Cascade error correction (Member C).

Alice and Bob hold sifted keys that differ in about a fraction Q of positions.
Cascade fixes this over the public channel using only parities:

1. Each pass shuffles the key positions (pass 1 keeps the original order) and
   cuts them into blocks. The block size starts near 0.73 / Q and doubles
   every pass.
2. Alice announces each block's parity. A block whose parity disagrees holds
   an odd number of errors, and a binary search (BINARY) finds one of them,
   revealing one sub-block parity per step.
3. Fixing a bit changes the parity of the blocks containing it in earlier
   passes. Any of those that now disagree are searched again. This cascade of
   re-checks is what gives the protocol its name.

Every parity Alice announces is public, so Eve learns it. ``leaked_bits``
counts them, and privacy amplification removes that much information.
Afterwards both parties compare a short random hash of their keys to verify
that error correction succeeded.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from qkd.key import Key
from qkd.keyrate import binary_entropy

DEFAULT_PASSES = 4
DEFAULT_VERIFY_BITS = 32
FIRST_BLOCK_FACTOR = 0.73  # k1 = 0.73 / Q, the usual Cascade choice
MIN_QBER_FOR_BLOCKS = 0.001  # floor so Q = 0 does not give infinite blocks
MIN_BLOCK = 4


@dataclass(frozen=True, eq=False)
class CascadeResult:
    alice_key: Key
    bob_key: Key  # Bob's corrected key
    leaked_bits: int  # parities announced, including the verification hash
    corrections: int  # bits Bob flipped
    passes: int
    first_block_size: int
    verified: bool  # the verification hashes matched

    def efficiency(self, qber: float) -> float:
        """f = leaked / (n h(Q)); 1.0 is the Shannon limit. NaN when undefined."""
        ideal = len(self.alice_key) * float(binary_entropy(qber))
        return self.leaked_bits / ideal if ideal > 0 else float("nan")


def first_block_size(qber: float, length: int) -> int:
    q = max(qber, MIN_QBER_FOR_BLOCKS)
    return int(min(max(length, 1), max(MIN_BLOCK, math.ceil(FIRST_BLOCK_FACTOR / q))))


class _Cascade:
    """Working state for one Cascade run. Bob's copy is the only mutable part."""

    def __init__(self, alice: np.ndarray, bob: np.ndarray) -> None:
        self.alice = alice
        self.bob = bob.copy()
        self.leaked = 0
        self.corrections = 0
        self.blocks: list[list[np.ndarray]] = []  # per pass: list of position arrays
        self.block_of: list[np.ndarray] = []  # per pass: block index of each position

    def _parities_differ(self, positions: np.ndarray) -> bool:
        return bool((self.alice[positions].sum() + self.bob[positions].sum()) % 2)

    def _binary_search(self, positions: np.ndarray) -> int:
        """Find one error in a block with odd error parity; one leaked parity per step."""
        while positions.size > 1:
            half = positions[: positions.size // 2]
            self.leaked += 1
            positions = half if self._parities_differ(half) else positions[positions.size // 2:]
        return int(positions[0])

    def _correct(self, pass_index: int, block_index: int) -> None:
        """Fix the error in a mismatched block, then cascade to earlier passes."""
        queue = deque([(pass_index, block_index)])
        while queue:
            p, b = queue.popleft()
            positions = self.blocks[p][b]
            if not self._parities_differ(positions):  # already fixed by an earlier correction
                continue
            error = self._binary_search(positions)
            self.bob[error] ^= 1
            self.corrections += 1
            # Alice's block parities are already public, so re-checking them leaks nothing.
            for q in range(len(self.blocks)):
                if q != p:
                    other = int(self.block_of[q][error])
                    if self._parities_differ(self.blocks[q][other]):
                        queue.append((q, other))

    def run_pass(self, block_size: int, order: np.ndarray) -> None:
        n = order.size
        blocks = [order[i:i + block_size] for i in range(0, n, block_size)]
        block_of = np.empty(n, dtype=np.int64)
        for b, positions in enumerate(blocks):
            block_of[positions] = b
        self.blocks.append(blocks)
        self.block_of.append(block_of)
        this_pass = len(self.blocks) - 1
        for b in range(len(blocks)):
            self.leaked += 1  # Alice announces this block's parity
            if self._parities_differ(blocks[b]):
                self._correct(this_pass, b)


def random_parity_hash(bits: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Hash = M x mod 2 for a public random binary matrix M (a universal hash family)."""
    return (matrix.astype(np.int64) @ bits.astype(np.int64)) % 2


def cascade(
    alice_key: Key,
    bob_key: Key,
    qber_estimate: float,
    rng: np.random.Generator,
    passes: int = DEFAULT_PASSES,
    verify_bits: int = DEFAULT_VERIFY_BITS,
) -> CascadeResult:
    """Correct Bob's key towards Alice's with Cascade, then verify with a hash.

    ``qber_estimate`` is the sampled QBER that both parties know, not the true
    error rate. All shuffles and the verification matrix are public randomness
    drawn from ``rng``.
    """
    if len(alice_key) != len(bob_key):
        raise ValueError(f"keys differ in length: {len(alice_key)} vs {len(bob_key)}")
    if passes < 1:
        raise ValueError(f"passes must be at least 1, got {passes}")
    if verify_bits < 0:
        raise ValueError(f"verify_bits must be non-negative, got {verify_bits}")

    n = len(alice_key)
    k1 = first_block_size(qber_estimate if np.isfinite(qber_estimate) else 0.0, n)
    state = _Cascade(alice_key.bits, bob_key.bits)
    if n:
        for p in range(passes):
            order = np.arange(n) if p == 0 else rng.permutation(n)
            state.run_pass(min(n, k1 * 2**p), order)

    matrix = rng.integers(0, 2, size=(verify_bits, n), dtype=np.uint8)
    verified = bool(np.array_equal(random_parity_hash(alice_key.bits, matrix), random_parity_hash(state.bob, matrix)))
    return CascadeResult(
        alice_key=alice_key,
        bob_key=Key(state.bob),
        leaked_bits=state.leaked + verify_bits,
        corrections=state.corrections,
        passes=passes,
        first_block_size=k1,
        verified=verified,
    )
