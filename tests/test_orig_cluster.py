"""原語基底 PoC: the portal's own original-language-first layer. For a resolved
concept it surfaces the SIBLING original-language lemmas that collapse into one
Japanese word (疎外 ← Entfremdung/Entäußerung/Selbstentfremdung/Vergegenständlichung;
身体 ← Leib/Körper) — the distinctions the translation discards. Offline Level-0.

A3 (honesty) is enforced MECHANICALLY here: every seed lemma must declare a
source, and the seed must announce itself as curated/non-exhaustive — so the card
can never present a fabricated or unsourced distinction as fact."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app.main import _orig_cluster, ORIG_CLUSTERS, ORIG_CLUSTER_INDEX  # noqa: E402


def _ent(label_en=None, en_wp=None, orig=None):
    return {"error": None, "data": {"label_en": label_en,
            "wikipedia": {"en": en_wp} if en_wp else {},
            "orig_labels": orig or {}}}


def test_japanese_word_matches_its_cluster():
    c = _orig_cluster("疎外", None)
    assert c and c["id"] == "alienation"
    lemmas = {l["lemma"] for l in c["lemmas"]}
    assert {"Entfremdung", "Entäußerung", "Selbstentfremdung", "Vergegenständlichung"} <= lemmas


def test_body_cluster_keeps_leib_körper_distinct():
    c = _orig_cluster("身体", None)
    assert c and c["id"] == "body"
    by = {l["lemma"]: l for l in c["lemmas"]}
    assert "Leib" in by and "Körper" in by
    assert by["Leib"]["gloss"] != by["Körper"]["gloss"]  # the distinction is preserved


def test_matches_via_resolved_english_anchor():
    # a query that resolves (entity) to 'Alienation' must reach the cluster even
    # if the raw query string itself is not a match key
    c = _orig_cluster("xyz", _ent(label_en="Alienation"))
    assert c and c["id"] == "alienation"


def test_live_orig_labels_augment_and_drop_english():
    c = _orig_cluster("疎外", _ent(label_en="Alienation", orig={"en": "Alienation", "de": "Entfremdung"}))
    assert c["live_orig_labels"] == {"de": "Entfremdung"}  # 'en' dropped (not an ORIGINAL)


def test_unknown_query_is_honest_silence():
    assert _orig_cluster("量子力学", None) is None
    assert _orig_cluster("", None) is None
    assert _orig_cluster("Kant", _ent(label_en="Immanuel Kant")) is None


def test_seed_never_mutated_by_lookup():
    before = len(ORIG_CLUSTERS["clusters"][0])
    _orig_cluster("疎外", _ent(orig={"de": "Entfremdung"}))
    assert "provenance" not in ORIG_CLUSTERS["clusters"][0]  # added only to the copy
    assert len(ORIG_CLUSTERS["clusters"][0]) == before


def test_A3_every_lemma_declares_a_source():
    # mechanical honesty gate: no unsourced distinction may ship
    for c in ORIG_CLUSTERS["clusters"]:
        for l in c["lemmas"]:
            assert l.get("source"), f"{l['lemma']} has no source"
            assert l.get("gloss") and l.get("collapses_to")
        assert c["confidence_terms"] and c["confidence_collapse"]
        assert c.get("primary_source")


def test_A3_seed_declares_itself_curated_not_exhaustive():
    meta = ORIG_CLUSTERS["_meta"]
    assert "CURATED SEED" in meta["honesty"] and "NOT exhaustive" in meta["honesty"]
    assert meta["verified_at"] and meta["verified_against"]


def test_index_covers_every_match_key():
    for c in ORIG_CLUSTERS["clusters"]:
        for m in c["match"]:
            assert ORIG_CLUSTER_INDEX[m.lower()]["id"] == c["id"]
