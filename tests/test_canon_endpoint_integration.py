"""/api/canon に訳語辺を統合する試験（2026-10-03）。

作った入口が利用者に到達していなければ、作っていないのと同じである。実測で
`/api/canon` は `app/static/app.js` と `app/templates/*.html` のどこからも
呼ばれていなかった。所有者の指摘「在る資源を使わない」の同型である。

この試験は、統合された入口が次を満たすことを固定する。

1. 日本語の語でも原語に到達する（訳語辺の経路が効く）
2. 試した経路を残す（空を「無い」と言い換えない）
3. 層の宣言を落とさない（一般辞書の訳語等価であること）

外部取得なし・決定論。
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app import main as m  # noqa: E402
from app.connectors.base import ok  # noqa: E402

# ── 実取得（2026-10-02）を縮約 ──
TE_HIT = {
    "query": "愛", "matched": True,
    "hit": {
        "headword": "love", "page": "love/translations",
        "sense": "strong affection",
        "japanese_in_sense": ["愛", "愛情", "愛好"],
        "originals": [
            {"lang": "grc", "term": "ἀγάπη"}, {"lang": "grc", "term": "φιλία"},
            {"lang": "grc", "term": "ἔρως"}, {"lang": "grc", "term": "στοργή"},
            {"lang": "la", "term": "amor"}, {"lang": "la", "term": "cāritās"},
        ],
        "other_senses": ["zero"],
        "original_count": 6,
    },
    "pivots": ["love"], "routes_tried": ["insource", "wikidata_label"],
    "headwords_checked": [{"headword": "love",
                           "pages": ["love", "love/translations"],
                           "sense_blocks": 11, "bare_blocks": 0}],
    "layer": "一般辞書の訳語等価。哲学術語の原語ではない",
    "evidence": "candidate", "note": "枠を跨がない",
}
TE_MISS = {
    "query": "権利", "matched": False, "hit": None,
    "pivots": ["patent", "right"], "routes_tried": ["insource", "wikidata_label"],
    "headwords_checked": [{"headword": "right", "pages": ["right"],
                           "sense_blocks": 4, "bare_blocks": 1}],
    "layer": "一般辞書の訳語等価。哲学術語の原語ではない",
    "evidence": "candidate", "note": "",
}
CANON_EMPTY = {
    "query": "愛", "matched": False, "item": None,
    "original_terms": [], "canon_entries": [], "authority_terms_tried": [],
    "note": "項目に到達していない",
}


def _install(monkeypatch, te_data, canon_data=None):
    async def fake_te(word, lang="ja", max_pivots=6):
        return ok("translation-edge", "fixture", True, te_data)

    async def fake_canon(word, lang="ja"):
        return ok("canon", "fixture", True, canon_data or CANON_EMPTY)

    monkeypatch.setattr(m.translation_edge, "collapse", fake_te)
    monkeypatch.setattr(m.canon, "resolve", fake_canon)


def test_japanese_word_reaches_originals_via_translation_edge(monkeypatch):
    """日本語の語でも原語に到達する。典拠経路が空でも訳語辺が補う。"""
    _install(monkeypatch, TE_HIT)
    r = asyncio.run(m.api_canon(q="愛", lang="ja"))
    te = r.get("translation_edge") or {}
    assert te.get("matched") is True
    terms = [x["term"] for x in (te.get("hit") or {}).get("originals", [])]
    assert "ἀγάπη" in terms and "στοργή" in terms, f"原語に到達していない: {terms}"
    assert r["matched"] is True, "どちらかの経路が当たれば matched は真にする"


def test_unreached_word_keeps_what_was_tried(monkeypatch):
    """到達しないとき、試した経路を残す。空を「無い」と言い換えない。"""
    _install(monkeypatch, TE_MISS)
    r = asyncio.run(m.api_canon(q="権利", lang="ja"))
    te = r.get("translation_edge") or {}
    assert te.get("matched") is False
    assert te.get("routes_tried"), "試した経路が記録されていない"
    checked = [c["headword"] for c in (te.get("headwords_checked") or [])]
    assert "right" in checked, f"試した見出し語が記録されていない: {checked}"
    assert r["matched"] is False


def test_layer_declaration_survives_integration(monkeypatch):
    """層の宣言を落とさない。哲学術語の原語と誤認させない。"""
    _install(monkeypatch, TE_HIT)
    r = asyncio.run(m.api_canon(q="愛", lang="ja"))
    assert "一般辞書" in ((r.get("translation_edge") or {}).get("layer") or "")


def test_existing_canon_fields_are_preserved(monkeypatch):
    """既存の返り値fieldを壊さない。"""
    _install(monkeypatch, TE_HIT)
    r = asyncio.run(m.api_canon(q="愛", lang="ja"))
    for key in ("query", "lang", "queried_at", "item", "original_terms",
                "canon_entries", "note", "sources"):
        assert key in r, f"既存field {key} が消えている"


def test_sources_name_the_translation_table(monkeypatch):
    """出所に訳語表を明記する。どこから来た語かを隠さない。"""
    _install(monkeypatch, TE_HIT)
    r = asyncio.run(m.api_canon(q="愛", lang="ja"))
    ids = [s["id"] for s in r.get("sources", [])]
    assert "wiktionary-translations" in ids, f"出所に訳語表が無い: {ids}"
