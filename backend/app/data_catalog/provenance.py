"""Read-only provenance composition for the Data page source-tracing tab."""
# ruff: noqa: RUF001

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.ext_data import ExtConfig

from .definitions import DatasetDefinition
from .models import DatasetState, LineageSummary, SourceHealth, SyncCheckpoint, SyncRun
from .provenance_models import (
    GithubReference,
    LocalChain,
    ProvenanceIssue,
    SourceProvenanceRecord,
    SourceProvenanceResponse,
    SubjectExplanation,
    TrueProducer,
)
from .provenance_registry import (
    adapter_paths_for_subject,
    explanation_for_subject,
    producer_for_id,
    producer_id_for_lineage_source,
    producer_id_for_url,
    producer_ids_for_subject,
    references_for_subject,
    replacement_candidates_for_subject,
)


class SourceProvenanceModule:
    """Compose source provenance from current local evidence without mutation."""

    def __init__(self, catalog_service: Any) -> None:
        self.catalog_service = catalog_service
        self.data_dir = Path(catalog_service.data_dir)
        self.control_db = catalog_service.control_db
        self.definitions: tuple[DatasetDefinition, ...] = tuple(catalog_service.definitions)

    def list_sources(self) -> SourceProvenanceResponse:
        states = self._read_dataset_states()
        refreshed_meta = self.control_db.read_meta("catalog_refreshed_at")
        stale_meta = self.control_db.read_meta("catalog_stale")
        catalog_refreshed_at = refreshed_meta.get("value") if refreshed_meta else None
        catalog_stale = not bool(states) or bool((stale_meta or {}).get("value"))
        policies = {
            policy.dataset_id: policy for policy in self.control_db.list_dataset_policies()
        }
        checkpoints = {
            checkpoint.dataset_id: checkpoint
            for checkpoint in self.control_db.list_sync_checkpoints()
        }
        health = self.control_db.read_source_health()
        latest_runs = self._read_latest_runs()

        records: list[SourceProvenanceRecord] = []
        for definition in self.definitions:
            state = states.get(definition.descriptor.dataset_id)
            entry = self.catalog_service._catalog_entry(
                definition,
                state,
                catalog_refreshed_at,
            )
            records.append(
                self._dataset_record(
                    definition,
                    entry,
                    policies.get(definition.descriptor.dataset_id),
                    checkpoints.get(definition.descriptor.dataset_id),
                    latest_runs.get(definition.descriptor.dataset_id),
                    health,
                    catalog_stale,
                )
            )

        for extension in self._read_extensions():
            records.append(self._extension_record(extension, catalog_stale))

        return SourceProvenanceResponse(
            generated_at=_utc_now(),
            catalog_refreshed_at=catalog_refreshed_at,
            catalog_stale=catalog_stale,
            records=records,
            missing_reference_count=sum(
                any(issue.code == "missing_github_mapping" for issue in record.issues)
                for record in records
            ),
        )

    def get_dataset_source(self, dataset_id: str) -> SourceProvenanceRecord | None:
        response = self.list_sources()
        return next(
            (
                record
                for record in response.records
                if record.subject_kind == "dataset" and record.subject_id == dataset_id
            ),
            None,
        )

    def _dataset_record(
        self,
        definition: DatasetDefinition,
        entry: Any,
        policy: Any | None,
        checkpoint: SyncCheckpoint | None,
        latest_run: SyncRun | None,
        health: Iterable[SourceHealth],
        catalog_stale: bool,
    ) -> SourceProvenanceRecord:
        subject_id = definition.descriptor.dataset_id
        availability = entry.descriptor.availability
        lineage = list(entry.lineage)
        references = _github_references(references_for_subject(subject_id))
        candidates = _github_references(replacement_candidates_for_subject(subject_id))
        lineage_sources = _unique(item.source for item in lineage)
        providers = _unique(value for value in [entry.provider, *lineage_sources] if value)
        materialized = bool(availability.local_materialized)
        issues = self._common_issues(
            subject_id,
            references,
            catalog_stale,
            health,
            providers,
        )
        if latest_run is not None and latest_run.status in {"failed", "degraded"}:
            operation_label = "本地目录扫描" if "catalog" in latest_run.operation else "数据同步"
            from app.data_catalog.service import lineage_quality_details

            details = (
                latest_run.error_message
                or lineage_quality_details(lineage)
                or latest_run.error_code
                or "未记录错误详情"
            )
            issues.append(
                ProvenanceIssue(
                    code="latest_run_failed" if latest_run.status == "failed" else "latest_run_degraded",
                    severity="error" if latest_run.status == "failed" else "warning",
                    message=f"最近一次{operation_label}{'失败' if latest_run.status == 'failed' else '降级'}: {details[:280]}",
                )
            )
        if materialized and definition.unit_policy == "lineage" and not lineage_sources:
            issues.append(
                ProvenanceIssue(
                    code="lineage_missing",
                    severity="warning",
                    message="物理数据已落库，但当前目录快照没有匹配的 lineage 来源记录。",
                )
            )

        producers = self._dataset_producers(subject_id, lineage, entry.provider)
        if materialized and not producers:
            issues.append(
                ProvenanceIssue(
                    code="producer_evidence_missing",
                    severity="warning",
                    message="物理数据已落库，但尚无足够证据确认真实生产者；GitHub 项目不会被用来填补该字段。",
                )
            )

        lifecycle = policy.phase if policy else None
        local_chain = LocalChain(
            providers=providers,
            adapter_paths=adapter_paths_for_subject(subject_id),
            physical_paths=list(definition.roots),
            lineage_sources=lineage_sources,
            lifecycle=lifecycle,
            quality_status=entry.state.quality_status,
            materialized=materialized,
            serving_ready=bool(availability.serving_ready),
            latest_time=entry.state.latest_time,
            checkpoint_watermark=checkpoint.watermark if checkpoint else None,
            latest_run=latest_run,
        )
        return SourceProvenanceRecord(
            subject_id=subject_id,
            subject_kind="dataset",
            title=entry.descriptor.title,
            explanation=SubjectExplanation(
                **explanation_for_subject(
                    subject_id, subject_kind="dataset", title=entry.descriptor.title
                )
            ),
            summary=_dataset_summary(entry, lifecycle),
            true_producers=producers,
            local_chain=local_chain,
            github_references=references,
            replacement_candidates=candidates,
            issues=issues,
        )

    def _extension_record(
        self,
        extension: tuple[str, ExtConfig | None, ProvenanceIssue | None],
        catalog_stale: bool,
    ) -> SourceProvenanceRecord:
        subject_id, config, parse_issue = extension
        references = _github_references(references_for_subject(subject_id))
        candidates = _github_references(replacement_candidates_for_subject(subject_id))
        issues: list[ProvenanceIssue] = []
        if catalog_stale:
            issues.append(
                ProvenanceIssue(
                    code="catalog_stale",
                    severity="warning",
                    message="Catalog 快照已过期或缺失；扩展数据证据可能不完整。",
                )
            )
        if parse_issue is not None:
            issues.append(parse_issue)
        if not references:
            issues.append(
                ProvenanceIssue(
                    code="missing_github_mapping",
                    severity="info",
                    message="尚未登记 Adapter 对照的 GitHub 项目。这不是数据缺失，也不表示生产者未知。",
                )
            )

        title = config.label if config is not None else subject_id
        pull = config.pull if config is not None else None
        producer_ids = producer_ids_for_subject(subject_id)
        if not producer_ids:
            producer_ids = [producer_id_for_url(pull.url)] if pull and pull.url else ["user_upload"]
        producers = [TrueProducer(**producer_for_id(producer_id)) for producer_id in producer_ids]
        if pull and pull.url:
            producers[0].note = f"扩展配置端点：{pull.method} {pull.url}"

        physical_path = f"ext_data/{subject_id}"
        latest_time = pull.last_run if pull else None
        local_chain = LocalChain(
            providers=[producer.producer_id for producer in producers],
            adapter_paths=adapter_paths_for_subject(subject_id),
            physical_paths=[physical_path],
            lineage_sources=[],
            lifecycle=None,
            quality_status=None,
            materialized=self._extension_materialized(subject_id),
            serving_ready=self._extension_materialized(subject_id),
            latest_time=latest_time,
            checkpoint_watermark=None,
            latest_run=None,
        )
        summary = (
            f"扩展数据配置（{'快照' if config.mode == 'snapshot' else '时序'}）"
            if config is not None
            else "扩展数据配置无法解析"
        )
        if subject_id.startswith("ext_fund_flow"):
            summary += "；GitHub 只作 Adapter 对照，真实生产者是东财。go-stock stock.db 不在主路径"
        return SourceProvenanceRecord(
            subject_id=subject_id,
            subject_kind="extension",
            title=title,
            explanation=SubjectExplanation(
                **explanation_for_subject(subject_id, subject_kind="extension", title=title)
            ),
            summary=summary,
            true_producers=producers,
            local_chain=local_chain,
            github_references=references,
            replacement_candidates=candidates,
            issues=issues,
        )

    def _dataset_producers(
        self, subject_id: str, lineage: list[LineageSummary], provider: str | None
    ) -> list[TrueProducer]:
        producers: list[TrueProducer] = []
        for source in _unique(item.source for item in lineage):
            producer = TrueProducer(**producer_for_id(producer_id_for_lineage_source(source)))
            producer.note = f"Observed in lineage source: {source}"
            producers.append(producer)
        if not producers:
            for producer_id in producer_ids_for_subject(subject_id, provider):
                producer = TrueProducer(**producer_for_id(producer_id))
                producer.note = f"由 one-trading 当前 Provider/Adapter 代码登记；本快照尚无匹配 lineage 观测（provider={provider or '未登记'}）。"
                producers.append(producer)
        return producers

    def _common_issues(
        self,
        subject_id: str,
        references: list[GithubReference],
        catalog_stale: bool,
        health: Iterable[SourceHealth],
        providers: list[str],
    ) -> list[ProvenanceIssue]:
        issues: list[ProvenanceIssue] = []
        if catalog_stale:
            issues.append(
                ProvenanceIssue(
                    code="catalog_stale",
                    severity="warning",
                    message="Catalog 快照已过期或缺失；不能据此推断数据已正式可用。",
                )
            )
        if not references:
            issues.append(
                ProvenanceIssue(
                    code="missing_github_mapping",
                    severity="info",
                    message="尚未登记 Adapter 对照的 GitHub 项目。这不是数据缺失，也不表示生产者未知。",
                )
            )
        for item in health:
            if not _health_matches(item, subject_id, providers):
                continue
            if item.consecutive_failures > 0 or _is_recent_failure(item):
                issues.append(
                    ProvenanceIssue(
                        code="recent_failure",
                        severity="warning",
                        message=(
                            f"{item.provider}/{item.operation} 最近失败"
                            f"（{item.last_error_code or '未记录错误代码'}）。"
                        ),
                    )
                )
        return issues

    def _read_dataset_states(self) -> dict[str, DatasetState]:
        rows = self._read_optional_all(
            "dataset_state",
            """
            SELECT dataset_id, schema_version, unit_version, quality_status, row_count,
                   symbol_count, expected_symbol_count, earliest_time, latest_time,
                   managed_bytes, last_run_id, updated_at, payload_json
            FROM dataset_state ORDER BY dataset_id
            """,
        )
        states: dict[str, DatasetState] = {}
        for row in rows:
            states[row["dataset_id"]] = DatasetState(
                dataset_id=row["dataset_id"],
                schema_version=row["schema_version"],
                unit_version=row["unit_version"],
                quality_status=row["quality_status"],
                row_count=row["row_count"],
                symbol_count=row["symbol_count"],
                expected_symbol_count=row["expected_symbol_count"],
                earliest_time=row["earliest_time"],
                latest_time=row["latest_time"],
                managed_bytes=row["managed_bytes"],
                last_run_id=row["last_run_id"],
                updated_at=row["updated_at"],
                payload=_json_object(row["payload_json"]),
            )
        return states

    def _read_latest_runs(self) -> dict[str, SyncRun]:
        rows = self._read_optional_all(
            "sync_runs",
            """
            SELECT run_id, dataset_id, provider, operation, started_at, finished_at,
                   status, rows_fetched, rows_published, quality_status,
                   error_code, error_message
            FROM sync_runs
            ORDER BY dataset_id ASC, started_at DESC, run_id ASC
            """,
        )
        runs: dict[str, SyncRun] = {}
        for row in rows:
            dataset_id = row["dataset_id"]
            if dataset_id in runs:
                continue
            runs[dataset_id] = SyncRun(
                run_id=row["run_id"],
                dataset_id=dataset_id,
                provider=row["provider"],
                operation=row["operation"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                status=row["status"],
                rows_fetched=row["rows_fetched"],
                rows_published=row["rows_published"],
                quality_status=row["quality_status"],
                error_code=row["error_code"],
                error_message=row["error_message"],
            )
        return runs

    def _read_optional_all(
        self,
        table_name: str,
        query: str,
        values: tuple[Any, ...] = (),
    ) -> list[sqlite3.Row]:
        path = self.control_db.path
        if not path.is_file():
            return []
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro",
                uri=True,
                isolation_level=None,
                timeout=5.0,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if exists is None:
                return []
            return connection.execute(query, values).fetchall()
        except (OSError, sqlite3.DatabaseError):
            return []
        finally:
            if connection is not None:
                connection.close()

    def _read_extensions(self) -> list[tuple[str, ExtConfig | None, ProvenanceIssue | None]]:
        base = self.data_dir / "ext_data"
        if not base.is_dir() or base.is_symlink():
            return []
        catalog_ids = {definition.descriptor.dataset_id for definition in self.definitions}
        items: list[tuple[str, ExtConfig | None, ProvenanceIssue | None]] = []
        for directory in sorted(base.iterdir(), key=lambda path: path.name):
            if directory.is_symlink() or not directory.is_dir() or directory.name.startswith("."):
                continue
            if directory.name in catalog_ids:
                continue
            config_path = directory / "config.json"
            if not config_path.is_file() or config_path.is_symlink():
                continue
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                config = ExtConfig.from_dict(payload)
                items.append((config.id, config, None))
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                items.append(
                    (
                        directory.name,
                        None,
                        ProvenanceIssue(
                            code="ext_config_unreadable",
                            severity="warning",
                            message=f"无法解析 ext_data/config.json：{type(error).__name__}",
                        ),
                    )
                )
        return items

    def _extension_materialized(self, config_id: str) -> bool:
        root = self.data_dir / "ext_data" / config_id
        if (root / "part.parquet").is_file():
            return True
        timeseries = root / "timeseries"
        if not timeseries.is_dir() or timeseries.is_symlink():
            return False
        try:
            return any(path.name == "part.parquet" and path.is_file() for path in timeseries.rglob("*.parquet"))
        except OSError:
            return False


def _github_references(rows: list[dict[str, object]]) -> list[GithubReference]:
    return [GithubReference.model_validate(row) for row in rows]


def _dataset_summary(entry: Any, lifecycle: str | None) -> str:
    state = entry.state
    availability = entry.descriptor.availability
    quality_labels = {"healthy": "健康", "degraded": "降级", "failed": "失败", "unknown": "未知"}
    bits = [f"质量：{quality_labels.get(state.quality_status, state.quality_status)}"]
    bits.append("已落库" if availability.local_materialized else "尚未落库")
    bits.append("当前可服务" if availability.serving_ready else "尚未正式可用")
    if lifecycle:
        bits.append(f"准入阶段：{lifecycle}")
    if state.latest_time:
        bits.append(f"最新：{state.latest_time}")
    if entry.descriptor.dataset_id.startswith("ext_fund_flow"):
        bits.append("GitHub 只作 Adapter 对照，真实生产者是东财。go-stock stock.db 不在主路径")
    return "；".join(bits)


def _health_matches(item: SourceHealth, subject_id: str, providers: list[str]) -> bool:
    operation = item.operation.lower()
    provider = item.provider.lower()
    if subject_id.lower() in operation:
        return True
    return any(provider_name and provider_name.lower() in provider for provider_name in providers)


def _is_recent_failure(item: SourceHealth) -> bool:
    if not item.last_failure_at:
        return False
    if not item.last_success_at:
        return True
    return item.last_failure_at > item.last_success_at


def _unique(values: Iterable[str | None]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
