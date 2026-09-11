"""本阶段 settings 压缩 / review-push mode / webhook-test 未配置路径。

只校验接口与 payload, 不发送真实通知或邮件。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import regime, settings
from app.services import preferences


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    yield path
    preferences._invalidate_cache()


def test_compress_put_updates_detail_and_batch_flags() -> None:
    minute = settings.update_minute_batch_compress(
        settings.MinuteBatchCompressPrefs(minute_batch_compress=False)
    )
    daily = settings.update_daily_batch_compress(
        settings.DailyBatchCompressPrefs(daily_batch_compress=False)
    )
    assert minute == {"minute_batch_compress": False}
    assert daily == {"daily_batch_compress": False}
    assert preferences.get_minute_batch_compress() is False
    assert preferences.get_daily_batch_compress() is False


def test_review_push_put_saves_mode_and_keeps_existing_channels() -> None:
    result = settings.update_review_push(
        settings.ReviewPushIn(channels=["feishu"], mode="auto")
    )
    assert result == {"review_push_channels": ["feishu"], "review_push_mode": "auto"}
    unchanged = settings.update_review_push(
        settings.ReviewPushIn(channels=["feishu"], mode=None)
    )
    assert unchanged["review_push_mode"] == "auto"


def test_webhook_test_unconfigured_channels_do_not_send(monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr("app.services.webhook_adapter.send_feishu", lambda *a, **k: sent.append("feishu") or True)
    monkeypatch.setattr("app.services.webhook_adapter.send_wecom", lambda *a, **k: sent.append("wecom") or True)
    monkeypatch.setattr("app.services.webhook_adapter.send_custom", lambda *a, **k: sent.append("custom") or True)
    monkeypatch.setattr("app.services.email_adapter.send_email", lambda *a, **k: sent.append("email") or True)

    for channel in ("feishu", "wecom", "custom", "email"):
        out = settings.test_webhook(settings.WebhookTestIn(channel=channel))
        assert out["ok"] is False
        assert "尚未" in out["detail"] or "配置" in out["detail"]
    assert sent == []


def test_regime_recompute_rejects_non_admin(monkeypatch) -> None:
    monkeypatch.setattr("app.services.user_context.is_admin", lambda: False)

    class DummyRequest:
        app = type("App", (), {"state": type("State", (), {"repo": None})()})()

    with pytest.raises(HTTPException) as exc:
        regime.regime_recompute(DummyRequest())
    assert exc.value.status_code == 403
    assert "管理员" in str(exc.value.detail)


def test_regime_recompute_admin_executes_builder(monkeypatch, tmp_path) -> None:
    """管理员补算必须走到 regime_builder, 不能只停在权限判断。"""
    import polars as pl
    from datetime import date

    from app.services import market_mainline, regime_builder

    monkeypatch.setattr("app.services.user_context.is_admin", lambda: True)
    computed = {"batch": 0, "upsert": 0, "phase": 0, "mainline": 0}

    def _batch(repo, start, end):
        computed["batch"] += 1
        assert start == date(2026, 8, 4)
        return pl.DataFrame({"date": [date(2026, 8, 4)], "state": ["neutral"], "score": [50]})

    monkeypatch.setattr(regime_builder, "run_regime_batch", _batch)
    monkeypatch.setattr(
        regime_builder,
        "upsert_regime_history",
        lambda data_dir, rows: computed.__setitem__("upsert", computed["upsert"] + rows.height),
    )
    monkeypatch.setattr(regime_builder, "refresh_phase_labels", lambda data_dir: computed.__setitem__("phase", 1) or 1)
    monkeypatch.setattr(
        market_mainline,
        "compute_mainline_range",
        lambda *a, **k: computed.__setitem__("mainline", computed["mainline"] + 1) or pl.DataFrame(),
    )
    monkeypatch.setattr(market_mainline, "upsert_mainline_history", lambda *a, **k: None)

    class DummyRequest:
        app = type("App", (), {"state": type("State", (), {"repo": object()})()})()

    monkeypatch.setattr(regime, "_data_dir", lambda request: tmp_path)
    out = regime.regime_recompute(DummyRequest(), start=date(2026, 8, 4), end=date(2026, 8, 4))
    assert out["ok"] is True
    assert out["computed"] == 1
    assert computed["batch"] == 1
    assert computed["upsert"] == 1
    assert computed["phase"] == 1
    assert computed["mainline"] == 2
