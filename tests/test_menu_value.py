"""メニューの結果の価値（所有者 2026-10-21）のサーバ側。外部取得は差し替える。

- 多言語の語を「その言語の言い方（綴りが遠い）」「借用・同語源（綴りが近い）」「比べていない」に分ける
- Wikipedia の転送（実存 → 実存主義）を黙って辿らず、転送先を返す
- 記事の無い語で、通常検索が映画などの記事を返したら概念として使わない（親密性 → 映画『親密さ』）
"""
import asyncio

from app import main
from app.connectors import concept

REFS = ["existentialism", "Existentialismus", "existentialisme"]


def test_own_wording_is_told_apart_from_borrowed_spelling():
    assert main._spelling_kind("Hebûnparêzî", REFS) == "own"
    assert main._spelling_kind("tilvistarstefna", REFS) == "own"
    assert main._spelling_kind("existencialismo", REFS) == "loan"
    assert main._spelling_kind("egzystencjalizm", REFS) == "loan"


def test_cyrillic_and_greek_are_transliterated_before_comparing():
    assert main._spelling_kind("экзистенциализм", REFS) == "loan"
    assert main._spelling_kind("υπαρξισμός", REFS) == "own"


def test_scripts_that_are_not_compared_are_marked_unknown():
    assert main._spelling_kind("存在主义", REFS) == "unknown"
    assert main._spelling_kind("الوجودية", REFS) == "unknown"
    assert main._spelling_kind("anything", []) == "unknown"


def _run(coro):
    return asyncio.run(coro)


def test_wikipedia_redirect_is_reported_not_hidden(monkeypatch):
    async def fetch(title, lang):
        return {"title": "実存主義", "extract": "実存主義とは…", "pageprops": {}}, "t", False
    monkeypatch.setattr(concept, "_fetch_article", fetch)
    r = _run(concept.node("実存", "ja"))
    d = r["data"]
    assert d["found"] is True
    assert d["redirected_to"] == "実存主義" and d["title"] == "実存主義"
    assert d["resolved_from"] is None   # 概念は従来どおり（転送を明示するだけ・自動で別の概念へ切り替えない）


def test_search_fallback_to_a_film_is_not_used_as_the_concept(monkeypatch):
    async def fetch(title, lang):
        if title == "親密性":
            return {"missing": ""}, "t", False
        return {"title": "親密さ", "extract": "『親密さ』は2012年の映画", "pageprops": {"wikibase_item": "Q17231549"}}, "t", False

    async def opensearch(word, lang):
        return ["親密さ"]

    async def get(url, params=None, **k):
        return {"entities": {"Q17231549": {"labels": {}, "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}]}}}}, "t", False
    monkeypatch.setattr(concept, "_fetch_article", fetch)
    monkeypatch.setattr(concept, "_opensearch", opensearch)
    monkeypatch.setattr(concept, "cached_get_json", get)
    d = _run(concept.node("親密性", "ja"))["data"]
    assert d["found"] is False
    assert d["rejected_article"] == "親密さ"
    assert d["suggestions"] == ["親密さ"]
