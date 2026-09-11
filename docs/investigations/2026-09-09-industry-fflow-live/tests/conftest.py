from __future__ import annotations

import inspect
import socket
import sys
from pathlib import Path

import pytest

MAIN_BACKEND = Path("/Users/simon/Trading/one-trading/backend")
if str(MAIN_BACKEND) not in sys.path:
    sys.path.insert(0, str(MAIN_BACKEND))


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise RuntimeError("network disabled in isolation tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture(autouse=True)
def _assert_main_tree_modules():
    from app.api import pipeline as pipeline_api
    from app.jobs import daily_pipeline
    from app.services.ext_data import write_ext_parquet
    from app.services.free_sources import fund_flow as ff

    root = Path("/Users/simon/Trading/one-trading")
    assert Path(inspect.getfile(ff)).resolve() == root / "backend/app/services/free_sources/fund_flow.py"
    assert Path(inspect.getfile(daily_pipeline)).resolve() == root / "backend/app/jobs/daily_pipeline.py"
    assert Path(inspect.getfile(write_ext_parquet)).resolve() == root / "backend/app/services/ext_data.py"
    assert Path(inspect.getfile(pipeline_api)).resolve() == root / "backend/app/api/pipeline.py"
    yield
