import json

from app.services import ai_provider, concept_rotation_analyzer


def test_compute_rotation_signals_classifies_leaders_rising_and_fading():
    dates = ["2026-08-08", "2026-08-07", "2026-08-06", "2026-08-05"]
    columns = {
        "2026-08-08": [("主线A", 0.04), ("新晋B", 0.03)] + [(f"中游{i}", 0.01) for i in range(28)] + [("退潮C", -0.01)],
        "2026-08-07": [("主线A", 0.03), ("新晋B", 0.02)] + [(f"中游{i}", 0.01) for i in range(28)] + [("退潮C", 0.00)],
        "2026-08-06": [("主线A", 0.03), ("退潮C", 0.04)] + [(f"中游{i}", 0.01) for i in range(28)] + [("新晋B", -0.01)],
        "2026-08-05": [("退潮C", 0.05), ("主线A", 0.02)] + [(f"中游{i}", 0.01) for i in range(28)] + [("新晋B", -0.02)],
    }
    # 补足每列长度到 40, 让新晋从 40 名外冲进前 20, 退潮从第 1 滑到 30 外。
    for date, col in columns.items():
        extra = [(f"垫底{i}", -0.02) for i in range(40 - len(col))]
        columns[date] = col + extra
    columns["2026-08-05"] = [("退潮C", 0.05)] + [(f"中游{i}", 0.01) for i in range(38)] + [("新晋B", -0.02), ("主线A", 0.02)]
    columns["2026-08-05"][1] = ("主线A", 0.02)
    columns["2026-08-08"][30] = ("退潮C", -0.01)
    columns["2026-08-07"][31] = ("退潮C", 0.00)

    signals = concept_rotation_analyzer._compute_rotation_signals(dates, columns)

    leader_names = [item["concept"] for item in signals["persistent_leaders"]]
    rising_names = [item["concept"] for item in signals["rising"]]
    fading_names = [item["concept"] for item in signals["fading"]]
    assert "主线A" in leader_names
    assert "新晋B" in rising_names
    assert "退潮C" in fading_names


async def test_analyze_rotation_stream_emits_meta_delta_done(monkeypatch):
    dates = ["2026-08-08", "2026-08-07"]
    columns = {
        "2026-08-08": [("主线A", 0.04)] + [(f"中游{i}", 0.01) for i in range(9)],
        "2026-08-07": [("主线A", 0.03)] + [(f"中游{i}", 0.01) for i in range(9)],
    }

    monkeypatch.setattr(
        "app.services.rps_rotation.build_rps_rotation",
        lambda repo, days, kind="concept", level=None: {
            "dates": dates,
            "columns": columns,
            "concept_count": 10,
        },
    )
    monkeypatch.setattr(
        "app.services.market_overview_builder.build_market_overview",
        lambda *args, **kwargs: {
            "indices": [{"name": "上证指数", "change_pct": 0.012}],
            "emotion": {"score": 62, "label": "偏强"},
            "limit": {"limit_up": 48, "broken": 12, "limit_down": 3, "max_boards": 5},
            "amount": {"total": 1.2e12},
        },
    )

    captured = []

    async def fake_stream_ai_text(messages, **kwargs):
        captured.extend(messages)
        yield "主线仍在半导体。"

    monkeypatch.setattr(ai_provider, "ai_configured", lambda: True)
    monkeypatch.setattr(ai_provider, "stream_ai_text", fake_stream_ai_text)

    events = [
        json.loads(chunk)
        async for chunk in concept_rotation_analyzer.analyze_rotation_stream(
            object(), days=7, focus="关注半导体", kind="concept"
        )
    ]

    assert [event["type"] for event in events] == ["meta", "delta", "done"]
    assert "主线: 主线A" in events[0]["summary"]
    assert events[1]["content"] == "主线仍在半导体。"
    assert captured[0]["role"] == "system"
    assert "概念板块" in captured[0]["content"]
    assert captured[1]["role"] == "user"
    assert "本次分析请特别关注: 关注半导体" in captured[1]["content"]


async def test_analyze_rotation_stream_uses_industry_copy(monkeypatch):
    monkeypatch.setattr(
        "app.services.rps_rotation.build_rps_rotation",
        lambda repo, days, kind="concept", level=None: {"dates": [], "columns": {}, "concept_count": 0},
    )

    events = [
        json.loads(chunk)
        async for chunk in concept_rotation_analyzer.analyze_rotation_stream(
            object(), kind="industry", level=2
        )
    ]

    assert events == [{
        "type": "error",
        "message": "暂无行业轮动数据,请先在「行业分析」页获取行业数据源",
    }]
