"""言語の橋（language bridge）— 入力の言語と、検索に使う言語と、表示の言語を分ける。

なぜ在るか（2026-10-14 実測・所有者の指示）:
  /api/origin は入力語を「画面の言語の語」だと決めつけて、その言語の Wikipedia で
  記事名として引いていた。そのため画面が日本語のとき、
    uhuru（スワヒリ語・自由）→ UBURU／kalayaan（タガログ語）→ コンサートツアー名／
    tự do（ベトナム語）→ Tudou／vapaus（フィンランド語）→ ヴァーサ市／
    libereco（エスペラント）→ LibreOffice／dharma → DRAMATIC BASEBALL
  となり、ラテン文字以外の語（ነፃነት・स्वतंत्रता・자유・เสรีภาพ・حرية）は全て候補止まりだった
  （19語中、正しく概念へ着いたのは「自由」の1語だけ）。

所有者の指示の要点（逐語ではない。原文は会話ログ a9605082 turn 4）:
  ・どの言語で入れても、情報源が最も多く応える言語（英・独・仏・羅など）へ自動で渡して
    検索することは、機械的に当然に行う。
  ・どう変換され、どう展開したかを利用者に明示する。
  ・展開した先の語の意味が分からなければ困るので、利用者の言語へ戻れるようにする。
  ・「情報源を最も効果的に使うための言語の選択」と「集めた内容の表示」は別の問題である。

だからこの module は三つを別々の欄として返す。
  input      入力の言語の判定（根拠と、ほかの候補）
  retrieval  検索に使う言語（情報源の厚さを実測した順。固定の中心言語を置かない＝P1）
  display    表示の言語（利用者が読む言語。画面の言語の記事へ戻す）

層の宣言（公理3・P6）:
  入力の言語の判定は en.wiktionary の見出しに依る。辞書に無い語は判定しない（推測で埋めない）。
  概念の同定は「Wiktionary の英語の語義 → Wikidata」と「Wikidata のその言語のラベル」の
  二つの経路の一致で確かめる。一致しないときは『推定』と表示し、ほかの候補を残す。
  生成 LLM は使わない（D16・D36）。機械翻訳は外部リンクとしてだけ示し、未確認と書く。
"""
import asyncio
import re
import unicodedata
import urllib.parse

from .base import cached_get_json, err, now, ok

WIKT_DEF = "https://en.wiktionary.org/api/rest_v1/page/definition/{w}"
WIKT_JA = "https://ja.wiktionary.org/w/api.php"
WP_API = "https://{lang}.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

# 検索に使う言語の「候補の母集団」。順位はここでは決めない（下で実測したヒット数で決める）。
# 母集団を限るのは費用のためだけである（1言語につき1往復）。
# 出所: meta.wikimedia.org/wiki/List_of_Wikipedias（2026-10-14 取得）の記事数上位から、
# bot 生成が大半の版（ceb・war・arz・ce・tt）を除いたもの。哲学の原典言語として
# la・el を足す。入力の言語と画面の言語は、ここに無くても必ず測る。
RETRIEVAL_POOL = ("en", "de", "fr", "es", "ru", "it", "pl", "zh", "ja", "uk", "ar",
                  "vi", "pt", "fa", "ca", "id", "ko", "nl", "sv", "he", "tr", "la", "el")
MAX_MEASURED = 14

# Wikidata の P31 のうち、概念の意味になり得ないもの（曖昧さ回避・人名・作品など）。
# main.NONCONCEPT_P31 と同じ集合を呼び出し側から渡す（二重定義を避ける）。


def script_of(q: str) -> str:
    """最初の文字の Unicode 文字体系名（LATIN / CJK / HANGUL / ETHIOPIC …）。"""
    for ch in q or "":
        if ch.isalpha():
            try:
                name = unicodedata.name(ch)
            except ValueError:
                return "UNKNOWN"
            head = name.split()[0]
            return "CJK" if head in ("CJK",) else head
    return "UNKNOWN"


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _en_lemmas(html: str) -> list:
    """語義の HTML の中の、英語の見出しへのリンク（＝その語の英語での言い換え）。"""
    out = []
    for href in re.findall(r'href="/wiki/([^"#?]+)', html or ""):
        t = urllib.parse.unquote(href).replace("_", " ")
        if ":" in t or t in out:
            continue
        out.append(t)
    return out


FORM_OF = re.compile(r'class="[^"]*form-of-definition')
FORM_OF_TEXT = re.compile(
    r"\b(?:transcription|romanization|romanisation|plural|singular|participle|"
    r"inflection|spelling|abbreviation|form|indicative|imperative|genitive|"
    r"accusative|nominative|dative)\b[^.;]*\bof\b", re.I)


def parse_definitions(body: dict) -> list:
    """en.wiktionary の definition 応答 → 言語ごとの候補。

    応答は {言語コード: [品詞ごとの {language, partOfSpeech, definitions}]}。
    ISO コードの無い言語は "other" にまとめて来るので、言語名で分ける。"""
    by_key = {}
    for code, blocks in (body or {}).items():
        if not isinstance(blocks, list):
            continue
        for b in blocks:
            name = b.get("language") or code
            key = code if code != "other" else "other:" + name
            c = by_key.setdefault(key, {"code": code if code != "other" else None,
                                        "name_en": name, "glosses": [], "en_lemmas": [],
                                        "_noun": [], "_other": []})
            is_noun = (b.get("partOfSpeech") or "").lower() in ("noun", "proper noun")
            for d in b.get("definitions", [])[:4]:
                html = d.get("definition", "")
                g = _strip_html(html)
                if g and g not in c["glosses"]:
                    c["glosses"].append(g)
                # 語形の注記（plural of hak・Rōmaji transcription of はき）は意味ではない。
                # リンク先は別の語の見出しなので、英語の言い換えとして使わない。
                if FORM_OF.search(html) or FORM_OF_TEXT.search(g):
                    continue
                for lem in _en_lemmas(html):
                    bucket = c["_noun"] if is_noun else c["_other"]
                    if lem not in bucket:
                        bucket.append(lem)
    # 概念を探す道具なので、名詞の語義の言い換えを先に使う（αλήθεια の副詞の語義 "really" を
    # 先に引くと RSS に着いた・2026-10-14）。名詞が無ければほかの品詞の言い換えを使う。
    out = []
    for c in by_key.values():
        c["en_lemmas"] = list(dict.fromkeys(c.pop("_noun") + c.pop("_other")))
        out.append(c)
    return out


async def definitions(q: str) -> dict:
    """入力語の en.wiktionary 見出し（全言語の節）。無ければ小文字でもう一度引く。"""
    tried = []
    for w in dict.fromkeys([q.strip(), q.strip().lower()]):
        if not w:
            continue
        tried.append(w)
        try:
            body, ts, cached = await cached_get_json(
                WIKT_DEF.format(w=urllib.parse.quote(w, safe="")), ttl=86400)
            cands = parse_definitions(body)
            if cands:
                return ok("wiktionary:definition", ts, cached,
                          {"word": w, "candidates": cands,
                           "url": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(w)})
        except Exception as e:  # 404（見出し無し）も含む
            last = e
            continue
    if tried and "last" in locals() and "404" not in str(last):
        return err("wiktionary:definition", last)
    return ok("wiktionary:definition", now(), False,
              {"word": q, "candidates": [], "url": None})


def order_candidates(cands: list, ui_lang: str) -> list:
    """検討する順。画面の言語の節（言い換えを持つもの）→ 言い換えを持つ節 → 持たない節。
    同じ組の中は辞書の並び順。言い換えを持たない節（語形の注記だけの節）を先に検討しても、
    概念へは経路A（ラベル）でしか着けないため（haki の 6番目のスワヒリ語が検討から漏れた）。"""
    return sorted(cands, key=lambda c: (
        not (c.get("code") == ui_lang and c.get("en_lemmas")),
        not c.get("en_lemmas"), c.get("code") is None))


# 文字の種類だけで言語が一つに決まるもの（辞書に見出しが無いときの最後の手がかり）。
# 複数の言語が使う文字（ラテン・キリル・アラビア・デーヴァナーガリー・漢字）は入れない。
SCRIPT_LANG = {
    "HANGUL": ("ko", "Korean"), "THAI": ("th", "Thai"), "GEORGIAN": ("ka", "Georgian"),
    "ARMENIAN": ("hy", "Armenian"), "HEBREW": ("he", "Hebrew"), "GREEK": ("el", "Greek"),
    "KHMER": ("km", "Khmer"), "LAO": ("lo", "Lao"), "MYANMAR": ("my", "Burmese"),
    "SINHALA": ("si", "Sinhalese"), "TAMIL": ("ta", "Tamil"), "TELUGU": ("te", "Telugu"),
    "KANNADA": ("kn", "Kannada"), "MALAYALAM": ("ml", "Malayalam"),
    "GUJARATI": ("gu", "Gujarati"), "GURMUKHI": ("pa", "Punjabi"), "TIBETAN": ("bo", "Tibetan"),
    "HIRAGANA": ("ja", "Japanese"), "KATAKANA": ("ja", "Japanese"),
}


def script_candidates(q: str) -> list:
    """辞書に見出しが無い語でも、文字の種類で言語が決まれば、その言語の候補を1つ作る。
    語義は無いので、概念へは経路A（その言語のラベルの一致）でしか着かない。"""
    hit = SCRIPT_LANG.get(script_of(q))
    if not hit:
        return []
    return [{"code": hit[0], "name_en": hit[1], "glosses": [], "en_lemmas": [],
             "from_script": True}]


async def _label_search(q: str, code: str) -> list:
    """Wikidata で、その言語のラベル・別名が入力語と完全に一致する項目。"""
    try:
        body, _, _ = await cached_get_json(WD_API, {
            "action": "wbsearchentities", "search": q, "language": code,
            "strictlanguage": 1, "uselang": code, "type": "item",
            "limit": 10, "format": "json"}, ttl=86400)
    except Exception:
        return []
    out = []
    for h in body.get("search", []):
        m = (h.get("match") or {})
        if (m.get("text") or "").casefold() == q.casefold():
            out.append(h["id"])
    return out


async def entity_raw(qid: str) -> dict:
    body, ts, cached = await cached_get_json(ENTITY.format(qid=qid), ttl=86400)
    ent = body.get("entities", {}).get(qid, {})
    ent["_retrieved_at"] = ts
    return ent


def _p31(ent: dict) -> list:
    out = []
    for c in ent.get("claims", {}).get("P31", []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def label_matches(ent: dict, code: str, q: str) -> bool:
    """その項目の、その言語のラベルか別名が入力語と一致するか（同定の照合）。"""
    if not code:
        return False
    qq = q.strip().casefold()
    lab = ((ent.get("labels") or {}).get(code) or {}).get("value", "")
    if lab.casefold() == qq:
        return True
    return any((a.get("value") or "").casefold() == qq
               for a in (ent.get("aliases") or {}).get(code, []))


def choose(votes: dict, ents: dict, nonconcept: frozenset, q: str,
           ui_lang: str = "") -> list:
    """候補の項目を、根拠の強さで並べる。

    votes: qid → {"routes": set, "langs": set}
    照合（その言語のラベルが入力語と一致）＋2、経路ごとに＋1。
    曖昧さ回避・人名・作品などの項目は除く。"""
    scored = []
    for qid, v in votes.items():
        ent = ents.get(qid)
        if not ent or (set(_p31(ent)) & nonconcept):
            continue
        confirmed = sorted(c for c in v["langs"] if c and label_matches(ent, c, q))
        # 辞書の語義から着いた（gloss）＝その語が「意味する」もの。ラベルの一致（label）＝
        # その語で「呼ばれている」もの（Uhuru という名の人工衛星・公園）。前者を重く見る。
        score = (2 * ("gloss" in v["routes"]) + 1 * ("label" in v["routes"])
                 + 1 * bool(confirmed) + 0.5 * len(v.get("lemmas", ())))
        has_display = f"{ui_lang}wiki" in (ent.get("sitelinks") or {}) if ui_lang else False
        scored.append({"qid": qid, "score": score, "confirmed_in": confirmed,
                       "routes": sorted(v["routes"]), "has_display": has_display})
    # 同点なら、利用者の言語の記事が在る項目（表示へ戻せる項目）を先にする
    scored.sort(key=lambda s: (-s["score"], not s["has_display"]))
    return scored


async def _measure(code: str, term: str) -> dict:
    """その言語の Wikipedia で、その語が何本の記事に現れるか（ヒット数）と記事の長さ。"""
    search_term = re.sub(r"\s*\([^)]*\)\s*$", "", term).strip() or term
    srsearch = f'"{search_term}"' if " " in search_term else search_term
    try:
        body, ts, cached = await cached_get_json(WP_API.format(lang=code), {
            "action": "query", "list": "search", "srsearch": srsearch, "srlimit": 1,
            "srinfo": "totalhits", "srprop": "", "prop": "info", "titles": term,
            "format": "json"}, ttl=604800)
        hits = (body.get("query", {}).get("searchinfo") or {}).get("totalhits")
        page = next(iter((body.get("query", {}).get("pages") or {}).values()), {})
        return {"hits": hits, "bytes": page.get("length"), "retrieved_at": ts,
                "search_term": search_term, "error": None}
    except Exception as e:
        return {"hits": None, "bytes": None, "retrieved_at": now(),
                "search_term": search_term, "error": f"{type(e).__name__}: {e}"}


async def retrieval_languages(ent: dict, input_code: str | None, ui_lang: str) -> list:
    """検索に使う言語を、その概念について実測したヒット数の多い順に並べる。

    中心言語を固定しない（P1）。母集団は RETRIEVAL_POOL＋入力の言語＋画面の言語のうち、
    その概念の記事が実在する言語。順位は測った値だけで決める。"""
    sitelinks = ent.get("sitelinks") or {}
    labels = ent.get("labels") or {}
    pool = list(dict.fromkeys([c for c in (input_code, ui_lang) if c] + list(RETRIEVAL_POOL)))
    langs = [c for c in pool if f"{c}wiki" in sitelinks][:MAX_MEASURED]
    rows = await asyncio.gather(*[
        _measure(c, sitelinks[f"{c}wiki"]["title"]) for c in langs])
    out = []
    for c, m in zip(langs, rows):
        title = sitelinks[f"{c}wiki"]["title"]
        out.append({
            "lang": c, "term": (labels.get(c) or {}).get("value") or title,
            "article_title": title,
            "article_url": f"https://{c}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "wiktionary_url": "https://en.wiktionary.org/wiki/" + urllib.parse.quote(
                (labels.get(c) or {}).get("value") or title),
            **m})
    out.sort(key=lambda r: -(r["hits"] or -1))
    return out


async def bridge(q: str, ui_lang: str, resolve_en, nonconcept: frozenset,
                 defs: dict | None = None, max_langs: int = 5,
                 force_qid: str = "") -> dict:
    """入力語 → 入力の言語の判定 → 概念（Wikidata）→ 検索に使う言語・表示の言語。

    resolve_en(lemma) -> qid|None は呼び出し側（main._resolve_entity を使う）から渡す。"""
    started = now()
    defs = defs or await definitions(q)
    cands = order_candidates((defs.get("data") or {}).get("candidates") or [], ui_lang) \
        or script_candidates(q)
    data = {"input": q, "script": script_of(q), "queried_at": started,
            "dictionary": {"source": "en.wiktionary", "url": (defs.get("data") or {}).get("url"),
                           "retrieved_at": defs.get("retrieved_at"), "error": defs.get("error")},
            "input_candidates": [{"code": c["code"], "name_en": c["name_en"],
                                  "glosses": c["glosses"][:3], "en_lemmas": c["en_lemmas"][:4]}
                                 for c in cands[:8]],
            "identified": None, "concept": None, "alternatives": [],
            "retrieval": [], "display": None, "steps": []}

    votes = {}
    if not cands and not force_qid:
        data["steps"].append({"step": "dictionary", "ok": False,
                              "note": "en.wiktionary にこの語の見出しが無いため、入力の言語を判定していない"})
        return ok("langpivot", started, False, data)
    if force_qid:
        # 画面が既に辿った項目がある（入力語そのもので記事に着いた語）。同定はやり直さず、
        # その項目について検索に使う言語と表示の言語だけを求める（画面と食い違わせない）。
        try:
            ent = await entity_raw(force_qid)
        except Exception as e:
            return err("langpivot", e)
        work = cands[:max_langs]
        best = {"qid": force_qid, "routes": ["page"],
                "confirmed_in": [c["code"] for c in work if c["code"] and label_matches(ent, c["code"], q)]}
        if not cands:
            data["concept"] = {"qid": force_qid, "url": f"https://www.wikidata.org/wiki/{force_qid}",
                               "label_ui": ((ent.get("labels") or {}).get(ui_lang) or {}).get("value"),
                               "routes": ["page"], "confirmed_in": [],
                               "retrieved_at": ent.get("_retrieved_at")}
            data["retrieval"] = await retrieval_languages(ent, None, ui_lang)
            return ok("langpivot", started, False, data)
        return await _finish(data, q, ui_lang, cands, work, best, ent, {force_qid: ent}, [],
                             {force_qid: {"langs": set(c["code"] for c in work if c["code"])}}, started)

    def vote(qid, route, code, lemma=None):
        v = votes.setdefault(qid, {"routes": set(), "langs": set(), "lemmas": set()})
        v["routes"].add(route)
        v["langs"].add(code)
        if lemma:
            v["lemmas"].add(lemma)

    work = cands[:max_langs]
    # 経路A: その言語のラベルが入力語と一致する項目（言語コードが在る候補だけ）
    a_res = await asyncio.gather(*[_label_search(q, c["code"]) if c["code"] else asyncio.sleep(0, [])
                                   for c in work])
    for c, qids in zip(work, a_res):
        for qid in qids[:5]:
            vote(qid, "label", c["code"])
    # 経路B: 辞書の英語の語義 → Wikidata（同じ英語の語は一度だけ解決する）
    lemma_of = {}
    for c in work:
        # 英語の節の語義は「訳語」ではなく「説明文」である（freedom = "The state of being free"）。
        # 説明文の中の語（free）を引くと別物（ロックバンド Free）に着く。英語の語はその語自身で引く。
        lems = [q.strip()] if c["code"] == "en" else c["en_lemmas"][:2]
        for lem in lems:
            lemma_of.setdefault(lem, []).append(c["code"])
    resolved = await asyncio.gather(*[resolve_en(lem) for lem in lemma_of])
    for lem, qids in zip(lemma_of, resolved):
        for qid in ([qids] if isinstance(qids, str) else (qids or [])):
            for code in lemma_of[lem]:
                vote(qid, "gloss", code, lem)

    top = sorted(votes, key=lambda k: -(2 * ("gloss" in votes[k]["routes"]) + len(votes[k]["routes"])
                                       + len(votes[k]["lemmas"])))[:8]
    fetched = await asyncio.gather(*[entity_raw(k) for k in top], return_exceptions=True)
    ents = {k: e for k, e in zip(top, fetched) if isinstance(e, dict)}
    ranked = choose({k: votes[k] for k in ents}, ents, nonconcept, q, ui_lang)
    if not ranked:
        data["steps"].append({"step": "concept", "ok": False,
                              "note": "辞書の語義からも、その言語のラベルからも、概念の項目に着かなかった"})
        return ok("langpivot", started, False, data)

    best = ranked[0]
    return await _finish(data, q, ui_lang, cands, work, best, ents[best["qid"]], ents, ranked,
                         votes, started)


async def _finish(data, q, ui_lang, cands, work, best, ent, ents, ranked, votes, started):
    # 入力の言語: 照合できた言語 → 票を入れた言語 → 辞書の先頭、の順で決める
    vlangs = [c for c in (best["confirmed_in"] or sorted(c for c in votes[best["qid"]]["langs"] if c))]
    ident_code = vlangs[0] if vlangs else work[0]["code"]
    ident = next((c for c in cands if c["code"] == ident_code), work[0])
    labels = ent.get("labels") or {}
    sitelinks = ent.get("sitelinks") or {}
    ui_title = (sitelinks.get(f"{ui_lang}wiki") or {}).get("title")
    data["identified"] = {"code": ident["code"], "name_en": ident["name_en"],
                          "confirmed": bool(best["confirmed_in"]),
                          "basis": ("Wikidata のこの言語のラベルが入力語と一致"
                                    if best["confirmed_in"] else
                                    "辞書の見出しと語義による推定（ラベルでは照合できていない）"),
                          "same_as_ui": ident["code"] == ui_lang}
    data["concept"] = {
        "qid": best["qid"], "url": f"https://www.wikidata.org/wiki/{best['qid']}",
        "label_ui": (labels.get(ui_lang) or labels.get("en") or {}).get("value"),
        "label_input": (labels.get(ident["code"] or "") or {}).get("value"),
        "description_ui": ((ent.get("descriptions") or {}).get(ui_lang)
                           or (ent.get("descriptions") or {}).get("en") or {}).get("value"),
        "routes": best["routes"], "confirmed_in": best["confirmed_in"],
        "retrieved_at": ent.get("_retrieved_at")}
    data["alternatives"] = [
        {"qid": r["qid"], "label_ui": ((ents[r["qid"]].get("labels") or {}).get(ui_lang)
                                       or (ents[r["qid"]].get("labels") or {}).get("en") or {}).get("value"),
         "ui_title": ((ents[r["qid"]].get("sitelinks") or {}).get(f"{ui_lang}wiki") or {}).get("title"),
         "routes": r["routes"], "confirmed_in": r["confirmed_in"]}
        for r in ranked[1:4]]
    data["retrieval"] = await retrieval_languages(ent, ident["code"], ui_lang)
    data["display"] = {"lang": ui_lang, "title": ui_title,
                       "url": (f"https://{ui_lang}.wikipedia.org/wiki/"
                               + urllib.parse.quote(ui_title.replace(" ", "_"))) if ui_title else None,
                       "input_lang_article": (sitelinks.get(f"{ident['code']}wiki") or {}).get("title")
                       if ident["code"] else None}
    data["steps"] = [
        {"step": "dictionary", "ok": True,
         "note": f"en.wiktionary の見出しで入力の言語を {ident['name_en']} と判定"},
        {"step": "concept", "ok": True,
         "note": f"Wikidata {best['qid']} に同定（経路: {'・'.join(best['routes'])}）"},
        {"step": "retrieval", "ok": bool(data["retrieval"]),
         "note": "その概念の記事を持つ言語ごとに、Wikipedia のヒット数を実測して並べた"},
        {"step": "display", "ok": bool(ui_title),
         "note": (f"画面の言語（{ui_lang}）の記事「{ui_title}」へ戻して表示する"
                  if ui_title else f"画面の言語（{ui_lang}）の記事がこの概念には無い")}]
    return ok("langpivot", started, False, data)


def needs_bridge(defs: dict, node: dict, ui_lang: str) -> bool:
    """既存の経路（画面の言語の記事名で引く）を使わず、橋を渡すべきか。

    画面の言語の記事に、入力語そのもので着いており、曖昧さ回避でもないときは渡さない
    （今まで正しく着いていた語を変えない）。それ以外で、辞書に見出しが在るときに渡す。"""
    word = (defs.get("data") or {}).get("word", "")
    cands = (defs.get("data") or {}).get("candidates") or script_candidates(word)
    if not cands:
        return False
    nd = node or {}
    exact = bool(nd.get("found") and nd.get("qid")
                 and not nd.get("resolved_from") and not nd.get("disambiguation"))
    if not exact:
        return True
    # 記事名は一致したが、辞書がその語を画面の言語の語として載せていない
    # （Freiheit が日本語版では同名のバンドの記事に着いた実例）。
    # ただし漢字・仮名の語は en.wiktionary に日本語の節が無いことが多いので、
    # 画面が日本語のときは既存の解決を保つ。
    if any(c.get("code") == ui_lang for c in cands):
        return False
    return not (ui_lang == "ja" and script_of(word) in ("CJK", "HIRAGANA", "KATAKANA"))


def _ja_section_glosses(wikitext: str, code: str) -> list:
    """ja.wiktionary の、その言語の節の語義行（# で始まる行）。"""
    m = re.search(r"(?m)^==\s*\{\{(?:L\|)?" + re.escape(code) + r"\}\}\s*==\s*$", wikitext or "")
    if not m:
        return []
    rest = wikitext[m.end():]
    nxt = re.search(r"(?m)^==[^=]", rest)
    seg = rest[:nxt.start()] if nxt else rest
    out = []
    for line in re.findall(r"(?m)^#(?![:*])\s*(.+)$", seg):
        s = line
        for _ in range(4):   # 入れ子の template（{{q|...{{...}}...}}）を内側から外す
            s2 = re.sub(r"\{\{[^{}]*\}\}", "", s)
            if s2 == s:
                break
            s = s2
        s = re.sub(r"\{\{|\}\}", "", s)
        s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s).strip(" 　。")
        if s and s not in out:
            out.append(s)
    return out[:4]


async def back_gloss(term: str, src: str, ui_lang: str) -> dict:
    """展開した先の語を、利用者の言語へ戻す（辞書の語義）。

    画面が日本語なら ja.wiktionary のその言語の節を先に読む。無ければ en.wiktionary の
    英語の語義を返し、その旨を書く。機械翻訳は外部リンクだけを返す（未確認）。"""
    started = now()
    out = {"term": term, "src": src, "ui": ui_lang, "glosses": [], "gloss_lang": None,
           "dictionary_url": None, "machine_translation_url":
               "https://translate.google.com/?" + urllib.parse.urlencode(
                   {"sl": src or "auto", "tl": ui_lang, "text": term, "op": "translate"}),
           "note": ""}
    if ui_lang == "ja" and src:
        try:
            body, ts, _ = await cached_get_json(WIKT_JA, {
                "action": "parse", "page": term, "prop": "wikitext",
                "format": "json", "redirects": 1}, ttl=86400)
            wt = (body.get("parse") or {}).get("wikitext", {}).get("*", "")
            g = _ja_section_glosses(wt, src)
            if g:
                out.update(glosses=g, gloss_lang="ja", retrieved_at=ts,
                           dictionary_url="https://ja.wiktionary.org/wiki/" + urllib.parse.quote(term))
                return ok("backgloss", ts, False, out)
        except Exception:
            pass
    d = await definitions(term)
    for c in (d.get("data") or {}).get("candidates") or []:
        if c.get("code") == src or (not src and c.get("glosses")):
            out.update(glosses=c["glosses"][:3], gloss_lang="en",
                       dictionary_url=(d.get("data") or {}).get("url"),
                       retrieved_at=d.get("retrieved_at"))
            if ui_lang != "en":
                out["note"] = "画面の言語の辞書にこの語の項が無いため、英語の語義を示す"
            return ok("backgloss", d.get("retrieved_at") or started, False, out)
    out["note"] = "辞書にこの語の語義が見つからなかった。機械翻訳のリンクだけを示す（未確認）"
    return ok("backgloss", started, False, out)
