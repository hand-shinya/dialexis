"""Concept path — follow the input word's OWN encyclopedic node (never a biased
search) to the concept-translation-origin and its multilingual breadth.

This is the human method the portal is built on: trace where a concept is densely
documented, find what it was translated FROM, and the languages that carry it. It
solves the cases word-etymology (Wiktionary) cannot — 訳語造語 疎外→独 Entfremdung,
縁起→梵 pratītyasamutpāda — and the breadth gap (→ Wikidata's N-language labels).

The word→item link is DETERMINISTIC (the article's own Wikidata id via pageprops),
so it avoids the wbsearchentities Western bias (search 'dharma' → 'Buddhism').

DISCIPLINE (A3): the original-language terms stated in a lead are LEADS surfaced
from dense discourse — grounded enough to show with provenance, but individual
claims stay 'encyclopedic lead', to be confirmed against authoritative sources /
the dictionary layer, never asserted as final fact.
"""
import re

from .base import cached_get_json, ok, err

WP_API = "https://{lang}.wikipedia.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

# Wikipedia lang-template codes → display name (for {{lang-de|Entfremdung}}).
_CODE = {
    "de": "ドイツ語", "en": "英語", "fr": "フランス語", "la": "ラテン語",
    "grc": "古典ギリシャ語", "el": "ギリシャ語", "sa": "サンスクリット語", "pi": "パーリ語",
    "zh": "中国語", "ko": "朝鮮語", "he": "ヘブライ語", "hbo": "古典ヘブライ語",
    "ar": "アラビア語", "fa": "ペルシア語", "ru": "ロシア語", "it": "イタリア語",
    "es": "スペイン語", "pt": "ポルトガル語", "nl": "オランダ語", "bo": "チベット語",
}
# Single-kanji abbreviations Japanese leads use plainly (独: Entfremdung).
_ABBREV = {
    "独": "ドイツ語", "英": "英語", "羅": "ラテン語", "希": "ギリシャ語",
    "梵": "サンスクリット語", "巴": "パーリ語", "中": "中国語", "露": "ロシア語",
    "伊": "イタリア語", "西": "スペイン語", "葡": "ポルトガル語", "蘭": "オランダ語",
    "韓": "韓国語", "朝": "朝鮮語", "蔵": "チベット語",
}


async def node(word: str, lang: str = "ja") -> dict:
    try:
        body, ts, cached = await cached_get_json(WP_API.format(lang=lang), {
            "action": "query", "prop": "pageprops|extracts|revisions",
            "rvprop": "content", "rvslots": "main", "exintro": 1, "explaintext": 1,
            "titles": word, "redirects": 1, "format": "json"})
        pages = body.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "missing" in page:
            return ok("concept-node", ts, cached, {"word": word, "found": False})
        qid = page.get("pageprops", {}).get("wikibase_item")
        extract = page.get("extract", "") or ""
        wikitext = (page.get("revisions", [{}])[0].get("slots", {})
                    .get("main", {}).get("*", "")) if page.get("revisions") else ""

        # original-language terms stated in the lead (concept-translation-origin
        # LEADS). Two forms: {{lang-xx|term}} templates and plain 独: term. Codes
        # like 'de-short'/'zh-hans' normalise to the base ('de'/'zh'); we keep the
        # longest term seen per language (the template form usually beats the
        # truncated plain-text one).
        by_name = {}

        def _add(name, term):
            term = re.sub(r"'''?|\[\[|\]\]", "", term or "").strip()
            if not name or not term:
                return
            if name not in by_name or len(term) > len(by_name[name]["term"]):
                by_name[name] = {"name": name, "term": term}
        for code, term in re.findall(r"\{\{lang-([a-z-]+)\|([^|}\n]+)", wikitext[:2500]):
            base = code.split("-")[0]
            _add(_CODE.get(code) or _CODE.get(base) or base, term)
        for ab, term in re.findall(
                r"([独英羅希梵巴中露伊西葡蘭韓朝蔵])\s*[:：]\s*([^\s、。，,）)（(]+)",
                extract[:700]):
            _add(_ABBREV.get(ab), term)
        origs = list(by_name.values())

        labels = {}
        if qid:
            eb, _, _ = await cached_get_json(ENTITY.format(qid=qid), ttl=86400)
            ent = eb.get("entities", {}).get(qid, {})
            labels = {lg: v["value"] for lg, v in ent.get("labels", {}).items()}

        return ok("concept-node", ts, cached, {
            "word": word, "found": True, "qid": qid,
            "original_terms": origs,          # 概念-翻訳-原点の候補（記事が明示・LEAD）
            "breadth_labels": labels,          # 多言語breadth（Wikidata全ラベル）
            "breadth_count": len(labels),
            "extract": extract[:500],
            "article_url": f"https://{lang}.wikipedia.org/wiki/{word}",
            "wikidata_url": (f"https://www.wikidata.org/wiki/{qid}" if qid else None),
        })
    except Exception as e:
        return err("concept-node", e)
