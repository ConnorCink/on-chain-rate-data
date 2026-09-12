"""Streamlit UI for Aave V3 ETH USDC yield exploration.

Run from repo root:
  source .venv/bin/activate
  pip install -e ".[ui]"
  set -a && source .env && set +a   # optional; app also loads .env quietly
  streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Ensure src layout works even if not installed editable
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aave_usdc_yield.archive_query import (  # noqa: E402
    connect_optional,
    fetch_reserve_data,
    resolve_block,
)
from aave_usdc_yield.asof import (  # noqa: E402
    BeforeStartBlockError,
    NoRateDataError,
    resolve_start_block,
    yield_at,
)
from aave_usdc_yield.config import load_config  # noqa: E402
from aave_usdc_yield.envload import load_dotenv, rpc_configured  # noqa: E402
from aave_usdc_yield.realized import (  # noqa: E402
    RealizedYieldError,
    annualized_realized,
    index_ratio,
    realized_between,
    wealth_curve,
)
from aave_usdc_yield.store import RateStore  # noqa: E402

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "streamlit is not installed. Run: pip install -e \".[ui]\""
    ) from exc


def _fmt_pct(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:.{digits}f}%"


def _fmt_ts(ts: int | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _init_session() -> None:
    if "env_loaded" not in st.session_state:
        loaded = load_dotenv(_ROOT / ".env")
        st.session_state["env_loaded"] = str(loaded) if loaded else None


@st.cache_resource
def _get_w3(rpc_present: bool, env_key: str):
    """Cache Web3 client for the process. Never cache the URL string in UI state."""
    if not rpc_present:
        return None
    import os

    url = os.environ.get(env_key)
    return connect_optional(url)


def _sidebar_status(cfg, store: RateStore) -> dict[str, Any]:
    st.sidebar.header("Runtime")
    db_default = str(cfg.db_path)
    db_path = st.sidebar.text_input("SQLite path", value=db_default)
    store = RateStore(db_path)

    n = store.count()
    mn = store.min_block(cfg.usdc_address)
    mx = store.max_block(cfg.usdc_address)
    start = resolve_start_block(cfg, store)
    st.sidebar.markdown(
        f"- **rows:** `{n}`\n"
        f"- **block range:** `{mn}` → `{mx}`\n"
        f"- **start_block:** `{start}`\n"
        f"- **RPC env:** `{'set' if rpc_configured(cfg.rpc_env_key) else 'missing'}` "
        f"(`{cfg.rpc_env_key}` — value never shown)"
    )
    st.sidebar.caption(
        "Indexed coverage only — not a verified since-inception claim. "
        "Confirm meta.start_block ≈ first USDC ReserveDataUpdated near pool activation "
        "before all-time narratives."
    )
    if n == 0:
        st.sidebar.warning("DB empty. Run `yield backfill` or point at a populated SQLite.")
    return {"store": store, "db_path": db_path, "n": n, "min": mn, "max": mx, "start": start}


def _block_or_date_inputs(
    *,
    key_prefix: str,
    default_block: int | None,
    label: str,
) -> tuple[str, int | None, date | None]:
    mode = st.radio(
        f"{label} input",
        ["block", "date"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )
    block: int | None = None
    d: date | None = None
    if mode == "block":
        block = st.number_input(
            f"{label} block",
            min_value=0,
            value=int(default_block or 0),
            step=1,
            key=f"{key_prefix}_block",
        )
    else:
        d = st.date_input(
            f"{label} date (UTC midnight → block via RPC)",
            value=date(2024, 1, 1),
            key=f"{key_prefix}_date",
        )
    return mode, block, d


def tab_point_rate(cfg, store: RateStore, w3) -> None:
    st.subheader("Point rate (instantaneous)")
    st.caption(
        "As-of join on `ReserveDataUpdated` liquidityRate (RAY). "
        "If DB misses coverage and RPC is set, falls back to archive `getReserveData`."
    )
    default = store.max_block(cfg.usdc_address) or store.get_start_block() or 18_000_000
    _mode, block, d = _block_or_date_inputs(
        key_prefix="pt", default_block=default, label="As-of"
    )
    allow_rpc = st.checkbox(
        "Allow archive getReserveData fallback if DB miss",
        value=True,
        key="pt_rpc_fallback",
    )
    if not st.button("Query point rate", type="primary", key="pt_go"):
        return

    try:
        n = resolve_block(w3, block_number=block if _mode == "block" else None, as_of_date=d if _mode == "date" else None)
    except Exception as e:  # noqa: BLE001
        st.error(str(e))
        return

    result: dict[str, Any] | None = None
    err: str | None = None
    try:
        result = yield_at(cfg, store, n)
    except (BeforeStartBlockError, NoRateDataError) as e:
        err = str(e)
        if allow_rpc and w3 is not None:
            with st.spinner(f"DB miss — eth_call getReserveData @ {n}…"):
                try:
                    result = fetch_reserve_data(
                        w3,
                        pool_address=cfg.pool_address,
                        asset=cfg.usdc_address,
                        block_number=n,
                    )
                    err = None
                except Exception as rpc_e:  # noqa: BLE001
                    st.error(f"DB: {err}\nRPC fallback failed: {rpc_e}")
                    return
        else:
            st.error(err)
            if w3 is None:
                st.info("Set ETH_ARCHIVE_RPC_URL in `.env` to enable archive fallback / date→block.")
            return

    assert result is not None
    src = result.get("source", "?")
    st.success(f"Resolved block **{n}** · source=`{src}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("RAY (liquidityRate)", f"{result['liquidity_rate_ray']}")
    c2.metric("Supply APR", _fmt_pct(result["supply_apr"]))
    c3.metric("Supply APY", _fmt_pct(result["supply_apy"]))
    c4.metric("As-of event block", str(result.get("as_of_event_block") or "—"))
    st.caption(
        f"Supply-side liquidityRate only (not borrow). "
        f"APY label=`{result.get('supply_apy_label') or 'continuous_compound_from_apr_aave_utilities'}`."
    )
    st.json(
        {
            "block_number": result["block_number"],
            "block_timestamp": result.get("block_timestamp"),
            "liquidity_rate_ray": result["liquidity_rate_ray"],
            "supply_apr": result["supply_apr"],
            "supply_apy": result["supply_apy"],
            "supply_apy_label": result.get("supply_apy_label"),
            "as_of_event_block": result.get("as_of_event_block"),
            "as_of_tx_hash": result.get("as_of_tx_hash"),
            "source": src,
            "reserve": result.get("reserve"),
        }
    )


def tab_realized(cfg, store: RateStore, w3) -> None:
    st.subheader("Realized / principal")
    st.caption(
        "Wealth from liquidityIndex ratio (passive supplier). "
        "Prefer DB index path; optional endpoint eth_call if DB insufficient."
    )
    updates = store.all_updates_ordered(chain_id=cfg.chain_id, reserve=cfg.usdc_address)
    start = resolve_start_block(cfg, store)
    def_from = start or (int(updates[0]["block_number"]) if updates else 18_000_000)
    def_to = int(updates[-1]["block_number"]) if updates else def_from

    col_a, col_b = st.columns(2)
    with col_a:
        _fm, from_block, from_date = _block_or_date_inputs(
            key_prefix="rz_from", default_block=def_from, label="From"
        )
    with col_b:
        _tm, to_block, to_date = _block_or_date_inputs(
            key_prefix="rz_to", default_block=def_to, label="To"
        )

    principal = st.number_input(
        "Principal (USDC)", min_value=0.0, value=1000.0, step=100.0, key="rz_principal"
    )
    allow_rpc = st.checkbox(
        "Allow archive getReserveData at endpoints if DB index missing",
        value=True,
        key="rz_rpc_fallback",
    )
    if not st.button("Compute realized", type="primary", key="rz_go"):
        return

    try:
        fb = resolve_block(
            w3,
            block_number=from_block if _fm == "block" else None,
            as_of_date=from_date if _fm == "date" else None,
        )
        tb = resolve_block(
            w3,
            block_number=to_block if _tm == "block" else None,
            as_of_date=to_date if _tm == "date" else None,
        )
    except Exception as e:  # noqa: BLE001
        st.error(str(e))
        return

    result: dict[str, Any] | None = None
    try:
        if not updates:
            raise RealizedYieldError("No rate_updates in DB")
        result = realized_between(updates, from_block=fb, to_block=tb)
    except RealizedYieldError as e:
        if not (allow_rpc and w3 is not None):
            st.error(str(e))
            st.info("Backfill index history, or enable RPC fallback with ETH_ARCHIVE_RPC_URL.")
            return
        with st.spinner(f"DB insufficient — eth_call indexes @ {fb} and {tb}…"):
            try:
                a = fetch_reserve_data(
                    w3, pool_address=cfg.pool_address, asset=cfg.usdc_address, block_number=fb
                )
                b = fetch_reserve_data(
                    w3, pool_address=cfg.pool_address, asset=cfg.usdc_address, block_number=tb
                )
                wealth = index_ratio(a["liquidity_index"], b["liquidity_index"])
                ann = annualized_realized(
                    wealth,
                    from_block=fb,
                    to_block=tb,
                    from_timestamp=a.get("last_update_timestamp"),
                    to_timestamp=b.get("last_update_timestamp"),
                )
                result = {
                    "from_block": fb,
                    "to_block": tb,
                    "from_event_block": None,
                    "to_event_block": None,
                    "from_timestamp": a.get("last_update_timestamp"),
                    "to_timestamp": b.get("last_update_timestamp"),
                    "liquidity_index_from": a["liquidity_index"],
                    "liquidity_index_to": b["liquidity_index"],
                    "index_ratio": wealth,
                    "wealth_of_1": wealth,
                    "cumulative_return": wealth - 1.0,
                    "annualized_realized": ann,
                    "annualized_label": "compound_from_index_ratio",
                    "source": "archive_getReserveData_endpoints",
                }
            except Exception as rpc_e:  # noqa: BLE001
                st.error(f"DB: {e}\nRPC fallback failed: {rpc_e}")
                return

    assert result is not None
    end_value = principal * float(result["wealth_of_1"])
    earned = end_value - principal
    st.success(f"source=`{result['source']}` · blocks {fb} → {tb}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("End value", f"{end_value:,.6f} USDC")
    c2.metric("Earned", f"{earned:,.6f} USDC")
    c3.metric("Cumulative", _fmt_pct(result["cumulative_return"]))
    c4.metric("Annualized realized", _fmt_pct(result.get("annualized_realized")))
    st.caption(
        f"Passive supply via liquidityIndex (not borrow). "
        f"Annualized label=`{result.get('annualized_label') or 'compound_from_index_ratio'}` · "
        f"source=`{result.get('source')}`."
    )
    st.json(result)


def tab_wealth(cfg, store: RateStore) -> None:
    st.subheader("Wealth curve")
    st.caption("Sparse cumulative wealth at each stored liquidityIndex update.")
    updates = store.all_updates_ordered(chain_id=cfg.chain_id, reserve=cfg.usdc_address)
    indexed = [
        u
        for u in updates
        if u.get("liquidity_index") is not None and u.get("liquidity_index") != ""
    ]
    if len(indexed) < 2:
        st.warning(
            "Need ≥2 rate_updates with liquidity_index in the DB for a curve.\n\n"
            "**Backfill:**\n"
            "```bash\n"
            "set -a && source .env && set +a\n"
            "yield backfill --db data/yield.sqlite\n"
            "# or a tip window:\n"
            "yield backfill --from-block TIP_MINUS_N --to-block TIP --db data/query.sqlite\n"
            "```"
        )
        return

    start = resolve_start_block(cfg, store)
    def_from = start or int(indexed[0]["block_number"])
    def_to = int(indexed[-1]["block_number"])
    c1, c2, c3 = st.columns(3)
    with c1:
        from_b = st.number_input("From block", min_value=0, value=def_from, step=1, key="wc_from")
    with c2:
        to_b = st.number_input("To block", min_value=0, value=def_to, step=1, key="wc_to")
    with c3:
        principal = st.number_input(
            "Principal (USDC)", min_value=0.01, value=1.0, step=1.0, key="wc_principal"
        )

    if not st.button("Plot wealth curve", type="primary", key="wc_go"):
        return

    points = wealth_curve(
        updates, from_block=int(from_b), to_block=int(to_b), initial_usd=float(principal)
    )
    if not points:
        st.warning("No index points in range. Widen the window or backfill.")
        return

    import pandas as pd

    df = pd.DataFrame(points)
    if df["block_timestamp"].notna().any():
        df["time_utc"] = df["block_timestamp"].apply(
            lambda t: datetime.fromtimestamp(int(t), tz=timezone.utc) if t is not None else None
        )
        chart_df = df.set_index("time_utc")[["wealth_usd"]]
        st.line_chart(chart_df)
    else:
        chart_df = df.set_index("block_number")[["wealth_usd"]]
        st.line_chart(chart_df)

    st.caption(f"{len(points)} points · principal={principal} USDC · source=liquidity_index (DB)")
    st.dataframe(
        df[
            [
                "block_number",
                "block_timestamp",
                "liquidity_index",
                "wealth_usd",
                "cumulative_return",
                "annualized_realized",
            ]
        ],
        use_container_width=True,
    )


def tab_inspiration() -> None:
    st.subheader("Next-analysis prompts (cash-sleeve thesis)")
    st.markdown(
        """
Engineering follow-ups — not pitch copy. Wire these once the all-time index tape is dense enough.

- **Rolling excess vs SOFR** — join realized annualized windows (30d/90d/365d) to a SOFR CSV (`yield compare-sofr`); plot excess spread and hit-rate of outperformance.
- **Worst underperformance windows** — scan sliding windows for min(realized − SOFR); report duration and drawdown of relative wealth vs rolling cash.
- **Utilization ↔ rate** — pull utilization (or borrow rate) alongside `liquidityRate` at event times; regression / regime splits (high util vs idle).
- **Snapshot APY vs index-realized gap** — for each window, integrate instantaneous APR path vs true index ratio; quantify path risk.
- **V2 vs V3 later** — same schema, second protocol pin; compare inception-normalized $1 wealth and rate volatility.
- **Stress / liquidity** — tag days with large index jumps or rate spikes; overlay known market events.
- **Fee / net-of-friction** — if modeling MMF net yield, subtract explicit ops friction assumptions so comparisons stay honest.
- **Coverage QA** — assert `meta.start_block` ≈ first USDC `ReserveDataUpdated` near pool activation before any “since inception” claim.
        """
    )


def main() -> None:
    st.set_page_config(
        page_title="Aave V3 ETH USDC yield",
        page_icon="📈",
        layout="wide",
    )
    _init_session()
    st.title("Aave V3 · ETH · USDC supply yield")
    st.caption(
        "Local explorer over event-indexed SQLite (+ optional archive RPC). "
        "Secrets stay in `.env` — never printed."
    )

    cfg = load_config(_ROOT / "config" / "default.toml")
    # Default DB relative to repo root even if cwd differs
    if not Path(cfg.db_path).is_file():
        alt = _ROOT / "data" / "yield.sqlite"
        if alt.is_file():
            from dataclasses import replace

            cfg = replace(cfg, db_path=alt.resolve())

    status = _sidebar_status(cfg, RateStore(cfg.db_path))
    store: RateStore = status["store"]

    rpc_ok = rpc_configured(cfg.rpc_env_key)
    w3 = None
    if rpc_ok:
        try:
            w3 = _get_w3(True, cfg.rpc_env_key)
        except Exception as e:  # noqa: BLE001
            st.sidebar.error(f"RPC connect failed (URL redacted): {e}")

    tabs = st.tabs(["Point rate", "Realized / principal", "Wealth curve", "Inspiration"])
    with tabs[0]:
        tab_point_rate(cfg, store, w3)
    with tabs[1]:
        tab_realized(cfg, store, w3)
    with tabs[2]:
        tab_wealth(cfg, store)
    with tabs[3]:
        tab_inspiration()


if __name__ == "__main__":
    main()
