"""Dense every-block expansion from sparse rate_updates.

Phase 1: expand logic + tests. Full parquet CLI export polish is Phase 2;
`yield materialize` calls this locally (no per-block eth_call).
"""

from __future__ import annotations

from typing import Any, Iterator

from .rates import ray_to_apr_apy
from .store import RateStore


def expand_sparse(
    updates: list[dict[str, Any]],
    *,
    from_block: int,
    to_block: int,
) -> Iterator[dict[str, Any]]:
    """Hold each liquidity_rate constant across contiguous blocks until next update."""
    if from_block > to_block:
        raise ValueError("from_block must be <= to_block")
    if not updates:
        return

    ordered = sorted(
        updates,
        key=lambda r: (int(r["block_number"]), int(r["log_index"])),
    )

    # Build segments: each update applies from its block until (next_update_block - 1)
    for i, upd in enumerate(ordered):
        seg_start = int(upd["block_number"])
        seg_end = (
            int(ordered[i + 1]["block_number"]) - 1
            if i + 1 < len(ordered)
            else to_block
        )
        # Clip to requested range
        lo = max(seg_start, from_block)
        hi = min(seg_end, to_block)
        if lo > hi:
            continue
        ray = int(upd["liquidity_rate_ray"])
        apr, apy = ray_to_apr_apy(ray)
        for block in range(lo, hi + 1):
            yield {
                "block_number": block,
                "liquidity_rate_ray": ray,
                "supply_apr": apr,
                "supply_apy": apy,
                "as_of_event_block": seg_start,
                "source": "event_index_expand",
            }


def materialize_range(
    store: RateStore,
    *,
    chain_id: int,
    reserve: str,
    from_block: int,
    to_block: int,
) -> list[dict[str, Any]]:
    updates = store.all_updates_ordered(chain_id=chain_id, reserve=reserve)
    return list(expand_sparse(updates, from_block=from_block, to_block=to_block))
