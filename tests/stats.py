"""Statistical tolerances shared by the tests."""

import numpy as np

SIGMAS = 4.5  # roughly a 1-in-150000 false-failure rate per check


def binomial_tolerance(p: float, n: int) -> float:
    """SIGMAS standard errors of a proportion p estimated from n trials (floor for p=0)."""
    return SIGMAS * np.sqrt(max(p * (1 - p), 1e-4) / max(n, 1))


def agree(q1: float, n1: int, q2: float, n2: int) -> bool:
    """Two independent proportion estimates agree within SIGMAS combined standard errors."""
    p = (q1 * n1 + q2 * n2) / (n1 + n2)
    se = np.sqrt(max(p * (1 - p), 1e-4) * (1 / n1 + 1 / n2))
    return abs(q1 - q2) <= SIGMAS * se
