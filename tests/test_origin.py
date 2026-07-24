"""原語による探求 (MVP) — lock the two brittle parsers offline so a DWDS/Wiktionary
markup change fails a test rather than silently emptying the experience (axiom 1:
visibility over silence). Fixtures are real fragments captured 2026-07-17."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app.connectors.dwds import _COLLO  # noqa: E402
from app.connectors.wiktionary import _extract  # noqa: E402

# A real DWDS Wortprofil collocate row (Entfremdung), trimmed.
DWDS_HTML = '''
<td data-wp-ccid="1" data-freq="208" >
  <span data-toggle="tooltip" title="Lemma: schleichend; häufigste Oberflächenform: schleichende">schleichende</span>
</span>
<span class="no-touch-only" title="aus der Relation »hat Adjektivattribut«" data-toggle="tooltip"><i></i></span>
<td data-wp-ccid="2" data-freq="27" >
  <span data-toggle="tooltip" title="Lemma: Verdinglichung; häufigste Oberflächenform: Verdinglichung">Verdinglichung</span>
</span>
<span class="no-touch-only" title="aus der Relation »ist in Koordination mit«" data-toggle="tooltip"><i></i></span>
'''

WIKT = """== Entfremdung ({{Sprache|Deutsch}}) ==
{{Bedeutungen}}
:[1] Gefühl des Fremdseins, des Nichtdazugehörens
:[2] Prozess des Fremdwerdens
{{Herkunft}}
:Ableitung vom Stamm des Verbs ''entfremden'' mit dem Derivatem ''-ung''
{{Synonyme}}
:[1] [[Distanz]]
"""


def test_dwds_collocate_parsing():
    hits = _COLLO.findall(DWDS_HTML)
    by = {rel.strip(): (lemma.strip(), int(freq)) for freq, lemma, rel in hits}
    assert by["hat Adjektivattribut"] == ("schleichend", 208)
    assert by["ist in Koordination mit"] == ("Verdinglichung", 27)


def test_wiktionary_section_extract():
    assert "Gefühl des Fremdseins" in _extract(WIKT, "Bedeutungen")
    ety = _extract(WIKT, "Herkunft")
    assert "entfremden" in ety and "''" not in ety  # italics stripped
    # a section that stops at the next {{Template}} — must not bleed into Herkunft
    assert "Ableitung" not in _extract(WIKT, "Bedeutungen")


def test_wiktionary_missing_section_is_empty():
    assert _extract(WIKT, "Gegenwörter") == ""


# ---- Phase 1: the word-first hierarchy (author sits UNDER the lineage) --------
from app.main import _author_lineage, AUTHOR_LINEAGE  # noqa: E402


def _ent(label_en=None):
    return {"error": None, "data": {"label_en": label_en, "wikipedia": {}, "orig_labels": {}}}


def test_author_lineage_matches_and_is_ordered_by_precedence():
    lg = _author_lineage("疎外", None)
    assert lg and lg["id"] == "alienation"
    years = [a["year"] for a in lg["authors"]]
    assert years == sorted(years)  # Hegel 1807 → Feuerbach 1841 → Marx 1844
    assert [a["author_de"] for a in lg["authors"]][0] == "Georg Wilhelm Friedrich Hegel"


def test_author_lineage_matches_via_english_anchor():
    assert _author_lineage("xyz", _ent(label_en="Alienation"))["id"] == "alienation"


def test_author_lineage_absent_is_none_not_fabricated():
    assert _author_lineage("量子力学", None) is None  # honest 未整備, not invented


def test_A3_every_author_entry_is_sourced_and_names_original_work():
    for lg in AUTHOR_LINEAGE["lineages"]:
        for a in lg["authors"]:
            assert a.get("source") and a.get("work_de") and a.get("term_de")
    meta = AUTHOR_LINEAGE["_meta"]
    assert "CURATED SEED" in meta["honesty"] and meta["order_basis"] and meta["verified_at"]


# ---- 無中心の原点エンジン: 原点推定ランクと言語名（純粋ロジックを固定） --------
from app.connectors.wiktionary import _ancientness, langname  # noqa: E402


def test_ancientness_ranks_proto_and_classical_above_recent():
    assert _ancientness("gem-pro") == 4          # proto = deepest
    assert _ancientness("sa") == 3               # classical/ancient
    assert _ancientness("ltc") == 2              # medieval
    assert _ancientness("en") == 1               # modern
    # origin = most ancient in a chain, not the last-in-text
    chain = ["sa", "ltc"]                          # 空: Sanskrit vs Middle Chinese
    assert max(chain, key=_ancientness) == "sa"   # → Sanskrit (non-Western origin)
    chain2 = ["enm", "ang", "gmw-pro", "gem-pro", "fr", "la"]  # soul
    assert _ancientness(max(chain2, key=_ancientness)) == 4    # a proto layer, not fr/la


def test_langname_keeps_unmapped_code_never_drops():
    assert langname("sa") == "サンスクリット語"
    assert langname("zzz") == "zzz"   # unmapped → raw code, breadth never silently narrowed
