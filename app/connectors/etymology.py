"""普遍的な語源解剖（半田様指摘＝弁証法のdia-対話性の脱落を復元）。

Wiktionaryの語源記述から、原語への連鎖（from Old French…, from Ancient Greek…）と、
構成要素（prefix+root, 例 dia+legein）を、意味glossつきで抽出する。特定語のseed不要＝
どんな語にも普遍適用（P11）。翻訳で見えなくなった原義を、原語の実文書に接地して見せる。

第三者提案の ConceptNet差分エンジンは不採用: (1) api.conceptnet.io がVPSから 502/不通
(2) 言語跨ぎの label 集合差分（ja語 − en語）は原理的に無意味（両者は文字列が重ならず差分＝全部）。
真の意味drift差分は多言語埋め込みが要りVPSのRAMで不可＝将来課題。本モジュールは"動く核"に絞る。
"""
import re

from .base import cached_get_json

WT = "https://en.wiktionary.org/w/api.php"


async def _extract(term):
    try:
        body, ts, cached = await cached_get_json(WT, {
            "action": "query", "titles": term, "prop": "extracts",
            "explaintext": 1, "format": "json"}, ttl=86400)
        page = next(iter(body.get("query", {}).get("pages", {}).values()), {})
        if "missing" in page:
            return None
        return page.get("extract", "") or ""
    except Exception:
        return None


def _gloss(inside):
    g = re.search(r"[“\"]([^”\"]+)[”\"]", inside or "")
    return g.group(1) if g else ""


def parse_etymology(text):
    m = re.search(r"===?\s*Etymology[^\n=]*=+\s*(.+?)(?:\n==|\Z)", text, re.DOTALL)
    seg = (m.group(1) if m else text)[:900]
    chain = []
    # 言語名は複数語がある（Late Latin / Ancient Greek / Old French）→ 大文字始まり語を貪欲に取る
    for lang, term, inside in re.findall(r"from ([A-Z][a-z]+(?: [A-Z][a-z]+)*) ([^\s,(]+)\s*(?:\(([^)]*)\))?", seg):
        chain.append({"lang": lang.strip(), "term": term.strip(" .,"), "gloss": _gloss(inside)})
    comps = []
    cm = re.search(r"([^\s]+\s*\([^)]*[“\"][^”\"]+[”\"][^)]*\)(?:\s*\+\s*[^\s]+\s*\([^)]*\))+)", seg)
    if cm:
        for term, inside in re.findall(r"([^\s+]+)\s*\(([^)]*)\)", cm.group(1)):
            comps.append({"part": term.strip(), "meaning": _gloss(inside) or inside.strip()[:40]})
    return {"summary": re.sub(r"\s+", " ", seg).strip()[:400], "chain": chain[:6], "components": comps[:6]}


async def anatomy(word, orig_terms, lang="ja"):
    """候補の原語（英/羅/独/希ラベル、無ければ入力語）を順に試し、語源が取れた最初のものを解剖。"""
    for term in [t for t in orig_terms if t] + [word]:
        if not term or not re.search(r"[A-Za-zΑ-Ωα-ωÀ-ÿ]", term):
            continue
        text = await _extract(term)
        if text and "Etymology" in text:
            r = parse_etymology(text)
            if r["chain"] or r["components"]:
                r["term"] = term
                r["wiktionary_url"] = f"https://en.wiktionary.org/wiki/{term}"
                return r
    return {"term": None, "chain": [], "components": [], "summary": ""}
