"""Generic HTTP provider for custom market data sources."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from app.config import settings
from app.data_providers.custom.config import CustomSourceConfig, DatasetConfig
from app.data_providers.custom.mapper import apply_transforms, datetime_payload, extract_rows, map_rows
from app.data_providers.custom.security import assert_safe_url
from app.data_providers.normalizer import normalize_adj_factors, normalize_daily
from app.tickflow.rate_limits import chunked, sleep_between_batches

logger = logging.getLogger(__name__)

_REQUIRED = {
    "daily": {"symbol", "date", "open", "high", "low", "close", "volume", "amount"},
    "adj_factor": {"symbol", "trade_date", "ex_factor"},
    "realtime": {"symbol", "last_price", "prev_close", "open", "high", "low", "volume"},
    "minute": {"symbol", "datetime", "open", "high", "low", "close", "volume", "amount"},
    # full_minute (全量分钟) 与 minute 同形: 当日窗口批量拉取, 字段映射一致
    "full_minute": {"symbol", "datetime", "open", "high", "low", "close", "volume", "amount"},
    # financial 字段由数据源决定, 只要求能映射出 symbol
    "financial": {"symbol"},
}


class GenericHTTPProvider:
    """HTTP-backed custom source. It only handles fetching and schema mapping."""

    def __init__(self, config: CustomSourceConfig) -> None:
        self.config = config
        self.name = config.name
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def validate(self) -> list[str]:
        errors: list[str] = []
        for dataset, cfg in self.config.datasets.items():
            if not cfg.url:
                errors.append(f"{dataset}: url is required")
            required = _REQUIRED.get(dataset)
            if required:
                mapped = set(cfg.field_map.values())
                missing = sorted(required - mapped)
                if missing:
                    errors.append(f"{dataset}: missing mapped fields: {', '.join(missing)}")
        return errors

    def _request_rows_retry(
        self, cfg, symbols: list[str], *, start_time=None, end_time=None, retries: int = 1
    ) -> list[dict]:
        """单批请求 + 短退避重试。仍失败抛出, 由调用方决定隔离粒度 (#226)。"""
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self._request_rows(
                    cfg, symbols=symbols, start_time=start_time, end_time=end_time
                )
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
        assert last is not None
        raise last

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",  # noqa: ARG002
        on_chunk_done=None,
    ) -> pl.DataFrame:
        cfg = self._dataset("daily")
        frames: list[pl.DataFrame] = []
        chunks = chunked(symbols, cfg.batch)
        failed: list[str] = []
        for i, chunk in enumerate(chunks):
            sleep_between_batches(i, cfg.rpm)
            try:
                rows = self._request_rows_retry(
                    cfg, chunk, start_time=start_time, end_time=end_time
                )
            except Exception as e:  # noqa: BLE001
                # 单批失败只隔离该批 (#226): 之前任一批 502 会让整个 stage
                # 抛异常, 已成功批次的结果留在内存里全部丢弃
                failed.extend(chunk)
                logger.warning(
                    "custom daily: batch %d/%d failed (%d symbols), skipped: %s",
                    i + 1, len(chunks), len(chunk), e,
                )
                if on_chunk_done:
                    on_chunk_done(i + 1, len(chunks))
                continue
            df = self._mapped_frame(cfg, rows)
            df = normalize_daily(df, source=self.name)
            if not df.is_empty():
                frames.append(df)
            if on_chunk_done:
                on_chunk_done(i + 1, len(chunks))
        if failed:
            logger.warning(
                "custom daily: %d/%d symbols missing due to batch failures: %s",
                len(failed), len(symbols), ", ".join(failed[:20]),
            )
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",  # noqa: ARG002
        on_chunk_done=None,
    ) -> pl.DataFrame:
        cfg = self._dataset("adj_factor")
        frames: list[pl.DataFrame] = []
        chunks = chunked(symbols, cfg.batch)
        failed: list[str] = []
        for i, chunk in enumerate(chunks):
            sleep_between_batches(i, cfg.rpm)
            try:
                rows = self._request_rows_retry(
                    cfg, chunk, start_time=start_time, end_time=end_time
                )
            except Exception as e:  # noqa: BLE001
                failed.extend(chunk)
                logger.warning(
                    "custom adj_factor: batch %d/%d failed (%d symbols), skipped: %s",
                    i + 1, len(chunks), len(chunk), e,
                )
                if on_chunk_done:
                    on_chunk_done(i + 1, len(chunks))
                continue
            df = self._mapped_frame(cfg, rows)
            df = normalize_adj_factors(df, source=self.name)
            if not df.is_empty():
                frames.append(df)
            if on_chunk_done:
                on_chunk_done(i + 1, len(chunks))
        if failed:
            logger.warning(
                "custom adj_factor: %d/%d symbols missing due to batch failures: %s",
                len(failed), len(symbols), ", ".join(failed[:20]),
            )
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_realtime(self) -> list[dict]:
        cfg = self._dataset("realtime")
        rows = self._request_rows(cfg)
        df = self._mapped_frame(cfg, rows)
        if df.is_empty():
            return []
        return df.to_dicts()

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        freq: str = "1m",
        on_chunk_done=None,
    ) -> pl.DataFrame:
        """拉取分钟 K。未配 asset_type_param/freq_param 时不把这两个字段传给上游。"""
        cfg = self._dataset("minute")
        override: dict[str, Any] = {}
        if cfg.asset_type_param:
            override[cfg.asset_type_param] = asset_type
        if cfg.freq_param:
            override[cfg.freq_param] = freq
        extra = override or None
        frames: list[pl.DataFrame] = []
        chunks = chunked(symbols, cfg.batch)
        for i, chunk in enumerate(chunks):
            sleep_between_batches(i, cfg.rpm)
            rows = self._request_rows(
                cfg, symbols=chunk, start_time=start_time, end_time=end_time,
                override_params=extra, override_body=extra,
            )
            df = self._mapped_frame(cfg, rows)
            df = self._normalize_minute(df)
            if not df.is_empty():
                frames.append(df)
            if on_chunk_done:
                on_chunk_done(i + 1, len(chunks))
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_financials(
        self,
        table: str,
        symbols: list[str],
        latest_only: bool = True,  # noqa: ARG002
    ) -> pl.DataFrame:
        """拉取财务数据。table ∈ {metrics, income, balance_sheet, cash_flow}。

        custom 源用一个 'financial' dataset 配置覆盖 4 张表; 请求时把 table 作为参数传给上游,
        上游根据 table 返回对应数据。字段由数据源决定, 这里只确保有 symbol 列。
        """
        cfg = self._dataset("financial")
        frames: list[pl.DataFrame] = []
        chunks = chunked(symbols, cfg.batch)
        for i, chunk in enumerate(chunks):
            sleep_between_batches(i, cfg.rpm)
            # 把 table 注入到请求参数 (上游据此区分 4 张表)
            extra_params = {**cfg.params, "table": table}
            extra_body = {**cfg.body, "table": table}
            rows = self._request_rows(
                cfg, symbols=chunk,
                override_params=extra_params, override_body=extra_body,
            )
            df = self._mapped_frame(cfg, rows)
            if not df.is_empty():
                frames.append(df)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    @classmethod
    def _normalize_minute(cls, df: pl.DataFrame) -> pl.DataFrame:
        """把映射后的 df 规范成 minute canonical 列。"""
        if df.is_empty():
            return df
        if "datetime" in df.columns and df.schema["datetime"] != pl.Datetime("us"):
            if df.schema["datetime"] == pl.Utf8:
                # 字符串 datetime 直接 cast 会整体置 null (polars 不做字符串解析);
                # 先解析再对齐微秒精度 (#225, 参照
                # kline_sync._enforce_minute_beijing_wallclock 的处理)。
                # Series 级立即解析: 表达式错误要到 collect 才抛, 无法按格式回退
                df = df.with_columns(cls._parse_datetime_series(df["datetime"]))
            df = df.with_columns(pl.col("datetime").cast(pl.Datetime("us"), strict=False))
        for col in ("open", "high", "low", "close", "volume", "amount"):
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
        keep = [c for c in ("symbol", "datetime", "open", "high", "low", "close", "volume", "amount") if c in df.columns]
        return df.select(keep) if keep else pl.DataFrame()

    _DATETIME_STR_FORMATS = (
        None,  # 自动推断
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )

    @classmethod
    def _parse_datetime_series(cls, s: pl.Series) -> pl.Series:
        """逐格式尝试解析字符串 datetime; 均失败返回全 null (宽松语义)。"""
        for fmt in cls._DATETIME_STR_FORMATS:
            try:
                return (
                    s.str.to_datetime(strict=False, format=fmt)
                    if fmt else s.str.to_datetime(strict=False)
                )
            except Exception:  # noqa: BLE001 — 该格式不适用, 换下一个
                continue
        return pl.Series("datetime", [None] * s.len(), dtype=pl.Datetime("us"))

    def test_dataset(self, dataset: str, symbols: list[str] | None = None) -> dict:
        cfg = self._dataset(dataset)
        rows = self._request_rows(cfg, symbols=symbols or [])
        df = self._mapped_frame(cfg, rows)
        return {
            "provider": self.name,
            "dataset": dataset,
            "rows": len(rows),
            "columns": df.columns,
            "preview": df.head(5).to_dicts() if not df.is_empty() else [],
        }

    def _dataset(self, name: str) -> DatasetConfig:
        cfg = self.config.datasets.get(name)
        if not cfg:
            raise ValueError(f"Custom data source '{self.name}' does not configure dataset '{name}'")
        return cfg

    def _mapped_frame(self, cfg: DatasetConfig, rows: list[dict]) -> pl.DataFrame:
        df = map_rows(rows, cfg.field_map)
        return apply_transforms(df, cfg.transforms)

    def _request_rows(
        self,
        cfg: DatasetConfig,
        *,
        symbols: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        override_params: dict[str, Any] | None = None,
        override_body: dict[str, Any] | None = None,
    ) -> list[dict]:
        headers, auth_params = self._auth_parts()
        params = dict(cfg.params)
        params.update(auth_params)
        if override_params:
            params.update(override_params)
        body = dict(cfg.body)
        if override_body:
            body.update(override_body)
        if symbols:
            body[cfg.symbols_param] = symbols
            params.setdefault(cfg.symbols_param, ",".join(symbols))
        start_value = datetime_payload(start_time)
        end_value = datetime_payload(end_time)
        if start_value:
            body[cfg.start_param] = start_value
            params.setdefault(cfg.start_param, start_value)
        if end_value:
            body[cfg.end_param] = end_value
            params.setdefault(cfg.end_param, end_value)

        method = cfg.method.upper()
        # SSRF: block private/loopback/metadata targets unless explicitly allowed
        allow_private = bool(getattr(self.config, "allow_private_hosts", False)) or bool(
            os.getenv("CUSTOM_HTTP_ALLOW_PRIVATE", "").lower() in {"1", "true", "yes"}
        )
        assert_safe_url(cfg.url, allow_private=allow_private)
        request_kwargs: dict[str, Any] = {"headers": headers, "timeout": cfg.timeout}
        if method == "GET":
            request_kwargs["params"] = params
        else:
            request_kwargs["params"] = auth_params
            request_kwargs["json"] = body
        resp = self._client.request(method, cfg.url, **request_kwargs)
        resp.raise_for_status()
        return extract_rows(resp.json(), cfg.response_path)

    def _auth_parts(self) -> tuple[dict[str, str], dict[str, str]]:
        auth = self.config.auth
        if auth.type == "none":
            return {}, {}
        token = _token_from_env(auth.token_env) if auth.token_env else None
        if not token:
            logger.warning("custom data source %s auth token is not set", self.name)
            return {}, {}
        if auth.type == "bearer":
            return {auth.header: f"Bearer {token}"}, {}
        if auth.type == "header":
            return {auth.header: token}, {}
        if auth.type == "query":
            return {}, {auth.param: token}
        return {}, {}


def _token_from_env(name: str | None) -> str | None:
    if not name:
        return None
    token = os.getenv(name)
    if token:
        return token
    candidates = [settings.data_dir.parent / ".env", Path.cwd() / ".env", Path.cwd().parent / ".env"]
    env_path = next((path for path in candidates if path.exists()), None)
    if env_path is None:
        return None
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        return None
    return None
