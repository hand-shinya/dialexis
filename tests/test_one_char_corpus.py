"""1字の語で用例層が空になる問題の試験（2026-10-05）。

実測（10-05 本番・直接照会）:
  NDL Book API の keyword は2字以上でないと0件になる。
  愛・恋・道・性・理 はいずれも hit=0、愛情・恋愛・慈愛・道徳・理性 は 10000。
  全文索引が2字単位のためと見られる。1字の語は照会そのものが成立しない。

対応: 0件と「照会できない」を区別し、辞書層の類義・関連語で代替照会する。
代替であることを payload に明示し、元の語の分布だと誤認させない。

純関数・外部取得なし・決定論。
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app import main as m  # noqa: E402
from app.connectors import ndl_fulltext as nf  # noqa: E402
from app.connectors.base import ok  # noqa: E402

DICT_AI = {
    "word": "愛", "missing": False, "note": "", "url": "u",
    "readings": [], "senses": ["慈しむ気持ち。"],
    "relations": [{"kind": "synonym", "term": "恋愛", "sense": "語義1"},
                  {"kind": "synonym", "term": "慈愛", "sense": "語義2"},
                  {"kind": "related", "term": "愛情", "sense": ""},
                  {"kind": "reading", "term": "あい", "sense": ""}],
    "layer": "L", "source": "ja.wiktionary",
}


def test_min_keyword_length_is_declared():
    assert nf.MIN_KEYWORD_CHARS == 2


def test_substitutes_prefer_synonyms_then_related():
    """代替語は類義語を先に採る。読みは語ではないので採らない。"""
    subs = m._corpus_substitutes(DICT_AI, limit=3)
    assert subs == ["恋愛", "慈愛", "愛情"], subs


def test_substitutes_skip_short_terms():
    """1字の代替語を採らない。同じ理由で照会できない。"""
    d = {"relations": [{"kind": "synonym", "term": "恋", "sense": ""},
                       {"kind": "synonym", "term": "恋愛", "sense": ""}]}
    assert m._corpus_substitutes(d, limit=3) == ["恋愛"]


def test_no_substitutes_without_dictionary():
    assert m._corpus_substitutes({}, limit=3) == []
    assert m._corpus_substitutes({"relations": []}, limit=3) == []


def test_one_char_word_is_short_circuited_with_a_reason():
    """1字では照会しない。無駄な要求を出さず、理由を残す。"""
    r = asyncio.run(nf.survey("愛"))
    d = r["data"]
    assert d["sampled"] == 0
    assert d["too_short"] is True, d
    assert "2字" in d["note"], d["note"]


def test_endpoint_substitutes_for_one_char_words(monkeypatch):
    """1字の語では類義語で代替照会し、代替であることを明示する。"""
    calls = []

    async def fake_dict(word, ttl=86400):
        return ok("ja.wiktionary", "t", False, DICT_AI)

    async def fake_survey(word, sample=100, variants=2):
        calls.append(word)
        if len(word.strip()) < 2:
            return ok("ndl-fulltext", "t", False,
                      {"word": word, "sampled": 0, "too_short": True,
                       "by_decade": {}, "works": [], "variants_tried": [word],
                       "note": "2字以上でないと照会できない"})
        return ok("ndl-fulltext", "t", False,
                  {"word": word, "sampled": 5, "too_short": False,
                   "by_decade": {1920: 5}, "works": [],
                   "variants_tried": [word], "note": ""})

    async def empty(*a, **k):
        return ok("x", "t", False, [])

    monkeypatch.setattr(m.ja_wiktionary, "lookup", fake_dict)
    monkeypatch.setattr(m.ndl_fulltext, "survey", fake_survey)
    monkeypatch.setattr(m.cinii, "search", empty)
    monkeypatch.setattr(m.openalex, "search_works", empty)

    r = asyncio.run(m.api_wordspace(q="愛", lang="ja"))
    c = r["corpus"]
    assert c["substituted_for"] == "愛", c
    assert c["substitutes"], c
    assert c["by_decade"], "代替照会の結果が入っていない"
    assert "愛" in calls and "恋愛" in calls, calls


def test_endpoint_does_not_substitute_for_normal_words(monkeypatch):
    """2字以上の語では代替照会をしない。余計な要求を出さない。"""
    calls = []

    async def fake_dict(word, ttl=86400):
        return ok("ja.wiktionary", "t", False, DICT_AI)

    async def fake_survey(word, sample=100, variants=2):
        calls.append(word)
        return ok("ndl-fulltext", "t", False,
                  {"word": word, "sampled": 3, "too_short": False,
                   "by_decade": {1930: 3}, "works": [], "variants_tried": [word],
                   "note": ""})

    async def empty(*a, **k):
        return ok("x", "t", False, [])

    monkeypatch.setattr(m.ja_wiktionary, "lookup", fake_dict)
    monkeypatch.setattr(m.ndl_fulltext, "survey", fake_survey)
    monkeypatch.setattr(m.cinii, "search", empty)
    monkeypatch.setattr(m.openalex, "search_works", empty)

    r = asyncio.run(m.api_wordspace(q="自然", lang="ja"))
    assert calls == ["自然"], calls
    assert not r["corpus"].get("substituted_for")
