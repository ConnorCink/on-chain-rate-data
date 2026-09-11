"""Ethereum RPC helpers for log backfill (archive-capable)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from web3 import Web3

from .decode import RESERVE_DATA_UPDATED_TOPIC, reserve_topic

ABI_PATH = Path(__file__).parent / "abi" / "pool.json"


def make_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 120}))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to RPC at {rpc_url!r}")
    return w3


def load_pool_abi() -> list[dict[str, Any]]:
    with ABI_PATH.open() as f:
        return json.load(f)


def iter_reserve_data_updated_logs(
    w3: Web3,
    *,
    pool_address: str,
    usdc_address: str,
    from_block: int,
    to_block: int,
    chunk_size: int = 10_000,
) -> Iterator[list[dict[str, Any]]]:
    """Yield chunks of raw logs for USDC ReserveDataUpdated on the Pool."""
    pool = Web3.to_checksum_address(pool_address)
    topics = [
        "0x" + RESERVE_DATA_UPDATED_TOPIC.hex(),
        reserve_topic(usdc_address),
    ]
    tip = to_block
    start = from_block
    while start <= tip:
        end = min(start + chunk_size - 1, tip)
        logs = w3.eth.get_logs(
            {
                "address": pool,
                "fromBlock": start,
                "toBlock": end,
                "topics": topics,
            }
        )
        # Normalize AttributeDict / HexBytes to plain dicts for decode
        normalized: list[dict[str, Any]] = []
        for log in logs:
            normalized.append(_normalize_log(log))
        yield normalized
        start = end + 1


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
    chunk_size: int = 50_000,
) -> int | None:
    """Scan forward from search_from for the first USDC ReserveDataUpdated block.

    Returns the block number of the first matching log, or None if none found.
    """
    tip = w3.eth.block_number if search_to is None else search_to
    for chunk in iter_reserve_data_updated_logs(
        w3,
        pool_address=pool_address,
        usdc_address=usdc_address,
        from_block=search_from,
        to_block=tip,
        chunk_size=chunk_size,
    ):
        if chunk:
            return min(int(l["blockNumber"]) for l in chunk)
    return None
