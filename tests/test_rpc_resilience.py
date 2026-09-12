"""Unit tests for eth_getLogs chunk shrink (no live RPC)."""

from aave_usdc_yield.rpc import is_retriable_log_range_error, iter_reserve_data_updated_logs


class _FakeEth:
    def __init__(self, plan):
        self.plan = list(plan)
        self.calls = []

    def get_logs(self, params):
        self.calls.append(params)
        action = self.plan.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class _FakeW3:
    def __init__(self, eth):
        self.eth = eth


def test_is_retriable_detects_400():
    assert is_retriable_log_range_error(Exception("HTTP 400 Bad Request: block range too large"))
    assert is_retriable_log_range_error(ValueError("query returned more than 10000 results"))
    assert not is_retriable_log_range_error(ValueError("invalid address"))


def test_chunk_shrinks_on_400_then_succeeds():
    # First call (chunk 50) fails; after shrink to 25, succeed empty; then next chunk
    eth = _FakeEth(
        [
            Exception("400 block range too large"),
            [],  # 100-124
            [],  # 125-149
        ]
    )
    w3 = _FakeW3(eth)
    msgs = []
    out = list(
        iter_reserve_data_updated_logs(
            w3,
            pool_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            usdc_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            from_block=100,
            to_block=149,
            chunk_size=50,
            progress=msgs.append,
        )
    )
    ends = [e for e, _ in out]
    assert ends == [124, 149]
    # First attempt used 50-wide, then 25-wide
    assert eth.calls[0]["fromBlock"] == 100
    assert eth.calls[0]["toBlock"] == 149
    assert eth.calls[1]["fromBlock"] == 100
    assert eth.calls[1]["toBlock"] == 124
    assert any("shrinking" in m for m in msgs)
