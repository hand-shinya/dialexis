"""国立国会図書館サーチ (NDL Search) connector — Japanese editions & translations.

Field requirement (半田様, 2026-07-07): when a Japanese user searches, works
originally in French/German/English are read as JAPANESE TRANSLATIONS (邦訳),
and WHICH TRANSLATOR matters as much as the original text — Kant's 純粋理性批判
in 天野貞祐 vs 中山元 renders Verstand/Vorstellung differently, changing the
argument. This is the Japanese face of the translation-analysis method (D).

NDL Search's OpenSearch API returns bibliographic records (title, creators —
which include the 訳者, publisher, year, NDL link) for essentially every book
published in Japan, including in-copyright translations we cannot show in full
text. It is the authoritative way to answer "which Japanese translations of
this work exist, and who translated them?". Free, keyless.
"""
import html as _html
import re

from .base import UA, ok, err, now
import httpx
import datetime
from ..db import get_conn

API = "https://ndlsearch.ndl.go.jp/api/opensearch"


def _clean(s: str) -> str:
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


async def _get_xml(params: dict, ttl: int = 86400):
    key = API + "?" + str(httpx.QueryParams(params))
    conn = get_conn()
    try:
        row = conn.execute("SELECT fetched_at, body FROM api_cache WHERE url=?",
                           (key,)).fetchone()
        if row:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(row["fetched_at"])).total_seconds()
            if age < ttl:
                import json
                return json.loads(row["body"]), row["fetched_at"], True
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": UA}) as client:
            resp = await client.get(API, params=params)
            resp.raise_for_status()
            body = resp.text
        import json
        ts = now()
        conn.execute("INSERT OR REPLACE INTO api_cache(url, fetched_at, body) VALUES(?,?,?)",
                     (key, ts, json.dumps(body)))
        conn.commit()
        return body, ts, False
    finally:
        conn.close()


def _parse(xml: str, limit: int) -> list:
    out = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        creators = [_clean(c) for c in re.findall(r"<dc:creator>(.*?)</dc:creator>", block, re.S)]
        pub = re.search(r"<dc:publisher>(.*?)</dc:publisher>", block, re.S)
        date = (re.search(r"<dcterms:issued[^>]*>(.*?)</dcterms:issued>", block, re.S)
                or re.search(r"<dc:date>(.*?)</dc:date>", block, re.S))
        link = re.search(r"<link>(.*?)</link>", block, re.S)
        out.append({
            "title": _clean(title.group(1)) if title else "(無題)",
            "creators": creators[:5],
            "publisher": _clean(pub.group(1)) if pub else "",
            "year": _clean(date.group(1))[:10] if date else "",
            "url": _clean(link.group(1)) if link else "",
        })
    return out


async def by_author(author_ja: str, limit: int = 10) -> dict:
    """Japanese translations/editions of an author's works. Uses the surname
    component (after 「・」) which NDL indexes best (イマヌエル・カント → カント)."""
    surname = author_ja.split("・")[-1].strip() if author_ja else ""
    if not surname:
        return ok("ndl", now(), False, [])
    try:
        xml, ts, cached = await _get_xml({"creator": surname, "cnt": limit,
                                          "mediatype": "books"})
        return ok("ndl", ts, cached, _parse(xml, limit))
    except Exception as e:
        return err("ndl", e)


async def by_work(author_ja: str, work_ja: str, limit: int = 5) -> dict:
    """Translations of ONE work: creator(surname) + title. Far more precise than
    a name-only search (surname substrings like メリカント⊃カント otherwise leak in).
    This is the precise 邦訳 lookup: カント + 純粋理性批判 → 天野貞祐訳・中山元訳…"""
    surname = author_ja.split("・")[-1].strip() if author_ja else ""
    if not surname or not work_ja:
        return ok("ndl", now(), False, {"work": work_ja, "editions": []})
    try:
        xml, ts, cached = await _get_xml({"creator": surname, "title": work_ja,
                                          "cnt": limit, "mediatype": "books"})
        return ok("ndl", ts, cached, {"work": work_ja, "editions": _parse(xml, limit)})
    except Exception as e:
        r = err("ndl", e)
        r["data"] = {"work": work_ja, "editions": []}
        return r


async def by_title(title_ja: str, limit: int = 8) -> dict:
    try:
        xml, ts, cached = await _get_xml({"title": title_ja, "cnt": limit,
                                          "mediatype": "1"})
        return ok("ndl", ts, cached, _parse(xml, limit))
    except Exception as e:
        return err("ndl", e)
