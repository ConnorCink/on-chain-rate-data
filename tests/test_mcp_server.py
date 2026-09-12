"""MCP server smoke tests (no live RPC / no stdio run)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_panel_html_exists_and_references_bg():
    html_path = REPO / "mcp_app" / "index.html"
    bg = REPO / "mcp_app" / "assets" / "hill-sun-bg.png"
    assert html_path.is_file()
    assert bg.is_file()
    text = html_path.read_text(encoding="utf-8")
    assert "hill-sun-bg.png" in text
    assert "APY" in text


def test_load_panel_inlines_bg():
    pytest.importorskip("mcp")
    from aave_usdc_yield.mcp_server import _load_panel_html

    html = _load_panel_html(inline_bg=True)
    assert "data:image/png;base64," in html
    assert "backdrop-filter" in html


def test_build_server_registers_tool_and_ui_resource():
    pytest.importorskip("mcp")
    from aave_usdc_yield.mcp_server import UI_RESOURCE_URI, build_server

    mcp = build_server()
    assert mcp.name == "aave-usdc-yield"

    async def _list():
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        return tools, resources

    tools, resources = asyncio.run(_list())
    names = [t.name for t in tools]
    assert "get_aave_usdc_supply_rate" in names
    uris = {str(r.uri) for r in resources}
    assert UI_RESOURCE_URI in uris
    assert "resource://aave-usdc-yield/panel.html" in uris
