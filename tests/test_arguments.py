"""Offline Level-0 tests for argument reconstruction (E1-E5): P1..C standard
form, hidden premises, voice, per-premise locator, and — critically — validity
kept SEPARATE from soundness. No network, no LLM key (axiom 5)."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _new_project(title="論証テスト"):
    return client.post("/api/projects", json={"title": title}).json()["id"]


def _new_argument(pid, title="奴隷制廃止論", conclusion="ゆえに奴隷制は廃止すべきである"):
    return client.post(f"/api/projects/{pid}/arguments", json={
        "title": title, "conclusion": conclusion}).json()["id"]


def test_argument_standard_form_roundtrip():
    pid = _new_project()
    aid = _new_argument(pid)
    client.post(f"/api/arguments/{aid}/premises", json={
        "text": "すべての人間は自由への権利を持つ", "voice": "author",
        "locator": "Republic 514a"})
    client.post(f"/api/arguments/{aid}/premises", json={
        "text": "奴隷は人間である", "voice": "author"})
    client.post(f"/api/arguments/{aid}/premises", json={
        "text": "権利は等しく尊重されねばならない", "hidden": 1, "voice": "self"})
    a = client.get(f"/api/arguments/{aid}").json()
    seqs = [p["seq"] for p in a["premises"]]
    assert seqs == [1, 2, 3]
    assert a["premises"][2]["hidden"] == 1
    assert a["premises"][2]["voice"] == "self"
    assert a["premises"][0]["locator"] == "Republic 514a"
    # retrieved_at auto-stamped (axiom 4)
    assert a["premises"][0]["retrieved_at"]


def test_validity_soundness_independent():
    """妥当≠健全: an argument can be valid yet unsound. The two must be set and
    stored independently."""
    pid = _new_project()
    aid = _new_argument(pid)
    client.patch(f"/api/arguments/{aid}", json={"validity": "valid"})
    client.patch(f"/api/arguments/{aid}", json={"soundness": "unsound"})
    a = client.get(f"/api/arguments/{aid}").json()
    assert a["validity"] == "valid" and a["soundness"] == "unsound"


def test_reorder_premises():
    pid = _new_project()
    aid = _new_argument(pid)
    ids = [client.post(f"/api/arguments/{aid}/premises",
                       json={"text": f"P{i}"}).json()["id"] for i in range(3)]
    client.post(f"/api/arguments/{aid}/premises/reorder",
                json={"order": list(reversed(ids))})
    a = client.get(f"/api/arguments/{aid}").json()
    assert [p["id"] for p in a["premises"]] == list(reversed(ids))
    assert [p["seq"] for p in a["premises"]] == [1, 2, 3]


def test_export_contains_standard_form():
    pid = _new_project()
    aid = _new_argument(pid)
    client.post(f"/api/arguments/{aid}/premises",
                json={"text": "自由は非支配である", "hidden": 1})
    client.patch(f"/api/arguments/{aid}", json={"validity": "valid",
                                                "soundness": "unsound"})
    md = client.get(f"/api/projects/{pid}/export.md").text
    assert "P1." in md and "∴ C." in md and "[hidden]" in md
    assert "自由は非支配である" in md and "ゆえに奴隷制は廃止すべきである" in md
    assert "validity: **valid**" in md and "soundness: **unsound**" in md
    ld = client.get(f"/api/projects/{pid}/export.jsonld").json()
    args = [n for n in ld["@graph"] if n.get("@type") == "Argument"]
    assert args and args[0]["hasPremise"] and args[0]["validity"] == "valid"


def test_argument_vocab_validation():
    pid = _new_project()
    aid = _new_argument(pid)
    assert client.patch(f"/api/arguments/{aid}",
                        json={"validity": "kinda"}).status_code == 400
    assert client.patch(f"/api/arguments/{aid}",
                        json={"soundness": "meh"}).status_code == 400
    assert client.post(f"/api/arguments/{aid}/premises",
                       json={"text": "x", "voice": "narrator"}).status_code == 400


def test_provenance_locator_column():
    """The ALTER-TABLE migration must have added provenance.locator; a node
    provenance with a standard locator survives to export."""
    pid = _new_project()
    client.post(f"/api/projects/{pid}/nodes", json={
        "type": "claim", "title": "洞窟の比喩は認識論的である",
        "provenance": [{"source_name": "Plato Republic", "locator": "Republic 514a",
                        "source_url": "https://example.org"}]})
    md = client.get(f"/api/projects/{pid}/export.md").text
    assert "Republic 514a" in md


def test_suggest_hidden_requires_key():
    """Level 0 never requires AI: without a key the suggestion endpoint 400s,
    while adding a hidden premise by hand (the Level-0 path) works keyless."""
    pid = _new_project()
    aid = _new_argument(pid)
    assert client.post(f"/api/arguments/{aid}/suggest_hidden",
                       json={"lang": "en"}).status_code == 400
    # keyless Level-0 path still works:
    r = client.post(f"/api/arguments/{aid}/premises",
                    json={"text": "hidden by hand", "hidden": 1})
    assert r.status_code == 200


def test_project_page_renders_argument_panel():
    pid = _new_project()
    for lang in ("ja", "en"):
        html = client.get(f"/project/{pid}?lang={lang}").text
        assert "arg-title" in html and ("論証再構成" in html or "Argument reconstruction" in html)
