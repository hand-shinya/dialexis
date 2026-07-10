"""Improvement #2 (G2 Zotero): export.bib / export.csl.json generate from
existing provenance + premise sources. Dependency-free, no schema change.
Offline Level-0 tests: shape, stability of citekeys, and empty-project safety."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import bibliography  # noqa: E402

client = TestClient(app)


def _project_with_source():
    pid = client.post("/api/projects", json={"title": "Bib"}).json()["id"]
    client.post(f"/api/projects/{pid}/nodes", json={
        "type": "source", "title": "吉本隆明と『共同幻想論』", "origin": "external",
        "provenance": [{"source_name": "CiNii", "source_url": "https://cir.nii.ac.jp/abc",
                        "retrieved_at": "2026-07-10T09:00:00+00:00"}]})
    return pid


def test_bib_unit_stable_citekeys():
    refs = [{"title": "A work", "url": "https://x/1", "urldate": "2026-07-10",
             "note": "", "source_name": "SEP"},
            {"title": "A work", "url": "https://x/2", "urldate": "2026-07-10",
             "note": "", "source_name": "SEP"}]  # same base name → must disambiguate
    b1 = bibliography.to_bibtex(refs)
    b2 = bibliography.to_bibtex(refs)
    assert b1 == b2                      # deterministic / stable
    assert b1.count("@misc{") == 2       # both emitted
    assert "@misc{sep," in b1 and "@misc{sep_" in b1  # disambiguated second key


def test_export_bib_endpoint():
    pid = _project_with_source()
    r = client.get(f"/api/projects/{pid}/export.bib")
    assert r.status_code == 200
    txt = r.text
    assert "@misc{" in txt
    assert "共同幻想論" in txt or "CiNii" in txt
    assert "https://cir.nii.ac.jp/abc" in txt
    assert "urldate = {2026-07-10}" in txt


def test_export_csl_endpoint():
    pid = _project_with_source()
    data = client.get(f"/api/projects/{pid}/export.csl.json").json()
    assert isinstance(data, list) and len(data) == 1
    item = data[0]
    assert item["URL"] == "https://cir.nii.ac.jp/abc"
    assert item["accessed"]["date-parts"][0] == [2026, 7, 10]
    assert item["id"]  # a citekey exists


def test_empty_project_bib_is_safe():
    pid = client.post("/api/projects", json={"title": "Empty"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/export.bib")
    assert r.status_code == 200  # no crash, possibly empty body
