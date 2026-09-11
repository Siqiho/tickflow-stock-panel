"""回归测试: 本轮修复的几处高风险行为(并发单飞 / 重任务槽 / sector fail-closed)。

均为纯逻辑, 不触网, 不依赖真实数据源。
"""
from __future__ import annotations

import polars as pl

from app.jobs import daily_pipeline
from app.services import pipeline_jobs, quote_service
from app.services.pipeline_jobs import JobStore
from app.services.quote_service import QuoteService
from app.strategy import monitor_rules
from app.strategy.monitor import MonitorRuleEngine, SectorScopeError, apply_monitor_scope

# ── JobStore 单飞 ────────────────────────────────────────────────────────

def test_create_returns_id_and_reuses_running(tmp_path):
    """create 返回 id 字符串, pending/running 窗口复用同一有效工作。"""
    store = JobStore(store_dir=tmp_path / "jobs")
    jid1 = store.create(timeout_s=60)
    assert isinstance(jid1, str) and jid1
    assert jid1.is_new is True
    store.start(jid1)
    jid2 = store.create(timeout_s=60)
    assert jid2 == jid1
    assert jid2.is_new is False


def test_create_pending_singleflight_same_identity(tmp_path):
    """同一有效工作在 pending 窗口并发/重复 create 只能得到一个 job。"""
    store = JobStore(store_dir=tmp_path / "jobs")
    first = store.create(timeout_s=60)
    second = store.create(timeout_s=60)
    assert str(first) == str(second)
    assert first.is_new is True
    assert second.is_new is False


def test_create_new_after_terminal(tmp_path):
    """终态以后新请求可以创建新任务。long_running 兼容接入。"""
    store = JobStore(store_dir=tmp_path / "jobs")
    jid1, is_new = store.create(timeout_s=60, long_running=True)
    assert is_new is True
    store.start(jid1)
    store.succeed(jid1, {"ok": True})
    jid2, is_new2 = store.create(timeout_s=60, long_running=True)
    assert is_new2 is True
    assert jid2 != jid1


def test_run_slot_is_exclusive():
    """重任务执行槽同一时刻只允许一个持有者; 异常后必须释放可重试。"""
    pipeline_jobs.release_run_slot()
    assert pipeline_jobs.try_acquire_run_slot("job-a") is True
    try:
        assert pipeline_jobs.try_acquire_run_slot("job-b") is False
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pipeline_jobs.release_run_slot("job-a")
        assert pipeline_jobs.try_acquire_run_slot("job-c") is True
    finally:
        pipeline_jobs.release_run_slot()
    pipeline_jobs.release_run_slot()


# ── 监控 sector fail-closed ──────────────────────────────────────────────

def _base_price_rule(scope: str) -> dict:
    return {
        "id": "r_test",
        "name": "t",
        "type": "price",
        "conditions": [{"field": "close", "op": ">", "value": 10}],
        "logic": "and",
        "scope": scope,
    }


def test_validate_rejects_sector_without_identifier():
    """sector 仍是合法 scope, 但没有板块标识时必须明确失败, 不能当全市场。"""
    try:
        monitor_rules.validate(_base_price_rule("sector"))
    except ValueError as exc:
        assert "sector" in str(exc)
    else:
        raise AssertionError("bare scope=sector must fail validation")


def test_validate_accepts_sector_with_identifier():
    rule = _base_price_rule("sector")
    rule["sector"] = "银行"
    monitor_rules.validate(rule)


def test_validate_accepts_symbols_scope():
    rule = _base_price_rule("symbols")
    rule["symbols"] = ["600000.SH"]
    monitor_rules.validate(rule)  # 不应抛


def test_apply_scope_sector_filters_members_not_full_market():
    """有行业列时只返回成员; 等于全量不得算成功。"""
    df = pl.DataFrame({
        "symbol": ["600000.SH", "000001.SZ", "600519.SH"],
        "industry": ["银行", "银行", "白酒"],
        "close": [12.0, 15.0, 1600.0],
    })
    out = apply_monitor_scope(df, {"id": "r_bank", "scope": "sector", "sector": "银行"})
    assert out.height == 2
    assert out.height != df.height
    assert set(out["symbol"].to_list()) == {"600000.SH", "000001.SZ"}

    assert apply_monitor_scope(df, {"scope": "all"}).height == 3
    picked = apply_monitor_scope(df, {"scope": "symbols", "symbols": ["600000.SH"]})
    assert picked.height == 1


def test_apply_scope_sector_without_identifier_raises():
    df = pl.DataFrame({"symbol": ["600000.SH", "000001.SZ"], "close": [10.0, 20.0]})
    try:
        apply_monitor_scope(df, {"id": "r_old", "scope": "sector"})
    except SectorScopeError:
        pass
    else:
        raise AssertionError("bare scope=sector must raise, not return full market")


def test_apply_scope_sector_without_members_raises():
    df = pl.DataFrame({"symbol": ["600000.SH", "000001.SZ"], "close": [10.0, 20.0]})
    try:
        apply_monitor_scope(df, {"id": "r_bank", "scope": "sector", "sector": "银行"})
    except SectorScopeError:
        pass
    else:
        raise AssertionError("sector without member mapping must raise")


def test_evaluate_sector_without_identifier_writes_no_alerts():
    """缺板块信息时不评估、不写告警, 即使条件能打中全市场。"""
    alerts: list[dict] = []
    engine = MonitorRuleEngine(alert_handler=alerts.append)
    engine.set_rules([{
        "id": "r_sector_placeholder",
        "name": "t",
        "type": "price",
        "enabled": True,
        "conditions": [{"field": "close", "op": ">", "value": 1}],
        "logic": "and",
        "scope": "sector",
        "cooldown_seconds": 0,
        "severity": "info",
        "message": "should-not-fire",
    }])
    df = pl.DataFrame({
        "symbol": ["600000.SH", "000001.SZ"],
        "name": ["浦发", "平安"],
        "close": [12.0, 15.0],
        "change_pct": [0.01, 0.02],
    })
    events = engine.evaluate(df)
    assert events == []
    assert alerts == []


def test_ladder_webhook_uses_chinese_title_without_brand(monkeypatch):
    calls = []

    class CaptureExecutor:
        def submit(self, fn, *args):
            calls.append((fn, args))

    monkeypatch.setattr(quote_service, "_WEBHOOK_EXECUTOR", CaptureExecutor())
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "https://open.feishu.cn/open-apis/bot/v2/hook/test")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "secret")
    monkeypatch.setattr("app.services.preferences.get_wecom_webhook_url", lambda: "wecom-key")
    monkeypatch.setattr("app.services.preferences.get_custom_webhook_url", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_email_smtp_config", lambda: {})
    monkeypatch.setattr("app.secrets_store.get_custom_webhook_secret", lambda: "")
    monkeypatch.setattr("app.secrets_store.get_email_smtp_password", lambda: "")

    engine = type("Engine", (), {
        "rules": {"r_ladder": {"webhook_channels": ["feishu", "wecom"]}},
    })()
    QuoteService._maybe_send_webhook(
        object.__new__(QuoteService),
        [{
            "rule_id": "r_ladder",
            "source": "ladder",
            "symbol": "600000.SH",
            "name": "浦发银行",
            "message": "炸板预警",
        }],
        engine,
    )

    assert [args[1] for _, args in calls] == ["连板梯队", "连板梯队"]
    assert all("TickFlow" not in args[1] for _, args in calls)


def test_ladder_dispatches_custom_webhook_and_email(monkeypatch):
    calls = []

    class CaptureExecutor:
        def submit(self, fn, *args):
            calls.append((fn.__name__, args))

    email_config = {
        "host": "smtp.example.com",
        "username": "bot@example.com",
        "from_address": "bot@example.com",
        "to_addresses": ["alerts@example.com"],
    }
    monkeypatch.setattr(quote_service, "_WEBHOOK_EXECUTOR", CaptureExecutor())
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_wecom_webhook_url", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_custom_webhook_url", lambda: "https://example.com/hook")
    monkeypatch.setattr("app.services.preferences.get_email_smtp_config", lambda: email_config)
    monkeypatch.setattr("app.secrets_store.get_custom_webhook_secret", lambda: "hook-secret")
    monkeypatch.setattr("app.secrets_store.get_email_smtp_password", lambda: "smtp-password")

    engine = type("Engine", (), {
        "rules": {"r_ladder": {"webhook_channels": ["custom", "email"]}},
    })()
    event = {
        "rule_id": "r_ladder",
        "source": "ladder",
        "symbol": "600000.SH",
        "name": "浦发银行",
        "message": "炸板预警",
    }
    QuoteService._maybe_send_webhook(object.__new__(QuoteService), [event], engine)

    assert [name for name, _ in calls] == ["send_custom", "send_email"]
    assert calls[0][1][3:] == ("monitor_alert", event, "hook-secret")
    assert calls[1][1][:2] == (email_config, "smtp-password")


def test_review_webhooks_use_title_without_brand(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.preferences.get_review_push_channels", lambda: ["feishu", "wecom"])
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "feishu-url")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "secret")
    monkeypatch.setattr("app.services.preferences.get_wecom_webhook_url", lambda: "wecom-url")
    monkeypatch.setattr(
        "app.services.webhook_adapter.send_feishu_card",
        lambda *args: calls.append(("feishu", args)) or True,
    )
    monkeypatch.setattr(
        "app.services.webhook_adapter.send_wecom_markdown",
        lambda *args: calls.append(("wecom", args)) or True,
    )

    daily_pipeline._maybe_push_review("复盘正文", {"as_of": "2026-07-18"})

    assert [args[1] for _, args in calls] == ["每日复盘", "每日复盘"]
    assert all("TickFlow" not in args[1] for _, args in calls)


def test_review_pushes_custom_webhook_and_email(monkeypatch):
    calls = []
    email_config = {
        "host": "smtp.example.com",
        "username": "bot@example.com",
        "from_address": "bot@example.com",
        "to_addresses": ["alerts@example.com"],
    }
    monkeypatch.setattr("app.services.preferences.get_review_push_channels", lambda: ["custom", "email"])
    monkeypatch.setattr("app.services.preferences.get_custom_webhook_url", lambda: "https://example.com/hook")
    monkeypatch.setattr("app.services.preferences.get_email_smtp_config", lambda: email_config)
    monkeypatch.setattr("app.secrets_store.get_custom_webhook_secret", lambda: "hook-secret")
    monkeypatch.setattr("app.secrets_store.get_email_smtp_password", lambda: "smtp-password")
    monkeypatch.setattr(
        "app.services.webhook_adapter.send_custom",
        lambda *args: calls.append(("custom", args)) or True,
    )
    monkeypatch.setattr(
        "app.services.email_adapter.send_email",
        lambda *args: calls.append(("email", args)) or True,
    )

    daily_pipeline._maybe_push_review("复盘正文", {"as_of": "2026-07-18"})

    assert [channel for channel, _ in calls] == ["custom", "email"]
    assert calls[0][1][3] == "market_review"
    assert calls[1][1][2] == "每日复盘"
