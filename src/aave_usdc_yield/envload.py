"""Load local .env into os.environ without printing values (secrets-safe)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | str | None = None, *, override: bool = False) -> Path | None:
    """Parse KEY=VALUE lines into os.environ. Never logs values.

    Returns the path loaded, or None if missing. Existing env wins unless override.
    """
    if path is None:
        # Prefer CWD (repo root when running streamlit), else package-relative repo root.
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
    else:
        candidates = [Path(path)]

    for p in candidates:
        if not p.is_file():
            continue
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key:
                continue
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if override or key not in os.environ:
                os.environ[key] = val
        return p.resolve()
    return None


def rpc_configured(env_key: str = "ETH_ARCHIVE_RPC_URL") -> bool:
    """True if the RPC env var is set and non-empty (value never returned)."""
    v = os.environ.get(env_key)
    return bool(v and v.strip())
