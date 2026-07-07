"""Stanford Encyclopedia of Philosophy (SEP) connector — the real entry point.

Field research (docs/RESEARCH_REALITY.md) is unambiguous: philosophers do NOT
start a topic with a keyword search over a scholarly index. They start at the
SEP, read the entry to map the DEBATE (its section headings are the positions),
and then MINE ITS BIBLIOGRAPHY (which is monograph-heavy — exactly what
citation indexes like OpenAlex structurally miss in philosophy). This connector
turns that path into structured data:

  search(q)  -> candidate entries (slug, title)
  entry(slug) -> title, authors, dates (SEP is cited by fixed edition, so the
                 revision date matters), the debate map (sections), the parsed
                 bibliography, related entries, and the canonical URL.

SEP has no JSON API, but entries live at stable URLs and the HTML is regular.
We parse conservatively and cache for a day (SEP itself revises on a quarterly
cadence). No key required; free.
"""
import html as _html
import re

from .base import cached_get_json, ok, err
import httpx
import datetime
from ..db import get_conn, now

BASE = "https://plato.stanford.edu"
_BOILER = {"entry contents", "bibliography", "academic tools",
           "other internet resources", "related entries", "notes",
           "acknowledgments", "supplement"}


def _clean(s: str) -> str:
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


async def _get_html(url: str, ttl: int = 86400):
    """Fetch raw HTML with the same politeness/caching as JSON connectors.
    Reuses api_cache (stores the HTML string as a JSON string)."""
    from .base import UA
    conn = get_conn()
    try:
        row = conn.execute("SELECT fetched_at, body FROM api_cache WHERE url=?",
                           (url,)).fetchone()
        if row:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(row["fetched_at"])).total_seconds()
            if age < ttl:
                import json
                return json.loads(row["body"]), row["fetched_at"], True
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": UA}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.text
        import json
        ts = now()
        conn.execute("INSERT OR REPLACE INTO api_cache(url, fetched_at, body) VALUES(?,?,?)",
                     (url, ts, json.dumps(body)))
        conn.commit()
        return body, ts, False
    finally:
        conn.close()


async def search(q: str, limit: int = 6) -> dict:
    try:
        h, ts, cached = await _get_html(
            f"{BASE}/search/searcher.py?query={httpx.QueryParams({'q': q})['q']}", ttl=86400)
        seen, out = set(), []
        # Result rows: <a href="...entries/<slug>/">Title</a>
        for m in re.finditer(r'entries/([a-z0-9-]+)/[^"]*"[^>]*>(.*?)</a>', h, re.S):
            slug, title = m.group(1), _clean(m.group(2))
            if slug in seen or not title or title.lower().startswith("http"):
                continue
            seen.add(slug)
            out.append({"slug": slug, "title": title,
                        "url": f"{BASE}/entries/{slug}/"})
            if len(out) >= limit:
                break
        return ok("sep", ts, cached, out)
    except Exception as e:
        return err("sep", e)


async def entry(slug: str) -> dict:
    try:
        h, ts, cached = await _get_html(f"{BASE}/entries/{slug}/")
        title = re.search(r"<h1>(.*?)</h1>", h, re.S)
        title = _clean(title.group(1)) if title else slug
        pub = re.search(r'id="pubinfo"[^>]*>(.*?)</', h, re.S)
        pubinfo = _clean(pub.group(1)) if pub else ""

        # Debate map: TOC section headings (drop boilerplate). These headings
        # are the positions/moves in the debate — the orientation payload.
        sections = []
        for m in re.finditer(r'<li><a href="#[^"]+">(.*?)</a>', h, re.S):
            s = _clean(m.group(1))
            base = re.sub(r"^\d+(\.\d+)*\.?\s*", "", s)
            if base.lower() in _BOILER or not base:
                continue
            sections.append(s)

        # Bibliography (monograph-heavy — the reason to prefer SEP over OpenAlex).
        bib = []
        bi = h.find('id="bibliography"')
        if bi > 0:
            end = h.find('id="academic-tools"', bi)
            seg = h[bi:end if end > 0 else bi + 40000]
            for m in re.finditer(r"<li[^>]*>(.*?)</li>", seg, re.S):
                item = _clean(m.group(1))
                if len(item) > 12:
                    link = re.search(r'href="(https?://[^"]+)"', m.group(1))
                    bib.append({"text": item[:400], "url": link.group(1) if link else ""})

        # Related SEP entries (the lateral map).
        related = []
        ri = h.find("related-entries")
        if ri < 0:
            ri = h.find("Related Entries")
        if ri > 0:
            seg = h[ri:ri + 6000]
            for m in re.finditer(r'\.\./([a-z0-9-]+)/"[^>]*>(.*?)</a>', seg, re.S):
                rslug, rtitle = m.group(1), _clean(m.group(2))
                if rtitle and rslug != slug:
                    related.append({"slug": rslug, "title": rtitle,
                                    "url": f"{BASE}/entries/{rslug}/"})

        data = {"slug": slug, "title": title, "pubinfo": pubinfo,
                "url": f"{BASE}/entries/{slug}/", "sections": sections[:20],
                "bibliography": bib[:40], "related": related[:12]}
        return ok("sep", ts, cached, data)
    except Exception as e:
        return err("sep", e)
