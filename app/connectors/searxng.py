"""一般ウェブ検索ボックス（SearXNG・VPSローカル・鍵不要・fail-safe）。

Wikipedia系＝構造の背骨に対し、SearXNGは一般ウェブの広さを機械取り込みするための層
（半田様承認 2026-07-27）。VPS上に自前設置（127.0.0.1:8888・sudo不要のuserspace）。
到達不能や空でも無害（例外時 []）＝GENESIS退化階梯（Level 0を壊さない）。
"""
import os

from .base import cached_get_json

SEARX_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")


async def search(q: str, lang: str = "ja", extra: str = "", n: int = 20):
    """一般ウェブ検索の結果 [{title, content, url, engine}] を返す。extra を足せば AND 検索
    （例 q='リゾーム' extra='哲学' → 'リゾーム 哲学'）。fail-safe（不通/空で []）。"""
    query = (q + " " + extra).strip()
    try:
        d, _, _ = await cached_get_json(f"{SEARX_URL}/search",
            {"q": query, "format": "json", "language": lang}, ttl=86400)
        out = []
        for r in (d.get("results") or [])[:n]:
            out.append({"title": r.get("title") or "", "content": r.get("content") or "",
                        "url": r.get("url") or "", "engine": r.get("engine") or ""})
        return out
    except Exception:
        return []
