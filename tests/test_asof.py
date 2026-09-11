import json
from pathlib import Path

import pytest

from aave_usdc_yield.asof import BeforeStartBlockError, NoRateDataError, yield_at
from aave_usdc_yield.config import AppConfig
from aave_usdc_yield.decode import decode_reserve_data_updated
from aave_usdc_yield.store import RateStore

FIXTURES = Path(__file__).parent / "fixtures" / "sample_logs.json"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"


def _cfg(tmp_path, start_block=16_291_127):
    return AppConfig(
        chain_id=1,
        protocol="aave_v3",
        pool_address=POOL,
        usdc_address=USDC,
        start_block=start_block,
        rpc_env_key="ETH_ARCHIVE_RPC_URL",
        log_chunk_size=10_000,
        db_path=tmp_path / "test.sqlite",
        config_path=tmp_path / "dummy.toml",
    )


def _seed(store: RateStore):
    logs = json.loads(FIXTURES.read_text())
    rows = [
        decode_reserve_data_updated(l, chain_id=1, protocol="aave_v3", expected_reserve=USDC)
        for l in logs
    ]
    store.upsert_rate_updates(rows)
    store.set_start_block(16_291_127)
    return rows


def test_asof_exact_update_block(tmp_path):
    cfg = _cfg(tmp_path)
    store = RateStore(cfg.db_path)
    rows = _seed(store)
    out = yield_at(cfg, store, 16_291_127)
    assert out["as_of_event_block"] == 16_291_127
    assert out["liquidity_rate_ray"] == rows[0]["liquidity_rate_ray"]
    assert out["source"] == "event_index"
    assert "supply_apr" in out and "supply_apy" in out
    assert out["supply_apy_label"]


def test_asof_carry_forward(tmp_path):
    cfg = _cfg(tmp_path)
    store = RateStore(cfg.db_path)
    rows = _seed(store)
    # Between updates: still first rate
    out = yield_at(cfg, store, 16_295_000)
    assert out["as_of_event_block"] == 16_291_127
    assert out["liquidity_rate_ray"] == rows[0]["liquidity_rate_ray"]
    # After second update
    out2 = yield_at(cfg, store, 16_300_000)
    assert out2["as_of_event_block"] == 16_300_000
    assert out2["liquidity_rate_ray"] == rows[1]["liquidity_rate_ray"]
    out3 = yield_at(cfg, store, 16_400_000)
    assert out3["as_of_event_block"] == 16_300_000


def test_before_start_block_errors(tmp_path):
    cfg = _cfg(tmp_path, start_block=16_291_127)
    store = RateStore(cfg.db_path)
    _seed(store)
    with pytest.raises(BeforeStartBlockError):
        yield_at(cfg, store, 16_000_000)


def test_empty_store_errors(tmp_path):
    cfg = _cfg(tmp_path, start_block=None)
    store = RateStore(cfg.db_path)
    with pytest.raises(NoRateDataError):
        yield_at(cfg, store, 16_291_127)
