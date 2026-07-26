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
WD_API = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"


def _claim_qids(claims, pid):
    """Target QIDs of a wikidata entity property (P61/P112/P138…) — deterministic."""
    out = []
    for c in claims.get(pid, []):
        dv = c.get("mainsnak", {}).get("datavalue")
        if dv and isinstance(dv.get("value"), dict) and dv["value"].get("id"):
            out.append(dv["value"]["id"])
    return out


async def _resolve(qids, lang="ja"):
    """Resolve QIDs → [{qid,label,is_person}] in one call (labels + P31 person check)."""
    qids = list(dict.fromkeys([q for q in qids if q]))
    if not qids:
        return {}
    body, _, _ = await cached_get_json(WD_API, {
        "action": "wbgetentities", "ids": "|".join(qids[:20]),
        "props": "labels|claims", "languages": f"{lang}|en", "format": "json"}, ttl=86400)
    out = {}
    for q, e in body.get("entities", {}).items():
        lab = e.get("labels", {})
        name = (lab.get(lang) or lab.get("en") or {}).get("value")
        p31 = _claim_qids(e.get("claims", {}), "P31")
        out[q] = {"qid": q, "label": name, "is_person": "Q5" in p31}
    return out

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


# 概念の星座（類語・対義）: 近い/類する関係と、対立/区別される関係を Wikidata の型付き
# 属性で。概念自身のclaim＝偏りなく決定論的。人物は含めない（思想家レンズの領分）。
_REL_NEAR = ["P460", "P1269", "P279", "P361", "P527"]   # 同一視/facet/上位/一部/部分
_REL_OPP = ["P461", "P1889"]                            # 対義/別物


async def _seealso_qids(word, lang):
    """記事の『関連項目/See also』セクションの他概念（title→qid）。人物除外は呼び出し側。"""
    try:
        s, _, _ = await cached_get_json(WP_API.format(lang=lang), {
            "action": "parse", "page": word, "prop": "sections", "format": "json"}, ttl=86400)
        idx = next((sec.get("index") for sec in s.get("parse", {}).get("sections", [])
                    if sec.get("line") in ("関連項目", "関連概念", "See also")), None)
        if not idx:
            return []
        lk, _, _ = await cached_get_json(WP_API.format(lang=lang), {
            "action": "parse", "page": word, "section": idx, "prop": "links", "format": "json"}, ttl=86400)
        titles = [l["*"] for l in lk.get("parse", {}).get("links", []) if l.get("ns") == 0][:10]
        if not titles:
            return []
        pp, _, _ = await cached_get_json(WP_API.format(lang=lang), {
            "action": "query", "prop": "pageprops", "titles": "|".join(titles),
            "redirects": 1, "format": "json"}, ttl=86400)
        return [pg.get("pageprops", {}).get("wikibase_item")
                for pg in pp.get("query", {}).get("pages", {}).values()
                if pg.get("pageprops", {}).get("wikibase_item")]
    except Exception:
        return []


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

        labels, originators, named_after = {}, [], []
        relations = {"near": [], "opposite": []}
        if qid:
            eb, _, _ = await cached_get_json(ENTITY.format(qid=qid), ttl=86400)
            ent = eb.get("entities", {}).get(qid, {})
            labels = {lg: v["value"] for lg, v in ent.get("labels", {}).items()}
            # 概念の知的原点（この概念を"立てた"人）: P61 発見者・考案者／P112 創始者。
            # 概念自身のclaim＝検索の偏りが無く高精度（リゾーム→ドゥルーズ・ガタリ）。
            # 無い概念(疎外・縁起)も多い＝高精度・低再現。無いときは捏造しない（P6）。
            claims = ent.get("claims", {})
            orig_q = _claim_qids(claims, "P61") + _claim_qids(claims, "P112")
            na_q = _claim_qids(claims, "P138")  # named after＝語形の由来（rhizome←根茎:植物）
            near_q = [x for p in _REL_NEAR for x in _claim_qids(claims, p)]  # 近い/類する
            opp_q = [x for p in _REL_OPP for x in _claim_qids(claims, p)]    # 対立/区別
            seealso_q = await _seealso_qids(word, lang)                      # 記事の関連項目で補完
            res = await _resolve(orig_q + na_q + near_q + opp_q + seealso_q, lang)
            originators = [res[q] for q in dict.fromkeys(orig_q) if q in res and res[q]["is_person"]]
            named_after = [res[q] for q in dict.fromkeys(na_q) if q in res]
            # 星座: 人物・自分自身を除外し、近い(Wikidata近縁＋関連項目)/対立(対義・別物)に分類
            near = [res[q] for q in dict.fromkeys(near_q + seealso_q)
                    if q in res and res[q]["label"] and not res[q]["is_person"] and q != qid]
            opp = [res[q] for q in dict.fromkeys(opp_q)
                   if q in res and res[q]["label"] and not res[q]["is_person"] and q != qid]
            relations = {"near": near[:10], "opposite": opp[:6]}

        return ok("concept-node", ts, cached, {
            "word": word, "found": True, "qid": qid,
            "original_terms": origs,          # 概念-翻訳-原点の候補（記事が明示・LEAD）
            "originators": originators,        # 概念を立てた思想家（P61/P112・決定論・人物のみ）
            "named_after": named_after,        # 語形の由来（P138・語源であって概念の原点でない）
            "relations": relations,            # 類語・対義の星座（近い/対立・人物除外・決定論）
            "breadth_labels": labels,          # 多言語breadth（Wikidata全ラベル）
            "breadth_count": len(labels),
            "extract": extract[:500],
            "article_url": f"https://{lang}.wikipedia.org/wiki/{word}",
            "wikidata_url": (f"https://www.wikidata.org/wiki/{qid}" if qid else None),
        })
    except Exception as e:
        return err("concept-node", e)
