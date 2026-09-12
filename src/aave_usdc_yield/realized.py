"""Realized yield / wealth curve from liquidityIndex.

Thesis path: "$1 left in → $X" via index ratio, not instantaneous APY.

Pins:
- liquidityIndex is RAY-scaled (1e27); ratios cancel the scale.
- wealth(t) = index(t) / index(t0)  for $1 deposited at t0
- cumulative_return = wealth - 1
- annualized = wealth ** (SECONDS_PER_YEAR / elapsed_seconds) - 1
  when timestamps are available; else approximate with ~12s/block.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

from .rates import RAY, SECONDS_PER_YEAR

# Post-Merge Ethereum slot time used only when block_timestamp is missing.
SECONDS_PER_BLOCK_FALLBACK = 12


class RealizedYieldError(ValueError):
    """Cannot compute realized yield from available index rows."""


def index_ratio(index_from: int | str, index_to: int | str) -> float:
    """Return liquidityIndex_to / liquidityIndex_from as float."""
    a = int(index_from)
    b = int(index_to)
    if a <= 0:
        raise RealizedYieldError(f"liquidity_index_from must be > 0; got {a}")
    if b <= 0:
        raise RealizedYieldError(f"liquidity_index_to must be > 0; got {b}")
    return b / a


def cumulative_return(index_from: int | str, index_to: int | str) -> float:
    return index_ratio(index_from, index_to) - 1.0


def annualized_realized(
    wealth: float,
    *,
    elapsed_seconds: float | None = None,
    from_block: int | None = None,
    to_block: int | None = None,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> float | None:
    """Compound annualized return from wealth multiple over an elapsed span.

    Preference: timestamps → else block delta × 12s. Returns None if span ≤ 0.
    """
    if wealth <= 0:
        raise RealizedYieldError(f"wealth must be > 0; got {wealth}")

    seconds = elapsed_seconds
    if seconds is None and from_timestamp is not None and to_timestamp is not None:
        seconds = float(to_timestamp - from_timestamp)
    if seconds is None and from_block is not None and to_block is not None:
        seconds = float(to_block - from_block) * SECONDS_PER_BLOCK_FALLBACK
    if seconds is None or seconds <= 0:
        return None

    years = seconds / SECONDS_PER_YEAR
    if years <= 0:
        return None
    return wealth ** (1.0 / years) - 1.0


def _require_index(row: dict[str, Any], label: str) -> int:
    raw = row.get("liquidity_index")
    if raw is None or raw == "":
        raise RealizedYieldError(
            f"{label} row at block {row.get('block_number')} missing liquidity_index"
        )
    return int(raw)


def asof_index_row(
    updates: Sequence[dict[str, Any]], block_number: int
) -> dict[str, Any] | None:
    """Latest update with block_number <= N that has a liquidity_index."""
    best: dict[str, Any] | None = None
    for u in updates:
        bn = int(u["block_number"])
        if bn > block_number:
            break
        if u.get("liquidity_index") is None or u.get("liquidity_index") == "":
            continue
        best = u
    return best


def realized_between(
    updates: Sequence[dict[str, Any]],
    *,
    from_block: int,
    to_block: int,
) -> dict[str, Any]:
    """Compute realized wealth for $1 held from from_block → to_block (as-of)."""
    if to_block < from_block:
        raise RealizedYieldError("to_block must be >= from_block")

    ordered = sorted(
        updates,
        key=lambda r: (int(r["block_number"]), int(r["log_index"])),
    )
    start_row = asof_index_row(ordered, from_block)
    end_row = asof_index_row(ordered, to_block)
    if start_row is None:
        raise RealizedYieldError(
            f"No liquidity_index as-of from_block={from_block}"
        )
    if end_row is None:
        raise RealizedYieldError(
            f"No liquidity_index as-of to_block={to_block}"
        )

    i0 = _require_index(start_row, "from")
    i1 = _require_index(end_row, "to")
    wealth = index_ratio(i0, i1)
    cum = wealth - 1.0
    ts0 = start_row.get("block_timestamp")
    ts1 = end_row.get("block_timestamp")
    ts0_i = int(ts0) if ts0 is not None else None
    ts1_i = int(ts1) if ts1 is not None else None
    ann = annualized_realized(
        wealth,
        from_block=from_block,
        to_block=to_block,
        from_timestamp=ts0_i,
        to_timestamp=ts1_i,
    )

    return {
        "from_block": from_block,
        "to_block": to_block,
        "from_event_block": int(start_row["block_number"]),
        "to_event_block": int(end_row["block_number"]),
        "from_timestamp": ts0_i,
        "to_timestamp": ts1_i,
        "liquidity_index_from": i0,
        "liquidity_index_to": i1,
        "index_ratio": wealth,
        "wealth_of_1": wealth,
        "cumulative_return": cum,
        "annualized_realized": ann,
        "annualized_label": "compound_from_index_ratio",
        "ray": RAY,
        "source": "liquidity_index",
    }


def wealth_curve(
    updates: Sequence[dict[str, Any]],
    *,
    from_block: int | None = None,
    to_block: int | None = None,
    initial_usd: float = 1.0,
) -> list[dict[str, Any]]:
    """Sparse wealth curve at each index update from t0 onward.

    Each point: wealth of `initial_usd` left in since the first included update
    (or as-of from_block). Points are one per rate_update with an index.
    """
    ordered = sorted(
        updates,
        key=lambda r: (int(r["block_number"]), int(r["log_index"])),
    )
    indexed = [
        u
        for u in ordered
        if u.get("liquidity_index") is not None and u.get("liquidity_index") != ""
    ]
    if not indexed:
        return []

    if from_block is None:
        from_block = int(indexed[0]["block_number"])
    if to_block is None:
        to_block = int(indexed[-1]["block_number"])

    base = asof_index_row(indexed, from_block)
    if base is None:
        # First update at/after from_block becomes the deposit moment
        later = [u for u in indexed if int(u["block_number"]) >= from_block]
        if not later:
            return []
        base = later[0]
        from_block = int(base["block_number"])

    i0 = _require_index(base, "base")
    ts0 = base.get("block_timestamp")
    ts0_i = int(ts0) if ts0 is not None else None

    points: list[dict[str, Any]] = []
    for u in indexed:
        bn = int(u["block_number"])
        if bn < from_block or bn > to_block:
            continue
        ix = _require_index(u, "curve")
        wealth = initial_usd * (ix / i0)
        cum = wealth / initial_usd - 1.0
        ts = u.get("block_timestamp")
        ts_i = int(ts) if ts is not None else None
        ann = annualized_realized(
            wealth / initial_usd,
            from_block=from_block,
            to_block=bn,
            from_timestamp=ts0_i,
            to_timestamp=ts_i,
        )
        points.append(
            {
                "block_number": bn,
                "block_timestamp": ts_i,
                "log_index": int(u["log_index"]),
                "liquidity_index": ix,
                "wealth_of_1": wealth if initial_usd == 1.0 else wealth / initial_usd,
                "wealth_usd": wealth,
                "cumulative_return": cum,
                "annualized_realized": ann,
                "from_block": from_block,
                "base_liquidity_index": i0,
            }
        )
    return points


def iter_wealth_curve_csv_rows(
    points: Sequence[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Flatten points for CSV writers (stable column set)."""
    for p in points:
        yield {
            "block_number": p["block_number"],
            "block_timestamp": p.get("block_timestamp") or "",
            "log_index": p["log_index"],
            "liquidity_index": p["liquidity_index"],
            "wealth_of_1": p["wealth_of_1"],
            "cumulative_return": p["cumulative_return"],
            "annualized_realized": (
                "" if p.get("annualized_realized") is None else p["annualized_realized"]
            ),
            "from_block": p["from_block"],
            "base_liquidity_index": p["base_liquidity_index"],
        }
