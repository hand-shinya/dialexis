"""匿名の報告窓口の試験（2026-10-10）。

なぜ在るか:
  公開repoのIssuesへのlinkを外したので、報告の窓口が無くなっていた。
  外部serviceやaccountを使うと、所有者の名へ繋がる経路か、第三者への文の受け渡しが生じる。
  app の中で受ける形にして、鍵も費用も第三者も要らないようにした。

この窓口が保証すること:
  保存するのは本文・種別・画面・時刻・参照番号だけである。
  名前・連絡先・IPaddress・workspace の識別子は**列として持たない**。
  持たない列には、後から「うっかり入れる」ことができない。
  参照番号を知る人は状態だけ見られる。本文は返らない。
  一覧の endpoint は存在しない（認証機構が無い公開instanceで他人の文が読める面を作らない）。

この窓口が保証しないこと（公理3）:
  報告の内容が正しいこと。報告が本物の利用者から来たこと。
  連絡先を持たないので返信はできない。

外部取得なし。
"""
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
BODY = "wordspaceで取得時刻が出ない面がありました。再現手順はこうです。"


@pytest.fixture()
def client():
    return TestClient(app)


def send(client, **kw):
    kw.setdefault("body", BODY)
    return client.post("/api/report", json=kw)


# ===========================================================================
# 受け取り
# ===========================================================================

def test_the_page_is_served(client):
    """TestClient は Accept-Language を送らないので既定は英語である。両方を見る。"""
    for lang, mark in (("ja", "匿名"), ("en", "anonymous")):
        r = client.get("/report?lang=" + lang)
        assert r.status_code == 200, lang
        assert mark in r.text, lang


@pytest.mark.parametrize("lang,keys", [
    ("ja", ("保存するもの", "保存しないもの", "IPaddress",
            "workspace の識別子", "連絡先")),
    ("en", ("Stored", "Not stored", "IP address",
            "workspace identifier", "contact")),
])
def test_the_page_states_what_is_and_is_not_stored(client, lang, keys):
    body = client.get("/report?lang=" + lang).text
    for k in keys:
        assert k in body, (lang, k)


def test_a_report_is_accepted_and_returns_a_code(client):
    r = send(client, kind=db.REPORT_KINDS[0], page="/wordspace")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert re.fullmatch(r"[0-9A-F]{8}", d["code"]), d["code"]


def test_a_short_body_is_refused(client):
    assert send(client, body="短い").status_code == 400
    assert send(client, body="   ").status_code == 400
    assert client.post("/api/report", json={}).status_code == 400


def test_an_unknown_kind_falls_back_to_other(client):
    d = send(client, kind="でっちあげの種別").json()
    s = client.get("/api/report/" + d["code"]).json()
    assert s["kind"] == db.REPORT_KINDS[-1]


def test_the_response_declares_what_was_stored(client):
    d = send(client).json()
    assert "本文" in d["stored"] and "参照番号" in d["stored"]
    for k in ("名前", "連絡先", "IPaddress", "workspace の識別子"):
        assert k in d["not_stored"], k
    assert "返信はしません" in d["no_reply"]


def test_a_long_body_is_capped_not_refused(client):
    d = send(client, body="あ" * 9000).json()
    assert d["ok"] is True


# ===========================================================================
# 保存しないものを、列として持たない（公理6: 外部に置く）
# ===========================================================================

def test_the_table_has_no_column_for_identifying_data():
    """列が無ければ、後から入れることができない。"""
    with db.get_conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(reports)")}
    assert cols == {"id", "ts", "code", "kind", "page", "body", "context",
                    "status", "handled_at"}, cols
    for bad in ("workspace_id", "ip", "ip_address", "email", "contact", "name",
                "user_agent", "referer"):
        assert bad not in cols, bad


def test_the_stored_row_contains_only_what_was_declared(client):
    d = send(client, kind=db.REPORT_KINDS[0], page="/wordspace").json()
    with db.get_conn() as conn:
        rows = db.rows(conn.execute("SELECT * FROM reports WHERE code=?", (d["code"],)))
    assert len(rows) == 1
    row = rows[0]
    assert row["body"] == BODY
    assert row["page"] == "/wordspace"
    assert row["status"] == "open"
    assert row["handled_at"] == ""
    assert row["context"] == ""        # 添付を選んでいないので空


def test_an_attachment_is_stored_only_when_the_user_sends_one(client):
    ctx = [{"layer": "Wikipedia全文検索", "query_sent": "理性", "count": 5}]
    d = send(client, context=ctx).json()
    assert "添付した受領証" in d["stored"]
    with db.get_conn() as conn:
        row = db.rows(conn.execute("SELECT context FROM reports WHERE code=?",
                                   (d["code"],)))[0]
    assert "Wikipedia" in row["context"]


# ===========================================================================
# 参照番号（本文は返さない）
# ===========================================================================

def test_the_status_lookup_never_returns_the_body(client):
    d = send(client).json()
    r = client.get("/api/report/" + d["code"])
    assert r.status_code == 200
    assert BODY not in r.text
    assert "body" not in r.json()


def test_an_unknown_code_says_so_without_a_dead_end(client):
    d = client.get("/api/report/DEADBEEF").json()
    assert d["found"] is False
    assert "確かめて" in d["note"] or "もう一度" in d["note"]


def test_a_malformed_code_does_not_crash(client):
    for bad in ("../../etc/passwd", "'; DROP TABLE reports;--", "%00", "x" * 200):
        r = client.get("/api/report/" + bad)
        assert r.status_code in (200, 404), (bad, r.status_code)
    # tableが残っていること（注入で消えていない）
    with db.get_conn() as conn:
        conn.execute("SELECT COUNT(*) FROM reports")


# ===========================================================================
# 一覧の面を作らないこと
# ===========================================================================

def test_there_is_no_endpoint_that_lists_other_peoples_reports(client):
    """認証機構が無いので、一覧を出すと他の利用者の文が読める面になる。"""
    for path in ("/api/reports", "/api/report", "/reports", "/api/report/all"):
        r = client.get(path)
        assert r.status_code != 200 or BODY not in r.text, path


def test_the_owner_reads_them_with_a_tool_not_an_endpoint():
    t = ROOT / "tools" / "read_reports.py"
    assert t.exists()
    src = t.read_text(encoding="utf-8")
    assert "認証機構が無い" in src
    assert "--close" in src and "--read" in src


# ===========================================================================
# どの画面からでも届くこと
# ===========================================================================

@pytest.mark.parametrize("path", ["/", "/origin", "/wordspace", "/validation", "/inquiry"])
def test_every_page_offers_the_channel(client, path):
    r = client.get(path)
    if r.status_code != 200:
        pytest.skip("%s は %d を返す" % (path, r.status_code))
    assert 'href="/report"' in r.text or 'href="/report?' in r.text, path


def test_validation_links_with_the_page_prefilled(client):
    assert 'href="/report?page=/validation"' in client.get("/validation").text
