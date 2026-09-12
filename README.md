# aave-usdc-yield

Open-source Python tool for **instantaneous** and **realized** Aave V3 Core (Ethereum) USDC supply yield at any historical block.

**Approach:** backfill `ReserveDataUpdated` logs (USDC-filtered) → sparse SQLite `rate_updates` (incl. `liquidityIndex`) → as-of join / dense expand / realized wealth curve.  
**Not** per-block archive `eth_call` for history.

## Pins (Myshk)

| Pin | Value |
|-----|--------|
| chainId | `1` |
| Pool | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` (confirmed vs [aave-address-book](https://github.com/bgd-labs/aave-address-book) `AaveV3Ethereum.POOL`) |
| USDC | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` |
| start_block | Empirical first USDC `ReserveDataUpdated` (`yield discover-start` / first `yield backfill`) |
| Supply rate | `liquidityRate` / `currentLiquidityRate` (RAY) only |
| APR | `ray / 1e27` |
| APY | `(1 + APR/31536000)**31536000 - 1` (Aave-utilities continuous style; always labeled) |

See `docs/decisions.md`.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Point queries need a populated DB (fixtures for tests, or live backfill):
export ETH_ARCHIVE_RPC_URL="https://your-archive-rpc"   # never commit
yield discover-start          # optional; also done inside backfill
yield backfill                # chunked eth_getLogs → data/yield.sqlite
yield at --block 18000000
yield at --block 18000000 --json
```

Without RPC, the full code path is covered by unit tests + fixtures:

```bash
pytest -q
```

## CLI

| Command | Phase | Description |
|---------|-------|-------------|
| `yield at --block N` | 1 | As-of point query (instantaneous) |
| `yield backfill` | 1 | Log backfill → SQLite (small chunks, resume-safe) |
| `yield discover-start` | 1 | Empirical start_block |
| `yield materialize --from A --to B` | 1 logic / 2 polish | Local dense expand (no per-block RPC) |
| `yield realized [--from] [--to]` | 1+ | Realized return via liquidityIndex ratio |
| `yield wealth-curve --out CSV` | 1+ | Export $1 wealth curve CSV |
| `yield compare-sofr --benchmark CSV` | scaffolding | Realized vs imported SOFR/benchmark |
| `yield follow` | 2 stub | Tip follower |
| `yield verify --blocks …` | 3 stub | Archive `getReserveData` checks |

Entrypoints: `yield` and `aave-usdc-yield`.

## Layout

```text
config/default.toml          # locked addresses + db path
src/aave_usdc_yield/         # package
data/                        # gitignored SQLite / exports
docs/decisions.md            # pins + formula
docs/runbook.md              # ops
tests/                       # rates, decode, asof, materialize
```

## License

MIT — see `LICENSE`.
