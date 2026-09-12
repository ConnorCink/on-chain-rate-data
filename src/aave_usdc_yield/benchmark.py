"""Thin SOFR / benchmark compare scaffolding.

Import a CSV of daily (or irregular) benchmark rates and align against a
realized wealth-curve window. This is scaffolding for Connor's thesis — not a
full FRED client.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class BenchmarkPoint:
    date: str  # YYYY-MM-DD
    rate: float  # decimal APR, e.g. 0.0532 = 5.32%


def load_benchmark_csv(
    path: Path | str,
    *,
    date_col: str = "date",
    rate_col: str = "rate",
    rate_is_percent: bool = False,
) -> list[BenchmarkPoint]:
    """Load benchmark rates from CSV.

    Expected columns (configurable): date (YYYY-MM-DD), rate (decimal or percent).
    """
    p = Path(path)
    points: list[BenchmarkPoint] = []
    with p.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"empty CSV: {p}")
        for row in reader:
            if date_col not in row or rate_col not in row:
                raise ValueError(
                    f"CSV must have columns {date_col!r} and {rate_col!r}; "
                    f"got {reader.fieldnames}"
                )
            raw = row[rate_col].strip()
            if raw == "":
                continue
            rate = float(raw)
            if rate_is_percent:
                rate = rate / 100.0
            points.append(BenchmarkPoint(date=row[date_col].strip(), rate=rate))
    return points


def _ts_to_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def average_benchmark_apr(
    points: Sequence[BenchmarkPoint],
    *,
    from_timestamp: int | None,
    to_timestamp: int | None,
) -> float | None:
    """Simple arithmetic average of benchmark APR over [from, to] by date."""
    if not points:
        return None
    if from_timestamp is None or to_timestamp is None:
        # No time window — average all imported points
        return sum(p.rate for p in points) / len(points)

    d0 = _ts_to_date(from_timestamp)
    d1 = _ts_to_date(to_timestamp)
    window = [p for p in points if d0 <= p.date <= d1]
    if not window:
        return None
    return sum(p.rate for p in window) / len(window)


def compare_realized_to_benchmark(
    realized: dict[str, Any],
    benchmark_points: Sequence[BenchmarkPoint],
) -> dict[str, Any]:
    """Scaffolding: juxtapose annualized realized vs average SOFR-like APR."""
    bench = average_benchmark_apr(
        benchmark_points,
        from_timestamp=realized.get("from_timestamp"),
        to_timestamp=realized.get("to_timestamp"),
    )
    ann = realized.get("annualized_realized")
    spread = None if ann is None or bench is None else float(ann) - float(bench)
    return {
        "realized_cumulative_return": realized.get("cumulative_return"),
        "realized_annualized": ann,
        "benchmark_avg_apr": bench,
        "spread_annualized_minus_benchmark": spread,
        "from_block": realized.get("from_block"),
        "to_block": realized.get("to_block"),
        "from_timestamp": realized.get("from_timestamp"),
        "to_timestamp": realized.get("to_timestamp"),
        "benchmark_points_used_hint": (
            "date-filtered average when timestamps present; else all rows"
        ),
        "note": (
            "SOFR is typically quoted as APR (simple); realized annualized is "
            "compound from liquidityIndex ratio — spread is indicative only."
        ),
    }
