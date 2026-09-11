"""Public A-share financial statements via East Money HSF10 (no TickFlow).

Tables (aligned with financial_sync / financial_analyzer / TickFlow SDK):
  - metrics
  - income
  - balance_sheet
  - cash_flow
  - shares  (snapshot from instruments; TickFlow-compatible shape)

Writes: data/financials/{table}/part.parquet

Sources (protocol intelligence from akshare three_report_em / adata core index):
  - dates:  .../NewFinanceAnalysis/{zcfzb|lrb|xjllb}DateAjaxNew
  - body:   .../NewFinanceAnalysis/{zcfzb|lrb|xjllb}AjaxNew  (POST)
  - metrics: datacenter RPT_F10_FINANCE_MAINFINADATA
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client
from app.services.atomic_io import atomic_write_parquet

logger = logging.getLogger(__name__)

FINANCIAL_TABLES = ("metrics", "income", "balance_sheet", "cash_flow", "shares")
STATEMENT_TABLES = ("metrics", "income", "balance_sheet", "cash_flow")
DEFAULT_MAX_PERIODS = 12

_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://emweb.securities.eastmoney.com/",
}

_DATE_AJAX = {
    "income": "lrbDateAjaxNew",
    "balance_sheet": "zcfzbDateAjaxNew",
    "cash_flow": "xjllbDateAjaxNew",
}
_BODY_AJAX = {
    "income": "lrbAjaxNew",
    "balance_sheet": "zcfzbAjaxNew",
    "cash_flow": "xjllbAjaxNew",
}

# Canonical rename maps (EastMoney UPPER → snake). Keep source extras under raw_* if needed later.
_COMMON = {
    "SECUCODE": "secucode",
    "SECURITY_CODE": "security_code",
    "SECURITY_NAME_ABBR": "name",
    "REPORT_DATE": "period_end",
    "REPORT_TYPE": "report_type",
    "REPORT_DATE_NAME": "report_name",
    "NOTICE_DATE": "notice_date",
    "UPDATE_DATE": "update_date",
    "CURRENCY": "currency",
}

_INCOME_MAP = {
    **_COMMON,
    "TOTAL_OPERATE_INCOME": "total_revenue",
    "TOTAL_OPERATE_INCOME_YOY": "total_revenue_yoy",
    "OPERATE_INCOME": "operate_revenue",
    "OPERATE_INCOME_YOY": "operate_revenue_yoy",
    "TOTAL_OPERATE_COST": "total_operate_cost",
    "OPERATE_COST": "operate_cost",
    "OPERATE_PROFIT": "operate_profit",
    "OPERATE_PROFIT_YOY": "operate_profit_yoy",
    "TOTAL_PROFIT": "total_profit",
    "TOTAL_PROFIT_YOY": "total_profit_yoy",
    "INCOME_TAX": "income_tax",
    "NETPROFIT": "net_profit",
    "NETPROFIT_YOY": "net_profit_yoy",
    "PARENT_NETPROFIT": "parent_net_profit",
    "PARENT_NETPROFIT_YOY": "parent_net_profit_yoy",
    "DEDUCT_PARENT_NETPROFIT": "deduct_parent_net_profit",
    "BASIC_EPS": "basic_eps",
    "DILUTED_EPS": "diluted_eps",
    # expense / other lines (TickFlow IncomeRecord)
    "SALE_EXPENSE": "selling_expense",
    "MANAGE_EXPENSE": "admin_expense",
    "RESEARCH_EXPENSE": "rd_expense",
    "FINANCE_EXPENSE": "financial_expense",
    "NONBUSINESS_INCOME": "non_operating_income",
    "NONBUSINESS_EXPENSE": "non_operating_expense",
    "INTEREST_INCOME": "interest_income",
    "INTEREST_EXPENSE": "interest_expense",
    "OPERATE_TAX_ADD": "operate_tax_add",
    "ASSET_IMPAIRMENT_LOSS": "asset_impairment_loss",
    "CREDIT_IMPAIRMENT_INCOME": "credit_impairment_income",
    "INVEST_INCOME": "invest_income",
    "OTHER_INCOME": "other_income",
}

_BALANCE_MAP = {
    **_COMMON,
    "TOTAL_ASSETS": "total_assets",
    "TOTAL_LIABILITIES": "total_liabilities",
    "TOTAL_EQUITY": "total_equity",
    "TOTAL_PARENT_EQUITY": "total_parent_equity",
    "TOTAL_CURRENT_ASSETS": "total_current_assets",
    "TOTAL_NONCURRENT_ASSETS": "total_noncurrent_assets",
    "TOTAL_CURRENT_LIAB": "total_current_liab",
    "TOTAL_NONCURRENT_LIAB": "total_noncurrent_liab",
    "MONETARYFUNDS": "monetary_funds",
    "ACCOUNTS_RECE": "accounts_receivable",
    "INVENTORY": "inventory",
    "FIXED_ASSET": "fixed_assets",
    "SHORT_LOAN": "short_loan",
    "LONG_LOAN": "long_loan",
    "ACCOUNTS_PAYABLE": "accounts_payable",
    "ADVANCE_RECEIVABLES": "advance_receivables",
    "NOTE_ACCOUNTS_RECE": "note_accounts_receivable",
    "NOTE_ACCOUNTS_PAYABLE": "note_accounts_payable",
    # equity / asset details (TickFlow BalanceSheetRecord)
    "INTANGIBLE_ASSET": "intangible_assets",
    "GOODWILL": "goodwill",
    # EM API typo: UNASSIGN_RPOFIT
    "UNASSIGN_RPOFIT": "retained_earnings",
    "UNASSIGN_PROFIT": "retained_earnings",
    "MINORITY_EQUITY": "minority_interest",
    "SHARE_CAPITAL": "share_capital",
    "CAPITAL_RESERVE": "capital_reserve",
    "SURPLUS_RESERVE": "surplus_reserve",
    "TREASURY_SHARES": "treasury_shares",
}

_CASH_MAP = {
    **_COMMON,
    "NETCASH_OPERATE": "netcash_operate",
    "NETCASH_INVEST": "netcash_invest",
    "NETCASH_FINANCE": "netcash_finance",
    "CCE_ADD": "cce_add",
    "END_CCE": "end_cce",
    "BEGIN_CCE": "begin_cce",
    "END_CASH": "end_cash",
    "BEGIN_CASH": "begin_cash",
    "SALES_SERVICES": "sales_services",
    "PAY_ALL_TAX": "pay_all_tax",
    "PAY_STAFF_CASH": "pay_staff_cash",
    "CONSTRUCT_LONG_ASSET": "construct_long_asset",
}

_METRICS_MAP = {
    "SECUCODE": "secucode",
    "SECURITY_CODE": "security_code",
    "SECURITY_NAME_ABBR": "name",
    "REPORT_DATE": "period_end",
    "REPORT_TYPE": "report_type",
    "REPORT_DATE_NAME": "report_name",
    "NOTICE_DATE": "notice_date",
    "UPDATE_DATE": "update_date",
    "CURRENCY": "currency",
    "EPSJB": "basic_eps",
    "EPSKCJB": "diluted_eps",
    "EPSXS": "non_gaap_eps",
    "BPS": "bps",
    "MGZBGJ": "cap_reserve_ps",
    "MGWFPLR": "undist_profit_ps",
    "MGJYXJJE": "oper_cf_ps",
    "TOTALOPERATEREVE": "total_revenue",
    "MLR": "gross_profit",
    "PARENTNETPROFIT": "parent_net_profit",
    "KCFJCXSYJLR": "non_gaap_net_profit",
    "TOTALOPERATEREVETZ": "total_revenue_yoy",
    "PARENTNETPROFITTZ": "parent_net_profit_yoy",
    "KCFJCXSYJLRTZ": "non_gaap_net_profit_yoy",
    "YYZSRGDHBZC": "total_revenue_qoq",
    "NETPROFITRPHBZC": "net_profit_qoq",
    "ROEJQ": "roe",
    "ROEKCJQ": "roe_non_gaap",
    "ZZCJLL": "roa",
    "XSMLL": "gross_margin",
    "XSJLL": "net_margin",
    "YSZKYYSR": "adv_receipts_to_rev",
    "XSJXLYYSR": "net_cf_sales_to_rev",
    "JYXJLYYSR": "oper_cf_to_rev",
    "TAXRATE": "eff_tax_rate",
    "LD": "current_ratio",
    "SD": "quick_ratio",
    "XJLLB": "cash_flow_ratio",
    "ZCFZL": "asset_liab_ratio",
    "QYCS": "equity_multiplier",
    "CQBL": "equity_ratio",
    "ZZCZZTS": "total_asset_turn_days",
    "CHZZTS": "inv_turn_days",
    "YSZKZZTS": "acct_recv_turn_days",
    "TOAZZL": "total_asset_turn_rate",
    "CHZZL": "inv_turn_rate",
    "YSZKZZL": "acct_recv_turn_rate",
}


def to_em_code(symbol: str) -> str | None:
    """000001.SZ -> sz000001 ; SH600519 -> sh600519."""
    s = (symbol or "").strip().upper()
    if not s:
        return None
    if s.startswith(("SH", "SZ", "BJ")) and len(s) >= 8 and s[2:8].isdigit():
        return f"{s[:2].lower()}{s[2:8]}"
    if "." in s:
        code, ex = s.split(".", 1)
    else:
        code, ex = s, ""
    code = code.zfill(6) if code.isdigit() else code
    if not (code.isdigit() and len(code) == 6):
        return None
    if ex == "SH" or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if ex == "BJ" or code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def to_std_symbol(symbol: str) -> str:
    em = to_em_code(symbol)
    if not em:
        return (symbol or "").strip().upper()
    mkt, code = em[:2], em[2:]
    return f"{code}.{mkt.upper()}"


def to_em_report_code(symbol: str) -> str | None:
    """SH600519 style used by HSF10 ajax."""
    em = to_em_code(symbol)
    if not em:
        return None
    return f"{em[:2].upper()}{em[2:]}"


def _parse_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


_CTYPE_CACHE: dict[str, str] = {}


def detect_company_type(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
) -> str:
    """Parse company type from HSF10 page ``hidctype`` (akshare-compatible).

    Banks/insurance use non-4 types; wrong type yields empty balance/cash tables.
    """
    em = to_em_code(symbol)
    if not em:
        return "4"
    if em in _CTYPE_CACHE:
        return _CTYPE_CACHE[em]
    client = client or get_shared_client()
    from urllib.parse import urlencode

    url = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index"
    full = f"{url}?{urlencode({'type': 'web', 'code': em})}"
    res = client.get_text(full, source_key="em_hsf10_index", headers=_EM_HEADERS, timeout=15.0)
    ctype = "4"
    if res.ok and res.text:
        text = res.text
        mm = re.search(r'id=["\']hidctype["\'][^>]*value=["\'](\d+)["\']', text, flags=re.I)
        if not mm:
            mm = re.search(r'value=["\'](\d+)["\'][^>]*id=["\']hidctype["\']', text, flags=re.I)
        if not mm:
            mm = re.search(r'name=["\']hidctype["\'][^>]*value=["\'](\d+)["\']', text, flags=re.I)
        if mm:
            ctype = mm.group(1)
    _CTYPE_CACHE[em] = ctype
    return ctype


def _http_get_json(client: ResilientHttpClient, url: str, *, source_key: str, params: dict | None = None) -> Any:
    from urllib.parse import urlencode

    full = url if not params else f"{url}?{urlencode(params)}"
    res = client.get_json(full, source_key=source_key, headers=_EM_HEADERS, timeout=20.0, parse_json=True)
    if not res.ok:
        raise RuntimeError(res.error or f"GET failed {source_key}")
    return res.data


def _http_post_json(client: ResilientHttpClient, url: str, *, source_key: str, data: dict) -> Any:
    """POST form body; small dedicated call (not on ResilientHttpClient)."""
    import httpx

    # Per-request key so one symbol failure does not block the whole table.
    key = f"{source_key}:{data.get('code','')}"
    if client.cooldown.is_cooling(key):
        raise RuntimeError(f"cooldown {client.cooldown.remaining(key):.1f}s")
    try:
        resp = httpx.post(url, data=data, headers=_EM_HEADERS, timeout=25.0, follow_redirects=True)
        if resp.status_code >= 400:
            client.cooldown.trip(key, 15.0)
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.json()
    except Exception as exc:
        client.cooldown.trip(key, 15.0)
        raise RuntimeError(str(exc)) from exc


def fetch_report_dates(
    symbol: str,
    table: str,
    *,
    company_type: str = "4",
    client: ResilientHttpClient | None = None,
    max_dates: int = 12,
) -> list[str]:
    """Return REPORT_DATE strings YYYY-MM-DD newest first."""
    if table not in _DATE_AJAX:
        raise ValueError(table)
    code = to_em_report_code(symbol)
    if not code:
        return []
    client = client or get_shared_client()
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/{_DATE_AJAX[table]}"
    data = _http_get_json(
        client,
        url,
        source_key=f"em_fin_dates_{table}",
        params={"companyType": company_type, "reportDateType": "0", "code": code},
    )
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    for row in rows:
        d = _parse_date((row or {}).get("REPORT_DATE"))
        if d:
            out.append(d.isoformat())
    return out[:max_dates]


def _normalize_statement_rows(
    rows: list[dict],
    *,
    symbol: str,
    table: str,
    field_map: dict[str, str],
) -> list[dict]:
    out: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        rec: dict[str, Any] = {
            "symbol": symbol,
            "source": "eastmoney_hsf10",
            "table": table,
        }
        pe = _parse_date(raw.get("REPORT_DATE"))
        if pe is None:
            continue
        rec["period_end"] = pe
        for src, dst in field_map.items():
            if src not in raw:
                continue
            val = raw[src]
            if dst in {"period_end", "notice_date", "update_date"}:
                rec[dst] = _parse_date(val)
            elif dst in {
                "secucode",
                "security_code",
                "name",
                "report_type",
                "report_name",
                "currency",
                "source",
                "table",
                "symbol",
            }:
                rec[dst] = None if val is None else str(val)
            else:
                rec[dst] = _to_float(val)
        out.append(rec)
    return out


# East Money HSF10 body endpoints accept many dates but only return ~5 rows per call.
_EM_STATEMENT_DATE_CHUNK = 5


def fetch_statement_table(
    symbol: str,
    table: str,
    *,
    company_type: str | None = None,
    max_periods: int = DEFAULT_MAX_PERIODS,
    client: ResilientHttpClient | None = None,
) -> pl.DataFrame:
    """Fetch one of income/balance_sheet/cash_flow for a symbol.

    EM body APIs silently cap each response at ~5 report periods even when more
    dates are requested. We chunk dates and merge to honor max_periods.
    """
    if table not in _BODY_AJAX:
        raise ValueError(f"not a statement table: {table}")
    sym = to_std_symbol(symbol)
    code = to_em_report_code(sym)
    empty = pl.DataFrame()
    if not code:
        return empty
    client = client or get_shared_client()
    ctype = company_type or detect_company_type(sym, client=client)
    dates = fetch_report_dates(sym, table, company_type=ctype, client=client, max_dates=max_periods)
    if not dates:
        for alt in ("3", "4", "2", "1"):
            if alt == str(ctype):
                continue
            dates = fetch_report_dates(sym, table, company_type=alt, client=client, max_dates=max_periods)
            if dates:
                ctype = alt
                em_key = to_em_code(sym)
                if em_key:
                    _CTYPE_CACHE[em_key] = alt
                break
    if not dates:
        return empty

    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/{_BODY_AJAX[table]}"
    rows_all: list[dict] = []
    chunk_size = max(1, int(_EM_STATEMENT_DATE_CHUNK))
    for i in range(0, len(dates), chunk_size):
        chunk = dates[i : i + chunk_size]
        payload = {
            "companyType": ctype,
            "reportDateType": "0",
            "reportType": "1",
            "dates": ",".join(chunk),
            "code": code,
        }
        data = None
        try:
            data = _http_post_json(client, url, source_key=f"em_fin_body_{table}", data=payload)
        except Exception as e:
            logger.debug("POST %s chunk failed: %s", table, e)
        rows = (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            try:
                data = _http_get_json(client, url, source_key=f"em_fin_body_get_{table}", params=payload)
                rows = (data or {}).get("data") if isinstance(data, dict) else None
            except Exception as e:
                logger.debug("GET %s chunk failed: %s", table, e)
                rows = None
        if isinstance(rows, list) and rows:
            rows_all.extend(rows)

    if not rows_all:
        return empty
    fmap = {"income": _INCOME_MAP, "balance_sheet": _BALANCE_MAP, "cash_flow": _CASH_MAP}[table]
    norm = _normalize_statement_rows(rows_all, symbol=sym, table=table, field_map=fmap)
    if not norm:
        return empty
    df = pl.DataFrame(norm)
    if "period_end" in df.columns:
        df = df.unique(subset=["symbol", "period_end"], keep="first").sort("period_end", descending=True)
        if max_periods and max_periods > 0:
            df = df.head(max_periods)
    return df


def _metrics_unique_periods(rows: list[dict]) -> int:
    seen: set[date] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        pe = _parse_date(raw.get("REPORT_DATE"))
        if pe is not None:
            seen.add(pe)
    return len(seen)


def _fetch_metrics_chunk(
    client: ResilientHttpClient,
    *,
    em_dot: str,
    report_type: str | None,
    max_periods: int,
) -> list[dict]:
    url = "https://datacenter.eastmoney.com/securities/api/data/get"
    if report_type:
        filt = f'(SECUCODE="{em_dot}")(REPORT_TYPE="{report_type}")'
    else:
        # One broader pull first — fewer round-trips when EM returns mixed report types.
        filt = f'(SECUCODE="{em_dot}")'
    params = {
        "type": "RPT_F10_FINANCE_MAINFINADATA",
        "sty": "APP_F10_MAINFINADATA",
        "filter": filt,
        "p": "1",
        "ps": str(max(8, int(max_periods) * 2)),
        "sr": "-1",
        "st": "REPORT_DATE",
        "source": "HSF10",
        "client": "PC",
    }
    try:
        data = _http_get_json(client, url, source_key="em_fin_metrics", params=params)
    except Exception as e:
        logger.debug("metrics %s %s failed: %s", em_dot, report_type or "*", e)
        return []
    if not isinstance(data, dict):
        return []
    if data.get("code") not in (0, "0", None) and not data.get("success"):
        return []
    result = (data or {}).get("result") or {}
    chunk = result.get("data") if isinstance(result, dict) else None
    return chunk if isinstance(chunk, list) else []


def fetch_metrics(
    symbol: str,
    *,
    max_periods: int = DEFAULT_MAX_PERIODS,
    client: ResilientHttpClient | None = None,
) -> pl.DataFrame:
    """Core financial metrics from East Money MAINFINADATA (all report types)."""
    sym = to_std_symbol(symbol)
    em_dot = sym  # 600519.SH
    if "." not in em_dot:
        return pl.DataFrame()
    client = client or get_shared_client()
    need = max(1, int(max_periods or DEFAULT_MAX_PERIODS))
    rows_all: list[dict] = []

    # Prefer 1 request; fall back to report-type loop only if depth is insufficient.
    rows_all.extend(_fetch_metrics_chunk(client, em_dot=em_dot, report_type=None, max_periods=need))
    if _metrics_unique_periods(rows_all) < need:
        for report_type in ("年报", "三季报", "中报", "一季报"):
            chunk = _fetch_metrics_chunk(
                client, em_dot=em_dot, report_type=report_type, max_periods=need
            )
            if chunk:
                rows_all.extend(chunk)
            if _metrics_unique_periods(rows_all) >= need:
                break

    if not rows_all:
        return pl.DataFrame()
    norm = _normalize_statement_rows(rows_all, symbol=sym, table="metrics", field_map=_METRICS_MAP)
    if not norm:
        return pl.DataFrame()
    df = pl.DataFrame(norm)
    df = df.unique(subset=["symbol", "period_end"], keep="first").sort("period_end", descending=True)
    if max_periods:
        df = df.head(max_periods)
    return df


def fetch_financials_symbol(
    symbol: str,
    *,
    tables: Sequence[str] = FINANCIAL_TABLES,
    max_periods: int = DEFAULT_MAX_PERIODS,
    client: ResilientHttpClient | None = None,
) -> dict[str, pl.DataFrame]:
    client = client or get_shared_client()
    sym = to_std_symbol(symbol)
    out: dict[str, pl.DataFrame] = {}
    ctype: str | None = None
    for t in tables:
        if t not in FINANCIAL_TABLES:
            continue
        try:
            if t == "metrics":
                out[t] = fetch_metrics(sym, max_periods=max_periods, client=client)
            elif t == "shares":
                # filled once per sync via instruments snapshot (see sync_financials_public)
                out[t] = pl.DataFrame()
            else:
                if ctype is None:
                    try:
                        ctype = detect_company_type(sym, client=client)
                    except Exception:
                        ctype = "4"
                out[t] = fetch_statement_table(
                    sym, t, company_type=ctype, max_periods=max_periods, client=client
                )
        except Exception as e:
            logger.warning("fetch financials %s %s failed: %s", sym, t, e)
            out[t] = pl.DataFrame()
    return out


def merge_write_financial_table(
    new_data: pl.DataFrame,
    data_dir: Path,
    table: str,
) -> int:
    """Merge by (symbol, period_end) into financials/{table}/part.parquet. Returns row count written."""
    if table not in FINANCIAL_TABLES:
        raise ValueError(table)
    out_dir = Path(data_dir) / "financials" / table
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "part.parquet"

    if new_data is None or new_data.is_empty():
        return pl.read_parquet(out).height if out.exists() else 0

    df = new_data
    if "symbol" not in df.columns or "period_end" not in df.columns:
        raise ValueError("financial frame requires symbol + period_end")
    df = df.with_columns(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("period_end").cast(pl.Date, strict=False),
    ).drop_nulls(subset=["symbol", "period_end"])

    try:
        from app.services.financial_sync import (
            _tag_financial_route,
            financial_cache_usable,
            financial_write_route,
        )

        route = financial_write_route()
        if route not in {"public", "tickflow"}:
            logger.info(
                "financials/%s public merge skipped for route=%s (no custom mix)",
                table, route,
            )
            return pl.read_parquet(out).height if out.exists() else 0
        df = _tag_financial_route(df)
        if out.exists():
            existing = pl.read_parquet(out)
            if not financial_cache_usable(existing, route):
                logger.info("financials/%s replace stale file for route=%s", table, route)
                existing = df.head(0)
            merged = pl.concat([existing, df], how="diagonal_relaxed")
            merged = merged.unique(subset=["symbol", "period_end"], keep="last").sort(
                ["symbol", "period_end"]
            )
        else:
            merged = df.unique(subset=["symbol", "period_end"], keep="last").sort(
                ["symbol", "period_end"]
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("financial route gate unavailable, leftover merge: %s", exc)
        if out.exists():
            existing = pl.read_parquet(out)
            merged = pl.concat([existing, df], how="diagonal_relaxed")
            merged = merged.unique(subset=["symbol", "period_end"], keep="last").sort(
                ["symbol", "period_end"]
            )
        else:
            merged = df.unique(subset=["symbol", "period_end"], keep="last").sort(
                ["symbol", "period_end"]
            )
    atomic_write_parquet(merged, out)
    logger.info("financials/%s wrote %d rows -> %s", table, merged.height, out)
    return int(merged.height)


def build_shares_from_instruments(
    data_dir: Path,
    symbols: Sequence[str] | None = None,
) -> pl.DataFrame:
    """Build TickFlow-compatible shares snapshot from instruments parquet.

    TickFlow `financials.shares` is a period series; free desk does not have a
    stable public historical shares time-series. We materialize the latest
    cross-section as period_end=as_of so API/UI shape matches SharesRecord:
      symbol, period_end, total_shares, float_shares, announce_date, source
    """
    inst_path = Path(data_dir) / "instruments" / "instruments.parquet"
    if not inst_path.exists():
        return pl.DataFrame()
    try:
        df = pl.read_parquet(inst_path)
    except Exception as e:
        logger.warning("read instruments for shares failed: %s", e)
        return pl.DataFrame()
    if df.is_empty() or "symbol" not in df.columns:
        return pl.DataFrame()

    df = df.with_columns(pl.col("symbol").cast(pl.Utf8).str.to_uppercase())
    if symbols is not None:
        want = {str(s).strip().upper() for s in symbols if s}
        df = df.filter(pl.col("symbol").is_in(list(want)))

    today = date.today()
    if "as_of" in df.columns:
        period_expr = pl.col("as_of").cast(pl.Date, strict=False).fill_null(today)
    else:
        period_expr = pl.lit(today)

    exprs = [
        pl.col("symbol"),
        period_expr.alias("period_end"),
        period_expr.alias("announce_date"),
        pl.lit("instruments_snapshot").alias("source"),
        pl.lit("shares").alias("table"),
    ]
    if "total_shares" in df.columns:
        exprs.append(pl.col("total_shares").cast(pl.Float64, strict=False))
    else:
        exprs.append(pl.lit(None).cast(pl.Float64).alias("total_shares"))
    if "float_shares" in df.columns:
        exprs.append(pl.col("float_shares").cast(pl.Float64, strict=False))
    else:
        exprs.append(pl.lit(None).cast(pl.Float64).alias("float_shares"))
    if "name" in df.columns:
        exprs.append(pl.col("name").cast(pl.Utf8))

    out = df.select(exprs).drop_nulls(subset=["symbol"])
    out = out.filter(
        pl.col("total_shares").is_not_null() | pl.col("float_shares").is_not_null()
    )
    return out.unique(subset=["symbol", "period_end"], keep="last").sort(["symbol", "period_end"])


def sync_shares_snapshot(data_dir: Path, symbols: Sequence[str] | None = None) -> int:
    df = build_shares_from_instruments(data_dir, symbols=symbols)
    if df.is_empty():
        return 0
    return merge_write_financial_table(df, data_dir, "shares")



def _period_stats_by_symbol(data_dir: Path, table: str) -> dict[str, dict[str, Any]]:
    """Return {symbol: {count, newest}} for a financials table parquet."""
    path = Path(data_dir) / "financials" / table / "part.parquet"
    if not path.exists():
        return {}
    try:
        from app.services.financial_sync import get_financial_df

        df = get_financial_df(Path(data_dir), table)
    except Exception as e:
        logger.debug("read financials/%s stats failed: %s", table, e)
        return {}
    if df.is_empty() or "symbol" not in df.columns:
        return {}
    if "period_end" not in df.columns:
        return {
            str(r["symbol"]): {"count": int(r["len"]), "newest": None}
            for r in df.group_by("symbol").len().to_dicts()
        }
    out: dict[str, dict[str, Any]] = {}
    for row in (
        df.group_by("symbol")
        .agg(pl.len().alias("count"), pl.col("period_end").max().alias("newest"))
        .to_dicts()
    ):
        out[str(row["symbol"])] = {
            "count": int(row["count"] or 0),
            "newest": row.get("newest"),
        }
    return out


def _as_date_val(newest: Any) -> date | None:
    if newest is None:
        return None
    try:
        if isinstance(newest, datetime):
            return newest.date()
        if isinstance(newest, date):
            return newest
        return _parse_date(newest)
    except Exception:
        return None


def _last_quarter_ends(today: date | None = None, n: int = 4) -> list[date]:
    """Recent quarter-ends newest first: Mar31/Jun30/Sep30/Dec31."""
    d = today or date.today()
    y, m = d.year, d.month
    # current quarter end
    if m <= 3:
        q_ends = [date(y - 1, 12, 31), date(y - 1, 9, 30), date(y - 1, 6, 30), date(y - 1, 3, 31),
                  date(y - 2, 12, 31)]
    elif m <= 6:
        q_ends = [date(y, 3, 31), date(y - 1, 12, 31), date(y - 1, 9, 30), date(y - 1, 6, 30),
                  date(y - 1, 3, 31)]
    elif m <= 9:
        q_ends = [date(y, 6, 30), date(y, 3, 31), date(y - 1, 12, 31), date(y - 1, 9, 30),
                  date(y - 1, 6, 30)]
    else:
        q_ends = [date(y, 9, 30), date(y, 6, 30), date(y, 3, 31), date(y - 1, 12, 31),
                  date(y - 1, 9, 30)]
    # only ends strictly before today (report period must have ended)
    q_ends = [q for q in q_ends if q < d]
    return q_ends[: max(1, int(n))]


def _is_fresh_enough(newest: Any, prefer_fresh_days: int | None) -> bool:
    """True if local newest period is recent enough.

    ``prefer_fresh_days`` meanings:
      - None / <=0: do not check freshness
      - special -1: calendar rule — newest period_end >= last completed quarter
        (with one-quarter lag tolerance)
      - >0: classic rolling day window from today
    """
    if prefer_fresh_days is None or prefer_fresh_days == 0:
        return True
    d = _as_date_val(newest)
    if d is None:
        return False
    try:
        if int(prefer_fresh_days) == -1:
            # Allow lagging one full quarter behind the latest completed quarter-end.
            ends = _last_quarter_ends(n=2)
            need = ends[-1] if ends else date.today().replace(month=1, day=1)
            return d >= need
        return (date.today() - d).days <= int(prefer_fresh_days)
    except Exception:
        return False



def _financial_sync_state_path(data_dir: Path) -> Path:
    return Path(data_dir) / "financials" / "sync_state.parquet"


def _read_financial_sync_state(data_dir: Path) -> pl.DataFrame:
    path = _financial_sync_state_path(data_dir)
    if not path.exists():
        return pl.DataFrame(schema={
            "symbol": pl.Utf8,
            "checked_at": pl.Utf8,
            "newest": pl.Utf8,
            "count": pl.Int64,
            "ok": pl.Boolean,
        })
    try:
        return pl.read_parquet(path)
    except Exception as e:
        logger.debug("read financial sync_state failed: %s", e)
        return pl.DataFrame(schema={
            "symbol": pl.Utf8,
            "checked_at": pl.Utf8,
            "newest": pl.Utf8,
            "count": pl.Int64,
            "ok": pl.Boolean,
        })


def _recently_checked_financial_symbols(
    data_dir: Path,
    symbols: Sequence[str],
    *,
    within_hours: float | None,
) -> set[str]:
    if within_hours is None or within_hours <= 0:
        return set()
    st = _read_financial_sync_state(data_dir)
    if st.is_empty() or "symbol" not in st.columns or "checked_at" not in st.columns:
        return set()
    want = set(symbols)
    now = datetime.now()
    out: set[str] = set()
    for row in st.select(["symbol", "checked_at"]).to_dicts():
        sym = str(row.get("symbol") or "").upper()
        if sym not in want:
            continue
        raw = row.get("checked_at")
        try:
            s = str(raw).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            if (now - dt).total_seconds() / 3600.0 <= float(within_hours):
                out.add(sym)
        except Exception:
            continue
    return out


def _write_financial_sync_state(
    data_dir: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    path = _financial_sync_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pl.DataFrame(rows).with_columns(
        pl.col("symbol").cast(pl.Utf8),
        pl.col("checked_at").cast(pl.Utf8),
        pl.col("newest").cast(pl.Utf8),
        pl.col("count").cast(pl.Int64, strict=False),
        pl.col("ok").cast(pl.Boolean),
    )
    old = _read_financial_sync_state(data_dir)
    if old.is_empty():
        merged = new_df
    else:
        merged = (
            pl.concat([old, new_df], how="diagonal_relaxed")
            .unique(subset=["symbol"], keep="last")
            .sort("symbol")
        )
    atomic_write_parquet(merged, path)


def _symbols_already_covered(
    data_dir: Path,
    symbols: Sequence[str],
    tables: Sequence[str],
    *,
    min_periods: int,
    prefer_fresh_days: int | None,
) -> set[str]:
    """Symbols that already satisfy depth(+freshness) for all non-shares requested tables."""
    req = [t for t in tables if t in FINANCIAL_TABLES and t != "shares"]
    if not req or min_periods <= 0:
        return set()
    stats = {t: _period_stats_by_symbol(data_dir, t) for t in req}
    covered: set[str] = set()
    for sym in symbols:
        ok = True
        for t in req:
            st = stats[t].get(sym) or {"count": 0, "newest": None}
            if int(st.get("count") or 0) < min_periods:
                ok = False
                break
            if not _is_fresh_enough(st.get("newest"), prefer_fresh_days):
                ok = False
                break
        if ok:
            covered.add(sym)
    return covered


def _flush_financial_buckets(
    buckets: dict[str, list[pl.DataFrame]],
    data_dir: Path,
    rows_out: dict[str, int],
) -> int:
    """Merge pending frames to parquet. Returns number of tables flushed."""
    flushed = 0
    for t, frames in buckets.items():
        if t == "shares" or not frames:
            continue
        new_df = pl.concat(frames, how="diagonal_relaxed")
        rows_out[t] = merge_write_financial_table(new_df, data_dir, t)
        frames.clear()
        flushed += 1
    return flushed


def sync_financials_public(
    symbols: Sequence[str],
    data_dir: Path,
    *,
    tables: Sequence[str] = FINANCIAL_TABLES,
    max_periods: int = DEFAULT_MAX_PERIODS,
    pause_s: float = 0.0,
    on_progress: Callable[[int, int, str], None] | None = None,
    client: ResilientHttpClient | None = None,
    resume: bool = True,
    min_periods: int | None = None,
    prefer_fresh_days: int | None = -1,
    workers: int = 3,
    flush_every: int = 20,
    skip_checked_within_hours: float | None = 18.0,
    max_attempts: int = 2,
    retry_delay_s: float = 0.2,
) -> dict[str, Any]:
    """Pull public financials and merge-write. No TickFlow Cap required.

    Improvements over the original single-pass design:
      - resume/skip symbols already deep+fresh enough in local parquet
      - checkpoint flush every ``flush_every`` successful symbols (interrupt-safe)
      - limited concurrency via ``workers`` (each worker uses its own HTTP client)
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for s in symbols:
        sym = to_std_symbol(s)
        if sym and sym not in seen:
            seen.add(sym)
            ordered.append(sym)

    table_list = [t for t in tables if t in FINANCIAL_TABLES]
    if not table_list:
        table_list = list(FINANCIAL_TABLES)

    need_periods = int(min_periods) if min_periods is not None else int(max_periods)
    need_periods = max(0, need_periods)
    workers_n = max(1, int(workers or 1))
    flush_n = max(1, int(flush_every or 1))
    attempts_n = max(1, int(max_attempts or 1))

    t0 = time.perf_counter()
    skipped_syms: list[str] = []
    todo = list(ordered)
    if resume:
        covered: set[str] = set()
        if need_periods > 0:
            covered |= _symbols_already_covered(
                data_dir,
                ordered,
                table_list,
                min_periods=need_periods,
                prefer_fresh_days=prefer_fresh_days,
            )
        covered |= _recently_checked_financial_symbols(
            data_dir,
            ordered,
            within_hours=skip_checked_within_hours,
        )
        if covered:
            skipped_syms = [s for s in ordered if s in covered]
            todo = [s for s in ordered if s not in covered]
            logger.info(
                "sync_financials resume skip=%d todo=%d min_periods=%d fresh_days=%s "
                "checked_within_h=%s tables=%s",
                len(skipped_syms),
                len(todo),
                need_periods,
                prefer_fresh_days,
                skip_checked_within_hours,
                ",".join(table_list),
            )

    buckets: dict[str, list[pl.DataFrame]] = {t: [] for t in table_list}
    ok_syms: list[str] = list(skipped_syms)  # skipped count as already-ok
    fail_syms: list[str] = []
    rows_out: dict[str, int] = {}
    total = len(ordered)
    done = len(skipped_syms)
    pending_ok = 0

    if on_progress and skipped_syms:
        on_progress(done, total, f"skip {len(skipped_syms)}")

    fetch_tables = tuple(t for t in table_list if t != "shares")

    state_rows: list[dict[str, Any]] = []
    attempts_by_symbol: dict[str, int] = {}
    retried_symbols: list[str] = []

    def _fetch_with_retry(
        sym: str,
        initial_client: ResilientHttpClient | None = None,
    ) -> tuple[dict[str, pl.DataFrame] | None, Exception | None, int]:
        last_error: Exception | None = None
        for attempt in range(1, attempts_n + 1):
            current_client = (
                initial_client
                if attempt == 1 and initial_client is not None
                else ResilientHttpClient(default_timeout=20.0, max_workers=2)
            )
            try:
                got = fetch_financials_symbol(
                    sym,
                    tables=fetch_tables,
                    max_periods=max_periods,
                    client=current_client,
                )
                if any(df is not None and not df.is_empty() for df in (got or {}).values()):
                    return got, None, attempt
                last_error = RuntimeError("empty financial response")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if attempt < attempts_n and retry_delay_s > 0:
                time.sleep(float(retry_delay_s))
        return None, last_error, attempts_n

    def _record_state(sym: str, got: dict[str, pl.DataFrame] | None, ok: bool) -> None:
        newest = None
        count = 0
        # prefer metrics depth for state; fall back to any table
        for key in ("metrics", "income", "balance_sheet", "cash_flow"):
            df = (got or {}).get(key)
            if df is None or df.is_empty() or "period_end" not in df.columns:
                continue
            count = max(count, int(df.height))
            try:
                pe = df["period_end"].max()
                if pe is not None:
                    newest = str(pe)
            except Exception:
                pass
            if key == "metrics":
                break
        state_rows.append({
            "symbol": sym,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "newest": newest or "",
            "count": int(count),
            "ok": bool(ok),
        })

    def _handle_result(sym: str, got: dict[str, pl.DataFrame] | None, err: Exception | None) -> None:
        nonlocal pending_ok
        any_rows = False
        if err is not None:
            logger.warning("sync financials %s failed: %s", sym, err)
            fail_syms.append(sym)
            _record_state(sym, None, False)
            return
        for t, df in (got or {}).items():
            if t in buckets and df is not None and not df.is_empty():
                buckets[t].append(df)
                any_rows = True
        if any_rows:
            ok_syms.append(sym)
            pending_ok += 1
            _record_state(sym, got, True)
            if pending_ok >= flush_n:
                _flush_financial_buckets(buckets, data_dir, rows_out)
                pending_ok = 0
                if state_rows:
                    _write_financial_sync_state(data_dir, state_rows)
                    state_rows.clear()
        else:
            fail_syms.append(sym)
            _record_state(sym, got, False)

    if not todo:
        # still refresh shares snapshot for the requested universe
        pass
    elif workers_n == 1:
        client = client or get_shared_client()
        for sym in todo:
            got, err, attempts = _fetch_with_retry(sym, client)
            attempts_by_symbol[sym] = attempts
            if attempts > 1:
                retried_symbols.append(sym)
            _handle_result(sym, got, err)
            done += 1
            if on_progress:
                on_progress(done, total, sym)
            if pause_s > 0 and done < total:
                time.sleep(pause_s)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _one(sym: str) -> tuple[str, dict[str, pl.DataFrame] | None, Exception | None, int]:
            got, err, attempts = _fetch_with_retry(sym)
            return sym, got, err, attempts

        with ThreadPoolExecutor(max_workers=workers_n, thread_name_prefix="fin-pub") as ex:
            futs = [ex.submit(_one, sym) for sym in todo]
            for fut in as_completed(futs):
                sym, got, err, attempts = fut.result()
                attempts_by_symbol[sym] = attempts
                if attempts > 1:
                    retried_symbols.append(sym)
                _handle_result(sym, got, err)
                done += 1
                if on_progress:
                    on_progress(done, total, sym)
                if pause_s > 0:
                    time.sleep(pause_s)

    if pending_ok:
        _flush_financial_buckets(buckets, data_dir, rows_out)
    if state_rows:
        _write_financial_sync_state(data_dir, state_rows)
        state_rows.clear()

    # Ensure rows_out has current file heights for tables with no new frames
    for t in table_list:
        if t == "shares":
            continue
        if t not in rows_out:
            path = Path(data_dir) / "financials" / t / "part.parquet"
            rows_out[t] = pl.read_parquet(path).height if path.exists() else 0

    try:
        if "shares" in table_list:
            rows_out["shares"] = sync_shares_snapshot(data_dir, symbols=ordered)
    except Exception as e:
        logger.warning("shares snapshot failed: %s", e)
        rows_out["shares"] = 0

    # De-dupe ok list while preserving order
    ok_seen: set[str] = set()
    ok_unique: list[str] = []
    for s in ok_syms:
        if s not in ok_seen:
            ok_seen.add(s)
            ok_unique.append(s)

    return {
        "ok": True,
        "source": "eastmoney_hsf10",
        "requested": total,
        "symbols_ok": ok_unique,
        "symbols_ok_n": len(ok_unique),
        "symbols_fail": fail_syms,
        "symbols_fail_n": len(fail_syms),
        "symbols_skipped": skipped_syms,
        "symbols_skipped_n": len(skipped_syms),
        "symbols_todo_n": len(todo),
        "rows": rows_out,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "path": str(Path(data_dir) / "financials"),
        "resume": bool(resume),
        "workers": workers_n,
        "flush_every": flush_n,
        "min_periods": need_periods,
        "skip_checked_within_hours": skip_checked_within_hours,
        "max_attempts": attempts_n,
        "attempts_by_symbol": attempts_by_symbol,
        "retried_symbols": retried_symbols,
    }
