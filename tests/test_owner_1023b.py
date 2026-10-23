"""所有者の写し（2026-10-23 17:27〜17:34）から。外部取得はすべて差し替える。

- 実存 → カントの関係で根拠の文が0件だった。実存主義の記事の本文にカントは出てこず、
  記事の横の案内枠（哲学のサイドバー）のリンクから地図に入っていた。消さずに「本文に無い」印を付ける
- ライプニッツの記法 を「ライプニッツの＋記法」に分けていた（助詞を前の語に付けたまま）
- 冒頭の「英: Leibniz's notation」を空白で切り、Leibniz's を英語の原語にしていた
"""
import asyncio

from app.connectors import concept
from app.connectors import etymology as ety


def test_particle_no_is_split_out(monkeypatch):
    async def titles(word):
        return {"記法"}, "t", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    u = asyncio.run(ety.grounded_cjk_units("ライプニッツの記法"))
    assert [(x["text"], x["role"]) for x in u] == [("ライプニッツ", "unresolved_unit"), ("の", "particle"), ("記法", "lexical_unit")]


def test_no_inside_a_hiragana_word_is_kept():
    assert ety._NO_PARTICLE.split("もののけ") == ["もののけ"]
    assert ety._NO_PARTICLE.split("存在のありか") == ["存在のありか"]   # 後ろがひらがなの時は分けない
    assert ety._NO_PARTICLE.split("存在の問い") == ["存在", "の", "問い"]


def test_lead_original_term_keeps_the_whole_phrase():
    t = "ライプニッツの記法（ライプニッツのきほう, 英: Leibniz's notation）とは, 数学における"
    assert concept._LEAD_ABBREV_RE.findall(t) == [("英", "Leibniz's notation")]
    assert concept._LEAD_ABBREV_RE.findall("疎外（独: Entfremdung、英: alienation）") == [("独", "Entfremdung"), ("英", "alienation")]


def test_body_links_exclude_template_links(monkeypatch):
    wt = "{{哲学のサイドバー|list=[[イマヌエル・カント]]}}本文で[[キルケゴール]]と[[ジャン＝ポール・サルトル|サルトル]]に触れる。{{see also|新カント派}}"
    async def fake(url, params, ttl=0):
        return {"parse": {"wikitext": {"*": wt}}}, "t", False
    monkeypatch.setattr(concept, "cached_get_json", fake)
    b = asyncio.run(concept._body_link_titles("実存主義", "ja"))
    assert b == {"キルケゴール", "ジャン＝ポール・サルトル"}


def test_persons_get_in_body_flag_through_redirects(monkeypatch):
    wt = "{{哲学のサイドバー|[[イマヌエル・カント]]}}本文の[[キルケゴール]]。"
    async def fake(url, params, ttl=0):
        if params.get("prop") == "links":
            return {"query": {"pages": {"1": {"links": [{"title": "イマヌエル・カント"}, {"title": "キルケゴール"}]}}}}, "t", False
        if params.get("action") == "parse":
            return {"parse": {"wikitext": {"*": wt}}}, "t", False
        if params.get("prop") == "pageprops":
            return {"query": {"redirects": [{"from": "キルケゴール", "to": "セーレン・キェルケゴール"}],
                              "pages": {"a": {"title": "イマヌエル・カント", "pageprops": {"wikibase_item": "Q9312"}},
                                        "b": {"title": "セーレン・キェルケゴール", "pageprops": {"wikibase_item": "Q6512"}}}}}, "t", False
        raise AssertionError(params)
    async def resolve(qids, lang="ja"):
        return {q: {"qid": q, "label": {"Q9312": "イマヌエル・カント", "Q6512": "セーレン・キェルケゴール"}[q], "is_person": True, "nclaims": 1} for q in qids}
    monkeypatch.setattr(concept, "cached_get_json", fake)
    monkeypatch.setattr(concept, "_resolve", resolve)
    res = {v["label"]: v["in_body"] for v in asyncio.run(concept._article_resolved("実存主義", "ja"))}
    assert res == {"イマヌエル・カント": False, "セーレン・キェルケゴール": True}


def test_unknown_body_is_not_reported_as_absent(monkeypatch):
    async def fake(url, params, ttl=0):
        if params.get("prop") == "links":
            return {"query": {"pages": {"1": {"links": [{"title": "イマヌエル・カント"}]}}}}, "t", False
        if params.get("action") == "parse":
            raise RuntimeError("down")
        return {"query": {"pages": {"a": {"title": "イマヌエル・カント", "pageprops": {"wikibase_item": "Q9312"}}}}}, "t", False
    async def resolve(qids, lang="ja"):
        return {q: {"qid": q, "label": "イマヌエル・カント", "is_person": True, "nclaims": 1} for q in qids}
    monkeypatch.setattr(concept, "cached_get_json", fake)
    monkeypatch.setattr(concept, "_resolve", resolve)
    assert asyncio.run(concept._article_resolved("実存主義", "ja"))[0]["in_body"] is None   # 取れない＝不明（「本文に無い」と言わない）


def test_more_particles_and_katakana_words_are_split(monkeypatch):
    # 所有者の承認（10/23 18:1x）:「の」以外の助詞と、漢字を含まない語にも同じ規則を広げる
    async def titles(word):
        return {"パラドックス", "存在", "他者", "対話", "時間", "弁証法", "ゲル", "ノン"}, "t", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    seg = lambda w: [(x["text"], x["role"]) for x in asyncio.run(ety.grounded_cjk_units(w))]
    assert seg("ゼノンのパラドックス") == [("ゼノン", "unresolved_unit"), ("の", "particle"), ("パラドックス", "lexical_unit")]
    assert seg("他者との対話") == [("他者", "lexical_unit"), ("との", "particle"), ("対話", "lexical_unit")]
    assert seg("存在と時間") == [("存在", "lexical_unit"), ("と", "particle"), ("時間", "lexical_unit")]
    # カタカナの語は内側で切らない（辞書に ゲル が在っても ヘー＋ゲル にしない）
    assert seg("ヘーゲルの弁証法") == [("ヘーゲル", "unresolved_unit"), ("の", "particle"), ("弁証法", "lexical_unit")]


def test_katakana_word_without_particle_is_not_split(monkeypatch):
    async def titles(word):
        return {"ポスト", "モダン"}, "t", None
    monkeypatch.setattr(ety, "_wikt_titles", titles)
    assert asyncio.run(ety.grounded_cjk_units("ポストモダン")) is None
