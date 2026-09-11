"""_write_lock 锁区间瘦身的回归测试。

背景: polars 并发执行存在死锁风险 (app.polars_guard), 若 polars 读/合并/排序
悬死在 _write_lock 内, 全局写锁被永久持有 → 所有写路径排队冻结 (2026-09-07
线上全站冻结事故的放大器)。乐观并发模式把重活移到锁外, 此处验证:
- 并发 upsert 不丢行 (乐观重试的正确性);
- 合并计算期间 _write_lock 可被其他线程获取 (重活确实不在锁内)。
"""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.tickflow.repository import DataStore, KlineRepository


def _frame(symbols: list[str], dt: date = date(2026, 9, 7)) -> pl.DataFrame:
    n = len(symbols)
    return pl.DataFrame({
        "symbol": symbols,
        "date": [dt] * n,
        "close": [10.0 + i for i in range(n)],
    })


def test_concurrent_upserts_do_not_lose_rows(tmp_path: Path) -> None:
    repo = KlineRepository(DataStore(tmp_path))

    groups = [[f"{i:03d}{j:04d}.SZ" for j in range(8)] for i in range(6)]
    errors: list[BaseException] = []

    def worker(symbols: list[str]) -> None:
        try:
            for _ in range(3):  # 每线程多轮写, 提高乐观重试路径命中
                repo.merge_live_daily_asset("stock", _frame(symbols))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(g,), daemon=True) for g in groups]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    assert all(not t.is_alive() for t in threads)

    out = tmp_path / "kline_daily" / "date=2026-09-07" / "part.parquet"
    final = pl.read_parquet(out)
    assert final["symbol"].n_unique() == sum(len(g) for g in groups)  # 无一丢失
    assert final["symbol"].to_list() == sorted(final["symbol"].to_list())


def test_heavy_merge_runs_outside_write_lock(tmp_path: Path, monkeypatch) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    # 预置旧分区内容, 让 upsert 走「读旧 + concat 合并」路径。
    repo.merge_live_daily_asset("stock", _frame(["000001.SZ"]))

    merge_entered = threading.Event()
    original_concat = pl.concat

    def slow_concat(*args, **kwargs):
        merge_entered.set()
        import time

        time.sleep(0.4)  # 模拟重合并耗时; 期间 _write_lock 必须是空闲的
        return original_concat(*args, **kwargs)

    monkeypatch.setattr(pl, "concat", slow_concat)

    done = threading.Event()

    def upsert() -> None:
        repo.merge_live_daily_asset("stock", _frame(["000002.SZ"]))
        done.set()

    t = threading.Thread(target=upsert, daemon=True)
    t.start()
    assert merge_entered.wait(timeout=5), "合并路径未被触发"

    acquired = repo._write_lock.acquire(timeout=1.0)
    assert acquired, "合并计算期间 _write_lock 被占用 — 重活仍在锁内"
    repo._write_lock.release()

    assert done.wait(timeout=5)
    t.join(timeout=5)
    out = tmp_path / "kline_daily" / "date=2026-09-07" / "part.parquet"
    assert pl.read_parquet(out)["symbol"].to_list() == ["000001.SZ", "000002.SZ"]


def test_merge_live_daily_preserves_file_when_publish_fails(tmp_path: Path, monkeypatch) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    repo.merge_live_daily_asset("stock", _frame(["000001.SZ"]))
    out = tmp_path / "kline_daily" / "date=2026-09-07" / "part.parquet"
    before = pl.read_parquet(out)

    def fail_write(self, path, *args, **kwargs):
        raise OSError("simulated interruption")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_write)
    with pytest.raises(OSError, match="simulated interruption"):
        repo.merge_live_daily_asset("stock", _frame(["000002.SZ"]))
    assert pl.read_parquet(out)["symbol"].to_list() == before["symbol"].to_list()


def test_concurrent_persist_and_minute_partition_do_not_lose_rows(tmp_path: Path) -> None:
    from datetime import datetime, timedelta

    from app.services.kline_sync import persist_historical_minute, _write_minute_partition

    trade_date = date(2026, 6, 29)

    def minute_frame(symbol: str, last_close: float = 47.82, volume_total: float = 2_245_847) -> pl.DataFrame:
        morning = [datetime(2026, 6, 29, 9, 30) + timedelta(minutes=i) for i in range(120)]
        afternoon = [datetime(2026, 6, 29, 13, 0) + timedelta(minutes=i) for i in range(120)]
        times = morning + afternoon
        prices = [50.92 - (50.92 - last_close) * i / 239 for i in range(240)]
        base = int(volume_total // 240)
        volumes = [float(base)] * 239
        volumes.append(float(volume_total - base * 239))
        return pl.DataFrame({
            "symbol": [symbol] * 240,
            "datetime": times,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": volumes,
            "amount": [p * v * 100 for p, v in zip(prices, volumes, strict=True)],
        })

    daily = pl.DataFrame({
        "symbol": ["301526.SZ"],
        "date": [trade_date],
        "close": [47.7995422],
        "raw_close": [47.82],
        "low": [45.6804492],
        "raw_low": [45.70],
        "high": [52.2476385],
        "raw_high": [52.27],
        "volume": [2_245_847.0],
        "amount": [10_823_434_410.0],
    })

    class _Repo:
        def __init__(self, data_dir: Path) -> None:
            self.store = type("Store", (), {"data_dir": data_dir})()
            self._write_lock = threading.Lock()

        def refresh_minute_views(self) -> None:
            return None

    repo = _Repo(tmp_path)
    minute_dir = tmp_path / "kline_minute"
    errors: list[BaseException] = []

    def persist_one() -> None:
        try:
            persist_historical_minute(
                minute_frame("301526.SZ"),
                repo,
                "301526.SZ",
                trade_date,
                daily,
                source="fixture",
            )
        except BaseException as exc:
            errors.append(exc)

    def batch_one() -> None:
        try:
            with repo._write_lock:
                _write_minute_partition(minute_frame("510300.SH"), minute_dir)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=persist_one, daemon=True),
        threading.Thread(target=batch_one, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, errors
    out = minute_dir / "date=2026-06-29" / "part.parquet"
    stored = pl.read_parquet(out)
    assert set(stored["symbol"].unique().to_list()) == {"301526.SZ", "510300.SH"}
    assert stored.height == 480
