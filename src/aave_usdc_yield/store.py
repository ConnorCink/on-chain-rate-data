"""SQLite sparse store for rate_updates."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_updates (
    chain_id INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    reserve TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    block_timestamp INTEGER,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    liquidity_rate_ray TEXT NOT NULL,
    liquidity_index TEXT,
    variable_borrow_rate_ray TEXT,
    UNIQUE (chain_id, tx_hash, log_index)
);

CREATE INDEX IF NOT EXISTS idx_rate_updates_asof
    ON rate_updates (chain_id, reserve, block_number);
"""


class RateStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_meta(self, key: str, value: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def get_start_block(self) -> int | None:
        v = self.get_meta("start_block")
        return int(v) if v is not None else None

    def set_start_block(self, block: int) -> None:
        self.set_meta("start_block", str(block))

    def upsert_rate_updates(self, rows: Sequence[dict[str, Any]]) -> int:
        if not rows:
            return 0
        sql = """
        INSERT INTO rate_updates (
            chain_id, protocol, reserve, block_number, block_timestamp,
            tx_hash, log_index, liquidity_rate_ray, liquidity_index,
            variable_borrow_rate_ray
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, tx_hash, log_index) DO UPDATE SET
            block_number = excluded.block_number,
            block_timestamp = excluded.block_timestamp,
            liquidity_rate_ray = excluded.liquidity_rate_ray,
            liquidity_index = excluded.liquidity_index,
            variable_borrow_rate_ray = excluded.variable_borrow_rate_ray
        """
        params = [
            (
                r["chain_id"],
                r["protocol"],
                r["reserve"],
                r["block_number"],
                r.get("block_timestamp"),
                r["tx_hash"],
                r["log_index"],
                str(r["liquidity_rate_ray"]),
                None if r.get("liquidity_index") is None else str(r["liquidity_index"]),
                None
                if r.get("variable_borrow_rate_ray") is None
                else str(r["variable_borrow_rate_ray"]),
            )
            for r in rows
        ]
        with self.connection() as conn:
            conn.executemany(sql, params)
        return len(params)

    def count(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM rate_updates").fetchone()
        return int(row["c"])

    def max_block(self, reserve: str | None = None) -> int | None:
        with self.connection() as conn:
            if reserve:
                row = conn.execute(
                    "SELECT MAX(block_number) AS m FROM rate_updates WHERE lower(reserve)=lower(?)",
                    (reserve,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT MAX(block_number) AS m FROM rate_updates"
                ).fetchone()
        return None if row["m"] is None else int(row["m"])

    def min_block(self, reserve: str | None = None) -> int | None:
        with self.connection() as conn:
            if reserve:
                row = conn.execute(
                    "SELECT MIN(block_number) AS m FROM rate_updates WHERE lower(reserve)=lower(?)",
                    (reserve,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT MIN(block_number) AS m FROM rate_updates"
                ).fetchone()
        return None if row["m"] is None else int(row["m"])

    def asof_row(
        self, *, chain_id: int, reserve: str, block_number: int
    ) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM rate_updates
                WHERE chain_id = ?
                  AND lower(reserve) = lower(?)
                  AND block_number <= ?
                ORDER BY block_number DESC, log_index DESC
                LIMIT 1
                """,
                (chain_id, reserve, block_number),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def all_updates_ordered(
        self, *, chain_id: int, reserve: str
    ) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM rate_updates
                WHERE chain_id = ? AND lower(reserve) = lower(?)
                ORDER BY block_number ASC, log_index ASC
                """,
                (chain_id, reserve),
            ).fetchall()
        return [dict(r) for r in rows]

    def updates_through(
        self, *, chain_id: int, reserve: str, to_block: int | None = None
    ) -> list[dict[str, Any]]:
        """Ordered updates up to to_block (inclusive), or all if to_block is None."""
        with self.connection() as conn:
            if to_block is None:
                rows = conn.execute(
                    """
                    SELECT * FROM rate_updates
                    WHERE chain_id = ? AND lower(reserve) = lower(?)
                    ORDER BY block_number ASC, log_index ASC
                    """,
                    (chain_id, reserve),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM rate_updates
                    WHERE chain_id = ? AND lower(reserve) = lower(?)
                      AND block_number <= ?
                    ORDER BY block_number ASC, log_index ASC
                    """,
                    (chain_id, reserve, to_block),
                ).fetchall()
        return [dict(r) for r in rows]
