"""Typed adapter over one-trading's admitted public data services."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities, ProviderDatasetManifest

_CN_QUOTE_UNITS = {
    "volume": "lot",
    "amount": "CNY",
    "ratio": "percentage_point",
    "daily_timestamp": "date",
    "realtime_timestamp": "iso8601",
    "realtime_timezone": "UTC",
    "market_timezone": "Asia/Shanghai",
}


def _public_financial_manifest(dataset_id: str) -> ProviderDatasetManifest:
    return ProviderDatasetManifest(
        provider="public",
        dataset_id=dataset_id,
        asset_types=("stock",),
        operations=("financial",),
        source_units={"monetary_currency": "unknown", "monetary_scale": "unknown"},
        canonical_units={"monetary_currency": "unknown", "monetary_scale": "unknown"},
    )


class PublicProvider:
    name = "public"
    capabilities = ProviderCapabilities(
        adj_factor=True,
        realtime=True,
        financial=True,
        quote_snapshot=True,
        sealed_l1=True,
        pools=True,
    )
    operations = frozenset({"quote_snapshot", "sealed_l1", "adj_factor", "financial", "pools"})
    dataset_manifests = (
        ProviderDatasetManifest(
            provider="public",
            dataset_id="quote_snapshot",
            asset_types=("stock", "index", "etf"),
            operations=("quote_snapshot",),
            # Quote rows carry per-row provenance and are already canonical.
            source_units={"volume": "unknown", "amount": "unknown", "ratio": "percentage_point"},
            canonical_units=_CN_QUOTE_UNITS,
        ),
        ProviderDatasetManifest(
            provider="public",
            dataset_id="sealed_l1",
            asset_types=("stock",),
            operations=("sealed_l1",),
            source_units={"book_volume": "unknown"},
            canonical_units={
                "book_volume": "unknown",
                "realtime_timestamp": "iso8601",
                "realtime_timezone": "UTC",
                "market_timezone": "Asia/Shanghai",
            },
        ),
        ProviderDatasetManifest(
            provider="public",
            dataset_id="stock_adj_factor",
            asset_types=("stock",),
            operations=("adj_factor",),
            source_units={"daily_timestamp": "date"},
            canonical_units={"daily_timestamp": "date"},
        ),
        _public_financial_manifest("financial_metrics"),
        _public_financial_manifest("financial_income"),
        _public_financial_manifest("financial_balance_sheet"),
        _public_financial_manifest("financial_cash_flow"),
        _public_financial_manifest("financial_shares"),
        ProviderDatasetManifest(
            provider="public",
            dataset_id="pools",
            asset_types=("stock",),
            operations=("pools",),
        ),
    )

    def supports(self, operation: str) -> bool:
        return operation in self.operations

    def get_quote_snapshot(
        self,
        symbols: list[str],
        *,
        batch_size: int = 80,
        pause_s: float = 0.05,
    ) -> pl.DataFrame:
        from app.services.free_sources.quote_fallback import fetch_public_market_quotes

        rows = fetch_public_market_quotes(symbols, batch_size=batch_size, pause_s=pause_s)
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def get_sealed_l1(self, symbols: list[str]) -> dict[str, dict]:
        from app.services.free_sources.intraday_public import fetch_public_depth_l1

        return fetch_public_depth_l1(symbols)

    def sync_adj_factors(
        self,
        symbols: list[str],
        data_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from app.services.free_sources.adj_factor_public import sync_adj_factor_public

        return sync_adj_factor_public(symbols, data_dir, **kwargs)

    def sync_financials(
        self,
        symbols: list[str],
        data_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from app.services.free_sources.financials_public import sync_financials_public

        return sync_financials_public(symbols, data_dir, **kwargs)

    def sync_shares_snapshot(self, data_dir: Path, symbols: list[str]) -> int:
        from app.services.free_sources.financials_public import sync_shares_snapshot

        return sync_shares_snapshot(data_dir, symbols=symbols)

    def sync_pools(self, data_dir: Path, **kwargs: Any) -> dict[str, Any]:
        from app.services.free_sources.pools_public import sync_pools_public

        return sync_pools_public(data_dir, **kwargs)

    # Protocol compatibility: public capability is intentionally limited to
    # typed operations above, not a second general-purpose daily provider.
    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:
        return pl.DataFrame()

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
        freq: str = "1m",
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        if universes:
            raise ValueError("public provider accepts explicit symbols, not remote universes")
        return self.get_quote_snapshot(symbols or [])
