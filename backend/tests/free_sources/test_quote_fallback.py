from __future__ import annotations

from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.quote_fallback import fetch_sina_quotes, fetch_tencent_quotes


def test_parse_tencent_quotes(monkeypatch):
    client = ResilientHttpClient()
    parts = [""] * 50
    parts[0] = "1"
    parts[1] = "平安银行"
    parts[2] = "000001"
    parts[3] = "11.20"
    parts[4] = "11.00"
    parts[5] = "11.10"
    parts[6] = "100"
    parts[9] = "11.19"   # bid1
    parts[10] = "12"     # bid1_vol
    parts[19] = "11.21"  # ask1
    parts[20] = "0"      # ask1_vol (sealed limit-up style)
    parts[33] = "11.50"
    parts[34] = "10.90"
    parts[37] = "123456"
    sample = 'v_sz000001="' + "~".join(parts) + '";\n'

    def fake_get_text(url, **kwargs):
        return FetchResult(ok=True, text=sample, status_code=200)

    monkeypatch.setattr(client, "get_text", fake_get_text)
    rows = fetch_tencent_quotes(["000001.SZ"], client=client)
    assert rows
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["last"] == 11.2
    assert rows[0]["source"] == "tencent"
    assert rows[0]["bid1_vol"] == 12
    assert rows[0]["ask1_vol"] == 0


def test_parse_sina_quotes(monkeypatch):
    client = ResilientHttpClient()
    sample = 'var hq_str_sz000001="平安银行,11.10,11.00,11.20,11.50,10.90,11.19,11.20,1000,123456,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-07,15:00:00,00";\n'

    def fake_get_text(url, **kwargs):
        return FetchResult(ok=True, text=sample, status_code=200)

    monkeypatch.setattr(client, "get_text", fake_get_text)
    rows = fetch_sina_quotes(["000001.SZ"], client=client)
    assert rows
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["last"] == 11.2
    assert rows[0]["source"] == "sina"
