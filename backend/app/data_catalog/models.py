"""Public data-catalog response and control-plane models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

QualityStatus = Literal["unknown", "healthy", "degraded", "failed"]
RunStatus = Literal["pending", "running", "succeeded", "degraded", "failed"]


class DatasetAvailability(BaseModel):
    provider_supported: bool = False
    entitled: bool = False
    local_materialized: bool = False
    serving_ready: bool = False
    reason_code: str | None = None


class FieldContract(BaseModel):
    name: str
    dtype: str
    semantic: str
    unit: str | None = None
    scale: str | None = None
    currency: str | None = None
    timezone: str | None = None
    nullable: bool


class DatasetDescriptor(BaseModel):
    dataset_id: str
    title: str
    asset_types: list[str]
    grain: str
    primary_key: list[str]
    partition_keys: list[str]
    schema_version: str
    unit_version: str
    point_in_time: bool
    adjustment: str | None = None
    availability: DatasetAvailability
    fields: list[FieldContract]


class DatasetState(BaseModel):
    dataset_id: str
    schema_version: str
    unit_version: str
    quality_status: QualityStatus = "unknown"
    row_count: int = Field(default=0, ge=0)
    symbol_count: int = Field(default=0, ge=0)
    expected_symbol_count: int | None = Field(default=None, ge=0)
    earliest_time: str | None = None
    latest_time: str | None = None
    managed_bytes: int = Field(default=0, ge=0)
    last_run_id: str | None = None
    updated_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MarketCoverage(BaseModel):
    market: Literal["SH", "SZ", "BJ", "OTHER"]
    symbol_count: int = Field(default=0, ge=0)
    expected_symbol_count: int | None = Field(default=None, ge=0)
    ratio: float | None = Field(default=None, ge=0, le=1)


class ArtifactRecord(BaseModel):
    run_id: str
    dataset_id: str
    path: str
    sha256: str
    row_count: int = Field(default=0, ge=0)
    bytes: int = Field(default=0, ge=0)
    partition_value: str | None = None
    published_at: str


class SyncRun(BaseModel):
    run_id: str
    dataset_id: str
    provider: str | None = None
    operation: str
    started_at: str | None = None
    finished_at: str | None = None
    status: RunStatus
    rows_fetched: int = Field(default=0, ge=0)
    rows_published: int = Field(default=0, ge=0)
    quality_status: QualityStatus = "unknown"
    error_code: str | None = None
    error_message: str | None = None


class SourceHealth(BaseModel):
    provider: str
    operation: str
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    cooldown_until: str | None = None
    last_error_code: str | None = None


class LineageSummary(BaseModel):
    run_id: str | None = None
    source: str
    fetched_at: str | None = None
    unit_version: str
    quality_status: QualityStatus = "unknown"
    scope: str | None = None
    artifact_path: str | None = None
    row_count: int | None = Field(default=None, ge=0)


class StorageCategory(BaseModel):
    key: str
    title: str
    kind: Literal["managed", "operational"]
    bytes: int = Field(default=0, ge=0)
    files: int = Field(default=0, ge=0)


class StorageBreakdown(BaseModel):
    managed_data_bytes: int = Field(default=0, ge=0)
    operational_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    categories: list[StorageCategory] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self) -> StorageBreakdown:
        if self.total_bytes != self.managed_data_bytes + self.operational_bytes:
            raise ValueError("total_bytes must equal managed_data_bytes + operational_bytes")
        if sum(category.bytes for category in self.categories) != self.total_bytes:
            raise ValueError("category bytes must equal total_bytes")
        return self


class DatasetCatalogEntry(BaseModel):
    descriptor: DatasetDescriptor
    state: DatasetState
    provider: str | None = None
    coverage: list[MarketCoverage] = Field(default_factory=list)
    lineage: list[LineageSummary] = Field(default_factory=list)
    depth5_available: bool = False


class CatalogResponse(BaseModel):
    datasets: list[DatasetCatalogEntry]
    storage: StorageBreakdown
    refreshed_at: str | None = None
    stale: bool = False
