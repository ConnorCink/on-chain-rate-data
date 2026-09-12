"""Unit tests for history sampling / cache (no live RPC)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aave_usdc_yield import archive_query as aq


class _FakeEth:
    def __init__(self, tip: int = 1000):
        self.block_number = tip
        self.chain_id = 1

    def get_block(self, n: int):
        return {"timestamp": 1_700_000_000 + int(n)}


def test_history_rejects_bad_points(monkeypatch):
    w3 = SimpleNamespace(eth=_FakeEth())

    def boom(*a, **k):
        raise AssertionError("should not call")

    monkeypatch.setattr(aq, "query_supply_rate_at_datetime_cached", boom)
    pool = "0x" + "11" * 20
    asset = "0x" + "22" * 20
    with pytest.raises(ValueError):
        aq.query_supply_rate_history(w3, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", 1, pool_address=pool, asset=asset)
    with pytest.raises(ValueError):
        aq.query_supply_rate_history(w3, "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", 200, pool_address=pool, asset=asset)


def test_history_cache_and_points(monkeypatch):
    w3 = SimpleNamespace(eth=_FakeEth())
    calls = {"n": 0}

    def fake_cached(w3, iso, *, pool_address, asset):
        calls["n"] += 1
        ts = aq.datetime_to_ts(iso)
        return {
            "block_number": 100,
            "block_timestamp": ts,
            "block_timestamp_iso": iso,
            "supply_apr": 0.05,
            "supply_apy": 0.051,
            "cache_hit": False,
        }

    monkeypatch.setattr(aq, "query_supply_rate_at_datetime_cached", fake_cached)
    aq._HISTORY_CACHE.clear()
    pool, asset = "0x" + "aa" * 20, "0x" + "bb" * 20
    out = aq.query_supply_rate_history(w3, "2024-06-01T00:00:00Z", "2024-06-08T00:00:00Z", 5, pool_address=pool, asset=asset)
    assert out["cache_hit"] is False
    assert len(out["points"]) == 5
    assert calls["n"] == 5
    out2 = aq.query_supply_rate_history(w3, "2024-06-01T00:00:00Z", "2024-06-08T00:00:00Z", 5, pool_address=pool, asset=asset)
    assert out2["cache_hit"] is True
    assert calls["n"] == 5
