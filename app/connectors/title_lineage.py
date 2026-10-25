"""著作の題の系譜（原題 → 各国語の題 → 日本語の訳題）と、題の語ごとの対応（所有者 2026-10-25 承認）。

所有者の写し（10/25 21:34・言葉と物）: 「原語・翻訳語の対応」が、著作の題を一つの語として
「言葉／と／物」に分け、日本語の辞書義を並べていた。著作の題は、題の単位で

  1. 原題（言語・初版年・著者）→ 各国語の題 → 日本語の訳題（訳者・出版社・年）
  2. 訳の経路（原語から直接か、別の言語を経たか）は、書誌に書かれているときだけ
  3. 題の語ごとの対応（Les Mots ↔ 言葉、et ↔ と、les Choses ↔ 物）は、原語の Wiktionary の
     日本語訳で裏づけが取れたものだけ

を示す。語ごとの対応は、日本語の辞書ではなく原語の辞書（fr.wiktionary の mot → 言葉）から引く
＝日本語にする前の、原点に近い言語の情報構造を使う（所有者 10/25「翻訳される前の段階で、原点に近い
ものから情報を得る」）。各国語の題も、同じ原語の辞書の各言語への訳と照らして「逐語か、別の題か」を示す。

すべて鍵の要らない公開の情報源（Wikidata・各言語版 Wiktionary・国立国会図書館サーチ）。LLM は使わない。
"""
import re

from .base import cached_get_json, now
from . import ndl

WD_API = "https://www.wikidata.org/w/api.php"
WIKT_API = "https://{lang}.wiktionary.org/w/api.php"

# 各言語版 Wiktionary の、訳語の書き方（日本語や他言語への訳）
_TRANS_RE = {
    "fr": r"\{\{trad[+-]?\|{to}\|([^|}]+)",
    "de": r"\{\{Üt?\|{to}\|([^|}]+)",
    "en": r"\{\{t\+?\|{to}\|([^|}]+)",
}
# 題の中の、意味の中身を持たない語（冠詞・前置詞）。接続詞（et/und/and）は「と」に当たるので残す
_FUNCTION = {
    "fr": {"le", "la", "les", "l", "un", "une", "des", "de", "du", "d", "à", "au", "aux", "en", "sur", "pour", "par"},
    "de": {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "zu", "zur", "zum", "von", "vom", "im", "in"},
    "en": {"the", "a", "an", "of", "on", "in", "to", "for", "by"},
}
_LANG_NAME = {"fr": "フランス語", "de": "ドイツ語", "en": "英語", "it": "イタリア語", "es": "スペイン語",
              "ru": "ロシア語", "la": "ラテン語", "ja": "日本語", "zh": "中国語", "pt": "ポルトガル語", "nl": "オランダ語",
              "ko": "朝鮮語", "ar": "アラビア語", "fa": "ペルシア語", "he": "ヘブライ語", "tr": "トルコ語", "pl": "ポーランド語",
              "cs": "チェコ語", "sv": "スウェーデン語", "da": "デンマーク語", "no": "ノルウェー語", "nb": "ノルウェー語",
              "fi": "フィンランド語", "hu": "ハンガリー語", "ro": "ルーマニア語", "el": "ギリシャ語", "uk": "ウクライナ語",
              "ca": "カタルーニャ語", "eu": "バスク語", "gl": "ガリシア語", "af": "アフリカーンス語", "vi": "ベトナム語",
              "id": "インドネシア語", "th": "タイ語", "hi": "ヒンディー語", "bg": "ブルガリア語", "sr": "セルビア語",
              "hr": "クロアチア語", "sk": "スロバキア語", "sl": "スロベニア語", "et": "エストニア語", "lv": "ラトビア語",
              "lt": "リトアニア語", "hy": "アルメニア語", "ka": "ジョージア語", "az": "アゼルバイジャン語", "eo": "エスペラント"}


def _val(c):
    dv = ((c or {}).get("mainsnak") or {}).get("datavalue") or {}
    v = dv.get("value")
    return v


async def _entities(ids, props="labels|claims", languages="ja|en|fr|de"):
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    body, _, _ = await cached_get_json(WD_API, {"action": "wbgetentities", "ids": "|".join(ids[:50]),
                                                "props": props, "languages": languages, "format": "json"}, ttl=7 * 86400)
    return body.get("entities") or {}


def _label(e, langs=("ja", "en")):
    lab = (e or {}).get("labels") or {}
    for l in langs:
        if lab.get(l):
            return lab[l]["value"]
    return next((x["value"] for x in lab.values()), "")


async def _lang_code(qid):
    """言語の項目（Q150 など）→ Wikimedia の言語コード（fr）。Wikidata P424。"""
    e = (await _entities([qid], props="claims")).get(qid) or {}
    v = [_val(c) for c in ((e.get("claims") or {}).get("P424") or [])]
    return next((x for x in v if isinstance(x, str)), "")


async def _translations(word_lang, word, to_lang):
    """原語の Wiktionary で word の to_lang への訳語。見出しが無ければ単数形などを試す。(訳語, 見出し, url)"""
    pat = _TRANS_RE.get(word_lang)
    if not pat:
        return [], "", ""
    cands = [word]
    if word_lang in ("fr", "en") and len(word) > 3 and word[-1] in "sx":
        cands.append(word[:-1])
    if word_lang == "de":
        cands += [word[:-2]] if word.endswith(("en", "er")) else []
        cands += [word[:-1]] if word.endswith(("e", "n", "s")) else []
        cands += [w[:1].upper() + w[1:] for w in list(cands)]   # 名詞は大文字で始まる
    for c in dict.fromkeys(cands):
        try:
            d, _, _ = await cached_get_json(WIKT_API.format(lang=word_lang),
                                            {"action": "parse", "page": c, "prop": "wikitext", "redirects": 1,
                                             "format": "json"}, ttl=30 * 86400)
        except Exception:  # noqa: BLE001
            continue
        w = (((d.get("parse") or {}).get("wikitext") or {}).get("*")) or ""
        if not w:
            continue
        found = re.findall(pat.replace("{to}", re.escape(to_lang)), w)
        found = [re.sub(r"\[\[|\]\]", "", x).strip() for x in found]
        if found:
            return list(dict.fromkeys(found)), c, f"https://{word_lang}.wiktionary.org/wiki/{c}"
    return [], "", ""


def _tokens(title, lang):
    toks = [t for t in re.split(r"[\s'’:,;.!?«»\"()\-–—]+", title or "") if t]
    fn = _FUNCTION.get(lang, set())
    return [t for t in toks if t.lower() not in fn]


async def _align(orig_title, orig_lang, target_title, target_lang):
    """原題の語ごとに、原語の辞書の target_lang への訳語を引き、訳題に現れるかを見る。"""
    out = []
    low = (target_title or "").lower()
    for t in _tokens(orig_title, orig_lang)[:8]:
        tr, head, url = await _translations(orig_lang, t.lower() if orig_lang != "de" else t, target_lang)
        hit = next((x for x in sorted(tr, key=len, reverse=True) if x and x.lower() in low), "")
        if not hit and re.search(r"[\u3040-\u9FFF]", target_title or ""):
            # 日本語の訳語の送り仮名（純粋な・批判する）は、題では落ちる。漢字の部分で探す
            hit = next((x for x in tr if len(re.sub(r"[\u3040-\u309F]+$", "", x)) >= 1 and re.sub(r"[\u3040-\u309F]+$", "", x) in target_title
                        and re.sub(r"[\u3040-\u309F]+$", "", x) != x), "")
        if not hit and not re.search(r"[\u3040-\u9FFF]", target_title or ""):
            # ラテン文字などの題は語尾が変わる（parola → parole、cosa → cose）。語頭が同じ語を探す
            words = re.findall(r"\w+", low)
            hit = next((x for x in tr if len(x) >= 4 and any(w.startswith(x.lower()[:max(3, len(x) - 1)]) for w in words)), "")
        out.append({"orig": t, "lemma": head, "candidates": tr[:6], "matched": hit, "dict_url": url})
    return out


_ERA = {"明治": 1867, "大正": 1911, "昭和": 1925, "平成": 1988, "令和": 2018}


def _year(y):
    """書誌の年を西暦4桁に（１９３１・昭和23 などを揃える）。読めなければ元のまま。"""
    import unicodedata
    y = unicodedata.normalize("NFKC", y or "").strip()
    m = re.match(r"(明治|大正|昭和|平成|令和)\s*(\d+|元)", y)
    if m:
        return str(_ERA[m.group(1)] + (1 if m.group(2) == "元" else int(m.group(2))))
    m = re.match(r"(\d{4})", y)
    return m.group(1) if m else y


def _translators(ed, authors_ja):
    """国立国会図書館の書誌の作成者から、著者を除いた人（訳者）。"""
    surn = {a.split("・")[-1] for a in authors_ja if a}
    out = []
    for c in ed.get("creators") or []:
        name = re.sub(r",?\s*\d{4}-(\d{4})?$", "", c).strip()
        if not name or any(s and s in name for s in surn) or re.search(r"[A-Za-z]", name):
            continue
        # 著者の別表記（ハイデッカー・ハイデガー）は片仮名だけの名前で入るので、訳者に数えない
        if re.fullmatch(r"[\u30A0-\u30FF・＝=\s]+", name):
            continue
        out.append(name.replace(", ", ""))
    return out


async def lineage(qid: str, ja_title: str) -> dict:
    ents = await _entities([qid], props="labels|claims|sitelinks", languages="ja|en|fr|de")
    e = ents.get(qid) or {}
    cl = e.get("claims") or {}
    titles = [_val(c) for c in cl.get("P1476") or []]
    titles = [t for t in titles if isinstance(t, dict)]
    lang_q = next((v.get("id") for v in (_val(c) for c in cl.get("P407") or []) if isinstance(v, dict)), "")
    lang = (titles[0].get("language") if titles else "") or (await _lang_code(lang_q) if lang_q else "")
    orig_title = (titles[0].get("text") if titles else "") or (_label(e, (lang,)) if lang else "")
    year = next((str(v.get("time"))[1:5] for v in (_val(c) for c in cl.get("P577") or []) if isinstance(v, dict)), "")
    auth_q = [v.get("id") for v in (_val(c) for c in cl.get("P50") or []) if isinstance(v, dict)]
    auths = await _entities(auth_q)
    authors_ja = [_label(auths.get(q) or {}) for q in auth_q]
    ja = (ja_title or _label(e, ("ja",)) or "").split(" : ")[0].split("：")[0].strip()
    # 各国語の題（各言語版 Wikipedia の記事名＝その言語で流通している題）
    sl = e.get("sitelinks") or {}
    by_lang = []
    for k, v in sl.items():
        m = re.fullmatch(r"([a-z]{2,3})wiki", k)
        if m and m.group(1) not in ("ja", lang, "commons", "species"):
            by_lang.append({"lang": m.group(1), "lang_name": _LANG_NAME.get(m.group(1), m.group(1)), "title": v.get("title", "")})
    order = {"en": 0, "de": 1, "fr": 2, "it": 3, "es": 4, "ru": 5, "zh": 6}
    by_lang.sort(key=lambda x: (order.get(x["lang"], 99), x["lang"]))
    # 日本語の訳書（国立国会図書館サーチ）
    ja_eds, ndl_at, ndl_err = [], None, None
    if authors_ja and ja:
        r = await ndl.by_work(authors_ja[0], ja, limit=6)
        ndl_at, ndl_err = r.get("retrieved_at"), r.get("error")
        seen = set()
        for ed in ((r.get("data") or {}).get("editions") or []):
            key = (_year(ed.get("year", "")), ed.get("publisher", ""))
            if key in seen:
                continue
            seen.add(key)
            ja_eds.append({"title": ed.get("title", ""), "translators": _translators(ed, authors_ja),
                           "publisher": ed.get("publisher", ""), "year": _year(ed.get("year", "")), "url": ed.get("url", "")})
        ja_eds.sort(key=lambda x: x["year"] or "9999")
    # 訳の経路: 書誌の注記に原題・経由した言語が書かれているときだけ言う（今は NDL の OpenSearch の項目に注記が無い）
    route = {"known": False,
             "text": "原語から直接訳したのか、別の言語を経たのかは、今回取得した書誌（国立国会図書館サーチ）と Wikidata には書かれていません。"}
    # 語ごとの対応（原語の辞書から）: 日本語の題と、主要な各国語の題
    align_ja = await _align(orig_title, lang, ja, "ja") if (orig_title and lang in _TRANS_RE) else []
    others = []
    if orig_title and lang in _TRANS_RE:
        for x in by_lang[:4]:
            al = await _align(orig_title, lang, x["title"], x["lang"])
            if al:
                others.append({**x, "matched": sum(1 for a in al if a["matched"]), "total": len(al), "align": al})

    def _verdict(al):
        if not al:
            return ""
        n = sum(1 for a in al if a["matched"])
        return "逐語（原題の語がそろって現れる）" if n == len(al) else ("一部が逐語" if n else "別の題（原題の語が現れない）")
    return {
        "applies": True, "qid": qid, "queried_at": now(),
        "original": {"title": orig_title, "lang": lang, "lang_name": _LANG_NAME.get(lang, lang), "year": year,
                     "authors": authors_ja, "wikidata_url": f"https://www.wikidata.org/wiki/{qid}"},
        "ja_title": ja, "ja_editions": ja_eds, "ndl_retrieved_at": ndl_at, "ndl_error": ndl_err,
        "titles_by_lang": by_lang, "route": route,
        "align_ja": align_ja, "align_ja_verdict": _verdict(align_ja),
        "align_others": [{**o, "verdict": _verdict(o["align"])} for o in others],
        "align_source": f"{lang}.wiktionary（原語の辞書の訳語）" if lang in _TRANS_RE else "",
        "align_note": "" if lang in _TRANS_RE else f"原語（{_LANG_NAME.get(lang, lang or '不明')}）の辞書の訳語の書き方にまだ対応していないため、語ごとの対応は出していません。",
    }
