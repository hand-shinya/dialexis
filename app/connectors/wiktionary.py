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


def _ja_clean(s: str) -> str:
    """Clean ja.wiktionary definition markup into readable text."""
    def _okuri(m):  # {{おくりがな2|疎|うと|んじる|…}} → 疎んじる (kanji + okurigana)
        p = m.group(1).split("|")
        return (p[0] + p[2]) if len(p) >= 3 else "".join(p)
    s = re.sub(r"\{\{おくりがな2\|([^}]*)\}\}", _okuri, s)
    def _ctx(m):    # {{context|哲学|経済|lang=ja}} → （哲学・経済）
        p = [x for x in m.group(1).split("|") if "=" not in x]
        return "（" + "・".join(p) + "）" if p else ""
    s = re.sub(r"\{\{context\|([^}]*)\}\}", _ctx, s, flags=re.I)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)                      # drop remaining templates
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)       # [[a|b]] → b
    s = re.sub(r"\[\[|\]\]", "", s)
    s = re.sub(r"''+", "", s)
    return s.strip()


# Wiktionary language codes → display names. Deliberately WIDE and not centred on
# any family: the point of the portal is to let unfamiliar languages surface. This
# is a convenience label only — an unmapped code is shown as the raw code (honest),
# never dropped, so breadth is never silently narrowed by our own gaps.
LANG_NAMES = {
    "en": "英語", "de": "ドイツ語", "fr": "フランス語", "it": "イタリア語", "es": "スペイン語",
    "pt": "ポルトガル語", "nl": "オランダ語", "ru": "ロシア語", "pl": "ポーランド語",
    "la": "ラテン語", "grc": "古典ギリシャ語", "el": "ギリシャ語", "sa": "サンスクリット語",
    "pi": "パーリ語", "he": "ヘブライ語", "hbo": "古典ヘブライ語", "ar": "アラビア語",
    "fa": "ペルシア語", "tr": "トルコ語", "zh": "中国語", "ltc": "中古中国語",
    "och": "上古中国語", "ja": "日本語", "ojp": "上代日本語", "jpx-pro": "祖日本語",
    "ko": "朝鮮語", "vi": "ベトナム語", "hi": "ヒンディー語", "ta": "タミル語",
    "bo": "チベット語", "my": "ビルマ語", "th": "タイ語", "km": "クメール語",
    "sw": "スワヒリ語", "am": "アムハラ語", "ka": "グルジア語", "hy": "アルメニア語",
    "ga": "アイルランド語", "cy": "ウェールズ語", "eu": "バスク語", "fi": "フィンランド語",
    "gem-pro": "祖ゲルマン語", "ine-pro": "印欧祖語", "gmw-pro": "西ゲルマン祖語",
    "ang": "古英語", "enm": "中英語", "iir-pro": "インド・イラン祖語", "sla-pro": "スラヴ祖語",
}


def langname(code: str) -> str:
    return LANG_NAMES.get(code, code)  # unmapped → raw code, never dropped


# Wiktionary section heading → language code, to drop self-references from a chain.
_SECTION_CODE = {
    "English": "en", "German": "de", "French": "fr", "Latin": "la", "Japanese": "ja",
    "Chinese": "zh", "Korean": "ko", "Vietnamese": "vi", "Sanskrit": "sa",
    "Ancient Greek": "grc", "Greek": "el", "Hebrew": "he", "Arabic": "ar",
    "Spanish": "es", "Italian": "it", "Russian": "ru", "Persian": "fa",
}

# Ancient classical / proto source languages, ranked so the ESTIMATED origin is the
# deepest layer the etymology reaches, not the most recent hop. Coarse on purpose.
_CLASSICAL = {"sa", "grc", "la", "och", "hbo", "pi", "peo", "xpr", "sga", "got"}


def _ancientness(code: str) -> int:
    if code.endswith("-pro"):
        return 4                      # proto-languages (deepest reconstructable)
    if code in _CLASSICAL:
        return 3                      # attested classical/ancient
    if code in ("ltc", "ang", "enm", "fro", "goh", "gml", "ojp", "ltc", "MIcl"):
        return 2                      # medieval stages
    return 1                          # modern / unranked


async def trace(word: str, section_lang: str = "") -> dict:
    """Wiktionary word-keyed backbone (no-centre): from a word in ANY language,
    read its own Wiktionary entry and return
      - origin_chain: the sequence of source-language codes the etymology traces
        back through (inh/der/bor…), deepest = the ORIGIN (空→sa=Sanskrit),
      - sections: every language Wiktionary documents this word/graph in (breadth),
      - senses / descendants for the requested language section.
    en.wiktionary is used as the hub because it documents the word across ALL
    languages (a CJK char carries Chinese/Japanese/Korean/Vietnamese sections),
    which is exactly the breadth the portal must surface. section_lang picks which
    language's etymology/senses to foreground; empty = whole entry."""
    try:
        body, ts, cached = await cached_get_json(
            API.format(lang="en"),
            {"action": "parse", "page": word, "prop": "wikitext",
             "format": "json", "redirects": 1}, ttl=86400)
        wt = body.get("parse", {}).get("wikitext", {}).get("*", "")
        if not wt:
            return ok("wiktionary:trace", ts, cached,
                      {"word": word, "found": False, "sections": [],
                       "origin_chain": [], "senses": [], "descendants": [],
                       "url": f"https://en.wiktionary.org/wiki/{word}"})
        sections = re.findall(r"(?m)^==[ ]*([^=\n]+?)[ ]*==[ ]*$", wt)
        # narrow to the requested language section for etymology/senses if given
        seg, self_code = wt, ""
        if section_lang:
            m = re.search(r"(?m)^==[ ]*" + re.escape(section_lang)
                          + r"[ ]*==[ ]*$\n(.*?)(?=^==[ ]*[^=\n]+[ ]*==[ ]*$|\Z)",
                          wt, re.S)
            if m:
                seg = m.group(1)
            self_code = _SECTION_CODE.get(section_lang, "")
        # source-language codes AND the actual word-form at each step the etymology
        # reaches back through — so the chain shows real words (空 ← サンスクリット
        # शून्यता), not just language names. Excludes self-reference / undetermined.
        raw = re.findall(
            r"\{\{(?:inh|inh\+|der|der\+|bor|bor\+|lbor|slbor|calque|cal|clq)\|"
            r"[a-z][a-z0-9-]*\|([a-z][a-z0-9-]*)\|?([^|}\n]*)", seg)
        chain, forms, seen = [], {}, set()
        for c, form in raw:
            if c not in seen and c not in ("und", self_code):
                seen.add(c); chain.append(c)
                f = form.strip()
                if f and f not in ("-", "") and "=" not in f:  # skip named params (sort=…)
                    forms[c] = f
        # fallback form from a {{m|code|FORM}} / {{l|code|FORM}} mention (CJK etyms
        # often give the source form there rather than as a positional param)
        for c in chain:
            if c not in forms:
                mm = re.search(r"\{\{(?:m|l|mention|link)\|" + re.escape(c)
                               + r"\|([^|}\n=]+)", seg)
                if mm and mm.group(1).strip() not in ("-", ""):
                    forms[c] = mm.group(1).strip()
        senses = [ _ja_clean_generic(l.lstrip("# ").strip())
                   for l in seg.splitlines()
                   if l.startswith("#") and not l.startswith(("#*", "#:")) ][:6]
        senses = [s for s in senses if s]
        dsec = re.search(r"===+[ ]*Descendants[ ]*===+\n(.*?)(\n===|\n==[ ]|\Z)", seg, re.S)
        descendants = re.findall(r"\{\{(?:desc|desctree)\|([a-z][a-z0-9-]*)\|", dsec.group(1)) if dsec else []
        # ESTIMATED origin = the most ANCIENT source in the chain (proto > classical
        # > medieval > modern), not the last one in text order. Labelled 推定 by the
        # caller — a word with several etymologies (道: native michi vs Sino dō) can
        # not be reduced to one true origin, so we never assert; we show the whole
        # chain and flag the deepest source as a hypothesis (A3).
        origin = None
        if chain:
            best = max(chain, key=_ancientness)
            origin = {"code": best, "name": langname(best),
                      "tier": _ancientness(best), "multi": len(chain) > 2,
                      "native": False}
        elif self_code and re.search(r"(?i)===+[ ]*Etymology", seg):
            # no foreign source in the etymology → the word is NATIVE to this
            # language; its origin IS this language (疎外の Entfremdung=独語生え抜き,
            # 甘え=日本語生え抜き). This is not a failure — some concepts originate
            # in the input language itself, and the portal must say so, not blank.
            origin = {"code": self_code, "name": langname(self_code),
                      "tier": 1, "multi": False, "native": True}
        return ok("wiktionary:trace", ts, cached, {
            "word": word, "found": True, "url": f"https://en.wiktionary.org/wiki/{word}",
            "sections": sections,
            "origin_chain": [{"code": c, "name": langname(c), "form": forms.get(c, "")}
                             for c in chain],
            "origin_estimate": origin,
            "senses": senses,
            "descendants": sorted({c for c in descendants}),
        })
    except Exception as e:
        return err("wiktionary:trace", e)


def _ja_clean_generic(s: str) -> str:
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[|\]\]", "", s)
    s = re.sub(r"''+", "", s)
    return s.strip()


async def ja_senses(term: str) -> dict:
    """The broadly-shared, EVERYDAY Japanese senses of a word (kokugo-style), from
    ja.wiktionary — 疎外 → 『疎んじること。仲間外れにすること』. This is the general
    meaning a normal reader already lives with; it is NOT philosophy-only, and it
    itself holds threads worth pulling. Empty (honest) for purely technical words."""
    try:
        body, ts, cached = await cached_get_json(
            API.format(lang="ja"),
            {"action": "parse", "page": term, "prop": "wikitext",
             "format": "json", "redirects": 1}, ttl=86400)
        wt = body.get("parse", {}).get("wikitext", {}).get("*", "")
        senses = []
        for line in wt.splitlines():
            if line.startswith("#") and not line.startswith(("#*", "#:")):
                c = _ja_clean(line.lstrip("# ").strip())
                if c:
                    senses.append(c)
        data = {"term": term, "senses": senses, "found": bool(wt),
                "url": f"https://ja.wiktionary.org/wiki/{term}"}
        return ok("wiktionary:ja", ts, cached, data)
    except Exception as e:
        return err("wiktionary:ja", e)


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
