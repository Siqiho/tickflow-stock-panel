"""WeCom webhook is implemented but default-off; invalid URL does not send."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services import webhook_adapter


def test_wecom_url_accepts_key_and_full_url() -> None:
    key = "12345678-1234-1234-1234-1234567890ab"
    assert webhook_adapter.is_valid_wecom_url(key)
    assert webhook_adapter.normalize_wecom_url(key).startswith(webhook_adapter.WECOM_HOOK_PREFIX)
    assert webhook_adapter.is_valid_wecom_url(
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + key
    )


def test_send_wecom_rejects_empty_without_http(monkeypatch) -> None:
    post = MagicMock()
    monkeypatch.setattr("httpx.post", post)
    assert webhook_adapter.send_wecom("", "t", "b") is False
    post.assert_not_called()


def test_send_wecom_posts_only_when_url_valid(monkeypatch) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"errcode": 0}
    post = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.post", post)
    assert webhook_adapter.send_wecom(
        "12345678-1234-1234-1234-1234567890ab",
        "title",
        "body",
    ) is True
    assert post.call_count == 1
    assert "qyapi.weixin.qq.com" in post.call_args.args[0]
