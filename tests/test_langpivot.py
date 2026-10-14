"""言語の橋（app/connectors/langpivot.py）の Level 0 試験。ネットワークを使わない。

守ること（2026-10-14 の実測から）:
  1. 語形の注記（Rōmaji transcription of はき・plural of hak）を英語の言い換えに使わない。
     使うと haki（スワヒリ語・正義）が「ローマ字」に着いた。
  2. 辞書の語義から着いた項目（＝その語が意味するもの）を、ラベルが一致しただけの項目
     （＝その名で呼ばれているもの・Uhuru という人工衛星）より重く見る。
  3. 画面の言語の記事に入力語そのもので着いた語（疎外・自由）は、橋を渡さない（既存の解決を保つ）。
  4. 記事名は一致しても、辞書がその語を画面の言語の語として載せていなければ橋を渡す
     （Freiheit が日本語版では同名のバンドの記事に着いた実例）。
"""
from app.connectors import langpivot as lp

NONCONCEPT = frozenset({"Q4167410", "Q215380"})


def _defs(cands, word="w"):
    return {"data": {"word": word, "candidates": cands}}


def test_form_of_definitions_do_not_become_pivots():
    body = {
        "ja": [{"language": "Japanese", "partOfSpeech": "Romanization", "definitions": [
            {"definition": '<a rel="mw:WikiLink" href="/wiki/R%C5%8Dmaji">Rōmaji</a> transcription of '
                           '<a href="/wiki/%E3%81%AF%E3%81%8D">はき</a>'}]}],
        "pl": [{"language": "Polish", "partOfSpeech": "Noun", "definitions": [
            {"definition": '<span class="form-of-definition">nominative plural of '
                           '<a href="/wiki/hak#Polish">hak</a></span>'}]}],
        "sw": [{"language": "Swahili", "partOfSpeech": "Noun", "definitions": [
            {"definition": '<a href="/wiki/right">right</a>; <a href="/wiki/justice">justice</a>'}]}],
    }
    by = {c["code"]: c for c in lp.parse_definitions(body)}
    assert by["ja"]["en_lemmas"] == []
    assert by["pl"]["en_lemmas"] == []
    assert by["sw"]["en_lemmas"] == ["right", "justice"]
    assert by["ja"]["glosses"]  # 語義の文そのものは表示用に残す


def test_other_languages_are_kept_apart_by_name():
    body = {"other": [
        {"language": "Maore Comorian", "definitions": [{"definition": '<a href="/wiki/independence">independence</a>'}]},
        {"language": "Yanomam", "definitions": [{"definition": '<a href="/wiki/child">child</a>'}]}]}
    cands = lp.parse_definitions(body)
    assert {c["name_en"] for c in cands} == {"Maore Comorian", "Yanomam"}
    assert all(c["code"] is None for c in cands)


def _ent(labels=None, p31=(), sitelinks=()):
    return {"labels": {k: {"value": v} for k, v in (labels or {}).items()},
            "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": x}}}} for x in p31]},
            "sitelinks": {f"{s}wiki": {"title": s} for s in sitelinks}}


def test_meaning_outweighs_a_mere_name_match():
    votes = {
        "Q580043": {"routes": {"label"}, "langs": {"en", "sw"}, "lemmas": set()},      # 人工衛星 Uhuru
        "Q2979": {"routes": {"gloss"}, "langs": {"en", "sw"}, "lemmas": {"freedom"}},  # 自由
    }
    ents = {"Q580043": _ent({"en": "Uhuru", "sw": "Uhuru"}, sitelinks=("ja",)),
            "Q2979": _ent({"en": "liberty", "ja": "自由"}, sitelinks=("ja",))}
    ranked = lp.choose(votes, ents, NONCONCEPT, "uhuru", "ja")
    assert ranked[0]["qid"] == "Q2979"


def test_both_routes_with_label_match_is_strongest():
    votes = {
        "Q1": {"routes": {"gloss", "label"}, "langs": {"tl"}, "lemmas": {"freedom"}},
        "Q2": {"routes": {"gloss"}, "langs": {"tl"}, "lemmas": {"freedom", "liberty"}},
    }
    ents = {"Q1": _ent({"tl": "kalayaan"}), "Q2": _ent({"en": "freedom"})}
    ranked = lp.choose(votes, ents, NONCONCEPT, "kalayaan", "ja")
    assert ranked[0]["qid"] == "Q1"
    assert ranked[0]["confirmed_in"] == ["tl"]


def test_nonconcept_items_are_dropped():
    votes = {"Q9": {"routes": {"gloss", "label"}, "langs": {"de"}, "lemmas": {"freedom"}}}
    ents = {"Q9": _ent({"de": "Freiheit"}, p31=("Q215380",))}   # musical group
    assert lp.choose(votes, ents, NONCONCEPT, "Freiheit", "ja") == []


def test_tie_prefers_an_item_that_can_return_to_the_users_language():
    votes = {"QA": {"routes": {"gloss"}, "langs": {"en"}, "lemmas": {"freedom"}},
             "QB": {"routes": {"gloss"}, "langs": {"en"}, "lemmas": {"freedom"}}}
    ents = {"QA": _ent({"en": "free will"}), "QB": _ent({"en": "liberty"}, sitelinks=("ja",))}
    assert lp.choose(votes, ents, NONCONCEPT, "freedom", "ja")[0]["qid"] == "QB"


def test_label_matches_uses_label_or_alias_casefolded():
    ent = _ent({"sw": "Uhuru"})
    ent["aliases"] = {"fi": [{"value": "Vapaus"}]}
    assert lp.label_matches(ent, "sw", "uhuru")
    assert lp.label_matches(ent, "fi", "vapaus")
    assert not lp.label_matches(ent, "de", "uhuru")
    assert not lp.label_matches(ent, None, "uhuru")


def test_exact_article_in_ui_language_keeps_existing_resolution():
    node = {"found": True, "qid": "Q2979", "resolved_from": None, "disambiguation": False}
    assert not lp.needs_bridge(_defs([{"code": "ja"}, {"code": "zh"}], "自由"), node, "ja")
    # 漢字の語は en.wiktionary に日本語の節が無くても、日本語の画面では既存の解決を保つ
    assert not lp.needs_bridge(_defs([{"code": "zh"}], "疎外"), node, "ja")


def test_bridge_when_the_ui_article_is_a_drift_or_disambiguation():
    drift = {"found": True, "qid": "Q11251775", "resolved_from": "uhuru", "disambiguation": False}
    disamb = {"found": True, "qid": "Q1622727", "resolved_from": None, "disambiguation": True}
    missing = {"found": False}
    d = _defs([{"code": "sw"}, {"code": "en"}], "uhuru")
    assert lp.needs_bridge(d, drift, "ja")
    assert lp.needs_bridge(d, disamb, "ja")
    assert lp.needs_bridge(d, missing, "ja")


def test_bridge_when_dictionary_says_the_word_is_not_in_the_ui_language():
    band = {"found": True, "qid": "Q37563136", "resolved_from": None, "disambiguation": False}
    assert lp.needs_bridge(_defs([{"code": "de"}], "Freiheit"), band, "ja")


def test_no_dictionary_entry_means_no_bridge():
    assert not lp.needs_bridge(_defs([], "人間関係がモノのようになる"), {"found": False}, "ja")


def test_script_of():
    assert lp.script_of("ነፃነት") == "ETHIOPIC"
    assert lp.script_of("자유") == "HANGUL"
    assert lp.script_of("自由") == "CJK"
    assert lp.script_of("tự do") == "LATIN"
    assert lp.script_of("") == "UNKNOWN"


def test_ja_wiktionary_section_glosses():
    wt = ("=={{fr}}==\n==={{noun}}===\n# [[自由]]、[[解放]]。\n"
          "=={{L|la}}==\n==={{noun}}===\n#[[自由]]。\n#{{context|legal|lang=la}}[[自由権]]。\n#: 用例\n")
    assert lp._ja_section_glosses(wt, "fr") == ["自由、解放"]
    assert lp._ja_section_glosses(wt, "la") == ["自由", "自由権"]
    assert lp._ja_section_glosses(wt, "de") == []


def test_english_word_is_resolved_by_itself_not_by_words_in_its_definition():
    """freedom の語義 "The state of being free" の free を引くと、ロックバンド Free に着いた（2026-10-14）。"""
    import asyncio
    seen = []

    async def resolve_en(lemma):
        seen.append(lemma)
        return []

    defs = {"data": {"word": "freedom", "url": None, "candidates": [
        {"code": "en", "name_en": "English", "glosses": ["The state of being free."],
         "en_lemmas": ["free", "lack"]}]}, "retrieved_at": "t", "error": None}

    async def no_labels(q, code):
        return []
    orig = lp._label_search
    lp._label_search = no_labels
    try:
        asyncio.run(lp.bridge("freedom", "ja", resolve_en, NONCONCEPT, defs=defs))
    finally:
        lp._label_search = orig
    assert seen == ["freedom"]


def test_ja_wiktionary_nested_templates_are_removed():
    wt = "=={{zh}}==\n# {{q|{{lb|zh|文語}}}}に[[自由]]である\n"
    assert lp._ja_section_glosses(wt, "zh") == ["に自由である"]


def test_noun_senses_are_used_before_other_parts_of_speech():
    """αλήθεια の副詞の語義 really を先に引くと RSS に着いた（2026-10-14）。"""
    body = {"el": [
        {"language": "Greek", "partOfSpeech": "Adverb", "definitions": [{"definition": '<a href="/wiki/really">really</a>'}]},
        {"language": "Greek", "partOfSpeech": "Noun", "definitions": [{"definition": '<a href="/wiki/truth">truth</a>'}]}]}
    assert lp.parse_definitions(body)[0]["en_lemmas"][:2] == ["truth", "really"]


def test_candidates_with_paraphrases_are_examined_first():
    """haki: 語形の注記だけの節（ja・fi・pl）が先に並び、6番目のスワヒリ語が検討から漏れた。"""
    cands = [{"code": "ja", "en_lemmas": []}, {"code": "fi", "en_lemmas": []},
             {"code": "pl", "en_lemmas": []}, {"code": "sw", "en_lemmas": ["right"]},
             {"code": None, "en_lemmas": ["flag"]}]
    order = [c["code"] for c in lp.order_candidates(cands, "ja")]
    assert order.index("sw") < order.index("ja")
    assert order[-1] is None or order.index(None) > order.index("sw")
    # 画面の言語の節が言い換えを持つときは、その節を先頭に置く（既存の解決を保つ）
    cands2 = [{"code": "en", "en_lemmas": ["x"]}, {"code": "ja", "en_lemmas": ["freedom"]}]
    assert lp.order_candidates(cands2, "ja")[0]["code"] == "ja"


def test_script_alone_gives_a_candidate_only_when_the_script_is_unique():
    assert lp.script_candidates("아름다움")[0]["code"] == "ko"
    assert lp.script_candidates("เสรีภาพ")[0]["code"] == "th"
    assert lp.script_candidates("Freiheit") == []      # ラテン文字は多くの言語が使う
    assert lp.script_candidates("حرية") == []          # アラビア文字も同じ
    assert lp.script_candidates("自由") == []          # 漢字も同じ


def test_no_dictionary_entry_but_unique_script_still_bridges():
    assert lp.needs_bridge(_defs([], "아름다움"), {"found": False}, "ja")
