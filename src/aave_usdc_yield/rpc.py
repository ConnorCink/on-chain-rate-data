"""Ethereum RPC helpers for log backfill (archive-capable)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from web3 import Web3

from .decode import RESERVE_DATA_UPDATED_TOPIC, reserve_topic

ABI_PATH = Path(__file__).parent / "abi" / "pool.json"

# Providers often reject large eth_getLogs ranges with HTTP 400 / -32005 / etc.
DEFAULT_LOG_CHUNK = 50
MIN_LOG_CHUNK = 1


def make_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 120}))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to RPC at {rpc_url!r}")
    return w3


def load_pool_abi() -> list[dict[str, Any]]:
    with ABI_PATH.open() as f:
        return json.load(f)


def _error_text(exc: BaseException) -> str:
    parts = [str(exc), repr(exc)]
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None:
        parts.append(str(cause))
    # web3 sometimes nests provider response
    args = getattr(exc, "args", ())
    for a in args:
        parts.append(str(a))
    return " ".join(parts).lower()


def is_retriable_log_range_error(exc: BaseException) -> bool:
    """True when shrinking eth_getLogs block range is a reasonable retry."""
    text = _error_text(exc)
    needles = (
        "400",
        "413",
        "429",
        "timeout",
        "timed out",
        "too many",
        "block range",
        "query returned more",
        "response size",
        "limit exceeded",
        "rate limit",
        "-32005",
        "-32602",
        "server error",
        "temporary",
        "try again",
        "pruned",
        "history",
    )
    return any(n in text for n in needles)


def iter_reserve_data_updated_logs(
    w3: Web3,
    *,
    pool_address: str,
    usdc_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int = DEFAULT_LOG_CHUNK,
    min_chunk_size: int = MIN_LOG_CHUNK,
    progress: Callable[[str], None] | None = None,
    max_retries_per_chunk: int = 8,
) -> Iterator[tuple[int, list[dict[str, Any]]]]:
    """Yield chunks of raw logs for USDC ReserveDataUpdated on the Pool.

    Resilient: on RPC range/size/400-class errors, shrink chunk (halve, floor
    at min_chunk_size) and retry the same start block. Resume-safe callers
    should persist after each successful chunk.
    """
    pool = Web3.to_checksum_address(pool_address)
    topics = [
        "0x" + RESERVE_DATA_UPDATED_TOPIC.hex(),
        reserve_topic(usdc_address),
    ]
    tip = to_block
    start = from_block
    current = max(min_chunk_size, int(chunk_size))
    # Remember the configured preferred size so we can gently grow after success
    preferred = current

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    while start <= tip:
        end = min(start + current - 1, tip)
        attempt = 0
        while True:
            attempt += 1
            try:
                logs = w3.eth.get_logs(
                    {
                        "address": pool,
                        "fromBlock": start,
                        "toBlock": end,
                        "topics": topics,
                    }
                )
                normalized: list[dict[str, Any]] = [
                    _normalize_log(log) for log in logs
                ]
                # Yield (chunk_end_block, logs) so callers can checkpoint empty ranges
                yield end, normalized
                start = end + 1
                # Mild growth toward preferred after success
                if current < preferred:
                    current = min(preferred, max(current + 1, current * 2))
                break
            except Exception as exc:  # noqa: BLE001 — provider errors vary widely
                if (
                    current > min_chunk_size
                    and is_retriable_log_range_error(exc)
                ):
                    new_size = max(min_chunk_size, current // 2)
                    log(
                        f"  RPC error on blocks {start}-{end} "
                        f"(chunk={current}); shrinking to {new_size} and retrying"
                    )
                    current = new_size
                    end = min(start + current - 1, tip)
                    continue
                if (
                    is_retriable_log_range_error(exc)
                    and attempt < max_retries_per_chunk
                    and current <= min_chunk_size
                ):
                    sleep_s = min(2 ** (attempt - 1), 30)
                    log(
                        f"  RPC error on blocks {start}-{end} at min chunk; "
                        f"sleep {sleep_s}s and retry ({attempt}/{max_retries_per_chunk})"
                    )
                    time.sleep(sleep_s)
                    continue
                raise


def _normalize_log(log: Any) -> dict[str, Any]:
    def _hex(v: Any) -> Any:
        if hasattr(v, "hex") and not isinstance(v, str):
            h = v.hex()
            return h if h.startswith("0x") else "0x" + h
        return v

    return {
        "address": _hex(log["address"]),
        "topics": [_hex(t) for t in log["topics"]],
        "data": _hex(log["data"]),
        "blockNumber": int(log["blockNumber"]),
        "transactionHash": _hex(log["transactionHash"]),
        "logIndex": int(log["logIndex"]),
        "transactionIndex": int(log.get("transactionIndex", 0)),
    }


def discover_first_usdc_update_block(
    w3: Web3,
    *,
    pool_address: str,
    usdc_address: str,
    search_from: int,
    search_to: int | None = None,
    chunk_size: int = 50,
    progress: Callable[[str], None] | None = None,
) -> int | None:
    """Scan forward from search_from for the first USDC ReserveDataUpdated block.

    Returns the block number of the first matching log, or None if none found.
    """
    tip = w3.eth.block_number if search_to is None else search_to
    for _end, chunk in iter_reserve_data_updated_logs(
        w3,
        pool_address=pool_address,
        usdc_address=usdc_address,
        from_block=search_from,
        to_block=tip,
        chunk_size=chunk_size,
        progress=progress,
    ):
        if chunk:
            return min(int(l["blockNumber"]) for l in chunk)
    return None
