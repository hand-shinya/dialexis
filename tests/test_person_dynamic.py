"""動的な人物同定・著作・概念・受容の契約を検証する。"""

import asyncio

from app import main


def _person_entity():
    return {
        "data": {
            "qid": "Q6512",
            "label": "セーレン・キェルケゴール",
            "label_en": "Søren Kierkegaard",
            "description": "Danish philosopher and theologian",
            "is_person": True,
            "labels": {
                "ja": "セーレン・キェルケゴール",
                "en": "Søren Kierkegaard",
                "de": "Søren Kierkegaard",
                "fr": "Søren Kierkegaard",
            },
            "aliases": {
                "ja": ["キェルケゴール", "セーレン・キルケゴール"],
                "en": ["Kierkegaard"],
            },
            "orig_labels": {"en": "Søren Kierkegaard", "de": "Søren Kierkegaard", "fr": "Søren Kierkegaard"},
            "wikipedia": {"ja": "セーレン・キェルケゴール", "en": "Søren Kierkegaard"},
            "claims": {
                "born": ["1813-05-05"], "died": ["1855-11-11"],
                "notable_work": ["Q1"], "field_of_work": ["Q101"],
                "movement": ["Q102"], "influenced_by": ["Q103"],
            },
            "url": "https://www.wikidata.org/wiki/Q6512",
        }
    }


def test_same_latin_form_is_one_record_with_language_coverage():
    profile = main._person_profile_from_entity("セーレン・キェルケゴール", _person_entity(), "ja")
    assert profile
    latin = [x for x in profile["name_forms"] if x["form"] == "Søren Kierkegaard"]
    assert len(latin) == 1
    assert {"英語", "ドイツ語", "フランス語"} <= set(latin[0]["languages"])
    assert len(profile["name_forms"]) == len({main._person_norm(x["form"]) for x in profile["name_forms"]})


def test_person_probe_gate_does_not_delay_ordinary_cjk_concepts():
    assert not main._history_person_candidate("自由")
    assert not main._history_person_candidate("共同幻想")
    assert not main._history_person_candidate("量子力学")
    assert main._history_person_candidate("西田幾多郎")
    assert main._history_person_candidate("セーレン・キェルケゴール")
    assert main._history_person_candidate("索倫·克爾凱郭爾")


def test_dynamic_person_expands_into_works_bibliography_concepts_timeline_and_reception(monkeypatch):
    async def fast(coro, timeout=8.0):
        return await coro

    async def search(*args, **kwargs):
        return {"error": None, "data": [{"qid": "Q6512"}]}

    async def resolve(*args, **kwargs):
        return _person_entity()

    async def batch(qids, lang="ja"):
        if "Q9035" in qids:
            return {"error": None, "data": [{"qid": "Q9035", "labels": {"en": "Danish"}, "label_en": "Danish"}]}
        rows = [
            {"qid": "Q1", "labels": {"da": "Enten - Eller", "en": "Either/Or", "ja": "あれか、これか"},
             "label": "Either/Or", "label_en": "Either/Or", "wikipedia": {"da": "Enten - Eller", "en": "Either/Or", "ja": "あれか、これか"},
             "claims": {"original_language": ["Q9035"], "publication_date": ["1843"]}, "url": "https://www.wikidata.org/wiki/Q1"},
            {"qid": "Q101", "labels": {"en": "Philosophy", "ja": "哲学"}, "label": "Philosophy", "label_en": "Philosophy", "claims": {}},
            {"qid": "Q102", "labels": {"en": "Existentialism", "ja": "実存主義"}, "label": "Existentialism", "label_en": "Existentialism", "claims": {}},
            {"qid": "Q103", "labels": {"en": "Socrates", "ja": "ソクラテス"}, "label": "Socrates", "label_en": "Socrates", "claims": {}},
        ]
        return {"error": None, "data": rows}

    async def by_author(*args, **kwargs):
        return {"error": None, "data": [{"title": "あれか、これか", "creators": ["キェルケゴール", "訳者A"], "publisher": "出版社", "year": "1950", "url": "https://example.test/ndl"}]}

    async def by_work(*args, **kwargs):
        return {"error": None, "data": {"work": "あれか、これか", "editions": [{"title": "あれか、これか", "creators": ["訳者A"], "publisher": "出版社", "year": "1950", "url": "https://example.test/edition"}]}}

    async def summary(*args, **kwargs):
        return {"error": None, "data": {"extract": "デンマークの哲学者。", "url": "https://ja.wikipedia.org/wiki/test"}}

    async def gut(*args, **kwargs):
        return {"error": None, "data": [{"id": 1, "title": "Either/Or", "authors": ["Kierkegaard, Søren"], "read_url": "https://example.test/text"}]}

    async def oa(*args, **kwargs):
        return {"error": None, "data": [{"title": "Kierkegaard and philosophy", "authors": ["Scholar"], "year": 2020, "url": "https://example.test/oa"}]}

    monkeypatch.setattr(main, "_history_bounded", fast)
    monkeypatch.setattr(main.wikidata, "search", search)
    monkeypatch.setattr(main, "_resolve_entity", resolve)
    monkeypatch.setattr(main.wikidata, "batch_entities", batch)
    monkeypatch.setattr(main.ndl, "by_author", by_author)
    monkeypatch.setattr(main.ndl, "by_work", by_work)
    monkeypatch.setattr(main.wikipedia, "summary", summary)
    monkeypatch.setattr(main.gutendex, "search", gut)
    monkeypatch.setattr(main.openalex, "search_works", oa)
    main._PERSON_DISCOVERY_CACHE.clear()

    profile = asyncio.run(main._discover_person_profile("セーレン・キェルケゴール", "ja"))
    assert profile
    assert profile["works"][0]["original_title"] == "Enten - Eller"
    assert profile["works"][0]["japanese_titles"] == ["あれか、これか"]
    assert profile["works"][0]["edition_count"] == 1
    assert profile["bibliography"]
    assert profile["concepts"]
    assert profile["timeline"]
    assert profile["reception"]
    assert profile["primary_texts"]
    assert profile["scholarship"]


def test_origin_graph_uses_person_mode_for_generic_person_profile(monkeypatch):
    profile = main._person_profile_from_entity("セーレン・キェルケゴール", _person_entity(), "ja")

    async def profile_for_query(*args, **kwargs):
        return profile

    monkeypatch.setattr(main, "_person_profile_for_query_async", profile_for_query)
    result = asyncio.run(main.api_origin_graph("セーレン・キェルケゴール", "ja"))
    assert result["research_mode"] == "person"
    assert result["entity_kind"] == "person"
    assert result["person_profile"]["display_name"] == "セーレン・キェルケゴール"
