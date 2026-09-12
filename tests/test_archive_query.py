"""Smoke tests for archive helpers (no live RPC)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from aave_usdc_yield.archive_query import (
    block_at_or_before_timestamp,
    date_to_utc_midnight_ts,
    datetime_to_ts,
    resolve_block,
)
from aave_usdc_yield.envload import load_dotenv, rpc_configured


def test_date_to_utc_midnight_ts():
    ts = date_to_utc_midnight_ts(date(2024, 1, 1))
    assert ts == int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())


def test_datetime_to_ts_iso_variants():
    expected = int(datetime(2024, 6, 15, 18, 30, 0, tzinfo=timezone.utc).timestamp())
    assert datetime_to_ts("2024-06-15T18:30:00Z") == expected
    assert datetime_to_ts("2024-06-15T18:30:00+00:00") == expected
    assert datetime_to_ts("2024-06-15T18:30:00") == expected  # naive → UTC
    assert datetime_to_ts(datetime(2024, 6, 15, 18, 30, 0, tzinfo=timezone.utc)) == expected
    # offset east of UTC
    assert datetime_to_ts("2024-06-15T20:30:00+02:00") == expected
    with pytest.raises(ValueError):
        datetime_to_ts("")
    with pytest.raises(ValueError):
        datetime_to_ts("not-a-date")


class _FakeEth:
    def __init__(self, blocks: dict[int, int], tip: int):
        self._blocks = blocks
        self.block_number = tip

    def get_block(self, n: int):
        return {"timestamp": self._blocks[n]}


def test_block_at_or_before_timestamp_binary_search():
    # timestamps: block i has ts = 1000 + i
    tip = 100
    blocks = {i: 1000 + i for i in range(tip + 1)}
    w3 = SimpleNamespace(eth=_FakeEth(blocks, tip))
    assert block_at_or_before_timestamp(w3, 1000) == 0
    assert block_at_or_before_timestamp(w3, 1050) == 50
    assert block_at_or_before_timestamp(w3, 9999) == tip


def test_resolve_block_modes():
    tip = 10
    blocks = {i: 1000 + i for i in range(tip + 1)}
    w3 = SimpleNamespace(eth=_FakeEth(blocks, tip))
    assert resolve_block(w3, block_number=7) == 7
    with pytest.raises(ValueError):
        resolve_block(w3, block_number=1, as_of_date=date(2020, 1, 1))
    with pytest.raises(ValueError):
        resolve_block(
            w3,
            as_of_date=date(2020, 1, 1),
            as_of_datetime="2020-01-01T12:00:00Z",
        )
    with pytest.raises(RuntimeError):
        resolve_block(None, as_of_date=date(2020, 1, 1))
    with pytest.raises(RuntimeError):
        resolve_block(None, as_of_datetime="2020-01-01T12:00:00Z")
    with pytest.raises(ValueError):
        # before genesis timestamp on fake chain
        resolve_block(w3, as_of_date=date(1970, 1, 1))


def test_resolve_block_date_with_fake_chain():
    # Genesis far in the past so 2020-01-01 maps inside range
    tip = 1_000
    # linear map: block 0 @ 2019-01-01, tip @ 2021-01-01
    t0 = int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())
    t1 = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
    blocks = {}
    for i in range(tip + 1):
        blocks[i] = t0 + int((t1 - t0) * i / tip)
    w3 = SimpleNamespace(eth=_FakeEth(blocks, tip))
    b = resolve_block(w3, as_of_date=date(2020, 1, 1))
    assert 0 <= b <= tip
    assert blocks[b] <= date_to_utc_midnight_ts(date(2020, 1, 1))
    if b < tip:
        assert blocks[b + 1] > date_to_utc_midnight_ts(date(2020, 1, 1))


def test_resolve_block_datetime_beyond_midnight():
    tip = 1_000
    t0 = int(datetime(2019, 1, 1, tzinfo=timezone.utc).timestamp())
    t1 = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp())
    blocks = {i: t0 + int((t1 - t0) * i / tip) for i in range(tip + 1)}
    w3 = SimpleNamespace(eth=_FakeEth(blocks, tip))

    midnight = "2020-06-15T00:00:00Z"
    afternoon = "2020-06-15T18:30:00Z"
    b_mid = resolve_block(w3, as_of_datetime=midnight)
    b_aft = resolve_block(w3, as_of_datetime=afternoon)
    assert b_aft >= b_mid
    assert blocks[b_aft] <= datetime_to_ts(afternoon)
    if b_aft < tip:
        assert blocks[b_aft + 1] > datetime_to_ts(afternoon)


def test_envload_does_not_require_file(tmp_path):
    assert load_dotenv(tmp_path / "missing.env") is None
    assert rpc_configured("NONEXISTENT_RPC_KEY_XYZ") is False


def test_envload_parses_without_exposing(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("ETH_ARCHIVE_RPC_URL=https://secret.example/KEY\nFOO=bar\n")
    monkeypatch.delenv("ETH_ARCHIVE_RPC_URL", raising=False)
    monkeypatch.delenv("FOO", raising=False)
    loaded = load_dotenv(p)
    assert loaded == p.resolve()
    assert rpc_configured("ETH_ARCHIVE_RPC_URL") is True
    import os

    assert os.environ["FOO"] == "bar"
    # value present in env but test must not print it; just check prefix
    assert os.environ["ETH_ARCHIVE_RPC_URL"].startswith("https://")
