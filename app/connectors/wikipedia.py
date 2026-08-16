"""Wikipedia / Wikisource connector — free, keyless summaries and primary-text links."""
import html
import re
import urllib.parse

from .base import cached_get_json, ok, err


async def summary(title: str, lang: str = "en") -> dict:
    try:
        t = urllib.parse.quote(title.replace(" ", "_"), safe="")
        body, ts, cached = await cached_get_json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{t}", ttl=86400)
        data = {
            "title": body.get("title", title),
            "extract": body.get("extract", ""),
            "url": body.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "thumbnail": (body.get("thumbnail") or {}).get("source", ""),
            "lang": lang,
        }
        return ok(f"wikipedia:{lang}", ts, cached, data)
    except Exception as e:
        return err(f"wikipedia:{lang}", e)


async def search(q: str, lang: str = "ja", limit: int = 20) -> dict:
    """全文検索の小さな退避経路（MediaWiki API、鍵不要）。

    SearXNGは一般ウェブの主経路だが、ローカル検索源が停止していても、
    2語検索そのものを「準備中」で捨てない。Wikipedia全文検索は一般ウェブ
    全体の代用品ではないため、呼び出し側が出所を明示して使う。
    """
    try:
        body, ts, cached = await cached_get_json(
            f"https://{lang}.wikipedia.org/w/api.php",
            {"action": "query", "list": "search", "srsearch": q,
             "srlimit": min(max(int(limit), 1), 50), "srprop": "snippet",
             "format": "json", "formatversion": 2, "utf8": 1},
            ttl=3600)
        rows = ((body.get("query") or {}).get("search") or [])
        data = []
        for row in rows[:limit]:
            title = (row.get("title") or "").strip()
            if not title:
                continue
            snippet = re.sub(r"<[^>]+>", " ", row.get("snippet") or "")
            snippet = html.unescape(re.sub(r"\s+", " ", snippet)).strip()
            data.append({
                "title": title,
                "content": snippet,
                "url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'), safe='')}",
                "engine": "Wikipedia全文検索",
            })
        return ok(f"wikipedia-search:{lang}", ts, cached, data)
    except Exception as e:
        return err(f"wikipedia-search:{lang}", e)


def wikisource_url(title: str, lang: str) -> str:
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return f"https://{lang}.wikisource.org/wiki/{t}"
