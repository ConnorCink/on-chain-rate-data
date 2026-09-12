import json
from pathlib import Path

import pytest

from aave_usdc_yield.decode import decode_reserve_data_updated
from aave_usdc_yield.rates import RAY, SECONDS_PER_YEAR
from aave_usdc_yield.realized import (
    RealizedYieldError,
    annualized_realized,
    cumulative_return,
    index_ratio,
    realized_between,
    wealth_curve,
)
from aave_usdc_yield.store import RateStore

FIXTURES = Path(__file__).parent / "fixtures" / "sample_logs.json"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def _rows():
    logs = json.loads(FIXTURES.read_text())
    return [
        decode_reserve_data_updated(l, chain_id=1, protocol="aave_v3", expected_reserve=USDC)
        for l in logs
    ]


def test_index_ratio_and_cumulative():
    i0 = 10**27
    i1 = 10**27 + 10**19
    r = index_ratio(i0, i1)
    assert abs(r - i1 / i0) < 1e-18
    assert abs(cumulative_return(i0, i1) - (r - 1)) < 1e-18


def test_annualized_from_timestamps():
    wealth = 1.05
    # Exactly one year
    ann = annualized_realized(
        wealth,
        from_timestamp=0,
        to_timestamp=SECONDS_PER_YEAR,
    )
    assert ann is not None
    assert abs(ann - 0.05) < 1e-12


def test_annualized_block_fallback():
    wealth = 1.0 + 1e-6
    ann = annualized_realized(wealth, from_block=100, to_block=100 + 2_628_000)  # ~1y @12s
    assert ann is not None
    assert ann > 0


def test_realized_between_fixtures():
    rows = _rows()
    out = realized_between(rows, from_block=16_291_127, to_block=16_300_000)
    assert out["liquidity_index_from"] == RAY
    expected_to = int(rows[1]["liquidity_index"])
    assert out["liquidity_index_to"] == expected_to
    assert abs(out["index_ratio"] - expected_to / RAY) < 1e-18
    assert abs(out["wealth_of_1"] - out["index_ratio"]) < 1e-18
    assert out["cumulative_return"] == pytest.approx(out["index_ratio"] - 1)
    assert out["annualized_realized"] is not None
    assert out["source"] == "liquidity_index"


def test_realized_carry_asof():
    rows = _rows()
    # Between updates: still first index at from, still first at mid
    mid = realized_between(rows, from_block=16_291_127, to_block=16_295_000)
    assert mid["liquidity_index_to"] == RAY
    assert mid["index_ratio"] == 1.0
    assert mid["cumulative_return"] == 0.0


def test_wealth_curve_points():
    rows = _rows()
    pts = wealth_curve(rows, from_block=16_291_127, to_block=16_300_000)
    assert len(pts) == 2
    assert pts[0]["wealth_of_1"] == 1.0
    assert pts[1]["wealth_of_1"] == pytest.approx(int(rows[1]["liquidity_index"]) / RAY)
    assert pts[1]["cumulative_return"] == pytest.approx(pts[1]["wealth_of_1"] - 1)


def test_missing_index_errors():
    bad = [{"block_number": 1, "log_index": 0, "liquidity_index": None}]
    with pytest.raises(RealizedYieldError):
        realized_between(bad, from_block=1, to_block=1)


def test_store_roundtrip_index(tmp_path):
    store = RateStore(tmp_path / "t.sqlite")
    rows = _rows()
    store.upsert_rate_updates(rows)
    stored = store.all_updates_ordered(chain_id=1, reserve=USDC)
    assert all(s["liquidity_index"] is not None for s in stored)
    out = realized_between(stored, from_block=16_291_127, to_block=16_300_000)
    assert out["wealth_of_1"] > 1.0
