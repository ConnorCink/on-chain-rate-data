from pathlib import Path

from aave_usdc_yield.config import LOCKED_POOL, LOCKED_USDC, load_config


def test_load_default_config():
    cfg = load_config()
    assert cfg.chain_id == 1
    assert cfg.pool_address == LOCKED_POOL
    assert cfg.usdc_address == LOCKED_USDC
    assert cfg.rpc_env_key == "ETH_ARCHIVE_RPC_URL"
    assert cfg.start_block is None  # empirical discovery


def test_config_path_exists():
    assert Path("config/default.toml").exists()
