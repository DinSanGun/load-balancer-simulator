"""
Read a benchmark_summary*.json file and write simple comparison charts (PNG).

Uses matplotlib with a non-interactive backend so it runs headless from the CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

# Matplotlib needs a writable config/cache dir; default ~/.config may be unavailable in some environments.
_repo_root = Path(__file__).resolve().parents[1]
_mpl_dir = _repo_root / ".mplconfig"
_mpl_dir.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


# Consistent colors for the three strategies (bars + legends).
STRATEGY_COLORS = ["#4477AA", "#EE6677", "#228833"]
BACKEND_COLORS = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#AA3377"]


def _format_strategy_label(key: str) -> str:
    return key.replace("_", " ").title()


def _title_prefix(data: dict[str, object]) -> str:
    name = data.get("scenario_name")
    if name:
        return f"Scenario: {name}"
    return "Benchmark (no named scenario)"


def _strategy_rows(data: dict[str, object]) -> list[dict[str, object]]:
    rows = data.get("strategies")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _total_overload_rejections(data: dict[str, object]) -> int:
    return sum(int(r.get("overload_rejected_requests") or 0) for r in _strategy_rows(data))


def _has_overload_metrics(data: dict[str, object]) -> bool:
    return _total_overload_rejections(data) > 0


def _subtitle_meta(data: dict[str, object]) -> str:
    parts: list[str] = []
    bp = data.get("benchmark_parameters")
    if isinstance(bp, dict):
        tr = bp.get("total_requests_per_run")
        conc = bp.get("concurrency")
        lb_cap = bp.get("load_balancer_max_in_flight")
        if tr is not None:
            parts.append(f"requests/run={tr}")
        if conc is not None:
            parts.append(f"concurrency={conc}")
        if lb_cap is not None:
            parts.append(f"LB_MAX_IN_FLIGHT={lb_cap}")
    tot_ol = _total_overload_rejections(data)
    if tot_ol > 0:
        parts.append(f"total HTTP 503 overload={tot_ol}")
    gen = data.get("generated_at")
    if gen:
        parts.append(str(gen))
    return " · ".join(parts) if parts else ""


def _format_backend_legend_label(key: str) -> str:
    if key == "__overload_503__":
        return "Overload 503 (LB)"
    return key


def load_benchmark_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "strategies" not in raw or not isinstance(raw["strategies"], list):
        raise ValueError(f"Not a benchmark summary file (missing 'strategies'): {path}")
    return raw


def _apply_figure_titles(fig, data: dict[str, object], chart_heading: str) -> None:
    """
    Place title in figure coordinates so lines do not overlap:
    line 1 — scenario / benchmark label
    line 2 — chart-specific heading
    line 3 — metadata (grey), separate from the lines above
    """
    sub = _subtitle_meta(data)
    # Figure coordinates (0–1). Separate lines so scenario, heading, and metadata never overlap.
    fig.text(0.5, 0.99, _title_prefix(data), ha="center", va="top", fontsize=12, transform=fig.transFigure)
    fig.text(0.5, 0.935, chart_heading, ha="center", va="top", fontsize=11, transform=fig.transFigure)
    if sub:
        fig.text(0.5, 0.88, sub, ha="center", va="top", fontsize=9, color="0.4", transform=fig.transFigure)


def _pad_inside_axes_top(ax) -> None:
    """
    Add empty space *inside* the axes above the data so bars (and value labels) do not sit on the top spine.

    Call after bars and bar_label so limits reflect drawn content.
    """
    ymin, ymax = ax.get_ylim()
    if ymax <= ymin:
        return
    span = ymax - ymin
    # Relative headroom; small floor so tiny values still get a visible gap
    extra = max(span * 0.14, 0.02 * max(abs(ymax), 1.0))
    ax.set_ylim(ymin, ymax + extra)


def _add_legend_below_axes(ax, title: str | None, entries: list[tuple[str, str]]) -> None:
    """
    Legend entirely *below* the axes so it never covers bars.

    `entries`: list of (label, facecolor hex).
    """
    if not entries:
        return
    handles = [
        Patch(facecolor=color, edgecolor="0.35", linewidth=0.6) for _, color in entries
    ]
    labels = [name for name, _ in entries]
    ax.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=min(len(entries), 4),
        frameon=True,
        fontsize=9,
        title=title,
        title_fontsize=10,
    )


def _finalize_bar_figure(fig, ax, *, right: float = 0.95, bottom: float = 0.15) -> None:
    """Tight layout under titles + room inside the plot area above the tallest bars."""
    _pad_inside_axes_top(ax)
    fig.subplots_adjust(left=0.1, right=right, top=0.78, bottom=bottom)


def plot_average_response_time(data: dict[str, object], out_path: Path) -> None:
    rows = data["strategies"]
    labels = [_format_strategy_label(str(r["strategy"])) for r in rows]
    values = [float(r["average_response_time_ms"]) for r in rows]

    colors = STRATEGY_COLORS[: len(labels)]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("Average response time (ms)")
    _apply_figure_titles(fig, data, "Average response time by strategy")
    ax.bar_label(bars, fmt="%.1f", padding=4)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    _add_legend_below_axes(ax, "Strategy", list(zip(labels, colors)))
    _finalize_bar_figure(fig, ax, bottom=0.30)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)


def plot_average_throughput(data: dict[str, object], out_path: Path) -> None:
    rows = data["strategies"]
    labels = [_format_strategy_label(str(r["strategy"])) for r in rows]
    values = [float(r["average_throughput_rps"]) for r in rows]

    colors = STRATEGY_COLORS[: len(labels)]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    bars = ax.bar(labels, values, color=colors)
    if _has_overload_metrics(data):
        ax.set_ylabel("Offered load (req/s)")
        thr_title = "Offered load by strategy (includes rejected requests)"
    else:
        ax.set_ylabel("Average throughput (req/s)")
        thr_title = "Average throughput by strategy"
    _apply_figure_titles(fig, data, thr_title)
    ax.bar_label(bars, fmt="%.2f", padding=4)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    _add_legend_below_axes(ax, "Strategy", list(zip(labels, colors)))
    _finalize_bar_figure(fig, ax, bottom=0.30)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)


def plot_overload_rejections(data: dict[str, object], out_path: Path) -> None:
    """Bar chart of fail-fast 503 overload rejections per strategy (only meaningful when totals > 0)."""
    rows = data["strategies"]
    labels = [_format_strategy_label(str(r["strategy"])) for r in rows]
    values = [int(r.get("overload_rejected_requests") or 0) for r in rows]

    colors = STRATEGY_COLORS[: len(labels)]
    fig, ax = plt.subplots(figsize=(8, 6.2))
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("Overload rejections (count)")
    _apply_figure_titles(
        fig,
        data,
        "HTTP 503 overload rejections by strategy (fail-fast backpressure)",
    )
    ax.bar_label(bars, fmt="%d", padding=4)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    _add_legend_below_axes(ax, "Strategy", list(zip(labels, colors)))
    _finalize_bar_figure(fig, ax, bottom=0.30)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)


def plot_backend_distribution(data: dict[str, object], out_path: Path) -> None:
    rows = data["strategies"]
    strategy_labels = [_format_strategy_label(str(r["strategy"])) for r in rows]

    backend_sets = [set(str(k) for k in r["requests_per_backend"].keys()) for r in rows]
    all_backends = sorted(set().union(*backend_sets)) if backend_sets else []
    if not all_backends:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "No per-backend data", ha="center", va="center")
        _apply_figure_titles(fig, data, "Requests per backend by strategy")
        fig.subplots_adjust(top=0.78, bottom=0.12)
        fig.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0.35)
        plt.close(fig)
        return

    n_strat = len(strategy_labels)
    n_back = len(all_backends)
    x_positions = list(range(n_strat))
    width = min(0.8 / max(n_back, 1), 0.25)

    fig, ax = plt.subplots(figsize=(9, 6.2))
    colors = [BACKEND_COLORS[i % len(BACKEND_COLORS)] for i in range(len(all_backends))]
    bars_list = []
    for i, backend in enumerate(all_backends):
        heights = [int(r["requests_per_backend"].get(backend, 0)) for r in rows]
        offset = width * (i - (n_back - 1) / 2)
        bar_x = [xp + offset for xp in x_positions]
        c = ax.bar(bar_x, heights, width, color=colors[i])
        bars_list.append(c)

    ax.set_ylabel("Request count")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(strategy_labels, rotation=0, ha="center")
    _apply_figure_titles(fig, data, "Requests per backend by strategy")
    legend_entries = [(_format_backend_legend_label(backend), colors[i]) for i, backend in enumerate(all_backends)]
    _add_legend_below_axes(ax, "Backend", legend_entries)
    for c in bars_list:
        ax.bar_label(c, padding=3, fontsize=8)
    _finalize_bar_figure(fig, ax, bottom=0.30)
    fig.savefig(out_path, dpi=120, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)


def _safe_stem(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem)
    return stem or "benchmark"


def run_visualization(input_path: Path, output_dir: Path) -> list[Path]:
    data = load_benchmark_json(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = _safe_stem(input_path)

    paths = [
        output_dir / f"{prefix}_response_time.png",
        output_dir / f"{prefix}_throughput.png",
        output_dir / f"{prefix}_backend_distribution.png",
    ]

    plot_average_response_time(data, paths[0])
    plot_average_throughput(data, paths[1])
    plot_backend_distribution(data, paths[2])

    if _has_overload_metrics(data):
        ol_path = output_dir / f"{prefix}_overload_503.png"
        plot_overload_rejections(data, ol_path)
        paths.append(ol_path)

    return paths


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visualize benchmark_summary JSON as PNG charts")
    p.add_argument(
        "input",
        type=Path,
        help="Path to results/benchmark_summary_*.json",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("charts"),
        help="Directory for PNG files (default: charts/)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"File not found: {args.input}")

    written = run_visualization(args.input, args.output_dir)
    print("Wrote:")
    for w in written:
        print(f"  {w}")


if __name__ == "__main__":
    main()
