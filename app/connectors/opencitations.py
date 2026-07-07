"""OpenCitations connector — free citation links for DOIs (token optional)."""
from .base import cached_get_json, ok, err

BASE = "https://opencitations.net/index/api/v2"


async def citation_count(doi: str) -> dict:
    doi = doi.replace("https://doi.org/", "").strip()
    try:
        body, ts, cached = await cached_get_json(
            f"{BASE}/citation-count/doi:{doi}", ttl=86400)
        count = body[0].get("count") if isinstance(body, list) and body else None
        return ok("opencitations", ts, cached, {"doi": doi, "citation_count": count})
    except Exception as e:
        return err("opencitations", e)
