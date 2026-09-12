"""Load locked market pins and runtime paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.toml"

# Checksums locked in docs/decisions.md
LOCKED_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
LOCKED_USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
LOCKED_CHAIN_ID = 1


@dataclass(frozen=True)
class AppConfig:
    chain_id: int
    protocol: str
    pool_address: str
    usdc_address: str
    start_block: int | None
    rpc_env_key: str
    log_chunk_size: int
    db_path: Path
    config_path: Path

    @property
    def rpc_url(self) -> str | None:
        return os.environ.get(self.rpc_env_key) or None

    def require_rpc_url(self) -> str:
        url = self.rpc_url
        if not url:
            raise RuntimeError(
                f"Missing RPC URL. Set {self.rpc_env_key} (see .env.example). "
                "Never commit secrets."
            )
        return url


def _checksum(addr: str) -> str:
    # Lazy import so unit tests without web3 for rates still work if needed;
    # web3 is a hard dep of the package.
    from web3 import Web3

    return Web3.to_checksum_address(addr)


def load_config(path: Path | str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any]
    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)

    pool = _checksum(raw.get("pool_address", LOCKED_POOL))
    usdc = _checksum(raw.get("usdc_address", LOCKED_USDC))
    chain_id = int(raw.get("chain_id", LOCKED_CHAIN_ID))

    if chain_id != LOCKED_CHAIN_ID:
        raise ValueError(f"chain_id must be {LOCKED_CHAIN_ID} for v1; got {chain_id}")
    if pool.lower() != LOCKED_POOL.lower():
        raise ValueError(f"pool_address pin mismatch: expected {LOCKED_POOL}, got {pool}")
    if usdc.lower() != LOCKED_USDC.lower():
        raise ValueError(f"usdc_address pin mismatch: expected {LOCKED_USDC}, got {usdc}")

    start = raw.get("start_block", None)
    start_block = int(start) if start is not None else None

    db = Path(raw.get("db_path", "data/yield.sqlite"))
    if not db.is_absolute():
        db = (Path.cwd() / db).resolve()

    return AppConfig(
        chain_id=chain_id,
        protocol=str(raw.get("protocol", "aave_v3")),
        pool_address=pool,
        usdc_address=usdc,
        start_block=start_block,
        rpc_env_key=str(raw.get("rpc_env_key", "ETH_ARCHIVE_RPC_URL")),
        log_chunk_size=int(raw.get("log_chunk_size", 50)),
        db_path=db,
        config_path=cfg_path.resolve(),
    )
