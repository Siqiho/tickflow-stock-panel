"""本地派生 reference 数据集构建器测试(移植自 7019d03 M6 测试并扩展)。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

from app.data_catalog.definitions import DATASET_DEFINITIONS
from app.services.reference_derived import (
    build_index_membership_from_pools,
    build_limit_up_events,
    build_valuation_daily,
    merge_membership_history,
    rebuild_reference_derived,
)


def _write_daily(data: Path, day: date, rows: list[dict]) -> None:
    p = data / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(p)


def _write_inst(data: Path, rows: list[dict]) -> None:
    p = data / "instruments" / "instruments.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(p)


def _daily_row(symbol: str, day: date, *, close: float, high: float, low: float) -> dict:
    return {
        "symbol": symbol,
        "date": day,
        "open": low,
        "high": high,
        "low": low,
        "close": close,
        "raw_close": close,
        "raw_high": high,
        "raw_low": low,
        "volume": 1.0,
        "amount": 1.0,
    }


def test_reference_derived_registered_in_catalog() -> None:
    ids = {d.descriptor.dataset_id for d in DATASET_DEFINITIONS}
    for ds in ("valuation_daily", "limit_up_events", "index_membership_history"):
        assert ds in ids
    by_id = {d.descriptor.dataset_id: d for d in DATASET_DEFINITIONS}
    assert by_id["valuation_daily"].roots == ("reference/valuation_daily",)
    assert by_id["limit_up_events"].roots == ("reference/limit_up_events",)
    assert by_id["index_membership_history"].roots == ("reference/index_membership_history",)
    for ds in ("valuation_daily", "limit_up_events", "index_membership_history"):
        assert by_id[ds].unit_policy == "reference"
        assert by_id[ds].coverage_policy == "on_demand"


def test_valuation_uses_pit_safe_shares_not_instruments_snapshot(tmp_path: Path) -> None:
    data = tmp_path / "data"
    day = date(2026, 7, 21)
    _write_daily(data, day, [_daily_row("600000.SH", day, close=10.0, high=11.0, low=9.0)])
    # instruments 快照股本存在但不得直接用于估值
    _write_inst(
        data,
        [
            {
                "symbol": "600000.SH",
                "name": "a",
                "total_shares": 999999.0,
                "float_shares": 999999.0,
            }
        ],
    )
    val0 = build_valuation_daily(data, day)
    assert val0.height == 1
    assert val0["total_mv"][0] is None
    assert val0["pe_ttm"][0] is None
    assert bool(val0["shares_pit_safe"][0]) is False

    # 加入严格 PIT 股本(权威来源 + announce/effective)后市值可派生
    sp = data / "financials" / "shares" / "part.parquet"
    sp.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "effective_date": [date(2026, 7, 1)],
            "announce_date": [date(2026, 6, 15)],
            "total_shares": [1000.0],
            "float_shares": [800.0],
            "source": ["exchange_share_capital"],
        }
    ).write_parquet(sp)
    val = build_valuation_daily(data, day)
    assert val.height == 1
    assert bool(val["shares_pit_safe"][0]) is True
    assert float(val["total_mv"][0]) == 10.0 * 1000.0
    assert float(val["float_mv"][0]) == 10.0 * 800.0
    assert val["pb"][0] is None


def test_limit_up_and_down_board_rules(tmp_path: Path) -> None:
    data = tmp_path / "data"
    day = date(2026, 7, 21)
    prev = date(2026, 7, 20)
    _write_daily(
        data,
        prev,
        [_daily_row(s, prev, close=10.0, high=10.0, low=10.0) for s in (
            "600000.SH", "000001.SZ", "300750.SZ", "830799.BJ", "600001.SH",
        )],
    )
    _write_daily(
        data,
        day,
        [
            _daily_row("600000.SH", day, close=11.0, high=11.0, low=10.0),
            _daily_row("000001.SZ", day, close=10.5, high=11.0, low=10.0),
            _daily_row("300750.SZ", day, close=12.0, high=12.0, low=10.0),
            _daily_row("830799.BJ", day, close=13.0, high=13.0, low=10.0),
            _daily_row("600001.SH", day, close=9.0, high=10.0, low=9.0),
        ],
    )
    _write_inst(
        data,
        [
            {"symbol": "600000.SH", "name": "浦发银行"},
            {"symbol": "000001.SZ", "name": "平安银行"},
            {"symbol": "300750.SZ", "name": "宁德时代"},
            {"symbol": "830799.BJ", "name": "北交所样例"},
            {"symbol": "600001.SH", "name": "ST示例"},
        ],
    )
    ep = data / "kline_daily_enriched" / f"date={day.isoformat()}" / "part.parquet"
    ep.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [day],
            "consecutive_limit_ups": [2],
        }
    ).write_parquet(ep)

    ev = build_limit_up_events(data, day)
    states = {r["symbol"]: r["state"] for r in ev.to_dicts()}
    boards = {r["symbol"]: r["board"] for r in ev.to_dicts()}
    assert states["600000.SH"] == "limit_up_final"
    assert states["000001.SZ"] == "broken_limit_up"
    assert states["300750.SZ"] == "limit_up_final"
    assert boards["300750.SZ"] == "CHINEXT"
    assert states["830799.BJ"] == "limit_up_final"
    assert boards["830799.BJ"] == "BJ"
    assert states["600001.SH"] == "limit_down_final"
    assert bool(ev.filter(pl.col("symbol") == "600001.SH")["is_st"][0]) is True
    assert (
        ev.filter(pl.col("symbol") == "600001.SH")["st_history_guarantee"][0]
        == "name_asof_snapshot_only"
    )
    assert int(ev.filter(pl.col("symbol") == "600000.SH")["board_height"][0]) == 2
    assert set(ev["price_basis"].unique().to_list()) == {"raw_unadjusted"}


def test_limit_events_seal_fund_only_from_same_day_sealed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    day = date(2026, 7, 21)
    prev = date(2026, 7, 20)
    _write_daily(data, prev, [_daily_row("600000.SH", prev, close=10.0, high=10.0, low=10.0)])
    _write_daily(data, day, [_daily_row("600000.SH", day, close=11.0, high=11.0, low=10.0)])
    _write_inst(data, [{"symbol": "600000.SH", "name": "a"}])
    # 异日 sealed_l1 不得套用到 trade_date
    other = data / "sealed_l1" / "date=2026-07-17"
    other.mkdir(parents=True)
    pl.DataFrame(
        {"symbol": ["600000.SH"], "sealed_up": [True], "bid1_vol": [999.0]}
    ).write_parquet(other / "part.parquet")
    ev = build_limit_up_events(data, day)
    assert ev.height == 1
    assert ev["seal_fund"][0] is None

    same = data / "sealed_l1" / f"date={day.isoformat()}"
    same.mkdir(parents=True)
    pl.DataFrame(
        {"symbol": ["600000.SH"], "sealed_up": [True], "bid1_vol": [777.0]}
    ).write_parquet(same / "part.parquet")
    ev2 = build_limit_up_events(data, day)
    assert float(ev2["seal_fund"][0]) == 777.0


def _write_pool(data: Path, pool_id: str, symbols: list[str], as_of: date) -> None:
    pools = data / "pools"
    pools.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "symbol": symbols,
            "name": ["x"] * len(symbols),
            "as_of": [as_of] * len(symbols),
            "index_code": ["000300"] * len(symbols),
            "source": ["csindex"] * len(symbols),
            "pool_id": [pool_id] * len(symbols),
        }
    ).write_parquet(pools / f"{pool_id}.parquet")


def test_membership_snapshot_seed_fields(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_pool(data, "CSI300", ["600000.SH", "000001.SZ"], date(2026, 7, 17))
    mem = build_index_membership_from_pools(data)
    assert mem.height == 2
    assert set(mem.get_column("effective_from").to_list()) == {date(2026, 7, 17)}
    assert mem["effective_to"].null_count() == 2
    assert set(mem["membership_basis"].unique().to_list()) == {"snapshot_seed"}
    assert set(mem["history_guarantee"].unique().to_list()) == {"as_collected"}


def test_membership_diff_merge_preserves_seed_and_closes_removed(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_pool(data, "CSI300", ["600000.SH", "000001.SZ"], date(2026, 7, 17))
    seed_old = build_index_membership_from_pools(data)

    # 新快照: 000001.SZ 移出, 600519.SH 加入
    _write_pool(data, "CSI300", ["600000.SH", "600519.SH"], date(2026, 8, 13))
    seed_new = build_index_membership_from_pools(data)
    merged = merge_membership_history(seed_old, seed_new)

    rows = {(r["symbol"]): r for r in merged.to_dicts()}
    assert len(rows) == 3
    # 持续成员保留原 effective_from
    assert rows["600000.SH"]["effective_from"] == date(2026, 7, 17)
    assert rows["600000.SH"]["effective_to"] is None
    # 移出成员关闭区间
    assert rows["000001.SZ"]["effective_to"] == date(2026, 8, 13)
    # 新成员按 snapshot_diff 追加
    assert rows["600519.SH"]["effective_from"] == date(2026, 8, 13)
    assert rows["600519.SH"]["membership_basis"] == "snapshot_diff"

    # 同一快照再并一次幂等
    merged2 = merge_membership_history(merged, seed_new)
    assert merged2.sort(["symbol"]).to_dicts() == merged.sort(["symbol"]).to_dicts()


def test_rebuild_reference_derived_writes_partitions_and_lineage(tmp_path: Path) -> None:
    data = tmp_path / "data"
    d1 = date(2026, 8, 11)
    d2 = date(2026, 8, 12)
    prev = date(2026, 8, 10)
    _write_daily(data, prev, [_daily_row("600000.SH", prev, close=10.0, high=10.0, low=10.0)])
    _write_daily(data, d1, [_daily_row("600000.SH", d1, close=11.0, high=11.0, low=10.0)])
    _write_daily(data, d2, [_daily_row("600000.SH", d2, close=11.0, high=11.5, low=10.5)])
    _write_inst(data, [{"symbol": "600000.SH", "name": "a"}])
    _write_pool(data, "CSI300", ["600000.SH"], date(2026, 8, 13))

    plan = rebuild_reference_derived(data, start=d1, end=d2, dry_run=True)
    assert plan["dry_run"] is True
    assert plan["dates"] == [d1.isoformat(), d2.isoformat()]
    assert not (data / "reference").exists()

    report = rebuild_reference_derived(data, start=d1, end=d2)
    val = report["datasets"]["valuation_daily"]
    assert val["written"] == 2
    lim = report["datasets"]["limit_up_events"]
    assert lim["written"] == 1  # d1 涨停; d2 无事件不写空分区
    assert lim["empty"] == 1
    mem = report["datasets"]["index_membership_history"]
    assert mem["ok"] is True

    assert (data / "reference" / "valuation_daily" / f"date={d1.isoformat()}" / "part.parquet").exists()
    assert (data / "reference" / "limit_up_events" / f"date={d1.isoformat()}" / "part.parquet").exists()
    assert not (data / "reference" / "limit_up_events" / f"date={d2.isoformat()}" / "part.parquet").exists()
    assert (data / "reference" / "index_membership_history" / "members.parquet").exists()

    # lineage 必须披露派生范围
    lineage_files = sorted(
        (data / "lineage" / "valuation_daily" / f"date={d1.isoformat()}").glob("*.json")
    )
    assert lineage_files
    payload = json.loads(lineage_files[0].read_text(encoding="utf-8"))
    assert payload["coverage_scope"] == "pipeline_scope_daily"
    assert payload["source_daily_symbols"] == 1
    assert payload["unit_version"] == "valuation_daily_v2"
    assert payload["target_artifact"].startswith("reference/valuation_daily/")
