"""CiNii Research connector — Japanese scholarship (articles, books, theses).

Field reality (半田様, 2026-07-08): the SEP-centric orientation is Anglophone
and returns nothing — worse, a misleading fallback — for a Japanese subject
like 吉本隆明's 共同幻想論. But the specialist system already exists: CiNii
Research (NII) indexes Japanese academic articles, books and theses. Standing on
it as the first-hint bibliography (then expanding secondarily) is the rational,
efficient method — we do NOT reinvent Japanese scholarly search.

CiNii exposes an OpenSearch endpoint returning JSON-LD:
  https://cir.nii.ac.jp/opensearch/all?q=<term>&count=<n>&format=json
Each item carries title, dc:creator[], dc:publisher, dc:type (Article/Book/…),
prism:publicationDate, and a stable crid URL. Free, keyless.
"""
from .base import cached_get_json, ok, err

API = "https://cir.nii.ac.jp/opensearch/all"


async def search(q: str, limit: int = 8) -> dict:
    if not q.strip():
        return ok("cinii", None, False, [])
    try:
        body, ts, cached = await cached_get_json(
            API, {"q": q, "count": limit, "format": "json"}, ttl=3600)
        out = []
        for it in (body.get("items") or [])[:limit]:
            cre = it.get("dc:creator") or []
            if isinstance(cre, str):
                cre = [cre]
            link = it.get("link") or {}
            url = (link.get("@id") if isinstance(link, dict) else link) or it.get("@id", "")
            out.append({
                "title": (it.get("title") or "").strip(),
                "creators": [str(c).strip() for c in cre][:5],
                "publisher": (it.get("dc:publisher") or "").strip(),
                "year": str(it.get("prism:publicationDate") or "")[:10],
                "type": it.get("dc:type") or "",
                "url": url,
            })
        return ok("cinii", ts, cached, out)
    except Exception as e:
        return err("cinii", e)
