"""CLI: yield at|backfill|materialize|follow|verify|discover-start"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .asof import BeforeStartBlockError, NoRateDataError, yield_at
from .backfill import AAVE_V3_ETH_SEARCH_FLOOR, backfill
from .config import load_config
from .materialize import materialize_range
from .rpc import discover_first_usdc_update_block, make_web3
from .store import RateStore


def _cfg(config: str | None):
    return load_config(Path(config) if config else None)


@click.group()
@click.version_option(package_name="aave-usdc-yield")
def main() -> None:
    """Aave V3 Ethereum USDC instantaneous supply yield (event-indexed)."""


@main.command("at")
@click.option("--block", "block_number", required=True, type=int, help="Block number N")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path(), help="Override SQLite path")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON")
def cmd_at(block_number: int, config_path: str | None, db_path: str | None, as_json: bool) -> None:
    """Point query: instantaneous USDC supply yield at block N (as-of join)."""
    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    try:
        result = yield_at(cfg, store, block_number)
    except (BeforeStartBlockError, NoRateDataError) as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(2)
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"block_number:        {result['block_number']}")
        click.echo(f"as_of_event_block:   {result['as_of_event_block']}")
        click.echo(f"liquidity_rate_ray:  {result['liquidity_rate_ray']}")
        click.echo(f"supply_apr:          {result['supply_apr']:.10%}")
        click.echo(f"supply_apy:          {result['supply_apy']:.10%}  ({result['supply_apy_label']})")
        click.echo(f"source:              {result['source']}")
        if result.get("block_timestamp") is not None:
            click.echo(f"block_timestamp:     {result['block_timestamp']}")


@main.command("backfill")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path())
@click.option("--from-block", "from_block", default=None, type=int)
@click.option("--to-block", "to_block", default=None, type=int)
def cmd_backfill(
    config_path: str | None,
    db_path: str | None,
    from_block: int | None,
    to_block: int | None,
) -> None:
    """Backfill USDC ReserveDataUpdated logs → SQLite rate_updates."""
    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    try:
        stats = backfill(
            cfg,
            store,
            from_block=from_block,
            to_block=to_block,
            progress=lambda m: click.echo(m, err=True),
        )
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(json.dumps(stats, indent=2))


@main.command("discover-start")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path())
@click.option("--from-block", "from_block", default=AAVE_V3_ETH_SEARCH_FLOOR, type=int)
def cmd_discover_start(
    config_path: str | None, db_path: str | None, from_block: int
) -> None:
    """Empirically find first USDC ReserveDataUpdated block and store as start_block."""
    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    rpc = cfg.require_rpc_url()
    w3 = make_web3(rpc)
    found = discover_first_usdc_update_block(
        w3,
        pool_address=cfg.pool_address,
        usdc_address=cfg.usdc_address,
        search_from=from_block,
        chunk_size=max(cfg.log_chunk_size, 20_000),
    )
    if found is None:
        click.echo("error: no USDC ReserveDataUpdated found", err=True)
        sys.exit(1)
    store.set_start_block(found)
    click.echo(json.dumps({"start_block": found, "stored_in": str(store.db_path)}))


@main.command("materialize")
@click.option("--from", "from_block", required=True, type=int)
@click.option("--to", "to_block", required=True, type=int)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path())
@click.option("--out", "out_path", default=None, type=click.Path(), help="Optional JSONL path")
def cmd_materialize(
    from_block: int,
    to_block: int,
    config_path: str | None,
    db_path: str | None,
    out_path: str | None,
) -> None:
    """Dense every-block series from sparse events (local; no per-block eth_call)."""
    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    rows = materialize_range(
        store,
        chain_id=cfg.chain_id,
        reserve=cfg.usdc_address,
        from_block=from_block,
        to_block=to_block,
    )
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        click.echo(f"wrote {len(rows)} rows → {path}")
    else:
        click.echo(json.dumps({"rows": len(rows), "from": from_block, "to": to_block}))
        if rows:
            click.echo(json.dumps(rows[0]))
            if len(rows) > 1:
                click.echo(json.dumps(rows[-1]))


@main.command("follow")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path())
def cmd_follow(config_path: str | None, db_path: str | None) -> None:
    """Tip follower (Phase 2 stub)."""
    from .follow import follow_tip

    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    try:
        follow_tip(cfg, store)
    except NotImplementedError as e:
        click.echo(f"stub: {e}", err=True)
        sys.exit(3)


@main.command("verify")
@click.option("--blocks", required=True, help="Comma-separated block numbers")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--db", "db_path", default=None, type=click.Path())
def cmd_verify(blocks: str, config_path: str | None, db_path: str | None) -> None:
    """Archive eth_call spot-check (Phase 3 stub)."""
    from .verify import verify_blocks

    cfg = _cfg(config_path)
    store = RateStore(db_path or cfg.db_path)
    blks = [int(x.strip()) for x in blocks.split(",") if x.strip()]
    try:
        verify_blocks(cfg, store, blks)
    except NotImplementedError as e:
        click.echo(f"stub: {e}", err=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
