"""Optional archive RPC helpers: date/datetime→block binary search + getReserveData eth_call.

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


def datetime_to_ts(value: datetime | str) -> int:
    """Parse ISO datetime (optional tz; default UTC) to unix seconds.

    Accepts ``datetime`` or ISO-8601 strings (``Z`` or offset). Naive values
    are treated as UTC.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if not s:
            raise ValueError("datetime string must be non-empty")
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            raise ValueError(
                f"Invalid ISO datetime {value!r}; expected e.g. "
                "2024-06-15T12:30:00Z or 2024-06-15T12:30:00+00:00"
            ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.astimezone(timezone.utc).timestamp())


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
    as_of_datetime: datetime | str | None = None,
) -> int:
    """Resolve UI/MCP input to a block. Date/datetime paths require w3."""
    provided = sum(
        x is not None for x in (block_number, as_of_date, as_of_datetime)
    )
    if provided > 1:
        raise ValueError(
            "Provide only one of block_number, as_of_date, or as_of_datetime"
        )
    if block_number is not None:
        if block_number < 0:
            raise ValueError("block_number must be >= 0")
        return int(block_number)
    if as_of_date is None and as_of_datetime is None:
        raise ValueError("Need block_number, as_of_date, or as_of_datetime")
    if w3 is None:
        raise RuntimeError(
            "Date/datetime→block requires ETH_ARCHIVE_RPC_URL (archive RPC). "
            "Enter a block number instead, or set the env var."
        )
    if as_of_datetime is not None:
        return block_at_or_before_timestamp(w3, datetime_to_ts(as_of_datetime))
    assert as_of_date is not None
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


def query_supply_rate_at_datetime(
    w3: Web3,
    datetime_iso: str,
    *,
    pool_address: str,
    asset: str,
) -> dict[str, Any]:
    """Resolve datetime → latest block ≤ instant, then archive getReserveData.

    Returns the MCP/demo payload fields (block meta + APR/APY + RAY + source).
    """
    target_ts = datetime_to_ts(datetime_iso)
    block_number = block_at_or_before_timestamp(w3, target_ts)
    data = fetch_reserve_data(
        w3,
        pool_address=pool_address,
        asset=asset,
        block_number=block_number,
    )
    block_ts = int(w3.eth.get_block(block_number)["timestamp"])
    data["block_timestamp"] = block_ts
    return {
        "block_number": data["block_number"],
        "block_timestamp": block_ts,
        "block_timestamp_iso": datetime.fromtimestamp(
            block_ts, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "requested_datetime": datetime_iso,
        "requested_timestamp": target_ts,
        "supply_apr": data["supply_apr"],
        "supply_apy": data["supply_apy"],
        "liquidity_rate_ray": data["liquidity_rate_ray"],
        "source": data["source"],
        "supply_apy_label": data["supply_apy_label"],
        "reserve": data["reserve"],
        "chain_id": data["chain_id"],
        "protocol": data["protocol"],
    }



# In-process cache: historical archive samples never change.
_RATE_CACHE: dict[tuple[str, str, int], dict[str, Any]] = {}
_HISTORY_CACHE: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}


def _cache_key_rate(pool: str, asset: str, block_number: int) -> tuple[str, str, int]:
    return (pool.lower(), asset.lower(), int(block_number))


def query_supply_rate_at_datetime_cached(
    w3: Web3,
    datetime_iso: str,
    *,
    pool_address: str,
    asset: str,
) -> dict[str, Any]:
    """Like query_supply_rate_at_datetime but caches by resolved block number."""
    target_ts = datetime_to_ts(datetime_iso)
    block_number = block_at_or_before_timestamp(w3, target_ts)
    key = _cache_key_rate(pool_address, asset, block_number)
    cached = _RATE_CACHE.get(key)
    if cached is not None:
        out = dict(cached)
        out["requested_datetime"] = datetime_iso
        out["requested_timestamp"] = target_ts
        out["cache_hit"] = True
        return out
    data = query_supply_rate_at_datetime(
        w3,
        datetime_iso,
        pool_address=pool_address,
        asset=asset,
    )
    store = {
        k: data[k]
        for k in (
            "block_number",
            "block_timestamp",
            "block_timestamp_iso",
            "supply_apr",
            "supply_apy",
            "liquidity_rate_ray",
            "source",
            "supply_apy_label",
            "reserve",
            "chain_id",
            "protocol",
        )
        if k in data
    }
    _RATE_CACHE[key] = store
    out = dict(data)
    out["cache_hit"] = False
    return out


def query_supply_rate_history(
    w3: Web3,
    start_iso: str,
    end_iso: str,
    points: int,
    *,
    pool_address: str,
    asset: str,
) -> dict[str, Any]:
    """Sample archive getReserveData evenly between start and end (inclusive).

    Returns ``{points: [{timestamp, timestamp_iso, supply_apr, supply_apy, block_number}], ...}``.
    Aggressive process cache: identical windows reuse results; per-block rates cached forever.
    """
    if points < 2:
        raise ValueError("points must be >= 2")
    if points > 120:
        raise ValueError("points must be <= 120")
    start_ts = datetime_to_ts(start_iso)
    end_ts = datetime_to_ts(end_iso)
    if end_ts < start_ts:
        raise ValueError("end_iso must be >= start_iso")

    hist_key = (
        pool_address.lower(),
        asset.lower(),
        f"{start_ts}:{end_ts}",
        int(points),
    )
    cached = _HISTORY_CACHE.get(hist_key)
    if cached is not None:
        return {
            "start_iso": start_iso,
            "end_iso": end_iso,
            "points_requested": points,
            "points": list(cached),
            "cache_hit": True,
            "source": "archive_getReserveData",
        }

    span = end_ts - start_ts
    samples: list[dict[str, Any]] = []
    for i in range(points):
        if points == 1:
            ts = end_ts
        else:
            ts = start_ts + int(round(span * i / (points - 1)))
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        row = query_supply_rate_at_datetime_cached(
            w3,
            iso,
            pool_address=pool_address,
            asset=asset,
        )
        samples.append(
            {
                "timestamp": row["block_timestamp"],
                "timestamp_iso": row["block_timestamp_iso"],
                "requested_timestamp": ts,
                "supply_apr": row["supply_apr"],
                "supply_apy": row["supply_apy"],
                "block_number": row["block_number"],
            }
        )

    _HISTORY_CACHE[hist_key] = samples
    return {
        "start_iso": start_iso,
        "end_iso": end_iso,
        "points_requested": points,
        "points": samples,
        "cache_hit": False,
        "source": "archive_getReserveData",
    }


def connect_optional(rpc_url: str | None) -> Web3 | None:
    if not rpc_url:
        return None
    return make_web3(rpc_url)
