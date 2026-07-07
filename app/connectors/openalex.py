"""OpenAlex connector — free, keyless scholarly catalog (works/authors/citations)."""
from .base import cached_get_json, ok, err

BASE = "https://api.openalex.org"


def _work(w: dict) -> dict:
    return {
        "id": w.get("id", ""),
        "title": w.get("display_name") or "(untitled)",
        "year": w.get("publication_year"),
        "doi": w.get("doi") or "",
        "type": w.get("type", ""),
        "cited_by_count": w.get("cited_by_count", 0),
        "authors": [a["author"]["display_name"]
                    for a in w.get("authorships", [])[:6] if a.get("author")],
        "url": (w.get("primary_location") or {}).get("landing_page_url")
               or w.get("doi") or w.get("id", ""),
        "open_access": (w.get("open_access") or {}).get("is_oa", False),
    }


async def search_works(q: str, limit: int = 10) -> dict:
    try:
        body, ts, cached = await cached_get_json(f"{BASE}/works", {
            "search": q, "per-page": limit, "sort": "relevance_score:desc"})
        return ok("openalex", ts, cached, [_work(w) for w in body.get("results", [])])
    except Exception as e:
        return err("openalex", e)


async def search_authors(q: str, limit: int = 5) -> dict:
    try:
        body, ts, cached = await cached_get_json(f"{BASE}/authors", {
            "search": q, "per-page": limit})
        data = [{"id": a["id"], "name": a.get("display_name", ""),
                 "works_count": a.get("works_count", 0),
                 "cited_by_count": a.get("cited_by_count", 0),
                 "hint": (a.get("hint") or "")}
                for a in body.get("results", [])]
        return ok("openalex", ts, cached, data)
    except Exception as e:
        return err("openalex", e)


async def works_by_author(author_id: str, from_date: str = "", limit: int = 25) -> dict:
    """author_id: full OpenAlex URL or bare id. from_date: YYYY-MM-DD filter."""
    aid = author_id.rsplit("/", 1)[-1]
    flt = f"author.id:{aid}"
    if from_date:
        flt += f",from_publication_date:{from_date}"
    try:
        body, ts, cached = await cached_get_json(f"{BASE}/works", {
            "filter": flt, "per-page": limit, "sort": "publication_date:desc"}, ttl=600)
        return ok("openalex", ts, cached, [_work(w) for w in body.get("results", [])])
    except Exception as e:
        return err("openalex", e)


async def works_search_since(q: str, from_date: str, limit: int = 25) -> dict:
    try:
        body, ts, cached = await cached_get_json(f"{BASE}/works", {
            "search": q, "filter": f"from_publication_date:{from_date}",
            "per-page": limit, "sort": "publication_date:desc"}, ttl=600)
        return ok("openalex", ts, cached, [_work(w) for w in body.get("results", [])])
    except Exception as e:
        return err("openalex", e)
