"""/api/wordspace の試験（2026-10-05）。

所有者の設計（10-04）: 1語から辞書を横断して辺を集め、別の層として
用例の分布（時代・著者・分野・文脈）を出す。2層は重ねずに持つ。

この試験は、2層が別のkeyで返り、片方が落ちてももう片方が返り、
標本であることの宣言が消えないことを固定する。外部取得なし・決定論。
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app import main as m  # noqa: E402
from app.connectors.base import ok  # noqa: E402

DICT = {
    "word": "自然", "missing": False, "note": "",
    "url": "https://ja.wiktionary.org/wiki/%E8%87%AA%E7%84%B6",
    "readings": [{"kana": "しぜん", "yomi": "kanon"}, {"kana": "じねん", "yomi": "goon"}],
    "senses": ["あるがままであること。無為。"],
    "relations": [{"kind": "synonym", "term": "天然", "sense": "語義1"},
                  {"kind": "antonym", "term": "人為", "sense": "語義1"}],
    "layer": "一般辞書の関係記述。哲学術語の定義ではない", "source": "ja.wiktionary",
}
CORPUS = {
    "word": "権理", "variants_tried": ["権理", "權理"],
    "hit_by_variant": {"権理": 6756, "權理": 6756}, "hit_total_reported": 13512,
    "by_decade": {1870: 44, 1880: 96}, "by_ndc": {"324": 36},
    "authors": [("西村茂樹", 2)], "translators": [("尾崎行雄", 8)],
    "unknown_year": 20, "unknown_ndc": 3, "sampled": 200, "sample_size": 100,
    "works": [{"title": "權理提綱", "year": 1877, "editions": 6,
               "authors": ["斯辺銷"], "translators": ["尾崎行雄"],
               "locators": ["生命並ニ自由之権理/1p"], "id": "798457",
               "url": "https://lab.ndl.go.jp/dl/book/798457"}],
    "layer": "近代刊行物の全文OCRの出現分布。標本であり全体の分布ではない",
    "errors": [], "note": "分布は標本である。",
}


def _install(monkeypatch, dict_data=DICT, corpus_data=CORPUS,
             dict_err=None, corpus_err=None):
    async def fake_dict(word, ttl=86400):
        if dict_err:
            return {"source": "ja.wiktionary", "retrieved_at": "t", "cached": False,
                    "error": dict_err, "data": None}
        return ok("ja.wiktionary", "t", False, dict_data)

    async def fake_corpus(word, sample=100, variants=2):
        if corpus_err:
            return {"source": "ndl-fulltext", "retrieved_at": "t", "cached": False,
                    "error": corpus_err, "data": None}
        return ok("ndl-fulltext", "t", False, corpus_data)

    monkeypatch.setattr(m.ja_wiktionary, "lookup", fake_dict)
    monkeypatch.setattr(m.ndl_fulltext, "survey", fake_corpus)


def test_two_layers_come_back_separately(monkeypatch):
    """辞書層と用例層を別のkeyで返す。混ぜない。"""
    _install(monkeypatch)
    r = asyncio.run(m.api_wordspace(q="自然", lang="ja"))
    assert r["dictionary"]["readings"], r
    assert r["corpus"]["by_decade"], r
    assert r["dictionary"] is not r["corpus"]


def test_edges_are_chainable_terms(monkeypatch):
    """辺は次に辿れる語として返る。種類と出所を必ず持つ。"""
    _install(monkeypatch)
    r = asyncio.run(m.api_wordspace(q="自然", lang="ja"))
    edges = r["edges"]
    assert edges, r
    for e in edges:
        assert e["term"] and e["kind"] and e["source"]
    kinds = {e["kind"] for e in edges}
    assert {"synonym", "antonym"} <= kinds, kinds


def test_corpus_layer_declares_it_is_a_sample(monkeypatch):
    """標本であることの宣言を落とさない。全体の分布と誤認させない。"""
    _install(monkeypatch)
    r = asyncio.run(m.api_wordspace(q="権理", lang="ja"))
    assert "標本" in r["corpus"]["layer"]
    assert r["corpus"]["sampled"] == 200


def test_dictionary_failure_does_not_kill_corpus(monkeypatch):
    """片方が落ちても、もう片方は返す。両方沈黙させない。"""
    _install(monkeypatch, dict_err="HTTPError: 500")
    r = asyncio.run(m.api_wordspace(q="権理", lang="ja"))
    assert r["corpus"]["by_decade"], r
    assert r["errors"], "落ちた層を黙って隠している"


def test_corpus_failure_does_not_kill_dictionary(monkeypatch):
    _install(monkeypatch, corpus_err="TimeoutError: ")
    r = asyncio.run(m.api_wordspace(q="自然", lang="ja"))
    assert r["dictionary"]["readings"], r
    assert r["errors"]


def test_variant_forms_are_visible(monkeypatch):
    """試した字体を画面に出せる形で返す。"""
    _install(monkeypatch)
    r = asyncio.run(m.api_wordspace(q="権理", lang="ja"))
    assert r["corpus"]["variants_tried"] == ["権理", "權理"]


def test_sources_name_both_layers(monkeypatch):
    _install(monkeypatch)
    r = asyncio.run(m.api_wordspace(q="自然", lang="ja"))
    ids = {s["id"] for s in r["sources"]}
    assert {"ja-wiktionary", "ndl-fulltext"} <= ids, ids
