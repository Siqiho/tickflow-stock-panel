"""Provider contracts for external market data sources.

The first implementation wraps TickFlow. Other providers (Tushare/AkShare/etc.)
should return the same normalized Polars schemas so storage, indicators and
backtests stay data-source agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import polars as pl
from pydantic import BaseModel, Field, field_validator

AssetType = Literal["stock", "index", "etf"]


@dataclass(frozen=True)
class ProviderCapabilities:
    instruments: bool = False
    daily: bool = False
    adj_factor: bool = False
    minute: bool = False
    realtime: bool = False
    financial: bool = False
    quote_snapshot: bool = False
    sealed_l1: bool = False
    pools: bool = False


class ProviderDatasetManifest(BaseModel):
    """Declared source and canonical unit contract for one provider dataset."""

    provider: str
    dataset_id: str
    asset_types: list[str]
    operations: list[str]
    source_units: dict[str, str] = Field(default_factory=dict)
    canonical_units: dict[str, str] = Field(default_factory=dict)
    entitlement_required: str | None
    history_guarantee: str | None
    verified_at: datetime | None

    @field_validator("provider", "dataset_id")
    @classmethod
    def validate_non_empty_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("provider and dataset_id must be non-empty")
        return value

    @field_validator("asset_types", "operations")
    @classmethod
    def validate_non_empty_values(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("asset_types and operations must contain non-empty strings")
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("asset_types and operations must contain non-empty strings")
            normalized.append(value.strip())
        if len(normalized) != len(set(normalized)):
            raise ValueError("operations and asset_types must be unique")
        return normalized

    @field_validator("source_units", "canonical_units")
    @classmethod
    def validate_unit_map(cls, value: dict[str, str]) -> dict[str, str]:
        if any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(unit, str)
            or not unit.strip()
            for key, unit in value.items()
        ):
            raise ValueError("source_units and canonical_units must be string unit maps")
        return dict(value)


class MarketDataProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities
    dataset_manifests: tuple[ProviderDatasetManifest, ...]

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:
        """Return normalized instruments: symbol/name/code/exchange/asset_type/source."""

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        """Return normalized daily K rows."""

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        """Return normalized adjustment factors: symbol/trade_date/ex_factor."""

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
        freq: str = "1m",
    ) -> pl.DataFrame:
        """Return normalized minute K rows. Implementations may return empty."""

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        """Return normalized realtime quotes. Implementations may return empty."""
