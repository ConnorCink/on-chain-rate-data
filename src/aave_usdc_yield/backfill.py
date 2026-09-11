"""Backfill USDC ReserveDataUpdated logs into SQLite."""

from __future__ import annotations

from typing import Callable

from .config import AppConfig
from .decode import decode_reserve_data_updated
from .rpc import discover_first_usdc_update_block, iter_reserve_data_updated_logs, make_web3
from .store import RateStore

# Aave V3 Ethereum Pool creation is around this era; used only as a search floor
# for empirical start_block discovery (not a guessed pin).
AAVE_V3_ETH_SEARCH_FLOOR = 16_200_000


def backfill(
    cfg: AppConfig,
    store: RateStore,
    *,
    to_block: int | None = None,
    from_block: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Chunked eth_getLogs backfill filtered to USDC.

    Discovers empirical start_block on first run if not already pinned/stored.
    """
    def log(msg: str) -> None:
        if progress:
            progress(msg)

    rpc = cfg.require_rpc_url()
    w3 = make_web3(rpc)
    tip = w3.eth.block_number if to_block is None else to_block

    start = store.get_start_block() or cfg.start_block
    if start is None:
        log(f"Discovering first USDC ReserveDataUpdated from block {AAVE_V3_ETH_SEARCH_FLOOR}…")
        found = discover_first_usdc_update_block(
            w3,
            pool_address=cfg.pool_address,
            usdc_address=cfg.usdc_address,
            search_from=AAVE_V3_ETH_SEARCH_FLOOR,
            search_to=tip,
            chunk_size=max(cfg.log_chunk_size, 20_000),
        )
        if found is None:
            raise RuntimeError(
                "No USDC ReserveDataUpdated found on pool; cannot set start_block."
            )
        store.set_start_block(found)
        start = found
        log(f"Empirical start_block = {start}")
    else:
        store.set_start_block(start)
        log(f"Using start_block = {start}")

    # Resume from last stored block if present
    last = store.max_block(cfg.usdc_address)
    begin = from_block if from_block is not None else (last + 1 if last is not None else start)
    if begin < start:
        begin = start

    if begin > tip:
        log(f"Already up to date (begin={begin} tip={tip})")
        return {"inserted": 0, "from_block": begin, "to_block": tip, "start_block": start}

    log(f"Backfilling logs {begin} → {tip} (chunk={cfg.log_chunk_size})")
    inserted = 0
    for chunk in iter_reserve_data_updated_logs(
        w3,
        pool_address=cfg.pool_address,
        usdc_address=cfg.usdc_address,
        from_block=begin,
        to_block=tip,
        chunk_size=cfg.log_chunk_size,
    ):
        rows = [
            decode_reserve_data_updated(
                log_item,
                chain_id=cfg.chain_id,
                protocol=cfg.protocol,
                expected_reserve=cfg.usdc_address,
            )
            for log_item in chunk
        ]
        n = store.upsert_rate_updates(rows)
        inserted += n
        if chunk:
            lo = min(r["block_number"] for r in rows)
            hi = max(r["block_number"] for r in rows)
            log(f"  stored {n} updates (blocks {lo}-{hi}); total rows≈{store.count()}")

    store.set_meta("last_backfill_to_block", str(tip))
    return {
        "inserted": inserted,
        "from_block": begin,
        "to_block": tip,
        "start_block": start,
        "total_rows": store.count(),
    }
