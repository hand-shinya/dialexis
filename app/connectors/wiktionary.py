"""Wiktionary connector — the ORIGINAL-language sense & etymology of a word.

原語による探求の柱: for a source-language term this returns its own-language
senses (Bedeutungen), etymology (Herkunft), and near-synonyms (Sinnverwandte) —
what the word MEANS in its own tongue and where it came from, not the Japanese
gloss. Etymology is where "元になった原語" and "捨てられた区別" become visible
(Entäußerung ← theological kenosis).

Uses the MediaWiki action=parse API (wikitext), then extracts the standardized
section templates. Section markup is stable across de.wiktionary entries.
"""
import re

from .base import cached_get_json, ok, err

API = "https://{lang}.wiktionary.org/w/api.php"

# de.wiktionary standardized section templates.
_SECTIONS = {
    "senses": "Bedeutungen",
    "etymology": "Herkunft",
    "synonyms": "Sinnverwandte",
    "antonyms": "Gegenwörter",
}


def _extract(wikitext: str, template: str) -> str:
    """Pull the block after {{Template}} up to the next {{Section}} template."""
    m = re.search(r"\{\{" + template + r"\}\}(.*?)(\n\{\{[A-ZÄÖÜ][^}|]*\}\}|\Z)",
                  wikitext, re.S)
    if not m:
        return ""
    txt = m.group(1)
    txt = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", txt)   # [[a|b]] → b
    txt = re.sub(r"\[\[|\]\]", "", txt)                       # [[x]] → x
    txt = re.sub(r"''+", "", txt)                             # italics
    txt = re.sub(r"<[^>]+>", "", txt)                         # stray html
    return txt.strip()


async def entry(term: str, lang: str = "de") -> dict:
    """Return {term, lang, senses, etymology, synonyms, url} for a term in its
    own-language Wiktionary. Empty strings for sections that are absent."""
    try:
        body, ts, cached = await cached_get_json(
            API.format(lang=lang),
            {"action": "parse", "page": term, "prop": "wikitext",
             "format": "json", "redirects": 1}, ttl=86400)
        wt = body.get("parse", {}).get("wikitext", {}).get("*", "")
        data = {"term": term, "lang": lang,
                "url": f"https://{lang}.wiktionary.org/wiki/{term}"}
        for key, tmpl in _SECTIONS.items():
            data[key] = _extract(wt, tmpl)
        data["found"] = bool(wt)
        return ok("wiktionary", ts, cached, data)
    except Exception as e:
        return err("wiktionary", e)
