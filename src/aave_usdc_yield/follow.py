"""Tip follower (Phase 2) — stub for Phase 1."""

from __future__ import annotations

from .config import AppConfig
from .store import RateStore


def follow_tip(cfg: AppConfig, store: RateStore, *, poll_seconds: float = 12.0) -> None:
    raise NotImplementedError(
        "Tip follow is Phase 2. Phase 1: use `yield backfill` periodically. "
        f"(poll_seconds={poll_seconds}, db={store.db_path})"
    )
