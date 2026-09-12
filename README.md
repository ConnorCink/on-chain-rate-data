# aave-usdc-yield

Engineering notes for agents and operators. Rebuild instantaneous and realized **Aave V3 Core (Ethereum) USDC supply** yield from chain logs — no reliance on Aave’s UI window.

| | |
|--|--|
| Scope | Aave V3 Core · `chainId=1` · USDC supply only |
| Primary path | `ReserveDataUpdated` logs → SQLite → as-of / realized |
| Rejected | Full-history per-block `eth_call` |
| License | MIT |
| Python | ≥ 3.11 |

Repo: https://github.com/ConnorCink/on-chain-rate-data

---

## 0. What “done” looks like

| Goal | Command | Expected outcome |
|------|---------|------------------|
| Unit confidence (no RPC) | `pytest -q` | `N passed` (currently 31+) |
| Instantaneous rate at block N | `yield at --block N --json` | JSON with `liquidity_rate_ray`, `supply_apr`, `supply_apy`, `as_of_event_block`, `source=event_index` |
| Realized return A→B | `yield realized --from A --to B --json` | Index ratio, cumulative return, annualized realized |
| $1 wealth path | `yield wealth-curve --out data/exports/wealth.csv` | CSV rows of cumulative wealth from index path |
| Populate DB | `yield backfill` | Growing `data/yield.sqlite`; resume-safe; tiny `eth_getLogs` chunks |

If `N < start_block` or DB empty → **explicit error** (not silent wrong zeros).

---

## 1. Setup

```bash
git clone https://github.com/ConnorCink/on-chain-rate-data.git
cd on-chain-rate-data
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env — set ETH_ARCHIVE_RPC_URL to an archive-capable Ethereum HTTPS endpoint.
# Never commit .env
```

Load env without printing secrets:

```bash
set -a && source .env && set +a
```

**RPC requirements**
- Must support historical `eth_getLogs` (and ideally archive `eth_call` for optional verify later).
- Many free tiers reject large block ranges → this tool defaults to **chunk size 10** and **auto-shrinks** on 400/range errors (floor 1). Expect slow inception→tip backfills; process is **resume-safe**.

**Config pins** (`config/default.toml`)

| Key | Value |
|-----|--------|
| `pool_address` | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` |
| `usdc_address` | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48` |
| `rpc_env_key` | `ETH_ARCHIVE_RPC_URL` |
| `log_chunk_size` | `10` (default; override in toml) |
| `db_path` | `data/yield.sqlite` |
| `start_block` | unset until `discover-start` / first backfill |

Details: `docs/decisions.md`. Ops: `docs/runbook.md`.

---

## 2. Offline verify (no RPC)

```bash
source .venv/bin/activate
pytest -q
```

**Expected:** all tests pass. Fixtures cover decode, as-of, RAY→APR→APY, materialize expand, realized math, chunk shrink, SOFR CSV import.

---

## 3. Live pipeline

Work from **repo root** so `config/` and `data/` resolve.

### 3.1 Discover start block

```bash
yield discover-start
```

**Expected:** prints empirical first USDC `ReserveDataUpdated` block; stores `meta.start_block`.  
**Note:** do not hand-wave this pin. If a DB was seeded with a late `start_block`, rediscover from floor ~`16200000` before claiming “since inception.”

### 3.2 Backfill logs → SQLite

```bash
yield backfill
# optional window:
yield backfill --from-block N --to-block M
# stubborn RPC:
yield backfill --config config/smoke.toml
```

**Expected (stdout/stderr):**
- `Using start_block = …` or discovery messages
- Periodic `stored K updates … total rows≈…`
- On provider 400s: `shrinking to … and retrying`
- Final JSON-ish stats: `inserted`, `from_block`, `to_block`, `start_block`, `total_rows`

**Artifacts:** `data/yield.sqlite` (gitignored). Resume uses `meta.last_scanned_to_block` and max event block.

### 3.3 Instantaneous point query

```bash
yield at --block 18000000
yield at --block 18000000 --json
```

**Expected JSON fields (names stable for agents):**

```json
{
  "block_number": 18000000,
  "liquidity_rate_ray": 0,
  "supply_apr": 0.0,
  "supply_apy": 0.0,
  "supply_apy_label": "continuous_compound_from_apr_aave_utilities",
  "as_of_event_block": 0,
  "source": "event_index",
  "reserve": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
  "chain_id": 1,
  "protocol": "aave_v3"
}
```

(`0` placeholders above — live values come from DB.)

**Formulas**
- `supply_apr = liquidity_rate_ray / 1e27`
- `supply_apy = (1 + apr/31536000)**31536000 - 1`
- As-of: latest USDC update with `block_number <= N`

### 3.4 Realized return (liquidity index)

```bash
yield realized
yield realized --from START --to END --json
```

**Expected:** cumulative growth `index_end/index_start`, implied `$1 → $x`, annualized realized for the window.  
This is **not** instantaneous APY. Use for “what did a passive supplier actually accrue?”

### 3.5 Wealth curve export

```bash
mkdir -p data/exports
yield wealth-curve --out data/exports/wealth.csv
yield wealth-curve --from START --to END --out data/exports/wealth.csv
```

**Expected:** CSV suitable for plotting cumulative wealth along stored index updates.

### 3.6 Benchmark scaffolding (SOFR CSV)

```bash
yield compare-sofr --benchmark tests/fixtures/sample_sofr.csv --json
# if CSV rates are percent (e.g. 5.32): --rate-is-percent
```

**Expected:** realized window vs imported benchmark series (indicative spread). Bring your own SOFR/MMF CSV for production compares.

### 3.7 Dense expand (local, no per-block RPC)

```bash
yield materialize --from A --to B --out data/exports/slice.jsonl
```

**Expected:** every-block series with rate held constant between updates.

---

## 4. CLI map

| Command | Needs RPC | Needs DB | Notes |
|---------|-----------|----------|-------|
| `yield discover-start` | yes | writes meta | Empirical start |
| `yield backfill` | yes | writes | Resume-safe; tiny chunks |
| `yield at --block N` | no | yes | Instantaneous as-of |
| `yield realized` | no | yes + index | Realized path |
| `yield wealth-curve` | no | yes + index | CSV export |
| `yield compare-sofr` | no | yes + CSV | Scaffolding |
| `yield materialize` | no | yes | Local expand |
| `yield follow` | — | — | Phase 2 stub |
| `yield verify` | — | — | Phase 3 stub |

Entrypoints: `yield` and `aave-usdc-yield`.

---

## 5. Layout

```text
app.py                   # optional Streamlit UI (pip install -e ".[ui]")
config/default.toml      # addresses, chunk size, db path
config/smoke.toml        # optional tiny-chunk overlay
src/aave_usdc_yield/     # cli, rpc, decode, store, asof, rates, realized, archive_query, …
data/                    # gitignored sqlite + exports
docs/decisions.md        # locked pins + formulas
docs/runbook.md          # ops detail
tests/                   # fixtures + unit tests
.env.example             # ETH_ARCHIVE_RPC_URL=
```

---

## 6. Agent operating notes

1. **Never commit** `.env`, RPC URLs, SQLite, or exports under `data/`.
2. Prefer `--json` for machine parsing.
3. After RPC 429/400 storms: wait, resume `yield backfill` (do not delete DB unless intentionally rediscovering start).
4. For a **single historical block** without full backfill, archive `getReserveData` at that block is acceptable as a one-off (verify path); indexed as-of remains the system of record once backfilled.
5. Before “all-time / since inception” claims: confirm `meta.start_block` matches first USDC `ReserveDataUpdated` near pool activation (~`16291127` era), not a late probe pin.
6. Pitch/narrative docs (if present under `docs/pitch/`) are optional product context — not required to run the tool.

---

## 7. Quick copy-paste (happy path)

```bash
git clone https://github.com/ConnorCink/on-chain-rate-data.git
cd on-chain-rate-data
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set ETH_ARCHIVE_RPC_URL
set -a && source .env && set +a
pytest -q
yield backfill --from-block TIP_MINUS_5000 --to-block TIP   # smoke window first
yield at --block TIP --json
yield realized --from TIP_MINUS_5000 --to TIP --json
```

Replace `TIP` / `TIP_MINUS_5000` with concrete integers from your RPC (`eth_blockNumber`).

---


---

## 8. Streamlit UI (optional)

Local explorer for point rate, realized principal, wealth curve, and analysis prompts. UI deps stay optional so a lean CLI install is unchanged.

**Prerequisites**
- Repo root checkout; Python ≥ 3.11 venv
- Populated SQLite (`data/yield.sqlite` or another path) — or archive RPC for one-off `getReserveData` / date→block
- Optional: `.env` with `ETH_ARCHIVE_RPC_URL` (never commit; app loads it quietly and never prints the value)

```bash
source .venv/bin/activate
pip install -e ".[ui]"
# optional RPC for date→block and archive fallback:
set -a && source .env && set +a
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

**Expected URL:** [http://localhost:8501](http://localhost:8501) (or `http://<host>:8501` when bound to `0.0.0.0`).

**Tabs**
| Tab | Behavior |
|-----|----------|
| Point rate | Block or date → RAY / APR% / APY% / as-of event; DB first, optional archive `getReserveData` |
| Realized / principal | From/to + principal → end value, earned, annualized realized % |
| Wealth curve | Charts index path when DB has history; otherwise backfill instructions |
| Inspiration | Short engineering prompts for cash-sleeve analysis |

Entrypoint file: `app.py` (repo root). Helpers: `aave_usdc_yield.envload`, `aave_usdc_yield.archive_query`.

## 9. Claude Desktop MCP (optional)

Stdio MCP server for point-in-time Aave V3 ETH USDC supply rates via archive `getReserveData`, plus an HTML MCP App panel.

```bash
source .venv/bin/activate
pip install -e ".[mcp]"
# Claude Desktop: see docs/claude-desktop.md for claude_desktop_config.json
# Entry: python -m aave_usdc_yield.mcp_server   OR   aave-usdc-yield-mcp
```

| | |
|--|--|
| Tool | `get_aave_usdc_supply_rate(datetime_iso)` → block meta, APR/APY, RAY, `source=archive_getReserveData` |
| Panel | `ui://aave-usdc-yield/panel` (MCP Apps) · standalone `mcp_app/index.html` |
| Config | Absolute venv python + `-m aave_usdc_yield.mcp_server` + `env.ETH_ARCHIVE_RPC_URL` |

RPC URL is loaded via `envload` / Claude `env` and is never printed.

## License

MIT — see `LICENSE`.
