import json
from pathlib import Path

from aave_usdc_yield.decode import (
    decode_reserve_data_updated,
    reserve_topic,
    topic_hex,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sample_logs.json"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def test_topic_hex_stable():
    assert topic_hex().startswith("0x")
    assert len(topic_hex()) == 66


def test_reserve_topic_padding():
    t = reserve_topic(USDC)
    assert t == "0x" + "0" * 24 + USDC.lower().removeprefix("0x")


def test_decode_sample_logs():
    logs = json.loads(FIXTURES.read_text())
    row0 = decode_reserve_data_updated(
        logs[0], chain_id=1, protocol="aave_v3", expected_reserve=USDC
    )
    assert row0["block_number"] == 16_291_127
    assert row0["log_index"] == 5
    assert row0["reserve"].lower() == USDC.lower()
    assert row0["liquidity_rate_ray"] > 0
    assert row0["liquidity_index"] == 10**27
    # Supply field is liquidityRate — variable borrow stored separately
    assert row0["variable_borrow_rate_ray"] > row0["liquidity_rate_ray"]

    row1 = decode_reserve_data_updated(
        logs[1], chain_id=1, protocol="aave_v3", expected_reserve=USDC
    )
    assert row1["block_number"] == 16_300_000
    assert row1["liquidity_rate_ray"] < row0["liquidity_rate_ray"]


def test_decode_rejects_wrong_reserve():
    logs = json.loads(FIXTURES.read_text())
    bad = dict(logs[0])
    # WETH
    bad["topics"] = [
        logs[0]["topics"][0],
        "0x000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    ]
    try:
        decode_reserve_data_updated(
            bad, chain_id=1, protocol="aave_v3", expected_reserve=USDC
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "reserve mismatch" in str(e)
