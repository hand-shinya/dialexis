"""翻訳・受容史の特別モードは、curated evidence dossier を正直に返す。"""
import asyncio
import os
import tempfile
import urllib.parse

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "translation-history-test.db")

from app.main import (TRANSLATION_HISTORY, _history_domain, _history_dossier,
                      _history_discovery_from_sources, api_translation_history)  # noqa: E402


def test_body_dossier_matches_japanese_and_original_aliases():
    for query in ("非有機的肉体", "unorganischer Leib", "Körper", "Stoffwechsel"):
        dossier, matched = _history_dossier(query, "philosophy")
        assert dossier and dossier["id"] == "marx-nonorganic-body"
        assert matched
        assert dossier["term_map"] and dossier["timeline"] and dossier["reception_ledger"]


def test_domain_aliases_are_normalized_without_changing_display_terms():
    assert _history_domain("哲学") == "philosophy"
    assert _history_domain("科学") == "science"
    assert _history_domain("") == "philosophy"


def test_seed_declares_scope_and_evidence_levels():
    meta = TRANSLATION_HISTORY["_meta"]
    assert "CURATED SEED" in meta["honesty"]
    assert "NOT exhaustive" in meta["honesty"]
    assert {x["id"] for x in meta["evidence_levels"]} >= {
        "confirmed", "bibliography_confirmed", "strong", "candidate", "unverified"
    }
    dossier = TRANSLATION_HISTORY["dossiers"][0]
    assert dossier["center_question"] and dossier["counterchecks"] and dossier["next_actions"]


def test_api_does_not_reuse_philosophy_seed_for_other_domains_or_unknown_terms(monkeypatch):
    async def no_discovery(*args, **kwargs):
        return None
    monkeypatch.setattr("app.main._history_discovery", no_discovery)
    ready = asyncio.run(api_translation_history("非有機的肉体", "哲学", "ja"))
    assert ready["status"] == "ready" and ready["matched"]
    empty_domain = asyncio.run(api_translation_history("非有機的肉体", "science", "ja"))
    assert empty_domain["status"] == "not_seeded" and empty_domain["dossier"] is None
    unknown = asyncio.run(api_translation_history("量子力学", "philosophy", "ja"))
    assert unknown["status"] == "not_seeded" and unknown["dossier"] is None


def test_api_returns_a_copy_so_one_view_cannot_mutate_the_seed():
    first = asyncio.run(api_translation_history("非有機的肉体", "philosophy", "ja"))
    first["dossier"]["term_map"].clear()
    second = asyncio.run(api_translation_history("非有機的肉体", "philosophy", "ja"))
    assert len(second["dossier"]["term_map"]) >= 5


def test_unknown_term_normalizes_dictionary_and_bibliographic_discovery():
    origin = {
        "general_meaning": ["複数の人々が共有する幻想"],
        "wiktionary_url": "https://ja.wiktionary.org/wiki/共同幻想",
        "wikidata_url": "https://www.wikidata.org/wiki/Q-test",
        "breadth": [{"name": "英語", "term": "communal illusion"}],
        "originators": [{"label": "吉本隆明"}],
    }
    anatomy = {"segment_layers": [{"level": "semantic", "units": [{"text": "共同", "gloss": "共に"}]}]}
    explore = {
        "japanese_scholarship": {"data": [{"title": "共同幻想論", "creators": ["吉本隆明"], "year": "1968", "url": "https://example.test/ndl"}]},
        "cinii": {"data": [{"title": "共同幻想の研究", "creators": ["研究者"], "year": "2020", "url": "https://example.test/cinii"}]},
        "recent_scholarship": {"data": [{"title": "共同幻想と社会", "authors": ["Scholar"], "year": 2021, "url": "https://example.test/openalex"}]},
    }
    d = _history_discovery_from_sources("共同幻想", "philosophy", "ja", origin, anatomy, explore)
    assert d and d["mode"] == "automated_discovery"
    assert any(x["source_term"] == "共同幻想" for x in d["term_map"])
    assert any(x["source_term"] == "共同" for x in d["term_map"])
    assert len(d["timeline"]) == 3
    assert any(x["who"] == "吉本隆明" for x in d["reception_ledger"])
    assert any(s["id"].startswith("auto-ndl-") for s in d["sources"])
    science = _history_discovery_from_sources("共同幻想", "science", "ja", origin, anatomy, explore)
    assert science and not any(s["id"].startswith("auto-openalex-") for s in science["sources"])


def test_unknown_term_returns_a_research_workspace_when_discovery_has_no_source_data(monkeypatch):
    async def no_discovery(*args, **kwargs):
        return None
    monkeypatch.setattr("app.main._history_discovery", no_discovery)
    result = asyncio.run(api_translation_history("自由", "哲学", "ja"))
    assert result["status"] == "not_seeded"
    assert result["research_brief"]["status"] == "new_research_workspace"
    assert "自由" in result["research_brief"]["title"]
    ids = {s["id"] for s in result["source_candidates"]}
    assert {"candidate-wiktionary-ja", "candidate-ndl", "candidate-cinii"} <= ids
    assert all("自由" in urllib.parse.unquote(s["url"]) for s in result["source_candidates"])
    assert all(a.get("source_ids") for a in result["next_actions"])
