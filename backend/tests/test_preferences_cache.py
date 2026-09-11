"""preferences mtime 缓存测试 — 读盘去重, 且外部修改/自身写入后立即可见。"""
from __future__ import annotations

import json
import os
import threading

import pytest

from app.services import preferences


def _same_size_user_docs() -> tuple[dict, dict, str, str]:
    alice = {"owner": "alice", "pick": "000001.SH"}
    bobby = {"owner": "bobby", "pick": "399001.SZ"}
    alice_text = json.dumps(alice, indent=2, ensure_ascii=False)
    bobby_text = json.dumps(bobby, indent=2, ensure_ascii=False)
    assert len(alice_text.encode("utf-8")) == len(bobby_text.encode("utf-8"))
    return alice, bobby, alice_text, bobby_text


def _force_same_mtime_ns(path_a, path_b, stamp_ns: int = 1_725_000_000_123_456_789) -> None:
    os.utime(path_a, ns=(stamp_ns, stamp_ns))
    os.utime(path_b, ns=(stamp_ns, stamp_ns))
    assert path_a.stat().st_mtime_ns == path_b.stat().st_mtime_ns == stamp_ns
    assert path_a.stat().st_size == path_b.stat().st_size


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    user = tmp_path / "user_preferences.json"
    server = tmp_path / "server_preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: user)
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    preferences._invalidate_cache()
    yield user
    preferences._invalidate_cache()


def _patched_loads(monkeypatch, counter: dict):
    real_loads = json.loads

    def _counting(text):
        counter["loads"] += 1
        return real_loads(text)

    monkeypatch.setattr(preferences.json, "loads", _counting)


def test_second_load_hits_cache_without_disk_parse(_isolated, monkeypatch):
    _isolated.write_text(json.dumps({"realtime_quotes_enabled": True}), encoding="utf-8")
    counter = {"loads": 0}
    _patched_loads(monkeypatch, counter)

    assert preferences.load()["realtime_quotes_enabled"] is True
    assert preferences.load()["realtime_quotes_enabled"] is True
    assert counter["loads"] == 1, "签名未变时第二次 load 不得重复读盘+parse"


def test_external_file_change_invalidates_cache(_isolated, monkeypatch):
    _isolated.write_text(json.dumps({"realtime_quote_interval": 6.0}), encoding="utf-8")
    assert preferences.load()["realtime_quote_interval"] == 6.0

    _isolated.write_text(json.dumps({"realtime_quote_interval": 3.0}), encoding="utf-8")
    # 同尺寸修改且 mtime 粒度可能不变时, 显式推进 mtime 模拟真实场景
    st = _isolated.stat()
    os.utime(_isolated, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    assert preferences.load()["realtime_quote_interval"] == 3.0


def test_save_then_load_sees_merged_values(_isolated):
    _isolated.write_text(json.dumps({"a": 1}), encoding="utf-8")
    out = preferences.save({"b": 2})
    assert out == {"a": 1, "b": 2}
    assert preferences.load() == {"a": 1, "b": 2}


def test_interval_setter_invalidates_cache(_isolated):
    # 行情间隔写 server prefs, 与用户文件分轨; getter 必须读 server。
    preferences.set_realtime_quote_interval(2.0)
    assert preferences.get_realtime_quote_interval() == 2.0
    assert "realtime_quote_interval" not in preferences.load()


def test_load_returns_copy_not_cached_object(_isolated):
    _isolated.write_text(json.dumps({"k": [1, 2]}), encoding="utf-8")
    first = preferences.load()
    first["k"].append(3)
    first["extra"] = True
    again = preferences.load()
    assert again == {"k": [1, 2]}


def test_mining_schedule_defaults_are_disabled(_isolated):
    assert preferences.get_mining_schedule() == {
        "mining_schedule_enabled": False,
        "mining_schedule_weekday": 4,
        "mining_budget_profile": "balanced",
    }


def test_mining_schedule_invalid_stored_values_fail_closed(_isolated):
    preferences._server_path().write_text(
        json.dumps(
            {
                "mining_schedule_enabled": "false",
                "mining_schedule_weekday": True,
                "mining_budget_profile": None,
            }
        ),
        encoding="utf-8",
    )

    assert preferences.get_mining_schedule() == {
        "mining_schedule_enabled": False,
        "mining_schedule_weekday": 4,
        "mining_budget_profile": "balanced",
    }


def test_mining_schedule_setter_saves_group_once(monkeypatch):
    calls = []
    monkeypatch.setattr(preferences, "save_server", lambda updates: calls.append(updates) or updates)

    result = preferences.set_mining_schedule(True, 2, "strict")

    assert result == {
        "mining_schedule_enabled": True,
        "mining_schedule_weekday": 2,
        "mining_budget_profile": "strict",
    }
    assert calls == [result]


@pytest.mark.parametrize("weekday", [-1, 5, True])
def test_mining_schedule_setter_rejects_invalid_weekday(weekday):
    with pytest.raises(ValueError, match="weekday"):
        preferences.set_mining_schedule(True, weekday, "balanced")


def test_mining_schedule_setter_rejects_invalid_profile():
    with pytest.raises(ValueError, match="profile"):
        preferences.set_mining_schedule(True, 4, "exploratory")


def test_external_push_channel_whitelists_include_custom_and_email(_isolated):
    assert preferences.set_webhook_default_channels([
        "custom", "email", "custom", "unsupported",
    ]) == ["custom", "email"]
    assert preferences.set_review_push_channels([
        "email", "wecom", "unsupported",
    ]) == ["email", "wecom"]


def test_email_smtp_config_falls_back_from_malformed_stored_values(_isolated):
    preferences.save({
        "email_smtp_config": {
            "host": " smtp.example.com ",
            "port": "invalid",
            "security": "invalid",
            "to_addresses": "alerts@example.com",
        },
    })

    assert preferences.get_email_smtp_config() == {
        "host": "smtp.example.com",
        "port": 465,
        "security": "ssl",
        "username": "",
        "from_address": "",
        "to_addresses": [],
    }
    assert "email_smtp_config" not in preferences.load_server()


def test_non_admin_cannot_change_server_preferences(_isolated, monkeypatch):
    server = preferences._server_path()
    server.write_text(json.dumps({"realtime_quote_interval": 15.0}), encoding="utf-8")
    monkeypatch.setattr("app.services.user_context.is_admin", lambda: False)
    with pytest.raises(PermissionError, match="administrator"):
        preferences.save_server({"realtime_quote_interval": 1.0})
    assert json.loads(server.read_text(encoding="utf-8"))["realtime_quote_interval"] == 15.0
    preferences.save({"review_push_mode": "manual"})
    assert preferences.load()["review_push_mode"] == "manual"
    assert "review_push_mode" not in preferences.load_server()


def test_sidebar_index_is_user_scoped_and_not_pipeline_alias(_isolated):
    assert preferences.get_sidebar_index_symbols() == preferences.SIDEBAR_INDEX_SYMBOLS_DEFAULT
    saved = preferences.set_sidebar_index_symbols(["000001.SH", "399006.SZ", "999999.SH"])
    assert saved == ["000001.SH", "399006.SZ"]
    assert preferences.load()["sidebar_index_symbols"] == ["000001.SH", "399006.SZ"]
    assert "sidebar_index_symbols" not in preferences.load_server()
    assert preferences.get_pipeline_index_symbols() == ""
    preferences.set_pipeline_index_symbols("000300.SH")
    assert preferences.get_pipeline_index_symbols() == "000300.SH"
    assert preferences.get_sidebar_index_symbols() == ["000001.SH", "399006.SZ"]
    assert preferences.load_server().get("pipeline_index_symbols") == "000300.SH"


def test_user_save_does_not_alias_server_file(_isolated):
    preferences.set_webhook_default_channels([])
    preferences.save({"email_smtp_config": {"host": "smtp.example.com", "port": 465}})
    assert preferences._path() != preferences._server_path()
    assert preferences._path().exists()
    assert not preferences._server_path().exists()
    assert preferences.get_webhook_default_channels() == []


def test_same_mtime_ns_same_size_two_files_do_not_cross_read(_isolated, tmp_path, monkeypatch):
    alice_doc, bobby_doc, alice_text, bobby_text = _same_size_user_docs()
    alice_path = tmp_path / "alice.json"
    bobby_path = tmp_path / "bobby.json"
    alice_path.write_text(alice_text, encoding="utf-8")
    bobby_path.write_text(bobby_text, encoding="utf-8")
    _force_same_mtime_ns(alice_path, bobby_path)

    current = {"path": alice_path}
    monkeypatch.setattr(preferences, "_path", lambda: current["path"])
    preferences._invalidate_cache()

    assert preferences.load() == alice_doc
    current["path"] = bobby_path
    assert preferences.load() == bobby_doc
    current["path"] = alice_path
    assert preferences.load() == alice_doc

    mutated = preferences.load()
    mutated["owner"] = "mutated"
    mutated["extra"] = True
    current["path"] = bobby_path
    assert preferences.load() == bobby_doc
    current["path"] = alice_path
    assert preferences.load() == alice_doc

    preferences.save({"n": 1})
    current["path"] = bobby_path
    after_bob = preferences.load()
    assert after_bob == bobby_doc
    assert "n" not in after_bob
    current["path"] = alice_path
    after_alice = preferences.load()
    assert after_alice["owner"] == "alice"
    assert after_alice["n"] == 1
    assert json.loads(bobby_path.read_text(encoding="utf-8")) == bobby_doc


def test_data_dir_change_is_part_of_cache_signature(_isolated, tmp_path, monkeypatch):
    alice_doc, bobby_doc, alice_text, bobby_text = _same_size_user_docs()
    dir_a = tmp_path / "data-a" / "user_data"
    dir_b = tmp_path / "data-b" / "user_data"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)
    path_a = dir_a / "preferences.json"
    path_b = dir_b / "preferences.json"
    path_a.write_text(alice_text, encoding="utf-8")
    path_b.write_text(bobby_text, encoding="utf-8")
    _force_same_mtime_ns(path_a, path_b)

    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data-a")

    def _real_path() -> object:
        from app.services.user_context import user_path
        p = user_path("preferences.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(preferences, "_path", _real_path)
    preferences._invalidate_cache()
    assert preferences.load() == alice_doc

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data-b")
    assert preferences.load() == bobby_doc
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data-a")
    assert preferences.load() == alice_doc


def test_concurrent_two_user_load_save_same_mtime_does_not_leak(_isolated, tmp_path, monkeypatch):
    alice_doc, bobby_doc, alice_text, bobby_text = _same_size_user_docs()
    alice_path = tmp_path / "alice.json"
    bobby_path = tmp_path / "bobby.json"
    alice_path.write_text(alice_text, encoding="utf-8")
    bobby_path.write_text(bobby_text, encoding="utf-8")
    _force_same_mtime_ns(alice_path, bobby_path)

    tls = threading.local()
    monkeypatch.setattr(preferences, "_path", lambda: tls.path)
    preferences._invalidate_cache()

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def _worker(path, owner: str, pick: str) -> None:
        tls.path = path
        try:
            barrier.wait()
            for i in range(30):
                data = preferences.load()
                if data["owner"] != owner or data["pick"] != pick:
                    errors.append(f"{owner} load leaked: {data}")
                    return
                data["local"] = i
                saved = preferences.save({"n": i})
                if saved["owner"] != owner:
                    errors.append(f"{owner} save leaked: {saved}")
                    return
                again = preferences.load()
                if again["owner"] != owner or again.get("n") != i:
                    errors.append(f"{owner} reload leaked: {again}")
                    return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{owner} {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=_worker, args=(alice_path, "alice", "000001.SH"))
    t2 = threading.Thread(target=_worker, args=(bobby_path, "bobby", "399001.SZ"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == []
    assert json.loads(alice_path.read_text(encoding="utf-8"))["owner"] == "alice"
    assert json.loads(bobby_path.read_text(encoding="utf-8"))["owner"] == "bobby"
