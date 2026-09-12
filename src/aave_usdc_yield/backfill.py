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
    Resume-safe: continues from max(last_scanned_to_block, max event block)+1.
    Chunk size from config (default ~50); RPC shrinks further on 400-class errors.
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
            chunk_size=cfg.log_chunk_size,
            progress=progress,
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

    # Resume: prefer explicit last_scanned checkpoint (covers empty ranges),
    # else max stored event block, else start_block.
    last_event = store.max_block(cfg.usdc_address)
    last_scanned_raw = store.get_meta("last_scanned_to_block")
    last_scanned = int(last_scanned_raw) if last_scanned_raw else None
    resume_from = None
    if last_scanned is not None and last_event is not None:
        resume_from = max(last_scanned, last_event) + 1
    elif last_scanned is not None:
        resume_from = last_scanned + 1
    elif last_event is not None:
        resume_from = last_event + 1

    begin = from_block if from_block is not None else (resume_from if resume_from is not None else start)
    if begin < start:
        begin = start

    if begin > tip:
        log(f"Already up to date (begin={begin} tip={tip})")
        return {"inserted": 0, "from_block": begin, "to_block": tip, "start_block": start}

    log(f"Backfilling logs {begin} → {tip} (chunk={cfg.log_chunk_size})")
    inserted = 0
    chunks = 0
    for chunk_end, chunk in iter_reserve_data_updated_logs(
        w3,
        pool_address=cfg.pool_address,
        usdc_address=cfg.usdc_address,
        from_block=begin,
        to_block=tip,
        chunk_size=cfg.log_chunk_size,
        progress=progress,
    ):
        chunks += 1
        rows = [
            decode_reserve_data_updated(
                log_item,
                chain_id=cfg.chain_id,
                protocol=cfg.protocol,
                expected_reserve=cfg.usdc_address,
            )
            for log_item in chunk
        ]
        # Persist after every RPC chunk so resume survives mid-run failure
        n = store.upsert_rate_updates(rows)
        inserted += n
        store.set_meta("last_scanned_to_block", str(chunk_end))
        store.set_meta("last_backfill_to_block", str(chunk_end))
        if chunk:
            lo = min(r["block_number"] for r in rows)
            hi = max(r["block_number"] for r in rows)
            log(
                f"  stored {n} updates (event blocks {lo}-{hi}; "
                f"scanned→{chunk_end}); total rows≈{store.count()}"
            )
        elif chunks % 50 == 0:
            log(
                f"  …scanned through {chunk_end} (chunk #{chunks}, no USDC events); "
                f"total rows≈{store.count()}"
            )

    store.set_meta("last_backfill_to_block", str(tip))
    store.set_meta("last_scanned_to_block", str(tip))
    return {
        "inserted": inserted,
        "from_block": begin,
        "to_block": tip,
        "start_block": start,
        "total_rows": store.count(),
        "chunks": chunks,
    }
