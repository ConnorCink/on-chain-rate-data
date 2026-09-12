#!/usr/bin/env python3
"""Assemble mcp_app/index.html: panel CSS/JS + inlined @modelcontextprotocol/ext-apps app-with-deps.

Produces a single HTML file suitable for MCP App resources (no vite required at runtime).
Equivalent outcome to vite-plugin-singlefile when Node is unavailable.
"""
from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SDK = REPO / ".vendor" / "ext-apps" / "package" / "dist" / "src" / "app-with-deps.js"


def build() -> Path:
    if not SDK.is_file():
        raise SystemExit(
            f"Missing vendored SDK at {SDK}. Extract @modelcontextprotocol/ext-apps@2.0.0 "
            "app-with-deps.js there (see docs/claude-desktop.md)."
        )
    css = (ROOT / "src" / "panel.css").read_text(encoding="utf-8")
    app_js = (ROOT / "src" / "app.js").read_text(encoding="utf-8")
    sdk = SDK.read_text(encoding="utf-8")
    sdk_url = "data:text/javascript;base64," + base64.b64encode(sdk.encode()).decode()
    app_url = "data:text/javascript;base64," + base64.b64encode(app_js.encode()).decode()
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Aave V3 USDC Supply Yield</title>
  <style>
{css}
  </style>
</head>
<body>
  <div id="app">
    <article class="card" aria-label="Aave USDC supply yield">
      <div class="eyebrow">
        <span class="badge">Aave V3 · ETH USDC</span>
        <span>archive getReserveData</span>
      </div>
      <h1>Supply yield</h1>
      <div class="hero">
        <div class="stat">
          <div class="label">APY</div>
          <div class="value" id="apy">—</div>
        </div>
        <div class="stat">
          <div class="label">APR</div>
          <div class="value" id="apr">—</div>
        </div>
      </div>
      <div class="meta">
        <dl>
          <dt>Block</dt>
          <dd id="block">—</dd>
        </dl>
        <dl>
          <dt>Block time (UTC)</dt>
          <dd id="time">—</dd>
        </dl>
      </div>
      <div class="chart-wrap" aria-label="APR history chart">
        <canvas id="chart" width="360" height="160"></canvas>
      </div>
      <div class="controls" id="presets">
        <button type="button" data-window="24h" aria-pressed="false">24h</button>
        <button type="button" data-window="7d" aria-pressed="true">7d</button>
        <button type="button" data-window="30d" aria-pressed="false">30d</button>
        <button type="button" data-window="90d" aria-pressed="false">90d</button>
        <button type="button" id="refresh">Refresh</button>
      </div>
      <div id="status"></div>
      <p class="foot">
        Presets and refresh use app-only tools (no chat / model tokens).
        Host theme applied via MCP Apps style helpers.
      </p>
    </article>
  </div>
  <script type="module">
    import {{
      App,
      applyDocumentTheme,
      applyHostStyleVariables,
      applyHostFonts,
    }} from "{sdk_url}";
    import {{ bootApp }} from "{app_url}";
    bootApp({{ App, applyDocumentTheme, applyHostStyleVariables, applyHostFonts }});
  </script>
</body>
</html>
"""
    out = ROOT / "index.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build()
    print(f"Wrote {p} ({p.stat().st_size} bytes)")
