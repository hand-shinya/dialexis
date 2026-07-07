"""Wikipedia / Wikisource connector — free, keyless summaries and primary-text links."""
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


def wikisource_url(title: str, lang: str) -> str:
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return f"https://{lang}.wikisource.org/wiki/{t}"
