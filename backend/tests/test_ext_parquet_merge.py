from datetime import date
from pathlib import Path

import polars as pl

from app.services.ext_data import ExtConfig, ExtField, write_ext_parquet


def test_write_ext_parquet_merges_when_optional_column_differs(tmp_path: Path):
    cfg = ExtConfig(
        id="ext_fund_flow_bk_daily",
        label="行业板块资金流日线",
        mode="timeseries",
        fields=[
            ExtField("code", "string", "板块代码"),
            ExtField("name", "string", "板块名称"),
            ExtField("date", "string", "日期"),
            ExtField("main_net", "float", "主力净流入"),
            ExtField("source", "string", "来源"),
        ],
    )
    existing = pl.DataFrame(
        {
            "code": ["BK0001", "BK0002"],
            "name": ["银行", "电力"],
            "date": ["2026-08-21", "2026-08-21"],
            "main_net": [1.0, 2.0],
            "source": ["go_stock_local_snapshot", "go_stock_local_snapshot"],
            "snap_time": ["2026-08-21 15:00:00", "2026-08-21 15:00:00"],
        }
    )
    incoming = pl.DataFrame(
        {
            "code": ["BK0002"],
            "name": ["电力"],
            "date": ["2026-08-21"],
            "main_net": [9.0],
            "source": ["eastmoney_fflow_day"],
        }
    )
    write_ext_parquet(existing, cfg, tmp_path, snapshot_date=date(2026, 8, 21))
    write_ext_parquet(incoming, cfg, tmp_path, snapshot_date=date(2026, 8, 21))
    out = pl.read_parquet(tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / "date=2026-08-21" / "part.parquet")
    assert out["code"].n_unique() == 2
    power = out.filter(pl.col("code") == "BK0002").row(0, named=True)
    assert power["main_net"] == 9.0
    assert power["source"] == "eastmoney_fflow_day"
    bank = out.filter(pl.col("code") == "BK0001").row(0, named=True)
    assert bank["main_net"] == 1.0
    assert bank["source"] == "go_stock_local_snapshot"
