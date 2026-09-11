"""运行日志服务与 API 测试。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_setup_and_query(tmp_path: Path):
    from app.services import runtime_logging as rl

    rl.reset_for_tests()
    log_dir = rl.setup_runtime_logging("INFO", tmp_path)
    assert log_dir == tmp_path / "logs"
    assert (log_dir / "app.log").exists()

    rl.emit_event(
        source="backend",
        level="INFO",
        category="data",
        message="sync started",
        change={"type": "sync", "from": 0, "to": 10},
    )
    rl.log_access(method="GET", path="/api/watchlist", status=200, duration_ms=12.5)
    accepted = rl.ingest_client_events(
        [
            {
                "level": "INFO",
                "category": "navigation",
                "message": "打开页面 /watchlist",
                "path": "/watchlist",
                "change": {"type": "route", "from": "/", "to": "/watchlist"},
            }
        ]
    )
    assert accepted == 1

    events = rl.query_events(limit=50)
    sources = {e["source"] for e in events}
    assert "backend" in sources
    assert "access" in sources
    assert "ui" in sources

    ui_only = rl.query_events(source="ui", limit=10)
    assert ui_only and ui_only[0]["category"] == "navigation"
    assert ui_only[0]["change"]["to"] == "/watchlist"

    # 敏感字段脱敏
    rl.ingest_client_events(
        [{"message": "login", "detail": {"password": "secret", "user": "a"}}]
    )
    hit = next(e for e in rl.query_events(q="login", limit=20) if e["message"] == "login")
    assert hit["detail"]["password"] == "***"
    assert hit["detail"]["user"] == "a"

    status = rl.get_status()
    assert status["configured"] is True
    assert status["files"]["app.log"] is not None
    assert (log_dir / "ui.log").exists()
    assert (log_dir / "access.log").exists()
    assert (log_dir / "runtime.jsonl").exists()

    cleared = rl.clear_logs(keep_files=True)
    assert cleared["ok"] is True
    assert rl.query_events(limit=10)  # lifecycle clear event remains


def test_runtime_jsonl_rotation(tmp_path: Path, monkeypatch):
    from app.services import runtime_logging as rl

    rl.reset_for_tests()
    log_dir = rl.setup_runtime_logging("INFO", tmp_path)
    jsonl = log_dir / "runtime.jsonl"

    # 阈值调小以便触发滚动, 策略与 app.log 一致: 超限即切换到 .1
    monkeypatch.setattr(rl, "_MAX_FILE_BYTES", 2048)
    for i in range(50):
        rl.emit_event(
            source="backend",
            level="INFO",
            category="data",
            message=f"rotation probe {i} " + "x" * 120,
            mirror_std_log=False,
        )

    rotated = jsonl.with_name("runtime.jsonl.1")
    assert rotated.exists(), "超过阈值后应产生 runtime.jsonl.1"
    assert jsonl.exists() and jsonl.stat().st_size <= 2048 + 1024
    # 备份数量受 _BACKUP_COUNT 限制
    backups = sorted(p.name for p in log_dir.glob("runtime.jsonl.*"))
    assert len(backups) <= rl._BACKUP_COUNT
    # 事件仍完整可查: 缓冲不受滚动影响
    assert any("rotation probe 49" in e["message"] for e in rl.query_events(limit=5))


def test_runtime_logs_api(tmp_path: Path):
    from app.api.runtime_logs import router
    from app.services import runtime_logging as rl

    rl.reset_for_tests()
    rl.setup_runtime_logging("INFO", tmp_path)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.post(
        "/api/runtime-logs/client",
        json={
            "session_id": "test_sess",
            "events": [
                {
                    "level": "INFO",
                    "category": "api",
                    "message": "GET /api/data/version → 200",
                    "method": "GET",
                    "path": "/api/data/version",
                    "status": 200,
                    "duration_ms": 8.2,
                    "change": {"type": "api", "path": "/api/data/version", "status": 200},
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 1

    r = client.get("/api/runtime-logs", params={"source": "ui", "limit": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert any("version" in e["message"] for e in body["events"])

    r = client.get("/api/runtime-logs/status")
    assert r.status_code == 200
    assert r.json()["configured"] is True
    assert r.json()["log_dir"] == str(tmp_path / "logs")

    r = client.delete("/api/runtime-logs", params={"keep_files": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True
