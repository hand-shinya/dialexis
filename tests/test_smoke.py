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


def test_openalex_philosophy_lens():
    # The humanities lens must be present in the request params so a common CJK
    # word cannot pull in natural-science papers (the 存在→chemistry bug).
    from app.connectors import openalex
    assert openalex.HUMANITIES_LENS == openalex.PHILOSOPHY_LENS
    assert "subfield.id:1211" in openalex.PHILOSOPHY_LENS
    import inspect
    src = inspect.getsource(openalex.search_works)
    assert "lens" in src and "params[\"filter\"]" in src


def test_crossref_skips_untitled():
    from app.connectors import crossref
    import inspect
    assert "skip untitled" in inspect.getsource(crossref.search_works)


def test_deepsearch_prompt():
    # The generated prompt must embody the value proposition: true question,
    # term genealogy / lost distinctions, primary-source precision, bias check.
    svcs = client.get("/api/deepsearch/services").json()
    assert any(s["id"] == "perplexity" for s in svcs)
    r = client.post("/api/deepsearch", json={
        "topic": "非有機的肉体", "service": "perplexity", "lang": "ja"}).json()
    p = r["level0"]
    assert "非有機的肉体" in p
    for must in ["本当の問い", "失われた区別", "原語", "確定／高蓋然", "バイアス"]:
        assert must in p, must
    assert r["level2"] is None
    assert client.post("/api/deepsearch", json={"topic": "", "lang": "ja"}).status_code == 400


def test_standard_locator():
    # The reference unit of philosophy is the standard locator, not a DOI.
    r = client.get("/api/locator", params={"author": "Plato", "work": "Republic",
                                            "locator": "514a"}).json()
    assert r["result"]["scheme"] == "Stephanus"
    assert r["result"]["resolved"] and "perseus" in r["result"]["deep_link"]
    a = client.get("/api/locator", params={"author": "Aristotle",
                                            "work": "Nicomachean Ethics",
                                            "locator": "1094a1"}).json()
    assert a["result"]["scheme"] == "Bekker"
    assert any(s["author"] == "Kant" for s in r["schemes"])


def test_sep_connector_shape():
    # SEP is the real entry point; the connector must expose the debate map and
    # bibliography structure (network-independent structural check).
    from app.connectors import sep
    import inspect
    src = inspect.getsource(sep.entry)
    assert "sections" in src and "bibliography" in src and "related" in src


def test_levels_seed():
    r = client.get("/api/levels?concept=自由")
    assert r.status_code == 200 and "elementary" in r.json()["levels"]
    assert client.get("/api/levels?concept=未収録概念").status_code == 404
