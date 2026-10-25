"""所有者の写し（2026-10-24 10:49・資本論）: 最初に語を入れて Enter を押しただけでは地図が出ず、
「原語から問い直す」を押して初めて出た。初めての語は、意味・語源などの取得と同時に走るため、地図の
組み立てが画面側の打ち切り（20秒）を超えていた（本番ログ: 最初の読み込みに地図の応答の記録が無い）。
地図の取得だけは長く待ち、1回取り直すことを、画面の source で守る。
"""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")


def test_graph_fetch_waits_longer_than_the_default_timeout():
    m = re.search(r"const GRAPH_TIMEOUT_MS = (\d+);", JS)
    d = re.search(r"const API_TIMEOUT_MS = (\d+);", JS)
    assert m and d and int(m.group(1)) >= 60000 > int(d.group(1))
    body = JS[JS.index("async function originResolveGraph"):JS.index("async function originExplore")]
    assert "timeout: GRAPH_TIMEOUT_MS" in body


def test_graph_fetch_is_retried_once():
    body = JS[JS.index("async function originResolveGraph"):JS.index("async function originExplore")]
    assert re.search(r"for \(let attempt = 0; attempt < 2 && !d; attempt\+\+\)", body)


def test_dimensions_use_the_same_article_as_the_map(monkeypatch):
    """所有者の写し（10/25 21:25）: 言葉と物 の「固有の切り口」に、全文検索の1位「建築物」の節が並んだ。
    地図・原点の欄と同じ解決（concept.node）で記事を選び、検索に頼ったときは matched_by=search と返す。"""
    import asyncio
    from app import main
    from app.connectors import concept

    async def bridged(q, lang):
        return (q, None)

    async def node(word, lang="ja"):
        return {"data": {"found": True, "title": "言葉と物"}}
    calls = []

    async def fake_get(url, params=None, **k):
        calls.append(dict(params or {}))
        if (params or {}).get("action") == "parse":
            return {"parse": {"sections": [{"toclevel": 1, "line": "概要", "anchor": "概要"}]}}, "t", True
        return {"query": {"pages": {"1": {}}}}, "t", True
    monkeypatch.setattr(main, "_bridged_term", bridged)
    monkeypatch.setattr(concept, "node", node)
    monkeypatch.setattr(main, "cached_get_json", fake_get)
    d = asyncio.run(main.api_dimensions("言葉と物", "ja"))
    assert d["title"] == "言葉と物" and d["matched_by"] == "title"
    assert not any(c.get("list") == "search" for c in calls)   # 全文検索の1位を使わない

    async def missing(word, lang="ja"):
        return {"data": {"found": False}}

    async def fake_get2(url, params=None, **k):
        if (params or {}).get("list") == "search":
            return {"query": {"search": [{"title": "近い記事"}]}}, "t", True
        if (params or {}).get("action") == "parse":
            return {"parse": {"sections": []}}, "t", True
        return {"query": {"pages": {"1": {}}}}, "t", True
    monkeypatch.setattr(concept, "node", missing)
    monkeypatch.setattr(main, "cached_get_json", fake_get2)
    d = asyncio.run(main.api_dimensions("ない語", "ja"))
    assert d["title"] == "近い記事" and d["matched_by"] == "search"   # 検索に頼ったことを返す（画面がそれを告げる）
