"""Point query: latest USDC ReserveDataUpdated with block_number <= N."""

from __future__ import annotations

from typing import Any

from .config import AppConfig
from .rates import ray_to_apr_apy
from .store import RateStore


class BeforeStartBlockError(ValueError):
    """Query block is before the empirical USDC inception start_block."""


class NoRateDataError(ValueError):
    """No rate_updates available for the query (empty DB or before first event)."""


def resolve_start_block(cfg: AppConfig, store: RateStore) -> int | None:
    """Prefer config pin, else meta from discovery/backfill, else min stored block."""
    if cfg.start_block is not None:
        return cfg.start_block
    meta = store.get_start_block()
    if meta is not None:
        return meta
    return store.min_block(cfg.usdc_address)


def yield_at(cfg: AppConfig, store: RateStore, block_number: int) -> dict[str, Any]:
    """As-of join for instantaneous USDC supply yield at block N."""
    if block_number < 0:
        raise ValueError("block_number must be >= 0")

    start = resolve_start_block(cfg, store)
    if start is not None and block_number < start:
        raise BeforeStartBlockError(
            f"block {block_number} is before USDC start_block {start}. "
            "Rate state is not defined for queries before the first empirical "
            "USDC ReserveDataUpdated."
        )

    row = store.asof_row(
        chain_id=cfg.chain_id,
        reserve=cfg.usdc_address,
        block_number=block_number,
    )
    if row is None:
        raise NoRateDataError(
            f"No USDC rate_updates with block_number <= {block_number}. "
            "Run `yield backfill` first (requires ETH_ARCHIVE_RPC_URL)."
        )

    ray = int(row["liquidity_rate_ray"])
    apr, apy = ray_to_apr_apy(ray)

    return {
        "block_number": block_number,
        "block_timestamp": row.get("block_timestamp"),
        "liquidity_rate_ray": ray,
        "supply_apr": apr,
        "supply_apy": apy,
        "supply_apy_label": "continuous_compound_from_apr_aave_utilities",
        "as_of_event_block": int(row["block_number"]),
        "as_of_tx_hash": row["tx_hash"],
        "as_of_log_index": int(row["log_index"]),
        "source": "event_index",
        "reserve": row["reserve"],
        "chain_id": int(row["chain_id"]),
        "protocol": row["protocol"],
    }
