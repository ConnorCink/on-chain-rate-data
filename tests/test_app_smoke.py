"""Light smoke: app helpers import; streamlit app module loads if ui extra present."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_archive_and_env_modules_importable():
    from aave_usdc_yield import archive_query, envload

    assert hasattr(archive_query, "fetch_reserve_data")
    assert hasattr(envload, "load_dotenv")


def test_app_py_exists():
    assert (ROOT / "app.py").is_file()


@pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None,
    reason="streamlit optional; pip install -e '.[ui]'",
)
def test_app_module_compiles():
    path = ROOT / "app.py"
    spec = importlib.util.spec_from_file_location("aave_yield_streamlit_app", path)
    assert spec and spec.loader
    # Loading executes imports; streamlit present so should succeed
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "tab_inspiration")
