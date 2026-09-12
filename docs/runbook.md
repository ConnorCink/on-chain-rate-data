# Runbook — Aave V3 USDC supply yield (+ realized)

## Prerequisites
- Python ≥ 3.11
- Archive-capable Ethereum RPC in `ETH_ARCHIVE_RPC_URL` (for live backfill / discover / follow / verify)
- Working directory: repo root (so `config/default.toml` and `data/` resolve)

## Install (Grok Bot / any Linux)
```bash
cd /workspace/on-chain-rate-data   # or your clone
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env               # then edit — do not commit .env
set -a; source .env; set +a        # export ETH_ARCHIVE_RPC_URL without printing it
```

## Phase 1 — backfill + point query
```bash
# 1) Discover empirical start_block (also runs inside backfill if missing)
yield discover-start

# 2) Backfill USDC ReserveDataUpdated → data/yield.sqlite
# Default chunk=50; auto-shrinks on RPC 400s; resume-safe
yield backfill
# optional: yield backfill --from-block N --to-block M
# tiny chunks for stubborn providers:
#   yield backfill --config config/smoke.toml

# 3) Point query (as-of join)
yield at --block 18000000
yield at --block 18000000 --json
```

Queries with `N < start_block` fail with an explicit error. Empty DB → error asking you to backfill.

## Realized yield / wealth curve
Uses stored `liquidityIndex` (not instantaneous APY).

```bash
# $1 left in from start_block → latest (or --from/--to)
yield realized
yield realized --from 16291127 --to 18000000 --json

# Sparse wealth curve CSV ($1 since start or --from)
yield wealth-curve --out data/exports/wealth.csv
yield wealth-curve --from 16291127 --to 18000000 --out data/exports/wealth.csv

# Thin SOFR scaffolding (CSV: date,rate as decimal APR)
yield compare-sofr --benchmark path/to/sofr.csv --from 16291127 --to 18000000 --json
# if CSV rates are percent (5.32): add --rate-is-percent
```

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
Fixtures under `tests/fixtures/` exercise decode, as-of, rates, expand, realized, RPC shrink, SOFR import.

## Data & secrets
- SQLite: `data/yield.sqlite` (gitignored)
- Never commit `.env` or RPC URLs
- `meta.start_block` — empirical pin after discovery
- `meta.last_scanned_to_block` — resume checkpoint (includes empty ranges)
- `meta.last_backfill_to_block` — last completed tip target / scan high-water

## Resume / idempotency
Backfill resumes from `max(last_scanned_to_block, max event block)+1` for the USDC reserve.
Upserts are unique on `(chain_id, tx_hash, log_index)`.
On RPC 400 / range-limit errors, chunk size halves (floor 1) and the same range is retried.
Re-run `yield backfill` after interruption; it continues from the checkpoint.
