# Runbook — Aave V3 USDC supply yield

## Prerequisites
- Python ≥ 3.10
- Archive-capable Ethereum RPC in `ETH_ARCHIVE_RPC_URL` (for live backfill / discover / follow / verify)
- Working directory: repo root (so `config/default.toml` and `data/` resolve)

## Install (Grok Bot / any Linux)
```bash
cd /workspace/on-chain-rate-data   # or your clone
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env               # then edit — do not commit .env
export ETH_ARCHIVE_RPC_URL=...     # or: set -a; source .env; set +a
```

## Phase 1 — backfill + point query
```bash
# 1) Discover empirical start_block (also runs inside backfill if missing)
yield discover-start

# 2) Backfill USDC ReserveDataUpdated → data/yield.sqlite
yield backfill
# optional: yield backfill --from-block N --to-block M

# 3) Point query (as-of join)
yield at --block 18000000
yield at --block 18000000 --json
```

Queries with `N < start_block` fail with an explicit error. Empty DB → error asking you to backfill.

## Dense expand (local)
```bash
yield materialize --from 18000000 --to 18001000 --out data/exports/slice.jsonl
```
No per-block `eth_call`. Full tip-follow + parquet polish = Phase 2.

## Stubs
- `yield follow` → Phase 2 (NotImplemented; re-run `backfill` periodically for now)
- `yield verify --blocks N1,N2` → Phase 3

## Tests without RPC
```bash
pytest -q
```
Fixtures under `tests/fixtures/` exercise decode, as-of, rates, and expand.

## Data & secrets
- SQLite: `data/yield.sqlite` (gitignored)
- Never commit `.env` or RPC URLs
- `meta.start_block` in SQLite holds the empirical pin after discovery

## Resume / idempotency
Backfill resumes from `max(block_number)+1` for the USDC reserve. Upserts are unique on `(chain_id, tx_hash, log_index)`.
