"""TickFlow provider implementation."""

from __future__ import annotations

import logging
from datetime import datetime

import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities, ProviderDatasetManifest
from app.data_providers.normalizer import (
    normalize_adj_factors,
    normalize_daily,
    normalize_instruments,
)
from app.tickflow.client import get_client

logger = logging.getLogger(__name__)

_EXCHANGES = ["SH", "SZ", "BJ"]


_CN_BAR_UNITS = {
    "volume": "lot",
    "amount": "CNY",
    "ratio": "percentage_point",
    "daily_timestamp": "date",
}


def _tickflow_daily_manifest(asset_type: AssetType) -> ProviderDatasetManifest:
    return ProviderDatasetManifest(
        provider="tickflow",
        dataset_id=f"{asset_type}_daily",
        asset_types=(asset_type,),
        operations=("daily",),
        source_units={"volume": "unknown", "amount": "unknown", "ratio": "fraction"},
        canonical_units=_CN_BAR_UNITS,
        verified_at=None,
    )


def _tickflow_financial_manifest(dataset_id: str) -> ProviderDatasetManifest:
    return ProviderDatasetManifest(
        provider="tickflow",
        dataset_id=dataset_id,
        asset_types=("stock",),
        operations=("financial",),
        source_units={"monetary_currency": "unknown", "monetary_scale": "unknown"},
        canonical_units={"monetary_currency": "unknown", "monetary_scale": "unknown"},
        verified_at=None,
    )


class TickFlowProvider:
    name = "tickflow"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=True,
        minute=True,
        realtime=True,
        financial=True,
    )
    dataset_manifests = (
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="stock_instruments",
            asset_types=("stock",),
            operations=("instruments",),
            verified_at=None,
        ),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="etf_instruments",
            asset_types=("etf",),
            operations=("instruments",),
            verified_at=None,
        ),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="index_instruments",
            asset_types=("index",),
            operations=("instruments",),
            verified_at=None,
        ),
        _tickflow_daily_manifest("stock"),
        _tickflow_daily_manifest("etf"),
        _tickflow_daily_manifest("index"),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="stock_minute",
            asset_types=("stock",),
            operations=("minute",),
            source_units={"volume": "unknown", "amount": "unknown"},
            canonical_units={"volume": "lot", "amount": "CNY", "realtime_timestamp": "iso8601"},
            verified_at=None,
        ),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="stock_adj_factor",
            asset_types=("stock",),
            operations=("adj_factor",),
            source_units={"daily_timestamp": "date"},
            canonical_units={"daily_timestamp": "date"},
            verified_at=None,
        ),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="quote_snapshot",
            asset_types=("stock", "index", "etf"),
            operations=("realtime",),
            source_units={"volume": "unknown", "amount": "unknown", "ratio": "fraction"},
            canonical_units={
                "volume": "lot",
                "amount": "CNY",
                "ratio": "percentage_point",
                "realtime_timestamp": "iso8601",
                "realtime_timezone": "UTC",
                "market_timezone": "Asia/Shanghai",
            },
            verified_at=None,
        ),
        ProviderDatasetManifest(
            provider="tickflow",
            dataset_id="depth5",
            asset_types=("stock",),
            operations=("depth5",),
            source_units={"book_volume": "unknown"},
            canonical_units={
                "book_volume": "unknown",
                "realtime_timestamp": "iso8601",
                "realtime_timezone": "UTC",
                "market_timezone": "Asia/Shanghai",
            },
            verified_at=None,
        ),
        _tickflow_financial_manifest("financial_metrics"),
        _tickflow_financial_manifest("financial_income"),
        _tickflow_financial_manifest("financial_balance_sheet"),
        _tickflow_financial_manifest("financial_cash_flow"),
        _tickflow_financial_manifest("financial_shares"),
    )

    @classmethod
    def _daily_manifest(cls, asset_type: AssetType) -> ProviderDatasetManifest:
        dataset_id = f"{asset_type}_daily"
        return next(
            manifest for manifest in cls.dataset_manifests if manifest.dataset_id == dataset_id
        )

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:
        tf = get_client()
        instrument_type = "stock" if asset_type == "stock" else asset_type
        rows: list[dict] = []
        for ex in _EXCHANGES:
            try:
                items = tf.exchanges.get_instruments(ex, instrument_type=instrument_type)
                rows.extend([it for it in (items or []) if isinstance(it, dict)])
            except Exception as e:
                logger.warning("TickFlow instruments %s/%s failed: %s", ex, instrument_type, e)
        return normalize_instruments(rows, asset_type=asset_type, source=self.name)

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        manifest = self._daily_manifest(asset_type)
        # This must precede get_client(): M3 has no verified TickFlow units yet.
        from app.data_providers.unit_contracts import ensure_publishable_units

        ensure_publishable_units(manifest, required_fields={"volume", "amount"}, market="CN")
        tf = get_client()
        kwargs = {
            "period": "1d",
            "adjust": "none",
            "count": 10000 if start_time and end_time else 250,
            "as_dataframe": True,
            "show_progress": False,
        }
        if start_time and end_time:
            from app.services.kline_sync import _datetime_to_ms

            kwargs["start_time"] = _datetime_to_ms(start_time)
            kwargs["end_time"] = _datetime_to_ms(end_time)
        raw = tf.klines.batch(symbols, **kwargs)
        frames: list[pl.DataFrame] = []
        if isinstance(raw, dict):
            for sym, sub in raw.items():
                normalized = normalize_daily(
                    sub,
                    default_symbol=sym,
                    source=self.name,
                    manifest=manifest,
                    for_publication=True,
                )
                if not normalized.is_empty():
                    frames.append(normalized)
        else:
            normalized = normalize_daily(
                raw, source=self.name, manifest=manifest, for_publication=True
            )
            if not normalized.is_empty():
                frames.append(normalized)
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        tf = get_client()
        kwargs = {"as_dataframe": False}
        if start_time or end_time:
            from app.services.kline_sync import _datetime_to_ms

            if start_time:
                kwargs["start_time"] = _datetime_to_ms(start_time)
            if end_time:
                kwargs["end_time"] = _datetime_to_ms(end_time)
        raw = tf.klines.ex_factors(symbols, **kwargs)
        return normalize_adj_factors(raw, source=self.name)

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
        freq: str = "1m",
    ) -> pl.DataFrame:
        # Existing minute sync remains in app.services.kline_sync for now.
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        tf = get_client()
        if universes and symbols:
            raise ValueError("TickFlow realtime accepts either universes or symbols, not both")
        if universes:
            resp = tf.quotes.get_by_universes(universes=universes)
        elif symbols:
            resp = tf.quotes.get(symbols=symbols)
        else:
            return pl.DataFrame()
        return pl.DataFrame(resp or [])
