"""Traceable experiment output.

Every experiment CSV starts with one comment line holding JSON metadata
(experiment name, master seed, all parameters, library versions and time), then
a normal CSV table. Each row also carries a ``seed`` column, so any plotted
number can be traced to the exact run that produced it::

    # {"experiment": "exp1_eavesdropping", "seed": 42, "params": {...}, ...}
    intercept_fraction,qber,...,seed
"""

from __future__ import annotations

import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import qiskit
import qiskit_aer

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
_COMMENT = "#"


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def write_results_csv(
    df: pd.DataFrame,
    name: str,
    seed: int,
    params: dict[str, Any],
    results_dir: Path | str = RESULTS_DIR,
) -> Path:
    """Write ``df`` to ``results_dir/<name>.csv`` with a metadata header line.

    A ``seed`` column filled with ``seed`` is added if ``df`` has none. Returns
    the path written.
    """
    if not _SAFE_NAME.match(name):
        raise ValueError(f"result name must be letters, digits, '_' or '-': {name!r}")
    if df.empty:
        raise ValueError("refusing to write an empty result table")

    table = df if "seed" in df.columns else df.assign(seed=seed)
    metadata = {
        "experiment": name,
        "seed": seed,
        "params": params,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
        },
        "versions": {
            "python": platform.python_version(),
            "qiskit": qiskit.__version__,
            "qiskit_aer": qiskit_aer.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    out_dir = Path(results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"{_COMMENT} {json.dumps(metadata, default=_json_default, sort_keys=True)}\n")
        table.to_csv(fh, index=False)
    return path


def read_results_csv(path: Path | str) -> tuple[dict[str, Any], pd.DataFrame]:
    """Return ``(metadata, table)`` for a file written by ``write_results_csv``."""
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        first = fh.readline()
    if not first.startswith(_COMMENT):
        raise ValueError(f"{path} has no metadata header line")
    metadata = json.loads(first[len(_COMMENT):].strip())
    table = pd.read_csv(path, skiprows=1)
    return metadata, table
