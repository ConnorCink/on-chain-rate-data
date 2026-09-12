"""Claude Desktop–connectable MCP server for Aave V3 ETH USDC supply rates.

Entry:
  python -m aave_usdc_yield.mcp_server
  aave-usdc-yield-mcp

Requires optional dep: pip install -e ".[mcp]"
Never prints ETH_ARCHIVE_RPC_URL.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from .envload import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_APP_HTML = REPO_ROOT / "mcp_app" / "index.html"
MCP_APP_BG = REPO_ROOT / "mcp_app" / "assets" / "hill-sun-bg.png"
UI_RESOURCE_URI = "ui://aave-usdc-yield/panel"


def _require_mcp():
    try:
        from mcp.server.apps import Apps, ResourceCsp
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "MCP SDK not installed. Run: pip install -e \".[mcp]\" "
            "(or pip install 'mcp>=1.0')"
        ) from exc
    return Apps, ResourceCsp, MCPServer


def _load_panel_html(*, inline_bg: bool = True) -> str:
    """Load mcp_app/index.html; inline hill-sun bg as data-URI for MCP iframe."""
    if not MCP_APP_HTML.is_file():
        raise FileNotFoundError(f"Missing MCP app HTML at {MCP_APP_HTML}")
    html = MCP_APP_HTML.read_text(encoding="utf-8")
    if inline_bg and MCP_APP_BG.is_file():
        b64 = base64.b64encode(MCP_APP_BG.read_bytes()).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"
        # Prefer CSS var path used by the panel script/stylesheet.
        html = html.replace(
            'var bg = "assets/hill-sun-bg.png";',
            f'var bg = "{data_uri}";',
        )
        html = html.replace(
            "assets/hill-sun-bg.png",
            data_uri,
        )
    elif inline_bg and not MCP_APP_BG.is_file():
        # CSS gradient fallback already in stylesheet when --bg-image unset/fails.
        pass
    return html


def build_server():
    """Construct MCPServer with supply-rate tool + HTML MCP App panel."""
    Apps, ResourceCsp, MCPServer = _require_mcp()

    load_dotenv()

    apps = Apps()
    html = _load_panel_html(inline_bg=True)
    apps.add_html_resource(
        UI_RESOURCE_URI,
        html,
        name="aave-usdc-yield-panel",
        title="Aave USDC Supply Yield",
        description="Glassmorphism panel for Aave V3 ETH USDC supply APR/APY.",
        prefers_border=True,
        csp=ResourceCsp(
            # data: images are embedded; no external connect needed for panel.
            resource_domains=["*"],
        ),
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
            "liquidity_rate_ray, and source."
        ),
    )
    def get_aave_usdc_supply_rate(datetime_iso: str) -> dict:
        """Resolve ISO datetime → block → Aave V3 USDC supply APR/APY."""
        from .archive_query import connect_optional, query_supply_rate_at_datetime
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
        return query_supply_rate_at_datetime(
            w3,
            datetime_iso,
            pool_address=cfg.pool_address,
            asset=cfg.usdc_address,
        )

    # Also expose a plain resource for hosts that list resources without Apps.
    mcp = MCPServer(
        name="aave-usdc-yield",
        title="Aave USDC Yield",
        description=(
            "Point-in-time Aave V3 Ethereum USDC supply rates via archive "
            "getReserveData, plus an HTML MCP App panel."
        ),
        instructions=(
            "Call get_aave_usdc_supply_rate with an ISO-8601 datetime "
            "(timezone optional; default UTC). Example: 2024-06-15T18:00:00Z."
        ),
        extensions=[apps],
    )

    @mcp.resource(
        "resource://aave-usdc-yield/panel.html",
        name="yield_panel_html",
        title="Yield panel (HTML)",
        description="Same polished panel as the MCP App; MIME text/html.",
        mime_type="text/html",
    )
    def yield_panel_html() -> str:
        return _load_panel_html(inline_bg=True)

    return mcp


def main() -> None:
    mcp = build_server()
    # stdio transport for Claude Desktop
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
