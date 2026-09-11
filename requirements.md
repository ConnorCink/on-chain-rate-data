# Requirements: Aave V3 USDC Supply Yield (Historical Blocks)

**Status:** Decisions locked — ready for build — v1.1  
**Date:** 2026-09-11  
**Owner:** Connor / Myshk  
**Supersedes:** Broad Aave+Morpho market warehouse draft (v0.1); requirements review v1.0

---

## 1. Problem

We need a reliable way to answer:

> At Ethereum block `N`, what was the **instantaneous** supply yield for **USDC** on **Aave V3 Core**?

Public dashboards make this awkward for arbitrary historical blocks. Per-block archive `eth_call` across history is correct but too slow and expensive if we materialize every block even once.

---

## 2. Goal (v1)

Build a small tool that, for **Aave V3 Ethereum USDC supply**, can return instantaneous supply yield for **any block since that reserve’s usable inception**, and can efficiently produce an **every-block series** at least once.

**Out of scope for v1 (explicit):**
- Realized / accrued yield (liquidity index path) — deferred; schema should not block it
- Morpho, other chains, other assets
- Liquidations, wallet positions, vault wrappers (ERC-4626 / MetaMorpho)
- Multi-tenant data product, sub-second trading latency

---

## 3. Definitions

### 3.1 Market
**Aave V3 Core** pool on Ethereum mainnet, **USDC** reserve (aUSDC supply side).  
Not a Morpho market and not a generic “vault” product — protocol reserve supply rate.

### 3.2 Instantaneous yield
The protocol’s **current supply interest rate** at block `N`: the rate last written by the pool for that reserve and still in effect at `N`.

- On-chain source field: `currentLiquidityRate` (RAY, 1e27), treated as **APR** in Aave’s usual encoding
- Between rate-update transactions, this value is **piecewise constant**
- v1 exposes:
  - **raw RAY**
  - **APR** (decimal / percent)
  - **APY** (compounded from APR using the same convention we document in code — Aave UI-style continuous compounding)

### 3.3 “Any block since inception”
Any block from the first block at which USDC reserve rate state is meaningfully defined on Aave V3 Ethereum (first `ReserveDataUpdated` / reserve activation for USDC — exact start block pinned during implementation) through chain tip.

### 3.4 Realized yield (deferred)
Growth implied by the reserve **liquidity index** between two blocks. Not delivered in v1; ingest should retain index fields when present on events so we do not re-backfill later.

---

## 4. Functional requirements

### F1 — Point query
Given block number `N`, return instantaneous USDC supply yield at that block:
- `block_number`, `block_timestamp` (if available)
- `liquidity_rate_ray`
- `supply_apr`
- `supply_apy`
- `as_of_event_block` (block of the rate update applied)
- `source` (`event_index`)

### F2 — Every-block materialization
Ability to generate a dense series for a block range `[start, end]` (default: inception → tip) where each block has an instantaneous yield row, **without** one RPC call per block.

### F3 — Tip follow
After historical backfill, continue ingesting new `ReserveDataUpdated` logs so queries near tip stay current.

### F4 — Reproducibility
Given the same event store, point queries are deterministic. Dense materialization is a pure function of the sparse event series + block range.

### F5 — Validation mode (non-primary)
Optional spot-check: archive `eth_call` `getReserveData` at sample blocks; compare to indexed as-of rate within documented tolerance. Failures are reported; this path is not used for full history.

---

## 5. Non-functional requirements

| Area | Target |
|------|--------|
| Cost | Historical build dominated by **log backfill**, not per-block calls |
| Speed | Dense every-block series from sparse events is local I/O/CPU bound |
| Freshness | Tip follower lag typically under a few minutes under normal RPC conditions |
| Correctness | As-of join uses latest USDC `ReserveDataUpdated` with `block_number <= N` |
| Operability | Runnable by one person; clear start block, pool address, USDC address in config |
| Runtime | Backfill and tip follower run in the **Grok Bot environment** (shared agent computer), not Connor's personal machine |

---

## 6. Technical approach (normative)

### 6.1 Primary path — event index + as-of / expand
1. Backfill `ReserveDataUpdated` logs from Aave V3 Pool, **filtered to the USDC reserve**.
2. Store sparse series: one row per rate update.
3. **Point query:** as-of join (latest update ≤ `N`).
4. **Every-block series:** expand sparse updates locally across contiguous blocks (rate held constant until next update).

### 6.2 Rejected as primary
- Archive `getReserveData` once per block for full history.

### 6.3 Hybrid
- Keep optional `eth_call` sampling for QA only.

### 6.4 RPC / providers
- Ethereum archive-capable RPC for log backfill + tip follow (+ optional validation calls).
- Indexed log providers (Goldsky, etc.) are optional accelerators, not required for v1 if direct log queries suffice for a single reserve.

---

## 7. Data model (minimum)

### `rate_updates` (append-only, sparse)
- `chain_id` (1)
- `protocol` (`aave_v3`)
- `reserve` (`USDC` / underlying address)
- `block_number`
- `block_timestamp` (nullable until enriched)
- `tx_hash`, `log_index`
- `liquidity_rate_ray`
- `liquidity_index` (store if present on event / companion data — for future realized yield)
- `variable_borrow_rate_ray` (optional, useful later; not required for v1 API)
- Unique on `(chain_id, tx_hash, log_index)`

### Derived (not necessarily stored)
- Point as-of views
- Dense every-block parquet/table produced on demand or via batch job

Storage for v1: **SQLite** for sparse events; **Parquet** acceptable for dense exports.

---

## 8. Interfaces (v1)

Minimum:
- CLI (or equivalent script entrypoints):
  - `yield at --block N`
  - `yield backfill` (logs)
  - `yield materialize --from A --to B` (dense series)
  - `yield follow` (tip)
  - `yield verify --blocks N1,N2,...` (optional eth_call checks)

A thin HTTP API is optional and not required to close v1.

---

## 9. Success criteria

v1 is done when:

1. USDC Aave V3 Ethereum rate updates are backfilled from inception → tip.  
2. `yield at --block N` works for arbitrary `N` in that range (including blocks with no USDC txs — carries forward last rate).  
3. An every-block materialization over a multi-day range completes **without** per-block `eth_call`.  
4. Documented: pool address, USDC address, start block, APR→APY formula.  
5. At least a handful of `verify` samples match archive `getReserveData` within tolerance (or discrepancies explained).

---

## 10. Phased delivery

| Phase | Deliverable |
|-------|-------------|
| **1** | Config + log backfill + sparse store + point query |
| **2** | Dense materialize + tip follow |
| **3** | Verify mode + short runbook |
| **Later** | Realized yield via liquidity index; more assets/protocols |

---

## 11. Open items for review

None for v1 scope. Implementation pins (start block, pool address, USDC address, APR→APY formula constant) are recorded in config/docs during Phase 1 — not product forks.

Still useful before coding (not requirements forks): archive RPC endpoint/credentials for the Grok Bot environment.

---

## 12. Decisions locked

- Scope: instantaneous supply yield only (realized deferred)  
- Market: **Aave V3 Core Ethereum USDC** only (not Morpho, not other chains/venues)  
- Outputs: **RAY + APR + APY** (APY = Aave UI-style continuous compounding from APR; formula documented in code)  
- Sparse store: **SQLite**  
- Runtime: backfill + tip follow in the **Grok Bot environment** (not Connor's personal machine)  
- Distribution: code will be **open-sourced**; keep the repo public-ready (no secrets)  
- Resolution strategy: index `ReserveDataUpdated` + local dense expansion  
- Efficiency constraint: engineered for at least one full every-block pass without per-block RPC  
- Prior broad Morpho/multi-market warehouse requirements: **shelved**, not v1
- Implementation language: **Python** (web3 + SQLite + parquet)
- Agent swarm: Orchestrator (Chief of Staff), Design co-owner (Myshk), Protocol/indexer eng bot, Query/QA (same eng bot until split)
