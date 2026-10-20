"""第1段「探求の経路」（所有者 2026-10-20 承認）のサーバ側。外部取得はすべて差し替える。

- 複合語の分け方（哲学草稿→哲学＋草稿、非有機的肉体→非＋有機的＋肉体）を辞書の見出しに接地させる
- 語義に CSS が漏れない（entgegenwirken）
- 動詞の語義からだけ着いた項目を、照合なしに概念として採らない（entgegenwirken→「取り消し」）
- つながりの根拠の文と、語の組の用例は、実在の文だけを出所つきで返す
"""
import asyncio

from app.connectors import etymology as ety
from app.connectors import langpivot as lp
from app.connectors import relation as rel

NONCONCEPT = frozenset()


def units(word, known):
    return [t for t, _ in ety._dp_units(word, known)]


def test_compound_split_uses_dictionary_headwords():
    assert units("哲学草稿", {"哲学", "草稿"}) == ["哲学", "草稿"]
    assert units("経済学哲学草稿", {"経済学", "経済", "哲学", "草稿"}) == ["経済学", "哲学", "草稿"]


def test_prefix_and_suffix_attach_the_way_a_reader_splits():
    # 非（接頭辞）＋有機的（有機＋的）＋肉体 ／ 存在論的（存在＋論＋的）＋差異
    assert units("非有機的肉体", {"有機", "肉体"}) == ["非", "有機的", "肉体"]
    assert units("存在論的差異", {"存在", "差異"}) == ["存在論的", "差異"]


def test_unknown_characters_stay_together_and_are_marked():
    out = ety._dp_units("哲学ほげふが", {"哲学"})
    assert out[0] == ("哲学", "lexical_unit")
    assert out[1] == ("ほげふが", "unresolved_unit")


def test_whole_headword_is_not_split(monkeypatch):
    async def titles(word):
        return {"弁証法", "弁証"}, "t", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    assert asyncio.run(ety.grounded_cjk_units("弁証法")) is None


def test_grounded_units_carry_source_url_and_time(monkeypatch):
    async def titles(word):
        return {"哲学", "草稿"}, "2026-10-20T00:00:00+00:00", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    u = asyncio.run(ety.grounded_cjk_units("哲学草稿"))
    assert [x["text"] for x in u] == ["哲学", "草稿"]
    assert all(x["source"] == "ja.wiktionary" and x["url"].startswith("https://ja.wiktionary.org/wiki/") for x in u)
    assert u[0]["retrieved_at"] == "2026-10-20T00:00:00+00:00"


def test_lookup_error_is_not_silent(monkeypatch):
    async def titles(word):
        return set(), None, "ConnectError"
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    # 見出しが取れなくても、境界辞書の分け方は残り、取れなかったことは記録される
    layers = asyncio.run(ety.semantic_layers_grounded("非有機的肉体"))
    sem = next(L for L in layers if L["level"] == "semantic")["units"]
    assert [x["text"] for x in sem] == ["非", "有機的", "肉体"]


def test_semantic_layer_is_replaced_only_when_weak(monkeypatch):
    async def titles(word):
        return {"哲学", "草稿"}, "t", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    layers = asyncio.run(ety.semantic_layers_grounded("哲学草稿"))
    sem = next(L for L in layers if L["level"] == "semantic")["units"]
    assert [x["text"] for x in sem] == ["哲学", "草稿"]
    assert all(x["role"] != "unresolved_unit" for x in sem)


def test_style_blocks_do_not_leak_into_glosses():
    html = ('to counteract or counter, <style data-mw-deduplicate="x">.mw-parser-output .object-usage-tag'
            '{font-style:italic}</style><span>[</span><i>with</i> dative<span>]</span>')
    g = lp._strip_html(html)
    assert "mw-parser-output" not in g and "{" not in g
    assert g.startswith("to counteract or counter")


def test_verb_only_gloss_is_not_taken_as_a_concept():
    defs = {"data": {"word": "entgegenwirken", "url": None, "candidates": [
        {"code": "de", "name_en": "German", "glosses": ["to counteract"],
         "en_lemmas": ["counteract"], "noun_lemmas": []}]}, "retrieved_at": "t", "error": None}

    async def resolve_en(lemma):
        return ["Q23090506"]

    async def no_labels(q, code):
        return []

    async def entity(qid):
        return {"labels": {"ja": {"value": "取り消し"}}, "aliases": {}, "claims": {}, "sitelinks": {"jawiki": {"title": "取り消し"}}}
    orig_l, orig_e = lp._label_search, lp.entity_raw
    lp._label_search, lp.entity_raw = no_labels, entity
    try:
        r = asyncio.run(lp.bridge("entgegenwirken", "ja", resolve_en, NONCONCEPT, defs=defs))
    finally:
        lp._label_search, lp.entity_raw = orig_l, orig_e
    assert not (r["data"].get("concept") or {}).get("qid")
    assert any("動詞" in (s.get("note") or "") for s in r["data"]["steps"])


def test_noun_gloss_still_reaches_its_concept():
    defs = {"data": {"word": "uhuru", "url": None, "candidates": [
        {"code": "sw", "name_en": "Swahili", "glosses": ["freedom"],
         "en_lemmas": ["freedom"], "noun_lemmas": ["freedom"]}]}, "retrieved_at": "t", "error": None}

    async def resolve_en(lemma):
        return ["Q2979"]

    async def no_labels(q, code):
        return []

    async def entity(qid):
        return {"labels": {"ja": {"value": "自由"}, "en": {"value": "freedom"}}, "aliases": {}, "claims": {},
                "sitelinks": {"jawiki": {"title": "自由"}}}

    async def no_measure(*a, **k):
        return []
    orig = (lp._label_search, lp.entity_raw, lp.retrieval_languages)
    lp._label_search, lp.entity_raw, lp.retrieval_languages = no_labels, entity, no_measure
    try:
        r = asyncio.run(lp.bridge("uhuru", "ja", resolve_en, NONCONCEPT, defs=defs))
    finally:
        lp._label_search, lp.entity_raw, lp.retrieval_languages = orig
    assert (r["data"].get("concept") or {}).get("qid") == "Q2979"


def test_name_forms_find_the_name_used_in_running_text():
    assert "ヘーゲル" in rel.name_forms("G.W.F. ヘーゲル")
    assert rel.name_forms("経済学・哲学草稿（1844年）")[0] == "経済学・哲学草稿"
    assert "Hegel" in rel.name_forms("Georg Wilhelm Friedrich Hegel")


def test_evidence_returns_only_sentences_that_contain_the_name(monkeypatch):
    texts = {
        "疎外": ("疎外", "疎外\nマルクスは、この疎外という用語をヘーゲルの『精神現象学』から継承した。別の文である。\nヘーゲル"),
        "G.W.F. ヘーゲル": (None, ""),
        "ヘーゲル": ("ヘーゲル", "ヘーゲルは疎外という問題を浮上させた。関係の無い文。"),
    }

    async def article_text(title, lang):
        t, body = texts.get(title, (None, ""))
        return t, body, "2026-10-20T00:00:00+00:00"
    monkeypatch.setattr(rel, "article_text", article_text)
    d = asyncio.run(rel.evidence("疎外", "G.W.F. ヘーゲル", "ja"))
    assert d["forward"]["sentences"] == ["マルクスは、この疎外という用語をヘーゲルの『精神現象学』から継承した。"]
    assert d["backward"]["article"] == "ヘーゲル"
    assert d["backward"]["sentences"] == ["ヘーゲルは疎外という問題を浮上させた。"]
    assert d["forward"]["retrieved_at"] and d["forward"]["url"].endswith("/疎外")


def test_pair_usage_keeps_only_snippets_with_both_words(monkeypatch):
    async def fake(url, params=None, **k):
        return {"query": {"searchinfo": {"totalhits": 23}, "search": [
            {"title": "Entfremdung", "snippet": 'Der <span class="searchmatch">Entfremdung</span> <span>entgegenwirken</span> würden'},
            {"title": "Sozialgesetzgebung", "snippet": "wollte dem entgegenwirken, nicht zuletzt"},
            {"title": "Lernort Natur", "snippet": "einer fortschreitenden Entfremdung des Menschen entgegenwirkt"}]}}, "t", False
    monkeypatch.setattr(rel, "cached_get_json", fake)
    d = asyncio.run(rel.pair_usage("Entfremdung", "entgegenwirken", "de"))
    assert [x["article"] for x in d["examples"]] == ["Entfremdung", "Lernort Natur"]
    assert d["total"] == 23 and "<span" not in d["examples"][0]["text"]
