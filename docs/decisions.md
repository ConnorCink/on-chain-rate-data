# Decisions & pins (Myshk sign-off 2026-09-11; realized path 2026-09-11)

## Product shape
Instantaneous USDC supply on Aave V3 Core Ethereum via `ReserveDataUpdated` → sparse SQLite → as-of / dense expand.
**Realized yield / wealth curve** via stored `liquidityIndex` is now in-scope for Connor’s thesis (“$1 left in → $X”).
Shelved: Morpho, multi-market.

## Pins (required before `yield at` ships APY)

| Pin | Value | Status |
|-----|--------|--------|
| chainId | `1` | Locked |
| Pool | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` | **Reconfirmed 2026-09-11** vs bgd-labs/aave-address-book `AaveV3Ethereum.POOL` and Etherscan “Aave: Pool V3” |
| USDC | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` | Locked (Ethereum native USDC) |
| Start block | Empirically first USDC `ReserveDataUpdated` on that pool | Discovered at runtime via `yield discover-start` / first `yield backfill`; stored in SQLite `meta.start_block`. Search floor for discovery: block `16200000` (not a pin). Queries with `N < start_block` → explicit `BeforeStartBlockError` |
| Rate field | Supply = `liquidityRate` / `currentLiquidityRate` (RAY). Never return variable borrow as supply yield | Locked in decode + API |
| APR→APY | RAY as APR: `APR = ray / 1e27`. `APY = (1 + APR/SECONDS_PER_YEAR)^SECONDS_PER_YEAR - 1` with `SECONDS_PER_YEAR=31536000` (Aave-utilities continuous). Always return RAY + APR; APY derived and labeled `continuous_compound_from_apr_aave_utilities` | Locked in `rates.py` |
| As-of | Latest update with `block_number <= N`; dense expand holds rate until next update | Locked in `asof.py` / `materialize.py` |
| Realized | `wealth = liquidityIndex(to) / liquidityIndex(from)` (RAY cancels). `cumulative_return = wealth - 1`. `annualized = wealth^(SECONDS_PER_YEAR/elapsed_s) - 1` preferring `block_timestamp`, else ~12s/block. Labeled `compound_from_index_ratio` | Locked in `realized.py` |
| Log chunks | Default `log_chunk_size=10` (config). On RPC 400 / range-limit class errors, iterator halves chunk down to 1 and retries. Resume via `meta.last_scanned_to_block` + max event block | Locked in `rpc.py` / `backfill.py` |

## Event signature
`ReserveDataUpdated(address indexed reserve, uint256 liquidityRate, uint256 stableBorrowRate, uint256 variableBorrowRate, uint256 liquidityIndex, uint256 variableBorrowIndex)`  
topic0 = `0x804c9b842b2748a22bb64b345453a3de7ca54a6ca45ce00d415894979e22897a`

`liquidityIndex` is always decoded and stored on `rate_updates.liquidity_index` (TEXT of uint256).

## SOFR compare
Thin scaffolding only: import a CSV (`date,rate`) and juxtapose average benchmark APR vs annualized realized (`yield compare-sofr`). Not a FRED client; spread is indicative (SOFR simple APR vs compound index growth).

## Non-blocking
SQLite OK; Grok Bot runtime OK; optional eth_call verify in Phase 3.

## Would block exit
Unlabeled APY with no formula; wrong reserve/rate field; hand-waved start block; every-block RPC backfill; realized without storing `liquidityIndex`.
