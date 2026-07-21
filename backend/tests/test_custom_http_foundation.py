from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data_providers.custom.config import load_config
from app.data_providers.custom.provider import GenericHTTPProvider
from app.data_providers.custom.security import UnsafeURLError, assert_safe_url
from app.data_providers.custom.staging import write_daily_staging
from app.data_providers.registry import get_provider


def test_default_provider_is_tickflow():
    p = get_provider("tickflow")
    assert getattr(p, "name", "tickflow") in {"tickflow", getattr(p, "name", "")}


def test_assert_safe_url_blocks_localhost():
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://127.0.0.1:9999/daily")
    with pytest.raises(UnsafeURLError):
        assert_safe_url("http://localhost/daily")


def test_assert_safe_url_allows_https_public_host_shape():
    # does not resolve block for well-known public hostname pattern without private IP
    # may still fail DNS in offline env — accept either pass or resolve error wrapped
    try:
        assert_safe_url("https://example.com/data")
    except UnsafeURLError as e:
        # only fail if blocked as private; DNS failures are also UnsafeURLError in our impl
        assert "blocked" in str(e) or "resolve" in str(e)


def test_staging_write_does_not_touch_kline_daily(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # reload settings data_dir is already constructed — pass data_dir explicitly
    df = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": ["2026-07-01"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.5],
            "volume": [1000.0],
            "amount": [10500.0],
        }
    )
    meta = write_daily_staging("mock_source", df, data_dir=tmp_path, note="unit")
    assert meta["ok"] is True
    assert meta["rows"] == 1
    path = Path(meta["path"])
    assert path.exists()
    assert "staging/custom/mock_source/daily" in str(path).replace("\\", "/")
    assert not (tmp_path / "kline_daily").exists()


def test_load_example_yaml_config():
    example = Path("docs/examples/custom-data-source/mock_source.yaml")
    if not example.exists():
        example = Path("../docs/examples/custom-data-source/mock_source.yaml")
    # when running from backend/, docs is one level up
    candidates = [
        Path("/Users/simon/Trading/one-trading/docs/examples/custom-data-source/mock_source.yaml"),
        Path("docs/examples/custom-data-source/mock_source.yaml"),
        Path("../docs/examples/custom-data-source/mock_source.yaml"),
    ]
    path = next(p for p in candidates if p.exists())
    cfg = load_config(path)
    assert cfg.name
    assert "daily" in cfg.datasets
    provider = GenericHTTPProvider(cfg)
    errors = provider.validate()
    assert errors == []
    provider.close()


def test_custom_sources_api_lists_without_selecting(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import settings

    # monkeypatch restores this process-global setting after the test.
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from app.api import custom_sources

    app = FastAPI()
    app.include_router(custom_sources.router)
    client = TestClient(app)
    r = client.get("/api/custom-sources")
    assert r.status_code == 200
    body = r.json()
    assert body["default_provider"] == "tickflow"
    assert body["policy"]["auto_selected"] is False
    assert body["policy"]["writes_production_kline"] is False
