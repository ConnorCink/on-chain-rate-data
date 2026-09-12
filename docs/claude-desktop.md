# Claude Desktop — Aave USDC yield MCP

Minimal stdio MCP server exposing archive `getReserveData` for **Aave V3 Core (Ethereum) USDC** supply rates, plus an HTML MCP App panel.

## Install

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[mcp]"
```

Set `ETH_ARCHIVE_RPC_URL` to an archive-capable Ethereum HTTPS endpoint (never commit the value). The server also loads a project `.env` via `envload` if present; Claude Desktop `env` overrides are preferred for demos.

## `claude_desktop_config.json`

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`  
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Replace the absolute path placeholders with your checkout and venv:

```json
{
  "mcpServers": {
    "aave-usdc-yield": {
      "command": "/ABS/PATH/TO/on-chain-rate-data/.venv/bin/python",
      "args": ["-m", "aave_usdc_yield.mcp_server"],
      "env": {
        "ETH_ARCHIVE_RPC_URL": "https://YOUR-ARCHIVE-RPC-ENDPOINT"
      }
    }
  }
}
```

Equivalent console script (same venv):

```json
{
  "mcpServers": {
    "aave-usdc-yield": {
      "command": "/ABS/PATH/TO/on-chain-rate-data/.venv/bin/aave-usdc-yield-mcp",
      "args": [],
      "env": {
        "ETH_ARCHIVE_RPC_URL": "https://YOUR-ARCHIVE-RPC-ENDPOINT"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config. Confirm the server appears under MCP / tools; call `get_aave_usdc_supply_rate` with an ISO datetime such as `2024-06-15T18:00:00Z`.

## Tool

| Tool | Args | Returns |
|------|------|---------|
| `get_aave_usdc_supply_rate` | `datetime_iso: str` | `block_number`, `block_timestamp`, `supply_apr`, `supply_apy`, `liquidity_rate_ray`, `source` (`archive_getReserveData`) |

Timezone optional; naive strings default to **UTC**. Resolution uses the latest Ethereum block with `timestamp <=` that instant (not date-only midnight).

## Visual panel

- **MCP App:** resource `ui://aave-usdc-yield/panel` (`text/html;profile=mcp-app`), bound to the tool when the host supports MCP Apps.
- **Also:** `resource://aave-usdc-yield/panel.html` as plain `text/html`.
- **Standalone:** open `mcp_app/index.html` in a browser (background: `mcp_app/assets/hill-sun-bg.png`).

The server inlines the background PNG as a data-URI for iframe hosts so the glass card still sits on the hill/sun plate.

## Security notes

- Never put real RPC URLs in git or chat logs.
- Prefer the Claude Desktop `env` block over shell-exported secrets when demoing.
