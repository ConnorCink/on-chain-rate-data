"""Archive getReserveData spot-check (Phase 3) — stub for Phase 1."""

from __future__ import annotations

from .config import AppConfig
from .store import RateStore


def verify_blocks(
    cfg: AppConfig, store: RateStore, blocks: list[int]
) -> list[dict]:
    raise NotImplementedError(
        "Verify mode is Phase 3. Indexed as-of path is the Phase 1 source of truth. "
        f"(blocks={blocks}, pool={cfg.pool_address})"
    )
