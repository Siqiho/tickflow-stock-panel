"""corporate_actions 闭环测试(移植自 7019d03 e5/v2 测试并适配主树 + 新批量报表)。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.data_catalog.definitions import DATASET_DEFINITIONS, get_dataset_definition
from app.data_lab.quality_reference import quality_passed, run_quality_checks
from app.data_lab.schemas_reference import get_reference_schema
from app.services.corporate_actions_sync import (
    CORPORATE_ACTIONS_UNIT_VERSION,
    MARKER_SOURCE_FAILED,
    MARKER_UNVERIFIED,
    MARKER_VERIFIED_EVENTS,
    MARKER_VERIFIED_NO_EVENT,
    apply_crosscheck_to_actions,
    build_verification_table,
    corporate_actions_from_adj_events,
    crosscheck_actions_vs_adj,
    fetch_sharebonus_events,
    formal_event_facts,
    map_coverage_status_to_marker,
    parse_em_bonus_rows,
    parse_sharebonus_report_rows,
    run_corporate_actions_loop,
)
from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient


def test_corporate_actions_registered() -> None:
    ids = {d.descriptor.dataset_id for d in DATASET_DEFINITIONS}
    assert "corporate_actions" in ids
    d = get_dataset_definition("corporate_actions")
    assert d.descriptor.unit_version == "corporate_actions_v2"
    assert d.unit_policy == "reference"
    schema = get_reference_schema("corporate_actions")
    assert "action_id" in schema.primary_key
    assert schema.unit_version == "corporate_actions_v2"


def test_marker_mapping_never_fails_as_no_event() -> None:
    assert map_coverage_status_to_marker("fetch_failed") == MARKER_SOURCE_FAILED
    assert map_coverage_status_to_marker("no_event") == MARKER_VERIFIED_NO_EVENT
    assert map_coverage_status_to_marker("events") == MARKER_VERIFIED_EVENTS
    assert map_coverage_status_to_marker("events", crosscheck_ok=False) == MARKER_UNVERIFIED
    assert map_coverage_status_to_marker("quarantined") == MARKER_UNVERIFIED
    assert map_coverage_status_to_marker(None) == MARKER_UNVERIFIED


def test_adj_derived_is_verification_signal_not_formal_fact() -> None:
    adj = pl.DataFrame(
        {
            "symbol": ["600000.SH", "600000.SH"],
            "trade_date": [date(2024, 6, 5), date(2020, 1, 2)],
            "ex_factor": [1.1, 1.0],
        }
    )
    acts = corporate_actions_from_adj_events(adj, as_of=date(2026, 7, 22))
    assert acts["unit_version"].unique().to_list() == [CORPORATE_ACTIONS_UNIT_VERSION]
    assert acts["is_verification_signal"].all()
    assert formal_event_facts(acts).is_empty()
    assert quality_passed(run_quality_checks("corporate_actions", acts))


def test_em_bonus_rows_have_source_trace_fields() -> None:
    rows = [
        {
            "SECUCODE": "600000.SH",
            "NOTICE_DATE": "2024-04-01",
            "EX_DIVIDEND_DATE": "2024-06-05",
            "IMPL_PLAN_PROFILE": "10派3.00元",
            "ASSIGN_PROGRESS": "实施",
        }
    ]
    df = parse_em_bonus_rows(rows, symbol="600000.SH", as_of=date(2026, 7, 22))
    assert not df.is_empty()
    row = df.to_dicts()[0]
    assert row["source"] == "eastmoney_bonus_f10"
    assert row["is_verification_signal"] is False
    assert row["raw_unit"] == "per_10_shares_plan_text"


def test_sharebonus_report_rows_parse_structured_fields() -> None:
    rows = [
        {
            "SECUCODE": "601899.SH",
            "SECURITY_NAME_ABBR": "紫金矿业",
            "PRETAX_BONUS_RMB": 4.2,
            "BONUS_IT_RATIO": None,
            "BONUS_RATIO": None,
            "IT_RATIO": None,
            "PLAN_NOTICE_DATE": "2026-03-21 00:00:00",
            "EQUITY_RECORD_DATE": "2026-08-20 00:00:00",
            "EX_DIVIDEND_DATE": "2026-08-21 00:00:00",
            "NOTICE_DATE": "2026-08-13 00:00:00",
            "ASSIGN_PROGRESS": "实施分配",
            "IMPL_PLAN_PROFILE": "10派4.20元(含税,扣税后3.78元)",
        },
        {
            "SECUCODE": "300001.SZ",
            "PRETAX_BONUS_RMB": 1.0,
            "BONUS_RATIO": 2.0,
            "IT_RATIO": 3.0,
            "PLAN_NOTICE_DATE": "2026-04-01 00:00:00",
            "EX_DIVIDEND_DATE": "2026-06-10 00:00:00",
            "NOTICE_DATE": "2026-06-05 00:00:00",
        },
        # 预案行(无除权除息日)跳过
        {"SECUCODE": "000001.SZ", "EX_DIVIDEND_DATE": None, "PRETAX_BONUS_RMB": 2.0},
    ]
    df = parse_sharebonus_report_rows(rows, as_of=date(2026, 8, 13))
    assert df.height == 2
    zijin = df.filter(pl.col("symbol") == "601899.SH").to_dicts()[0]
    assert zijin["action_type"] == "dividend_cash"
    assert abs(zijin["cash_per_share"] - 0.42) < 1e-12
    assert zijin["announce_date"] == date(2026, 3, 21)
    assert zijin["record_date"] == date(2026, 8, 20)
    assert zijin["ex_date"] == date(2026, 8, 21)
    assert zijin["source"] == "eastmoney_sharebonus_det"
    assert zijin["is_verification_signal"] is False
    mixed = df.filter(pl.col("symbol") == "300001.SZ").to_dicts()[0]
    assert mixed["action_type"] == "mixed"
    assert abs(mixed["stock_ratio"] - 0.5) < 1e-12
    assert quality_passed(run_quality_checks("corporate_actions", df))
    # 正式事实进入 formal 面
    assert formal_event_facts(df).height == 2


def test_fetch_sharebonus_events_paginates_and_stops_on_failure(monkeypatch) -> None:
    client = ResilientHttpClient()
    pages = {
        1: {
            "result": {
                "pages": 2,
                "count": 3,
                "data": [
                    {
                        "SECUCODE": "601899.SH",
                        "PRETAX_BONUS_RMB": 4.2,
                        "EX_DIVIDEND_DATE": "2026-08-21 00:00:00",
                        "PLAN_NOTICE_DATE": "2026-03-21 00:00:00",
                    }
                ],
            }
        },
        2: {
            "result": {
                "pages": 2,
                "count": 3,
                "data": [
                    {
                        "SECUCODE": "600000.SH",
                        "PRETAX_BONUS_RMB": 3.0,
                        "EX_DIVIDEND_DATE": "2026-06-05 00:00:00",
                        "PLAN_NOTICE_DATE": "2026-04-01 00:00:00",
                    }
                ],
            }
        },
    }

    def fake_get_json(url, **kwargs):
        for page, payload in pages.items():
            if f"pageNumber={page}" in url:
                return FetchResult(ok=True, status_code=200, data=payload)
        return FetchResult(ok=False, status_code=502, data=None, error="boom")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    frame, stats = fetch_sharebonus_events(client=client, sleep_s=0)
    assert stats["ok"] is True
    assert stats["pages_fetched"] == 2
    assert frame.height == 2

    # 中途失败如实报告
    def failing_get_json(url, **kwargs):
        if "pageNumber=1" in url:
            return FetchResult(ok=True, status_code=200, data=pages[1])
        return FetchResult(ok=False, status_code=502, data=None, error="boom")

    monkeypatch.setattr(client, "get_json", failing_get_json)
    frame2, stats2 = fetch_sharebonus_events(client=client, sleep_s=0)
    assert stats2["ok"] is False
    assert stats2["failed_page"] == 2
    assert frame2.height == 1


def test_crosscheck_mismatch_quarantines_formal_fact() -> None:
    formal = parse_em_bonus_rows(
        [
            {
                "SECUCODE": "600000.SH",
                "NOTICE_DATE": "2024-04-01",
                "EX_DIVIDEND_DATE": "2024-06-05",
                "IMPL_PLAN_PROFILE": "10派3元",
            }
        ],
        symbol="600000.SH",
    )
    cc = {
        "per_symbol": [
            {"symbol": "600000.SH", "crosscheck_ok": False, "only_actions": 1, "only_adj": 0}
        ]
    }
    out = apply_crosscheck_to_actions(formal, cc)
    assert out["verification_status"].to_list() == ["quarantined"]
    assert out["plan_status"].to_list() == ["quarantined"]


def test_crosscheck_and_verification_markers() -> None:
    adj = pl.DataFrame(
        [
            {"symbol": "600000.SH", "trade_date": date(2020, 6, 12), "ex_factor": 1.05},
            {"symbol": "000002.SZ", "trade_date": date(2019, 3, 1), "ex_factor": 1.1},
        ]
    )
    actions = corporate_actions_from_adj_events(adj, as_of=date(2026, 7, 22))
    actions_m = actions.filter(
        ~((pl.col("symbol") == "000002.SZ") & (pl.col("ex_date") == date(2019, 3, 1)))
    )
    cross = crosscheck_actions_vs_adj(actions_m, adj)
    assert cross["only_adj_dates"] >= 1
    cov = pl.DataFrame(
        [
            {"symbol": "600000.SH", "status": "events", "source": "sina_qfq", "events_n": 1, "checked_at": "t", "note": ""},
            {"symbol": "000002.SZ", "status": "events", "source": "sina_qfq", "events_n": 1, "checked_at": "t", "note": ""},
            {"symbol": "000001.SZ", "status": "no_event", "source": "sina_unit", "events_n": 0, "checked_at": "t", "note": ""},
            {"symbol": "300001.SZ", "status": "fetch_failed", "source": "sina_qfq", "events_n": 0, "checked_at": "t", "note": "timeout"},
        ]
    )
    ver = build_verification_table(
        coverage=cov,
        crosscheck=cross,
        universe=["600000.SH", "000002.SZ", "000001.SZ", "300001.SZ", "688001.SH"],
    )
    by = {r["symbol"]: r["verification"] for r in ver.to_dicts()}
    assert by["600000.SH"] == MARKER_VERIFIED_EVENTS
    assert by["000002.SZ"] == MARKER_UNVERIFIED  # crosscheck fail
    assert by["000001.SZ"] == MARKER_VERIFIED_NO_EVENT
    assert by["300001.SZ"] == MARKER_SOURCE_FAILED
    assert by["688001.SH"] == MARKER_UNVERIFIED  # not fetched


def test_run_loop_writes_lab_actions_and_verification(tmp_path: Path, monkeypatch) -> None:
    from app.services import kline_sync

    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    data = tmp_path / "data"
    (data / "adj_factor").mkdir(parents=True)
    adj = pl.DataFrame(
        [
            {"symbol": "600000.SH", "trade_date": date(2020, 6, 12), "ex_factor": 1.05},
            {"symbol": "000001.SZ", "trade_date": date(2021, 1, 4), "ex_factor": 1.01},
        ]
    )
    adj.write_parquet(data / "adj_factor" / "all.parquet")
    cov = pl.DataFrame(
        [
            {"symbol": "600000.SH", "status": "events", "source": "sina_qfq", "events_n": 1, "checked_at": "2026-07-22", "note": ""},
            {"symbol": "000001.SZ", "status": "events", "source": "sina_qfq", "events_n": 1, "checked_at": "2026-07-22", "note": ""},
            {"symbol": "300001.SZ", "status": "fetch_failed", "source": "sina_qfq", "events_n": 0, "checked_at": "2026-07-22", "note": "fail"},
        ]
    )
    cov.write_parquet(data / "adj_factor" / "coverage.parquet")
    inst = data / "instruments" / "instruments.parquet"
    inst.parent.mkdir(parents=True)
    pl.DataFrame(
        [
            {"symbol": "600000.SH", "name": "a"},
            {"symbol": "000001.SZ", "name": "b"},
            {"symbol": "300001.SZ", "name": "c"},
            {"symbol": "688001.SH", "name": "d"},
        ]
    ).write_parquet(inst)

    lab = tmp_path / "lab"
    report = run_corporate_actions_loop(
        data,
        asset_type="stock",
        as_of=date(2026, 7, 22),
        fetch_missing_adj=False,
        publish_actions=True,
        lab_dir=lab,
    )
    assert report["action_rows"] == 2
    assert (lab / "reference" / "corporate_actions" / "actions.parquet").exists()
    assert Path(report["verification_path"]).exists()
    counts = report["verification_counts"]
    assert counts.get(MARKER_SOURCE_FAILED, 0) >= 1
    assert counts.get(MARKER_UNVERIFIED, 0) >= 1  # 688001 not fetched
    assert counts.get(MARKER_VERIFIED_EVENTS, 0) >= 1

    # 幂等: 同数据二跑行数不变
    rerun = run_corporate_actions_loop(
        data,
        asset_type="stock",
        as_of=date(2026, 7, 22),
        fetch_missing_adj=False,
        publish_actions=True,
        lab_dir=lab,
    )
    assert rerun["publish"]["ok"] is True
    assert rerun["publish"]["row_count"] == report["publish"]["row_count"]
