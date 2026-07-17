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
