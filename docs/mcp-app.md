# Aave USDC MCP App

SEP-1865 MCP App for Aave V3 ETH USDC supply rates.

## Architecture

Python mcp_server via mcp.server.apps; UI mcp_app/index.html built by build_panel.py.
Inlines ext-apps 2.0.0 app-with-deps from .vendor/ext-apps/.
Host theme helpers; autoResize true; archive_query caches.


## Install

pip install -e ".[mcp]" then run: python mcp_app/build_panel.py

Set ETH_ARCHIVE_RPC_URL in env or .env (never commit).

## Claude Desktop

Config file on macOS: Library/Application Support/Claude/claude_desktop_config.json

Server entry name: aave-usdc-yield
command: ABS_PATH/.venv/bin/python
args: -m aave_usdc_yield.mcp_server
env key: ETH_ARCHIVE_RPC_URL = your archive HTTPS URL

Or command ABS_PATH/.venv/bin/aave-usdc-yield-mcp with no args.

## Tools

get_aave_usdc_supply_rate(datetime_iso): model+app, resourceUri ui://aave-usdc-yield/mcp-app.html, text + structuredContent

get_rate_history(start_iso, end_iso, points): app-only visibility, cached archive samples

Presets 24h/7d/30d/90d and Refresh use app-only tools (zero model tokens).

## Verify

1. MCP Inspector on the stdio server
2. basic-host from ext-apps v2.0.0 (HTTP sidecar may be needed)
3. Claude last — iframe caveat issue 671 on modelcontextprotocol/ext-apps

Widget does no direct network; data only via MCP tools.
