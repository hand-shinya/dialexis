"""DWDS connector — the ORIGINAL-language (German) neighborhood of a word.

原語による探求の柱: for a German term this returns (a) its corpus frequency and
(b) its Wortprofil collocations grouped by grammatical relation — the living
neighborhood a word travels with in German (Entfremdung ↔ Aufhebung /
Verdinglichung / überwinden), which a Japanese translation makes invisible.

NOTE (axiom 3, honesty): Wortprofil has no clean JSON API, so collocations are
extracted from the server-rendered HTML table. This is a SCRAPE — brittle to
DWDS markup changes — and is labelled as such to callers. Cached politely; DWDS
sets a tdm-reservation, so we never hammer it. Frequency uses the real JSON API.
"""
import re
import urllib.parse

from .base import cached_get_json, cached_get_text, ok, err, now

FREQ_API = "https://www.dwds.de/api/frequency/"
WP_URL = "https://www.dwds.de/wp/{term}"

# One collocate row: data-freq="N" > <span title="Lemma: WORD; ...">…</span>
# </span> <span title="aus der Relation »RELATION«"> — validated 2026-07-17.
_COLLO = re.compile(
    r'data-freq="(\d+)"\s*>\s*<span[^>]*title="Lemma:\s*([^;"]+)[^"]*"[^>]*>'
    r'[^<]+</span>\s*</span>\s*<span[^>]*title="aus der Relation[^»]*»([^«]+)«',
    re.S)


async def frequency(term: str) -> dict:
    """Corpus frequency of a German lemma (real JSON API)."""
    try:
        body, ts, cached = await cached_get_json(FREQ_API, {"q": term}, ttl=86400)
        return ok("dwds_frequency", ts, cached, body)
    except Exception as e:
        return err("dwds_frequency", e)


async def wortprofil(term: str, per_relation: int = 8) -> dict:
    """Collocations grouped by grammatical relation, each sorted by frequency.
    data = {"scraped": True, "relations": {relation: [{word, freq}, ...]}}."""
    try:
        url = WP_URL.format(term=urllib.parse.quote(term))
        html, ts, cached = await cached_get_text(url, ttl=86400)
        rels: dict[str, list] = {}
        for freq, lemma, rel in _COLLO.findall(html):
            rels.setdefault(rel.strip(), []).append(
                {"word": lemma.strip(), "freq": int(freq)})
        for rel, items in rels.items():
            seen, uniq = set(), []
            for it in sorted(items, key=lambda x: -x["freq"]):
                if it["word"] in seen:
                    continue
                seen.add(it["word"])
                uniq.append(it)
            rels[rel] = uniq[:per_relation]
        return ok("dwds_wortprofil", ts, cached,
                  {"scraped": True, "term": term, "relations": rels})
    except Exception as e:
        return err("dwds_wortprofil", e)
