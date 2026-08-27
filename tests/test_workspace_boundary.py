"""Deterministic checks for the anonymous public-instance boundary.

These tests call the authorization helpers directly so they do not depend on
the host's ASGI thread-pool implementation.  The browser/HTTP contract is
covered by the deployment checklist in docs/PUBLIC_DEPLOYMENT_SECURITY.md.
"""
import os
import tempfile
from types import SimpleNamespace

from app import db, main
from starlette.responses import Response


class RequestLike:
    def __init__(self, token):
        self.cookies = {main.WORKSPACE_COOKIE: token}
        self.state = SimpleNamespace()


def test_signed_workspace_cookie_rejects_tampering():
    payload, token = main._new_workspace_token()
    assert payload
    assert main._workspace_from_cookie(token) == (payload, True)
    assert main._workspace_from_cookie(token + "x")[1] is False


def test_browser_record_redacts_owner_and_exposes_capability_only():
    row = {"id": 7, "title": "public", "workspace_id": "owner-secret"}
    visible = main._expose_workspace_record(row, "reader")
    owned = main._expose_workspace_record(row, "owner-secret")
    assert "workspace_id" not in visible
    assert visible["can_edit"] is False
    assert owned["can_edit"] is True


def test_public_flag_does_not_treat_string_false_as_public():
    assert main._public_flag(False) == 0
    assert main._public_flag("false") == 0
    assert main._public_flag("0") == 0
    assert main._public_flag(True) == 1
    assert main._public_flag("true") == 1


def test_vary_cookie_is_appended_without_discarding_existing_dimensions():
    response = Response()
    response.headers["Vary"] = "Accept-Encoding"
    main._append_vary(response, "Cookie")
    main._append_vary(response, "cookie")
    assert response.headers["Vary"] == "Accept-Encoding, Cookie"


def test_private_assets_are_isolated_and_public_assets_are_read_only(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "boundary.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(main, "_PUBLIC_INSTANCE", True)
    db.init_db()
    first, first_token = main._new_workspace_token()
    second, second_token = main._new_workspace_token()
    assert first != second
    conn = db.get_conn()
    private = conn.execute(
        "INSERT INTO projects(title, workspace_id) VALUES(?,?)",
        ("private", first)).lastrowid
    public = conn.execute(
        "INSERT INTO projects(title, is_public, workspace_id) VALUES(?,?,?)",
        ("public", 1, first)).lastrowid
    ledger = conn.execute(
        "INSERT INTO ledgers(title, workspace_id) VALUES(?,?)",
        ("private ledger", first)).lastrowid
    public_ledger = conn.execute(
        "INSERT INTO ledgers(title, is_public, workspace_id) VALUES(?,?,?)",
        ("public ledger", 1, first)).lastrowid
    conn.commit()
    try:
        own = RequestLike(first_token)
        other = RequestLike(second_token)
        assert main._project_or_404(conn, private, own)["title"] == "private"
        assert main._project_or_404(conn, public, other)["title"] == "public"
        assert main._ledger_or_404(conn, ledger, own)["title"] == "private ledger"
        assert main._ledger_or_404(conn, public_ledger, other)["title"] == "public ledger"
        own_projects = {item["id"]: item for item in main.list_projects(own)}
        other_projects = {item["id"]: item for item in main.list_projects(other)}
        assert "workspace_id" not in own_projects[private]
        assert own_projects[private]["can_edit"] is True
        assert public in other_projects and other_projects[public]["can_edit"] is False
        visible_ledgers = {item["id"]: item for item in main.list_ledgers(other)}
        assert "workspace_id" not in visible_ledgers[public_ledger]
        assert visible_ledgers[public_ledger]["can_edit"] is False
        public_detail = main._ledger_detail(conn, public_ledger, second)
        assert "workspace_id" not in public_detail["ledger"]
        assert public_detail["ledger"]["can_edit"] is False
        for resolver, ident in ((main._project_or_404, private),
                                (main._ledger_or_404, ledger)):
            try:
                resolver(conn, ident, other)
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 404
            else:
                raise AssertionError("private asset crossed workspace boundary")
        for resolver, ident in ((main._project_or_404, public),
                                (main._ledger_or_404, public_ledger)):
            try:
                resolver(conn, ident, other, write=True)
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 404
            else:
                raise AssertionError("public asset became writable by reader")
    finally:
        conn.close()
