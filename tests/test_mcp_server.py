"""MCP server smoke tests (no live RPC / no stdio run)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_panel_html_exists_and_is_mcp_app():
    html_path = REPO / "mcp_app" / "index.html"
    assert html_path.is_file()
    text = html_path.read_text(encoding="utf-8")
    assert "APY" in text
    assert "get_rate_history" in text or "data-window" in text
    assert "bootApp" in text or "text/javascript;base64," in text
    assert html_path.stat().st_size > 100_000  # inlined ext-apps


def test_load_panel_html():
    pytest.importorskip("mcp")
    from aave_usdc_yield.mcp_server import _load_panel_html

    html = _load_panel_html()
    assert "<!DOCTYPE html>" in html
    assert "applyDocumentTheme" in html or "base64," in html


def test_build_server_registers_tools_and_ui_resource():
    pytest.importorskip("mcp")
    from aave_usdc_yield.mcp_server import UI_RESOURCE_URI, build_server

    mcp = build_server()
    assert mcp.name == "aave-usdc-yield"

    async def _list():
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        return tools, resources

    tools, resources = asyncio.run(_list())
    by_name = {t.name: t for t in tools}
    assert "get_aave_usdc_supply_rate" in by_name
    assert "get_rate_history" in by_name
    rate_meta = by_name["get_aave_usdc_supply_rate"].meta or {}
    assert rate_meta.get("ui", {}).get("resourceUri") == UI_RESOURCE_URI
    hist_meta = by_name["get_rate_history"].meta or {}
    assert hist_meta.get("ui", {}).get("visibility") == ["app"]
    uris = {str(r.uri) for r in resources}
    assert UI_RESOURCE_URI in uris
    assert "resource://aave-usdc-yield/panel.html" in uris


def test_ui_resource_mime_and_meta():
    pytest.importorskip("mcp")
    from aave_usdc_yield.mcp_server import UI_RESOURCE_URI, build_server

    mcp = build_server()

    async def _read():
        return list(await mcp.read_resource(UI_RESOURCE_URI))

    items = asyncio.run(_read())
    assert len(items) == 1
    assert items[0].mime_type == "text/html;profile=mcp-app"
    assert items[0].meta is not None
    assert "ui" in items[0].meta
