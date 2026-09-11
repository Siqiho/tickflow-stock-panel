"""能力路由矩阵契约测试。

覆盖: 注册表与路由偏好字段一一对应、候选按各源 datasets 声明过滤、
候选只含当前可用源 (未就绪插件进 pending 并携带原因)、TickFlow 候选
按当前订阅档位过滤、偏好指向 tickflow 但档位不足时的 tf_available
标记、usable 跟随生效源 (各页能力门控的统一判定)、每能力独立路由
(「跟随日K」特殊值已下线, 存量旧值由 preferences getter 自愈回退)、
偏好指向未知源时的回退形态。全部用假插件/自定义源,
不依赖真实网络与本地 data/ 目录。
"""
from __future__ import annotations

from app.data_providers import custom as custom_sources
from app.data_providers.capabilities import CAPABILITY_REGISTRY, build_capability_matrix

DEFAULT_CURRENT = {
    "daily_data_provider": "tickflow",
    "adj_factor_provider": "tickflow",
    "minute_data_provider": "tickflow",
    "full_minute_data_provider": "tickflow",
    "depth5_data_provider": "tickflow",
    "realtime_data_provider": "tickflow",
    "financial_data_provider": "tickflow",
}


def _fake_sources(monkeypatch, plugins: list[dict], customs: list[dict] | None = None) -> None:
    monkeypatch.setattr(custom_sources, "list_plugins", lambda: plugins)
    monkeypatch.setattr(custom_sources, "list_sources", lambda: customs or [])


def _by_id(matrix: dict) -> dict[str, dict]:
    return {c["id"]: c for c in matrix["capabilities"]}


def test_registry_covers_all_routing_fields():
    """注册表是能力的单一权威: 可路由能力与偏好键一一对应、无重复。"""
    routable = [c["field"] for c in CAPABILITY_REGISTRY if c["field"] is not None]
    assert sorted(routable) == sorted(DEFAULT_CURRENT)
    assert len(set(routable)) == len(routable)
    assert {c["id"] for c in CAPABILITY_REGISTRY} == {
        "realtime", "daily", "minute", "full_minute", "depth5", "adj_factor", "financial",
    }
    full_minute = next(c for c in CAPABILITY_REGISTRY if c["id"] == "full_minute")
    assert full_minute["field"] == "full_minute_data_provider"
    assert full_minute["tf_tier"] == "expert"
    for cap in CAPABILITY_REGISTRY:
        expected_default = "public" if cap["id"] == "realtime" else "tickflow"
        assert cap["default"] == expected_default
        assert cap["tf_tier"] in ("none", "starter", "pro", "expert")
        assert "follow" not in cap


def test_matrix_without_third_party_sources(monkeypatch):
    """无插件无自定义源: 每个能力只剩 TickFlow 候选, 默认路由全部生效。"""
    _fake_sources(monkeypatch, [])
    matrix = build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="expert")
    assert matrix["tickflow_tier"] == "expert"
    assert len(matrix["capabilities"]) == 7
    for cap in matrix["capabilities"]:
        names = [c["name"] for c in cap["candidates"]]
        if cap["id"] in {"adj_factor", "realtime", "financial"}:
            assert names == ["tickflow", "public"]
        else:
            assert names == ["tickflow"]
        assert cap["candidates"][0]["kind"] == "builtin"
        assert cap["tf_available"] is True
        assert cap["usable"] is True
        assert cap["pending"] == []
        assert cap["current"] == cap["effective"] == "tickflow"


def test_candidates_only_available_unready_goes_pending(monkeypatch):
    """候选只包含声明了该能力且可用的源; 未就绪插件进 pending 并携带原因。"""
    _fake_sources(
        monkeypatch,
        [
            {"name": "fuyao", "display_name": "fuyao", "datasets": ["realtime"],
             "available": True, "status": "ok"},
            {"name": "sdk", "display_name": "SDK", "datasets": ["daily", "minute"],
             "available": False, "status": "依赖未安装"},
        ],
        [{"name": "myhttp", "display_name": "MyHTTP", "datasets": ["financial", "realtime"]}],
    )
    caps = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="expert"))
    assert [c["name"] for c in caps["realtime"]["candidates"]] == ["tickflow", "public", "fuyao", "myhttp"]
    assert [c["name"] for c in caps["daily"]["candidates"]] == ["tickflow"]
    assert [c["name"] for c in caps["daily"]["pending"]] == ["sdk"]
    assert caps["daily"]["pending"][0]["available"] is False
    assert caps["daily"]["pending"][0]["note"] == "依赖未安装"
    assert [c["name"] for c in caps["financial"]["candidates"]] == ["tickflow", "public", "myhttp"]
    assert caps["financial"]["candidates"][2]["kind"] == "custom"
    assert [c["name"] for c in caps["adj_factor"]["candidates"]] == ["tickflow", "public"]


def test_tickflow_candidates_filtered_by_tier(monkeypatch):
    """TickFlow 只出现在当前档位确实提供的能力候选里 (free: 仅日K)。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="free"))
    assert caps["daily"]["tf_available"] is True
    assert [c["name"] for c in caps["daily"]["candidates"]] == ["tickflow"]
    for cap_id in ("realtime", "minute", "depth5", "adj_factor", "financial"):
        assert caps[cap_id]["tf_available"] is False
    assert [c["name"] for c in caps["minute"]["candidates"]] == []
    assert [c["name"] for c in caps["depth5"]["candidates"]] == []
    for cap_id in ("realtime", "adj_factor", "financial"):
        assert [c["name"] for c in caps[cap_id]["candidates"]] == ["public"]
    # starter 解锁实时与除权, 分钟/五档/财务仍锁
    caps = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="starter"))
    assert caps["realtime"]["tf_available"] is True
    assert caps["adj_factor"]["tf_available"] is True
    assert caps["minute"]["tf_available"] is False
    assert caps["depth5"]["tf_available"] is False
    assert caps["financial"]["tf_available"] is False


def test_current_tickflow_unmet_tier_flagged(monkeypatch):
    """偏好仍指向 tickflow 但档位不足: current 不动, tf_available=False 供前端警示。"""
    _fake_sources(monkeypatch, [])
    cap = _by_id(
        build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="free"),
    )["realtime"]
    assert cap["current"] == cap["effective"] == "tickflow"
    assert cap["tf_available"] is False
    assert cap["usable"] is False
    assert [c["name"] for c in cap["candidates"]] == ["public"]


def test_usable_follows_effective_provider(monkeypatch):
    """usable 跟随生效源而非 TickFlow 套餐: 各页能力门控的统一判定。

    - 生效源是可用插件 → usable (即使 TickFlow 档位不足);
    - 生效源是未就绪插件 → 不可用 (即使有其他可用候选);
    - 除权独立路由, 档位门槛/插件可用性同样生效。
    """
    _fake_sources(
        monkeypatch,
        [
            {"name": "fuyao", "display_name": "fuyao", "datasets": ["realtime", "minute"],
             "available": True, "status": "ok"},
            {"name": "sdk", "display_name": "SDK", "datasets": ["daily", "adj_factor", "minute"],
             "available": False, "status": "依赖未安装"},
        ],
    )
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, realtime_data_provider="fuyao", minute_data_provider="sdk"),
            tickflow_tier="free",
        ),
    )
    # 路由到可用插件: TickFlow 档位不足不影响 usable
    assert caps["realtime"]["tf_available"] is False
    assert caps["realtime"]["usable"] is True
    # 路由到未就绪插件: 有可用候选 (fuyao) 也不算 usable
    minute = caps["minute"]
    assert [c["name"] for c in minute["candidates"]] == ["fuyao"]
    assert minute["usable"] is False
    # 除权默认路由 tickflow: 自身档位门槛 (starter+) 生效, free 档不可用
    # (独立路由, 不再随日K联动)
    assert caps["adj_factor"]["effective"] == "tickflow"
    assert caps["adj_factor"]["tf_available"] is False
    assert caps["adj_factor"]["usable"] is False
    # 除权显式路由到未就绪 sdk → 不可用 (有 tickflow 候选也不算, 日K不受影响)
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, adj_factor_provider="sdk"), tickflow_tier="expert",
        ),
    )
    assert [c["name"] for c in caps["adj_factor"]["candidates"]] == ["tickflow", "public"]
    assert caps["adj_factor"]["effective"] == "sdk"
    assert caps["adj_factor"]["usable"] is False
    assert caps["daily"]["usable"] is True


def test_unknown_or_empty_tier_fails_closed(monkeypatch):
    """未知档 (探测缺失) 与空档按 none 处理: 仅全档位能力 (日K) 保留 TickFlow。"""
    _fake_sources(monkeypatch, [])
    for tier in ("", "unknown", None):
        matrix = build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier=tier)
        caps = _by_id(matrix)
        assert [c["name"] for c in caps["daily"]["candidates"]] == ["tickflow"]
        assert caps["realtime"]["tf_available"] is False
        assert [c["name"] for c in caps["realtime"]["candidates"]] == ["public"]
        assert caps["minute"]["tf_available"] is False
        assert caps["minute"]["candidates"] == []


def test_adj_factor_routes_independently(monkeypatch):
    """除权独立路由: 显式切到声明除权的插件即生效, 与日K当前源无关。

    存量 same_as_daily 只做状态解析, 见 test_same_as_daily_status_follows_daily。
    """
    _fake_sources(
        monkeypatch,
        [{"name": "sdk", "display_name": "SDK", "datasets": ["adj_factor"],
          "available": True, "status": "ok"}],
    )
    # 日K走 tickflow, 除权显式走 sdk → 互不影响 (TickFlow none 档下插件照常可用)
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, adj_factor_provider="sdk"), tickflow_tier="none",
        ),
    )
    adj = caps["adj_factor"]
    assert adj["current"] == adj["effective"] == "sdk"
    assert adj["usable"] is True
    assert caps["daily"]["effective"] == "tickflow"
    assert caps["daily"]["usable"] is True


def test_depth5_capability_semantics(monkeypatch):
    """五档可独立路由到声明 depth5 的插件, 不受 TickFlow 档位限制。"""
    _fake_sources(
        monkeypatch,
        [{"name": "depth_src", "display_name": "Depth", "datasets": ["depth5"],
          "available": True, "status": "ok"}],
    )
    # pro 档: TickFlow 进候选, 默认路由 tickflow → usable
    cap = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="pro"))["depth5"]
    assert cap["tf_available"] is True
    assert [c["name"] for c in cap["candidates"]] == ["tickflow", "depth_src"]
    assert cap["usable"] is True
    # starter 档: TickFlow 不可供, 但显式路由到插件后仍可用
    current = dict(DEFAULT_CURRENT, depth5_data_provider="depth_src")
    cap = _by_id(build_capability_matrix(current, tickflow_tier="starter"))["depth5"]
    assert cap["tf_available"] is False
    assert [c["name"] for c in cap["candidates"]] == ["depth_src"]
    assert cap["effective"] == "depth_src"
    assert cap["usable"] is True


def test_unknown_current_display_falls_back_to_name(monkeypatch):
    """偏好指向未注册源 (正常经 getters 校验不会发生): 展示回退为原始名, 不抛异常。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, realtime_data_provider="ghost"), tickflow_tier="expert",
        ),
    )
    assert caps["realtime"]["current"] == "ghost"
    assert caps["realtime"]["current_display"] == "ghost"
    assert caps["realtime"]["effective_display"] == "ghost"


def test_full_minute_routes_like_other_capabilities(monkeypatch):
    """全量分钟与取数路径一致: 偏好 full_minute_data_provider 决定生效源。

    TickFlow 仍仅 Expert 进候选; 自定义源声明 full_minute 后可被路由。
    """
    _fake_sources(
        monkeypatch,
        [],
        [{"name": "myfm", "display_name": "MyFM", "datasets": ["full_minute"]}],
    )
    caps = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="expert"))
    fm = caps["full_minute"]
    assert fm["field"] == "full_minute_data_provider"
    assert [c["name"] for c in fm["candidates"]] == ["tickflow", "myfm"]
    assert fm["usable"] is True
    assert fm["tf_available"] is True
    assert fm["effective"] == "tickflow"

    routed = dict(DEFAULT_CURRENT, full_minute_data_provider="myfm")
    caps_routed = _by_id(build_capability_matrix(routed, tickflow_tier="expert"))
    assert caps_routed["full_minute"]["effective"] == "myfm"
    assert caps_routed["full_minute"]["usable"] is True

    caps_pro = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="pro"))
    fm_pro = caps_pro["full_minute"]
    assert [c["name"] for c in fm_pro["candidates"]] == ["myfm"]
    assert fm_pro["tf_available"] is False
    assert fm_pro["effective"] == "tickflow"
    assert fm_pro["usable"] is False

    caps_pro_routed = _by_id(build_capability_matrix(routed, tickflow_tier="pro"))
    assert caps_pro_routed["full_minute"]["effective"] == "myfm"
    assert caps_pro_routed["full_minute"]["usable"] is True


def test_public_only_on_implemented_capabilities(monkeypatch):
    """public 只进入复权/实时/财务候选, 不放行日K/分钟/五档/全量分钟。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(build_capability_matrix(dict(DEFAULT_CURRENT), tickflow_tier="expert"))
    for cap_id in ("adj_factor", "realtime", "financial"):
        assert "public" in [c["name"] for c in caps[cap_id]["candidates"]]
    for cap_id in ("daily", "minute", "depth5", "full_minute"):
        assert "public" not in [c["name"] for c in caps[cap_id]["candidates"]]


def test_public_alias_is_usable_without_rewriting_current(monkeypatch):
    """公开源别名只影响 usable/展示, current 保持 getter 注入值。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(
        build_capability_matrix(
            dict(
                DEFAULT_CURRENT,
                realtime_data_provider="public",
                adj_factor_provider="sina",
                financial_data_provider="eastmoney",
            ),
            tickflow_tier="none",
        ),
    )
    assert caps["realtime"]["current"] == "public"
    assert caps["realtime"]["effective"] == "public"
    assert caps["realtime"]["usable"] is True
    assert caps["adj_factor"]["current"] == "sina"
    assert caps["adj_factor"]["effective"] == "public"
    assert caps["adj_factor"]["current_display"] == "公开源"
    assert caps["adj_factor"]["usable"] is True
    assert caps["financial"]["current"] == "eastmoney"
    assert caps["financial"]["effective"] == "public"
    assert caps["financial"]["usable"] is True
    assert caps["daily"]["current"] == "tickflow"
    assert caps["daily"]["usable"] is True


def test_same_as_daily_status_follows_daily(monkeypatch):
    """same_as_daily 按日K生效源判定复权 usable, 不改注入的 current。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, adj_factor_provider="same_as_daily"),
            tickflow_tier="none",
        ),
    )
    adj = caps["adj_factor"]
    assert adj["current"] == "same_as_daily"
    assert adj["current_display"] == "跟随日K"
    assert adj["effective"] == "tickflow"
    assert adj["effective_display"] == "跟随日K · TickFlow"
    assert adj["usable"] is False
    assert caps["daily"]["usable"] is True

    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, adj_factor_provider="same_as_daily"),
            tickflow_tier="starter",
        ),
    )
    assert caps["adj_factor"]["current"] == "same_as_daily"
    assert caps["adj_factor"]["effective"] == "tickflow"
    assert caps["adj_factor"]["usable"] is True


def test_daily_public_preference_is_not_usable(monkeypatch):
    """日K没有 public 实现: 偏好写 public 只展示, usable 仍为假。"""
    _fake_sources(monkeypatch, [])
    caps = _by_id(
        build_capability_matrix(
            dict(DEFAULT_CURRENT, daily_data_provider="public"),
            tickflow_tier="none",
        ),
    )
    assert caps["daily"]["current"] == "public"
    assert caps["daily"]["effective"] == "public"
    assert caps["daily"]["usable"] is False
    assert [c["name"] for c in caps["daily"]["candidates"]] == ["tickflow"]
