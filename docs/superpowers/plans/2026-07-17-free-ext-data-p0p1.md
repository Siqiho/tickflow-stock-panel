# Free Ext Data P0/P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a no-subscription TickFlow free-api setup, land free derived/extension data-desk features: approximate chip distribution, stock/board/concept fund flow, daily quality gates, THS concept/industry pull controls, watchlist quote fallback, on-demand intraday, stock changes, F10 snapshot, and lightweight multi-source resilience.

**Architecture:** Keep TickFlow free-api as the only core OHLCV producer. Put new market extras under `backend/app/services/free_sources/` and `ext_data` (snapshot/timeseries). Pure local math (chips, quality) reads existing parquet. Public HTTP sources use `httpx` with timeout/cooldown/partial-fail. Never vendor go-stock/finshare/adata runtimes—reimplement algorithms and endpoints. Core `kline_*` partitions stay free of fund-flow/chip/news fields.

**Tech Stack:** Python 3.11+, FastAPI, Polars, DuckDB, httpx, pytest, existing `ExtConfig`/`write_ext_parquet`/`pipeline_jobs`.

**Worktree:** `/Users/simon/Trading/one-trading/.worktrees/free-ext-data-p0p1` on branch `feature/free-ext-data-p0p1`  
**Data/env:** symlink to main `data/` and `.env` (TICKFLOW key empty / free-api).  
**Do not implement:** TickFlow paid minute/financial/depth, Tushare production, easy_tdx production, chip-race token, EastMoney AI SaaS.

---

## File Map

| Path | Responsibility |
|---|---|
| `backend/app/services/free_sources/__init__.py` | Package exports |
| `backend/app/services/free_sources/http_resilience.py` | timeout, cooldown, in-flight de-dupe, partial results |
| `backend/app/services/free_sources/chip_distribution.py` | local approx chip distribution |
| `backend/app/services/free_sources/fund_flow.py` | EastMoney stock/board/concept fund flow fetch + normalize |
| `backend/app/services/free_sources/quote_fallback.py` | Tencent/Sina watchlist quotes |
| `backend/app/services/free_sources/intraday_public.py` | single-symbol public minute/intraday |
| `backend/app/services/free_sources/stock_changes.py` | EastMoney stock changes |
| `backend/app/services/free_sources/f10_snapshot.py` | EastMoney F10 summary fields |
| `backend/app/services/daily_quality.py` | daily quality gate report |
| `backend/app/api/free_ext.py` | REST for chips/fundflow/changes/f10/quality |
| `backend/app/services/ext_presets.py` | optional THS pull enable helper (default still user-triggered) |
| `backend/app/services/quote_service.py` | wire free quote fallback when TickFlow quote cap missing |
| `backend/app/api/intraday.py` | optional public fallback path |
| `backend/app/main.py` | include free_ext router |
| `backend/app/jobs/daily_pipeline.py` | optional quality stage after daily sync |
| `backend/tests/free_sources/*.py` | unit tests with fixtures / mocked HTTP |

---

### Task 1: HTTP resilience helper (foundation for all public sources)

**Files:**
- Create: `backend/app/services/free_sources/__init__.py`
- Create: `backend/app/services/free_sources/http_resilience.py`
- Test: `backend/tests/free_sources/test_http_resilience.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/free_sources/test_http_resilience.py
from __future__ import annotations

import time

import pytest

from app.services.free_sources.http_resilience import (
    CooldownRegistry,
    InFlightDeduper,
    ResilientHttpClient,
)


def test_cooldown_blocks_until_elapsed():
    reg = CooldownRegistry()
    reg.trip("eastmoney", seconds=0.2)
    assert reg.is_cooling("eastmoney") is True
    time.sleep(0.25)
    assert reg.is_cooling("eastmoney") is False


def test_inflight_dedupes_same_key(monkeypatch):
    deduper = InFlightDeduper()
    calls = {"n": 0}

    def work():
        calls["n"] += 1
        return "ok"

    a = deduper.run("k1", work)
    b = deduper.run("k1", work)
    # sequential call after first completes may run again; concurrent path is what matters.
    # Use concurrent.futures for real dedupe:
    import concurrent.futures

    calls["n"] = 0

    def slow():
        calls["n"] += 1
        time.sleep(0.1)
        return "v"

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(deduper.run, "same", slow) for _ in range(4)]
        vals = [f.result() for f in futs]
    assert vals == ["v", "v", "v", "v"]
    assert calls["n"] == 1


def test_client_returns_partial_on_one_failure(monkeypatch):
    client = ResilientHttpClient(default_timeout=1.0)

    def fake_get(url, **kwargs):
        if "bad" in url:
            raise TimeoutError("boom")
        class R:
            status_code = 200
            def json(self):
                return {"ok": True}
            text = "{}"
        return R()

    monkeypatch.setattr(client, "_get", fake_get)
    results = client.get_many([
        ("good", "https://example.com/good"),
        ("bad", "https://example.com/bad"),
    ])
    assert results["good"].ok is True
    assert results["bad"].ok is False
    assert results["bad"].error
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/simon/Trading/one-trading/.worktrees/free-ext-data-p0p1/backend
uv run pytest tests/free_sources/test_http_resilience.py -v
```
Expected: import/collection failure (module missing).

- [ ] **Step 3: Implement minimal resilience module**

```python
# backend/app/services/free_sources/__init__.py
"""Free public/local data helpers for no-subscription data desk features."""

# backend/app/services/free_sources/http_resilience.py
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass
class FetchResult:
    ok: bool
    data: Any = None
    error: str | None = None
    status_code: int | None = None


class CooldownRegistry:
    def __init__(self) -> None:
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def trip(self, key: str, seconds: float) -> None:
        with self._lock:
            self._until[key] = max(self._until.get(key, 0.0), time.monotonic() + max(0.0, seconds))

    def is_cooling(self, key: str) -> bool:
        with self._lock:
            return time.monotonic() < self._until.get(key, 0.0)

    def remaining(self, key: str) -> float:
        with self._lock:
            return max(0.0, self._until.get(key, 0.0) - time.monotonic())


class InFlightDeduper:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, Future] = {}

    def run(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            fut = self._inflight.get(key)
            if fut is None:
                fut = Future()
                self._inflight[key] = fut
                owner = True
            else:
                owner = False
        if not owner:
            return fut.result()
        try:
            val = fn()
            fut.set_result(val)
            return val
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)


class ResilientHttpClient:
    def __init__(self, default_timeout: float = 8.0, max_workers: int = 4) -> None:
        self.default_timeout = default_timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="free-http")
        self.cooldown = CooldownRegistry()
        self.deduper = InFlightDeduper()

    def _get(self, url: str, *, headers: dict | None = None, timeout: float | None = None) -> httpx.Response:
        return httpx.get(url, headers=headers or {}, timeout=timeout or self.default_timeout, follow_redirects=True)

    def get_json(
        self,
        url: str,
        *,
        source_key: str | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
        cooldown_on_error: float = 30.0,
    ) -> FetchResult:
        key = source_key or url
        if self.cooldown.is_cooling(key):
            return FetchResult(ok=False, error=f"cooldown {self.cooldown.remaining(key):.1f}s")

        def work() -> FetchResult:
            try:
                resp = self._get(url, headers=headers, timeout=timeout)
                if resp.status_code >= 400:
                    self.cooldown.trip(key, cooldown_on_error)
                    return FetchResult(ok=False, error=f"HTTP {resp.status_code}", status_code=resp.status_code)
                return FetchResult(ok=True, data=resp.json(), status_code=resp.status_code)
            except Exception as exc:  # noqa: BLE001
                self.cooldown.trip(key, cooldown_on_error)
                return FetchResult(ok=False, error=str(exc))

        return self.deduper.run(f"GET:{key}:{url}", work)

    def get_many(self, items: list[tuple[str, str]], *, headers: dict | None = None) -> dict[str, FetchResult]:
        # items: (name, url)
        futs = {
            name: self._executor.submit(self.get_json, url, source_key=name, headers=headers)
            for name, url in items
        }
        return {name: fut.result() for name, fut in futs.items()}
```

- [ ] **Step 4: Run tests to pass**

```bash
uv run pytest tests/free_sources/test_http_resilience.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/free_sources backend/tests/free_sources/test_http_resilience.py
git commit -m "feat(free_sources): add resilient HTTP helper with cooldown and dedupe"
```

---

### Task 2: Approximate chip distribution (local compute, P0)

**Files:**
- Create: `backend/app/services/free_sources/chip_distribution.py`
- Create: `backend/app/services/free_sources/kline_loader.py` (read daily+turnover for a symbol)
- Test: `backend/tests/free_sources/test_chip_distribution.py`

- [ ] **Step 1: Write failing unit tests (synthetic bars)**

```python
# backend/tests/free_sources/test_chip_distribution.py
from app.services.free_sources.chip_distribution import calculate_chip_distribution


def test_chip_distribution_basic_shape():
    bars = [
        {"open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 1000, "amount": 10500, "turnover_rate": 2.0},
        {"open": 10.5, "high": 12, "low": 10.2, "close": 11.5, "volume": 1200, "amount": 13500, "turnover_rate": 3.0},
        {"open": 11.5, "high": 11.8, "low": 11.0, "close": 11.2, "volume": 800, "amount": 9000, "turnover_rate": 1.5},
    ]
    result = calculate_chip_distribution("000001.SZ", bars, bins=40)
    assert result["symbol"] == "000001.SZ"
    assert result["bins"] == 40
    assert result["days"] == 3
    assert abs(sum(i["ratio"] for i in result["items"]) - 1.0) < 1e-6
    assert 0.0 <= result["profit_ratio"] <= 1.0
    assert result["cost70"]["low_price"] <= result["cost70"]["high_price"]
    assert result["avg_cost"] > 0
    assert result["method"] == "approx_turnover_decay_vwap_kernel"
    assert "disclaimer" in result


def test_chip_distribution_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        calculate_chip_distribution("x", [], bins=10)
```

- [ ] **Step 2: Run to fail**

```bash
uv run pytest tests/free_sources/test_chip_distribution.py -v
```

- [ ] **Step 3: Implement Python port of go-stock algorithm**

Port logic from `/Users/simon/Trading/go-stock/backend/data/chip_distribution.go`:
- turnover decay: `remain = 1 - clamp(turnover/100, 0, 0.98)` applied to all bins before adding day volume
- cost center: VWAP `amount/volume` clamped to [low,high], else typical price
- gaussian kernel over bins intersecting [low,high], sigma = max(span*0.18, ...)
- cost70/cost90 concentration ranges
- mark `method` + `disclaimer` that this is approximate, not exchange official chips

Also implement loader:

```python
# kline_loader.py
# Prefer kline_daily_enriched for turnover_rate; fallback kline_daily with turnover_rate=0
# Use polars scan_parquet over data_dir partitions filtered by symbol, last `days` rows ordered by date.
```

Signature:

```python
def calculate_chip_distribution(symbol: str, bars: list[dict], bins: int = 80) -> dict: ...
def chips_for_symbol(data_dir: Path, symbol: str, *, days: int = 120, bins: int = 80) -> dict: ...
```

- [ ] **Step 4: Tests pass**

```bash
uv run pytest tests/free_sources/test_chip_distribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/free_sources/chip_distribution.py backend/app/services/free_sources/kline_loader.py backend/tests/free_sources/test_chip_distribution.py
git commit -m "feat(free_sources): add approximate chip distribution from local daily bars"
```

---

### Task 3: Daily quality gate (P0)

**Files:**
- Create: `backend/app/services/daily_quality.py`
- Test: `backend/tests/free_sources/test_daily_quality.py`
- Modify: `backend/app/jobs/daily_pipeline.py` to call quality after daily sync when enabled (default on, non-fatal)

- [ ] **Step 1: Failing tests**

```python
from pathlib import Path
import polars as pl
from app.services.daily_quality import run_daily_quality_check

def test_quality_flags_negative_volume(tmp_path: Path):
    d = tmp_path / "kline_daily" / "date=2026-07-07"
    d.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ", "000002.SZ"],
        "date": ["2026-07-07", "2026-07-07"],
        "open": [10.0, 6.0],
        "high": [11.0, 6.5],
        "low": [9.5, 5.8],
        "close": [10.5, 6.2],
        "volume": [1000.0, -5.0],
        "amount": [10500.0, 0.0],
    }).write_parquet(d / "part.parquet")
    report = run_daily_quality_check(tmp_path, date="2026-07-07")
    assert report["ok"] is False
    codes = {i["code"] for i in report["issues"]}
    assert "negative_volume" in codes
    assert "zero_amount" in codes
```

Checks to implement for a partition (and optional latest auto-detect):
- negative volume / amount
- null OHLC
- high < low
- amount/volume unit heuristic sample on liquid names (report only)
- row count vs instruments coverage ratio
- write report JSON to `data/user_data/daily_quality_latest.json`

- [ ] **Step 2–4: implement + test + commit**

```bash
git commit -m "feat(data): add daily quality gate for free-api kline partitions"
```

Wire into pipeline non-fatally:
```python
# after sync_daily / compute_enriched success path
try:
    report = run_daily_quality_check(repo.store.data_dir)
    on_progress("quality", ..., f"quality ok={report['ok']} issues={len(report['issues'])}")
except Exception as e:
    logger.warning("quality gate failed: %s", e)
```

---

### Task 4: Fund flow fetchers + ext_data writers (P0)

**Files:**
- Create: `backend/app/services/free_sources/fund_flow.py`
- Test: `backend/tests/free_sources/test_fund_flow.py` (mock HTTP)
- Optional preset helpers under free_sources for config creation

EastMoney endpoints (intelligence only; implement own parser):
- Stock day moneyflow: `https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=0&klt=101&secid={market}.{code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65`
  - market: SH=1, SZ/BJ=0
- Board: `https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bs%3A4`
- Concept: `https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bt%3A3`

Headers: `Referer: https://data.eastmoney.com/` or quote.eastmoney.com

Normalized stock timeseries row:
```python
{
  "symbol": "000001.SZ",
  "date": "2026-07-07",
  "main_net": float,          # 主力净流入
  "small_net": float,
  "med_net": float,
  "large_net": float,
  "super_net": float,
  "main_net_pct": float | None,
  "source": "eastmoney_fflow",
  "unit_amount": "yuan",
}
```

Board/concept snapshot row:
```python
{
  "code": "...",
  "name": "...",
  "main_net": float,
  "change_pct": float | None,
  "rank": int | None,
  "as_of": "YYYY-MM-DD",
  "source": "eastmoney_bkzj",
}
```

Functions:
```python
def fetch_stock_fund_flow(symbol: str, client: ResilientHttpClient | None = None) -> list[dict]: ...
def fetch_board_fund_flow_top(client=None) -> list[dict]: ...
def fetch_concept_fund_flow_top(client=None) -> list[dict]: ...
def persist_stock_fund_flow(data_dir: Path, symbol: str, rows: list[dict]) -> Path: ...
# uses ExtConfig mode=timeseries id=ext_fund_flow_stock OR per-symbol write under timeseries partitions by trade date
def persist_board_snapshot(data_dir, rows) -> None:  # ext_fund_flow_bk snapshot
def persist_concept_snapshot(data_dir, rows) -> None:  # ext_fund_flow_concept snapshot
```

For stock timeseries, prefer writing through existing `ExtConfig` + `write_ext_parquet` with `mode="timeseries"` and `snapshot_date=trade_date` for each date group, or one upsert helper that merges by symbol+date.

Tests: mock `get_json` returning fixture payloads; assert normalized fields and no network.

Commit:
```bash
git commit -m "feat(free_sources): add EastMoney fund flow fetchers and ext_data writers"
```

---

### Task 5: Free ext API router (chips, fund flow, quality) 

**Files:**
- Create: `backend/app/api/free_ext.py`
- Modify: `backend/app/main.py` include router
- Test: `backend/tests/free_sources/test_free_ext_api.py` (TestClient + mocks)

Endpoints:
```
GET  /api/free/chips/{symbol}?days=120&bins=80
POST /api/free/fund-flow/stock/{symbol}/refresh
GET  /api/free/fund-flow/stock/{symbol}?limit=60
POST /api/free/fund-flow/boards/refresh
GET  /api/free/fund-flow/boards?top=20
POST /api/free/fund-flow/concepts/refresh
GET  /api/free/fund-flow/concepts?top=20
GET  /api/free/quality/latest
POST /api/free/quality/run
GET  /api/free/changes?date=  (Task 7)
GET  /api/free/f10/{symbol}   (Task 7)
GET  /api/free/intraday/{symbol} (Task 6)
```

All responses include `source`, `cached`, and for chips `disclaimer`.
Failures return 502/404 with clear message; never raise uncaught.

Commit: `feat(api): expose free chips/fund-flow/quality endpoints`

---

### Task 6: Watchlist quote fallback + on-demand intraday (P1)

**Files:**
- Create: `backend/app/services/free_sources/quote_fallback.py`
- Create: `backend/app/services/free_sources/intraday_public.py`
- Modify: `backend/app/services/quote_service.py` — if TickFlow lacks `quote.by_symbol`, call fallback for watchlist symbols
- Modify: `backend/app/api/intraday.py` or free_ext — public single-symbol minute query

Tencent list quote: `http://qt.gtimg.cn/q=sz000001,sh600000`
Sina: `http://hq.sinajs.cn/list=sz000001,sh600000` with Referer finance.sina.com.cn

Parse into:
```python
{"symbol", "last", "open", "high", "low", "prev_close", "volume", "amount", "change_pct", "source": "tencent"|"sina"}
```

Intraday: `https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sz000001`
Return points list; do **not** write full-market `kline_minute`.

Tests with fixture text bodies.

Commit: `feat(quotes): free watchlist fallback and on-demand public intraday`

---

### Task 7: Stock changes + F10 snapshot on-demand (P1)

**Files:**
- Create: `backend/app/services/free_sources/stock_changes.py`
- Create: `backend/app/services/free_sources/f10_snapshot.py`
- Wire into free_ext API
- Optional short TTL cache under `data/user_data/cache/free/`

Changes: `https://push2ex.eastmoney.com/getAllStockChanges?type=8201&ut=...` (use go-stock known working query params; keep fields documented in code comments)
F10: EastMoney datacenter endpoints used by go-stock `f10_data_api.go` — only a **small summary** subset (PE/PB/MV/industry if available), not full financial statements.

Commit: `feat(free_sources): on-demand stock changes and F10 summary`

---

### Task 8: THS concept/industry pull polish (P0)

**Files:**
- Modify: `backend/app/services/ext_presets.py` and/or `backend/app/api/ext_data.py`
- Ensure manual pull endpoints already exist; add:
  - clear docs in config description
  - `POST /api/free/ths/refresh` that calls existing fetch for `ext_gn_ths` and `ext_hy_ths` without enabling silent startup auto-pull
  - keep `pull.enabled=False` by default (user control)

Test: unit test that refresh helper invokes pull functions (mocked).

Commit: `feat(ext): controlled THS concept/industry refresh helper`

---

### Task 9: Integration polish + verification

- [ ] Run full free_sources test suite
- [ ] Manual smoke (offline-safe where possible):
  - chips for `000001.SZ` against real local data symlink
  - quality on latest partition
  - fund flow with live HTTP only if network allows; otherwise mocks suffice
- [ ] Update `docs/superpowers/reports/2026-07-17-free-ext-data-p0p1-status.md` with done/not-done
- [ ] Ensure no paid TickFlow endpoints introduced
- [ ] Final commit: `docs: free ext data p0/p1 verification report`

---

## Spec Coverage Checklist

| Requirement | Task |
|---|---|
| Approx chips from local daily + turnover | Task 2, 5 |
| Stock fund flow ext | Task 4, 5 |
| Board/concept fund flow | Task 4, 5 |
| Daily quality gate | Task 3, 5 |
| THS pull control | Task 8 |
| Watchlist free quotes | Task 6 |
| On-demand intraday | Task 6 |
| Stock changes | Task 7 |
| F10 summary | Task 7 |
| Resilience timeout/cooldown/partial | Task 1 |
| No paid subscriptions | All tasks (explicit denylist) |

## Out of Scope (reject if implementer adds)

- TickFlow minute full-market sync enabling
- Tushare / BaoStock / easy_tdx production adapters
- Chip race token API
- Vendoring go-stock / finshare / adata packages
