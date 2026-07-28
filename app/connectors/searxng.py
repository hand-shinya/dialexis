"""一般ウェブ検索ボックス（SearXNG・VPSローカル・鍵不要・fail-safe）。

Wikipedia系＝構造の背骨に対し、SearXNGは一般ウェブの広さを機械取り込みするための層
（半田様承認 2026-07-27）。VPS上に自前設置（127.0.0.1:8888・sudo不要のuserspace）。
到達不能や空でも無害（例外時 []）＝GENESIS退化階梯（Level 0を壊さない）。
"""
import os
import re

from .base import cached_get_json

SEARX_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")

# 商業ノイズ除去（情報収集の妨げ＝会社/求人/通販/予約を機械カット・確立した一般手法）。
# ①NOT検索でクエリ側から排除 ②残りをホスト/キーワードでポストフィルタ。
_NOT_TERMS = "-株式会社 -採用 -求人 -通販 -料金 -予約"
_COMM_HOSTS = ("mynavi.jp", "rikunabi.com", "doda.jp", "indeed.com", "en-japan.com", "wantedly.com",
               "type.jp", "green-japan.com", "hotpepper.jp", "beauty.hotpepper", "tabelog.com",
               "rakuten.co.jp", "amazon.co", "kakaku.com", "mercari.com", "shopping.yahoo",
               "studio.site", "hpb.jp", "ekiten.jp", "itp.ne.jp")
_COMM_KW = ("株式会社", "有限会社", "合同会社", "会社概要", "会社案内", "企業情報", "採用", "求人",
            "新卒", "中途", "運営会社", "創業", "通販", "販売", "送料", "購入", "カート", "ECサイト",
            "公式通販", "料金表", "店舗案内", "予約", "口コミ")


def _host(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else "").lower()


def _is_commercial(r):
    h = _host(r.get("url"))
    if any(c in h for c in _COMM_HOSTS):
        return True
    blob = (r.get("title", "") + " " + r.get("content", ""))
    return sum(1 for k in _COMM_KW if k in blob) >= 1


async def search(q: str, lang: str = "ja", extra: str = "", n: int = 20, drop_commercial: bool = False):
    """一般ウェブ検索の結果 [{title, content, url, engine}] を返す。extra を足せば AND 検索
    （例 q='リゾーム' extra='哲学' → 'リゾーム 哲学'）。drop_commercial=True で会社/求人/通販等の
    商業ノイズを NOT検索＋ポストフィルタで除去。fail-safe（不通/空で []）。"""
    query = (q + " " + extra).strip()
    if drop_commercial:
        query = query + " " + _NOT_TERMS
    try:
        d, _, _ = await cached_get_json(f"{SEARX_URL}/search",
            {"q": query, "format": "json", "language": lang}, ttl=86400)
        out = []
        for r in (d.get("results") or []):
            item = {"title": r.get("title") or "", "content": r.get("content") or "",
                    "url": r.get("url") or "", "engine": r.get("engine") or ""}
            if drop_commercial and _is_commercial(item):
                continue
            out.append(item)
            if len(out) >= n:
                break
        return out
    except Exception:
        return []
