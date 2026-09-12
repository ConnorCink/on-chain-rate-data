"""Claude Desktop–connectable MCP App server for Aave V3 ETH USDC supply rates.

SEP-1865 / MCP Apps (`io.modelcontextprotocol/ui`) via `mcp.server.apps`.

Entry:
  python -m aave_usdc_yield.mcp_server
  aave-usdc-yield-mcp

Requires: pip install -e ".[mcp]"
Never prints ETH_ARCHIVE_RPC_URL.

Architecture note
-----------------
Primary runtime is this Python server (SDK `mcp.server.apps`) because the
interactive UI is a single HTML resource bundling
`@modelcontextprotocol/ext-apps` `app-with-deps` (assembled by
`mcp_app/build_panel.py`). A TypeScript `mcp-app/` scaffold may be added later
for hosts that prefer `registerAppTool` from `@modelcontextprotocol/ext-apps/server`;
wire format is the same.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .envload import load_dotenv

try:
    from mcp.types import CallToolResult, TextContent
except ImportError:  # pragma: no cover
    CallToolResult = Any  # type: ignore[misc, assignment]
    TextContent = Any  # type: ignore[misc, assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_APP_HTML = REPO_ROOT / "mcp_app" / "index.html"
UI_RESOURCE_URI = "ui://aave-usdc-yield/mcp-app.html"


def _require_mcp():
    try:
        from mcp.server.apps import APP_MIME_TYPE, Apps, ResourceCsp, client_supports_apps
        from mcp.server.mcpserver import MCPServer
        from mcp.types import CallToolResult, TextContent
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "MCP SDK not installed. Run: pip install -e \".[mcp]\" "
            "(or pip install 'mcp>=1.0')"
        ) from exc
    return Apps, ResourceCsp, MCPServer, CallToolResult, TextContent, client_supports_apps, APP_MIME_TYPE


def _load_panel_html() -> str:
    """Load assembled single-file MCP App HTML (ext-apps app-with-deps inlined)."""
    if not MCP_APP_HTML.is_file():
        raise FileNotFoundError(
            f"Missing MCP app HTML at {MCP_APP_HTML}. "
            "Run: python mcp_app/build_panel.py"
        )
    return MCP_APP_HTML.read_text(encoding="utf-8")


def _rpc_web3():
    from .archive_query import connect_optional
    from .config import load_config

    cfg = load_config()
    rpc = os.environ.get(cfg.rpc_env_key) or cfg.rpc_url
    if not rpc or not str(rpc).strip():
        raise RuntimeError(
            f"Missing {cfg.rpc_env_key}. Set it in Claude Desktop mcpServers.env "
            "or in the project .env (value is never logged)."
        )
    w3 = connect_optional(rpc)
    if w3 is None:
        raise RuntimeError("Failed to connect to archive RPC (URL not shown).")
    return w3, cfg


def _format_rate_summary(data: dict[str, Any]) -> str:
    apr = data.get("supply_apr")
    apy = data.get("supply_apy")
    block = data.get("block_number")
    ts = data.get("block_timestamp_iso") or data.get("block_timestamp")
    try:
        apr_s = f"{float(apr) * 100:.2f}%"
        apy_s = f"{float(apy) * 100:.2f}%"
    except (TypeError, ValueError):
        apr_s, apy_s = "—", "—"
    return (
        f"Aave V3 ETH USDC supply APR {apr_s} / APY {apy_s} "
        f"at block {block} ({ts}). Source: archive getReserveData."
    )


def _format_history_summary(data: dict[str, Any]) -> str:
    pts = data.get("points") or []
    n = len(pts)
    if not pts:
        return "No history points."
    first, last = pts[0], pts[-1]
    return (
        f"Aave V3 ETH USDC APR history: {n} samples from "
        f"{first.get('timestamp_iso')} → {last.get('timestamp_iso')} "
        f"(last APR {float(last['supply_apr']) * 100:.2f}%)."
    )


def build_server():
    """Construct MCPServer with model tool + app-only history + HTML MCP App."""
    (
        Apps,
        ResourceCsp,
        MCPServer,
        CallToolResult,
        TextContent,
        client_supports_apps,
        APP_MIME_TYPE,
    ) = _require_mcp()

    load_dotenv()

    apps = Apps()
    html = _load_panel_html()
    # CSP on resource (flows to contents[] _meta.ui via SDK). Widget uses only
    # app-bridge tools — no direct network — so keep CSP minimal.
    apps.add_html_resource(
        UI_RESOURCE_URI,
        html,
        name="aave-usdc-yield-panel",
        title="Aave USDC Supply Yield",
        description=(
            "Inline MCP App: current Aave V3 ETH USDC supply APR/APY with "
            "history chart and 24h/7d/30d/90d presets."
        ),
        prefers_border=True,
        # No connectDomains/resourceDomains: widget uses only app-only tools
        # (no direct network). CSP key omitted rather than empty allowlists.
    )

    @apps.tool(
        resource_uri=UI_RESOURCE_URI,
        visibility=["model", "app"],
        name="get_aave_usdc_supply_rate",
        title="Aave USDC supply rate",
        description=(
            "Archive eth_call getReserveData for Aave V3 Ethereum USDC at the "
            "latest block with timestamp <= the given ISO datetime. Returns "
            "block_number, block_timestamp, supply_apr, supply_apy, "
            "liquidity_rate_ray, and source. Hosts with MCP Apps render the "
            "inline yield panel; text-only hosts still get a one-line summary."
        ),
    )
    def get_aave_usdc_supply_rate(datetime_iso: str) -> CallToolResult:
        """Resolve ISO datetime → block → Aave V3 USDC supply APR/APY."""
        from .archive_query import query_supply_rate_at_datetime_cached

        w3, cfg = _rpc_web3()
        data = query_supply_rate_at_datetime_cached(
            w3,
            datetime_iso,
            pool_address=cfg.pool_address,
            asset=cfg.usdc_address,
        )
        summary = _format_rate_summary(data)
        return CallToolResult(
            content=[TextContent(type="text", text=summary)],
            structured_content=data,
        )

    mcp = MCPServer(
        name="aave-usdc-yield",
        title="Aave USDC Yield",
        description=(
            "Point-in-time Aave V3 Ethereum USDC supply rates via archive "
            "getReserveData, plus an HTML MCP App panel with history chart."
        ),
        instructions=(
            "Call get_aave_usdc_supply_rate with an ISO-8601 datetime "
            "(timezone optional; default UTC). Example: 2024-06-15T18:00:00Z. "
            "Chart presets are handled inside the App via get_rate_history "
            "(app-only; do not call it yourself unless debugging)."
        ),
        extensions=[apps],
    )

    @mcp.tool(
        name="get_rate_history",
        title="Aave USDC rate history",
        description=(
            "App-only: sample archive supply APR/APY between start_iso and "
            "end_iso (inclusive endpoints) at `points` evenly spaced timestamps. "
            "Cached aggressively. Not for the model — UI chart presets only."
        ),
        meta={"ui": {"visibility": ["app"]}},
    )
    def get_rate_history(
        start_iso: str,
        end_iso: str,
        points: int = 28,
    ) -> CallToolResult:
        from .archive_query import query_supply_rate_history

        w3, cfg = _rpc_web3()
        data = query_supply_rate_history(
            w3,
            start_iso,
            end_iso,
            int(points),
            pool_address=cfg.pool_address,
            asset=cfg.usdc_address,
        )
        return CallToolResult(
            content=[TextContent(type="text", text=_format_history_summary(data))],
            structured_content=data,
        )

    # Plain HTML resource for hosts that list resources without Apps capability.
    @mcp.resource(
        "resource://aave-usdc-yield/panel.html",
        name="yield_panel_html",
        title="Yield panel (HTML)",
        description="Same panel HTML as the MCP App; MIME text/html.",
        mime_type="text/html",
    )
    def yield_panel_html() -> str:
        return _load_panel_html()

    # Silence unused import warnings in type checkers; capability helper
    # is available for future branching.
    _ = (client_supports_apps, APP_MIME_TYPE, datetime, timezone)
    return mcp


def main() -> None:
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
