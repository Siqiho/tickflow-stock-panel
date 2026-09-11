"""E6/M5.4 point-in-time financials helpers.

Adds/normalizes:
  report_date, announce_date, update_date, available_at, pit_unsafe,
  history_guarantee, schema_version, unit_version, period_type,
  currency, amount_scale, source, fetched_at, first_seen_at, restatement_id

Rules:
  - restatements retained (do not overwrite prior versions of same report_date)
  - never invent announce_date from report_date
  - available_at only from announce_date or validated update_date
  - strict as_of queries require pit_unsafe=false and available_at <= as_of
  - shares uses true effective_date history; snapshot capture days are pit_unsafe
  - staging merge then atomic replace of part.parquet
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.atomic_io import atomic_write_parquet, write_lineage_record

logger = logging.getLogger(__name__)

FINANCIAL_TABLES = ("metrics", "income", "balance_sheet", "cash_flow", "shares")

FINANCIAL_DATASET_IDS = {
    "metrics": "financial_metrics",
    "income": "financial_income",
    "balance_sheet": "financial_balance_sheet",
    "cash_flow": "financial_cash_flow",
    "shares": "financial_shares",
}

PIT_COLS = (
    "report_date",
    "announce_date",
    "update_date",
    "available_at",
    "pit_unsafe",
    "history_guarantee",
    "schema_version",
    "unit_version",
    "period_type",
    "currency",
    "amount_scale",
    "source",
    "fetched_at",
    "first_seen_at",
    "restatement_id",
)

FINANCIAL_UNIT_VERSION = "financial_cn_v2"
FINANCIAL_SCHEMA_VERSION = "2"


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def infer_period_type(report_date: date | None) -> str | None:
    if report_date is None:
        return None
    m, d = report_date.month, report_date.day
    if (m, d) == (12, 31):
        return "annual"
    if (m, d) == (9, 30):
        return "q3"
    if (m, d) in {(6, 30)}:
        return "semi_annual"
    if (m, d) == (3, 31):
        return "q1"
    return "other"


def _restatement_id(
    symbol: str,
    report_date: date,
    announce_date: date | None,
    update_date: date | None,
    source: str | None,
) -> str:
    parts = [
        symbol,
        report_date.isoformat(),
        announce_date.isoformat() if announce_date else "",
        update_date.isoformat() if update_date else "",
        source or "",
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def ensure_pit_columns(
    df: pl.DataFrame,
    *,
    table: str,
    default_source: str | None = None,
    fetched_at: datetime | None = None,
    first_seen_at: datetime | None = None,
) -> pl.DataFrame:
    """Normalize a financial frame to include PIT identity columns."""
    if df is None or df.is_empty():
        return df if df is not None else pl.DataFrame()

    out = df
    # report_date from period_end if missing
    if "report_date" not in out.columns:
        if "period_end" in out.columns:
            out = out.with_columns(pl.col("period_end").alias("report_date"))
        else:
            out = out.with_columns(pl.lit(None).cast(pl.Date).alias("report_date"))
    else:
        if out.schema.get("report_date") != pl.Date:
            out = out.with_columns(pl.col("report_date").cast(pl.Date, strict=False))

    # announce_date from notice_date / announce_date
    if "announce_date" not in out.columns:
        if "notice_date" in out.columns:
            out = out.with_columns(pl.col("notice_date").alias("announce_date"))
        else:
            out = out.with_columns(pl.lit(None).cast(pl.Date).alias("announce_date"))
    if out.schema.get("announce_date") != pl.Date:
        # may be utf8
        try:
            out = out.with_columns(pl.col("announce_date").cast(pl.Date, strict=False))
        except Exception:
            out = out.with_columns(
                pl.col("announce_date").cast(pl.Utf8).str.to_date(strict=False).alias("announce_date")
            )

    if "update_date" not in out.columns:
        out = out.with_columns(pl.lit(None).cast(pl.Date).alias("update_date"))
    elif out.schema.get("update_date") != pl.Date:
        try:
            out = out.with_columns(pl.col("update_date").cast(pl.Date, strict=False))
        except Exception:
            out = out.with_columns(
                pl.col("update_date").cast(pl.Utf8).str.to_date(strict=False).alias("update_date")
            )

    # M5.4: NEVER fill announce_date from report_date. update_date may fill only
    # when it is a source-validated publication/update timestamp, and even then
    # the row is marked pit_unsafe unless announce_date itself was present.
    had_announce = (
        pl.col("announce_date").is_not_null()
        if "announce_date" in out.columns
        else pl.lit(False)
    )
    out = out.with_columns(had_announce.alias("_had_real_announce"))
    # Keep announce_date as-is (nulls stay null). Do not coalesce report_date.

    if "period_type" not in out.columns:
        # compute via map on report_date
        rds = out.get_column("report_date").to_list()
        pts = [infer_period_type(d if isinstance(d, date) else _as_date(d)) for d in rds]
        out = out.with_columns(pl.Series("period_type", pts))
    else:
        # fill nulls
        rds = out.get_column("report_date").to_list()
        existing = out.get_column("period_type").to_list()
        pts = []
        for i, v in enumerate(existing):
            if v:
                pts.append(str(v))
            else:
                pts.append(infer_period_type(rds[i] if isinstance(rds[i], date) else _as_date(rds[i])))
        out = out.with_columns(pl.Series("period_type", pts))

    if "currency" not in out.columns:
        out = out.with_columns(pl.lit("CNY").alias("currency"))
    else:
        out = out.with_columns(pl.col("currency").cast(pl.Utf8).fill_null("CNY"))

    if "amount_scale" not in out.columns:
        # East Money values are typically yuan (1.0)
        out = out.with_columns(pl.lit(1.0).cast(pl.Float64).alias("amount_scale"))

    if "source" not in out.columns:
        out = out.with_columns(pl.lit(default_source or "unknown").alias("source"))
    elif default_source:
        out = out.with_columns(pl.col("source").cast(pl.Utf8).fill_null(default_source))

    now = fetched_at or _utc_naive()
    seen = first_seen_at or now
    if "fetched_at" not in out.columns:
        out = out.with_columns(pl.lit(now).alias("fetched_at"))
    if "first_seen_at" not in out.columns:
        out = out.with_columns(pl.lit(seen).alias("first_seen_at"))

    # shares effective_date
    if table == "shares":
        if "effective_date" not in out.columns:
            # prefer period_end / report_date / announce_date
            base = None
            for c in ("period_end", "report_date", "announce_date"):
                if c in out.columns:
                    base = pl.col(c)
                    break
            if base is None:
                out = out.with_columns(pl.lit(date.today()).alias("effective_date"))
            else:
                out = out.with_columns(base.cast(pl.Date, strict=False).alias("effective_date"))
        elif out.schema.get("effective_date") != pl.Date:
            out = out.with_columns(pl.col("effective_date").cast(pl.Date, strict=False))

    # restatement_id
    if "restatement_id" not in out.columns:
        rid: list[str | None] = []
        for row in out.select(
            [
                c
                for c in (
                    "symbol",
                    "report_date",
                    "announce_date",
                    "update_date",
                    "source",
                )
                if c in out.columns
            ]
        ).to_dicts():
            sym = str(row.get("symbol") or "")
            rd = row.get("report_date")
            if isinstance(rd, datetime):
                rd = rd.date()
            elif not isinstance(rd, date):
                rd = _as_date(rd)
            if not sym or rd is None:
                rid.append(None)
                continue
            ad = row.get("announce_date")
            ud = row.get("update_date")
            if isinstance(ad, datetime):
                ad = ad.date()
            elif not isinstance(ad, date):
                ad = _as_date(ad)
            if isinstance(ud, datetime):
                ud = ud.date()
            elif not isinstance(ud, date):
                ud = _as_date(ud)
            rid.append(
                _restatement_id(sym, rd, ad, ud, str(row.get("source") or "") or None)
            )
        out = out.with_columns(pl.Series("restatement_id", rid))

    # Keep period_end aligned with report_date for legacy consumers
    if "period_end" not in out.columns and "report_date" in out.columns:
        out = out.with_columns(pl.col("report_date").alias("period_end"))
    elif "period_end" in out.columns and "report_date" in out.columns:
        out = out.with_columns(
            pl.coalesce([pl.col("period_end").cast(pl.Date, strict=False), pl.col("report_date")]).alias(
                "period_end"
            )
        )

    if "symbol" in out.columns:
        out = out.with_columns(pl.col("symbol").cast(pl.Utf8).str.to_uppercase())

    # ---- M5.4 available_at / pit_unsafe / history_guarantee ----
    # available_at prefers real announce_date, else update_date (still unsafe if no announce)
    out = out.with_columns(
        pl.coalesce([pl.col("announce_date"), pl.col("update_date")]).alias("available_at")
    )
    # pit_unsafe when no real announce, or shares without authoritative effective date semantics
    unsafe_expr = pl.col("available_at").is_null() | (~pl.col("_had_real_announce").fill_null(False))
    # instruments_snapshot / fetch-day snapshots cannot backfill valuation history;
    # if effective_date equals fetched_at date only, still allow but keep unsafe unless announce exists
    if table == "shares" and "source" in out.columns:
        unsafe_expr = unsafe_expr | pl.col("source").cast(pl.Utf8).str.contains(
            "snapshot|instruments|fetch", literal=False
        ).fill_null(False)
    if "pit_unsafe" in out.columns:
        out = out.with_columns((pl.col("pit_unsafe").fill_null(False) | unsafe_expr).alias("pit_unsafe"))
    else:
        out = out.with_columns(unsafe_expr.alias("pit_unsafe"))
    if "history_guarantee" not in out.columns:
        out = out.with_columns(pl.lit("as_collected").alias("history_guarantee"))
    else:
        out = out.with_columns(pl.col("history_guarantee").cast(pl.Utf8).fill_null("as_collected"))
    out = out.with_columns(
        [
            pl.lit(FINANCIAL_SCHEMA_VERSION).alias("schema_version"),
            pl.lit(FINANCIAL_UNIT_VERSION).alias("unit_version"),
        ]
    )
    if "_had_real_announce" in out.columns:
        out = out.drop("_had_real_announce")

    return out


def merge_financial_pit(
    existing: pl.DataFrame | None,
    new_data: pl.DataFrame,
    *,
    table: str,
) -> pl.DataFrame:
    """Merge retaining restatements.

    Non-shares PK: (symbol, report_date, restatement_id)
    Shares PK: (symbol, effective_date, restatement_id) — historical series, append
    Legacy rows without restatement_id get one assigned via ensure_pit_columns.
    """
    new_df = ensure_pit_columns(new_data, table=table)
    if existing is None or existing.is_empty():
        base = new_df
    else:
        old = ensure_pit_columns(existing, table=table)
        # preserve first_seen_at from old when same restatement_id reappears
        base = pl.concat([old, new_df], how="diagonal_relaxed")

    if table == "shares":
        keys = ["symbol", "effective_date", "restatement_id"]
        # also keep period_end for compatibility = effective_date
        if "period_end" in base.columns and "effective_date" in base.columns:
            base = base.with_columns(
                pl.coalesce(
                    [
                        pl.col("effective_date"),
                        pl.col("period_end").cast(pl.Date, strict=False),
                    ]
                ).alias("effective_date")
            )
            base = base.with_columns(pl.col("effective_date").alias("period_end"))
    else:
        keys = ["symbol", "report_date", "restatement_id"]

    for k in keys:
        if k not in base.columns:
            raise ValueError(f"financial pit merge missing key {k}")

    # Drop null keys
    base = base.drop_nulls(subset=[k for k in keys if k != "restatement_id"])
    # restatement_id nulls: treat as unstable; drop rather than collapsing history incorrectly
    base = base.filter(pl.col("restatement_id").is_not_null() & (pl.col("restatement_id") != ""))

    # Prefer newest fetched_at when identical restatement_id
    sort_cols = [c for c in ("fetched_at", "update_date", "announce_date") if c in base.columns]
    if sort_cols:
        base = base.sort(keys + sort_cols)
    merged = base.unique(subset=keys, keep="last")
    order = ["symbol", "report_date" if table != "shares" else "effective_date"]
    order = [c for c in order if c in merged.columns]
    return merged.sort(order)


def staging_atomic_replace_financial_table(
    data_dir: Path,
    table: str,
    frame: pl.DataFrame,
) -> dict[str, Any]:
    """Write full table via staging then atomic replace."""
    if table not in FINANCIAL_TABLES:
        raise ValueError(table)
    data_dir = Path(data_dir)
    out_dir = data_dir / "financials" / table
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "part.parquet"
    staging_dir = data_dir / ".staging" / "financials" / table
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging = staging_dir / "part.parquet"
    frame = ensure_pit_columns(frame, table=table)
    atomic_write_parquet(frame, staging)
    # atomic replace into formal path
    atomic_write_parquet(frame, target)
    sources = sorted(
        {
            str(value).strip()
            for value in frame.get_column("source").drop_nulls().unique().to_list()
            if str(value).strip()
        }
    )
    source = sources[0] if len(sources) == 1 else f"mixed:{','.join(sources)}"
    run_id = f"financial-pit-{table}-{uuid.uuid4().hex}"
    lineage_path = write_lineage_record(
        data_dir,
        FINANCIAL_DATASET_IDS[table],
        {
            "run_id": run_id,
            "dataset_id": FINANCIAL_DATASET_IDS[table],
            "source": source or "unknown",
            "sources": sources,
            "unit_version": FINANCIAL_UNIT_VERSION,
            "quality_status": "healthy",
            "row_count": int(frame.height),
            "target_artifact": f"financials/{table}/part.parquet",
            "migration": "financial_pit_v2",
            "date": date.today().isoformat(),
        },
        run_id=run_id,
    )
    # cleanup staging best-effort
    with contextlib.suppress(Exception):
        staging.unlink(missing_ok=True)
    return {
        "table": table,
        "path": str(target),
        "lineage_path": str(lineage_path),
        "rows": int(frame.height),
        "symbols": int(frame.get_column("symbol").n_unique()) if "symbol" in frame.columns and frame.height else 0,
    }


def filter_as_of(
    df: pl.DataFrame,
    as_of: date,
    *,
    table: str = "metrics",
    strict: bool = True,
) -> pl.DataFrame:
    """Point-in-time filter.

    Strict (default, Agent/backtest):
      - available_at is not null and available_at <= as_of
      - pit_unsafe == False
    Non-strict (UI):
      - uses available_at when present; may include pit_unsafe rows for display

    For shares: also require effective_date <= as_of. Snapshot-only shares remain
    pit_unsafe and are excluded in strict mode.
    """
    if df is None or df.is_empty():
        return df if df is not None else pl.DataFrame()
    out = ensure_pit_columns(df, table=table)

    if strict:
        out = out.filter(
            pl.col("available_at").is_not_null()
            & (pl.col("available_at") <= as_of)
            & (pl.col("pit_unsafe") == False)  # noqa: E712
        )
    else:
        # UI path: prefer available_at, but do not invent from report_date
        out = out.filter(
            pl.col("available_at").is_not_null() & (pl.col("available_at") <= as_of)
        )
    if out.is_empty():
        return out

    if table == "shares":
        out = out.filter(
            pl.col("effective_date").is_not_null() & (pl.col("effective_date") <= as_of)
        )
        if out.is_empty():
            return out
        sort_cols = [c for c in ("fetched_at", "update_date", "announce_date", "available_at") if c in out.columns]
        out = out.sort(["symbol", "effective_date", *sort_cols])
        return out.unique(subset=["symbol", "effective_date"], keep="last").sort(
            ["symbol", "effective_date"]
        )

    sort_cols = [c for c in ("fetched_at", "update_date", "announce_date", "available_at") if c in out.columns]
    out = out.sort(["symbol", "report_date", *sort_cols])
    return out.unique(subset=["symbol", "report_date"], keep="last").sort(
        ["symbol", "report_date"]
    )


def latest_as_of_per_symbol(
    df: pl.DataFrame,
    as_of: date,
    *,
    table: str,
    strict: bool = True,
) -> pl.DataFrame:
    """One row per symbol as-of (latest report_date / effective_date after PIT filter)."""
    filtered = filter_as_of(df, as_of, table=table, strict=strict)
    if filtered.is_empty():
        return filtered
    key = "effective_date" if table == "shares" else "report_date"
    filtered = filtered.sort(["symbol", key])
    return filtered.unique(subset=["symbol"], keep="last")


def append_shares_history(
    data_dir: Path,
    snapshot: pl.DataFrame,
    *,
    effective_date: date | None = None,
) -> pl.DataFrame:
    """Append a shares cross-section as historical points (does not delete prior)."""
    data_dir = Path(data_dir)
    path = data_dir / "financials" / "shares" / "part.parquet"
    existing = pl.read_parquet(path) if path.exists() else pl.DataFrame()
    snap = snapshot
    if snap.is_empty():
        return ensure_pit_columns(existing, table="shares") if not existing.is_empty() else snap
    eff = effective_date or date.today()
    snap = snap.with_columns(
        [
            pl.lit(eff).alias("effective_date"),
            pl.lit(eff).alias("period_end"),
            pl.lit(eff).alias("report_date"),
            pl.lit(eff).alias("announce_date"),
        ]
    )
    snap = ensure_pit_columns(snap, table="shares", default_source="instruments_snapshot")
    merged = merge_financial_pit(existing if not existing.is_empty() else None, snap, table="shares")
    return merged


def migrate_existing_financials_to_pit(data_dir: Path, *, tables: Sequence[str] | None = None) -> dict[str, Any]:
    """One-shot local migration: add PIT columns + restatement_id; retain rows.

    Uses staging atomic replace. Does not fetch network data.
    """
    data_dir = Path(data_dir)
    tables = tuple(tables or FINANCIAL_TABLES)
    out: dict[str, Any] = {"tables": {}, "ok": True}
    for table in tables:
        path = data_dir / "financials" / table / "part.parquet"
        if not path.exists():
            out["tables"][table] = {"exists": False}
            continue
        try:
            df = pl.read_parquet(path)
            # shares: ensure effective_date history from period_end
            if table == "shares" and "effective_date" not in df.columns and "period_end" in df.columns:
                df = df.with_columns(pl.col("period_end").alias("effective_date"))
            merged = merge_financial_pit(None, df, table=table)
            # For non-shares, collapsing identical restatement_ids is fine; different
            # announce/update produce different restatement_ids and are retained.
            info = staging_atomic_replace_financial_table(data_dir, table, merged)
            info["exists"] = True
            # estimate restatement retention: rows vs unique symbol+report_date
            if table != "shares" and "report_date" in merged.columns:
                uniq = merged.select(["symbol", "report_date"]).unique().height
                info["unique_symbol_report"] = int(uniq)
                info["restatement_extra_rows"] = int(merged.height - uniq)
            out["tables"][table] = info
        except Exception as exc:
            out["ok"] = False
            out["tables"][table] = {"exists": True, "error": str(exc)}
            logger.exception("migrate financials/%s failed", table)
    return out

def pit_warning_payload(df: pl.DataFrame, *, table: str = "metrics") -> dict[str, object]:
    """Ordinary financial page warning when non-PIT rows are present."""
    if df is None or df.is_empty():
        return {"has_non_pit_rows": False, "non_pit_rows": 0, "warning": None}
    out = ensure_pit_columns(df, table=table)
    unsafe = int(out.filter(pl.col("pit_unsafe") == True).height)  # noqa: E712
    missing = int(out.filter(pl.col("available_at").is_null()).height)
    non_pit = max(unsafe, missing)
    return {
        "has_non_pit_rows": non_pit > 0,
        "non_pit_rows": non_pit,
        "unsafe_rows": unsafe,
        "missing_available_at_rows": missing,
        "history_guarantee": "as_collected",
        "warning": (
            "包含非严格 PIT 财务行(无权威 announce/available_at 或来自抓取快照); "
            "Agent/回测严格模式不会使用这些行"
            if non_pit > 0
            else None
        ),
    }


def migrate_financial_table_to_v2(data_dir: Path, table: str) -> dict[str, object]:
    """Rewrite one financial table with v2 PIT columns (RC/candidate safe)."""
    if table not in FINANCIAL_TABLES:
        raise ValueError(table)
    path = Path(data_dir) / "financials" / table / "part.parquet"
    if not path.exists():
        return {"table": table, "ok": True, "skipped": True, "reason": "missing"}
    frame = pl.read_parquet(path)
    upgraded = ensure_pit_columns(frame, table=table)
    if table == "shares" and "source" in upgraded.columns:
        upgraded = upgraded.with_columns(
            (
                pl.col("pit_unsafe").fill_null(False)
                | pl.col("source")
                .cast(pl.Utf8)
                .str.contains("snapshot|instruments", literal=False)
                .fill_null(False)
            ).alias("pit_unsafe")
        )
    result = staging_atomic_replace_financial_table(Path(data_dir), table, upgraded)
    result["pit_warning"] = pit_warning_payload(upgraded, table=table)
    result["ok"] = True
    return result

