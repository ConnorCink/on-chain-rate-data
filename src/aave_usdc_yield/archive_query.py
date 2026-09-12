"""Optional archive RPC helpers: date→block binary search + getReserveData eth_call.

Used when the event-index DB lacks coverage. Never log RPC URLs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from web3 import Web3

from .rates import ray_to_apr_apy
from .rpc import load_pool_abi, make_web3


def date_to_utc_midnight_ts(d: date) -> int:
    """UTC midnight for a calendar date (UI date pickers are date-only)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def block_at_or_before_timestamp(w3: Web3, target_ts: int) -> int:
    """Binary search for the latest block with timestamp <= target_ts."""
    if target_ts < 0:
        raise ValueError("target_ts must be >= 0")
    tip = int(w3.eth.block_number)
    tip_ts = int(w3.eth.get_block(tip)["timestamp"])
    if target_ts >= tip_ts:
        return tip
    genesis_ts = int(w3.eth.get_block(0)["timestamp"])
    if target_ts < genesis_ts:
        raise ValueError(
            f"timestamp {target_ts} is before genesis block timestamp {genesis_ts}"
        )

    lo, hi = 0, tip
    while lo < hi:
        mid = (lo + hi + 1) // 2
        ts = int(w3.eth.get_block(mid)["timestamp"])
        if ts <= target_ts:
            lo = mid
        else:
            hi = mid - 1
    return lo


def resolve_block(
    w3: Web3 | None,
    *,
    block_number: int | None = None,
    as_of_date: date | None = None,
) -> int:
    """Resolve UI input to a block. Date path requires w3."""
    if block_number is not None and as_of_date is not None:
        raise ValueError("Provide block_number OR as_of_date, not both")
    if block_number is not None:
        if block_number < 0:
            raise ValueError("block_number must be >= 0")
        return int(block_number)
    if as_of_date is None:
        raise ValueError("Need block_number or as_of_date")
    if w3 is None:
        raise RuntimeError(
            "Date→block requires ETH_ARCHIVE_RPC_URL (archive RPC). "
            "Enter a block number instead, or set the env var."
        )
    return block_at_or_before_timestamp(w3, date_to_utc_midnight_ts(as_of_date))


def fetch_reserve_data(
    w3: Web3,
    *,
    pool_address: str,
    asset: str,
    block_number: int,
) -> dict[str, Any]:
    """Archive eth_call Pool.getReserveData(asset) at block_number."""
    pool = Web3.to_checksum_address(pool_address)
    token = Web3.to_checksum_address(asset)
    contract = w3.eth.contract(address=pool, abi=load_pool_abi())
    raw = contract.functions.getReserveData(token).call(block_identifier=int(block_number))
    # Tuple / named tuple — index by position for version resilience
    liquidity_index = int(raw[1])
    current_liquidity_rate = int(raw[2])
    last_update_timestamp = int(raw[6])
    apr, apy = ray_to_apr_apy(current_liquidity_rate)
    return {
        "block_number": int(block_number),
        "block_timestamp": None,
        "liquidity_rate_ray": current_liquidity_rate,
        "liquidity_index": liquidity_index,
        "supply_apr": apr,
        "supply_apy": apy,
        "supply_apy_label": "continuous_compound_from_apr_aave_utilities",
        "as_of_event_block": None,
        "as_of_tx_hash": None,
        "as_of_log_index": None,
        "last_update_timestamp": last_update_timestamp,
        "source": "archive_getReserveData",
        "reserve": token,
        "chain_id": int(w3.eth.chain_id),
        "protocol": "aave_v3",
    }


def connect_optional(rpc_url: str | None) -> Web3 | None:
    if not rpc_url:
        return None
    return make_web3(rpc_url)
