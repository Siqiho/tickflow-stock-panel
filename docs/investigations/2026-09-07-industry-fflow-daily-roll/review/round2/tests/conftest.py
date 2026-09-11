from __future__ import annotations

import importlib.util
import inspect
import socket
import sys
from pathlib import Path

import pytest

TASK_DIR = Path(__file__).resolve().parents[3]
OVERLAY_BACKEND = TASK_DIR / "overlay" / "backend"
MAIN_BACKEND = Path("/Users/simon/Trading/one-trading/backend")

if str(MAIN_BACKEND) not in sys.path:
    sys.path.insert(0, str(MAIN_BACKEND))


def _load_overlay_module(fullname: str, relpath: str):
    parts = fullname.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        if pkg not in sys.modules:
            __import__(pkg)
    path = OVERLAY_BACKEND / relpath
    spec = importlib.util.spec_from_file_location(fullname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load overlay module {fullname} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module


ext_data_mod = _load_overlay_module("app.services.ext_data", "app/services/ext_data.py")
fund_flow_mod = _load_overlay_module(
    "app.services.free_sources.fund_flow",
    "app/services/free_sources/fund_flow.py",
)
daily_pipeline_mod = _load_overlay_module(
    "app.jobs.daily_pipeline",
    "app/jobs/daily_pipeline.py",
)
pipeline_api_mod = _load_overlay_module("app.api.pipeline", "app/api/pipeline.py")
sys.modules["app.services"].ext_data = ext_data_mod
sys.modules["app.services.free_sources"].fund_flow = fund_flow_mod
sys.modules["app.jobs"].daily_pipeline = daily_pipeline_mod
sys.modules["app.api"].pipeline = pipeline_api_mod


@pytest.fixture(autouse=True)
def _reset_pipeline_guard():
    daily_pipeline_mod._reset_pipeline_guard_for_tests()
    yield
    daily_pipeline_mod._reset_pipeline_guard_for_tests()


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise RuntimeError("network disabled in round2 review tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture(scope="session", autouse=True)
def _assert_overlay_loaded():
    assert "overlay" in Path(inspect.getfile(fund_flow_mod)).parts
    assert "overlay" in Path(inspect.getfile(daily_pipeline_mod)).parts
    assert "overlay" in Path(inspect.getfile(ext_data_mod)).parts
    assert "overlay" in Path(inspect.getfile(pipeline_api_mod)).parts
