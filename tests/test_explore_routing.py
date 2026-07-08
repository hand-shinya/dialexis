"""Offline tests for tradition-routed exploration: a Japanese subject must route
orientation to the Japanese specialist indexes (NDL + CiNii), and SEP's fuzzy
fallback (共同幻想論 → 'Laozi') must be suppressed. No network needed — the unit
helpers are pure, and the endpoint returns the routing keys even when the live
sources error offline."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app, orientation_plan, _sep_relevant, _has_cjk  # noqa: E402

client = TestClient(app)


def test_cinii_connector_shape():
    from app.connectors import cinii
    import inspect
    src = inspect.getsource(cinii.search)
    assert "items" in src and "format" in src and "cir.nii.ac.jp" in cinii.API


def test_has_cjk():
    assert _has_cjk("共同幻想論") and _has_cjk("ひらがな") and _has_cjk("カタカナ")
    assert not _has_cjk("freedom") and not _has_cjk("Sein und Zeit")


def test_orientation_routing():
    jp = orientation_plan("共同幻想論", None)
    assert jp["tradition"] == "japanese" and jp["ndl"] and jp["cinii"]
    we = orientation_plan("freedom", None)
    assert we["tradition"] == "western" and not we["ndl"] and not we["cinii"]
    assert we["sep"] and jp["sep"]  # SEP is always attempted (then gated)


def test_sep_relevance_gate():
    # The reported bug: 共同幻想論 resolved (or not) into an unrelated SEP entry.
    assert _sep_relevant("Laozi", "Communal Illusion") is False
    assert _sep_relevant("Laozi", "共同幻想論") is False       # CJK term, SEP is EN-only
    assert _sep_relevant("Freedom", "freedom") is True         # genuine match survives
    assert _sep_relevant("Positive and Negative Liberty", "liberty") is True


def test_explore_returns_routing_keys():
    # The endpoint must expose orientation + the Japanese-source keys regardless
    # of whether the live sources are reachable (offline → error envelopes, keys
    # still present). Routing is deterministic from the query script.
    d = client.get("/api/explore", params={"q": "共同幻想論", "lang": "ja"}).json()
    assert d["orientation"]["tradition"] == "japanese"
    assert "japanese_scholarship" in d and "cinii" in d
    w = client.get("/api/explore", params={"q": "freedom", "lang": "en"}).json()
    assert w["orientation"]["tradition"] == "western"
