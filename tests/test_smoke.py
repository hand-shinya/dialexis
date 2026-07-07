"""Offline smoke tests: the research-process graph and exports must work with
no network and no LLM key (axiom 5, Level 0)."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_pages_render():
    for path in ("/", "/desk", "/watches", "/levels", "/settings", "/donate", "/about"):
        assert client.get(path).status_code == 200, path
    assert "Dialexis" in client.get("/?lang=ja").text


def test_research_graph_roundtrip():
    pid = client.post("/api/projects", json={
        "title": "テスト研究", "question": "自由とは何か"}).json()["id"]
    claim = client.post(f"/api/projects/{pid}/nodes", json={
        "type": "claim", "title": "自由は非支配である",
        "confidence": "interpretive_hypothesis",
        "provenance": [{"source_name": "Pettit 1997",
                        "source_url": "https://example.org"}]}).json()["id"]
    counter = client.post(f"/api/projects/{pid}/nodes", json={
        "type": "counterclaim", "title": "非干渉で足りる", "origin": "human"}).json()["id"]
    client.post(f"/api/projects/{pid}/edges", json={
        "src": counter, "dst": claim, "rel": "contradicts"})
    g = client.get(f"/api/projects/{pid}/graph").json()
    assert len(g["nodes"]) == 3  # auto question + claim + counterclaim
    assert len(g["edges"]) == 1 and len(g["provenance"]) == 1
    md = client.get(f"/api/projects/{pid}/export.md").text
    assert "自由は非支配である" in md and "Pettit 1997" in md
    ld = client.get(f"/api/projects/{pid}/export.jsonld").json()
    assert any(n.get("@type") == "Counterclaim" for n in ld["@graph"])


def test_validation():
    pid = client.post("/api/projects", json={"title": "v"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/nodes",
                       json={"type": "bogus", "title": "x"}).status_code == 400
    assert client.post(f"/api/projects/{pid}/nodes",
                       json={"type": "claim", "title": "x",
                             "confidence": "certain!!"}).status_code == 400


def test_counter_level0_offline():
    # OpenAlex search may fail offline; level0 must still return perspectives.
    r = client.post("/api/counter", json={"claim": "LLMs are inorganic organs", "lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["level0"]) >= 5
    assert body["level2"] is None  # no key supplied


def test_levels_seed():
    r = client.get("/api/levels?concept=自由")
    assert r.status_code == 200 and "elementary" in r.json()["levels"]
    assert client.get("/api/levels?concept=未収録概念").status_code == 404
