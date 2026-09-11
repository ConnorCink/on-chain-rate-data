"""Decode ReserveDataUpdated logs into rate_updates rows."""

from __future__ import annotations

from typing import Any, Mapping

from eth_abi import decode as abi_decode
from eth_utils import event_abi_to_log_topic, to_checksum_address

# ReserveDataUpdated(address,uint256,uint256,uint256,uint256,uint256)
RESERVE_DATA_UPDATED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "reserve", "type": "address"},
        {"indexed": False, "name": "liquidityRate", "type": "uint256"},
        {"indexed": False, "name": "stableBorrowRate", "type": "uint256"},
        {"indexed": False, "name": "variableBorrowRate", "type": "uint256"},
        {"indexed": False, "name": "liquidityIndex", "type": "uint256"},
        {"indexed": False, "name": "variableBorrowIndex", "type": "uint256"},
    ],
    "name": "ReserveDataUpdated",
    "type": "event",
}

RESERVE_DATA_UPDATED_TOPIC = event_abi_to_log_topic(RESERVE_DATA_UPDATED_ABI)


def topic_hex() -> str:
    return "0x" + RESERVE_DATA_UPDATED_TOPIC.hex()


def reserve_topic(usdc_address: str) -> str:
    """Indexed address topic (32-byte left-padded)."""
    addr = usdc_address.lower().removeprefix("0x")
    return "0x" + ("0" * 24) + addr


def decode_reserve_data_updated(
    log: Mapping[str, Any],
    *,
    chain_id: int,
    protocol: str,
    expected_reserve: str | None = None,
) -> dict[str, Any]:
    """Decode one log into a rate_updates dict.

    Supply yield uses liquidityRate (RAY) only — never variableBorrowRate.
    """
    topics = list(log["topics"])
    if not topics:
        raise ValueError("log missing topics")

    topic0 = topics[0]
    if isinstance(topic0, (bytes, bytearray)):
        topic0_hex = "0x" + bytes(topic0).hex()
    else:
        topic0_hex = str(topic0).lower()
        if not topic0_hex.startswith("0x"):
            topic0_hex = "0x" + topic0_hex

    if topic0_hex.lower() != topic_hex().lower():
        raise ValueError(f"unexpected topic0: {topic0_hex}")

    if len(topics) < 2:
        raise ValueError("ReserveDataUpdated missing indexed reserve topic")

    reserve_raw = topics[1]
    if isinstance(reserve_raw, (bytes, bytearray)):
        reserve_bytes = bytes(reserve_raw)
    else:
        reserve_bytes = bytes.fromhex(str(reserve_raw).removeprefix("0x"))
    reserve = to_checksum_address("0x" + reserve_bytes[-20:].hex())

    if expected_reserve and reserve.lower() != expected_reserve.lower():
        raise ValueError(
            f"reserve mismatch: expected {expected_reserve}, got {reserve}"
        )

    data = log["data"]
    if isinstance(data, (bytes, bytearray)):
        data_bytes = bytes(data)
    else:
        data_bytes = bytes.fromhex(str(data).removeprefix("0x"))

    (
        liquidity_rate,
        stable_borrow_rate,
        variable_borrow_rate,
        liquidity_index,
        variable_borrow_index,
    ) = abi_decode(
        ["uint256", "uint256", "uint256", "uint256", "uint256"],
        data_bytes,
    )

    tx_hash = log.get("transactionHash") or log.get("tx_hash")
    if isinstance(tx_hash, (bytes, bytearray)):
        tx_hash = "0x" + bytes(tx_hash).hex()
    else:
        tx_hash = str(tx_hash)

    block_number = int(log["blockNumber"], 16) if isinstance(log["blockNumber"], str) else int(log["blockNumber"])
    log_index = int(log["logIndex"], 16) if isinstance(log["logIndex"], str) else int(log["logIndex"])

    block_ts = log.get("block_timestamp")
    if block_ts is not None:
        block_ts = int(block_ts)

    return {
        "chain_id": chain_id,
        "protocol": protocol,
        "reserve": reserve,
        "block_number": block_number,
        "block_timestamp": block_ts,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "liquidity_rate_ray": int(liquidity_rate),
        "liquidity_index": int(liquidity_index),
        "variable_borrow_rate_ray": int(variable_borrow_rate),
        "stable_borrow_rate_ray": int(stable_borrow_rate),
        "variable_borrow_index": int(variable_borrow_index),
    }
