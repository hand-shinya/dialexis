"""Research-ledger persistence and many-to-many project reuse tests."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "ledger-test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_one_ledger_can_be_reused_by_two_projects_without_copying_it():
    ledger = client.post("/api/ledgers", json={
        "title": "哲学の訳語史",
        "central_question": "philosophy は誰によって哲学へ移されたか",
        "subject": "哲学",
        "subject_type": "discipline",
    }).json()
    lid = ledger["ledger"]["id"]
    entry = client.post(f"/api/ledgers/{lid}/entries", json={
        "kind": "translation", "title": "philosophy＝哲学",
        "source_term": "philosophy", "target_term": "哲学",
        "source_language": "英語", "target_language": "日本語",
        "evidence_level": "bibliography_confirmed", "status": "candidate",
    }).json()
    eid = entry["id"]

    p1 = client.post("/api/projects", json={"title": "研究A"}).json()["id"]
    p2 = client.post("/api/projects", json={"title": "研究B"}).json()["id"]
    assert client.post(f"/api/projects/{p1}/ledgers", json={
        "ledger_id": lid, "role": "evidence"}).status_code == 200
    assert client.post(f"/api/projects/{p2}/ledgers", json={
        "ledger_id": lid, "role": "background"}).status_code == 200
    assert client.post(f"/api/projects/{p1}/ledger-entries", json={
        "entry_id": eid, "relation": "evidence"}).status_code == 200
    assert client.post(f"/api/projects/{p2}/ledger-entries", json={
        "entry_id": eid, "relation": "translation"}).status_code == 200

    detail = client.get(f"/api/ledgers/{lid}").json()
    assert detail["counts"]["projects"] == 2
    assert {p["id"] for p in detail["linked_projects"]} == {p1, p2}
    assert len(detail["entries"]) == 1

    assert len(client.get(f"/api/projects/{p1}/ledger-entries").json()) == 1
    assert len(client.get(f"/api/projects/{p2}/ledger-entries").json()) == 1
    graph = client.get(f"/api/projects/{p1}/graph").json()
    assert len(graph["ledgers"]) == 1 and len(graph["ledger_entries"]) == 1


def test_ledger_version_is_pinned_and_fork_keeps_parent_unchanged():
    created = client.post("/api/ledgers", json={"title": "親台帳", "subject": "共同幻想"}).json()
    lid = created["ledger"]["id"]
    before = client.get(f"/api/ledgers/{lid}").json()["ledger"]["version"]
    entry = client.post(f"/api/ledgers/{lid}/entries", json={
        "kind": "term", "title": "共同幻想", "evidence_level": "candidate"}).json()
    after = client.get(f"/api/ledgers/{lid}").json()
    assert after["ledger"]["version"] > before

    project = client.post("/api/projects", json={"title": "固定版を使う研究"}).json()["id"]
    assert client.post(f"/api/projects/{project}/ledgers", json={
        "ledger_id": lid, "pinned_version": after["ledger"]["version"]}).status_code == 200
    fork = client.post(f"/api/ledgers/{lid}/fork", json={"title": "子台帳"}).json()
    child = fork["ledger"]["id"]
    assert fork["ledger"]["parent_ledger_id"] == lid
    assert len(fork["entries"]) == 1

    client.patch(f"/api/ledger-entries/{entry['id']}", json={
        "status": "confirmed", "evidence_level": "dictionary_confirmed"})
    parent = client.get(f"/api/ledgers/{lid}").json()
    child_detail = client.get(f"/api/ledgers/{child}").json()
    assert parent["entries"][0]["status"] == "confirmed"
    assert child_detail["entries"][0]["status"] == "candidate"
    link = client.get(f"/api/projects/{project}/ledgers").json()[0]
    assert link["pinned_version"] < parent["ledger"]["version"]


def test_translation_history_can_be_saved_as_a_reusable_ledger():
    r = client.post("/api/ledgers/from-translation-history", json={
        "query": "非有機的肉体", "domain": "philosophy", "lang": "ja"})
    assert r.status_code == 200
    body = r.json()
    assert body["ledger"]["ledger"]["subject"] == "非有機的肉体"
    assert body["ledger"]["entries"]
    assert body["ledger"]["versions"]
