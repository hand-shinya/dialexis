"""Crossref connector — free, keyless DOI metadata."""
from .base import cached_get_json, ok, err

BASE = "https://api.crossref.org"


async def search_works(q: str, limit: int = 8, from_date: str = "") -> dict:
    params = {"query": q, "rows": limit, "sort": "relevance"}
    if from_date:
        params["filter"] = f"from-pub-date:{from_date}"
        params["sort"] = "published"
        params["order"] = "desc"
    try:
        body, ts, cached = await cached_get_json(f"{BASE}/works", params, ttl=600)
        items = []
        for it in body.get("message", {}).get("items", []):
            title_list = it.get("title") or []
            title = title_list[0].strip() if title_list and title_list[0].strip() else ""
            if not title:
                continue  # skip untitled records (e.g. bare JST DOIs) — they are noise
            items.append({
                "doi": it.get("DOI", ""),
                "title": title,
                "year": (it.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0],
                "type": it.get("type", ""),
                "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip()
                            for a in it.get("author", [])[:6]],
                "url": it.get("URL", ""),
                "publisher": it.get("publisher", ""),
            })
        return ok("crossref", ts, cached, items)
    except Exception as e:
        return err("crossref", e)
