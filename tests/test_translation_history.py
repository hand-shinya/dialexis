"""翻訳・受容史の特別モードは、curated evidence dossier を正直に返す。"""
import asyncio
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "translation-history-test.db")

from app.main import TRANSLATION_HISTORY, _history_domain, _history_dossier, api_translation_history  # noqa: E402


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


def test_api_does_not_reuse_philosophy_seed_for_other_domains_or_unknown_terms():
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
