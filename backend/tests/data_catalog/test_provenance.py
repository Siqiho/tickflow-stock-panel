from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data_catalog.api import router
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.definitions import DATASET_DEFINITIONS, get_dataset_definition
from app.data_catalog.models import DatasetState, SourceHealth, SyncRun
from app.data_catalog.service import CatalogService
from app.services.ext_data import ExtConfig, ExtField, PullConfig


def _service(tmp_path: Path) -> CatalogService:
    return CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())


def _client(service: CatalogService) -> TestClient:
    app = FastAPI()
    app.state.catalog_service = service
    app.include_router(router)
    return TestClient(app)


def _state(dataset_id: str, *, lineage: list[dict] | None = None) -> DatasetState:
    definition = get_dataset_definition(dataset_id)
    return DatasetState(
        dataset_id=dataset_id,
        schema_version=definition.descriptor.schema_version,
        unit_version=definition.descriptor.unit_version,
        quality_status="healthy",
        row_count=1,
        symbol_count=1,
        managed_bytes=128,
        latest_time="2026-07-31",
        last_run_id=f"run-{dataset_id}",
        updated_at="2026-08-01T09:00:00Z",
        payload={
            "file_count": 1,
            "lineage": lineage or [],
            "coverage": [],
            "scan_errors": [],
        },
    )


def _run(dataset_id: str, *, status: str = "succeeded") -> SyncRun:
    return SyncRun(
        run_id=f"run-{dataset_id}",
        dataset_id=dataset_id,
        provider="public",
        operation=f"sync:{dataset_id}",
        started_at="2026-08-01T08:00:00Z",
        finished_at="2026-08-01T08:01:00Z",
        status=status,
        rows_fetched=1,
        rows_published=1,
        quality_status="healthy" if status == "succeeded" else "failed",
        error_code=None if status == "succeeded" else "provider_failed",
    )


def _write_ext_config(tmp_path: Path, config: ExtConfig) -> None:
    path = tmp_path / "ext_data" / config.id / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False), encoding="utf-8")


def test_every_catalog_dataset_has_dedicated_explanation() -> None:
    """守护: 新增数据集必须同步登记中文说明, 否则来源追踪只能显示兜底文案。"""
    from app.data_catalog.provenance_registry import SUBJECT_EXPLANATIONS

    missing = [
        definition.descriptor.dataset_id
        for definition in DATASET_DEFINITIONS
        if definition.descriptor.dataset_id not in SUBJECT_EXPLANATIONS
    ]
    assert missing == [], f"这些数据集缺少 SUBJECT_EXPLANATIONS 中文说明: {missing}"
    for subject_id, entry in SUBJECT_EXPLANATIONS.items():
        for key in ("category", "cadence", "description", "provides"):
            assert entry.get(key), f"{subject_id} 的 {key} 不能为空"


def test_source_provenance_returns_catalog_definitions_and_extensions_without_rescan_or_write(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.rescan = lambda dataset_id=None: (_ for _ in ()).throw(AssertionError("rescan called"))  # type: ignore[method-assign]
    service.control_db.upsert_dataset_state(
        _state(
            "stock_daily",
            lineage=[
                {
                    "source": "tickflow",
                    "fetched_at": "2026-08-01T08:00:00Z",
                    "unit_version": "canonical_daily_v1",
                    "quality_status": "healthy",
                    "artifact_path": "kline_daily/date=2026-07-31/part.parquet",
                }
            ],
        )
    )
    service.control_db.upsert_dataset_state(_state("stock_adj_factor"))
    service.control_db.upsert_sync_run(_run("stock_daily"))
    service.control_db.upsert_source_health(
        SourceHealth(
            provider="public",
            operation="sync:stock_adj_factor",
            last_failure_at="2026-08-01T07:00:00Z",
            consecutive_failures=2,
            last_error_code="timeout",
        )
    )
    with service.control_db.transaction() as connection:
        connection.executescript(
            """
            CREATE TABLE dataset_policies (
                dataset_id TEXT PRIMARY KEY, phase TEXT NOT NULL,
                max_lag_trading_days INTEGER, sync_mode TEXT, schedule_cron TEXT,
                source_policy_json TEXT NOT NULL DEFAULT '{}',
                retention_policy_json TEXT NOT NULL DEFAULT '{}',
                supports_backfill INTEGER NOT NULL DEFAULT 0,
                supports_repair INTEGER NOT NULL DEFAULT 0, updated_at TEXT
            );
            CREATE TABLE sync_checkpoints (
                dataset_id TEXT NOT NULL, scope TEXT NOT NULL,
                cursor_json TEXT NOT NULL DEFAULT '{}', watermark TEXT,
                last_success_run_id TEXT, updated_at TEXT,
                PRIMARY KEY (dataset_id, scope)
            );
            INSERT INTO dataset_policies VALUES (
                'stock_daily', 'isolated', 1, 'manual', NULL, '{}', '{}', 1, 1,
                '2026-08-01T08:00:00Z'
            );
            INSERT INTO sync_checkpoints VALUES (
                'stock_daily', 'default', '{}', '2026-07-31', 'run-stock_daily',
                '2026-08-01T08:00:00Z'
            );
            """
        )
    _write_ext_config(
        tmp_path,
        ExtConfig(
            id="ext_fund_flow_bk_daily",
            label="板块资金流日线",
            mode="timeseries",
            fields=[ExtField("symbol", "string", "标的代码")],
            pull=PullConfig(
                url="https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get",
                method="GET",
                last_run="2026-08-01T08:30:00Z",
            ),
        ),
    )
    _write_ext_config(
        tmp_path,
        ExtConfig(
            id="ext_custom_user",
            label="用户自建扩展表",
            mode="snapshot",
            fields=[ExtField("symbol", "string", "标的代码")],
            pull=PullConfig(
                url="https://example.test/custom.json",
                method="GET",
                last_run="2026-08-01T08:30:00Z",
            ),
        ),
    )

    before = service.control_db.path.stat().st_mtime_ns
    response = _client(service).get("/api/data/source-provenance")
    after = service.control_db.path.stat().st_mtime_ns

    assert response.status_code == 200
    assert after == before
    body = response.json()
    assert set(body) == {
        "generated_at",
        "catalog_refreshed_at",
        "catalog_stale",
        "records",
        "missing_reference_count",
    }
    assert len([r for r in body["records"] if r["subject_kind"] == "dataset"]) == len(
        DATASET_DEFINITIONS
    )
    assert len([r for r in body["records"] if r["subject_kind"] == "extension"]) == 1
    leftover = next(r for r in body["records"] if r["subject_id"] == "ext_custom_user")
    assert leftover["subject_kind"] == "extension"
    daily = next(r for r in body["records"] if r["subject_id"] == "stock_daily")
    assert daily["local_chain"]["lineage_sources"] == ["tickflow"]
    assert daily["local_chain"]["lifecycle"] == "isolated"
    assert daily["local_chain"]["checkpoint_watermark"] == "2026-07-31"
    assert daily["local_chain"]["latest_run"]["run_id"] == "run-stock_daily"
    assert daily["true_producers"][0]["producer_id"] == "tickflow"
    assert [ref["project_id"] for ref in daily["github_references"]] == [
        "tickflow-stock-panel",
        "go-stock",
    ]
    assert all(ref["runtime_dependency"] is False for ref in daily["github_references"])
    assert "easy_tdx" not in {ref["project_id"] for ref in daily["github_references"]}
    assert "akshare" not in {ref["project_id"] for ref in daily["github_references"]}
    instruments = next(r for r in body["records"] if r["subject_id"] == "stock_instruments")
    assert [ref["project_id"] for ref in instruments["github_references"]] == ["tickflow-stock-panel"]
    minute = next(r for r in body["records"] if r["subject_id"] == "stock_minute")
    assert [ref["project_id"] for ref in minute["github_references"]] == [
        "easy_tdx",
        "tickflow-stock-panel",
    ]
    easy_tdx = next(ref for ref in minute["github_references"] if ref["project_id"] == "easy_tdx")
    assert easy_tdx["runtime_dependency"] is True

    adj = next(r for r in body["records"] if r["subject_id"] == "stock_adj_factor")
    assert any(issue["code"] == "lineage_missing" for issue in adj["issues"])
    assert any(issue["code"] == "recent_failure" for issue in adj["issues"])

    ext = next(r for r in body["records"] if r["subject_id"] == "ext_fund_flow_bk_daily")
    assert ext["subject_kind"] == "dataset"
    assert [producer["producer_id"] for producer in ext["true_producers"]] == ["eastmoney"]
    assert any(ref["project_id"] == "go-stock" for ref in ext["github_references"])
    go_stock = next(ref for ref in ext["github_references"] if ref["project_id"] == "go-stock")
    assert "local_fallback" not in go_stock["roles"]
    assert "stock.db" in go_stock["contributions"]
    assert "GitHub 只作 Adapter 对照" in ext["summary"]
    assert "akshare" not in {ref["project_id"] for ref in ext["github_references"]}
    assert "finshare" not in {ref["project_id"] for ref in ext["github_references"]}


def test_source_provenance_does_not_initialize_missing_control_database(tmp_path: Path) -> None:
    service = object.__new__(CatalogService)
    service.data_dir = tmp_path
    service.control_db = CatalogControlDB(tmp_path)
    service.definitions = DATASET_DEFINITIONS
    service.manifests = ()
    service.entitlement_resolver = None

    response = _client(service).get("/api/data/source-provenance")

    assert response.status_code == 200
    assert not service.control_db.path.exists()
    body = response.json()
    assert body["catalog_stale"] is True
    assert len([r for r in body["records"] if r["subject_kind"] == "dataset"]) == len(
        DATASET_DEFINITIONS
    )
    margin = next(r for r in body["records"] if r["subject_id"] == "stock_margin_trading")
    assert [producer["producer_id"] for producer in margin["true_producers"]] == ["eastmoney"]
    assert [reference["project_id"] for reference in margin["github_references"]] == [
        "go-stock"
    ]
    go_stock = margin["github_references"][0]
    assert go_stock["roles"] == ["endpoint_intelligence", "field_semantics"]
    assert "不采用 go-stock 运行时或本地快照" in go_stock["contributions"]
    assert margin["replacement_candidates"] == []


def test_source_provenance_surfaces_latest_local_run_failure_without_blame_shift(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.control_db.upsert_dataset_state(_state("stock_daily"))
    service.control_db.upsert_sync_run(_run("stock_daily", status="failed"))

    body = _client(service).get("/api/data/source-provenance").json()

    daily = next(record for record in body["records"] if record["subject_id"] == "stock_daily")
    issue = next(issue for issue in daily["issues"] if issue["code"] == "latest_run_failed")
    assert "数据同步失败" in issue["message"]
    assert "provider_failed" in issue["message"]


def test_source_provenance_explains_degraded_catalog_scan_without_empty_fallback(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.control_db.upsert_dataset_state(
        _state(
            "stock_daily",
            lineage=[
                {
                    "source": "legacy_local_artifact",
                    "fetched_at": "2026-08-12T17:46:00Z",
                    "unit_version": "canonical_daily_v1",
                    "quality_status": "degraded",
                    "artifact_path": "kline_daily/date=2026-08-12/part.parquet",
                }
            ],
        )
    )
    service.control_db.upsert_sync_run(
        SyncRun(
            run_id="catalog-empty-degraded",
            dataset_id="stock_daily",
            provider="local",
            operation="catalog_rescan",
            started_at="2026-08-14T07:30:44Z",
            finished_at="2026-08-14T07:31:09Z",
            status="degraded",
            rows_published=8_065_671,
            quality_status="degraded",
            error_code=None,
            error_message=None,
        )
    )

    body = _client(service).get("/api/data/source-provenance").json()
    daily = next(record for record in body["records"] if record["subject_id"] == "stock_daily")
    issue = next(issue for issue in daily["issues"] if issue["code"] == "latest_run_degraded")
    assert "本地目录扫描降级" in issue["message"]
    assert "legacy_local_artifact" in issue["message"]
    assert "未记录错误详情" not in issue["message"]


def test_source_provenance_omits_latest_run_issue_after_succeeded_catalog_scan(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.control_db.upsert_dataset_state(_state("stock_daily"))
    service.control_db.upsert_sync_run(
        SyncRun(
            run_id="catalog-healthy",
            dataset_id="stock_daily",
            provider="local",
            operation="catalog_rescan",
            started_at="2026-08-17T06:00:00Z",
            finished_at="2026-08-17T06:01:00Z",
            status="succeeded",
            rows_published=1,
            quality_status="healthy",
        )
    )

    body = _client(service).get("/api/data/source-provenance").json()
    daily = next(record for record in body["records"] if record["subject_id"] == "stock_daily")
    assert all(issue["code"] != "latest_run_degraded" for issue in daily["issues"])


def test_source_provenance_ignores_malformed_extension_config_as_issue(tmp_path: Path) -> None:
    service = _service(tmp_path)
    bad_dir = tmp_path / "ext_data" / "ext_bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "config.json").write_text("{bad", encoding="utf-8")

    body = _client(service).get("/api/data/source-provenance").json()

    bad = next(record for record in body["records"] if record["subject_id"] == "ext_bad")
    assert bad["subject_kind"] == "extension"
    assert any(issue["code"] == "ext_config_unreadable" for issue in bad["issues"])


def test_source_provenance_query_uses_sqlite_readonly_mode(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.control_db.upsert_dataset_state(_state("stock_daily"))
    service.control_db.path.chmod(0o444)
    try:
        response = _client(service).get("/api/data/source-provenance")
    finally:
        service.control_db.path.chmod(0o644)

    assert response.status_code == 200
    assert response.json()["records"]
