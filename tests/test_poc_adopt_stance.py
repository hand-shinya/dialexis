"""PoC-0 (explore→adopt) and PoC-1 (reading-stance decision) rely ONLY on
existing endpoints and the fixed NODE_TYPES — no schema change. These offline
Level-0 tests pin the backend paths the two PoCs depend on, so a future edit
that breaks them fails loudly."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import db  # noqa: E402

client = TestClient(app)


def _project():
    return client.post("/api/projects", json={"title": "PoC"}).json()["id"]


def test_decision_is_a_valid_node_type():
    # PoC-1 records a stance choice as a `decision` node; it must be in the fixed vocab.
    assert "decision" in db.NODE_TYPES


def test_adopt_creates_source_node_with_provenance():
    # PoC-0: one click on a live search result becomes a grounded source node.
    pid = _project()
    r = client.post(f"/api/projects/{pid}/nodes", json={
        "type": "source", "title": "吉本隆明と『共同幻想論』", "origin": "external",
        "provenance": [{"source_name": "CiNii", "source_url": "https://cir.nii.ac.jp/x",
                        "retrieved_at": "2026-07-10T00:00:00+00:00"}]})
    assert r.status_code == 200
    g = client.get(f"/api/projects/{pid}/graph").json()
    node = next(n for n in g["nodes"] if n["type"] == "source")
    assert node["title"].startswith("吉本") and node["origin"] == "external"
    prov = [p for p in g["provenance"] if p["node_id"] == node["id"]]
    assert prov and prov[0]["source_name"] == "CiNii"
    # retrieved_at stamp is preserved end-to-end (GENESIS axiom 4).
    assert prov[0]["retrieved_at"] == "2026-07-10T00:00:00+00:00"


def test_stance_decision_node_recorded_with_rationale():
    # PoC-1: the pivotal stance choice lands as a grounded decision with its reach/blind-spot.
    pid = _project()
    r = client.post(f"/api/projects/{pid}/nodes", json={
        "type": "decision", "title": "読解の構え：系譜学（Foucault）",
        "body": "ゲート：歴史的な産物として\n射程：権力/知の生成\n死角：著者の意図は射程外",
        "origin": "human", "status": "adopted"})
    assert r.status_code == 200
    g = client.get(f"/api/projects/{pid}/graph").json()
    dec = next(n for n in g["nodes"] if n["type"] == "decision")
    assert "系譜学" in dec["title"] and dec["status"] == "adopted"
    assert "射程" in dec["body"] and "死角" in dec["body"]
