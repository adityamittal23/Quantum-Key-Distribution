"""Shared helpers for the experiment scripts.

Each experiment module exposes:

* a frozen ``Config`` dataclass with ``FULL`` and ``QUICK`` instances;
* ``run(config, seed) -> DataFrame``, one row per simulation run, each row
  carrying its own seed;
* ``plot(table) -> Figure``, built only from the CSV table, so every plotted
  number can be traced to a row;
* ``main()`` for ``python -m experiments.<name> [--quick] [--seed N]``.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from qkd.results_io import RESULTS_DIR, read_results_csv, write_results_csv

DEFAULT_SEED = 2026
PNG_WIDTH = 1400  # report-figure size in CSS pixels; PNG_SCALE doubles it for print
PNG_SCALE = 2

# Reference palette (dataviz skill, light mode), used by role.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # slots 1 to 3, in fixed order
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def run_seed(master_seed: int, index: int) -> int:
    """Seed of the ``index``-th run of an experiment: master * 100000 + index (readable)."""
    return master_seed * 100_000 + index


def style_figure(fig: go.Figure, title: str) -> go.Figure:
    """Recessive grid and axes, system font, hover on every mark."""
    fig.update_layout(
        title={"text": title, "font": {"size": 18, "color": INK}, "x": 0.01},
        font={"family": FONT, "size": 13, "color": INK_SECONDARY},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        hovermode="closest",
        legend={"orientation": "h", "y": -0.18, "x": 0},
        margin={"l": 70, "r": 30, "t": 80, "b": 90},
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="outside", tickcolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, ticks="outside", tickcolor=AXIS)
    return fig


# Visual convention shared by every experiment figure:
#   markers with 95% error bars = simulation (fast mode), coloured by series slot;
#   dark hollow diamonds        = Qiskit-mode validation runs;
#   dashed lines                = analytic prediction (muted ink, or the series colour it predicts).


def simulated_trace(stats: pd.DataFrame, x: str, name: str, color: str, hover: str, **kwargs) -> go.Scatter:
    """Fast-mode means with 95% intervals, from ``mean_and_interval`` output."""
    return go.Scatter(
        x=stats[x], y=stats["mean"], mode="markers", name=name,
        error_y={"type": "data", "array": stats["half_width"], "color": color, "thickness": 1.5, "width": 0},
        marker={"color": color, "size": 8, "line": {"color": SURFACE, "width": 1}},
        hovertemplate=hover + "<extra>" + name + "</extra>", **kwargs)


def qiskit_trace(stats: pd.DataFrame, x: str, name: str, hover: str, **kwargs) -> go.Scatter:
    """Qiskit-mode validation means, drawn so they never compete with a series colour."""
    return go.Scatter(
        x=stats[x], y=stats["mean"], mode="markers", name=name,
        marker={"color": SURFACE, "size": 11, "symbol": "diamond", "line": {"color": INK, "width": 2}},
        hovertemplate=hover + "<extra>" + name + "</extra>", **kwargs)


def analytic_trace(x, y, name: str, color: str = INK_MUTED, **kwargs) -> go.Scatter:
    return go.Scatter(x=x, y=y, mode="lines", name=name, line={"color": color, "width": 2, "dash": "dash"},
                      hoverinfo="skip", **kwargs)


def mean_and_interval(table: pd.DataFrame, by: list[str], column: str) -> pd.DataFrame:
    """Mean and 95% normal interval of ``column`` over the trials of each group."""
    grouped = table.groupby(by, sort=True)[column]
    out = grouped.agg(mean="mean", std="std", trials="count").reset_index()
    out["half_width"] = 1.96 * out["std"].fillna(0.0) / np.sqrt(out["trials"])
    return out


def config_params(config: Any) -> dict[str, Any]:
    return dataclasses.asdict(config)


def cli(
    name: str,
    run: Callable[[Any, int], pd.DataFrame],
    plot: Callable[[pd.DataFrame], go.Figure],
    full: Any,
    quick: Any,
    argv: list[str] | None = None,
    results_dir: Path = RESULTS_DIR,
) -> tuple[Path, Path]:
    """Parse arguments, run the experiment, write ``<name>.csv``, ``.html`` and ``.png``."""
    parser = argparse.ArgumentParser(description=f"Run {name} and write its CSV and plot to results/.")
    parser.add_argument("--quick", action="store_true", help="small sweep for a fast check")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="master seed")
    parser.add_argument("--plot-only", action="store_true", help="re-plot the existing CSV")
    args = parser.parse_args(argv)
    return execute(name, run, plot, quick if args.quick else full, args.seed, results_dir, args.plot_only)


def execute(
    name: str,
    run: Callable[[Any, int], pd.DataFrame],
    plot: Callable[[pd.DataFrame], go.Figure],
    config: Any,
    seed: int,
    results_dir: Path = RESULTS_DIR,
    plot_only: bool = False,
    write_png: bool = True,
) -> tuple[Path, Path]:
    csv_path = Path(results_dir) / f"{name}.csv"
    if not plot_only:
        table = run(config, seed)
        csv_path = write_results_csv(table, name, seed, config_params(config), results_dir)
        print(f"wrote {csv_path} ({len(table)} rows)")
    _, table = read_results_csv(csv_path)  # plot from the file, not from memory
    figure = plot(table)
    html_path = Path(results_dir) / f"{name}.html"
    figure.write_html(html_path, include_plotlyjs="cdn")
    print(f"wrote {html_path}")
    if write_png:
        png_path = html_path.with_suffix(".png")
        figure.write_image(png_path, width=PNG_WIDTH, height=figure.layout.height or 560, scale=PNG_SCALE)
        print(f"wrote {png_path}")
    return csv_path, html_path
