"""Read-only source provenance response models for the Data page."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import QualityStatus, SyncRun

SubjectKind = Literal["dataset", "extension"]
GithubRole = Literal[
    "host",
    "endpoint_intelligence",
    "field_semantics",
    "local_fallback",
    "engineering_mechanism",
    "protocol_reference",
    "candidate",
]
IssueSeverity = Literal["info", "warning", "error"]


class ProvenanceIssue(BaseModel):
    code: str
    severity: IssueSeverity
    message: str


class TrueProducer(BaseModel):
    producer_id: str
    name: str
    kind: str
    role: str
    access: str
    note: str


class GithubReference(BaseModel):
    project_id: str
    name: str
    repo_url: str
    pinned_ref: str | None = None
    commit_url: str | None = None
    reviewed_at: str | None = None
    roles: list[GithubRole] = Field(default_factory=list)
    contributions: str
    runtime_dependency: bool = False
    adoption_status: str
    evidence_level: str


class LocalChain(BaseModel):
    providers: list[str] = Field(default_factory=list)
    adapter_paths: list[str] = Field(default_factory=list)
    physical_paths: list[str] = Field(default_factory=list)
    lineage_sources: list[str] = Field(default_factory=list)
    lifecycle: str | None = None
    quality_status: QualityStatus | None = None
    materialized: bool = False
    serving_ready: bool = False
    latest_time: str | None = None
    checkpoint_watermark: str | None = None
    latest_run: SyncRun | None = None


class SubjectExplanation(BaseModel):
    """数据集/扩展对象的中文说明, 由后端注册表统一下发。"""

    category: str
    cadence: str
    description: str
    provides: str


class SourceProvenanceRecord(BaseModel):
    subject_id: str
    subject_kind: SubjectKind
    title: str
    explanation: SubjectExplanation | None = None
    summary: str
    true_producers: list[TrueProducer] = Field(default_factory=list)
    local_chain: LocalChain
    github_references: list[GithubReference] = Field(default_factory=list)
    replacement_candidates: list[GithubReference] = Field(default_factory=list)
    issues: list[ProvenanceIssue] = Field(default_factory=list)


class SourceProvenanceResponse(BaseModel):
    generated_at: str
    catalog_refreshed_at: str | None = None
    catalog_stale: bool = False
    records: list[SourceProvenanceRecord] = Field(default_factory=list)
    missing_reference_count: int = 0
