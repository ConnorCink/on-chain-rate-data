# Architecture — Aave V3 USDC Supply Yield (v1)

## Repo layout (proposed)

```text
aave-v3-usdc-yield/
  README.md                 # goal, quickstart, addresses, start block, APR→APY formula
  pyproject.toml            # or requirements.txt
  config/
    default.toml            # chain_id, pool, usdc, start_block, rpc_url env key
  src/aave_usdc_yield/
    __init__.py
    cli.py                  # yield at|backfill|materialize|follow|verify
    config.py
    abi/                    # Pool ReserveDataUpdated (+ getReserveData for verify)
    rpc.py                  # eth_getLogs, eth_call helpers
    decode.py               # event → rate row (RAY fields, index if present)
    store.py                # SQLite schema + upsert rate_updates
    asof.py                 # point query: latest update <= N
    materialize.py          # sparse → dense every-block series (parquet/csv)
    follow.py               # tip poller / log subscription loop
    rates.py                # RAY → APR → APY (documented)
    verify.py               # sample archive getReserveData compare
  data/                     # gitignored: yield.sqlite, exports/
  .env.example              # RPC_URL=  (real secrets stay out of git)
  tests/
    test_asof.py
    test_materialize.py
    test_rates.py
  docs/
    runbook.md              # local backfill, follow, verify
    decisions.md            # pinned addresses + start block once known
```

## Data flow

1. **Backfill:** `eth_getLogs` on Pool `ReserveDataUpdated`, topic/data filter to USDC reserve, from `start_block` → tip → append-only `rate_updates`.
2. **Point query:** as-of join on `block_number <= N` (carry-forward).
3. **Materialize:** walk sparse updates; hold rate constant across contiguous blocks; write parquet/csv — **no per-block RPC**.
4. **Follow:** poll new logs after last stored block; same decode/store path.
5. **Verify:** optional archive `getReserveData` at sample blocks; compare `currentLiquidityRate` to indexed as-of within tolerance.

## CLI surface

- `yield at --block N`
- `yield backfill`
- `yield materialize --from A --to B`
- `yield follow`
- `yield verify --blocks N1,N2,...`

## Phase gates

| Phase | Done when |
|-------|-----------|
| 1 | Config + backfill + SQLite + `yield at` works inception→tip |
| 2 | Dense materialize over multi-day range + tip follow |
| 3 | Verify samples + runbook |

## Runtime

Backfill and follow run in the **Grok Bot environment** (agent computer), not Connor's personal machine. RPC URL via env/secrets (never committed). SQLite under `data/`. Repo is intended to be **open source** — public-ready layout, no private keys or RPC URLs in git.
