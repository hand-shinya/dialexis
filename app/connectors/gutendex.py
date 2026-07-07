"""Gutendex connector — free, keyless Project Gutenberg catalog (public-domain texts)."""
from .base import cached_get_json, ok, err

BASE = "https://gutendex.com/books"


async def search(q: str, limit: int = 6) -> dict:
    try:
        body, ts, cached = await cached_get_json(BASE, {"search": q}, ttl=86400)
        items = []
        for b in body.get("results", [])[:limit]:
            fmts = b.get("formats", {})
            items.append({
                "id": b.get("id"),
                "title": b.get("title", ""),
                "authors": [a.get("name", "") for a in b.get("authors", [])],
                "languages": b.get("languages", []),
                "read_url": fmts.get("text/html") or fmts.get("text/plain; charset=us-ascii")
                            or f"https://www.gutenberg.org/ebooks/{b.get('id')}",
            })
        return ok("gutendex", ts, cached, items)
    except Exception as e:
        return err("gutendex", e)
