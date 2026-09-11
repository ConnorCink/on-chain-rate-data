from aave_usdc_yield.materialize import expand_sparse


def test_expand_holds_rate_until_next_update():
    updates = [
        {"block_number": 100, "log_index": 0, "liquidity_rate_ray": 1_000},
        {"block_number": 103, "log_index": 0, "liquidity_rate_ray": 2_000},
    ]
    rows = list(expand_sparse(updates, from_block=100, to_block=105))
    by_block = {r["block_number"]: r for r in rows}
    assert set(by_block) == {100, 101, 102, 103, 104, 105}
    assert by_block[100]["liquidity_rate_ray"] == 1_000
    assert by_block[101]["liquidity_rate_ray"] == 1_000
    assert by_block[102]["liquidity_rate_ray"] == 1_000
    assert by_block[103]["liquidity_rate_ray"] == 2_000
    assert by_block[105]["liquidity_rate_ray"] == 2_000
    assert by_block[101]["as_of_event_block"] == 100
    assert by_block[104]["as_of_event_block"] == 103


def test_expand_clips_range():
    updates = [
        {"block_number": 50, "log_index": 0, "liquidity_rate_ray": 9},
        {"block_number": 60, "log_index": 0, "liquidity_rate_ray": 8},
    ]
    rows = list(expand_sparse(updates, from_block=55, to_block=58))
    assert [r["block_number"] for r in rows] == [55, 56, 57, 58]
    assert all(r["liquidity_rate_ray"] == 9 for r in rows)


def test_expand_empty():
    assert list(expand_sparse([], from_block=1, to_block=10)) == []
