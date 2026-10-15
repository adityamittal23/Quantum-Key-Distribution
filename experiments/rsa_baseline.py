"""Textbook RSA in pure Python, the classical key-exchange baseline for experiment 4.

For timing comparison only. It uses a seeded ``random.Random`` so runs are
reproducible, and textbook RSA has no padding, so it is not secure and must
not be used to protect data.

The security of RSA rests on factoring N = p q being hard. The cost models
below are standard analytic estimates, not measurements:

* the general number field sieve, the best known classical attack, needs about
  L_N[1/3, (64/9)^(1/3)] = exp((64/9)^(1/3) (ln N)^(1/3) (ln ln N)^(2/3))
  operations (heuristic, o(1) term dropped);
* Shor's algorithm factors N in polynomial time; Beauregard's circuit (2003)
  uses 2L + 3 logical qubits for an L-bit modulus, with O(L^3) gates.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

PUBLIC_EXPONENT = 65537
MILLER_RABIN_ROUNDS = 40
_SMALL_PRIMES = [p for p in range(3, 2000) if all(p % d for d in range(2, int(p**0.5) + 1))]


def is_probable_prime(n: int, rng: random.Random, rounds: int = MILLER_RABIN_ROUNDS) -> bool:
    """Miller-Rabin test; the error probability is at most 4^-rounds."""
    if n < 2:
        return False
    for p in [2, *_SMALL_PRIMES]:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        x = pow(rng.randrange(2, n - 1), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits: int, rng: random.Random) -> int:
    """A random prime with exactly ``bits`` bits and its top two bits set (so p q has 2 bits)."""
    if bits < 8:
        raise ValueError(f"prime size too small: {bits} bits")
    while True:
        candidate = rng.getrandbits(bits) | (0b11 << (bits - 2)) | 1
        if is_probable_prime(candidate, rng):
            return candidate


@dataclass(frozen=True)
class RSAKeyPair:
    n: int
    e: int
    d: int

    @property
    def bits(self) -> int:
        return self.n.bit_length()

    def encrypt(self, message: int) -> int:
        if not 0 <= message < self.n:
            raise ValueError("message must be in [0, n)")
        return pow(message, self.e, self.n)

    def decrypt(self, ciphertext: int) -> int:
        return pow(ciphertext, self.d, self.n)


def generate_keypair(bits: int, rng: random.Random, e: int = PUBLIC_EXPONENT) -> RSAKeyPair:
    """RSA key pair with an exactly ``bits``-bit modulus."""
    if bits % 2:
        raise ValueError("modulus size must be even")
    while True:
        p, q = random_prime(bits // 2, rng), random_prime(bits // 2, rng)
        phi = (p - 1) * (q - 1)
        if p != q and math.gcd(e, phi) == 1 and (p * q).bit_length() == bits:
            return RSAKeyPair(n=p * q, e=e, d=pow(e, -1, phi))


def gnfs_log2_operations(modulus_bits: int) -> float:
    """log2 of the heuristic GNFS work to factor an L-bit modulus (o(1) term dropped)."""
    ln_n = modulus_bits * math.log(2)
    return (64 / 9) ** (1 / 3) * ln_n ** (1 / 3) * math.log(ln_n) ** (2 / 3) / math.log(2)


def shor_logical_qubits(modulus_bits: int) -> int:
    """Logical qubits for Shor's algorithm with Beauregard's 2L + 3 circuit."""
    return 2 * modulus_bits + 3
