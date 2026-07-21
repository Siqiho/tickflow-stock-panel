from __future__ import annotations

from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.quote_fallback import (
    fetch_public_market_quotes,
    fetch_sina_quotes,
    fetch_tencent_quotes,
)


def _tencent_line(code: str, *, raw_volume: str, raw_amount_wan: str) -> str:
    parts = [""] * 50
    parts[1] = "测试"
    parts[2] = code[2:]
    parts[3] = "10"
    parts[4] = "9"
    parts[5] = "9.5"
    parts[6] = raw_volume
    parts[9] = "9.9"
    parts[10] = "1"
    parts[19] = "10.1"
    parts[20] = "2"
    parts[33] = "10.2"
    parts[34] = "9.4"
    parts[37] = raw_amount_wan
    return f'v_{code}="' + "~".join(parts) + '";\n'


def test_tencent_quote_normalizes_amount_and_main_board_volume(monkeypatch):
    client = ResilientHttpClient()
    monkeypatch.setattr(
        client,
        "get_text",
        lambda *args, **kwargs: FetchResult(
            ok=True,
            text=_tencent_line("sz000001", raw_volume="1256397", raw_amount_wan="137273"),
            status_code=200,
        ),
    )

    [row] = fetch_tencent_quotes(["000001.SZ"], client=client)

    assert row["volume"] == 1_256_397  # canonical unit: lots (100 shares)
    assert row["amount"] == 1_372_730_000  # canonical unit: CNY
    assert row["source_volume_unit"] == "lot"
    assert row["source_amount_unit"] == "ten_thousand_cny"
    assert row["unit_version"] == "cn_quote_v1"


def test_tencent_quote_normalizes_star_market_shares_to_lots(monkeypatch):
    client = ResilientHttpClient()
    monkeypatch.setattr(
        client,
        "get_text",
        lambda *args, **kwargs: FetchResult(
            ok=True,
            text=_tencent_line("sh688549", raw_volume="107491870", raw_amount_wan="258234"),
            status_code=200,
        ),
    )

    [row] = fetch_tencent_quotes(["688549.SH"], client=client)

    assert row["volume"] == 1_074_918.7  # Tencent STAR volume is shares
    assert row["amount"] == 2_582_340_000
    assert row["source_volume_unit"] == "share"


def test_sina_quote_normalizes_shares_to_lots(monkeypatch):
    client = ResilientHttpClient()
    fields = ["测试", "9.5", "9", "10", "10.2", "9.4", "0", "0", "125639700", "1372730000"]
    monkeypatch.setattr(
        client,
        "get_text",
        lambda *args, **kwargs: FetchResult(
            ok=True,
            text='var hq_str_sz000001="' + ",".join(fields) + '";\n',
            status_code=200,
        ),
    )

    [row] = fetch_sina_quotes(["000001.SZ"], client=client)

    assert row["volume"] == 1_256_397
    assert row["amount"] == 1_372_730_000
    assert row["source_volume_unit"] == "share"
    assert row["source_amount_unit"] == "cny"
    assert row["unit_version"] == "cn_quote_v1"


def test_fetch_public_market_quotes_batches(monkeypatch):
    client = ResilientHttpClient()
    calls = {"n": 0}

    def fake_get_text(url, **kwargs):
        calls["n"] += 1
        body = _tencent_line("sz000001", raw_volume="100", raw_amount_wan="123")
        return FetchResult(ok=True, text=body, status_code=200)

    monkeypatch.setattr(client, "get_text", fake_get_text)
    # 120 symbols -> at least 2 batches with batch_size=80
    syms = [f"{i:06d}.SZ" for i in range(1, 121)]
    rows = fetch_public_market_quotes(syms, batch_size=80, pause_s=0, client=client)
    assert calls["n"] >= 2
    assert rows
    assert rows[0]["source"] == "tencent"
